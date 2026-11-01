"""认证模块测试 (v0.6): SQLite 用户表 + bcrypt + JWT + 接口鉴权。

运行环境由 tests/conftest.py 隔离 (临时用户库 + 固定测试密钥), 不碰开发库。
"""
import json
import os
import time
from datetime import timedelta

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

import auth
import config

from server import app

client = TestClient(app)


def _login(username="admin", password="123123"):
    return client.post("/api/login", json={"username": username, "password": password})


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 用户表与密码
# ============================================================

def test_init_db_seeds_demo_admin():
    user = auth.authenticate_user("admin", "123123")
    assert user is not None
    assert user["username"] == "admin"


def test_authenticate_rejects_wrong_password():
    assert auth.authenticate_user("admin", "wrong-pass") is None
    assert auth.authenticate_user("nobody", "123123") is None


def test_password_hashes_are_bcrypt_and_salted():
    h1 = auth.hash_password("secret123")
    h2 = auth.hash_password("secret123")
    assert h1 != h2                      # 盐随机
    assert h1.startswith("$2")           # bcrypt 格式
    assert auth.verify_password("secret123", h1)
    assert not auth.verify_password("other", h1)


def test_create_user_validates_credentials():
    with pytest.raises(ValueError):
        auth.create_user("ab", "password123")          # 用户名过短
    with pytest.raises(ValueError):
        auth.create_user("bad name!", "password123")   # 非法字符
    with pytest.raises(ValueError):
        auth.create_user("valid_user", "123")          # 密码过短


# ============================================================
# JWT 签发与校验
# ============================================================

def test_token_roundtrip():
    token = auth.create_access_token("alice")
    payload = auth.verify_token(token)
    assert payload["username"] == "alice"
    assert payload["exp"] > int(time.time())


def test_expired_token_rejected():
    token = auth.create_access_token("alice", expires_delta=timedelta(seconds=-10))
    with pytest.raises(pyjwt.InvalidTokenError):
        auth.verify_token(token)


def test_token_signed_with_wrong_key_rejected():
    forged = pyjwt.encode(
        {"username": "admin", "exp": int(time.time()) + 3600},
        "not-the-real-secret",
        algorithm="HS256",
    )
    with pytest.raises(pyjwt.InvalidTokenError):
        auth.verify_token(forged)


# ============================================================
# REST 接口鉴权
# ============================================================

def test_login_returns_jwt():
    resp = _login()
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    # JWT 形态: header.payload.signature
    assert len(payload["token"].split(".")) == 3


def test_login_wrong_password_401():
    resp = _login(password="nope")
    assert resp.status_code == 401
    assert resp.json()["success"] is False


def test_register_and_login_flow():
    resp = client.post(
        "/api/register", json={"username": "newuser1", "password": "abc12345"}
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 重复注册同名用户被拒
    dup = client.post(
        "/api/register", json={"username": "newuser1", "password": "abc12345"}
    )
    assert dup.status_code == 400
    assert "已被注册" in dup.json()["message"]

    # 新用户可登录
    login = _login("newuser1", "abc12345")
    assert login.status_code == 200


def test_protected_endpoints_require_token():
    for method, url in [
        ("get", "/api/roles"),
        ("get", "/api/reports"),
        ("get", "/api/interviews"),
        ("post", "/api/config"),
        ("post", "/api/resume/parse-text"),
    ]:
        resp = getattr(client, method)(url, **(
            {"json": {"role": "python_dev"}} if method == "post" else {}
        ))
        assert resp.status_code == 401, f"{url} 未带 token 应返回 401"


def test_roles_with_valid_token():
    token = _login().json()["token"]
    resp = client.get("/api/roles", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_roles_with_garbage_token_401():
    resp = client.get("/api/roles", headers=_auth_headers("garbage.token.value"))
    assert resp.status_code == 401


# ============================================================
# 报告按用户隔离
# ============================================================

def _write_report(report_id: str, username: str):
    meta = {"report_id": report_id, "username": username, "avg_score": 5.0}
    with open(
        os.path.join(config.REPORTS_DIR, f"{report_id}.json"), "w", encoding="utf-8"
    ) as f:
        json.dump(meta, f)
    with open(
        os.path.join(config.REPORTS_DIR, f"{report_id}.md"), "w", encoding="utf-8"
    ) as f:
        f.write("# report")


@pytest.fixture()
def isolated_reports(tmp_path, monkeypatch):
    """把报告目录指到临时目录, 测试后自动清理。"""
    monkeypatch.setattr(config, "REPORTS_DIR", str(tmp_path))
    return tmp_path


def test_report_list_isolated_by_user(isolated_reports):
    _write_report("r_admin", "admin")
    _write_report("r_alice", "alice")

    admin_token = _login().json()["token"]
    resp = client.get("/api/reports", headers=_auth_headers(admin_token))
    assert resp.status_code == 200
    ids = [r["report_id"] for r in resp.json()["reports"]]
    assert ids == ["r_admin"]            # 只看到自己的


def test_report_detail_denied_for_other_user(isolated_reports):
    _write_report("r_admin", "admin")

    client.post("/api/register", json={"username": "bob01", "password": "abc12345"})
    bob_token = _login("bob01", "abc12345").json()["token"]

    resp = client.get("/api/reports/r_admin", headers=_auth_headers(bob_token))
    assert resp.status_code == 404       # 他人报告不可见 (不泄露存在性)
    radar = client.get("/api/reports/r_admin/radar", headers=_auth_headers(bob_token))
    assert radar.status_code == 404

    admin_token = _login().json()["token"]
    ok = client.get("/api/reports/r_admin", headers=_auth_headers(admin_token))
    assert ok.status_code == 200


def test_legacy_report_without_username_belongs_to_admin(isolated_reports):
    _write_report("r_legacy", "")        # 旧报告无 username 字段
    client.post("/api/register", json={"username": "carol1", "password": "abc12345"})
    carol_token = _login("carol1", "abc12345").json()["token"]

    other = client.get("/api/reports", headers=_auth_headers(carol_token))
    assert other.json()["reports"] == []

    admin_token = _login().json()["token"]
    own = client.get("/api/reports", headers=_auth_headers(admin_token))
    assert [r["report_id"] for r in own.json()["reports"]] == ["r_legacy"]
