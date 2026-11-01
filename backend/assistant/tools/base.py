"""base.py — 工具注册约定 (AGENT_PLAN §5.3)。

每个能力一个 @assistant_tool 声明, registry 自动收集。"后续接入别的功能"
就是加一个文件 + 一个装饰器, 不动图也不动 server。

两条硬约定:
  - username 永远不是工具参数, 工具体内经 runtime.state["username"] 取
    (ToolRuntime 字段集合见 langgraph/prebuilt/tool_node.py:1673-1728, 无 username);
  - 返回值一律 dict + found/ok, 不抛异常给上层循环 (异常由 ToolNode 的
    handle_tool_errors 转成可自纠文案, AGENT_PLAN §5.11)。
"""
import hashlib
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Type

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel


@dataclass
class ToolSpec:
    name: str
    description: str
    args_schema: Type[BaseModel]
    coroutine: Callable
    risk: str = "read"                    # read | write | execute
    needs_approval: bool = False
    model_visible: bool = True            # False = 从 bind_tools 可见面摘除
    max_output_chars: Optional[int] = None
    auto_accept_default: bool = False     # read_auto 档下写工具是否默认放行
    always_confirm: bool = False          # 不使用历史审批，每次独立确认
    tool: BaseTool = field(default=None)


_REGISTRY: Dict[str, ToolSpec] = {}


def assistant_tool(*, name: str, description: str, args_schema: Type[BaseModel],
                   risk: str = "read", needs_approval: bool = False,
                   model_visible: bool = True,
                   max_output_chars: Optional[int] = None,
                   auto_accept_default: bool = False,
                   always_confirm: bool = False):
    def deco(fn: Callable) -> Callable:
        tool = StructuredTool.from_function(
            coroutine=fn,
            name=name,
            description=description,
            args_schema=args_schema,
        )
        _REGISTRY[name] = ToolSpec(
            name=name, description=description, args_schema=args_schema,
            coroutine=fn, risk=risk, needs_approval=needs_approval,
            model_visible=model_visible, max_output_chars=max_output_chars,
            auto_accept_default=auto_accept_default, always_confirm=always_confirm, tool=tool,
        )
        return fn
    return deco


def get_specs() -> List[ToolSpec]:
    return list(_REGISTRY.values())


def get_spec(name: str) -> Optional[ToolSpec]:
    return _REGISTRY.get(name)


def get_visible_tools() -> List[BaseTool]:
    """bind_tools 的可见面。model_visible=False 的工具 (提案类) 不在其中。"""
    return [s.tool for s in _REGISTRY.values() if s.model_visible]


def get_all_tools() -> List[BaseTool]:
    return [s.tool for s in _REGISTRY.values()]


def tool_descriptions() -> List[tuple]:
    """供 prompts 渲染工具清单 (每轮实时渲染, 不存副本)。"""
    return [(s.name, s.description) for s in _REGISTRY.values() if s.model_visible]


def args_digest(name: str, args: dict) -> str:
    """(tool, 参数指纹) 是批准缓存与提案身份的键 (analysis_zcode s09:40)。"""
    canonical = json.dumps({"tool": name, "args": args or {}},
                           sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def reset_for_tests() -> None:
    # registry 是模块级单例, 测试间不重置 (工具定义本身无状态);
    # 需要隔离的是 permission 的批准缓存, 见 permission.reset_for_tests。
    pass
