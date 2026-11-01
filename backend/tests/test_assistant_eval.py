import asyncio

from langgraph.checkpoint.memory import MemorySaver

import assistant.graph as ag
from assistant_eval import (aggregate_status, check_case, load_cases,
                            skill_false_trigger_summary, _execute_trajectory)
from assistant import db, permission, vector_index
from assistant.prompts import build_system_prompt
import application_store
import assistant_eval
from test_assistant_graph import StubLLM, _chunk


def test_failure_is_not_hidden_by_manual_review():
    assert aggregate_status(["passed", "pending_review"]) == "pending_review"
    assert aggregate_status(["failed", "pending_review"]) == "failed"
    assert aggregate_status([]) == "failed"
    assert check_case({"criteria": {"type": "state_assert", "assert": "missing_field"}}, {}, [], "") == "failed"
    assert check_case({"criteria": {"type": "rubric"}}, {}, [{"type": "error"}], "") == "failed"


def test_failed_run_keeps_evaluation_running_without_sensitive_error_text(monkeypatch):
    async def execute(_graph, case, _index, _reports):
        if case["id"] == "broken":
            raise RuntimeError("sensitive credential in exception")
        return {"run": 1, "status": "passed"}

    monkeypatch.setattr(assistant_eval, "_execute_case", execute)
    failed = asyncio.run(assistant_eval.execute_run(None, {"id": "broken"}, 1, None))
    passed = asyncio.run(assistant_eval.execute_run(None, {"id": "valid"}, 1, None))
    assert failed == {"run": 1, "status": "failed", "error_type": "RuntimeError"}
    assert passed["status"] == "passed"


def test_skill_namespace_counts_only_activations():
    """skill_trace 中只有 activate 计入激活数; 断言命名空间暴露技能相关字段 (§8)。"""
    final = {"tool_trace": [], "skill_trace": [
        {"skill": "weekly-interview-review", "event": "activate", "turn": 1},
        {"skill": "weekly-interview-review", "event": "auto_unload", "turn": 7},
    ]}
    extra = {"expected_skills": ["weekly-interview-review"],
             "forbidden_skills": ["jd-gap-analysis"], "max_activations": 2}
    case = {"criteria": {"type": "state_assert", "assert": (
        "'weekly-interview-review' in activated_skills and activation_count==1 "
        "and 'jd-gap-analysis' not in activated_skills and max_activations==2")}}
    assert check_case(case, final, [], "", extra) == "passed"
    # 不应触发用例被激活 -> 激活数非 0 判失败
    assert check_case({"criteria": {"type": "state_assert", "assert": "activation_count==0"}},
                      final, [], "", extra) == "failed"


def test_skill_false_trigger_summary():
    results = [
        {"id": "route-022", "no_trigger": False,
         "runs": [{"activation_count": 1, "skill_false_trigger": False}]},
        {"id": "route-023", "no_trigger": True,
         "runs": [{"activation_count": 0, "skill_false_trigger": False},
                  {"activation_count": 1, "skill_false_trigger": True}]},
    ]
    assert skill_false_trigger_summary(results) == {
        "no_trigger_runs": 2, "false_trigger_runs": 1, "rate": 0.5}


def test_skill_routing_cases_cover_three_boundaries():
    cases = load_cases()
    skill_cases = [case for case in cases if case.get("type") == "skill_routing"]
    assert 3 <= len(skill_cases) <= 6
    assert any(case.get("expected_skills") for case in skill_cases)   # 应触发
    assert any(case.get("no_trigger") for case in skill_cases)        # 不应触发
    assert any(not case.get("no_trigger") and not case.get("expected_skills")
               for case in skill_cases)                              # 模糊边界
    for case in skill_cases:
        assert isinstance(case.get("max_activations"), int)


def test_prompt_distinguishes_tool_submission_from_confirmed_write():
    prompt = build_system_prompt({}, [], [])
    assert "禁止只在 Markdown 中模拟确认卡" in prompt
    assert "立即调用 update_application_jd 或 restore_application_jd" in prompt
    assert "参数缺失时明确问出缺少的题量或难度" in prompt
    assert "写工具返回 ok=true 表示用户已批准且实际执行完成" in prompt


def test_skill_l1_routes_by_activation_not_improvisation():
    """技能路由契约: L1 目录要求命中即激活, 不得跳过技能拼工具 (route-022 回归)。"""
    prompt = build_system_prompt({}, [], [],
                                 l1_skills=[("weekly-interview-review",
                                             "问最近表现如何、该补什么、要不要做复盘时使用")])
    assert "必须先调用 activate_skill(name, reason) 激活" in prompt
    assert "不得跳过技能、用零散的工具调用自行拼凑同类流程" in prompt
    assert "<available_skills>" in prompt
    assert "weekly-interview-review" in prompt


def test_trajectory_resumes_real_graph_and_checks_database(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "assistant.db"))
    application_store.init_db(str(tmp_path / "applications.db"))
    permission.reset_for_tests()
    monkeypatch.setattr(vector_index, "search", lambda *args, **kwargs: [])
    stub = StubLLM([
        _chunk(tool_calls=[{"name": "update_application_jd", "id": "write", "type": "tool_call",
                            "args": {"application_id": 1, "jd_text": "Redis", "expected_version": 1,
                                     "source_url": "https://example.test/job"}}]),
        _chunk(content="Saved"),
        _chunk(tool_calls=[{"name": "read_application_jd", "id": "read", "type": "tool_call",
                            "args": {"application_id": 1}}]),
        _chunk(content="Redis v2"),
    ])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    case = next(c for c in load_cases() if c["id"] == "trajectory-015")
    result = asyncio.run(_execute_trajectory(graph, case, 1, tmp_path))
    assert result["status"] == "passed"
    assert len(result["steps"]) == 3
    assert result["steps"][0]["state"]["application_jd_version"] == 1
    assert result["steps"][1]["state"]["application_jd_version"] == 2
