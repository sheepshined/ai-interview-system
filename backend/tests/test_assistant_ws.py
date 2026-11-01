"""Real assistant graph behind authenticated REST/WS; model and vectors are local stubs."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk
from langgraph.checkpoint.memory import MemorySaver

import auth
import server
import assistant.graph as ag
from assistant import db, permission, vector_index, persistence


class Model:
    def __init__(self, script):
        self.script = iter(script)

    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        item = next(self.script)
        if item == "slow":
            await asyncio.sleep(30)
            yield AIMessageChunk(content="late")
        else:
            yield item


def answer(text):
    return AIMessageChunk(content=text)


def proposal(kind="interview"):
    args = {"intent": "start_interview", "role": "llm_app",
            "question_count": 8, "difficulty": 2, "mode": "standard"}
    if kind == "kb_session":
        args = {"intent": "kb_session", "question": "RAG 分块"}
    return AIMessageChunk(content="请确认。", tool_calls=[{
        "name": "request_action", "id": "proposal-call", "args": args,
        "type": "tool_call"}])


@pytest.fixture
def harness(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "assistant.db"))
    permission.reset_for_tests()
    server._assistant_active_sessions.clear()
    monkeypatch.setattr(vector_index, "search", lambda *a, **k: [])
    monkeypatch.setattr(vector_index, "upsert", lambda *a, **k: None)
    monkeypatch.setattr(vector_index, "delete", lambda *a, **k: None)
    saver = MemorySaver()
    graph = ag.build_assistant_graph().compile(checkpointer=saver)
    monkeypatch.setattr(server, "_assistant_graph", graph)

    async def get_saver():
        return saver

    monkeypatch.setattr(persistence, "get_shared_saver", get_saver)
    token = auth.create_access_token("admin")
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(server.app) as client:
        def set_script(script):
            model = Model(script)
            monkeypatch.setattr(ag, "get_fast_llm", lambda: model)
        yield client, token, headers, set_script
    server._assistant_active_sessions.clear()


def turn(ws, msg):
    ws.send_json(msg)
    events = []
    for _ in range(100):
        event = ws.receive_json()
        events.append(event)
        if event["type"] == "turn_end":
            return events
        if event["type"] == "error":
            pytest.fail(str(event))
    pytest.fail("turn did not end")


def test_multiturn_same_session_and_history(harness):
    client, token, headers, script = harness
    script([answer("第一轮"), answer("第二轮")])
    with client.websocket_connect(f"/ws/assistant?token={token}") as ws:
        first = turn(ws, {"type": "user_message", "text": "你好"})
        sid = first[0]["session_id"]
        second = turn(ws, {"type": "user_message", "text": "继续", "session_id": sid})
        assert second[0]["session_id"] == sid
    detail = client.get(f"/api/assistant/sessions/{sid}", headers=headers).json()
    assert [m["content"] for m in detail["messages"]] == ["你好", "第一轮", "继续", "第二轮"]
    assert detail["phase"] == "idle" and not detail["awaiting_confirm"]
    assert len(client.get("/api/assistant/sessions", headers=headers).json()["sessions"]) == 1


@pytest.mark.parametrize("action", ["approve", "edit", "reject"])
def test_reconnect_confirm_edit_reject_and_duplicate(harness, action):
    client, token, headers, script = harness
    script([proposal()])
    before = len(server._sessions)
    with client.websocket_connect(f"/ws/assistant?token={token}") as ws:
        events = turn(ws, {"type": "user_message", "text": "中级8题"})
        sid = events[0]["session_id"]
        pending = next(e["pending"] for e in events if e["type"] == "proposal_asked")
        assert events[-1]["awaiting_confirm"]
        ws.send_json({"type": "user_message", "session_id": sid, "text": "不要覆盖提案"})
        assert ws.receive_json()["code"] == "awaiting_confirm"
    detail = client.get(f"/api/assistant/sessions/{sid}", headers=headers).json()
    assert detail["pending_action"]["operation_id"] == pending["operation_id"]
    assert len(server._sessions) == before
    decision = {"type": "proposal_decision", "session_id": sid,
                "operation_id": pending["operation_id"], "action": action,
                "args": {"question_count": 6} if action == "edit" else {}}
    with client.websocket_connect(f"/ws/assistant?token={token}") as ws:
        for bad in ({"operation_id": "old"}, {"action": "invalid"},
                    {"action": "edit", "args": {"question_count": 0}},
                    {"action": "edit", "args": {"question_count": "6"}},
                    {"action": "edit", "args": {"question_count": True}},
                    {"action": "edit", "args": {"difficulty": 4}},
                    {"action": "edit", "args": {"difficulty": "2"}},
                    {"action": "edit", "args": {"role": "other"}},
                    {"action": "edit", "args": {"mode": "project", "resume_ref": "a.pdf"}}):
            ws.send_json({**decision, **bad})
            assert ws.receive_json()["code"] == "invalid_decision"
            assert client.get(f"/api/assistant/sessions/{sid}", headers=headers).json()["awaiting_confirm"]
        resumed = turn(ws, decision)
        handoffs = [e for e in resumed if e["type"] == "handoff"]
        assert len(handoffs) == (0 if action == "reject" else 1)
        if action == "edit":
            assert handoffs[0]["config"]["question_count"] == 6
        ws.send_json(decision)
        assert ws.receive_json()["code"] == "invalid_decision"
    detail = client.get(f"/api/assistant/sessions/{sid}", headers=headers).json()
    assert len(detail["messages"]) == 2  # resume cannot duplicate the previous answer
    assert not detail["awaiting_confirm"] and detail["pending_action"] is None


def test_kb_invalid_question_then_edit(harness):
    client, token, headers, script = harness
    script([proposal("kb_session")])
    with client.websocket_connect(f"/ws/assistant?token={token}") as ws:
        events = turn(ws, {"type": "user_message", "text": "去知识库聊RAG"})
        sid = events[0]["session_id"]
        pending = next(e["pending"] for e in events if e["type"] == "proposal_asked")
        msg = {"type": "proposal_decision", "session_id": sid,
               "operation_id": pending["operation_id"], "action": "edit"}
        for question in (" ", None, 7, {}, []):
            ws.send_json({**msg, "args": {"question": question}})
            assert ws.receive_json()["code"] == "invalid_decision"
            assert client.get(f"/api/assistant/sessions/{sid}", headers=headers).json()["awaiting_confirm"]
        events = turn(ws, {**msg, "args": {"question": "召回评估"}})
        assert next(e for e in events if e["type"] == "handoff")["config"]["question"] == "召回评估"


def test_cross_account_read_confirm_and_delete_rejected(harness):
    client, token, headers, script = harness
    script([proposal()])
    with client.websocket_connect(f"/ws/assistant?token={token}") as ws:
        events = turn(ws, {"type": "user_message", "text": "8题中级"})
    sid = events[0]["session_id"]
    pending = next(e["pending"] for e in events if e["type"] == "proposal_asked")
    other = "assistant_other_test"
    response = client.post("/api/register", json={
        "username": other,
        "password": "test-password-123",
    })
    assert response.status_code in (200, 201)
    other_token = auth.create_access_token(other)
    other_headers = {"Authorization": f"Bearer {other_token}"}
    assert client.get(f"/api/assistant/sessions/{sid}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/assistant/sessions/{sid}", headers=other_headers).status_code == 404
    with client.websocket_connect(f"/ws/assistant?token={other_token}") as ws:
        ws.send_json({"type": "proposal_decision", "session_id": sid,
                      "operation_id": pending["operation_id"], "action": "approve"})
        assert ws.receive_json()["code"] == "no_session"


def test_competing_socket_stop_and_active_delete(harness):
    client, token, headers, script = harness
    script(["slow", answer("停止后继续")])
    sid = client.post("/api/assistant/sessions", headers=headers).json()["session"]["id"]
    with client.websocket_connect(f"/ws/assistant?token={token}") as first:
        first.send_json({"type": "user_message", "text": "等一下", "session_id": sid})
        assert first.receive_json()["type"] == "turn_start"
        with client.websocket_connect(f"/ws/assistant?token={token}") as second:
            second.send_json({"type": "user_message", "text": "竞争", "session_id": sid})
            assert second.receive_json()["code"] == "busy"
        assert client.delete(f"/api/assistant/sessions/{sid}", headers=headers).status_code == 409
        first.send_json({"type": "interrupt_turn"})
        assert first.receive_json()["reason"] == "cancelled"
        events = turn(first, {"type": "user_message", "text": "继续", "session_id": sid})
        assert events[-1]["reason"] == "normal"
    assert client.delete(f"/api/assistant/sessions/{sid}", headers=headers).json()["success"]
    assert client.get(f"/api/assistant/sessions/{sid}", headers=headers).status_code == 404


def test_disconnect_cleans_active_turn(harness):
    client, token, headers, script = harness
    script(["slow"])
    with client.websocket_connect(f"/ws/assistant?token={token}") as ws:
        ws.send_json({"type": "user_message", "text": "慢任务"})
        sid = ws.receive_json()["session_id"]
    assert client.get(f"/api/assistant/sessions/{sid}", headers=headers).json()["phase"] == "idle"
    assert ("admin", sid) not in server._assistant_active_sessions
