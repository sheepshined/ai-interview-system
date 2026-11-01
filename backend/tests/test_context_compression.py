import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

import config
from assistant import db
from assistant.context_compression import maybe_compress_session
from assistant.state import AssistantState


@pytest.fixture(autouse=True)
def _db(tmp_path):
    db.init_db(str(tmp_path / "assistant.db"))


def test_schema_migration_preserves_visible_history(tmp_path):
    path = tmp_path / "legacy.db"
    import sqlite3
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE assistant_sessions (
          id INTEGER PRIMARY KEY, username TEXT NOT NULL, title TEXT NOT NULL,
          summary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE assistant_messages (
          id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, role TEXT NOT NULL,
          content TEXT NOT NULL, tool_trace TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
        );
        """)
    db.init_db(str(path))
    columns = []
    with sqlite3.connect(path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(assistant_messages)")]
    assert "compacted" in columns


def test_compaction_keeps_full_history_but_reduces_context(monkeypatch):
    monkeypatch.setattr(config, "ASSISTANT_SUMMARY_TOKEN_THRESHOLD", 1)
    monkeypatch.setattr(config, "ASSISTANT_SUMMARY_KEEP_MESSAGES", 2)
    session = db.create_session("alice")
    for role, text in (("user", "早期问题"), ("assistant", "早期回答"),
                       ("user", "最近问题"), ("assistant", "最近回答")):
        db.append_message(session["id"], role, text)

    class Snapshot:
        tasks = []
        values = {"messages": [], "pending_action": {}}

    class Graph:
        updates = []
        async def aupdate_state(self, _cfg, values):
            self.updates.append(values)

    async def summarize(previous, rows):
        assert previous == ""
        assert [row["content"] for row in rows] == ["早期问题", "早期回答"]
        return "用户先询问早期问题，助手已回答。"

    result = asyncio.run(maybe_compress_session(
        Graph(), {"configurable": {"thread_id": "x"}}, "alice", session["id"],
        snapshot=Snapshot(), summarize=summarize,
    ))
    assert result["compressed"] == 2
    assert len(db.list_messages("alice", session["id"])) == 4
    assert [row["content"] for row in db.list_context_messages("alice", session["id"])] == [
        "最近问题", "最近回答"
    ]
    assert db.get_session("alice", session["id"])["summary"].startswith("用户先询问")


def test_pending_action_is_never_compressed(monkeypatch):
    monkeypatch.setattr(config, "ASSISTANT_SUMMARY_TOKEN_THRESHOLD", 1)
    session = db.create_session("alice")
    db.append_message(session["id"], "user", "x" * 100)

    class Snapshot:
        tasks = []
        values = {"messages": [], "pending_action": {"operation_id": "op"}}

    result = asyncio.run(maybe_compress_session(
        object(), {}, "alice", session["id"], snapshot=Snapshot()
    ))
    assert result["reason"] == "pending_action"
    assert db.get_session("alice", session["id"])["summary"] == ""


def test_checkpoint_pruning_keeps_tool_pairs_and_recent_round(monkeypatch):
    monkeypatch.setattr(config, "ASSISTANT_SUMMARY_TOKEN_THRESHOLD", 1)
    monkeypatch.setattr(config, "ASSISTANT_SUMMARY_KEEP_MESSAGES", 2)
    session = db.create_session("alice")
    for role, text in (("user", "old"), ("assistant", "done"),
                       ("user", "new"), ("assistant", "answer")):
        db.append_message(session["id"], role, text)

    messages = [
        HumanMessage(content="old", id="h1"),
        AIMessage(content="", id="a1", tool_calls=[{
            "name": "recall_memory", "args": {"query": "x"}, "id": "c1",
            "type": "tool_call",
        }]),
        ToolMessage(content='{"ok": true}', tool_call_id="c1", id="t1"),
        AIMessage(content="done", id="a2"),
        HumanMessage(content="new", id="h2"),
        AIMessage(content="answer", id="a3"),
    ]

    class Snapshot:
        tasks = []
        values = {"messages": messages, "pending_action": {}}

    class Graph:
        updates = []
        async def aupdate_state(self, _cfg, values): self.updates.append(values)

    graph = Graph()
    async def summarize(_previous, _rows): return "old summary"
    result = asyncio.run(maybe_compress_session(
        graph, {}, "alice", session["id"], snapshot=Snapshot(), summarize=summarize
    ))
    removed = [message.id for message in graph.updates[0]["messages"]]
    assert removed == ["h1", "a1", "t1", "a2"]
    assert result["pruned"] == 4


def test_checkpoint_pruning_with_real_memory_saver(monkeypatch):
    monkeypatch.setattr(config, "ASSISTANT_SUMMARY_TOKEN_THRESHOLD", 1)
    monkeypatch.setattr(config, "ASSISTANT_SUMMARY_KEEP_MESSAGES", 2)
    session = db.create_session("alice")
    for role, text in (("user", "old"), ("assistant", "done"),
                       ("user", "new"), ("assistant", "answer")):
        db.append_message(session["id"], role, text)

    messages = [
        HumanMessage(content="old", id="h1"),
        AIMessage(content="", id="a1", tool_calls=[{
            "name": "recall_memory", "args": {"query": "x"}, "id": "c1",
            "type": "tool_call",
        }]),
        ToolMessage(content='{"ok": true}', tool_call_id="c1", id="t1"),
        AIMessage(content="done", id="a2"),
        HumanMessage(content="new", id="h2"),
        AIMessage(content="answer", id="a3"),
    ]

    builder = StateGraph(AssistantState)
    builder.add_node("seed", lambda _state: {})
    builder.add_edge(START, "seed")
    builder.add_edge("seed", END)
    graph = builder.compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "compression-real"}}

    async def exercise():
        await graph.ainvoke({"messages": messages}, cfg)

        async def summarize(_previous, _rows):
            return "old summary"

        result = await maybe_compress_session(
            graph, cfg, "alice", session["id"], summarize=summarize
        )
        snapshot = await graph.aget_state(cfg)
        return result, snapshot

    result, snapshot = asyncio.run(exercise())
    assert result["pruned"] == 4
    assert [message.id for message in snapshot.values["messages"]] == ["h2", "a3"]


def test_compaction_is_user_isolated(monkeypatch):
    monkeypatch.setattr(config, "ASSISTANT_SUMMARY_TOKEN_THRESHOLD", 1)
    monkeypatch.setattr(config, "ASSISTANT_SUMMARY_KEEP_MESSAGES", 2)
    alice = db.create_session("alice")
    bob = db.create_session("bob")
    for session in (alice, bob):
        for role, text in (("user", "old"), ("assistant", "reply"),
                           ("user", "new"), ("assistant", "reply")):
            db.append_message(session["id"], role, text)

    class Snapshot:
        tasks = []
        values = {"messages": [], "pending_action": {}}
    class Graph:
        async def aupdate_state(self, *_): pass
    async def summarize(*_): return "summary"
    asyncio.run(maybe_compress_session(
        Graph(), {}, "alice", alice["id"], snapshot=Snapshot(), summarize=summarize
    ))
    assert len(db.list_context_messages("alice", alice["id"])) == 2
    assert len(db.list_context_messages("bob", bob["id"])) == 4
