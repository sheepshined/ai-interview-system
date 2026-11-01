"""个人知识库测试 (v0.7): notes CRUD + [[链接]]解析 + 图谱 + 反链 + 报告入库。

运行环境由 tests/conftest.py 隔离 (KB_DB_PATH 指向临时目录)。
"""
import pytest
from fastapi.testclient import TestClient

import knowledge

from server import app

client = TestClient(app)


def _login(username="admin", password="123123"):
    resp = client.post("/api/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(autouse=True)
def headers():
    """每个用例用独立用户, 避免用例间数据串扰。"""
    import itertools
    counter = getattr(headers, "_counter", itertools.count())
    headers._counter = counter
    username = f"kbuser{next(counter)}"
    resp = client.post(
        "/api/register", json={"username": username, "password": "pass12345"}
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _create(headers, title, content="", tags=None):
    resp = client.post(
        "/api/kb/notes",
        json={"title": title, "content": content, "tags": tags or []},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ============================================================
# 单元: 链接解析
# ============================================================

def test_parse_links_basic_and_dedup():
    content = "参考 [[快速排序]] 与 [[快速排序]], 还要看 [[时间复杂度]]"
    assert knowledge.parse_links(content) == ["快速排序", "时间复杂度"]


def test_parse_links_ignores_nested_and_multiline():
    assert knowledge.parse_links("[[a\nb]]") == []          # 换行不匹配
    # 嵌套括号: 引擎从第二个 [ 起匹配出 x
    assert knowledge.parse_links("[[[x]]]") == ["x"]
    assert knowledge.parse_links("普通文本") == []


# ============================================================
# API: CRUD
# ============================================================

def test_create_and_get_note(headers):
    created = _create(headers, "RAG 基础", "向量检索是 [[RAG]] 的核心", ["RAG"])
    assert created["success"] is True

    resp = client.get(f"/api/kb/notes/{created['id']}", headers=headers)
    assert resp.status_code == 200
    note = resp.json()["note"]
    assert note["title"] == "RAG 基础"
    assert note["links"] == ["RAG"]
    assert note["tags"] == ["RAG"]


def test_duplicate_title_rejected(headers):
    _create(headers, "唯一标题")
    resp = client.post(
        "/api/kb/notes", json={"title": "唯一标题"}, headers=headers
    )
    assert resp.status_code == 400
    assert "同名" in resp.json()["message"]


def test_update_and_delete(headers):
    note = _create(headers, "待更新", "旧内容")
    resp = client.put(
        f"/api/kb/notes/{note['id']}",
        json={"title": "已更新", "content": "新内容 [[目标]}", "tags": ["t1"]},
        headers=headers,
    )
    assert resp.status_code == 200

    resp = client.delete(f"/api/kb/notes/{note['id']}", headers=headers)
    assert resp.status_code == 200
    resp = client.get(f"/api/kb/notes/{note['id']}", headers=headers)
    assert resp.status_code == 404


def test_notes_isolated_between_users(headers):
    _create(headers, "admin 的私有笔记")
    other = _login("admin")   # 另一个用户(admin)看不到 kbuserX 的笔记
    resp = client.get("/api/kb/notes", headers=other)
    assert resp.status_code == 200
    titles = [n["title"] for n in resp.json()["notes"]]
    assert "admin 的私有笔记" not in titles


def test_kb_endpoints_require_token():
    for method, url in [("get", "/api/kb/notes"), ("get", "/api/kb/graph"),
                        ("post", "/api/kb/notes"), ("post", "/api/kb/notes/from-report")]:
        resp = getattr(client, method)(url, **({"json": {"title": "x"}} if method == "post" else {}))
        assert resp.status_code == 401, f"{url} 未带 token 应 401"


def test_search_and_tag_filter(headers):
    _create(headers, "Python 装饰器", "闭包相关", ["Python"])
    _create(headers, "Java 并发", "volatile", ["Java"])
    resp = client.get("/api/kb/notes", params={"search": "装饰"}, headers=headers)
    assert [n["title"] for n in resp.json()["notes"]] == ["Python 装饰器"]
    resp = client.get("/api/kb/notes", params={"tag": "Java"}, headers=headers)
    assert [n["title"] for n in resp.json()["notes"]] == ["Java 并发"]


# ============================================================
# 图谱与反链
# ============================================================

def test_graph_builds_nodes_edges_and_virtual(headers):
    _create(headers, "A", "看 [[B]] 和 [[不存在的C]]")
    _create(headers, "B", "回到 [[A]]")

    resp = client.get("/api/kb/graph", headers=headers)
    assert resp.status_code == 200
    graph = resp.json()["graph"]

    by_id = {n["id"]: n for n in graph["nodes"]}
    assert set(by_id) == {"A", "B", "不存在的C"}
    assert by_id["不存在的C"]["virtual"] is True
    assert by_id["不存在的C"]["note_id"] is None
    assert by_id["A"]["virtual"] is False
    # A: 出链 2 (B, C) + 入链 1 (B→A) = 3; B: 入 1 + 出 1 = 2; C: 入 1
    assert by_id["A"]["degree"] == 3
    assert by_id["B"]["degree"] == 2
    assert by_id["不存在的C"]["degree"] == 1

    edge_pairs = {(e["source"], e["target"], e["virtual"]) for e in graph["edges"]}
    assert ("A", "B", False) in edge_pairs
    assert ("A", "不存在的C", True) in edge_pairs


def test_backlinks(headers):
    a = _create(headers, "目标笔记", "内容")
    _create(headers, "来源1", "链接到 [[目标笔记]]")
    _create(headers, "来源2", "没有链接")
    resp = client.get(f"/api/kb/notes/{a['id']}", headers=headers)
    backlinks = resp.json()["backlinks"]
    assert [b["title"] for b in backlinks] == ["来源1"]


def test_self_link_ignored_in_graph(headers):
    _create(headers, "自环", "链接自己 [[自环]]")
    graph = client.get("/api/kb/graph", headers=headers).json()["graph"]
    assert graph["edges"] == []
    assert graph["nodes"][0]["degree"] == 0


# ============================================================
# 报告薄弱点入库
# ============================================================

def test_import_from_report(headers):
    resp = client.post(
        "/api/kb/notes/from-report",
        json={
            "report_id": "rpt_001",
            "items": [
                {"topic": "MySQL 索引", "suggestion": "学习 B+ 树结构"},
                {"topic": "Redis 持久化", "suggestion": "对比 RDB 与 AOF"},
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["created"]) == 2
    assert data["skipped"] == []

    # 笔记带 source 与标签
    note = client.get(
        f"/api/kb/notes/{data['created'][0]['id']}", headers=headers
    ).json()["note"]
    assert note["source"] == "interview_report"
    assert "面试薄弱点" in note["tags"]
    assert "rpt_001" in note["content"]


def test_import_from_report_skips_existing(headers):
    _create(headers, "MySQL 索引", "已有笔记")
    resp = client.post(
        "/api/kb/notes/from-report",
        json={"items": [{"topic": "MySQL 索引", "suggestion": "again"}]},
        headers=headers,
    )
    data = resp.json()
    assert data["created"] == []
    assert data["skipped"] == ["MySQL 索引"]
