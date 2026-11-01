"""角色分级与账号管理回归 (v1.3): 迁移/改密码/管理员端点/停用。"""

import sqlite3

import auth
import config
import server
from fastapi.testclient import TestClient


client = TestClient(server.app)


def _init_auth_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUTH_DB_PATH", str(tmp_path / "users.db"))
    auth.init_db()


def _login(username, password="password123"):
    return client.post("/api/login", json={"username": username, "password": password}).json()


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_admin(tmp_path, monkeypatch, username="role_admin"):
    _init_auth_db(tmp_path, monkeypatch)
    auth.create_user(username, "password123", role="admin")
    return _login(username)["token"]


def _make_user(username):
    auth.create_user(username, "password123")
    return _login(username)["token"]


def test_old_schema_migrates_and_admin_bootstraps(tmp_path, monkeypatch):
    """旧 users.db (无 role/enabled 列) 幂等迁移; admin 账号自动补为管理员。"""
    db_path = str(tmp_path / "users.db")
    monkeypatch.setattr(config, "AUTH_DB_PATH", db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, "
                 "created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO users (username, password_hash, created_at) VALUES "
                 "('admin', 'x', '2026-01-01'), ('alice', 'y', '2026-01-02')")
    conn.commit()
    conn.close()

    auth.init_db()
    record = auth.get_user_record("admin")
    assert record["role"] == "admin" and record["enabled"] == 1
    assert auth.get_user_record("alice")["role"] == "user"


def test_login_and_me_carry_role(tmp_path, monkeypatch):
    _init_auth_db(tmp_path, monkeypatch)
    result = _login("admin", "123123")
    assert result["success"] and result["role"] == "admin"

    me = client.get("/api/account/me", headers=_headers(result["token"])).json()
    assert me["success"] and me["role"] == "admin" and me["username"] == "admin"


def test_change_password_requires_old_and_rules(tmp_path, monkeypatch):
    token = _make_admin(tmp_path, monkeypatch)
    # 旧密码错误
    bad = client.post("/api/account/password",
                      json={"old_password": "wrong_old", "new_password": "newpass66"},
                      headers=_headers(token))
    assert bad.status_code == 400
    # 新密码过短
    short = client.post("/api/account/password",
                        json={"old_password": "password123", "new_password": "123"},
                        headers=_headers(token))
    assert short.status_code == 400
    # 正确修改
    ok = client.post("/api/account/password",
                     json={"old_password": "password123", "new_password": "newpass66"},
                     headers=_headers(token))
    assert ok.status_code == 200
    assert auth.authenticate_user("role_admin", "newpass66") is not None
    assert auth.authenticate_user("role_admin", "password123") is None


def test_admin_endpoints_reject_non_admin(tmp_path, monkeypatch):
    _init_auth_db(tmp_path, monkeypatch)
    user_token = _make_user("plain_user")
    for method, url in (("get", "/api/admin/users"),
                        ("post", "/api/admin/users/someone/enabled"),
                        ("get", "/api/admin/qbank/stats"),
                        ("post", "/api/admin/qbank/rebuild")):
        resp = getattr(client, method)(url, headers=_headers(user_token),
                                       **({"json": {"enabled": True}} if method == "post" else {}))
        assert resp.status_code == 403, url


def test_user_management_lifecycle(tmp_path, monkeypatch):
    token = _make_admin(tmp_path, monkeypatch)
    _make_user("managee")

    # 列表
    listing = client.get("/api/admin/users", headers=_headers(token)).json()
    names = {u["username"] for u in listing["users"]}
    assert {"role_admin", "managee"} <= names

    # 重置密码 → 新密码可登录
    reset = client.post("/api/admin/users/managee/password",
                        json={"new_password": "resetpass9"}, headers=_headers(token))
    assert reset.status_code == 200
    assert _login("managee", "resetpass9")["success"] is True

    # 停用 → 登录拒绝 + 已有 token 立即失效
    user_token = _login("managee", "resetpass9")["token"]
    disable = client.post("/api/admin/users/managee/enabled",
                          json={"enabled": False}, headers=_headers(token))
    assert disable.status_code == 200
    assert _login("managee", "resetpass9")["success"] is False
    me = client.get("/api/account/me", headers=_headers(user_token))
    assert me.status_code == 401

    # 不能停用/降级自己
    self_disable = client.post(f"/api/admin/users/role_admin/enabled",
                               json={"enabled": False}, headers=_headers(token))
    assert self_disable.status_code == 400

    # 最后一个管理员不可降级/停用: 只留 managee 一个启用管理员
    client.post("/api/admin/users/managee/enabled",
                json={"enabled": True}, headers=_headers(token))
    auth.set_user_role("managee", "admin")
    auth.set_user_enabled("role_admin", False)  # 只剩 managee 一个启用管理员
    managee_token = _login("managee", "resetpass9")["token"]
    demote = client.post("/api/admin/users/managee/role",
                         json={"role": "user"}, headers=_headers(managee_token))
    assert demote.status_code == 400
    demote2 = client.post("/api/admin/users/managee/enabled",
                          json={"enabled": False}, headers=_headers(managee_token))
    assert demote2.status_code == 400


def test_disabled_user_cannot_authenticate_at_module_level(tmp_path, monkeypatch):
    _init_auth_db(tmp_path, monkeypatch)
    auth.create_user("disabled_u", "password123")
    assert auth.authenticate_user("disabled_u", "password123") is not None
    auth.set_user_enabled("disabled_u", False)
    assert auth.authenticate_user("disabled_u", "password123") is None
    auth.set_user_enabled("disabled_u", True)
    assert auth.authenticate_user("disabled_u", "password123") is not None


def test_password_change_revokes_existing_tokens(tmp_path, monkeypatch):
    """第一轮审查 P0-2: 改密码后旧 token 立即失效, 新 token 正常。"""
    _init_auth_db(tmp_path, monkeypatch)
    auth.create_user("pwv_user", "password123")
    old_token = auth.create_access_token("pwv_user")
    assert auth.get_user_from_token(old_token) is not None

    auth.update_password("pwv_user", "newpass66")
    assert auth.get_user_from_token(old_token) is None  # 旧 token 立即失效
    new_token = auth.create_access_token("pwv_user")
    assert auth.get_user_from_token(new_token) is not None


def test_register_rate_limited(tmp_path, monkeypatch):
    """注册限成功注册数 (防批量刷号); 校验失败不计数。测试用小窗口并自清理。"""
    _init_auth_db(tmp_path, monkeypatch)
    auth._register_times.clear()  # 套件内前序用例可能已占用同 IP 窗口
    monkeypatch.setattr(auth, "REGISTER_MAX_PER_WINDOW", 2)
    # 校验失败不消耗窗口 (空窗口下 400 而非 429)
    bad = client.post("/api/register", json={"username": "reg_d", "password": "x"})
    assert bad.status_code == 400
    r1 = client.post("/api/register", json={"username": "reg_a", "password": "pass12345"})
    r2 = client.post("/api/register", json={"username": "reg_b", "password": "pass12345"})
    assert r1.status_code == 200 and r2.status_code == 200
    r3 = client.post("/api/register", json={"username": "reg_c", "password": "pass12345"})
    assert r3.status_code == 429  # 成功数达上限, 后续请求 (含无效) 一并拒绝
    auth._register_times.clear()  # 清理本测试占用的 IP 窗口, 不影响后续用例
