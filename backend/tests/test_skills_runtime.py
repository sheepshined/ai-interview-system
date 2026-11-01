"""技能运行时单测 (SKILL_RUNTIME_PLAN §5/§6/§9)。

覆盖: 激活/卸载/上限 / allowed-tools 软门控 / 脚本审批 / 路径穿越拦截 /
超期自动卸载 / L1-L2 装配。
不依赖 pytest-asyncio: 异步用例统一 asyncio.run, 与既有测试风格一致。
"""
import asyncio

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

import assistant.graph as ag
from assistant import db, permission, vector_index
from assistant import tools as registry
from assistant.tools.skills import (
    MAX_ACTIVE_SKILLS, SKILL_MARKER, UNLOAD_AFTER_TURNS,
    activate_skill, apply_skill_effects, deactivate_skill, list_skills,
    prune_expired, read_skill_reference, run_skill_script, soft_gate_message,
)
from skills import loader
from skills import runtime as skill_runtime


class _Runtime:
    """ToolRuntime 的最小替身: 技能工具只依赖 state。"""

    def __init__(self, active=None):
        active = active or []
        self.state = {
            "username": "alice", "session_id": 1,
            "active_skills": active,
            "skill_allowed_tools": sorted({t for e in active
                                           for t in e.get("allowed_tools", [])}),
            "skill_trace": [], "messages": [],
        }
        self.events = []
        self.stream_writer = self.events.append


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "assistant.db"))
    permission.reset_for_tests()
    monkeypatch.setattr(vector_index, "search", lambda *a, **k: [])
    monkeypatch.setattr(vector_index, "upsert", lambda *a, **k: None)
    yield
    loader.reload(loader.SKILLS_ROOT)


@pytest.fixture
def skill_root(tmp_path):
    """铺 3 个校验通过的内置技能 (alpha 带 scripts/references)。"""
    specs = {
        "alpha-skill": "list_reports",
        "beta-skill": "read_resume_summary",
        "gamma-skill": "get_weakness_trend",
    }
    for name, tools in specs.items():
        directory = tmp_path / name
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\n"
            f"description: 用于测试的技能 {name}。当用户需要测试时使用。\n"
            f"allowed-tools: {tools}\n---\n# {name}\n步骤一。\n",
            encoding="utf-8")
    scripts = tmp_path / "alpha-skill" / "scripts"
    scripts.mkdir()
    (scripts / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    refs = tmp_path / "alpha-skill" / "references"
    refs.mkdir()
    (refs / "guide.md").write_text("# 指南\n\n细节内容。\n", encoding="utf-8")
    loader.reload(str(tmp_path))
    return tmp_path


def _active_entry(name, tools, activated_turn=1, last_referenced_turn=1):
    return {"name": name, "allowed_tools": tools,
            "activated_turn": activated_turn,
            "last_referenced_turn": last_referenced_turn, "reason": ""}


# ============================================================
# 激活 / 卸载 / 上限
# ============================================================
def test_activate_returns_body_and_marker():
    res = asyncio.run(activate_skill("weekly-interview-review",
                                     reason="复盘", runtime=_Runtime()))
    assert res["ok"] and res["found"]
    assert res["activated"] == "weekly-interview-review"
    assert res["body"].startswith('<skill_body name="weekly-interview-review"')
    assert res[SKILL_MARKER] == {"action": "activate",
                                 "name": "weekly-interview-review", "reason": "复盘"}


def test_activate_unknown_skill_found_false():
    res = asyncio.run(activate_skill("not-a-skill", runtime=_Runtime()))
    assert res["ok"] is False and res["found"] is False
    assert "weekly-interview-review" in res["available"]


def test_activate_cap_requires_deactivate(skill_root):
    active = [_active_entry("alpha-skill", ["list_reports"]),
              _active_entry("beta-skill", ["read_resume_summary"])]
    rt = _Runtime(active=active)
    res = asyncio.run(activate_skill("gamma-skill", runtime=rt))
    assert res["ok"] is False and res["found"] is True
    assert "最多" in res["message"] and res["active"] == ["alpha-skill", "beta-skill"]
    # 已激活的重复激活: 允许, 走 already_active
    again = asyncio.run(activate_skill("alpha-skill", runtime=rt))
    assert again["ok"] and again.get("already_active") is True


def test_deactivate(skill_root):
    rt = _Runtime(active=[_active_entry("alpha-skill", ["list_reports"])])
    res = asyncio.run(deactivate_skill("alpha-skill", runtime=rt))
    assert res["ok"] and res["deactivated"] == "alpha-skill"
    assert res[SKILL_MARKER]["action"] == "deactivate"
    miss = asyncio.run(deactivate_skill("beta-skill", runtime=rt))
    assert miss["ok"] and miss["found"] is False


def test_list_skills_marks_active_and_issues(skill_root):
    rt = _Runtime(active=[_active_entry("alpha-skill", ["list_reports"])])
    res = asyncio.run(list_skills(runtime=rt))
    assert res["ok"] and res["found"]
    by_name = {item["name"]: item for item in res["skills"]}
    assert by_name["alpha-skill"]["active"] is True
    assert by_name["beta-skill"]["active"] is False
    assert res["max_active"] == MAX_ACTIVE_SKILLS
    assert res["issues"] == []


# ============================================================
# allowed-tools 软门控 / 引用追踪 / 超期卸载
# ============================================================
def test_soft_gate_only_when_skills_active():
    idle = {"active_skills": [], "skill_allowed_tools": []}
    assert soft_gate_message(idle, "anything") == ""

    active = {"active_skills": [{"name": "jd-gap-analysis"}],
              "skill_allowed_tools": ["read_resume_summary"]}
    assert soft_gate_message(active, "read_resume_summary") == ""
    assert "未声明该工具" in soft_gate_message(active, "list_reports")
    # 技能管理工具本身不受门控
    for meta_tool in ("activate_skill", "deactivate_skill", "list_skills",
                      "read_skill_reference", "run_skill_script"):
        assert soft_gate_message(active, meta_tool) == ""


def test_apply_skill_effects_activate_and_reference():
    state = {"messages": [HumanMessage(content="a"), HumanMessage(content="b")],
             "active_skills": [], "skill_trace": []}
    out = apply_skill_effects(
        state, [{"action": "activate", "name": "weekly-interview-review",
                 "reason": "r"}], [])
    assert [e["name"] for e in out["active_skills"]] == ["weekly-interview-review"]
    assert "list_reports" in out["skill_allowed_tools"]
    assert out["skill_trace"][-1]["event"] == "activate"

    # 第二轮执行了该技能的 allowed-tool -> 引用轮次刷新到当前轮
    state2 = {"messages": [HumanMessage(content="a"), HumanMessage(content="b")],
              "active_skills": out["active_skills"], "skill_trace": out["skill_trace"]}
    out2 = apply_skill_effects(state2, [], ["list_reports"])
    assert out2["active_skills"][0]["last_referenced_turn"] == 2

    out3 = apply_skill_effects(
        {"messages": [HumanMessage(content="a")], "active_skills": out["active_skills"],
         "skill_trace": out["skill_trace"]},
        [{"action": "deactivate", "name": "weekly-interview-review"}], [])
    assert out3["active_skills"] == [] and out3["skill_allowed_tools"] == []
    assert out3["skill_trace"][-1]["event"] == "deactivate"


def test_prune_expired_after_six_turns():
    expired = _active_entry("weekly-interview-review", ["list_reports"],
                            activated_turn=1, last_referenced_turn=1)
    fresh = _active_entry("jd-gap-analysis", ["read_resume_summary"],
                          activated_turn=1, last_referenced_turn=2)
    state = {"messages": [HumanMessage(content=str(i)) for i in range(7)],
             "active_skills": [expired, fresh]}
    remaining, events = prune_expired(state)
    assert [e["name"] for e in remaining] == ["jd-gap-analysis"]
    assert events == [{"skill": "weekly-interview-review",
                       "event": "auto_unload", "turn": 7}]
    assert 7 - 1 >= UNLOAD_AFTER_TURNS


# ============================================================
# L3 资源读取 / 脚本路径安全
# ============================================================
def test_read_skill_reference(skill_root):
    res = asyncio.run(read_skill_reference("alpha-skill", "guide.md", runtime=_Runtime()))
    assert res["ok"] and res["found"] and "细节内容" in res["content"]
    miss = asyncio.run(read_skill_reference("alpha-skill", "nope.md", runtime=_Runtime()))
    assert miss["ok"] and miss["found"] is False and miss["available"] == ["guide.md"]


def test_path_traversal_and_extension_blocked(skill_root):
    # 路径穿越 / 非法扩展名一律拒绝
    assert skill_runtime.resolve_script("alpha-skill", "../evil.py") is None
    assert skill_runtime.resolve_script("alpha-skill", "sub/evil.py") is None
    assert skill_runtime.resolve_script("alpha-skill", "hello.txt") is None
    assert skill_runtime.resolve_script("alpha-skill", "hello.py") is not None
    assert skill_runtime.read_reference("alpha-skill", "../../etc/passwd") == ("", False)
    assert skill_runtime.read_reference("alpha-skill", "./guide.md") == ("", False)

    res = asyncio.run(run_skill_script("alpha-skill", "../evil.py", runtime=_Runtime()))
    assert res["ok"] is False and res["found"] is False


def test_run_skill_script_executes_whitelisted(skill_root):
    res = asyncio.run(run_skill_script("alpha-skill", "hello.py", runtime=_Runtime()))
    assert res["ok"] is True and res["found"] is True
    assert "hi" in res["stdout"]


def test_run_script_spec_is_execute_with_mandatory_confirm():
    spec = registry.get_spec("run_skill_script")
    assert spec.risk == "execute" and spec.always_confirm is True
    meta = {"name": "run_skill_script", "risk": spec.risk,
            "needs_approval": True, "always_confirm": True}
    for level in ("read_auto", "exec_only", "all_confirm"):
        settings = {"auto_accept_level": level, "memory_enabled": True}
        assert permission.evaluate(meta, "d", settings, "alice", 1) == permission.ASK


# ============================================================
# 图集成: 软门控 / 脚本审批 / 无技能时行为不变
# ============================================================
class _StubLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.bound = None

    def bind_tools(self, tools):
        self.bound = [t.name for t in tools]
        return self

    async def astream(self, messages):
        yield self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1


def _chunk(content="", tool_calls=None):
    return AIMessageChunk(content=content, tool_calls=tool_calls or [])


def _run(graph, payload, cfg):
    events, final = [], {}

    async def go():
        nonlocal final
        async for mode, item in graph.astream(payload, cfg,
                                              stream_mode=["custom", "values"]):
            if mode == "custom":
                events.append(item)
            else:
                final = item
        return events, final

    return asyncio.run(go())


def _base_input(**extra):
    state = {"messages": [], "username": "alice", "session_id": 1,
             "thread_id": "as_alice_skills", "env_ongoing_interview": False}
    state.update(extra)
    return state


def test_graph_soft_gate_skips_undeclared_tool(monkeypatch):
    allowed = ["list_reports", "get_weakness_trend", "read_report_weak_points",
               "read_interview_record", "remember"]
    stub = _StubLLM([
        _chunk(tool_calls=[
            {"name": "list_reports", "id": "allowed", "args": {},
             "type": "tool_call"},
            {"name": "search_interview_records", "id": "blocked",
             "args": {"keyword": "x"}, "type": "tool_call"},
        ]),
        _chunk(content="完成。"),
    ])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    state = _base_input(active_skills=[_active_entry(
        "weekly-interview-review", allowed)], skill_allowed_tools=allowed)
    _, final = _run(graph, state, {"configurable": {"thread_id": "as_alice_skills"}})
    msgs = {m.tool_call_id: m for m in final["messages"] if isinstance(m, ToolMessage)}
    assert "未声明该工具" in msgs["blocked"].content
    assert msgs["blocked"].status == "error"
    assert "未声明该工具" not in msgs["allowed"].content
    # 技能状态经 tools_node 回写, 且 allowed-tool 被引用
    assert final["active_skills"][0]["name"] == "weekly-interview-review"


def test_graph_without_active_skills_behaves_normally(monkeypatch):
    stub = _StubLLM([
        _chunk(tool_calls=[{"name": "search_interview_records", "id": "c1",
                            "args": {"keyword": "RRF"}, "type": "tool_call"}]),
        _chunk(content="完成。"),
    ])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    _, final = _run(graph, _base_input(), {"configurable": {"thread_id": "as_alice_plain"}})
    results = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert results and all("未声明该工具" not in m.content for m in results)
    assert final["active_skills"] == []


def test_graph_run_skill_script_requires_confirmation(monkeypatch):
    stub = _StubLLM([
        _chunk(tool_calls=[{"name": "run_skill_script", "id": "s1",
                            "args": {"name": "weekly-interview-review",
                                     "script": "x.py"}, "type": "tool_call"}]),
    ])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    _, final = _run(graph, _base_input(), {"configurable": {"thread_id": "as_alice_script"}})
    pending = final.get("pending_action") or {}
    assert pending.get("kind") == "tool_call_approval"
    assert pending["args"]["calls"][0]["name"] == "run_skill_script"


def test_graph_activation_flows_into_state(monkeypatch):
    """activate_skill 经图执行后, 激活状态写入 state.active_skills 与 skill_trace。"""
    stub = _StubLLM([
        _chunk(tool_calls=[{"name": "activate_skill", "id": "a1",
                            "args": {"name": "jd-gap-analysis", "reason": "JD 对照"},
                            "type": "tool_call"}]),
        _chunk(content="已激活。"),
    ])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    _, final = _run(graph, _base_input(), {"configurable": {"thread_id": "as_alice_act"}})
    assert [e["name"] for e in final["active_skills"]] == ["jd-gap-analysis"]
    assert "read_resume_summary" in final["skill_allowed_tools"]
    assert final["skill_trace"][-1]["event"] == "activate"
    assert final["skill_trace"][-1]["skill"] == "jd-gap-analysis"
    # 前端技能徽章数据源: 工具轨迹条目携带技能名 (tools_node 写入)
    activate_trace = [t for t in final["tool_trace"] if t["tool"] == "activate_skill"]
    assert activate_trace and activate_trace[-1].get("skill") == "jd-gap-analysis"
