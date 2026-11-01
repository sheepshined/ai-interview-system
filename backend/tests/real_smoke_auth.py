"""v0.6 鉴权端到端冒烟 (手动): 验证 登录/无token 401/带token 200/注册/WS 握手拒绝。

前置: 后端已启动 (默认 127.0.0.1:8000; 端口不同时设 SMOKE_PORT 环境变量)。
"""
import asyncio
import json
import os
import sys

import httpx
import websockets

_PORT = os.getenv("SMOKE_PORT", "8000")
BASE_URL = f"http://127.0.0.1:{_PORT}"
WS_URL = f"ws://127.0.0.1:{_PORT}/ws/chat"


def main() -> None:
    ok = True

    # 1. 登录签发 JWT
    resp = httpx.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "123123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    assert len(token.split(".")) == 3
    print("[1] login OK, JWT issued")

    # 2. 无 token 访问受保护接口 → 401
    resp = httpx.get(f"{BASE_URL}/api/roles")
    assert resp.status_code == 401, f"expected 401, got {resp.status_code}"
    print("[2] /api/roles without token -> 401 OK")

    # 3. 伪造 token → 401
    resp = httpx.get(f"{BASE_URL}/api/roles", headers={"Authorization": "Bearer fake.token.here"})
    assert resp.status_code == 401
    print("[3] /api/roles with forged token -> 401 OK")

    # 4. 带有效 token → 200
    resp = httpx.get(f"{BASE_URL}/api/roles", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200 and resp.json()["success"] is True
    print(f"[4] /api/roles with valid token -> 200, {len(resp.json()['roles'])} roles")

    # 5. 注册新用户 + 新用户隔离 (看不到 admin 的会话)
    resp = httpx.post(f"{BASE_URL}/api/register", json={"username": "smoke_user", "password": "smoke12345"})
    if resp.status_code == 400 and "已被注册" in resp.json().get("message", ""):
        print("[5] smoke_user already registered (re-run), continue")
    else:
        assert resp.status_code == 200, resp.text
        print("[5] register OK")
    resp = httpx.post(f"{BASE_URL}/api/login", json={"username": "smoke_user", "password": "smoke12345"})
    assert resp.status_code == 200, resp.text
    smoke_token = resp.json()["token"]
    resp = httpx.get(f"{BASE_URL}/api/interviews", headers={"Authorization": f"Bearer {smoke_token}"})
    assert resp.status_code == 200 and resp.json()["interviews"] == []
    print("[6] new user sees empty /api/interviews (isolated) OK")

    # 6. WS 无 token 握手被拒
    async def ws_check() -> None:
        try:
            async with websockets.connect(WS_URL, open_timeout=5):
                pass
            raise AssertionError("WS without token should be rejected")
        except websockets.exceptions.InvalidStatus as exc:
            assert exc.response.status_code == 403, f"expected 403, got {exc.response.status_code}"
        # 有效 token 可正常握手并收到错误提示(config 前发消息)
        async with websockets.connect(f"{WS_URL}?token={token}", open_timeout=5) as ws:
            await ws.send(json.dumps({"type": "unknown"}))
            data = json.loads(await ws.recv())
            assert data["type"] == "error"

    asyncio.run(ws_check())
    print("[7] WS handshake: no-token rejected (403), valid token accepted OK")
    print("\nAll auth smoke checks passed.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)
