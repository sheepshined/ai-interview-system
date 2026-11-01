"""WebSocket 面试协议的阶段约束。

保持为无框架依赖的纯函数，便于服务端和自动化测试共同使用。
"""

ALLOWED_PHASES = {
    "answer": {"await_answer", "await_followup"},
    "end": {"await_answer", "await_followup"},
    "report": {"await_report"},
    "hint": {"await_answer", "await_followup"},
}


def command_allowed(message_type: str, phase: str) -> bool:
    """返回指定 WebSocket 命令能否在当前 graph phase 执行。"""
    return phase in ALLOWED_PHASES.get(message_type, set())


def phase_error(message_type: str, phase: str) -> str:
    """生成稳定、可直接返回前端的阶段错误信息。"""
    display_phase = phase or "unknown"
    labels = {"answer": "回答", "end": "提前结束", "report": "生成报告", "hint": "获取提示"}
    action = labels.get(message_type, message_type or "该操作")
    return f"当前阶段 {display_phase} 不能执行{action}"
