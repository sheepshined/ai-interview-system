import hashlib

import pytest

from resume import store


@pytest.fixture(autouse=True)
def _db(tmp_path):
    store.init_db(str(tmp_path / "resumes.db"))


def _content(name="张三"):
    return {
        "name": name,
        "phone": "13800138000",
        "email": "zhang@example.com",
        "location": "上海",
        "summary": "后端工程师",
        "skills": ["Python", "FastAPI"],
        "experience": "甲公司 后端工程师",
        "projects": "面试系统",
        "education": "某大学 计算机 本科",
    }


def test_create_update_confirm_preserves_raw_text():
    raw = "张三 13800138000 zhang@example.com 上海 Python FastAPI 后端工程师 甲公司 后端工程师 面试系统 某大学 计算机 本科"
    created = store.create_resume("alice", raw, _content())
    assert created["is_master"] is True
    changed = _content("张三（已核对）")
    updated = store.update_content("alice", created["id"], changed, "主简历")
    assert updated["parsed_data"] == raw
    assert updated["content"]["name"] == "张三（已核对）"
    assert updated["import_review"] == {}

    confirmed = store.confirm_import("alice", created["id"])
    assert confirmed["parse_status"] == "reviewed"
    assert confirmed["import_review"]["raw_text_sha256"] == hashlib.sha256(raw.encode()).hexdigest()


def test_user_isolation_and_merge_empty():
    item = store.create_resume("alice", "张三 Python", _content())
    assert store.get_resume("bob", item["id"]) is None
    assert store.list_resumes("bob") == []
    merged = store.merge_empty({"name": "用户修改", "skills": []}, _content())
    assert merged["name"] == "用户修改"
    assert merged["skills"] == ["Python", "FastAPI"]


def test_evidence_never_trusts_fabricated_values():
    evidence = store.build_evidence("张三熟悉 Python", _content())
    assert {item["value"] for item in evidence} == {"张三", "Python"}
    assert store.validate_evidence("张三熟悉 Python", [
        {"path": "/skills/0", "value": "Kubernetes", "evidence": "Python"},
    ]) == []
