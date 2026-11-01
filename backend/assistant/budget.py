"""budget.py — 迭代 / token / 输出上限 (AGENT_PLAN §5.9)。

停机靠语义事件而非纯计数: 模型不再发 tool_calls 即结束, 预算只是天花板。
超限时不是硬切断, 而是追加一轮"收敛轮" (bind_tools([])) 让它基于已有信息给结论,
抄 analysis_opencode s01_runloop:33,65 的做法。
"""
import config


def over_iteration(state: dict) -> bool:
    return state.get("iter_count", 0) >= config.ASSISTANT_MAX_ITERATIONS


def over_token(state: dict) -> bool:
    return state.get("token_spent", 0) >= config.ASSISTANT_TOKEN_BUDGET


def over_budget(state: dict) -> bool:
    return over_iteration(state) or over_token(state)


def estimate_tokens(message) -> int:
    """粗估: 中文约 1 字 1 token, 英文约 4 字符 1 token, 取 len//2 作保守中值。"""
    content = getattr(message, "content", "") or ""
    if isinstance(content, list):  # 多模态块只取文本部分
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    tool_calls = getattr(message, "tool_calls", None) or []
    extra = sum(len(str(call.get("args", ""))) for call in tool_calls)
    return max(1, (len(content) + extra) // 2)


def truncate_output(text: str) -> tuple:
    """超限落盘留指针 (压缩四步的第 1 步)。返回 (展示文本, 是否被截)。"""
    limit = config.ASSISTANT_TOOL_OUTPUT_CHARS
    if len(text) <= limit:
        return text, False
    return (
        text[:limit]
        + f"\n…[输出过长已截断, 全文 {len(text)} 字; 需要细节请用对应读取工具按 id 重取]",
        True,
    )
