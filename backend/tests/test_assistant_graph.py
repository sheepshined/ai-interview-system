"""assistant 图的端到端单测: 假 LLM + MemorySaver, 不打网络。

覆盖三件事 (AGENT_PLAN §5.2 / §5.5 / §5.11):
  1. 一轮工具调用 -> 配对 ToolMessage 必须存在 (配对不变量);
  2. 提案 -> interrupt -> approve -> handoff 事件;
  3. 被门控的写工具 -> 挂起 -> reject -> 配对拒绝消息。
"""
import asyncio

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

import assistant.graph as ag
from assistant import db, vector_index, permission
from assistant import events as ev


class StubLLM:
    """按脚本逐次返回 AIMessageChunk; bind_tools 记录可见面。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.bound = None

    def bind_tools(self, tools):
        self.bound = [t.name for t in tools]
        return self

    async def astream(self, messages):
        item = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        yield item


def _chunk(content="", tool_calls=None):
    return AIMessageChunk(content=content, tool_calls=tool_calls or [])


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "assistant.db"))
    permission.reset_for_tests()
    monkeypatch.setattr(vector_index, "search", lambda *a, **k: [])
    monkeypatch.setattr(vector_index, "upsert", lambda *a, **k: None)
    yield


def _run(graph, payload, cfg):
    """收集 custom 事件并返回最终 values。"""
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


def _base_input():
    return {"messages": [], "username": "alice", "session_id": 1,
            "thread_id": "as_alice_1", "env_ongoing_interview": False}


def test_tool_call_gets_paired_tool_message(tmp_path, monkeypatch):
    stub = StubLLM([
        _chunk(tool_calls=[{"name": "recall_memory", "id": "c1",
                            "args": {"query": "我的偏好"}, "type": "tool_call"}]),
        _chunk(content="没有相关记忆。"),
    ])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    events, final = _run(graph, _base_input(),
                         {"configurable": {"thread_id": "as_alice_1"}})
    names = [e.get("type") for e in events]
    assert ev.TOOL_CALL in names and ev.TOOL_RESULT in names
    tool_msgs = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in tool_msgs] == ["c1"]   # 配对不变量
    assert final["phase"] != "error"


def test_proposal_interrupt_then_approve_emits_handoff(monkeypatch):
    stub = StubLLM([
        _chunk(tool_calls=[{"name": "propose_kb_session", "id": "p1",
                            "args": {"question": "RAG 分块怎么设"},
                            "type": "tool_call"}]),
    ])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "as_alice_2"}}
    events, final = _run(graph, _base_input(), cfg)
    assert ev.PROPOSAL_ASKED in [e.get("type") for e in events]
    assert final.get("pending_action", {}).get("kind") == "kb_session"

    # 用 Command(resume=...) 恢复 (与 server 的 WS 路径一致)
    from langgraph.types import Command

    events2, final2 = [], {}

    async def resume():
        nonlocal final2
        async for mode, item in graph.astream(
            Command(resume={"action": "approve", "args": {}, "reason": ""}),
            cfg, stream_mode=["custom", "values"]):
            if mode == "custom":
                events2.append(item)
            else:
                final2 = item

    asyncio.run(resume())
    types = [e.get("type") for e in events2]
    assert ev.PROPOSAL_DECIDED in types
    assert ev.HANDOFF in types
    handoff = next(e for e in events2 if e.get("type") == ev.HANDOFF)
    assert handoff["target"] == "kb_session"
    assert final2["decision"] == {} and final2["pending_action"] == {}


def test_gated_write_reject_keeps_pairing(monkeypatch):
    """forget_memory 在默认档位需要确认; 拒绝后必须补配对 ToolMessage。"""
    stub = StubLLM([
        _chunk(tool_calls=[{"name": "forget_memory", "id": "g1",
                            "args": {"memory_id": 1}, "type": "tool_call"}]),
        _chunk(content="好的, 没有删除。"),
    ])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "as_alice_3"}}
    events, final = _run(graph, _base_input(), cfg)
    assert final.get("pending_action", {}).get("kind") == "tool_call_approval"

    from langgraph.types import Command

    events2, final2 = [], {}

    async def resume():
        nonlocal final2
        async for mode, item in graph.astream(
            Command(resume={"action": "reject", "args": {},
                            "reason": "我不想删"}),
            cfg, stream_mode=["custom", "values"]):
            if mode == "custom":
                events2.append(item)
            else:
                final2 = item

    asyncio.run(resume())
    ids = [m.tool_call_id for m in final2["messages"]
           if isinstance(m, ToolMessage)]
    assert "g1" in ids                      # 被拒也要配对, 不留悬空 tool_call
    rejected = [m for m in final2["messages"]
                if isinstance(m, ToolMessage) and m.tool_call_id == "g1"]
    assert "拒绝" in rejected[0].content


def test_budget_exceeded_forces_convergence(monkeypatch):
    import config
    monkeypatch.setattr(config, "ASSISTANT_MAX_ITERATIONS", 1)
    stub = StubLLM([
        _chunk(tool_calls=[{"name": "recall_memory", "id": "b1",
                            "args": {"query": "x"}, "type": "tool_call"}]),
        _chunk(content="基于已有信息: 结论。"),
        _chunk(tool_calls=[{"name": "recall_memory", "id": "b2",
                            "args": {"query": "y"}, "type": "tool_call"}]),
    ])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    events, final = _run(graph, _base_input(),
                         {"configurable": {"thread_id": "as_alice_4"}})
    assert final.get("budget_exceeded") is True
    assert ev.BUDGET_EXCEEDED in [e.get("type") for e in events]
    assert stub.bound == [] or "recall_memory" not in (stub.bound or [])


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_mixed_batch_never_replays_allowed_write(monkeypatch, action):
    from langgraph.types import Command
    mid = db.insert_memory("alice", "fact", "user_said", "delete me", 8)
    stub = StubLLM([
        _chunk(tool_calls=[
            {"name": "remember", "id": "allowed", "args": {
                "kind": "preference", "text": "技术优先", "importance": 8}, "type": "tool_call"},
            {"name": "forget_memory", "id": "gated", "args": {"memory_id": mid}, "type": "tool_call"},
        ]),
        _chunk(content="处理完成。"),
    ])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    monkeypatch.setattr(vector_index, "delete", lambda *a, **k: None)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "mixed"}}
    events, final = _run(graph, _base_input(), cfg)
    assert len(db.list_memories("alice")) == 2
    assert [m.tool_call_id for m in final["messages"] if isinstance(m, ToolMessage)] == ["allowed"]
    _, final = _run(graph, Command(resume={"action": action}), cfg)
    ids = [m.tool_call_id for m in final["messages"] if isinstance(m, ToolMessage)]
    assert sorted(ids) == ["allowed", "gated"]
    assert len([m for m in db.list_memories("alice") if m["text"] == "技术优先"]) == 1
    assert bool(db.get_memory("alice", mid)) == (action == "reject")
    assert final["decision"] == {} and final["pending_action"] == {}


def test_denied_unknown_and_over_limit_calls_do_not_execute(monkeypatch):
    import config
    monkeypatch.setattr(config, "ASSISTANT_MAX_TOOL_CALLS_PER_ITER", 2)
    db.put_settings("alice", memory_enabled=False)
    calls = [
        {"name": "remember", "id": "deny", "args": {"kind": "fact", "text": "do not write", "importance": 8}, "type": "tool_call"},
        {"name": "does_not_exist", "id": "unknown", "args": {}, "type": "tool_call"},
        {"name": "remember", "id": "limit", "args": {"kind": "fact", "text": "do not write either", "importance": 8}, "type": "tool_call"},
    ]
    stub = StubLLM([_chunk(tool_calls=calls), _chunk(content="未执行。")])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    _, final = _run(graph, _base_input(), {"configurable": {"thread_id": "filter"}})
    results = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert sorted(m.tool_call_id for m in results) == ["deny", "limit", "unknown"]
    assert all(m.status == "error" for m in results)
    assert db.list_memories("alice") == []


def test_context_marks_historical_proposals_as_already_resolved():
    state = _base_input()
    state["messages"] = []
    state["pending_action"] = {}
    update = asyncio.run(ag.load_context_node(state))
    prompt = update["system_prompt"]
    assert "当前是否有待确认提案: 否" in prompt
    assert "权威状态: 当前没有任何待确认提案" in prompt
    assert "不得声称它们仍待确认" in prompt


def test_pending_status_query_uses_checkpoint_not_historical_text(monkeypatch):
    stub = StubLLM([_chunk(content="错误：历史里还有三份提案。")])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    state = _base_input()
    state["messages"] = [
        AIMessage(content="待确认提案三份：旧面试、旧知识库、旧面试。"),
        HumanMessage(content="现在还有待确认提案吗？"),
    ]
    state["pending_action"] = {}
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    events, final = _run(
        graph, state, {"configurable": {"thread_id": "authoritative-status"}}
    )
    assert stub.calls == 0
    assert final["messages"][-1].content == "当前没有待确认提案。历史中出现过的提案均已处理。"
    deltas = [e["text"] for e in events if e.get("type") == ev.ASSISTANT_DELTA]
    assert deltas == ["当前没有待确认提案。历史中出现过的提案均已处理。"]


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_application_write_confirmation_is_one_operation_only(tmp_path, monkeypatch, action):
    import application_store
    from langgraph.types import Command
    application_store.init_db(str(tmp_path / "applications.db"))
    db.put_settings("alice", auto_accept_level="exec_only")
    call = {"name": "create_application", "id": "app1", "type": "tool_call",
            "args": {"company": "Alpha", "role_title": "Dev"}}
    stub = StubLLM([_chunk(tool_calls=[call]), _chunk(content="Done"),
                   _chunk(tool_calls=[{**call, "id": "app2"}])])
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "application-confirm"}}
    _, first = _run(graph, _base_input(), cfg)
    assert first["pending_action"]["kind"] == "tool_call_approval"
    assert application_store.list_all("alice") == []
    _, resumed = _run(graph, Command(resume={"action": action}), cfg)
    assert len(application_store.list_all("alice")) == (1 if action == "approve" else 0)
    assert [m.tool_call_id for m in resumed["messages"] if isinstance(m, ToolMessage)] == ["app1"]
    _, second = _run(graph, {"messages": [HumanMessage(content="Again")]}, cfg)
    assert second["pending_action"]["kind"] == "tool_call_approval"
    assert second["pending_action"]["operation_id"] != first["pending_action"]["operation_id"]


@pytest.mark.parametrize("tool_name", ["update_application_jd", "restore_application_jd"])
@pytest.mark.parametrize("action", ["approve", "reject"])
def test_jd_tools_run_only_after_confirmation(tmp_path, monkeypatch, tool_name, action):
    import application_store as store
    from langgraph.types import Command
    store.init_db(str(tmp_path / "applications.db"))
    first = store.create("alice", {"company": "Alpha", "role_title": "Dev", "jd_text": "Python"})
    app = store.save_jd("alice", first["id"], "SQL", "", 1)
    args = {"application_id": app["id"], "expected_version": 2}
    args.update({"jd_text": "Redis"} if tool_name == "update_application_jd" else {"version_id": first["jd_version"]["id"]})
    call = {"name": tool_name, "id": "jd1", "args": args, "type": "tool_call"}
    stub = StubLLM([_chunk(tool_calls=[call]), _chunk(content="Done"),
                   _chunk(tool_calls=[{**call, "id": "jd2", "args": {**args, "expected_version": 3 if action == "approve" else 2}}])])
    db.put_settings("alice", auto_accept_level="exec_only")
    monkeypatch.setattr(ag, "get_fast_llm", lambda: stub)
    graph = ag.build_assistant_graph().compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": f"jd-{tool_name}-{action}"}}
    _, pending = _run(graph, _base_input(), cfg)
    assert pending["pending_action"]["kind"] == "tool_call_approval"
    assert store.get("alice", app["id"])["jd_text"] == "SQL"
    _, final = _run(graph, Command(resume={"action": action}), cfg)
    expected = "SQL" if action == "reject" else "Redis" if tool_name == "update_application_jd" else "Python"
    assert store.get("alice", app["id"])["jd_text"] == expected
    assert len(store.list_jd_versions("alice", app["id"])) == (3 if action == "approve" else 2)
    assert [m.tool_call_id for m in final["messages"] if isinstance(m, ToolMessage)] == ["jd1"]
    _, again = _run(graph, {"messages": [HumanMessage(content="Again")]}, cfg)
    assert again["pending_action"]["operation_id"] != pending["pending_action"]["operation_id"]
