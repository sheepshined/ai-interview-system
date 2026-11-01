"""events.py — /ws/assistant 事件类型的单一事实源。

现有 /ws/chat 的事件是散字符串 (stream_start/stream_chunk/...), 本层不重复
这个债: 前后端契约只从这里取名字。新增事件必须先在 AGENT_PLAN §6 登记。
"""

# ---- 客户端 -> 服务端 ----
USER_MESSAGE = "user_message"
PROPOSAL_DECISION = "proposal_decision"
INTERRUPT_TURN = "interrupt_turn"

# ---- 服务端 -> 客户端 ----
TURN_START = "turn_start"
TURN_END = "turn_end"
ASSISTANT_DELTA = "assistant_delta"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
PROPOSAL_ASKED = "proposal_asked"
PROPOSAL_DECIDED = "proposal_decided"
MEMORY_WRITTEN = "memory_written"
HANDOFF = "handoff"
BUDGET_EXCEEDED = "budget_exceeded"
ERROR = "error"

# turn_end 的收尾原因
END_NORMAL = "normal"
END_CANCELLED = "cancelled"
END_BUDGET = "budget"
END_REJECTED = "rejected"
