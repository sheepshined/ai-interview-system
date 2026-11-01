"""records.py — 面试记录 (backend/agent/interview_records_*.md) 只读工具。

记录文件头部格式见 agent/graph.py:508-518 (含 `- **用户**: x`)。
按用户过滤靠解析头部, 不靠文件名。
"""
import asyncio
import os
import re
from typing import Optional

from pydantic import BaseModel, Field

import config
from assistant import budget
from assistant.tools.base import assistant_tool
from langchain.tools import ToolRuntime

_NAME_RE = re.compile(r"^interview_records_[0-9]{8}_[0-9]{6}_[0-9a-f]{6}\.md$")
_USER_RE = re.compile(r"-\s*\*\*用户\*\*:\s*(.+)$", re.M)
_ROLE_RE = re.compile(r"-\s*\*\*岗位\*\*:\s*(.+)$", re.M)


class ListRecordsArgs(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)


class RecordNameArgs(BaseModel):
    filename: str = Field(description="来自 list_interview_records 的文件名")


class SearchRecordsArgs(BaseModel):
    keyword: str = Field(min_length=1, description="要全文检索的关键词")
    limit: int = Field(default=8, ge=1, le=20, description="命中片段条数上限")


_SECTION_RE = re.compile(r"^##\s*(第\d+题[^\n]*)", re.M)
_TS_LEN = len("interview_records_20261018_172818")


def _search_sync(keyword: str, limit: int, username: str) -> dict:
    """在当前用户的记录文件里做关键词全文检索 (轻量, 不上向量: 记录量小)。

    每个文件最多取 3 条命中, 片段前后各带 80 字上下文, 并标注命中所在的
    「## 第N题」小节, 方便模型引用出处。
    """
    matches = []
    files_searched = 0
    try:
        names = sorted(os.listdir(config.INTERVIEW_RECORDS_DIR), reverse=True)
    except OSError:
        names = []
    for name in names:
        if not _NAME_RE.match(name):
            continue
        try:
            with open(os.path.join(config.INTERVIEW_RECORDS_DIR, name),
                      encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        meta = _parse_header(text[:600])
        if username and meta["user"] != username:
            continue
        files_searched += 1
        per_file = 0
        for m in re.finditer(re.escape(keyword), text, re.IGNORECASE):
            if per_file >= 3 or len(matches) >= limit:
                break
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 80)
            snippet = re.sub(r"\s+", " ", text[start:end]).strip()
            section = ""
            for s in _SECTION_RE.finditer(text, 0, m.start()):
                section = s.group(1)
            matches.append({
                "filename": name, "role": meta["role"],
                "timestamp": name[len("interview_records_"):_TS_LEN],
                "section": section, "snippet": snippet,
            })
            per_file += 1
        if len(matches) >= limit:
            break
    return {"matches": matches, "files_searched": files_searched}


@assistant_tool(
    name="search_interview_records",
    description=(
        "在当前用户的全部面试记录里按关键词全文检索, 返回命中片段"
        "(含所在文件名/第几题/前后文)。用户问『我哪次提到过 X / 哪个概念我"
        "当时怎么答的』时用它, 不要逐篇 read_interview_record 翻。"
        "要整篇原文时再按 filename 调 read_interview_record。"
        "无命中时 found=false, matches=[], 不是错误。"
    ),
    args_schema=SearchRecordsArgs,
)
async def search_interview_records(keyword: str, limit: int = 8,
                                   runtime: ToolRuntime = None) -> dict:
    username = runtime.state["username"]
    keyword = keyword.strip()
    if not keyword:
        return {"ok": True, "found": False, "matches": [],
                "files_searched": 0, "message": "关键词不能为空"}
    data = await asyncio.to_thread(_search_sync, keyword, limit, username)
    return {"ok": True, "found": bool(data["matches"]), **data}


def _parse_header(text: str) -> dict:
    user = _USER_RE.search(text)
    role = _ROLE_RE.search(text)
    return {
        "user": user.group(1).strip() if user else "",
        "role": role.group(1).strip() if role else "",
    }


def _list_sync(limit: int, username: str) -> list:
    out = []
    try:
        names = sorted(os.listdir(config.INTERVIEW_RECORDS_DIR), reverse=True)
    except OSError:
        return out
    for name in names:
        if not _NAME_RE.match(name):
            continue
        try:
            with open(os.path.join(config.INTERVIEW_RECORDS_DIR, name),
                      encoding="utf-8") as fh:
                head = fh.read(600)
        except OSError:
            continue
        meta = _parse_header(head)
        if username and meta["user"] != username:
            continue
        out.append({"filename": name, "role": meta["role"],
                    "timestamp": name[len("interview_records_"):
                                      len("interview_records_") + 15]})
        if len(out) >= limit:
            break
    return out


@assistant_tool(
    name="list_interview_records",
    description=(
        "列出当前用户最近的面试逐题记录文件 (filename/岗位/时间)。"
        "用于『我上次答了什么/某题我的原话』这类回溯。"
        "要分数与汇总用 list_reports, 记录文件只有逐题原文。"
        "没有记录时 found=false。"
    ),
    args_schema=ListRecordsArgs,
)
async def list_interview_records(limit: int = 10, runtime: ToolRuntime = None) -> dict:
    username = runtime.state["username"]
    records = await asyncio.to_thread(_list_sync, limit, username)
    return {"ok": True, "found": bool(records), "records": records}


@assistant_tool(
    name="read_interview_record",
    description=(
        "读取一份面试记录的全文 (逐题: 题目/你的回答/追问/标准答案/得分)。"
        "用户问『我当时怎么答的』时用。过长会截断。"
        "filename 来自 list_interview_records。不存在时 found=false。"
    ),
    args_schema=RecordNameArgs,
)
async def read_interview_record(filename: str, runtime: ToolRuntime = None) -> dict:
    if not _NAME_RE.match(filename or ""):
        return {"ok": True, "found": False, "message": "非法文件名"}
    path = os.path.join(config.INTERVIEW_RECORDS_DIR, filename)
    if not os.path.isfile(path):
        return {"ok": True, "found": False, "message": "记录不存在"}

    def _read():
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    text = await asyncio.to_thread(_read)
    meta = _parse_header(text[:600])
    if meta["user"] not in ("", runtime.state["username"]):
        return {"ok": True, "found": False, "message": "无权读取该记录"}
    shown, truncated = budget.truncate_output(text)
    return {"ok": True, "found": True, "content": shown,
            "truncated": truncated, "role": meta["role"]}
