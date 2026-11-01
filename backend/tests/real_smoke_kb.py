"""v0.7 知识库端到端冒烟 (手动): CRUD + 链接解析 + 图谱 + 反链 + 报告入库。

前置: 后端已启动 (默认 8000; 端口不同设 SMOKE_PORT)。
"""
import os
import sys

import httpx

BASE = f"http://127.0.0.1:{os.getenv('SMOKE_PORT', '8000')}"


def main():
    http = httpx.Client(base_url=BASE, timeout=15)

    # 登录独立测试用户
    uname = "kb_smoke_user"
    r = http.post("/api/login", json={"username": uname, "password": "kb12345"})
    if r.status_code != 200:
        r = http.post("/api/register", json={"username": uname, "password": "kb12345"})
        assert r.status_code == 200, r.text
        r = http.post("/api/login", json={"username": uname, "password": "kb12345"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    print("[1] login OK")

    # 未带 token 401
    assert http.get("/api/kb/notes").status_code == 401
    print("[2] /api/kb/notes without token -> 401 OK")

    # 建笔记 (带双链)
    r = http.post("/api/kb/notes", headers=h, json={
        "title": "冒烟-快速排序", "content": "分治, 参见 [[冒烟-时间复杂度]]",
        "tags": ["冒烟测试"],
    })
    assert r.status_code == 200, r.text
    nid = r.json()["id"]
    r = http.post("/api/kb/notes", headers=h, json={
        "title": "冒烟-时间复杂度", "content": "回到 [[冒烟-快速排序]] 与 [[冒烟-未创建]]",
    })
    assert r.status_code == 200
    print("[3] create 2 notes with [[links]] OK")

    # 图谱: 3 节点 (1 虚) 3 边
    g = http.get("/api/kb/graph", headers=h).json()["graph"]
    titles = {n["id"]: n for n in g["nodes"]}
    assert set(titles) == {"冒烟-快速排序", "冒烟-时间复杂度", "冒烟-未创建"}
    assert titles["冒烟-未创建"]["virtual"] is True
    assert len(g["edges"]) == 3
    print(f"[4] graph: {len(g['nodes'])} nodes (1 virtual), {len(g['edges'])} edges OK")

    # 反链
    r = http.get(f"/api/kb/notes/{nid}", headers=h).json()
    assert [b["title"] for b in r["backlinks"]] == ["冒烟-时间复杂度"]
    print("[5] backlinks OK")

    # 报告入库
    r = http.post("/api/kb/notes/from-report", headers=h, json={
        "report_id": "smoke_rpt",
        "items": [{"topic": "冒烟-MySQL索引", "suggestion": "学 B+ 树"}],
    })
    assert r.status_code == 200 and len(r.json()["created"]) == 1
    print("[6] import from report OK")

    # 清理
    for n in http.get("/api/kb/notes", headers=h).json()["notes"]:
        http.delete(f"/api/kb/notes/{n['id']}", headers=h)
    print("[7] cleanup OK")

    print("\nAll knowledge-base smoke checks passed.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)
