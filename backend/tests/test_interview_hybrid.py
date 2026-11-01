"""hybrid 面试模式的 WS 配置校验: 简历门槛、热身题数、题量口径与 JD 注入。

图与检索器替换为本地桩, 只验证 server.py config 分支的纯逻辑。
"""
import pytest
from fastapi.testclient import TestClient

import auth
import server


class _StubSnapshot:
    values = {}


class _StubGraph:
    """捕获 initial_state, 不产生任何流事件。"""

    def __init__(self):
        self.inputs = []

    async def aget_state(self, cfg):
        return _StubSnapshot()

    async def astream(self, input_or_command, cfg, stream_mode=None):
        self.inputs.append(input_or_command)
        return
        yield  # pragma: no cover - 使本函数成为异步生成器


class _StubRetriever:
    def get_categories(self, role=None):
        return ["项目深挖", "RAG"]


@pytest.fixture
def harness(monkeypatch):
    graph = _StubGraph()

    async def get_graph():
        return graph

    monkeypatch.setattr(server, "get_graph", get_graph)
    monkeypatch.setattr(server, "get_retriever", lambda: _StubRetriever())
    try:
        auth.create_user("hybrid_user", "secret1")
    except ValueError:
        pass
    token = auth.create_access_token("hybrid_user")
    with TestClient(server.app) as client:
        yield client, token, graph
    server._sessions.clear()


def _send_config(ws, **overrides):
    msg = {
        "type": "config",
        "role": "llm_app",
        "question_count": 5,
        "difficulty": 2,
        "mode": "hybrid",
    }
    msg.update(overrides)
    ws.send_json(msg)
    return ws.receive_json()


def test_hybrid_requires_resume(harness):
    client, token, graph = harness
    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        event = _send_config(ws)
    assert event["type"] == "error"
    assert "简历" in event["content"]
    assert graph.inputs == []


def test_handoff_focus_sets_first_topic_hint(harness, monkeypatch):
    """handoff: 助手批准的定向意图被 config 消费 → 注入 first_topic_hint。"""
    from assistant import handoff

    captured = {}

    def fake_consume(username):
        captured["username"] = username
        return {"focus": "LoRA", "role": "llm_app", "operation_id": "op_x"}

    monkeypatch.setattr(handoff, "consume_intent", fake_consume)
    client, token, graph = harness
    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        event = _send_config(ws, mode="standard")
    assert event["type"] == "config_ok"
    assert captured["username"] == "hybrid_user"
    state = graph.inputs[0]
    assert state["first_topic_hint"] == "LoRA"


def test_no_handoff_no_hint(harness, monkeypatch):
    from assistant import handoff

    monkeypatch.setattr(handoff, "consume_intent", lambda u: None)
    client, token, graph = harness
    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        event = _send_config(ws, mode="standard")
    assert event["type"] == "config_ok"
    assert "first_topic_hint" not in graph.inputs[0]


def test_hybrid_warmup_counts_as_extra_questions(harness):
    client, token, graph = harness
    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        event = _send_config(ws, resume_context="姓名: 张三\n项目: SmartSteer 多智能体面试系统")
    assert event["type"] == "config_ok"
    # 题量口径: 5 项目热身题额外再加 5 题库题
    assert event["question_count"] == 10
    assert event["interview_mode"] == "hybrid"
    assert event["warmup_count"] == 5
    state = graph.inputs[0]
    assert state["total_count"] == 10
    assert state["warmup_count"] == 5
    assert state["interview_mode"] == "hybrid"


def test_hybrid_warmup_clamped_and_total_capped(harness):
    client, token, graph = harness
    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        event = _send_config(ws, resume_context="姓名: 张三", warmup_count=99, question_count=18)
    assert event["type"] == "config_ok"
    assert event["warmup_count"] == 8
    assert event["question_count"] == 20  # min(18 + 8, 20)


def test_standard_mode_ignores_warmup(harness):
    client, token, graph = harness
    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        event = _send_config(ws, mode="standard", warmup_count=5)
    assert event["type"] == "config_ok"
    assert event["warmup_count"] == 0
    assert event["question_count"] == 5
    assert graph.inputs[0]["warmup_count"] == 0


def test_jd_text_injected_as_untrusted_data(harness):
    client, token, graph = harness
    jd = "负责多 Agent 系统设计与工具调用链路"
    with client.websocket_connect(f"/ws/chat?token={token}") as ws:
        event = _send_config(ws, resume_context="姓名: 张三\n项目: SmartSteer", jd_text=jd)
    assert event["type"] == "config_ok"
    state = graph.inputs[0]
    assert state["jd_text"] == jd
    # JD 只能以数据标签形式进入简历上下文, 不作为指令
    assert f"<job_description_data>\n{jd}\n</job_description_data>" in state["resume_context"]
