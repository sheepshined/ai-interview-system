"""actions.py — 提议型工具 (AGENT_PLAN §5.5)。

model_visible=False: 这两个工具不在 bind_tools 的可见面里。模型只能输出
结构化意图标记, 由 server 的入口构造提案; 执行权不在模型手上
(offerpilot ai/deterministic_actions.py:64-91 的同款约束)。

返回形态刻意不用 Command: ToolNode 对返回 Command 的工具不会自动补配对
ToolMessage (tool_node.py:881-916), 而返回普通 dict 会被自动包成 ToolMessage,
配对不变量 (§5.11) 白捡。提案载荷走内容里的 __proposal__ 标记,
由 graph 的 tools_node 解析后写入 state["pending_action"]。
"""
import uuid
from typing import Literal

import config
from assistant.tools.base import args_digest, assistant_tool
from langchain.tools import ToolRuntime
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ProposeInterviewArgs(BaseModel):
    model_config = ConfigDict(strict=True)

    role: str = Field(default="llm_app", description="岗位 key")
    question_count: int = Field(default=5, ge=1, le=20)
    difficulty: int = Field(default=2, ge=1, le=3)
    mode: Literal["standard", "project"] = Field(
        default="standard", description="standard | project")
    resume_ref: str = Field(default="", description="简历文件名, project 模式必填")
    focus: str = Field(default="", max_length=100,
                       description="定向主题 (如弱项分类), 作为首题方向, 可空")


class ProposeKbSessionArgs(BaseModel):
    model_config = ConfigDict(strict=True)

    question: str = Field(min_length=1, description="要带去知识库对话的问题")


class RequestActionArgs(BaseModel):
    model_config = ConfigDict(strict=True)

    intent: Literal["start_interview", "kb_session"] = Field(
        description="start_interview | kb_session")
    role: str = Field(default="llm_app")
    question_count: int = Field(default=5, ge=1, le=20)
    difficulty: int = Field(default=2, ge=1, le=3)
    mode: Literal["standard", "project"] = Field(default="standard")
    resume_ref: str = Field(default="")
    question: str = Field(default="")
    focus: str = Field(default="", max_length=100,
                       description="start_interview 时的定向主题, 可空")


@assistant_tool(
    name="request_action",
    description=(
        "当用户明确想开始面试或去知识库对话、且必填参数已齐时调用本工具生成提案。"
        "本工具只生成待确认提案, 不执行任何动作; 确认权在用户手上。"
        "参数不齐时不要调用, 先追问用户。"
        "intent=start_interview 需要 role/question_count/difficulty，当前只允许 mode=standard。"
        "若刚用 get_weakness_trend 发现持续弱项, 可把该弱项分类填进 focus 做定向面试。"
        "用户要求项目深挖时，不调用本工具，改为引导其去简历页上传或粘贴简历，"
        "再从面试配置页开始；intent=kb_session 需要 question。"
    ),
    args_schema=RequestActionArgs,
    risk="read",              # 只提议无副作用; 真正的确认闸是提案卡片
    needs_approval=False,
)
async def request_action(intent: str, role: str = "llm_app",
                         question_count: int = 5, difficulty: int = 2,
                         mode: str = "standard", resume_ref: str = "",
                         question: str = "", focus: str = "",
                         runtime: ToolRuntime = None) -> dict:
    session_id = runtime.state.get("session_id", 0)
    if intent == "start_interview":
        return propose_interview_impl(
            {"role": role, "question_count": question_count,
             "difficulty": difficulty, "mode": mode, "resume_ref": resume_ref,
             "focus": focus},
            session_id)
    if intent == "kb_session":
        return propose_kb_session_impl({"question": question}, session_id)
    return {"ok": False, "found": False, "message": f"未知 intent: {intent}"}


def _interview_editable_fields() -> list:
    """可编辑范围是服务端白名单 (offerpilot metadata.py:358-371)。
    role 不在其中: 身份字段结构性不可编辑。"""
    return [
        {"field": "question_count", "value_type": "number",
         "options": None, "clearable": False, "clear_value": None},
        {"field": "difficulty", "value_type": "enum",
         "options": [{"value": 1, "label": "Junior"},
                     {"value": 2, "label": "Intermediate"},
                     {"value": 3, "label": "Senior"}],
         "clearable": False, "clear_value": None},
    ]


def build_interview_proposal(args: dict, session_id: int) -> dict:
    role_info = config.ROLES.get(args.get("role", ""), {})
    difficulty = args.get("difficulty", 2)
    pending = {
        "operation_id": f"op_{session_id}_{uuid.uuid4().hex}",
        "kind": "interview",
        "human": (
            f"{role_info.get('title', args.get('role'))} · "
            f"{args.get('question_count')} 题 · "
            f"{config.DIFFICULTY_LABELS.get(difficulty, difficulty)} · "
            f"{'项目深挖' if args.get('mode') == 'project' else '题库出题'}"
            + (f" · 定向 {args['focus']}" if args.get("focus") else "")
            + (f" · 简历 {args['resume_ref']}" if args.get("resume_ref") else "")
        ),
        "args": args,
        "editable_fields": _interview_editable_fields(),
        "evidence": [],
        "confirmation_token": args_digest("propose_interview", args),
        "risk_hint": "确认后将跳转到面试页并开始一场真实计分的面试",
    }
    return pending


def validate_interview_args(args: dict) -> str:
    """返回错误文案 (空串=通过)。缺槽/非法值一律让模型去追问, 不许默认兜底。"""
    try:
        parsed = ProposeInterviewArgs.model_validate(args)
    except ValidationError as exc:
        return "面试参数无效: " + "; ".join(
            error.get("msg", "参数错误") for error in exc.errors())
    if parsed.role not in config.ROLES:
        return (f"岗位 {parsed.role} 不存在; 当前只有 "
                + "、".join(config.ROLES.keys()) + "。请向用户说明并确认。")
    if parsed.mode == "project":
        return ("助手暂不能安全读取用户归属的简历。请引导用户进入简历页上传或"
                "粘贴简历，再从面试配置页启动项目深挖。")
    return ""


def propose_interview_impl(args: dict, session_id: int) -> dict:
    err = validate_interview_args(args)
    if err:
        return {"ok": False, "found": False, "message": err}
    pending = build_interview_proposal(args, session_id)
    return {"ok": True, "found": True, "__proposal__": pending,
            "human": pending["human"],
            "note": "提案已生成, 等待用户确认。不要重复调用本工具。"}


def propose_kb_session_impl(args: dict, session_id: int) -> dict:
    try:
        parsed = ProposeKbSessionArgs.model_validate(args)
    except ValidationError as exc:
        return {"ok": False, "found": False,
                "message": "知识库问题无效: " + "; ".join(
                    error.get("msg", "参数错误") for error in exc.errors())}
    question = parsed.question.strip()
    if not question:
        return {"ok": False, "found": False, "message": "问题不能为空, 请先问清用户。"}
    pending = {
        "operation_id": f"op_{session_id}_{uuid.uuid4().hex}",
        "kind": "kb_session",
        "human": f"去知识库对话: {question[:40]}",
        "args": {"question": question},
        "editable_fields": [
            {"field": "question", "value_type": "long_text",
             "options": None, "clearable": False, "clear_value": None},
        ],
        "evidence": [],
        "confirmation_token": args_digest("propose_kb_session", args),
        "risk_hint": "确认后将跳转到知识库对话页并预填该问题",
    }
    return {"ok": True, "found": True, "__proposal__": pending,
            "human": pending["human"],
            "note": "提案已生成, 等待用户确认。不要重复调用本工具。"}


def validate_proposal_edit(kind: str, args: dict) -> str:
    if kind == "interview":
        return validate_interview_args(args)
    if kind == "kb_session":
        try:
            parsed = ProposeKbSessionArgs.model_validate(args)
        except ValidationError as exc:
            return "知识库问题无效: " + "; ".join(
                error.get("msg", "参数错误") for error in exc.errors())
        if not parsed.question.strip():
            return "知识库问题不能为空。"
        return ""
    return "该提案不支持编辑。"


# ---- 注册形态: model_visible=False, 进 registry 供 permission/观测, 但不进可见面 ----

@assistant_tool(
    name="propose_interview",
    description=(
        "生成一场面试的待确认提案 (不执行)。模型不可主动调用: "
        "由显式入口或意图标记经 server 构造。确认后才由前端跳转起面试。"
    ),
    args_schema=ProposeInterviewArgs,
    risk="execute",
    needs_approval=True,
    model_visible=False,
)
async def propose_interview(role: str = "llm_app", question_count: int = 5,
                            difficulty: int = 2, mode: str = "standard",
                            resume_ref: str = "", runtime: ToolRuntime = None) -> dict:
    args = {"role": role, "question_count": question_count,
            "difficulty": difficulty, "mode": mode, "resume_ref": resume_ref}
    return propose_interview_impl(args, runtime.state.get("session_id", 0))


@assistant_tool(
    name="propose_kb_session",
    description=(
        "生成一个『去知识库对话』的待确认提案 (不执行)。模型不可主动调用。"
    ),
    args_schema=ProposeKbSessionArgs,
    risk="execute",
    needs_approval=True,
    model_visible=False,
)
async def propose_kb_session(question: str, runtime: ToolRuntime = None) -> dict:
    return propose_kb_session_impl({"question": question},
                                   runtime.state.get("session_id", 0))
