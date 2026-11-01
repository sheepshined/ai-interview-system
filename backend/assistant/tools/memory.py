"""memory.py — 长期记忆工具 (AGENT_PLAN §5.7)。

写入三门槛 (context-handbook:495-504,200):
  importance < 门槛拒写; origin=="untrusted" 拒写; 冲突走 supersede 不并存。
recall-loop 防护 (context-handbook:177): 本轮已注入过的记忆文本, 禁止再写成新记忆,
否则记忆自我繁殖。哈希由 load_context 写进 state["memory_injected"]。
检索打分: cosine × 关键词重合 × 0.5**(天/30) × importance/10 (context-handbook:511)。
"""
import asyncio
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

import config
from assistant import db, vector_index
from assistant.tools.base import assistant_tool
from langchain.tools import ToolRuntime

VALID_KINDS = ("fact", "weakness_pattern", "preference", "project")


class RememberArgs(BaseModel):
    kind: str = Field(description="fact | weakness_pattern | preference | project")
    text: str = Field(description="一句话记忆内容, 不要写成长文")
    importance: int = Field(default=6, ge=1, le=10,
                            description="低于 6 会被拒写; 稳定偏好/事实给 7-9")
    origin: str = Field(default="agent_inferred",
                        description="user_said | agent_inferred | report_derived")
    source_ref: str = Field(default="", description="出处: report_id / note_id 等")
    trigger_keywords: str = Field(default="", description="逗号分隔的召回关键词")
    supersession_key: str = Field(
        default="", description="同 key 的新记忆会取代旧的, 用于偏好翻转")


class RecallArgs(BaseModel):
    query: str = Field(description="想回忆的内容")
    top_k: int = Field(default=5, ge=1, le=10)


class ForgetArgs(BaseModel):
    memory_id: int = Field(description="来自记忆面板或 recall_memory 的 id")


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def _tokens(text: str) -> set:
    return {t for t in re.split(r"[\s,，、。;；]+", text or "") if len(t) >= 2}


def _keyword_overlap(query: str, memory: dict) -> float:
    qt = _tokens(query)
    mt = _tokens(memory.get("trigger_keywords", "")) | _tokens(memory.get("text", ""))
    if not qt or not mt:
        return 0.0
    return len(qt & mt) / len(qt)


def _decay_score(cosine: float, memory: dict, query: str) -> float:
    try:
        ts = datetime.fromisoformat(memory.get("ts") or "")
        days = max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400)
    except ValueError:
        days = 0.0
    half = config.ASSISTANT_MEMORY_HALF_LIFE_DAYS
    return (cosine * 0.6 + _keyword_overlap(query, memory) * 0.4) \
        * (0.5 ** (days / half)) * (memory.get("importance", 6) / 10)


@assistant_tool(
    name="remember",
    description=(
        "把一条稳定信息写进长期记忆 (跨会话生效)。"
        "只记三类: 用户的稳定事实、跨场面试的弱项轨迹、交互偏好。"
        "不要记一次性任务细节 ('这次要 8 题')——那是会话内的事。"
        "importance<6 或内容来自不可信来源会被拒写, 返回 stored=false 及原因。"
    ),
    args_schema=RememberArgs,
    risk="write",
    needs_approval=True,
    auto_accept_default=True,   # read_auto 档下默认放行, 面板可见可删
)
async def remember(kind: str, text: str, importance: int = 6,
                   origin: str = "agent_inferred", source_ref: str = "",
                   trigger_keywords: str = "", supersession_key: str = "",
                   runtime: ToolRuntime = None) -> dict:
    username = runtime.state["username"]
    text = (text or "").strip()
    if not text:
        return {"ok": True, "stored": False, "reason": "记忆内容不能为空"}
    if kind not in VALID_KINDS:
        return {"ok": True, "stored": False, "reason": f"非法 kind: {kind}"}
    if origin == "untrusted":
        return {"ok": True, "stored": False,
                "reason": "不可信来源的内容不允许写入长期记忆"}
    if importance < config.ASSISTANT_MEMORY_MIN_IMPORTANCE:
        return {"ok": True, "stored": False,
                "reason": f"importance {importance} 低于门槛 "
                          f"{config.ASSISTANT_MEMORY_MIN_IMPORTANCE}, 视为噪声拒写"}
    if _text_hash(text) in set(runtime.state.get("memory_injected") or []):
        return {"ok": True, "stored": False,
                "reason": "该内容本轮已由记忆注入, 禁止回写成新记忆 (recall-loop)"}

    mid = await asyncio.to_thread(
        db.insert_memory, username, kind, origin, text, importance,
        source_ref, trigger_keywords, supersession_key,
    )
    await asyncio.to_thread(vector_index.upsert, mid, username, text, kind)
    runtime.stream_writer({"type": "memory_written", "id": mid,
                           "kind": kind, "text": text,
                           "importance": importance})
    return {"ok": True, "stored": True, "memory_id": mid}


@assistant_tool(
    name="recall_memory",
    description=(
        "主动检索长期记忆 (用户明确问『我之前说过/我的偏好是什么』时用)。"
        "日常对话不需要调它: 每轮开场已自动注入 topK 记忆。"
        "没有命中时 memories=[]。"
    ),
    args_schema=RecallArgs,
)
async def recall_memory(query: str, top_k: int = 5, runtime: ToolRuntime = None) -> dict:
    username = runtime.state["username"]
    hits = await asyncio.to_thread(vector_index.search, username, query, top_k * 2)
    scored = []
    for hit in hits:
        memory = await asyncio.to_thread(db.get_memory, username, hit["mid"])
        if not memory or memory.get("superseded"):
            continue
        scored.append((
            _decay_score(hit["cosine"], memory, query),
            {"id": memory["id"], "kind": memory["kind"], "text": memory["text"],
             "importance": memory["importance"], "ts": memory["ts"]},
        ))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[:top_k]
    await asyncio.to_thread(db.mark_recalled, [m["id"] for _, m in top])
    return {"ok": True, "found": bool(top),
            "memories": [{"score": round(s, 3), **m} for s, m in top]}


@assistant_tool(
    name="forget_memory",
    description=(
        "删除一条长期记忆。memory_id 来自 recall_memory 或用户转述的面板条目。"
        "删除不可逆; 用户没明确要求时不要调用。"
    ),
    args_schema=ForgetArgs,
    risk="write",
    needs_approval=True,
)
async def forget_memory(memory_id: int, runtime: ToolRuntime = None) -> dict:
    username = runtime.state["username"]
    existed = await asyncio.to_thread(db.get_memory, username, memory_id)
    if not existed:
        return {"ok": True, "found": False, "message": "记忆不存在或不属于当前用户"}
    await asyncio.to_thread(db.delete_memory, username, memory_id)
    await asyncio.to_thread(vector_index.delete, memory_id, username)
    return {"ok": True, "found": True, "deleted": memory_id}
