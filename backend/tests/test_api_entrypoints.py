"""REST API 入口测试 (v0.6 起接口需 Bearer JWT, 通过 conftest 隔离认证库)。"""
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def _auth_headers() -> dict:
    resp = client.post(
        "/api/login",
        json={"username": "admin", "password": "123123"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_demo_login_accepts_only_fixed_account():
    success = client.post(
        "/api/login",
        json={"username": "admin", "password": "123123"},
    )
    assert success.status_code == 200
    payload = success.json()
    assert payload["success"] is True
    assert payload["username"] == "admin"
    # v0.6: JWT (header.payload.signature), 不再是 MD5 hex
    assert len(payload["token"].split(".")) == 3

    rejected = client.post(
        "/api/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert rejected.status_code == 401
    assert rejected.json()["success"] is False


def test_roles_endpoint_returns_all_eight_roles():
    """/api/roles 应返回 config.ROLES 中定义的全部岗位 (需登录)。"""
    import config
    response = client.get("/api/roles", headers=_auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert len(payload["roles"]) == len(config.ROLES)
    assert len({role["key"] for role in payload["roles"]}) == len(config.ROLES)


def test_text_resume_endpoint_is_available():
    response = client.post(
        "/api/resume/parse-text",
        json={"content": "熟悉 LangChain、RAG 检索增强、Agent 工具调用与提示词工程, 有大模型应用落地经验"},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "LangChain" in payload["skills"]
    assert payload["suggested_role"]


def test_multipart_resume_endpoint_exists_and_validates_file_type():
    response = client.post(
        "/api/upload/resume",
        files={"file": ("resume.txt", b"plain text", "text/plain")},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    assert response.status_code != 404
    assert response.json() == {"success": False, "message": "仅支持 PDF 文件"}


def test_backend_root_no_longer_serves_frontend():
    response = client.get("/")
    assert response.status_code == 404
