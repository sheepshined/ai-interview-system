"""graph.py — 统筹智能体的四节点 StateGraph (AGENT_PLAN §5.2)。

    START → load_context → agent ⇄ tools → (提案?) wait_confirm → …→ END

手写而不用 create_agent 的理由见 AGENT_PLAN §2.3 第 3 条。三个已核实的
LangGraph 事实支撑本文件:
  - ToolNode 并行执行多个 tool_call (tool_node.py:855-858);
  - 未知工具名合成错误 ToolMessage 而非抛异常 (tool_node.py:944-947);
  - 工具返回普通 dict 会被自动包成配对 ToolMessage (tool_node.py:881-887),
    所以提案走内容标记而非 Command (Command 路径不补配对消息, :881-916)。
"""
import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

import config
from assistant import budget, db, permission, prompts, vector_index
from assistant import events as ev
from assistant import tools as tool_registry
from assistant.tools import skills as skill_tools
from agent.llm import get_fast_llm
from assistant.state import AssistantState

logger = logging.getLogger(__name__)

PROPOSAL_MARKER = "__proposal__"

_PENDING_STATUS_QUERY = re.compile(
    r"(?:现在|当前|目前)?.{0,8}(?:还有|是否有|有没有|有无).{0,8}"
    r"(?:待确认|未确认|待处理).{0,6}(?:提案|操作|请求)"
)


def _error_text(exc: Exception) -> str:
    """handle_tool_errors 文案: 给模型可自纠的指引, 不裸抛 traceback。
    注解必须是 Exception 子类: ToolNode 会反射处理器签名来定捕获范围
    (tool_node.py:503 附近), 写 BaseException 会直接 ValueError。"""
    return f"工具执行失败: {type(exc).__name__}: {exc}。请检查参数或换用其他工具。"


def _last_ai_message(state: AssistantState) -> AIMessage:
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, AIMessage):
            return msg
    return AIMessage(content="")


def _last_user_text(state: AssistantState) -> str:
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


def _authoritative_state_reply(state: AssistantState, query: str) -> str:
    """用 checkpoint 回答即时状态，避免模型把历史提案误当成当前提案。"""
    if not _PENDING_STATUS_QUERY.search(query.replace(" ", "")):
        return ""
    pending = state.get("pending_action") or {}
    if not pending:
        return "当前没有待确认提案。历史中出现过的提案均已处理。"
    human = str(pending.get("human") or "").strip()
    return f"当前有一份待确认提案：{human}" if human else "当前有一份待确认提案。"


def _score_memories(username: str, query: str) -> List[dict]:
    """检索 + 衰减打分 (AGENT_PLAN §5.7 公式)。向量不可用时退化为关键词。"""
    hits = vector_index.search(username, query, top_k=config.ASSISTANT_MEMORY_TOPK * 2)
    scored = []
    for hit in hits:
        memory = db.get_memory(username, hit["mid"])
        if not memory or memory.get("superseded"):
            continue
        from assistant.tools.memory import _decay_score
        scored.append((_decay_score(hit["cosine"], memory, query), memory))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [m for _, m in scored[:config.ASSISTANT_MEMORY_TOPK]]


async def load_context_node(state: AssistantState) -> dict:
    """每轮入口: 拼 system prompt 动态段 + 记忆注入。单独成节点是为了让
    动态段落在静态前缀之后 (缓存友好, context-handbook:112)。"""
    username = state.get("username", "")
    settings = await asyncio.to_thread(db.get_settings, username)
    memory_texts: List[str] = []
    injected: List[str] = []
    if settings.get("memory_enabled", True):
        query = _last_user_text(state)
        if query:
            memories = await asyncio.to_thread(_score_memories, username, query)
            for memory in memories:
                memory_texts.append(memory["text"])
            from assistant.tools.memory import _text_hash
            injected = [_text_hash(m["text"]) for m in memories]
            await asyncio.to_thread(
                db.mark_recalled, [m["id"] for m in memories]
            )
    session = await asyncio.to_thread(
        db.get_session, username, state.get("session_id", 0)
    )
    query = _last_user_text(state)
    # handoff 回流: 定向面试完成事件, 一次性注入并 ack
    from assistant import handoff as assistant_handoff
    handoff_events = await asyncio.to_thread(
        assistant_handoff.drain_events_for_prompt, username
    )
    env = {
        "username": username,
        "ongoing_interview": bool(state.get("env_ongoing_interview")),
        "awaiting_confirm": bool(state.get("pending_action")),
        "session_summary": (session or {}).get("summary", ""),
        "handoff_events": handoff_events,
    }
    # 技能段 (SKILL_RUNTIME_PLAN §5): L1 目录 + 超期卸载。异常降级为空技能, 不阻断。
    try:
        active, unloaded = skill_tools.prune_expired(state)
        skill_trace = list(state.get("skill_trace") or []) + unloaded
        l1_skills = skill_tools.l1_skills(state)
        active_views = skill_tools.active_skill_views(active)
        skill_allowed = skill_tools.allowed_union(active)
    except Exception:
        logger.warning("技能段装配失败, 降级为空技能", exc_info=True)
        active, skill_trace, l1_skills, active_views, skill_allowed = \
            [], list(state.get("skill_trace") or []), [], [], []
    system_prompt = prompts.build_system_prompt(
        env, memory_texts, tool_registry.tool_descriptions(),
        l1_skills=l1_skills, active_skills=active_views,
    )
    return {
        "system_prompt": system_prompt,
        "authoritative_reply": _authoritative_state_reply(state, query),
        "memory_injected": injected,
        "tool_trace": [],
        "iter_count": 0,
        "token_spent": 0,
        "budget_exceeded": False,
        "pending_action": {},
        "deferred_action": {},
        "decision": {},
        "active_skills": active,
        "skill_allowed_tools": skill_allowed,
        "skill_trace": skill_trace,
        "phase": "thinking",
    }


async def agent_node(state: AssistantState) -> dict:
    """唯一调 LLM 的节点; 不执行工具。正文 token 经 writer 逐字推流,
    模式与 agent/graph.py:115-139 的 _stream_chain 一致。"""
    writer = get_stream_writer()
    authoritative_reply = state.get("authoritative_reply", "")
    if authoritative_reply:
        writer({"type": ev.ASSISTANT_DELTA, "text": authoritative_reply})
        return {
            "messages": [AIMessage(content=authoritative_reply)],
            "iter_count": state.get("iter_count", 0) + 1,
            "token_spent": state.get("token_spent", 0),
            "phase": "thinking",
        }
    visible = [] if state.get("budget_exceeded") else tool_registry.get_visible_tools()
    llm = get_fast_llm().bind_tools(visible)
    messages = [SystemMessage(content=state.get("system_prompt", ""))]
    messages += list(state.get("messages") or [])

    merged = None
    try:
        async for chunk in llm.astream(messages):
            merged = chunk if merged is None else merged + chunk
            if chunk.content:
                writer({"type": ev.ASSISTANT_DELTA, "text": str(chunk.content)})
    except Exception as exc:
        logger.exception("assistant LLM 调用失败: %s", exc)
        writer({"type": ev.ERROR, "code": "llm_error",
                "message": "模型调用失败, 请重试", "retryable": True})
        merged = merged or AIMessage(content="模型调用失败, 请重试。")

    for call in (getattr(merged, "tool_calls", None) or []):
        writer({"type": ev.TOOL_CALL, "call_id": call.get("id", ""),
                "name": call.get("name", ""),
                "args_digest": tool_registry.args_digest(
                    call.get("name", ""), call.get("args", {}))[-8:]})
    return {
        "messages": [merged],
        "iter_count": state.get("iter_count", 0) + 1,
        "token_spent": state.get("token_spent", 0) + budget.estimate_tokens(merged),
        "phase": "thinking",
    }


def route_after_agent(state: AssistantState) -> str:
    if state.get("budget_exceeded"):
        return END
    last = _last_ai_message(state)
    return "tools" if getattr(last, "tool_calls", None) else END


async def tools_node(state: AssistantState) -> dict:
    """ToolNode 的包装: 加权限预检、提案解析、轨迹与预算。"""
    writer = get_stream_writer()
    username = state.get("username", "")
    settings = await asyncio.to_thread(db.get_settings, username)
    ai = _last_ai_message(state)
    original_calls = list(getattr(ai, "tool_calls", None) or [])
    resuming = (state.get("decision") or {}).get("kind") == "tool_call_approval"
    if resuming:
        ids = {c["id"] for c in state["pending_action"]["args"]["calls"]}
        calls = [c for c in original_calls if c.get("id") in ids]
    else:
        calls = original_calls

    updates: Dict[str, Any] = {
        "tool_trace": list(state.get("tool_trace") or []),
        "decision": {}, "pending_action": {}, "deferred_action": {},
    }
    proposal = state.get("deferred_action") if resuming else None

    # 单轮工具数上限: 超出的直接合成跳过消息, 保证配对
    skipped: List[ToolMessage] = []
    if not resuming and len(calls) > config.ASSISTANT_MAX_TOOL_CALLS_PER_ITER:
        for call in calls[config.ASSISTANT_MAX_TOOL_CALLS_PER_ITER:]:
            skipped.append(ToolMessage(
                content=json.dumps(
                    {"ok": False, "message": "本轮工具调用数超限, 已跳过该调用"},
                    ensure_ascii=False),
                tool_call_id=call.get("id", ""), name=call.get("name", ""),
                status="error"))
        calls = calls[:config.ASSISTANT_MAX_TOOL_CALLS_PER_ITER]

    # 权限预检: 需要 ask 的调用整轮挂起等确认, 不执行。
    # 模型不可见的提案工具跳过预门控: 它们的确认就是提案卡片那道闸,
    # 再预门控一次会变成双重确认 (test_proposal_* 抓到的冲突)。
    gated, allowed_calls = [], []
    for call in calls:
        spec = tool_registry.get_spec(call.get("name", ""))
        if spec is None:
            skipped.append(ToolMessage(
                content=json.dumps({"ok": False, "message": "未知工具，未执行"},
                                   ensure_ascii=False),
                tool_call_id=call.get("id", ""), name=call.get("name", ""),
                status="error"))
            continue
        # 技能 allowed-tools 软门控 (SKILL_RUNTIME_PLAN §5): 仅当存在已激活技能时
        # 生效; 异常降级不阻断主流程。
        try:
            skill_skip = skill_tools.soft_gate_message(state, call.get("name", ""))
        except Exception:
            skill_skip = ""
        if skill_skip:
            skipped.append(ToolMessage(
                content=json.dumps({"ok": False, "message": skill_skip},
                                   ensure_ascii=False),
                tool_call_id=call.get("id", ""), name=call.get("name", ""),
                status="error"))
            continue
        if spec is not None and not spec.model_visible:
            allowed_calls.append(call)
            continue
        meta = {"name": call.get("name", ""), "risk": spec.risk if spec else "read",
                "needs_approval": spec.needs_approval if spec else False,
                "auto_accept_default": spec.auto_accept_default if spec else False,
                "always_confirm": spec.always_confirm}
        digest = tool_registry.args_digest(meta["name"], call.get("args", {}))
        verdict = permission.evaluate(meta, digest, settings,
                                      username, state.get("session_id", 0))
        if resuming and verdict != permission.DENY and state["decision"].get("action") == "approve":
            approved = state["pending_action"]["args"]["calls"]
            if any(c["id"] == call["id"] and c["digest"] == digest for c in approved):
                verdict = permission.ALLOW
        if verdict == permission.ASK:
            gated.append({"call": call, "digest": digest})
        elif verdict == permission.DENY:
            permission.record_denial(meta["name"], digest, "硬拒绝",
                                     username, state.get("session_id", 0))
            skipped.append(ToolMessage(
                content=json.dumps({"ok": False, "message": "该操作被安全策略拒绝"},
                                   ensure_ascii=False),
                tool_call_id=call.get("id", ""), name=meta["name"], status="error"))
        else:
            allowed_calls.append(call)

    tool_node = ToolNode(tool_registry.get_all_tools(),
                         handle_tool_errors=_error_text)
    started = time.monotonic()
    # 传完整 state 而非只传 messages: ToolNode 会把 state 注入 ToolRuntime,
    # 工具靠 runtime.state["username"] 取身份 (AGENT_PLAN §5.1)。
    # ToolRuntime still receives the identity-bearing state, but ToolNode only
    # sees this execution subset. The checkpoint retains the original AI call.
    result = {"messages": []}
    if allowed_calls:
        execution_ai = ai.model_copy(update={"tool_calls": allowed_calls})
        result = await tool_node.ainvoke({**state, "messages": [execution_ai]})
    elapsed_ms = int((time.monotonic() - started) * 1000)

    new_messages = list(result.get("messages") or []) + skipped
    trace = list(updates["tool_trace"])
    by_id = {c.get("id"): c for c in original_calls}
    skill_markers: List[dict] = []
    executed_tools: List[str] = []
    for msg in new_messages:
        if not isinstance(msg, ToolMessage):
            continue
        call = by_id.get(msg.tool_call_id, {})
        try:
            payload = json.loads(msg.content) if isinstance(msg.content, str) else None
        except (ValueError, TypeError):
            payload = None
        ok = ((msg.status or "success") != "error"
              and not (isinstance(payload, dict) and payload.get("ok") is False))
        skill_name = ""
        if isinstance(payload, dict) and payload.get(skill_tools.SKILL_MARKER):
            skill_name = str(payload[skill_tools.SKILL_MARKER].get("name") or "")
        entry = {"tool": msg.name or call.get("name", ""),
                 "args_digest": tool_registry.args_digest(
                     msg.name or "", call.get("args", {}))[-8:],
                 "ok": ok, "ms": elapsed_ms, "bytes": len(str(msg.content))}
        if skill_name:
            entry["skill"] = skill_name
        trace.append(entry)
        result_event = {"type": ev.TOOL_RESULT, "call_id": msg.tool_call_id,
                        "name": msg.name, "ok": ok, "ms": elapsed_ms,
                        "bytes": len(str(msg.content)),
                        "summary": str(msg.content)[:160]}
        if skill_name:
            result_event["skill"] = skill_name
        writer(result_event)
        if msg.name:
            executed_tools.append(msg.name)
        # 技能激活/卸载标记: 由 tools_node 统一回写 state (见 tools/skills.py)
        if isinstance(payload, dict) and payload.get(skill_tools.SKILL_MARKER):
            skill_markers.append(payload[skill_tools.SKILL_MARKER])
        # 提案解析: 内容标记 -> state.pending_action (见模块 docstring)
        if isinstance(payload, dict) and payload.get(PROPOSAL_MARKER):
            if proposal is None:
                proposal = payload[PROPOSAL_MARKER]

    # 技能副作用: 激活/卸载 + 引用追踪 (薄钩子, 异常降级不阻断主流程)
    try:
        updates.update(skill_tools.apply_skill_effects(
            state, skill_markers, executed_tools))
    except Exception:
        logger.warning("技能状态更新降级 (不影响主流程)", exc_info=True)

    if gated:
        updates["pending_action"] = {
            "operation_id": f"gate_{uuid.uuid4().hex}",
            "kind": "tool_call_approval",
            "human": "；".join(
                f"{tool_registry.get_spec(g['call']['name']).description.split('。')[0]}："
                + json.dumps(g["call"].get("args", {}), ensure_ascii=False)
                for g in gated) + "。需要你的确认",
            "args": {"calls": [{**g["call"], "digest": g["digest"]} for g in gated]},
            "editable_fields": [], "evidence": [],
            "confirmation_token": gated[0]["digest"],
            "risk_hint": "确认后立即执行上述工具",
        }
        updates["deferred_action"] = proposal or {}
    elif proposal:
        updates["pending_action"] = proposal
    if updates["pending_action"]:
        updates["phase"] = "awaiting_confirm"
        updates["proposal_id"] = updates["pending_action"]["confirmation_token"]

    updates["messages"] = new_messages
    updates["tool_trace"] = trace
    if budget.over_budget({**state, **updates}):
        updates["budget_exceeded"] = True
        writer({"type": ev.BUDGET_EXCEEDED,
                "used": state.get("token_spent", 0),
                "limit": config.ASSISTANT_TOKEN_BUDGET})
    return updates


def route_after_tools(state: AssistantState) -> str:
    if state.get("pending_action") and not state.get("decision"):
        return "wait_confirm"
    return "agent"


async def wait_confirm_node(state: AssistantState) -> dict:
    """interrupt 只放这个独立节点 (与 agent/graph.py:781 同构)。
    工具体内绝不调 interrupt: 依赖 contextvar, 脱离原 task 即失效,
    且节点重跑会重放工具前半段副作用 (AGENT_PLAN §2.3)。"""
    writer = get_stream_writer()
    pending = state.get("pending_action") or {}
    writer({"type": ev.PROPOSAL_ASKED, "pending": pending})
    decision = interrupt({"operation_id": pending.get("operation_id", ""),
                          "kind": pending.get("kind", "")})
    decision = decision if isinstance(decision, dict) else {"action": "reject"}
    decision.setdefault("action", "reject")
    decision.setdefault("args", {})
    decision.setdefault("reason", "")

    kind = pending.get("kind", "")
    decision["kind"] = kind
    if decision["action"] in ("approve", "edit") and kind in ("interview", "kb_session"):
        # 可编辑字段白名单合入 + 服务端重渲染摘要 (AGENT_PLAN §5.5 第二条修正)
        from assistant.tools import actions
        merged_args = dict(pending.get("args", {}))
        allowed = {f["field"] for f in pending.get("editable_fields", [])}
        for key, value in ((decision.get("args") or {})
                           if decision["action"] == "edit" else {}).items():
            if key in allowed:
                merged_args[key] = value
        err = actions.validate_proposal_edit(kind, merged_args)
        if err:
            raise ValueError(err)  # WS validates before resume; guard direct graph callers.
        pending = {**pending, "args": merged_args}
        decision["args"] = merged_args

    if decision["action"] in ("approve", "edit") and kind in ("interview", "kb_session"):
        writer({"type": ev.PROPOSAL_DECIDED,
                "operation_id": pending.get("operation_id", ""),
                "action": decision["action"],
                "effective_args_digest": tool_registry.args_digest(
                    kind, pending.get("args", {}))})
        writer({"type": ev.HANDOFF, "target": kind,
                "operation_id": pending.get("operation_id", ""),
                "config": pending.get("args", {})})
    elif decision["action"] == "approve" and kind == "tool_call_approval":
        for call in (pending.get("args", {}) or {}).get("calls", []):
            spec = tool_registry.get_spec(call.get("name", ""))
            if spec and not spec.always_confirm:
                permission.record_approval(call.get("name", ""), call.get("digest", ""),
                                           state.get("username", ""), state.get("session_id", 0))
        writer({"type": ev.PROPOSAL_DECIDED,
                "operation_id": pending.get("operation_id", ""),
                "action": "approve"})
    else:
        reason = decision.get("reason") or "用户拒绝"
        permission.record_denial(pending.get("kind", ""),
                                 pending.get("confirmation_token", ""), reason,
                                 state.get("username", ""), state.get("session_id", 0))
        writer({"type": ev.PROPOSAL_DECIDED,
                "operation_id": pending.get("operation_id", ""),
                "action": decision["action"]})

    return {"decision": decision if kind == "tool_call_approval" else {},
            "pending_action": pending if kind == "tool_call_approval" else {},
            "denied_reasons": (state.get("denied_reasons") or [])
            + ([decision["reason"]] if decision.get("reason") else []),
            "phase": "confirm_received"}


def confirm_router(state: AssistantState) -> str:
    action = (state.get("decision") or {}).get("action", "reject")
    kind = (state.get("decision") or {}).get("kind", "")
    if action == "approve" and kind == "tool_call_approval":
        return "tools"          # 批准后执行被门控的调用
    if action == "reject" and kind == "tool_call_approval":
        return "apply_rejection"
    return END                  # 面试/KB 提案: approve/edit 已发 handoff; reject 收尾


async def apply_rejection_node(state: AssistantState) -> dict:
    """被门控的调用被拒: 补配对 ToolMessage (配对不变量 §5.11), 回灌理由。"""
    pending = state.get("pending_action") or {}
    calls = (pending.get("args", {}) or {}).get("calls", [])
    reason = (state.get("decision") or {}).get("reason") or "用户拒绝执行"
    messages = [
        ToolMessage(
            content=json.dumps({"ok": False, "message": f"用户拒绝: {reason}"},
                               ensure_ascii=False),
            tool_call_id=call.get("id", ""), name=call.get("name", ""),
            status="error")
        for call in calls
    ]
    return {"messages": messages, "pending_action": {}, "decision": {},
            "deferred_action": {},
            "phase": "thinking"}


def build_assistant_graph() -> StateGraph:
    graph = StateGraph(AssistantState)
    graph.add_node("load_context", load_context_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("wait_confirm", wait_confirm_node)
    graph.add_node("apply_rejection", apply_rejection_node)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "agent")
    graph.add_conditional_edges(
        "agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_conditional_edges(
        "tools", route_after_tools,
        {"wait_confirm": "wait_confirm", "agent": "agent"})
    graph.add_conditional_edges(
        "wait_confirm", confirm_router,
        {"tools": "tools", "apply_rejection": "apply_rejection", END: END})
    graph.add_edge("apply_rejection", "agent")
    return graph
