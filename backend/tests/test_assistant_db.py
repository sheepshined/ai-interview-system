"""assistant.db 的表与 CRUD 单测 (不打 LLM, 不碰向量)。"""
import pytest

from assistant import db


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path):
    db.init_db(str(tmp_path / "assistant.db"))
    yield


def test_session_crud_and_cascade(tmp_path):
    sess = db.create_session("alice", "首轮")
    assert sess["id"] >= 1
    db.append_message(sess["id"], "user", "你好")
    db.append_message(sess["id"], "assistant", "在的", [{"tool": "x", "ok": True}])
    msgs = db.list_messages("alice", sess["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["tool_trace"] == [{"tool": "x", "ok": True}]
    # 越权读不到
    assert db.list_messages("bob", sess["id"]) == []
    assert db.get_session("bob", sess["id"]) is None
    # 级联删除
    assert db.delete_session("alice", sess["id"]) is True
    assert db.list_messages("alice", sess["id"]) == []
    assert db.delete_session("alice", sess["id"]) is False


def test_settings_validation():
    s = db.get_settings("alice")
    assert s["auto_accept_level"] == "read_auto" and s["memory_enabled"] is True
    db.put_settings("alice", auto_accept_level="all_confirm", memory_enabled=False)
    s = db.get_settings("alice")
    assert s["auto_accept_level"] == "all_confirm" and s["memory_enabled"] is False
    with pytest.raises(ValueError):
        db.put_settings("alice", auto_accept_level="yolo")


def test_memory_supersede_not_coexist():
    mid1 = db.insert_memory("alice", "preference", "user_said",
                            "要客套一点", 8, supersession_key="tone")
    mid2 = db.insert_memory("alice", "preference", "user_said",
                            "别客套, 直给", 8, supersession_key="tone")
    active = db.list_memories("alice")
    assert [m["id"] for m in active] == [mid2]   # 旧的被取代, 不并存
    assert db.get_memory("alice", mid1)["superseded"] == 1
    assert db.find_active_by_key("alice", "tone")["id"] == mid2
    assert db.delete_memory("alice", mid2) is True
    # 被取代的旧行仍在表里 (superseded=1, 不物理删除), clear 会一并清掉
    assert db.clear_memories("alice") == 1


def test_mark_recalled_increments():
    mid = db.insert_memory("alice", "fact", "user_said", "在做 RAG 项目", 8)
    db.mark_recalled([mid])
    db.mark_recalled([mid])
    assert db.get_memory("alice", mid)["recall_count"] == 2
    assert db.get_memory("alice", mid)["last_recalled_at"]
