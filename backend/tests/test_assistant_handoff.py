"""test_assistant_handoff.py — handoff 机制 (assistant -> interview -> assistant)。"""
import json

import config
from assistant import db, handoff
from assistant.tools.actions import propose_interview_impl, validate_interview_args


def _init(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "assistant.db"))
    monkeypatch.setattr(config, "REPORTS_DIR", str(tmp_path / "reports"))
    (tmp_path / "reports").mkdir()


def test_intent_single_consume(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    handoff.record_intent("alice", {"focus": "RAG", "role": "llm_app"}, "op_1")
    first = handoff.consume_intent("alice")
    assert first and first["focus"] == "RAG" and first["role"] == "llm_app"
    assert handoff.consume_intent("alice") is None  # 单次消费
    # 他人无影响
    assert handoff.consume_intent("bob") is None


def test_intent_ttl_expired(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    handoff.record_intent("alice", {"focus": "RAG", "role": "llm_app"}, "op_2")
    # ttl=0 等价于已过期 → 不消费
    assert db.consume_handoff_intent("alice", ttl_seconds=0) is None
    # 未被标记消费, 正常 TTL 下仍可取走
    again = handoff.consume_intent("alice")
    assert again and again["focus"] == "RAG"


def test_completion_reads_report_and_drains_once(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    report_id = "interview_report_20261018_120000_alice_llm_app"
    (tmp_path / "reports" / f"{report_id}.json").write_text(json.dumps({
        "report_id": report_id, "username": "alice", "avg_score": 7.8,
        "role_title": "大模型应用开发工程师", "questions": [],
    }), encoding="utf-8")

    handoff.record_completion("alice", report_id, "RAG")
    text = handoff.drain_events_for_prompt("alice")
    assert report_id in text and "7.8" in text and "RAG" in text
    # 再次取空 (已 ack)
    assert handoff.drain_events_for_prompt("alice") == ""
    # 他人取不到
    assert handoff.drain_events_for_prompt("bob") == ""


def test_completion_tolerates_missing_report(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    handoff.record_completion("alice", "interview_report_20261018_120000_x_llm_app", "")
    text = handoff.drain_events_for_prompt("alice")
    assert "interview_report_20261018_120000_x_llm_app" in text  # avg=0 兜底


def test_focus_plumbing_in_proposal(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    args = {"role": "llm_app", "question_count": 5, "difficulty": 2,
            "mode": "standard", "focus": "RAG"}
    assert validate_interview_args(args) == ""
    result = propose_interview_impl(args, session_id=1)
    assert result["ok"] and result["__proposal__"]["args"]["focus"] == "RAG"
    assert "定向 RAG" in result["__proposal__"]["human"]
    # focus 超长被拒
    bad = validate_interview_args({**args, "focus": "x" * 101})
    assert "面试参数无效" in bad


def test_system_prompt_renders_handoff_events():
    from assistant import prompts
    prompt = prompts.build_system_prompt(
        {"username": "alice", "handoff_events": "- 报告 r1 (面试): 平均分 7.8"},
        [], [])
    assert "面试回流事件" in prompt and "平均分 7.8" in prompt
    # 无事件时不出现该段落
    prompt2 = prompts.build_system_prompt({"username": "alice"}, [], [])
    assert "面试回流事件" not in prompt2
