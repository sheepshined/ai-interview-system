"""
auth.py — 用户认证模块 (SQLite 用户表 + bcrypt 密码哈希 + JWT)

v0.6 引入, 替代原先"固定账号 admin/123123 + MD5 token + 后端不校验"的演示级登录:
  - 用户存 SQLite (默认 backend/users.db, 可用 AUTH_DB_PATH 覆盖), 密码 bcrypt 哈希
  - 首次启动自动建表并预置演示账号 admin/123123 (答辩兼容)
  - 登录成功签发 JWT (HS256, 默认 24h 过期), 所有 REST 接口与 WS 握手均校验
  - JWT 密钥: 优先 .env 的 JWT_SECRET_KEY; 未配置则自动生成并落盘 .jwt_secret 复用

公开接口: POST /api/login、POST /api/register; 其余 REST 与 /ws/chat 均需 Bearer token。
"""
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config

ALGORITHM = "HS256"
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")

# HTTPBearer(auto_error=False): 缺头/格式错时由我们自己抛 401 (而非默认 403)
_bearer_scheme = HTTPBearer(auto_error=False)


# ============================================================
# JWT 密钥管理
# ============================================================

def _load_or_create_secret() -> str:
    """读取签名密钥: .env 优先, 否则自动生成并持久化到 backend/.jwt_secret"""
    if config.JWT_SECRET_KEY:
        return config.JWT_SECRET_KEY
    secret_path = os.path.join(config.BASE_DIR, ".jwt_secret")
    try:
        if os.path.isfile(secret_path):
            with open(secret_path, encoding="utf-8") as f:
                existing = f.read().strip()
                if existing:
                    return existing
        generated = secrets.token_hex(32)
        with open(secret_path, "w", encoding="utf-8") as f:
            f.write(generated)
        return generated
    except OSError:
        # 文件不可用时退化为进程内随机密钥 (重启后旧 token 全部失效)
        return secrets.token_hex(32)


_SECRET_KEY = _load_or_create_secret()


# ============================================================
# SQLite 用户表
# ============================================================

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.AUTH_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """建表; 空库时预置演示账号 admin/123123 (管理员角色)。旧库自动迁移 role/enabled 列。"""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # v1.3: 角色分级 (admin 可管理用户与题库) 与停用开关; 旧库幂等补列
        existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "role" not in existing_cols:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        if "enabled" not in existing_cols:
            conn.execute("ALTER TABLE users ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
        # 演示账号 admin 固定为管理员 (旧库幂等补齐, 不覆盖用户自建的同名角色)
        conn.execute("UPDATE users SET role = 'admin' WHERE username = 'admin' AND role != 'admin'")
        # v0.9: 登出吊销黑名单 (存 token 摘要, 不存原文)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                exp INTEGER NOT NULL
            )
            """
        )
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        if row[0] == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
                ("admin", hash_password("123123"), _now_iso()),
            )


def _token_digest(token: str) -> str:
    import hashlib
    return hashlib.sha256(f"{_SECRET_KEY}:{token}".encode("utf-8")).hexdigest()


def revoke_token(token: str) -> bool:
    """登出吊销: 把 token 摘要写进黑名单, 到期后可清理。"""
    try:
        payload = verify_token(token)
    except jwt.InvalidTokenError:
        return False
    with _connect() as conn:
        # 顺手清理已过期的黑名单项
        conn.execute("DELETE FROM revoked_tokens WHERE exp < ?",
                     (int(datetime.now(timezone.utc).timestamp()),))
        conn.execute(
            "INSERT OR REPLACE INTO revoked_tokens (token_hash, username, exp) VALUES (?, ?, ?)",
            (_token_digest(token), payload.get("username", ""), int(payload.get("exp", 0))),
        )
    return True


def is_revoked(token: str) -> bool:
    try:
        digest = _token_digest(token)
    except Exception:
        return False
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM revoked_tokens WHERE token_hash = ?", (digest,)
        ).fetchone()
    return row is not None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ============================================================
# 密码与用户操作
# ============================================================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def validate_credentials(username: str, password: str) -> Optional[str]:
    """校验用户名/密码格式, 返回错误信息 (None 表示合法)。"""
    if not _USERNAME_RE.fullmatch(username or ""):
        return "用户名须为 3-20 位字母、数字或下划线"
    # bcrypt 只取前 72 字节, 超长部分直接拒绝更安全
    if not password or len(password.encode("utf-8")) < 6:
        return "密码至少 6 位"
    if len(password.encode("utf-8")) > 72:
        return "密码过长 (最多 72 字节)"
    return None


def create_user(username: str, password: str, role: str = "user") -> dict:
    """注册新用户。用户名冲突时抛 ValueError。"""
    error = validate_credentials(username, password)
    if error:
        raise ValueError(error)
    if role not in ("admin", "user"):
        raise ValueError("非法角色")
    try:
        with _connect() as conn:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (username, hash_password(password), role, _now_iso()),
            )
            return {"id": cursor.lastrowid, "username": username, "role": role}
    except sqlite3.IntegrityError as exc:
        raise ValueError("用户名已被注册") from exc


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """校验账号密码, 成功返回 {id, username, role}; 失败/停用返回 None。"""
    if not username or not password:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, role, enabled FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    if not row["enabled"]:
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


# ============================================================
# 用户管理 (v1.3: 角色分级 / 改密码 / 停用)
# ============================================================

def get_user_record(username: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, role, enabled, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list:
    """全部用户 (按创建时间), 不含密码哈希。"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT username, role, enabled, created_at FROM users ORDER BY created_at, id"
        ).fetchall()
    return [dict(r) for r in rows]


def count_admins() -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND enabled = 1"
        ).fetchone()
    return row[0]


def verify_user_password(username: str, password: str) -> bool:
    """校验某用户的密码 (改密码前验证旧密码用)。"""
    if not username or not password:
        return False
    with _connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    return bool(row) and verify_password(password, row["password_hash"])


def update_password(username: str, new_password: str) -> None:
    """更新密码 (改密码与管理员重置共用); 用户不存在抛 ValueError。"""
    error = validate_credentials("abc123", new_password)  # 只用其密码规则
    if error:
        raise ValueError(error)
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hash_password(new_password), username),
        )
        if cursor.rowcount == 0:
            raise ValueError("用户不存在")


def set_user_enabled(username: str, enabled: bool) -> None:
    """停用/启用账号; 停用后该账号立即无法登录, 已签发 token 也一并失效。"""
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE users SET enabled = ? WHERE username = ?",
            (1 if enabled else 0, username),
        )
        if cursor.rowcount == 0:
            raise ValueError("用户不存在")


def set_user_role(username: str, role: str) -> None:
    if role not in ("admin", "user"):
        raise ValueError("非法角色")
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE users SET role = ? WHERE username = ?", (role, username)
        )
        if cursor.rowcount == 0:
            raise ValueError("用户不存在")


# ============================================================
# 登录限流 (进程内, 按 IP + 用户名维度计数)
# ============================================================
# 窗口内连续失败达到上限即锁定; 单进程部署足够, 多进程部署需换 Redis。
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 5 * 60
LOGIN_LOCK_SECONDS = 15 * 60

_login_lock = threading.Lock()
_login_failures: dict[str, Deque[float]] = defaultdict(deque)
_login_locked_until: dict[str, float] = {}


def _login_key(ip: str, username: str) -> str:
    return f"{ip or 'unknown'}::{(username or '').strip().lower()}"


def login_retry_after(ip: str, username: str) -> int:
    """账号仍处于锁定时返回剩余秒数, 否则返回 0。"""
    remain = _login_locked_until.get(_login_key(ip, username), 0) - time.time()
    return int(remain) + 1 if remain > 0 else 0


def record_login_failure(ip: str, username: str) -> None:
    """记录一次失败登录; 窗口内失败数达上限则锁定。

    顺带清扫: 锁定过期条目与空 deque 不再无限累积 (进程内字典防膨胀)。
    """
    key = _login_key(ip, username)
    now = time.time()
    with _login_lock:
        attempts = _login_failures[key]
        attempts.append(now)
        while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= LOGIN_MAX_FAILURES:
            _login_locked_until[key] = now + LOGIN_LOCK_SECONDS
        if len(_login_failures) > 1024 or len(_login_locked_until) > 1024:
            expired = [k for k, until in _login_locked_until.items() if until <= now]
            for k in expired:
                _login_locked_until.pop(k, None)
            empty = [k for k, q in _login_failures.items()
                     if not q or now - q[0] > LOGIN_WINDOW_SECONDS]
            for k in empty:
                _login_failures.pop(k, None)


def record_login_success(ip: str, username: str) -> None:
    """登录成功后清除该 IP+用户名的失败计数与锁定。"""
    key = _login_key(ip, username)
    with _login_lock:
        _login_failures.pop(key, None)
        _login_locked_until.pop(key, None)


# ============================================================
# 注册限流 (进程内, 按 IP 限制成功注册数)
# ============================================================
# 刷号的滥用面是"成功建号"而非校验失败, 因此只对成功注册计数;
# 校验失败不计数, 避免共享出口 IP 下一次手误锁死他人正常注册。
# 上限取 100/5min: 正常单人使用远达不到, 脚本批量建号会被有效节流。
REGISTER_MAX_PER_WINDOW = 100
REGISTER_WINDOW_SECONDS = 5 * 60

_register_lock = threading.Lock()
_register_times: dict[str, Deque[float]] = defaultdict(deque)


def _register_key(ip: str) -> str:
    return f"{ip or 'unknown'}::register"


def register_retry_after(ip: str) -> int:
    """当前 IP 的成功注册数达到窗口上限时, 返回需等待的秒数, 否则 0。"""
    key = _register_key(ip)
    now = time.time()
    with _register_lock:
        times = _register_times.get(key)
        if not times:
            return 0
        while times and now - times[0] > REGISTER_WINDOW_SECONDS:
            times.popleft()
        if len(times) >= REGISTER_MAX_PER_WINDOW:
            return int(REGISTER_WINDOW_SECONDS - (now - times[0])) + 1
        return 0


def record_register_success(ip: str) -> None:
    with _register_lock:
        times = _register_times[_register_key(ip)]
        times.append(time.time())
        while times and time.time() - times[0] > REGISTER_WINDOW_SECONDS:
            times.popleft()


# ============================================================
# JWT 签发与校验
# ============================================================

def _pw_fingerprint(username: str) -> str:
    """密码版本指纹: password_hash 的 sha256 前 16 位。

    写进 JWT claim, 改密码/管理员重置后旧 token 里的指纹与库中不符即失效——
    "改密码踢掉旧会话"不再依赖 24h 自然过期。
    """
    import hashlib
    with _connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        return ""
    return hashlib.sha256(row["password_hash"].encode("utf-8")).hexdigest()[:16]


def create_access_token(username: str, expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(hours=config.TOKEN_EXPIRE_HOURS))
    payload = {
        "sub": username,
        "username": username,
        "pw": _pw_fingerprint(username),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """校验并解析 JWT。无效/过期抛 jwt.InvalidTokenError 子类。"""
    return jwt.decode(token, _SECRET_KEY, algorithms=[ALGORITHM])


# ============================================================
# FastAPI 集成 (REST 依赖 + WS 握手)
# ============================================================

def get_user_from_token(token: str) -> Optional[dict]:
    """统一 token 校验: 吊销名单 → JWT 有效性 → 用户仍存在且未停用。
    成功返回 {id, username, role} (role 以数据库为准, 实时生效), 失败 None。"""
    if not token or is_revoked(token):
        return None
    try:
        payload = verify_token(token)
    except jwt.InvalidTokenError:
        return None
    username = payload.get("username") or payload.get("sub") or ""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, role, enabled FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        # 用户已被删除但 token 仍有效
        return None
    if not row["enabled"]:
        # 已停用账号: 已签发 token 一并失效
        return None
    # 密码版本指纹: 改密码/重置后, 旧 token 立即失效 (无该 claim 的旧版 token 同样拒绝)
    if payload.get("pw") != _pw_fingerprint(username):
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"] or "user"}


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """REST 接口鉴权依赖: Authorization: Bearer <jwt> → {id, username}。"""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未提供访问令牌，请先登录")
    user = get_user_from_token(credentials.credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="登录已过期或令牌无效，请重新登录")
    return user


def ws_authenticate(ws: WebSocket) -> Optional[dict]:
    """WebSocket 握手鉴权: query 参数 ?token=<jwt>。失败返回 None (由调用方关闭连接)。"""
    return get_user_from_token(ws.query_params.get("token", ""))
