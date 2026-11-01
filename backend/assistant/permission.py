"""permission.py — 三闸门权限判定 (AGENT_PLAN §5.6)。

闸门顺序 (抄 analysis_claude_code s03_permission:24-33):
  1 硬 deny 表 -> 2 规则判定 (risk + 设置档位) -> 3 用户审批 (ask 才弹卡片)
无匹配默认 ask (analysis_opencode s04_permission:43 的保守默认)。
批准记忆按 (tool, 参数指纹) 存, 不是按工具全局放行 (analysis_zcode s09:40)。
注解 (risk) 只参与规则判定, 服务端的安全边界另有硬 deny 表, 不依赖注解
(mcp-handbook:305)。
"""
from typing import Optional

# 闸门 1: 任何档位下都拒绝的操作。模型无权要求的都进这里。
HARD_DENY_TOOLS = frozenset({
    # 预留: 未来若出现执行 shell / 改面试图配置 / 读他人数据的工具, 进此表
})

ALLOW, ASK, DENY = "allow", "ask", "deny"

# 进程级批准指纹缓存。v1 不持久化: 重启后重新确认一次是更安全的行为,
# 也避免把"用户批准过"变成跨会话的隐式授权。
_approvals: dict = {}
_denials: dict = {}


def _key(username: str, session_id: int, tool_name: str,
         args_digest: str) -> tuple:
    return (username or "", int(session_id or 0), tool_name, args_digest)


def evaluate(tool_meta: dict, args_digest: str, settings: dict,
             username: str = "", session_id: int = 0) -> str:
    """返回 allow | ask | deny。settings 来自 assistant_settings 表。"""
    name = tool_meta.get("name", "")
    if name in HARD_DENY_TOOLS:
        return DENY
    # Hard settings must win over a remembered approval. Otherwise enabling
    # remember, approving once, then disabling memory would still allow writes.
    if name == "remember" and not settings.get("memory_enabled", True):
        return DENY
    if tool_meta.get("always_confirm"):
        return ASK
    key = _key(username, session_id, name, args_digest)
    if _approvals.get(key):
        return ALLOW
    level = settings.get("auto_accept_level", "read_auto")
    risk = tool_meta.get("risk", "read")
    if risk == "read":
        return ASK if level == "all_confirm" else ALLOW
    if risk == "write":
        if level == "all_confirm":
            return ASK
        if level == "exec_only":
            return ALLOW
        # read_auto 档: 声明了默认自动放行的写工具 (remember) 放行, 其余问
        return ALLOW if tool_meta.get("auto_accept_default") else ASK
    # execute: 起面试这类高代价动作, 任何档位都必须人确认
    return ASK


def record_approval(tool_name: str, args_digest: str, username: str = "",
                    session_id: int = 0) -> None:
    _approvals[_key(username, session_id, tool_name, args_digest)] = True


def record_denial(tool_name: str, args_digest: str, reason: str,
                  username: str = "", session_id: int = 0) -> None:
    _denials[_key(username, session_id, tool_name, args_digest)] = reason


def denial_reason(tool_name: str, args_digest: str, username: str = "",
                  session_id: int = 0) -> Optional[str]:
    return _denials.get(_key(username, session_id, tool_name, args_digest))


def reset_for_tests() -> None:
    _approvals.clear()
    _denials.clear()
