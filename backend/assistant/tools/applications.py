"""Owned application queries and explicitly confirmed local writes."""
import asyncio

from langchain.tools import ToolRuntime
from pydantic import BaseModel, ConfigDict, Field

import application_store as store
from application_models import ApplicationBody, ApplicationOutcomeBody, ApplicationEventBody, JdVersionBody, Stage
from assistant.tools.base import assistant_tool
from resume import store as resume_store


class ListArgs(BaseModel):
    # ToolNode injects ToolRuntime after the model has produced its arguments.
    # The public API models remain strict; tool schemas must ignore that
    # internal field while retaining strict validation for model-controlled data.
    model_config = ConfigDict(strict=True, extra="ignore")
    stage: Stage | None = None
    limit: int = Field(default=20, ge=1, le=50)


class IdArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    application_id: int = Field(gt=0)


class ApplicationToolBody(ApplicationBody):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="ignore")


class StageArgs(IdArgs):
    stage: Stage


class EventArgs(ApplicationEventBody):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="ignore")
    application_id: int = Field(gt=0)


class OutcomeArgs(ApplicationOutcomeBody):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="ignore")
    application_id: int = Field(gt=0)


class JdReadArgs(IdArgs):
    version_id: int | None = Field(default=None, gt=0)


class JdWriteArgs(JdVersionBody):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="ignore")
    application_id: int = Field(gt=0)


class JdRestoreArgs(IdArgs):
    version_id: int = Field(gt=0)
    expected_version: int = Field(ge=0)


def _owned(runtime, application_id):
    username = runtime.state["username"]
    item = store.get(username, application_id)
    return username, item if item and not item["archived"] else None


def _result(item):
    return {"ok": bool(item), "found": bool(item), "application": item,
            "message": "" if item else "投递档案不存在或已归档"}


@assistant_tool(
    name="list_applications",
    description="查询当前用户的投递档案列表。可按阶段筛选，返回档案 ID、公司、岗位、简历 ID 和复盘结果。",
    args_schema=ListArgs,
)
async def list_applications(stage: str = None, limit: int = 20, runtime: ToolRuntime = None) -> dict:
    args = ListArgs(stage=stage, limit=limit)
    rows = await asyncio.to_thread(store.list_all, runtime.state["username"])
    rows = [r for r in rows if not args.stage or r["stage"] == args.stage]
    fields = ("id", "company", "role_title", "stage", "resume_id", "updated_at")
    return {"ok": True, "found": bool(rows), "total": len(rows),
            "applications": [{**{k: r[k] for k in fields},
                               "result": (r["outcome"] or {}).get("result", "")}
                              for r in rows[:args.limit]]}


@assistant_tool(
    name="read_application",
    description="读取当前用户的一份投递档案。包含 JD、时间线、关联报告与结果复盘；ID 来自 list_applications。",
    args_schema=IdArgs,
)
async def read_application(application_id: int, runtime: ToolRuntime = None) -> dict:
    args = IdArgs(application_id=application_id)
    _, item = await asyncio.to_thread(_owned, runtime, args.application_id)
    return _result(item)


@assistant_tool(
    name="read_application_jd",
    description="读取当前用户投递档案的 JD 版本目录与当前版本正文；指定 version_id 可读取历史正文。更新或恢复前先读取最新版本号。",
    args_schema=JdReadArgs,
)
async def read_application_jd(application_id: int, version_id: int = None,
                               runtime: ToolRuntime = None) -> dict:
    args = JdReadArgs(application_id=application_id, version_id=version_id)
    username, item = await asyncio.to_thread(_owned, runtime, args.application_id)
    if not item:
        return _result(None)
    versions = await asyncio.to_thread(store.list_jd_versions, username, args.application_id)
    selected_id = args.version_id or (item["jd_version"] or {}).get("id")
    version = await asyncio.to_thread(store.get_jd_version, username, args.application_id, selected_id) if selected_id else None
    return {"ok": args.version_id is None or version is not None, "found": bool(version),
            "current_version": (item["jd_version"] or {}).get("version", 0),
            "versions": versions, "version": version}


@assistant_tool(
    name="update_application_jd",
    description="提交更新 JD 的待确认操作；调用后服务端先展示确认卡，用户批准才写入新版本。不访问外部网址；先读取当前版本号。不要只用文字模拟确认卡。",
    args_schema=JdWriteArgs, risk="write", needs_approval=True, always_confirm=True,
)
async def update_application_jd(application_id: int, jd_text: str, expected_version: int,
                                 source_url: str = "", runtime: ToolRuntime = None) -> dict:
    args = JdWriteArgs(application_id=application_id, jd_text=jd_text,
                       expected_version=expected_version, source_url=source_url)
    try:
        return _result(await asyncio.to_thread(store.save_jd, runtime.state["username"],
            args.application_id, args.jd_text, args.source_url, args.expected_version))
    except store.JdVersionConflict as exc:
        return {"ok": False, "found": True, "conflict": True, "message": str(exc)}


@assistant_tool(
    name="restore_application_jd",
    description="提交恢复历史 JD 的待确认操作；调用后服务端先展示确认卡，批准才追加新版本并保留历史。先读取版本目录与最新版本号。不要只用文字模拟确认卡。",
    args_schema=JdRestoreArgs, risk="write", needs_approval=True, always_confirm=True,
)
async def restore_application_jd(application_id: int, version_id: int, expected_version: int,
                                  runtime: ToolRuntime = None) -> dict:
    args = JdRestoreArgs(application_id=application_id, version_id=version_id, expected_version=expected_version)
    try:
        return _result(await asyncio.to_thread(store.save_jd, runtime.state["username"],
            args.application_id, "", "", args.expected_version, restore_id=args.version_id))
    except store.JdVersionConflict as exc:
        return {"ok": False, "found": True, "conflict": True, "message": str(exc)}


@assistant_tool(
    name="create_application",
    description="新建本地投递档案。仅记录，不会向雇主投递简历；每次写入都需用户确认。",
    args_schema=ApplicationToolBody, risk="write", needs_approval=True, always_confirm=True,
)
async def create_application(company: str, role_title: str, job_url: str = "", jd_text: str = "",
                             stage: str = "saved", resume_id: int = None,
                             runtime: ToolRuntime = None) -> dict:
    args = ApplicationBody(company=company, role_title=role_title, job_url=job_url,
                           jd_text=jd_text, stage=stage, resume_id=resume_id)
    username = runtime.state["username"]
    if resume_id and not await asyncio.to_thread(resume_store.get_resume, username, resume_id):
        return {"ok": False, "found": False, "message": "关联简历不存在"}
    item = await asyncio.to_thread(store.create, username, args.model_dump())
    return _result(item)


@assistant_tool(
    name="update_application_stage",
    description="更新本地投递档案的阶段。不会实际投递，每次更新都需用户确认。",
    args_schema=StageArgs, risk="write", needs_approval=True, always_confirm=True,
)
async def update_application_stage(application_id: int, stage: str,
                                   runtime: ToolRuntime = None) -> dict:
    args = StageArgs(application_id=application_id, stage=stage)
    username, item = await asyncio.to_thread(_owned, runtime, args.application_id)
    if not item:
        return _result(None)
    return _result(await asyncio.to_thread(store.update, username, args.application_id,
                                           {"stage": args.stage}))


@assistant_tool(
    name="add_application_note",
    description="添加本地投递档案的时间线备注。每次写入都需用户确认。",
    args_schema=EventArgs, risk="write", needs_approval=True, always_confirm=True,
)
async def add_application_note(application_id: int, note: str,
                               runtime: ToolRuntime = None) -> dict:
    args = EventArgs(application_id=application_id, note=note)
    username, item = await asyncio.to_thread(_owned, runtime, args.application_id)
    if not item:
        return _result(None)
    return _result(await asyncio.to_thread(store.add_event, username, args.application_id,
                                           args.note))


@assistant_tool(
    name="save_application_reflection",
    description="保存本地投递结果、反馈、反思和下一步。覆盖已有复盘前需先读取档案，每次写入需确认。",
    args_schema=OutcomeArgs, risk="write", needs_approval=True, always_confirm=True,
)
async def save_application_reflection(application_id: int, result: str = "", feedback: str = "",
                                      reflection: str = "", next_steps: str = "",
                                      tags: list[str] = None, runtime: ToolRuntime = None) -> dict:
    args = OutcomeArgs(application_id=application_id, result=result, feedback=feedback,
                       reflection=reflection, next_steps=next_steps, tags=tags or [])
    username, item = await asyncio.to_thread(_owned, runtime, args.application_id)
    if not item:
        return _result(None)
    return _result(await asyncio.to_thread(
        store.save_outcome, username, args.application_id,
        args.model_dump(exclude={"application_id"}),
    ))
