"""tools 包入口 — 导入即注册。

新增能力 = 加一个文件 + @assistant_tool, 然后在这里加一行 import。
提案类工具 (actions) 的 model_visible=False, 注册但不进可见面。
"""
from assistant.tools import base  # noqa: F401  (注册表与装饰器)
from assistant.tools import reports  # noqa: F401
from assistant.tools import records  # noqa: F401
from assistant.tools import kb  # noqa: F401
from assistant.tools import question_bank  # noqa: F401
from assistant.tools import resume  # noqa: F401
from assistant.tools import memory  # noqa: F401
from assistant.tools import applications  # noqa: F401
from assistant.tools import skills  # noqa: F401  (技能运行时: activate/deactivate/…)

from assistant.tools.base import (  # noqa: F401
    args_digest,
    get_all_tools,
    get_spec,
    get_specs,
    get_visible_tools,
    tool_descriptions,
)

# 提案工具以"实现函数"形式暴露给 server 的确定性入口 (AGENT_PLAN §5.5):
# 模型不可见, 由显式入口或意图标记触发。
from assistant.tools.actions import (  # noqa: F401
    propose_interview_impl,
    propose_kb_session_impl,
    validate_interview_args,
)
