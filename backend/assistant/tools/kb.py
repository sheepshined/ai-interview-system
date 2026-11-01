"""kb.py — 知识库只读工具。

不新建第二套 RAG: kb_ask 内部就是 server.py:906 的同一条链
(kb_parent.search + kb_llm.answer_from_knowledge), 只是把它暴露给 agent。
"""
import asyncio

from pydantic import BaseModel, Field

from assistant.tools.base import assistant_tool
from langchain.tools import ToolRuntime


class KbSearchArgs(BaseModel):
    q: str = Field(description="检索问题")
    top_k: int = Field(default=5, ge=1, le=10)


class KbAskArgs(BaseModel):
    question: str = Field(description="要回答的问题")
    top_k: int = Field(default=5, ge=1, le=10)


class ListNotesArgs(BaseModel):
    search: str = Field(default="", description="标题/内容关键词, 可空")


class NoteIdArgs(BaseModel):
    note_id: int = Field(description="来自 list_notes 的笔记 id")


@assistant_tool(
    name="kb_search",
    description=(
        "在用户的个人知识库里做向量检索, 返回最相关的笔记片段与来源标题。"
        "用于『我笔记里记过什么』这类定位。要成段回答用 kb_ask。"
        "检索为空时 results=[] 且 sparse=true, 表示库里没有相关内容。"
    ),
    args_schema=KbSearchArgs,
)
async def kb_search(q: str, top_k: int = 5, runtime: ToolRuntime = None) -> dict:
    import kb_parent
    username = runtime.state["username"]
    results = await asyncio.to_thread(kb_parent.search, username, q, top_k)
    return {"ok": True, "found": bool(results), "results": results,
            "sparse": kb_parent.is_sparse(results)}


@assistant_tool(
    name="kb_ask",
    description=(
        "基于用户知识库回答问题 (检索 + LLM 综合), 返回 answer 与 sources。"
        "用户问知识库里的概念/方法时用。sources 必须原样转述给用户作为出处。"
        "sparse=true 表示证据不足, 此时要明确说『笔记里没有』, 不许编。"
    ),
    args_schema=KbAskArgs,
)
async def kb_ask(question: str, top_k: int = 5, runtime: ToolRuntime = None) -> dict:
    import kb_llm
    import kb_parent
    username = runtime.state["username"]
    contexts = await asyncio.to_thread(kb_parent.search, username, question, top_k)
    result = await asyncio.to_thread(
        kb_llm.answer_from_knowledge, question, contexts
    )
    result = dict(result or {})
    return {"ok": True, "found": bool(result.get("answer")), **result}


@assistant_tool(
    name="list_notes",
    description=(
        "列出用户知识库的笔记 (id/标题/分类/更新时间)。"
        "用于先定位再精读: 拿到 id 后用 read_note 看全文。"
        "没有匹配时 notes=[]。"
    ),
    args_schema=ListNotesArgs,
)
async def list_notes(search: str = "", runtime: ToolRuntime = None) -> dict:
    import knowledge
    username = runtime.state["username"]
    notes = await asyncio.to_thread(knowledge.list_notes, username, search)
    slim = [
        {"id": n.get("id"), "title": n.get("title"),
         "category": n.get("category", ""), "updated_at": n.get("updated_at", "")}
        for n in notes
    ]
    return {"ok": True, "found": bool(slim), "notes": slim}


@assistant_tool(
    name="read_note",
    description=(
        "读取一篇笔记的全文 (含双链)。note_id 来自 list_notes 或 kb_search 的来源。"
        "过长会截断。不存在时 found=false。"
    ),
    args_schema=NoteIdArgs,
)
async def read_note(note_id: int, runtime: ToolRuntime = None) -> dict:
    import knowledge
    from assistant import budget
    username = runtime.state["username"]
    note = await asyncio.to_thread(knowledge.get_note, username, note_id)
    if not note:
        return {"ok": True, "found": False, "message": "笔记不存在"}
    shown, truncated = budget.truncate_output(note.get("content", ""))
    return {"ok": True, "found": True, "title": note.get("title"),
            "category": note.get("category", ""), "content": shown,
            "truncated": truncated}
