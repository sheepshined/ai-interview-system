"""题库管理回归 (v1.3): 校验/导入 roundtrip/删除/统计/运行时重建。"""

import asyncio
import json

import qbank_admin
from retrieval.kb_builder import parse_questions_from_file


def _good(i=1, **overrides):
    base = {
        "id": f"imp_test_{i:03d}",
        "category": "RAG",
        "difficulty": 2,
        "type": "scenario",
        "question": f"测试题面 {i}: 什么是混合检索?",
        "answer": "BM25 与向量双路召回, RRF 融合。",
        "scoring_points": ["说出双路", "说出 RRF"],
        "followup_directions": ["RRF 的 k 怎么取?"],
    }
    base.update(overrides)
    return base


def _write_md(path, questions):
    blocks = ["# 测试题库\n"]
    for q in questions:
        blocks.append(qbank_admin.render_question_markdown(q))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocks) + "\n")


def test_validate_rejects_bad_rows_and_duplicate_ids(tmp_path):
    existing = ["imp_test_001"]
    items = [
        _good(1),                                  # 与 existing 重复
        _good(2, question="   "),                  # 题面为空
        _good(3, answer=""),                       # 答案为空
        _good(4, difficulty=9),                    # 难度非法
        _good(5, type="weird"),                    # 类型非法
        _good(6), _good(6),                        # 批次内重复
        {"question": "只有题面没有答案"},            # 缺 answer
    ]
    normalized, errors = qbank_admin.validate_questions(items, existing)
    ids = {q["id"] for q in normalized}
    assert len(normalized) == 1
    assert "imp_test_006" in ids
    assert len(errors) == 7
    # 缺省 id 自动生成
    auto, _ = qbank_admin.validate_questions([{"question": "q", "answer": "a",
                                               "difficulty": 1, "type": "knowledge"}], [])
    assert auto[0]["id"].startswith("imp_")


def test_import_roundtrip_matches_builder_format(tmp_path):
    """写入的 markdown 必须能被 kb_builder 原样解析回结构化题目。"""
    md = str(tmp_path / "llm_app.md")
    _write_md(md, [])
    normalized, errors = qbank_admin.validate_questions(
        [_good(1), _good(2, category="微调 | 危险", difficulty=3)], [])
    assert not errors
    # 管道符应被清洗, 防止破坏元信息
    assert "|" not in normalized[1]["category"]

    report = qbank_admin.import_questions(md, [_good(1), normalized[1]], [], dry_run=False)
    assert report["written"] == 2
    # 空文件被补了文件头, 两次导入之间以 --- 块分隔
    parsed = {q["id"]: q for q in parse_questions_from_file(md)}
    assert set(parsed) == {"imp_test_001", "imp_test_002"}
    assert parsed["imp_test_001"]["scoring_points"] == ["说出双路", "说出 RRF"]
    assert parsed["imp_test_001"]["followup_directions"] == ["RRF 的 k 怎么取?"]
    assert parsed["imp_test_002"]["difficulty_label"] == "高级"

    # dry_run 不落盘
    before = open(md, encoding="utf-8").read()
    dry = qbank_admin.import_questions(md, [_good(9)], [], dry_run=True)
    assert dry["written"] == 0 and dry["validated"] == 1
    assert open(md, encoding="utf-8").read() == before


def test_import_appends_without_touching_existing(tmp_path):
    """真实题库场景: 已有题目块 + 文件头, 导入只追加不改旧块。"""
    md = str(tmp_path / "llm_app.md")
    old = qbank_admin.render_question_markdown(_good(1))
    with open(md, "w", encoding="utf-8") as f:
        f.write("# 大模型应用开发工程师面试题库\n\n" + old + "\n")
    report = qbank_admin.import_questions(md, [_good(2)], ["imp_test_001"])
    assert report["written"] == 1
    parsed = {q["id"]: q for q in parse_questions_from_file(md)}
    assert parsed["imp_test_001"]["answer"] == "BM25 与向量双路召回, RRF 融合。"
    assert parsed["imp_test_002"]["category"] == "RAG"


def test_delete_question_removes_exact_block(tmp_path):
    md_dir = str(tmp_path)
    md = str(tmp_path / "llm_app.md")
    _write_md(md, [_good(1, category="RAG"), _good(2, category="微调")])
    result = qbank_admin.delete_question(md_dir, "imp_test_002")
    assert result["deleted"] and result["source_file"] == "llm_app.md"
    parsed = {q["id"] for q in parse_questions_from_file(md)}
    assert parsed == {"imp_test_001"}

    assert qbank_admin.delete_question(md_dir, "no_such_id")["deleted"] is False


def test_stats_aggregation(tmp_path):
    questions = [
        _good(1, category="RAG", difficulty=1, type="knowledge"),
        _good(2, category="RAG", difficulty=2),
        _good(3, category="微调", difficulty=3),
    ]
    data = qbank_admin.stats(questions)
    assert data["total"] == 3
    assert data["categories"][0] == {"name": "RAG", "count": 2}
    assert data["difficulty"] == {"1": 1, "2": 1, "3": 1}
    assert data["type"]["scenario"] == 2 and data["type"]["knowledge"] == 1


def test_rebuild_index_invokes_builder_and_reload(tmp_path, monkeypatch):
    """运行时重建: 调 builder.build(force_recreate) 并触发检索器 reload; 解析为空时取消。"""
    import retrieval.kb_builder as kb_builder

    calls = {"build": 0, "force": None, "reload": 0}

    class StubBuilder:
        def __init__(self, data_dir=None, chroma_path=None):
            self.data_dir = data_dir

        def build(self, force_recreate=True):
            calls["build"] += 1
            calls["force"] = force_recreate
            return calls["build"] < 2  # 第二次返回 False 模拟解析为空

    class StubRetriever:
        def reload(self):
            calls["reload"] += 1

    monkeypatch.setattr(kb_builder, "KnowledgeBaseBuilder", StubBuilder)

    stub = StubRetriever()
    result = asyncio.run(qbank_admin.rebuild_index(lambda: stub, str(tmp_path), str(tmp_path / "chroma")))
    assert result["ok"] is True and calls["build"] == 1 and calls["force"] is True
    assert calls["reload"] == 1

    result2 = asyncio.run(qbank_admin.rebuild_index(lambda: stub, str(tmp_path), str(tmp_path / "chroma")))
    assert result2["ok"] is False and calls["reload"] == 1  # 失败路径不触发 reload


def test_import_api_admin_only_and_dry_run(tmp_path, monkeypatch):
    """API 层: 非 admin 403; dry_run 只校验; 全错时报 400 语义。"""
    import auth
    import config
    import server
    from fastapi.testclient import TestClient

    test_client = TestClient(server.app)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "AUTH_DB_PATH", str(tmp_path / "users.db"))
    auth.init_db()
    auth.create_user("api_admin", "password123", role="admin")
    auth.create_user("api_user", "password123")
    admin_h = {"Authorization": f"Bearer {auth.create_access_token('api_admin')}"}
    user_h = {"Authorization": f"Bearer {auth.create_access_token('api_user')}"}

    assert test_client.get("/api/admin/qbank/stats", headers=user_h).status_code == 403

    md = tmp_path / "llm_app.md"
    with open(md, "w", encoding="utf-8") as f:
        json.dump([], f)
    before = md.read_text(encoding="utf-8")

    dry = test_client.post("/api/admin/qbank/import",
                           json={"questions": [_good(1)], "dry_run": True},
                           headers=admin_h).json()
    assert dry["success"] and dry["written"] == 0 and dry["validated"] == 1
    assert md.read_text(encoding="utf-8") == before

    all_bad = test_client.post("/api/admin/qbank/import",
                               json={"questions": [{"question": "缺答案"}]},
                               headers=admin_h).json()
    assert all_bad["success"] is False

    real = test_client.post("/api/admin/qbank/import",
                            json={"questions": [_good(1)]}, headers=admin_h).json()
    assert real["written"] == 1
    assert "imp_test_001" in md.read_text(encoding="utf-8")


def test_validate_rejects_markdown_reserved_sequences(tmp_path):
    """第一轮审查 P0-1: 含保留序列的内容必须被拒, 杜绝"导入成功但重建后失真"。"""
    items = [
        {**_good(1), "answer": "前半答案\n---\n后半伪造块"},          # 劈开 --- 块
        {**_good(2), "question": "题面\n### A: 伪造答案顶替"},        # 伪造字段
        {**_good(3), "scoring_points": ["第一点\n第二点被截断"]},     # 列表项内部换行 → 清洗
        {**_good(4), "id": "bad|id"},                                # id 非法字符
        {**_good(5), "id": "x-->y"},                                 # id 截断元信息
    ]
    normalized, errors = qbank_admin.validate_questions(items, [])
    # 1/2/4/5 被拒, 3 通过且换行被清洗
    assert [q["id"] for q in normalized] == ["imp_test_003"]
    assert len(errors) == 4
    assert normalized[0]["scoring_points"] == ["第一点；第二点被截断"]
    # roundtrip: 通过校验的题写进文件再解析, 字段不变形
    md = str(tmp_path / "llm_app.md")
    _write_md(md, [])
    qbank_admin.import_questions(md, normalized, [])
    parsed = {q["id"]: q for q in parse_questions_from_file(md)}
    assert parsed["imp_test_003"]["scoring_points"] == ["第一点；第二点被截断"]
    assert parsed["imp_test_003"]["answer"] == "BM25 与向量双路召回, RRF 融合。"


def test_reserved_line_at_start_of_answer(tmp_path):
    """answer 整体以 --- 或 ### 开头同样被拒 (正则的 ^ 分支)。"""
    _, errors = qbank_admin.validate_questions(
        [{**_good(6), "answer": "---\n看起来像分隔线"}], [])
    assert len(errors) == 1 and "保留序列" in errors[0]


def test_validate_rejects_inline_field_hijack(tmp_path):
    """第二轮复审 R1: 行内 '### 字段:' 会劫持 kb_builder 未锚定的字段正则, 必须拒绝。"""
    items = [
        {**_good(1), "answer": "真答案\n(补充) ### S: 伪造得分点"},
        {**_good(2), "question": "题面 ### A: 伪造答案"},
        {**_good(3), "scenario": "场景 ### GOOD: 伪造好答案"},
    ]
    normalized, errors = qbank_admin.validate_questions(items, [])
    assert normalized == [] and len(errors) == 3
    # 行内 ### 但不是字段标记 (如标题级文字) 不误伤
    ok, errs = qbank_admin.validate_questions(
        [{**_good(4), "answer": "见第三章 ### 相关论述"}], [])
    assert ok and not errs


def test_validate_rejects_bad_list_items_and_edge_ids(tmp_path):
    """第二轮复审 R3/R4: 列表项被解析器吃前缀、尾横线 id 永远删不掉, 都在校验层拒绝。"""
    items = [
        {**_good(1), "scoring_points": ["- 前导横线的要点"]},
        {**_good(2), "good_points": ["---"]},
        {**_good(3), "id": "tricky-"},   # 尾横线: 删除定位的 \b 在横线+空格处失配
        {**_good(4), "id": "-lead"},     # 首横线同理拒绝
    ]
    normalized, errors = qbank_admin.validate_questions(items, [])
    assert normalized == [] and len(errors) == 4


def test_existing_ids_for_reads_under_lock(tmp_path):
    """existing_ids_for: 与导入共锁的 id 快照, 空文件/缺失文件返回空。"""
    md = str(tmp_path / "llm_app.md")
    assert qbank_admin.existing_ids_for(md) == []
    _write_md(md, [_good(1), _good(2)])
    assert qbank_admin.existing_ids_for(md) == ["imp_test_001", "imp_test_002"]
