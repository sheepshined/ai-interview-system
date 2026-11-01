"""question_bank.py — 题库只读工具 (只检索, 不参与出题)。

面试进行中仍可使用，但只返回题面元数据，不返回标准答案。
"""
import asyncio

from pydantic import BaseModel, Field

from assistant import deps
from assistant.tools.base import assistant_tool
from langchain.tools import ToolRuntime

DEFAULT_ROLE = "llm_app"   # config.ROLES 目前仅此一个 (config.py:109)


class SearchQuestionsArgs(BaseModel):
    topic: str = Field(description="主题关键词, 如『RAG 分块』")
    top_k: int = Field(default=5, ge=1, le=10)


class ListCategoriesArgs(BaseModel):
    pass


@assistant_tool(
    name="search_questions",
    description=(
        "在面试题库里按主题检索题目 (题面/分类/难度), 不含标准答案。"
        "用于『题库里有没有关于 X 的题』这类问题。"
        "要标准答案要点请说明, 该工具不返回答案以免泄题。"
    ),
    args_schema=SearchQuestionsArgs,
)
async def search_questions(topic: str, top_k: int = 5, runtime: ToolRuntime = None) -> dict:
    retriever = deps.get_retriever()
    candidates = await asyncio.to_thread(
        retriever.get_question, topic=topic, role=DEFAULT_ROLE, top_k=top_k
    )
    slim = [
        {"id": q.get("id"), "question": q.get("question", "")[:120],
         "category": q.get("category", ""), "difficulty": q.get("difficulty", 2)}
        for q in (candidates or [])
    ]
    return {"ok": True, "found": bool(slim), "questions": slim}


@assistant_tool(
    name="list_categories",
    description=(
        "列出题库的知识分类 (如 RAG/Agent/微调)。"
        "用于回答『题库覆盖哪些方向』或帮用户选题复习。"
    ),
    args_schema=ListCategoriesArgs,
)
async def list_categories(runtime: ToolRuntime = None) -> dict:
    retriever = deps.get_retriever()
    categories = await asyncio.to_thread(
        retriever.get_categories, role=DEFAULT_ROLE
    )
    return {"ok": True, "found": bool(categories), "categories": categories or []}
