"""state.py — 统筹智能体图的共享状态。

username 的注入链路 (AGENT_PLAN §5.1, 闭环写死):
  ws 握手鉴权 -> initial_state["username"] -> 图内 state ->
  工具经 runtime.state["username"] 读取。
它不在任何工具 args_schema 里, 也不进 messages 历史, 模型结构性不可见。
"""
from typing import Annotated, List, TypedDict

from langgraph.graph.message import add_messages  # langgraph/graph/message.py:61


class AssistantState(TypedDict, total=False):
    # 消息通道: 只放 user/assistant/tool 消息, system prompt 每轮临时拼 (§5.2)
    messages: Annotated[list, add_messages]

    # ---- 身份 (server 注入) ----
    thread_id: str          # as_{username}_{session_id}, 与面试 iv_ 前缀隔离
    username: str
    session_id: int
    env_ongoing_interview: bool   # server 每轮注入的环境事实 (prompt ③区)

    # ---- 每轮动态段 (load_context 写, 不进历史) ----
    system_prompt: str
    memory_injected: List[str]      # 本轮注入的记忆文本哈希, recall-loop 防护用
    authoritative_reply: str        # checkpoint 可直接回答的状态查询, 避免模型从历史猜测

    # ---- 提案 (offerpilot PendingAction 契约, AGENT_PLAN §5.5) ----
    pending_action: dict
    deferred_action: dict          # proposal produced before a tool approval
    proposal_id: str                # arguments_digest, 批准指纹缓存的键
    decision: dict                  # {action: approve|edit|reject, args, reason}
    denied_reasons: List[str]       # 拒绝理由回灌给模型

    # ---- 技能运行时 (SKILL_RUNTIME_PLAN §6) ----
    active_skills: List[dict]       # [{name, allowed_tools, activated_turn, last_referenced_turn, reason}]
    skill_allowed_tools: List[str]  # 已激活技能 allowed-tools 的并集 (软门控用)
    skill_trace: List[dict]         # [{skill, event: activate|deactivate|auto_unload, turn, reason?}]

    # ---- 观测与预算 ----
    tool_trace: List[dict]          # [{tool, args_digest, ok, ms, bytes}]
    iter_count: int
    token_spent: int
    budget_exceeded: bool

    phase: str                      # idle|thinking|awaiting_confirm|completed|error
