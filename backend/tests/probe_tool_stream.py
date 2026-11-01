"""probe_tool_stream.py — DeepSeek 兼容接口 tool_calls 流式探针 (AGENT_PLAN §2.4)。

全计划唯一押在外部服务行为上的断言: bind_tools 后 astream, 分片 chunk 的
tool_call_chunks 能否经 AIMessageChunk.__add__ 合并成完整 tool_calls。
用法: backend/.venv/Scripts/python.exe tests/probe_tool_stream.py
通过标准: 打印 MERGE_OK 且退出码 0。不通过则按 AGENT_PLAN 风险 #2 降级。
"""
import asyncio
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from langchain_core.messages import HumanMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

from agent.llm import get_fast_llm  # noqa: E402


@tool
def echo_number(value: int) -> int:
    """原样返回一个整数。"""
    return value


async def main() -> int:
    llm = get_fast_llm().bind_tools([echo_number])
    merged = None
    chunks = 0
    async for chunk in llm.astream([HumanMessage(content="用 echo_number 工具返回 42")]):
        chunks += 1
        merged = chunk if merged is None else merged + chunk
    calls = getattr(merged, "tool_calls", None) or []
    print(f"chunks={chunks} tool_calls={len(calls)}")
    for call in calls:
        print(f"  name={call.get('name')} args={call.get('args')} id={bool(call.get('id'))}")
    ok = bool(calls) and calls[0].get("name") == "echo_number" \
        and calls[0].get("args", {}).get("value") == 42 and bool(calls[0].get("id"))
    print("MERGE_OK" if ok else "MERGE_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
