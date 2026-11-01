"""User-isolated, read-only resume tools."""
from pydantic import BaseModel

from assistant.tools.base import assistant_tool
from langchain.tools import ToolRuntime
from resume import store


class NoArgs(BaseModel):
    pass


@assistant_tool(
    name="list_resume_files",
    description=(
        "列出用户已上传的简历 PDF 原件 (文件名/上传时间)。"
        "用于确认『我上周传的那份』指的是哪一份。"
        "没有上传过时 files=[]。"
    ),
    args_schema=NoArgs,
)
async def list_resume_files(runtime: ToolRuntime = None) -> dict:
    username = (runtime.state or {}).get("username", "")
    records = store.list_resumes(username)
    return {
        "ok": True,
        "found": bool(records),
        "files": [{
            "resume_id": item["id"],
            "title": item["title"],
            "file_name": item.get("file_name", ""),
            "source": item.get("source", ""),
            "parse_status": item.get("parse_status", ""),
            "updated_at": item.get("updated_at", ""),
        } for item in records],
        "message": "" if records else "尚未保存简历，请前往简历页上传或粘贴简历。",
    }


@assistant_tool(
    name="read_resume_summary",
    description=(
        "读取用户最近一份简历的结构化摘要 (姓名/技能/经历/项目)。"
        "起面试提案前用它确认简历是否已经由用户审核。"
    ),
    args_schema=NoArgs,
)
async def read_resume_summary(runtime: ToolRuntime = None) -> dict:
    username = (runtime.state or {}).get("username", "")
    record = store.latest_resume(username)
    if not record:
        return {"ok": True, "found": False,
                "message": "尚未保存简历，请前往简历页上传或粘贴简历。"}
    return {
        "ok": True,
        "found": True,
        "resume_id": record["id"],
        "title": record["title"],
        "reviewed": record.get("parse_status") == "reviewed",
        "content": record.get("content") or {},
        "evidence": record.get("evidence") or [],
    }
