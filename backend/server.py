"""
server.py — AI 面试系统 FastAPI 后端 (LangGraph 版, 流式输出)

架构 (答辩稳定版): 面试流程由 LangGraph StateGraph 驱动 (agent/graph.py),
  WebSocket /ws/chat 仅作"人在回路驱动器": 接收 config/answer/end/report 消息,
  转为 graph 的 astream / Command(resume=...) 调用, 并把图推送的 custom event
  转发给前端。替代原 server.py 的 if/elif 手动编排。

接口:
  POST /api/login              登录认证 (SQLite + bcrypt + JWT)
  POST /api/register           注册新用户
  POST /api/config             配置面试参数 (需登录)
  GET  /api/roles              获取所有岗位列表 (需登录)
  POST /api/resume/parse-text  解析粘贴的文本简历 (需登录)
  POST /api/upload/resume      上传简历 PDF (需登录)
  GET  /api/reports*           报告查询 (需登录, 按用户隔离)
  GET  /api/interviews         会话列表 (需登录, 按用户隔离)
  WebSocket /ws/chat           实时面试对话 (握手需 ?token=<jwt>)
  GET  /                       静态前端页面
"""
import json
import logging
import os
import re
import sys
import uuid
import asyncio
from datetime import datetime
from typing import Optional, List

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

# 将项目根目录加入 sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from retrieval.retriever import HybridRetriever
from resume.parser import parse_resume, parse_resume_text, build_resume_context
from resume import store as resume_store
import jd_analysis
import config
import auth
import asr
import knowledge
import application_store
import growth
import qbank_admin
from application_models import ApplicationBody, ApplicationUpdateBody, ApplicationOutcomeBody, ApplicationEventBody, JdVersionBody, JdRestoreBody
import kb_parent
import kb_extract
import kb_llm
from auth import get_current_user, ws_authenticate
from common import match_role, get_difficulty_label, extract_skills
from starlette.concurrency import run_in_threadpool
from agent.graph import build_interview_graph
from agent.protocol import command_allowed, phase_error
from agent.chains import build_hint_chain
from agent.llm import get_fast_llm
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# v2.0 统筹智能体层 (AGENT_PLAN.md): 独立 WS 通道 + REST, 不改面试图
from assistant import db as assistant_db
from assistant import events as assistant_ev
from assistant import persistence
from assistant.graph import build_assistant_graph
from assistant import tools as assistant_tools
from langchain_core.messages import HumanMessage as _AssistantHumanMessage

# v0.9: 会话持久化 — SQLite checkpointer, 后端重启后可续接面试线程。
# 图以 astream 执行, 必须用 AsyncSqliteSaver; 服务端读状态的
# get_state 也相应改为 await aget_state。
try:
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    _SQLITE_SAVER_OK = True
except ImportError:  # 依赖缺失时退回进程内 MemorySaver
    _SQLITE_SAVER_OK = False

_logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# --- FastAPI 应用 ---
app = FastAPI(title="AI Interview System (LangGraph)", version="3.0.0")

# --- 知识库原始上传文件目录 (不再公开静态挂载; 经 /api/kb/files/{name} 鉴权下载) ---
KB_FILES_DIR = os.path.join(BASE_DIR, "kb_files")
os.makedirs(KB_FILES_DIR, exist_ok=True)

# 上传文件名允许字符: 中英文/数字/点/下划线/连字符 (过滤路径分隔符与特殊字符)
_UPLOAD_NAME_RE = re.compile(r"[^0-9A-Za-z一-龥._-]+")


def _sanitize_upload_filename(name: str) -> str:
    """净化客户端文件名: 丢弃目录部分, 替换危险字符, 防路径穿越与控制字符注入。"""
    base = os.path.basename(str(name or "").replace("\\", "/")).strip()
    base = base.lstrip(".")
    cleaned = _UPLOAD_NAME_RE.sub("_", base).strip("._")
    return cleaned[:120] if cleaned else "file"

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 全局状态 (懒加载检索器) ---
_retriever: Optional[HybridRetriever] = None
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")


def get_retriever() -> HybridRetriever:
    """懒加载混合检索器 (BM25 + 向量 + RRF)"""
    global _retriever
    if _retriever is None:
        print("[SERVER] 正在初始化混合检索器 (BM25 + 向量)...")
        _retriever = HybridRetriever()
    return _retriever


# --- LangGraph 引擎 (懒加载) ---
_graph = None
_checkpointer: Optional[MemorySaver] = None

# --- 用户库初始化 (建表 + 空库时预置演示账号 admin/123123) ---
auth.init_db()

# --- 知识库初始化 (v0.7: notes 表, 按用户隔离) ---
knowledge.init_db(config.KB_DB_PATH)

# --- 统筹智能体库初始化 (v2.0: 会话/消息/设置/长期记忆, 独立 assistant.db) ---
assistant_db.init_db()

# --- 简历库初始化 (原文与可编辑结构化副本分离, 按用户隔离) ---
resume_store.init_db()
application_store.init_db()


async def get_graph():
    """获取 (懒加载) 编译后的 LangGraph 面试图

    v0.9: checkpointer 升级为 SQLite 持久化 (backend/checkpoints.db),
    服务重启后未结束的面试线程可继续续接; 依赖缺失时退回 MemorySaver。
    v2.0: 连接与 saver 抽到 assistant.persistence 单例, 面试图与 assistant 图
    共用同一实例 (AGENT_PLAN §5.10); shutdown 钩子负责关连接防 graph hang。
    """
    global _graph, _checkpointer
    if _graph is None:
        r = get_retriever()
        _checkpointer = await persistence.get_shared_saver()
        _graph = build_interview_graph(r).compile(checkpointer=_checkpointer)
    return _graph


async def run_graph_stream(ws: WebSocket, graph, input_or_command, thread_id: str):
    """运行 graph、转发 custom event，并同步会话 phase。"""
    cfg = {"configurable": {"thread_id": thread_id}}
    final_values = {}
    try:
        snapshot = await graph.aget_state(cfg)
        previous = snapshot.values or {}
        last_decision = previous.get("decision")
    except Exception:
        last_decision = None
    try:
        async for mode, payload in graph.astream(
            input_or_command, cfg, stream_mode=["custom", "values"]
        ):
            if mode == "custom" and isinstance(payload, dict):
                await ws.send_json(payload)
            elif mode == "values" and isinstance(payload, dict):
                final_values = payload
                if thread_id in _sessions:
                    _sessions[thread_id]["phase"] = payload.get("phase", "")
                    _sessions[thread_id]["answered_count"] = payload.get(
                        "main_question_count", 0
                    )
                    if payload.get("report_id"):
                        _sessions[thread_id]["report_id"] = payload["report_id"]
                        application_id = _sessions[thread_id].get("application_id")
                        if application_id:
                            application_store.attach_interview(
                                _sessions[thread_id]["username"],
                                application_id,
                                payload["report_id"],
                            )
                decision = payload.get("decision")
                if decision and decision != last_decision:
                    last_decision = decision
                    await ws.send_json({
                        "type": "decision",
                        "action": decision.get("action", "next"),
                        "reason": decision.get("reason", ""),
                    })
    except WebSocketDisconnect:
        logger.info("WebSocket 在图执行期间断开 (thread=%s)", thread_id)
        raise
    except Exception as e:
        logger.exception("LangGraph 流程错误 (thread=%s): %s", thread_id, e)
        if thread_id in _sessions:
            _sessions[thread_id]["status"] = "error"
        try:
            await ws.send_json({"type": "error", "content": "面试流程执行失败，请重试"})
        except (WebSocketDisconnect, RuntimeError):
            logger.info("错误事件未发送：连接已关闭 (thread=%s)", thread_id)
    return final_values


async def get_graph_values(graph, thread_id: str) -> dict:
    """读取线程当前已提交状态，用于校验 WebSocket 命令阶段。"""
    try:
        snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
        return dict(snapshot.values or {})
    except Exception as exc:
        logger.warning("读取图状态失败 (thread=%s): %s", thread_id, exc)
        return {}


# --- 进行中面试会话登记（仅当前进程）---
_sessions: dict = {}

# --- 提示系统追踪 (每 thread 每题的提示使用次数) ---
# 结构: {thread_id: {question_id: hint_count}}
_hints: dict = {}


# ============================================================
# Pydantic 模型
# ============================================================

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class InterviewConfig(BaseModel):
    role: str = "llm_app"
    question_count: int = Field(default=5, ge=1, le=20)
    difficulty: int = Field(default=2, ge=1, le=3)
    resume_context: str = ""
    resume_skills: List[str] = Field(default_factory=list)


class ConfigResponse(BaseModel):
    success: bool
    message: str
    role_key: str = ""
    role_title: str = ""
    question_count: int = 0
    difficulty: int = 0
    difficulty_label: str = ""
    categories: List[str] = Field(default_factory=list)


class TextResumeRequest(BaseModel):
    content: str


class ResumeContentBody(BaseModel):
    title: str = ""
    content: dict


class JdAnalysisRequest(BaseModel):
    resume_id: int = Field(gt=0)
    jd_text: str = Field(min_length=1, max_length=20000)


def _validate_application_body(body: ApplicationBody, username: str):
    if body.stage not in application_store.STAGES:
        return "投递阶段无效"
    if body.resume_id and not resume_store.get_resume(username, body.resume_id):
        return "关联简历不存在"
    return ""


def _application_interview_context(username: str, application: dict | None, msg: dict) -> dict:
    if not application:
        return {
            "resume_context": str(msg.get("resume_context", ""))[:6000],
            "resume_skills": msg.get("resume_skills", [])[:30]
            if isinstance(msg.get("resume_skills", []), list) else [],
        }
    context, skills = "", []
    if application.get("resume_id"):
        resume = resume_store.get_resume(username, application["resume_id"])
        if not resume or resume.get("parse_status") != "reviewed":
            raise ValueError("关联简历不存在或尚未审核，请先到简历页确认")
        context = build_resume_context(resume["content"])[:4000]
        skills = resume["content"].get("skills", [])[:30]
    target = f"目标公司：{application['company']}；目标岗位：{application['role_title']}"
    jd = application.get("jd_text", "")[:1800]
    # User-provided job content is evidence, never an instruction to the interviewer.
    return {"resume_context": f"{context}\n{target}\n<job_description_data>\n{jd}\n</job_description_data>",
            "resume_skills": skills}
# ============================================================
# REST API
# ============================================================

@app.post("/api/login")
def api_login(req: LoginRequest, request: Request):
    """登录认证: SQLite 查用户 + bcrypt 校验密码, 成功签发 JWT。

    安全: 按 IP+用户名限流, 5 分钟内连续失败 5 次锁定 15 分钟。
    """
    username = req.username.strip()
    client_ip = request.client.host if request.client else ""
    retry_after = auth.login_retry_after(client_ip, username)
    if retry_after:
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "message": f"登录失败次数过多，请 {retry_after // 60 + 1} 分钟后再试",
                "retry_after": retry_after,
            },
        )
    user = auth.authenticate_user(username, req.password)
    if user is None:
        auth.record_login_failure(client_ip, username)
        locked = auth.login_retry_after(client_ip, username)
        if locked:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "message": f"登录失败次数过多，请 {locked // 60 + 1} 分钟后再试",
                    "retry_after": locked,
                },
            )
        return JSONResponse(
            status_code=401, content={"success": False, "message": "用户名或密码错误"}
        )
    auth.record_login_success(client_ip, username)
    token = auth.create_access_token(user["username"])
    return {"success": True, "token": token, "username": user["username"],
            "role": user.get("role", "user")}


@app.post("/api/register")
def api_register(req: RegisterRequest, request: Request):
    """注册新用户: 用户名 3-20 位字母/数字/下划线, 密码至少 6 位 (角色固定 user)。

    限流: 按 IP 限制窗口内的成功注册数 (防批量刷号); 校验失败不计数,
    避免共享出口 IP 上一次手误锁死他人正常注册。
    """
    client_ip = request.client.host if request.client else ""
    retry_after = auth.register_retry_after(client_ip)
    if retry_after:
        return JSONResponse(
            status_code=429,
            content={"success": False,
                     "message": f"注册尝试过于频繁，请 {max(1, retry_after // 60) + 1} 分钟后再试",
                     "retry_after": retry_after},
        )
    username = req.username.strip()
    try:
        user = auth.create_user(username, req.password)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    auth.record_register_success(client_ip)
    token = auth.create_access_token(user["username"])
    return {"success": True, "token": token, "username": user["username"],
            "role": user.get("role", "user")}


# ============================================================
# v1.3: 账号设置与管理员能力 (角色分级 / 改密码 / 用户管理 / 题库管理)
# ============================================================

def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """管理员依赖: 非 admin 角色一律 403。"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


class PasswordChangeBody(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class AdminPasswordBody(BaseModel):
    new_password: str = Field(min_length=1, max_length=128)


class AdminEnabledBody(BaseModel):
    enabled: bool


class AdminRoleBody(BaseModel):
    role: str


class QuestionImportBody(BaseModel):
    questions: list = Field(default_factory=list)
    dry_run: bool = False


@app.get("/api/account/me")
def api_account_me(user: dict = Depends(get_current_user)):
    """当前账号信息 (用户名 + 角色), 供前端按角色渲染管理功能。"""
    return {"success": True, "username": user["username"], "role": user.get("role", "user")}


@app.post("/api/account/password")
def api_account_password(body: PasswordChangeBody, user: dict = Depends(get_current_user)):
    """自助改密码: 必须验证旧密码; 新密码沿用注册规则 (≥6 位)。"""
    username = user["username"]
    if not auth.verify_user_password(username, body.old_password):
        return JSONResponse(status_code=400, content={"success": False, "message": "旧密码不正确"})
    try:
        auth.update_password(username, body.new_password)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    return {"success": True, "message": "密码已更新"}


@app.get("/api/admin/users")
def api_admin_users(admin: dict = Depends(require_admin)):
    """用户列表 (管理员), 不含密码哈希。"""
    return {"success": True, "users": auth.list_users(),
            "current": admin["username"]}


@app.post("/api/admin/users/{username}/password")
def api_admin_reset_password(username: str, body: AdminPasswordBody,
                             admin: dict = Depends(require_admin)):
    """管理员重置任意用户密码。"""
    if auth.get_user_record(username) is None:
        return JSONResponse(status_code=404, content={"success": False, "message": "用户不存在"})
    try:
        auth.update_password(username, body.new_password)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    return {"success": True, "message": f"已重置 {username} 的密码"}


@app.post("/api/admin/users/{username}/enabled")
def api_admin_set_enabled(username: str, body: AdminEnabledBody,
                          admin: dict = Depends(require_admin)):
    """启用/停用账号; 停用即时生效 (token 校验拒收)。"""
    if username == admin["username"]:
        return JSONResponse(status_code=400, content={"success": False, "message": "不能停用当前登录的管理员自己"})
    record = auth.get_user_record(username)
    if record is None:
        return JSONResponse(status_code=404, content={"success": False, "message": "用户不存在"})
    if not body.enabled and record["role"] == "admin" and auth.count_admins() <= 1:
        return JSONResponse(status_code=400, content={"success": False, "message": "至少保留一个启用的管理员"})
    auth.set_user_enabled(username, body.enabled)
    return {"success": True, "message": f"{username} 已{'启用' if body.enabled else '停用'}"}


@app.post("/api/admin/users/{username}/role")
def api_admin_set_role(username: str, body: AdminRoleBody,
                       admin: dict = Depends(require_admin)):
    """调整用户角色 (admin/user); 不允许降级最后一个启用的管理员。"""
    if username == admin["username"]:
        return JSONResponse(status_code=400, content={"success": False, "message": "不能修改当前登录的管理员自己的角色"})
    record = auth.get_user_record(username)
    if record is None:
        return JSONResponse(status_code=404, content={"success": False, "message": "用户不存在"})
    if body.role != "admin" and record["role"] == "admin" and auth.count_admins() <= 1:
        return JSONResponse(status_code=400, content={"success": False, "message": "至少保留一个启用的管理员"})
    try:
        auth.set_user_role(username, body.role)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    return {"success": True, "message": f"{username} 角色已设为 {body.role}"}


@app.get("/api/qbank/summary")
def api_qbank_summary(user: dict = Depends(get_current_user)):
    """题库公开摘要 (登录即可): 首页展示真实题量与分类数, 不暴露题目内容。"""
    questions = qbank_admin.load_questions(config.DATA_DIR)
    data = qbank_admin.stats(questions)
    return {"success": True, "total": data["total"],
            "categories": len(data["categories"]),
            "difficulty": data["difficulty"]}


@app.get("/api/admin/qbank/stats")
def api_admin_qbank_stats(admin: dict = Depends(require_admin)):
    """题库统计: markdown 事实源聚合 + 向量索引条数。"""
    questions = qbank_admin.load_questions(config.DATA_DIR)
    data = qbank_admin.stats(questions)
    data.pop("ids", None)
    try:
        data["index_count"] = get_retriever().vectorstore._collection.count()
    except Exception:
        data["index_count"] = None
    return {"success": True, "stats": data}


@app.get("/api/admin/qbank/list")
def api_admin_qbank_list(category: str = "", q: str = "", limit: int = 200, offset: int = 0,
                         admin: dict = Depends(require_admin)):
    """题库列表 (管理视图, 含答案摘要), 供浏览与删除; limit+offset 分页。"""
    questions = qbank_admin.load_questions(config.DATA_DIR)
    if category:
        questions = [item for item in questions if item.get("category") == category]
    if q:
        needle = q.strip().lower()
        questions = [item for item in questions
                     if needle in item.get("question", "").lower()
                     or needle in item.get("id", "").lower()]
    total = len(questions)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    rows = [{
        "id": item.get("id", ""), "category": item.get("category", ""),
        "difficulty": item.get("difficulty", 2), "difficulty_label": item.get("difficulty_label", ""),
        "type": item.get("type", "knowledge"), "question": item.get("question", ""),
        "answer_preview": (item.get("answer", "") or "")[:80],
        "source_file": item.get("source_file", ""),
    } for item in questions[offset:offset + limit]]
    return {"success": True, "total": total, "returned": len(rows), "questions": rows}


@app.get("/api/admin/qbank/template")
def api_admin_qbank_template(admin: dict = Depends(require_admin)):
    """导入模板: 下载一份标准 JSON 示例 (含全部可选字段)。"""
    template = [{
        "id": "llm_rag_101",
        "category": "RAG",
        "difficulty": 2,
        "type": "scenario",
        "scenario": "可选：面试官引入该题的场景背景",
        "question": "题面（必填）：例如请解释混合检索中 RRF 的作用",
        "answer": "标准答案（必填，评分对照用）",
        "scoring_points": ["得分点 1", "得分点 2"],
        "good_points": ["好答案特征（可选）"],
        "bad_points": ["差答案特征（可选）"],
        "followup_directions": ["预设追问方向（可选）"],
    }]
    return {"success": True, "template": template}


@app.post("/api/admin/qbank/import")
def api_admin_qbank_import(body: QuestionImportBody, admin: dict = Depends(require_admin)):
    """导入题目: JSON 数组 → 校验 → 追加进题库 markdown (dry_run 只校验不写)。"""
    if not isinstance(body.questions, list) or not body.questions:
        return JSONResponse(status_code=400, content={"success": False,
                                                      "message": "questions 须为非空数组"})
    target = os.path.join(config.DATA_DIR, "llm_app.md")
    if not os.path.isfile(target):
        return JSONResponse(status_code=400, content={"success": False,
                                                      "message": "题库文件不存在, 请先运行 python main.py build"})
    existing = qbank_admin.existing_ids_for(target)
    try:
        report = qbank_admin.import_questions(target, body.questions, existing,
                                              dry_run=body.dry_run)
    except Exception as exc:
        logger.warning("题库导入失败: %s", exc)
        return JSONResponse(status_code=500, content={"success": False, "message": f"导入失败: {exc}"})
    result = {"success": True, "dry_run": body.dry_run,
              "validated": report["validated"], "written": report["written"],
              "ids": report["ids"], "errors": report["errors"]}
    if report["errors"] and report["written"] == 0 and report["validated"] == 0:
        result["success"] = False
        result["message"] = f"全部 {len(report['errors'])} 条校验失败, 未写入"
    return result


@app.delete("/api/admin/qbank/question/{question_id}")
def api_admin_qbank_delete(question_id: str, admin: dict = Depends(require_admin)):
    """从题库 markdown 删除一道题 (向量索引需重建后生效)。"""
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", question_id or ""):
        return JSONResponse(status_code=400, content={"success": False, "message": "非法题目 id"})
    try:
        result = qbank_admin.delete_question(config.DATA_DIR, question_id)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    if not result.get("deleted"):
        return JSONResponse(status_code=404, content={"success": False, "message": "题目不存在"})
    return {"success": True, "message": f"已删除 {question_id}, 重建索引后生效"}


@app.post("/api/admin/qbank/rebuild")
async def api_admin_qbank_rebuild(admin: dict = Depends(require_admin)):
    """运行时重建向量索引 (互斥; 重建期间进行中的面试可能短暂受影响)。"""
    return await qbank_admin.rebuild_index(
        lambda: _retriever, config.DATA_DIR, config.CHROMA_DB_PATH)


@app.post("/api/config", response_model=ConfigResponse)
def api_config(cfg: InterviewConfig, user: dict = Depends(get_current_user)):
    """配置面试参数, 返回岗位信息与题目分类"""
    role_key = cfg.role if cfg.role in config.ROLES else "llm_app"
    role_info = config.ROLES[role_key]
    categories = get_retriever().get_categories(role=role_key)
    difficulty_label = get_difficulty_label(cfg.difficulty)
    return ConfigResponse(
        success=True,
        message=f"配置成功: {role_info['title']}, {cfg.question_count}题, {difficulty_label}",
        role_key=role_key, role_title=role_info["title"],
        question_count=cfg.question_count, difficulty=cfg.difficulty,
        difficulty_label=difficulty_label, categories=categories,
    )


@app.get("/api/roles")
def api_get_roles(user: dict = Depends(get_current_user)):
    """获取所有可选岗位列表"""
    roles = [{"key": k, "title": info["title"], "tags": info["tags"]}
             for k, info in config.ROLES.items()]
    return {"success": True, "roles": roles}


def _resume_response(record: dict) -> dict:
    content = record.get("content") or {}
    skills = content.get("skills") or []
    best_role, best_score = match_role(skills)
    return {
        "success": True,
        "resume_id": record["id"],
        "title": record["title"],
        "filename": record.get("file_name", ""),
        "source": record.get("source", ""),
        "content": content,
        "evidence": record.get("evidence") or [],
        "audit": resume_store.evidence_audit(record),
        "parse_status": record.get("parse_status", "classified"),
        "import_review": record.get("import_review") or {},
        "is_master": bool(record.get("is_master")),
        "char_count": len(record.get("parsed_data") or ""),
        "resume_context": build_resume_context(content),
        "suggested_role": best_role if best_score > 0 else None,
        "suggested_role_title": config.ROLES[best_role]["title"] if best_role and best_score > 0 else None,
        **content,
    }


@app.post("/api/resume/parse-text")
def api_parse_text_resume(req: TextResumeRequest, user: dict = Depends(get_current_user)):
    """解析并保存粘贴简历。原文保持不变，后续编辑只更新结构化副本。"""
    text = req.content.strip()
    if not text:
        return JSONResponse(status_code=400, content={"success": False, "message": "简历内容不能为空"})
    data = parse_resume_text(text)
    if not data:
        return JSONResponse(status_code=400, content={"success": False, "message": "简历解析失败"})
    content = {field: data.get(field, [] if field == "skills" else "")
               for field in resume_store.CONTENT_FIELDS}
    try:
        record = resume_store.create_resume(
            user["username"], data["raw_text"], content, source="text",
            title=content.get("name") or "粘贴简历",
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    return _resume_response(record)


@app.post("/api/upload/resume")
def api_upload_resume(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """上传并解析 PDF 简历 (parse_resume 内部调 LLM, 耗时较长, 用 def 不阻塞事件循环)"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"success": False, "message": "仅支持 PDF 文件"}

    MAX_SIZE = 10 * 1024 * 1024  # 10MB
    contents = file.file.read()
    if len(contents) == 0:
        return {"success": False, "message": "文件为空，请重新选择"}
    if len(contents) > MAX_SIZE:
        return {"success": False, "message": f"文件过大 ({len(contents)//1024//1024}MB)，最大支持 10MB"}

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = f"resume_{uuid.uuid4().hex}.pdf"
    save_path = os.path.join(UPLOAD_DIR, safe_name)
    try:
        with open(save_path, "wb") as f:
            f.write(contents)
    except OSError as e:
        print(f"[ERROR] 保存文件失败: {e}")
        return {"success": False, "message": "文件保存失败，请重试"}

    try:
        data = parse_resume(save_path)
    except Exception as e:
        print(f"[ERROR] parse_resume 抛出异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "message": f"简历解析异常: {type(e).__name__}", "detail": str(e)}
    if not data:
        return {"success": False, "message": "简历解析失败，请检查文件内容（可能为扫描件或加密PDF）"}

    content = {field: data.get(field, [] if field == "skills" else "")
               for field in resume_store.CONTENT_FIELDS}
    try:
        record = resume_store.create_resume(
            user["username"], data.get("raw_text", ""), content,
            source="upload", file_name=_sanitize_upload_filename(file.filename),
            title=content.get("name") or file.filename,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    return _resume_response(record)


@app.get("/api/resumes")
def api_list_resumes(user: dict = Depends(get_current_user)):
    records = resume_store.list_resumes(user["username"])
    return {"success": True, "resumes": [_resume_response(item) for item in records]}


@app.get("/api/resumes/latest")
def api_latest_resume(user: dict = Depends(get_current_user)):
    record = resume_store.latest_resume(user["username"])
    if not record:
        return JSONResponse(status_code=404, content={"success": False, "message": "尚未保存简历"})
    return _resume_response(record)


@app.get("/api/resumes/{resume_id}")
def api_get_resume(resume_id: int, user: dict = Depends(get_current_user)):
    record = resume_store.get_resume(user["username"], resume_id)
    if not record:
        return JSONResponse(status_code=404, content={"success": False, "message": "简历不存在"})
    return _resume_response(record)


@app.put("/api/resumes/{resume_id}")
def api_update_resume(resume_id: int, body: ResumeContentBody,
                      user: dict = Depends(get_current_user)):
    try:
        record = resume_store.update_content(
            user["username"], resume_id, body.content, body.title,
        )
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"success": False, "message": str(exc)})
    if not record:
        return JSONResponse(status_code=404, content={"success": False, "message": "简历不存在"})
    return _resume_response(record)


@app.post("/api/resumes/{resume_id}/confirm")
def api_confirm_resume(resume_id: int, user: dict = Depends(get_current_user)):
    record = resume_store.confirm_import(user["username"], resume_id)
    if not record:
        return JSONResponse(status_code=404, content={"success": False, "message": "简历不存在"})
    return _resume_response(record)


@app.post("/api/jd/analyze")
def api_analyze_jd(body: JdAnalysisRequest, user: dict = Depends(get_current_user)):
    record = resume_store.get_resume(user["username"], body.resume_id)
    if not record:
        return JSONResponse(status_code=404, content={"success": False, "message": "简历不存在"})
    if record.get("parse_status") != "reviewed":
        return JSONResponse(status_code=409, content={"success": False, "message": "请先审核并确认简历"})
    try:
        result = jd_analysis.analyze(record, body.jd_text)
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"success": False, "message": str(exc)})
    return {"success": True, "resume_id": body.resume_id, "analysis": result}


@app.get("/api/applications")
def api_list_applications(user: dict = Depends(get_current_user)):
    return {"success": True, "applications": application_store.list_all(user["username"]),
            "stages": list(application_store.STAGES)}


@app.post("/api/applications")
def api_create_application(body: ApplicationBody, user: dict = Depends(get_current_user)):
    error = _validate_application_body(body, user["username"])
    if error:
        return JSONResponse(status_code=422, content={"success": False, "message": error})
    data = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    return {"success": True, "application": application_store.create(user["username"], data)}


@app.get("/api/applications/{application_id}")
def api_get_application(application_id: int, user: dict = Depends(get_current_user)):
    item = application_store.get(user["username"], application_id)
    if not item:
        return JSONResponse(status_code=404, content={"success": False, "message": "投递档案不存在"})
    return {"success": True, "application": item}


@app.put("/api/applications/{application_id}")
def api_update_application(application_id: int, body: ApplicationUpdateBody,
                           user: dict = Depends(get_current_user)):
    error = _validate_application_body(body, user["username"])
    if error:
        return JSONResponse(status_code=422, content={"success": False, "message": error})
    data = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    if data.get("expected_jd_version") is None:
        data.pop("expected_jd_version", None)
    try:
        item = application_store.update(user["username"], application_id, data)
    except application_store.JdVersionConflict as exc:
        return JSONResponse(status_code=409, content={"success": False, "message": str(exc)})
    if not item:
        return JSONResponse(status_code=404, content={"success": False, "message": "投递档案不存在"})
    return {"success": True, "application": item}


@app.get("/api/applications/{application_id}/jd/versions")
def api_list_jd_versions(application_id: int, user: dict = Depends(get_current_user)):
    versions = application_store.list_jd_versions(user["username"], application_id)
    if versions is None:
        return JSONResponse(status_code=404, content={"success": False, "message": "投递档案不存在"})
    return {"success": True, "versions": versions}


@app.get("/api/applications/{application_id}/jd/versions/{version_id}")
def api_get_jd_version(application_id: int, version_id: int, user: dict = Depends(get_current_user)):
    version = application_store.get_jd_version(user["username"], application_id, version_id)
    if not version:
        return JSONResponse(status_code=404, content={"success": False, "message": "JD 版本不存在"})
    return {"success": True, "version": version}


def _jd_write_response(username, application_id, **kwargs):
    try:
        item = application_store.save_jd(username, application_id, **kwargs)
    except application_store.JdVersionConflict as exc:
        return JSONResponse(status_code=409, content={"success": False, "message": str(exc)})
    if not item:
        return JSONResponse(status_code=404, content={"success": False, "message": "投递档案或 JD 版本不存在，或档案已归档"})
    return {"success": True, "application": item}


@app.put("/api/applications/{application_id}/jd")
def api_save_jd_version(application_id: int, body: JdVersionBody, user: dict = Depends(get_current_user)):
    return _jd_write_response(user["username"], application_id, text=body.jd_text,
                              url=body.source_url, expected_version=body.expected_version)


@app.post("/api/applications/{application_id}/jd/versions/{version_id}/restore")
def api_restore_jd_version(application_id: int, version_id: int, body: JdRestoreBody,
                           user: dict = Depends(get_current_user)):
    return _jd_write_response(user["username"], application_id, text="", url="",
                              expected_version=body.expected_version, restore_id=version_id)


@app.post("/api/applications/{application_id}/events")
def api_add_application_event(application_id: int, body: ApplicationEventBody,
                              user: dict = Depends(get_current_user)):
    item = application_store.add_event(user["username"], application_id, body.note.strip())
    if not item:
        return JSONResponse(status_code=404, content={"success": False, "message": "投递档案不存在"})
    return {"success": True, "application": item}


@app.put("/api/applications/{application_id}/outcome")
def api_save_application_outcome(application_id: int, body: ApplicationOutcomeBody,
                                 user: dict = Depends(get_current_user)):
    data = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    data["tags"] = [tag.strip()[:60] for tag in data["tags"] if tag.strip()]
    item = application_store.save_outcome(user["username"], application_id, data)
    if not item:
        return JSONResponse(status_code=404, content={"success": False, "message": "投递档案不存在"})
    return {"success": True, "application": item}


@app.delete("/api/applications/{application_id}")
def api_archive_application(application_id: int, user: dict = Depends(get_current_user)):
    if not application_store.archive(user["username"], application_id):
        return JSONResponse(status_code=404, content={"success": False, "message": "投递档案不存在"})
    return {"success": True}


# ============================================================
# 报告管理 + 会话管理 API (阶段2)
# ============================================================

def _safe_report_id(report_id: str) -> bool:
    """校验 report_id 防路径穿越"""
    return bool(report_id) and "/" not in report_id and "\\" not in report_id and ".." not in report_id


def _load_report_meta(report_id: str) -> Optional[dict]:
    """读取报告 JSON 元数据 (存在性由调用方判断), 失败返回 None"""
    jp = os.path.join(config.REPORTS_DIR, f"{report_id}.json")
    try:
        with open(jp, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _report_owner(meta: Optional[dict]) -> str:
    """报告归属用户: v0.6 起记录 username; 旧报告无该字段, 归 admin"""
    return (meta or {}).get("username") or "admin"


# ---------- v1.1: 本地语音识别 (SenseVoice ONNX, 完全离线) ----------

@app.post("/api/asr")
async def api_asr(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """WAV 音频 → 文本。模型与推理全在本地 (SenseVoice int8), 不联网不耗 token。

    供面试答题输入与知识库问答输入共用; 解码是 CPU 密集操作,
    丢线程池执行避免阻塞事件循环。
    """
    if not asr.available():
        return JSONResponse(
            status_code=503,
            content={"success": False,
                     "error": "语音识别模型未就绪: 请将 SenseVoice 模型放到 backend/models/ "
                              "(见 .gitignore 中说明, 从 ~/.dsh/speech-to-text/ 拷贝)"},
        )
    data = await file.read()
    if not data:
        return {"success": False, "error": "音频内容为空"}
    try:
        result = await run_in_threadpool(asr.transcribe_wav_bytes, data)
    except ValueError as e:  # 位深/时长等音频格式问题
        return {"success": False, "error": str(e)}
    except Exception:
        _logger.exception("ASR 识别失败")
        return {"success": False, "error": "识别失败, 请重试"}
    return {"success": True, **result}


@app.get("/api/reports")
def api_list_reports(user: dict = Depends(get_current_user)):
    """列出当前用户的历史面试报告 (读 reports/*.json 元信息, 按用户隔离)"""
    reports = []
    if os.path.isdir(config.REPORTS_DIR):
        for fn in sorted(os.listdir(config.REPORTS_DIR), reverse=True):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(config.REPORTS_DIR, fn), encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("跳过无效报告元数据 %s: %s", fn, exc)
                continue
            if _report_owner(data) != user["username"]:
                continue
            reports.append({
                "report_id": data.get("report_id", fn[:-5]),
                "role_title": data.get("role_title", ""),
                "role_key": data.get("role_key", ""),
                "difficulty_label": data.get("difficulty_label", ""),
                "avg_score": data.get("avg_score", 0),
                "total_questions": data.get("total_questions", 0),
                "timestamp": data.get("timestamp", ""),
            })
    return {"success": True, "reports": reports}


@app.get("/api/reports/growth")
def api_reports_growth(user: dict = Depends(get_current_user)):
    """能力成长档案: 跨报告确定性聚合 (走势/分类弱项/总览), 按用户隔离。

    必须注册在 /api/reports/{report_id} 之前, 否则 growth 会被路径参数吞掉。
    """
    data = growth.build_growth(config.REPORTS_DIR, user["username"])
    return {"success": True, "growth": data}


@app.get("/api/reports/{report_id}")
def api_get_report(report_id: str, user: dict = Depends(get_current_user)):
    """获取某场面试报告全文 (markdown), 仅报告归属用户可访问"""
    if not _safe_report_id(report_id):
        return JSONResponse(status_code=400, content={"success": False, "message": "非法 report_id"})
    meta = _load_report_meta(report_id)
    if _report_owner(meta) != user["username"]:
        return JSONResponse(status_code=404, content={"success": False, "message": "报告不存在"})
    rp = os.path.join(config.REPORTS_DIR, f"{report_id}.md")
    if not os.path.isfile(rp):
        return JSONResponse(status_code=404, content={"success": False, "message": "报告不存在"})
    with open(rp, encoding="utf-8") as f:
        content = f.read()
    return {"success": True, "report_id": report_id, "content": content}


@app.get("/api/reports/{report_id}/radar")
def api_get_report_radar(report_id: str, user: dict = Depends(get_current_user)):
    """获取某场面试的雷达/维度数据 (四维均值 + 分类均值 + 逐题), 仅归属用户可访问"""
    if not _safe_report_id(report_id):
        return JSONResponse(status_code=400, content={"success": False, "message": "非法 report_id"})
    meta = _load_report_meta(report_id)
    if _report_owner(meta) != user["username"]:
        return JSONResponse(status_code=404, content={"success": False, "message": "雷达数据不存在"})
    if meta is None:
        return JSONResponse(status_code=404, content={"success": False, "message": "雷达数据不存在"})
    return {"success": True, "radar": meta}


@app.post("/api/logout")
def api_logout(
    user: dict = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
):
    """登出: 把当前 token 加入吊销黑名单 (v0.9)。"""
    if credentials and credentials.credentials:
        auth.revoke_token(credentials.credentials)
    return {"success": True, "message": "已登出"}


@app.get("/api/reports/{report_id}/weak-points")
def api_get_report_weak_points(
    report_id: str,
    threshold: int = 6,
    user: dict = Depends(get_current_user),
):
    """提取某场面试的低分考点 (v0.9, 供 THINK 错题本/间隔复习使用)

    score < threshold (默认 6 分) 的题目逐条返回, 附 good/bad 得分点;
    同时带回报告级的 weaknesses 与 learning_suggestions。
    """
    if not _safe_report_id(report_id):
        return JSONResponse(status_code=400, content={"success": False, "message": "非法 report_id"})
    meta = _load_report_meta(report_id)
    if _report_owner(meta) != user["username"]:
        return JSONResponse(status_code=404, content={"success": False, "message": "报告不存在"})
    jp = os.path.join(config.REPORTS_DIR, f"{report_id}.json")
    if not os.path.isfile(jp):
        return JSONResponse(status_code=404, content={"success": False, "message": "报告不存在"})
    with open(jp, encoding="utf-8") as f:
        data = json.load(f)
    threshold = max(0, min(int(threshold), 10))
    items = []
    for q in data.get("questions", []):
        try:
            score = int(q.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        if score < threshold:
            items.append({
                "question_id": q.get("question_id", ""),
                "question": q.get("question", ""),
                "category": q.get("category", ""),
                "score": score,
                "max_score": q.get("max_score", 10),
                "good_points": q.get("good_points", []) or [],
                "bad_points": q.get("bad_points", []) or [],
            })
    return {
        "success": True,
        "report_id": report_id,
        "role_title": data.get("role_title", ""),
        "timestamp": data.get("timestamp", ""),
        "avg_score": data.get("avg_score", 0),
        "threshold": threshold,
        "weak_count": len(items),
        "items": items,
        "weaknesses": data.get("weaknesses", []) or [],
        "learning_suggestions": data.get("learning_suggestions", []) or [],
    }


@app.get("/api/interviews")
def api_list_interviews(user: dict = Depends(get_current_user)):
    """列出当前用户在进程内登记的面试会话 (按用户隔离)。"""
    sessions = [
        s for s in _sessions.values() if s.get("username") == user["username"]
    ]
    return {"success": True, "interviews": sessions}


def _parse_md_header(filepath: str) -> Optional[dict]:
    """从逐题 md 文件头部提取元信息 (用户/岗位/难度/题量/时间)"""
    try:
        with open(filepath, encoding="utf-8") as f:
            head = f.read(2000)
    except OSError:
        return None
    meta = {"username": "anonymous"}
    for line in head.splitlines():
        line = line.strip()
        if not line.startswith("- **"):
            continue
        match = re.match(r"- \*\*(.+?)\*\*:\s*(.+)", line)
        if not match:
            continue
        key = match.group(1).strip()
        val = match.group(2).strip()
        key_map = {
            "用户": "username", "岗位": "role_title", "难度": "difficulty_label",
            "题量": "total_count", "简历": "has_resume", "时间": "timestamp",
        }
        if key in key_map:
            meta[key_map[key]] = val
    return meta


@app.get("/api/interview-records")
def api_list_interview_records(user: dict = Depends(get_current_user)):
    """列出当前用户的逐题面试记录 (按用户隔离)。"""
    records_dir = config.INTERVIEW_RECORDS_DIR
    records = []
    if not os.path.isdir(records_dir):
        return {"success": True, "records": []}
    for fn in sorted(os.listdir(records_dir), reverse=True):
        if not fn.startswith("interview_records_") or not fn.endswith(".md"):
            continue
        fp = os.path.join(records_dir, fn)
        meta = _parse_md_header(fp) or {}
        if meta.get("username", "anonymous") != user["username"]:
            continue
        records.append({
            "filename": fn,
            "role_title": meta.get("role_title", ""),
            "difficulty_label": meta.get("difficulty_label", ""),
            "total_count": meta.get("total_count", ""),
            "timestamp": meta.get("timestamp", ""),
            "size": os.path.getsize(fp),
        })
    return {"success": True, "records": records}


@app.get("/api/interview-records/{filename}")
def api_get_interview_record(filename: str, user: dict = Depends(get_current_user)):
    """获取某场面试的逐题记录全文 (md), 仅归属用户可访问。"""
    if not re.match(r"^interview_records_[A-Za-z0-9_]+\.md$", filename):
        return JSONResponse(status_code=400, content={"success": False, "message": "非法文件名"})
    fp = os.path.join(config.INTERVIEW_RECORDS_DIR, filename)
    if not os.path.isfile(fp):
        return JSONResponse(status_code=404, content={"success": False, "message": "记录不存在"})
    meta = _parse_md_header(fp) or {}
    if meta.get("username", "anonymous") != user["username"]:
        return JSONResponse(status_code=404, content={"success": False, "message": "记录不存在"})
    with open(fp, encoding="utf-8") as f:
        content = f.read()
    return {"success": True, "filename": filename, "content": content}


@app.delete("/api/interview-records/{filename}")
def api_delete_interview_record(filename: str, user: dict = Depends(get_current_user)):
    """删除某场面试的逐题记录, 仅归属用户可操作。"""
    if not re.match(r"^interview_records_[A-Za-z0-9_]+\.md$", filename):
        return JSONResponse(status_code=400, content={"success": False, "message": "非法文件名"})
    fp = os.path.join(config.INTERVIEW_RECORDS_DIR, filename)
    if not os.path.isfile(fp):
        return JSONResponse(status_code=404, content={"success": False, "message": "记录不存在"})
    meta = _parse_md_header(fp) or {}
    if meta.get("username", "anonymous") != user["username"]:
        return JSONResponse(status_code=404, content={"success": False, "message": "记录不存在"})
    try:
        os.remove(fp)
    except OSError as exc:
        return JSONResponse(status_code=500, content={"success": False, "message": f"删除失败: {exc}"})
    return {"success": True}


# ============================================================
# 个人知识库 API (v0.7 双链笔记; v0.8 文件/网址/分类/检索增强)
# ============================================================

class NoteRequest(BaseModel):
    title: str
    content: str = ""
    tags: List[str] = Field(default_factory=list)
    category: str = ""


class UrlNoteRequest(BaseModel):
    """网址收藏: 描述必填 (用户拍板: 不抓网页, 描述是检索主体)。"""
    url: str
    title: str = ""
    description: str
    category: str = ""


def _kb_after_write(username: str, note: dict, note_id: int) -> None:
    """写入后处理: 父文档索引同步 (失败不阻断)。"""
    kb_parent.sync_note(username, note)


@app.get("/api/kb/notes")
def api_kb_list_notes(search: str = "", tag: str = "", category: str = "",
                      user: dict = Depends(get_current_user)):
    """列出当前用户笔记 (search 匹配标题/内容, tag/category 精确匹配)。"""
    return {"success": True,
            "notes": knowledge.list_notes(user["username"], search=search,
                                          tag=tag, category=category)}


@app.get("/api/kb/categories")
def api_kb_categories(user: dict = Depends(get_current_user)):
    """用户已有分类及计数 (供筛选与 LLM 归类参考)。"""
    return {"success": True, "categories": knowledge.list_categories(user["username"])}


@app.post("/api/kb/notes")
def api_kb_create_note(req: NoteRequest, user: dict = Depends(get_current_user)):
    try:
        result = knowledge.create_note(
            user["username"], req.title, req.content, req.tags,
            category=req.category,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    note = knowledge.get_note(user["username"], result["id"])
    _kb_after_write(user["username"], note, result["id"])
    return {"success": True, **result}


@app.get("/api/kb/notes/{note_id}")
def api_kb_get_note(note_id: int, user: dict = Depends(get_current_user)):
    note = knowledge.get_note(user["username"], note_id)
    if not note:
        return JSONResponse(status_code=404, content={"success": False, "message": "笔记不存在"})
    backlinks = knowledge.get_backlinks(user["username"], note_id)
    return {"success": True, "note": note, "backlinks": backlinks}


@app.put("/api/kb/notes/{note_id}")
def api_kb_update_note(note_id: int, req: NoteRequest,
                       user: dict = Depends(get_current_user)):
    try:
        knowledge.update_note(user["username"], note_id, req.title, req.content,
                              req.tags, category=req.category)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    except LookupError:
        return JSONResponse(status_code=404, content={"success": False, "message": "笔记不存在"})
    note = knowledge.get_note(user["username"], note_id)
    _kb_after_write(user["username"], note, note_id)
    return {"success": True, "id": note_id, "title": req.title.strip()}


@app.delete("/api/kb/notes/{note_id}")
def api_kb_delete_note(note_id: int, user: dict = Depends(get_current_user)):
    if not knowledge.delete_note(user["username"], note_id):
        return JSONResponse(status_code=404, content={"success": False, "message": "笔记不存在"})
    kb_parent.remove_note(user["username"], note_id)
    return {"success": True}


@app.get("/api/kb/graph")
def api_kb_graph(semantic: bool = True, category: str = "",
                 user: dict = Depends(get_current_user)):
    """知识图谱: 节点=笔记(含虚节点,带类型/分类), 边=wiki([[链接]]) + semantic(语义)。"""
    cats = [c for c in category.split(",") if c.strip()] if category else []
    return {"success": True,
            "graph": knowledge.build_graph(user["username"],
                                           include_semantic=semantic,
                                           categories=cats)}


# ---------- v0.8: 文件上传 (模型提取 + 结构化) ----------

@app.post("/api/kb/notes/upload")
def api_kb_upload(files: List[UploadFile] = File(...),
                  user: dict = Depends(get_current_user)):
    """多文件批量入库: 保存原始文件 → 提取原文 → LLM 结构化 → 建笔记 → 向量同步。

    每文件独立成败, 返回明细; LLM 失败降级为原文直入。
    """
    if len(files) > 10:
        return JSONResponse(status_code=400, content={"success": False, "message": "单次最多上传 10 个文件"})
    results = []
    for f in files:
        name = f.filename or "未命名"
        entry = {"file": name, "status": "failed", "message": ""}
        try:
            data = f.file.read()
            if len(data) > 50 * 1024 * 1024:
                entry["message"] = "文件超过 50MB 限制"
                results.append(entry)
                continue
            # 保存原始文件到 kb_files 目录 (文件名净化防路径穿越, 下载需鉴权)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            clean_name = _sanitize_upload_filename(name)
            safe_name = f"{user['username']}_{ts}_{clean_name}"
            file_path = os.path.join(KB_FILES_DIR, safe_name)
            with open(file_path, "wb") as fp:
                fp.write(data)
            # 记录逻辑路径 (鉴权下载接口据此校验归属)
            file_url = f"/kb_files/{safe_name}"
            extracted = kb_extract.extract_file(name, data)
            structured = kb_llm.structure_file_note(name, extracted["raw_text"])
            created = knowledge.create_note(
                user["username"], structured["title"], structured["markdown"],
                tags=structured["tags"], source="file_upload",
                note_type="file", category=structured["category"],
                file_name=name, file_path=file_url,
            )
            note = knowledge.get_note(user["username"], created["id"])
            kb_parent.sync_note(user["username"], note)
            entry.update(status="created", title=created["title"],
                         note_id=created["id"], llm_used=structured["llm_used"],
                         pages=extracted["pages"], extract_mode=extracted["extract_mode"])
        except ValueError as exc:
            entry["message"] = str(exc)
            entry["status"] = "skipped" if "同名" in str(exc) else "failed"
        except Exception as exc:
            logger.exception("文件入库失败 %s", name)
            entry["message"] = f"处理异常: {type(exc).__name__}"
        results.append(entry)
    return {"success": True, "results": results}


@app.get("/api/kb/files/{filename}")
def api_kb_download_file(
    filename: str,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
):
    """知识库原始文件下载: Bearer 头或 ?token=<jwt> 鉴权, 且文件必须归属于该用户的笔记。

    替代原公开静态挂载, 防止"猜到 URL 即可访问他人上传原件"。
    """
    token = credentials.credentials if credentials else request.query_params.get("token", "")
    user = auth.get_user_from_token(token)
    if user is None:
        return JSONResponse(status_code=401, content={"success": False, "message": "未登录或登录已过期"})
    if not re.fullmatch(r"[0-9A-Za-z一-龥._-]+", filename) or ".." in filename:
        return JSONResponse(status_code=400, content={"success": False, "message": "非法文件名"})
    note = knowledge.find_note_by_file(user["username"], f"/kb_files/{filename}")
    if note is None:
        return JSONResponse(status_code=404, content={"success": False, "message": "文件不存在"})
    fp = os.path.join(KB_FILES_DIR, filename)
    if not os.path.isfile(fp):
        return JSONResponse(status_code=404, content={"success": False, "message": "文件不存在"})
    return FileResponse(fp)


# ---------- 启动迁移: 旧版绝对路径 file_path → /kb_files/ 逻辑路径 ----------

@app.on_event("startup")
def _migrate_kb_file_paths():
    migrated = knowledge.migrate_file_paths(KB_FILES_DIR)
    if migrated:
        logger.info("已迁移 %d 条旧版文件链接到 /kb_files/", migrated)


# ---------- v0.8: 网址收藏 ----------

@app.post("/api/kb/notes/url")
def api_kb_create_url_note(req: UrlNoteRequest, user: dict = Depends(get_current_user)):
    """网址收藏: 不抓网页, 描述必填; 内容格式带来源链接。"""
    url = (req.url or "").strip()
    description = (req.description or "").strip()
    title = (req.title or "").strip() or url[:80]
    if not url.startswith(("http://", "https://")):
        return JSONResponse(status_code=400, content={"success": False, "message": "网址必须以 http(s):// 开头"})
    if not description:
        return JSONResponse(status_code=400, content={"success": False, "message": "网址笔记必须填写描述内容"})
    content = f"> 🔗 来源: {url}\n\n## 我的描述\n\n{description}"
    try:
        result = knowledge.create_note(
            user["username"], title, content,
            note_type="url", category=req.category, source_url=url,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    note = knowledge.get_note(user["username"], result["id"])
    kb_parent.sync_note(user["username"], note)
    return {"success": True, **result}


# ---------- v0.8: 语义检索 / AI 整理 / 自动分类 / 重建 ----------

@app.get("/api/kb/search")
def api_kb_search(q: str = "", top_k: int = 5,
                  user: dict = Depends(get_current_user)):
    """向量检索知识库; top1 相关度低于阈值时带 sparse 标记 (前端提示导入)。"""
    results = kb_parent.search(user["username"], q, top_k=top_k)
    return {"success": True, "results": results,
            "sparse": kb_parent.is_sparse(results)}


class KbQaRequest(BaseModel):
    question: str
    top_k: int = 5
    session_id: int | None = None


class KbInterpretRequest(BaseModel):
    note_id: int | None = None
    title: str = ""
    content: str = ""


@app.post("/api/kb/qa")
def api_kb_qa(req: KbQaRequest, user: dict = Depends(get_current_user)):
    """RAG 问答: 检索 → LLM 回答 → 自动持久化会话与消息。"""
    q = (req.question or "").strip()
    if not q:
        return {"success": False, "error": "问题不能为空"}

    username = user["username"]
    # 确定会话: 有 session_id 就用, 没有就新建
    session_id = req.session_id
    if session_id:
        sess = knowledge.get_chat_session(username, session_id)
        if not sess:
            return {"success": False, "error": "会话不存在"}
    else:
        title = q[:20] + ("…" if len(q) > 20 else "")
        sess = knowledge.create_chat_session(username, title)
        session_id = sess["id"]

    # 存用户问题
    knowledge.append_chat_message(session_id, "user", q)

    # 检索 + LLM
    contexts = kb_parent.search(username, q, top_k=req.top_k)
    result = kb_llm.answer_from_knowledge(q, contexts)

    # 存 AI 回答
    knowledge.append_chat_message(session_id, "assistant", result["answer"],
                                   sources=result.get("sources"),
                                   sparse=result.get("sparse", False))

    return {"success": True, "session_id": session_id, **result}


@app.post("/api/kb/interpret")
def api_kb_interpret(req: KbInterpretRequest,
                     user: dict = Depends(get_current_user)):
    """只读解读当前草稿；note_id 仅用于校验笔记归属，不覆盖草稿。"""
    stored_note = None
    if req.note_id is not None:
        stored_note = knowledge.get_note(user["username"], req.note_id)
        if not stored_note:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "笔记不存在"},
            )

    title = (req.title or "").strip() or (stored_note or {}).get("title", "")
    content = req.content or ""
    if not content.strip():
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "笔记内容不能为空"},
        )
    if len(title) > knowledge.MAX_TITLE_LEN:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": f"标题过长 (最多 {knowledge.MAX_TITLE_LEN} 字)"},
        )
    if len(content) > knowledge.MAX_CONTENT_LEN:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": f"内容过长 (最多 {knowledge.MAX_CONTENT_LEN} 字)"},
        )

    interpretation = kb_llm.interpret_note(title, content)
    if not interpretation:
        return JSONResponse(
            status_code=502,
            content={"success": False, "message": "AI 解读失败, 请稍后重试"},
        )
    return {"success": True, "interpretation": interpretation}


# ---------- v0.9: AI 对话会话管理 ----------

@app.get("/api/kb/chat/sessions")
def api_kb_chat_list(user: dict = Depends(get_current_user)):
    sessions = knowledge.list_chat_sessions(user["username"])
    return {"success": True, "sessions": sessions}


@app.post("/api/kb/chat/sessions")
def api_kb_chat_create(user: dict = Depends(get_current_user)):
    title = "新对话"
    sess = knowledge.create_chat_session(user["username"], title)
    return {"success": True, "session": sess}


@app.get("/api/kb/chat/sessions/{session_id}")
def api_kb_chat_get(session_id: int, user: dict = Depends(get_current_user)):
    sess = knowledge.get_chat_session(user["username"], session_id)
    if not sess:
        return {"success": False, "error": "会话不存在"}
    messages = knowledge.list_chat_messages(user["username"], session_id)
    return {"success": True, "session": sess, "messages": messages}


@app.patch("/api/kb/chat/sessions/{session_id}")
def api_kb_chat_rename(session_id: int, body: dict = None,
                        user: dict = Depends(get_current_user)):
    title = (body or {}).get("title", "").strip()
    if not title:
        return {"success": False, "error": "标题不能为空"}
    ok = knowledge.rename_chat_session(user["username"], session_id, title)
    return {"success": ok}


@app.delete("/api/kb/chat/sessions/{session_id}")
def api_kb_chat_delete(session_id: int, user: dict = Depends(get_current_user)):
    ok = knowledge.delete_chat_session(user["username"], session_id)
    return {"success": ok}


@app.post("/api/kb/tidy")
def api_kb_tidy(note_id: int, user: dict = Depends(get_current_user)):
    """AI 整理笔记内容为结构化 Markdown (编辑页手动触发)。"""
    note = knowledge.get_note(user["username"], note_id)
    if not note:
        return JSONResponse(status_code=404, content={"success": False, "message": "笔记不存在"})
    tidied = kb_llm.tidy_markdown(note["content"])
    if not tidied:
        return JSONResponse(status_code=502, content={"success": False, "message": "AI 整理失败, 请稍后重试"})
    return {"success": True, "content": tidied}


@app.post("/api/kb/auto-category")
def api_kb_auto_category(note_id: int, user: dict = Depends(get_current_user)):
    """AI 自动分类建议: 未手动分类时写回 (手动分类永远优先)。"""
    note = knowledge.get_note(user["username"], note_id)
    if not note:
        return JSONResponse(status_code=404, content={"success": False, "message": "笔记不存在"})
    existing = [c["category"] for c in knowledge.list_categories(user["username"])]
    suggestion = kb_llm.suggest_category(note["title"], note["content"], existing)
    if not suggestion:
        return JSONResponse(status_code=502, content={"success": False, "message": "分类建议生成失败"})
    return {"success": True, **suggestion}


@app.post("/api/kb/rebuild")
def api_kb_rebuild(user: dict = Depends(get_current_user)):
    """手动触发该用户向量 + 语义关联全量重建。"""
    stats = kb_parent.rebuild(user["username"])
    return {"success": True, **stats}


@app.post("/api/kb/notes/{note_id}/auto-link")
def api_kb_auto_link(note_id: int, user: dict = Depends(get_current_user)):
    """智能关联: 为已有笔记补全 [[双链]] (孤立笔记融入知识图谱, 编辑页手动触发)。

    检索最相关的 top3 笔记 (相关度 ≥ 语义边阈值), 追加缺失的双链到正文;
    与 from-report 的入库自动关联同一套标准, 但作用于已存在的老笔记。
    """
    note = knowledge.get_note(user["username"], note_id)
    if not note:
        return JSONResponse(status_code=404, content={"success": False, "message": "笔记不存在"})
    title = note["title"]
    content = note.get("content") or ""
    if not content.strip():
        return JSONResponse(status_code=400, content={"success": False, "message": "笔记内容为空, 无法关联"})

    query_text = f"{title}\n{content[:400]}"
    related = [
        m for m in kb_parent.search(user["username"], query_text, top_k=10)
        if m["note_id"] != note_id
        and m["score"] >= kb_parent.SEM_LINK_THRESHOLD
        and m.get("title")
    ][:3]
    # 只追加尚不存在的链接, 已有的不重复
    new_titles = [m["title"] for m in related if f"[[{m['title']}]]" not in content]
    if not new_titles:
        return {"success": True, "linked": [], "message": "暂无足够相关的新笔记可关联"}

    if "## 相关笔记" in content:
        new_content = content.rstrip() + "".join(f"\n- [[{t}]]" for t in new_titles)
    else:
        new_content = content.rstrip() + "\n\n## 相关笔记" + "".join(f"\n- [[{t}]]" for t in new_titles)
    try:
        knowledge.update_note(user["username"], note_id, title, new_content,
                              note["tags"], note.get("category") or "")
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})
    fresh = knowledge.get_note(user["username"], note_id)
    kb_parent.sync_note(user["username"], fresh)
    return {"success": True, "linked": new_titles}


class ReportImportRequest(BaseModel):
    """报告薄弱点一键入库: 每条 {topic, suggestion} → 一篇笔记。"""
    items: List[dict]
    report_id: str = ""


@app.post("/api/kb/notes/from-report")
def api_kb_import_from_report(req: ReportImportRequest,
                              user: dict = Depends(get_current_user)):
    """面试报告薄弱点/学习建议批量入库 (source=interview_report, 自动打标签)。

    v0.8: 入库后逐条向量检索知识库, 返回 coverage (已有覆盖/缺失提示)。
    """
    created, skipped = [], []
    created_ids = set()   # 本轮新建笔记 id: 覆盖检测需排除 (避免"自我覆盖"误判)
    # 自动关联: 相关度达到语义边阈值才追加 [[双链]], 每条最多 3 条
    LINK_SCORE = getattr(kb_parent, "SEM_LINK_THRESHOLD", 0.66)
    LINK_TOP_K = 3
    for item in req.items[:50]:  # 防御性上限
        title = str(item.get("topic", "")).strip()[:knowledge.MAX_TITLE_LEN]
        suggestion = str(item.get("suggestion", "")).strip()
        if not title:
            continue
        content = (
            f"**来源面试报告**: {req.report_id or '未记录'}\n\n"
            f"**学习建议**:\n\n{suggestion}\n\n"
            "*此笔记由面试报告薄弱点自动创建，可编辑补充。*"
        )
        try:
            result = knowledge.create_note(
                user["username"], title, content,
                tags=["面试薄弱点"], source="interview_report",
            )
        except ValueError:
            skipped.append(title)  # 同名笔记已存在, 跳过不覆盖
            continue

        created.append(result)
        created_ids.add(result["id"])

        # 自动融入知识图谱: 检索相关已有笔记, 追加 [[双链]] 实线边。
        # 用"标题+建议"作为查询比单标题信息更足; 排除本轮新建的薄弱点(它们互查只会抱团)。
        try:
            query_text = f"{title} {suggestion}".strip()
            related = [
                m for m in kb_parent.search(user["username"], query_text, top_k=10)
                if m["note_id"] not in created_ids
                and m["score"] >= LINK_SCORE
                and m.get("title")
            ][:LINK_TOP_K]
            if related:
                link_block = "\n\n## 相关笔记\n" + "".join(
                    f"\n- [[{m['title']}]]" for m in related
                )
                fresh = knowledge.get_note(user["username"], result["id"])
                if fresh and "[[" not in (fresh.get("content") or ""):
                    knowledge.update_note(
                        user["username"], result["id"],
                        fresh["title"], fresh["content"].rstrip() + link_block,
                        fresh["tags"], fresh["category"],
                    )
        except Exception as exc:
            logger.warning("薄弱点自动关联失败 (note=%s): %s", result["id"], exc)

        # 向量在最终内容(含双链)确定后再刷新, 保证后续检索能感知新链接
        note = knowledge.get_note(user["username"], result["id"])
        if note:
            kb_parent.sync_note(user["username"], note)

    # 覆盖检测: 每条薄弱点在知识库中检索相关内容 (向量库不可用时静默跳过)
    # 排除本轮刚创建的薄弱点笔记自身 —— 否则检索必然命中自己, 缺失提示永不触发
    coverage = []
    for item in req.items[:50]:
        topic = str(item.get("topic", "")).strip()
        if not topic:
            continue
        raw_matched = kb_parent.search(user["username"], topic, top_k=6)
        matched = [m for m in raw_matched if m["note_id"] not in created_ids][:3]
        coverage.append({
            "topic": topic,
            "matched": [
                {"note_id": m["note_id"], "title": m["title"],
                 "note_type": m["note_type"], "score": m["score"]}
                for m in matched if m["score"] >= kb_parent.SPARSE_THRESHOLD
            ],
            "sparse": kb_parent.is_sparse(matched),
        })
    return {"success": True, "created": created, "skipped": skipped,
            "coverage": coverage}


# ============================================================
# WebSocket /ws/chat (LangGraph 驱动)
# ============================================================

@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    """实时面试对话；握手需带 ?token=<jwt>，所有 resume 命令都先按 graph phase 校验。"""
    user = ws_authenticate(ws)
    if user is None:
        # accept 前直接 close → 服务端拒绝握手 (HTTP 403)
        await ws.close(code=4401)
        return
    await ws.accept()
    thread_id = None

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "content": "无效的 JSON 格式"})
                continue
            if not isinstance(msg, dict):
                await ws.send_json({"type": "error", "content": "消息必须是 JSON 对象"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "config":
                thread_id = msg.get("thread_id") or f"iv_{uuid.uuid4().hex[:12]}"
                role = msg.get("role", "llm_app")
                if role not in config.ROLES:
                    role = "llm_app"
                # 面试模式: standard=题库检索; project=全程项目深挖; hybrid=项目热身题+题库
                interview_mode = msg.get("mode", "standard")
                if interview_mode not in ("standard", "project", "hybrid"):
                    interview_mode = "standard"
                try:
                    count = max(1, min(int(msg.get("question_count", 5)), 20))
                    diff = int(msg.get("difficulty", 2))
                except (TypeError, ValueError):
                    await ws.send_json({"type": "error", "content": "题量或难度格式错误"})
                    continue
                if diff not in config.DIFFICULTY_LABELS:
                    await ws.send_json({"type": "error", "content": "难度必须为 1、2 或 3"})
                    continue
                # hybrid 的项目热身题数 (默认 5, 1-8); 题量口径: 热身题额外再加题库题
                try:
                    warmup = max(1, min(int(msg.get("warmup_count", 5)), 8))
                except (TypeError, ValueError):
                    warmup = 5
                if interview_mode != "hybrid":
                    warmup = 0
                total = min(count + warmup, 20)

                application_id = msg.get("application_id")
                current_application = None
                if application_id is not None:
                    if type(application_id) is int and application_id > 0:
                        current_application = application_store.get(user["username"], application_id)
                    if not current_application or current_application.get("archived"):
                        await ws.send_json({"type": "error", "content": "投递档案不存在或无权访问"})
                        continue

                try:
                    interview_context = _application_interview_context(user["username"], current_application, msg)
                except ValueError as exc:
                    await ws.send_json({"type": "error", "content": str(exc)})
                    continue

                if interview_mode in ("project", "hybrid") and not interview_context["resume_context"].strip():
                    await ws.send_json({"type": "error", "content": "该模式需要先上传/粘贴简历"})
                    continue

                # JD: 投递档案取档案 JD (已拼入 resume_context); 否则取配置阶段提交的 jd_text,
                # 同样按数据标签拼入简历上下文, 并单独入 state 供项目出题链显式对齐
                jd_text = ""
                if current_application:
                    jd_text = str(current_application.get("jd_text", ""))[:20000].strip()
                else:
                    jd_text = str(msg.get("jd_text", ""))[:20000].strip()
                    if jd_text:
                        interview_context["resume_context"] += (
                            f"\n<job_description_data>\n{jd_text[:1800]}\n</job_description_data>"
                        )

                try:
                    graph = await get_graph()
                except Exception as exc:
                    logger.exception("引擎初始化失败: %s", exc)
                    await ws.send_json({"type": "error", "content": "引擎初始化失败，请检查服务配置"})
                    continue

                retriever = get_retriever()
                role_info = config.ROLES[role]
                existing = _sessions.get(thread_id)
                if (
                    existing
                    and existing.get("status") == "ongoing"
                    and msg.get("thread_id")
                    and existing.get("username") != user["username"]
                ):
                    # 会话归属校验: 不能续接他人的 thread_id
                    await ws.send_json({"type": "error", "content": "会话不存在或无权访问"})
                    continue
                if existing and existing.get("status") == "ongoing" and msg.get("thread_id"):
                    await ws.send_json({
                        "type": "config_ok", "content": "会话已恢复, 请继续作答",
                        "thread_id": thread_id,
                        "role_key": existing["role_key"], "role_title": existing["role_title"],
                        "question_count": existing["question_count"],
                        "difficulty": existing["difficulty"],
                        "difficulty_label": existing.get("difficulty_label", ""),
                        "categories": retriever.get_categories(role=existing["role_key"]),
                        "phase": existing.get("phase", ""),
                        "application_id": existing.get("application_id"),
                        "resumed": True,
                    })
                    await ws.send_json({
                        "type": "status",
                        "content": "已恢复内存中的会话状态",
                    })
                    continue

                # handoff 消费: 统筹助手批准的定向面试意图 (单次有效, 30 分钟 TTL)
                from assistant import handoff as assistant_handoff
                handoff_intent = assistant_handoff.consume_intent(user["username"])
                handoff_focus = (handoff_intent or {}).get("focus", "").strip()

                await ws.send_json({
                    "type": "config_ok", "content": "配置完成",
                    "thread_id": thread_id,
                    "role_key": role, "role_title": role_info["title"],
                    "question_count": total, "difficulty": diff,
                    "difficulty_label": get_difficulty_label(diff),
                    "categories": retriever.get_categories(role=role),
                    "application_id": application_id,
                    "interview_mode": interview_mode,
                    "warmup_count": warmup,
                    "resumed": False,
                })
                _sessions[thread_id] = {
                    "thread_id": thread_id, "role_key": role, "role_title": role_info["title"],
                    "question_count": total, "difficulty": diff,
                    "difficulty_label": get_difficulty_label(diff),
                    "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "ongoing",
                    "phase": "starting",
                    "answered_count": 0,
                    "username": user["username"],
                    "application_id": application_id,
                }
                if handoff_intent:
                    _sessions[thread_id]["handoff_focus"] = handoff_focus

                initial_state = {
                    "thread_id": thread_id, "role_key": role, "difficulty": diff,
                    "total_count": total,
                    "username": user["username"],
                    "interview_mode": interview_mode,
                    "warmup_count": warmup,
                    "jd_text": jd_text,
                    **interview_context,
                    "application_id": application_id,
                }
                if handoff_focus:
                    initial_state["first_topic_hint"] = handoff_focus
                if application_id:
                    if current_application and current_application.get("stage") != "interview":
                        application_store.update(
                            user["username"], application_id,
                            {**current_application, "stage": "interview"},
                        )
                await run_graph_stream(ws, graph, initial_state, thread_id)

            elif msg_type == "answer":
                if not thread_id:
                    await ws.send_json({"type": "error", "content": "请先发送 config 配置面试"})
                    continue
                answer = str(msg.get("content", "")).strip()
                if not answer:
                    await ws.send_json({"type": "error", "content": "回答不能为空"})
                    continue
                if len(answer) > 5000:
                    await ws.send_json({"type": "error", "content": "单次回答不能超过 5000 字"})
                    continue
                graph = await get_graph()
                values = await get_graph_values(graph, thread_id)
                phase = values.get("phase", "")
                if not command_allowed("answer", phase):
                    await ws.send_json({
                        "type": "error",
                        "content": phase_error("answer", phase),
                    })
                    continue
                
                # 获取当前题目的提示使用次数
                current_question = values.get("current_question", {})
                question_id = current_question.get("id", "")
                hint_count = 0
                if thread_id in _hints and question_id in _hints[thread_id]:
                    hint_count = _hints[thread_id][question_id]
                
                action = "end" if answer.lower() in {"quit", "exit", "q"} else "answer"
                await run_graph_stream(
                    ws,
                    graph,
                    Command(resume={"action": action, "content": answer, "hint_count": hint_count}),
                    thread_id,
                )

            elif msg_type == "end":
                if not thread_id:
                    await ws.send_json({"type": "error", "content": "面试尚未开始"})
                    continue
                graph = await get_graph()
                phase = (await get_graph_values(graph, thread_id)).get("phase", "")
                if not command_allowed("end", phase):
                    await ws.send_json({
                        "type": "error",
                        "content": phase_error("end", phase),
                    })
                    continue
                await run_graph_stream(
                    ws,
                    graph,
                    Command(resume={"action": "end", "content": ""}),
                    thread_id,
                )

            elif msg_type == "report":
                if not thread_id:
                    await ws.send_json({"type": "error", "content": "面试尚未开始"})
                    continue
                graph = await get_graph()
                values = await get_graph_values(graph, thread_id)
                phase = values.get("phase", "")
                if not command_allowed("report", phase):
                    await ws.send_json({
                        "type": "error",
                        "content": phase_error("report", phase),
                    })
                    continue
                await run_graph_stream(
                    ws,
                    graph,
                    Command(resume={"action": "report", "content": ""}),
                    thread_id,
                )
                final_values = await get_graph_values(graph, thread_id)
                if thread_id in _sessions and final_values.get("phase") == "completed":
                    _sessions[thread_id]["status"] = "ended"
                    _sessions[thread_id]["report_id"] = final_values.get("report_id", "")
                    # handoff 回流: 定向面试完成 → 写事件给统筹助手下一轮简报
                    if "handoff_focus" in _sessions[thread_id]:
                        from assistant import handoff as assistant_handoff
                        assistant_handoff.record_completion(
                            user["username"], final_values.get("report_id", ""),
                            _sessions[thread_id]["handoff_focus"])

            elif msg_type == "hint":
                if not thread_id:
                    await ws.send_json({"type": "error", "content": "面试尚未开始"})
                    continue
                graph = await get_graph()
                values = await get_graph_values(graph, thread_id)
                phase = values.get("phase", "")
                if not command_allowed("hint", phase):
                    await ws.send_json({
                        "type": "error",
                        "content": phase_error("hint", phase),
                    })
                    continue
                
                # 获取当前题目和候选人已回答内容
                current_question = values.get("current_question", {})
                question_id = current_question.get("id", "")
                question_text = current_question.get("question", "")
                candidate_answer = values.get("main_answer", "") or ""
                
                # 获取标准答案
                retriever = get_retriever()
                answer_data = retriever.get_answer(question_id)
                if not answer_data:
                    await ws.send_json({"type": "error", "content": "无法获取题目信息"})
                    continue
                standard_answer = answer_data.get("standard_answer", "")
                
                # 追踪提示使用次数
                if thread_id not in _hints:
                    _hints[thread_id] = {}
                if question_id not in _hints[thread_id]:
                    _hints[thread_id][question_id] = 0
                
                hint_count = _hints[thread_id][question_id]
                if hint_count >= 2:
                    await ws.send_json({"type": "error", "content": "每题最多使用 2 次提示"})
                    continue
                
                # 生成提示 (hint_level 从 1 开始)
                hint_level = hint_count + 1
                try:
                    hint_chain = build_hint_chain(get_fast_llm())
                    hint_text = hint_chain.invoke({
                        "question": question_text,
                        "standard_answer": standard_answer,
                        "hint_level": hint_level,
                        "candidate_answer": candidate_answer or "（尚未回答）",
                    })
                    _hints[thread_id][question_id] = hint_count + 1
                    
                    await ws.send_json({
                        "type": "hint",
                        "content": hint_text,
                        "hint_level": hint_level,
                        "question_id": question_id,
                    })
                except Exception as e:
                    logger.exception("生成提示失败: %s", e)
                    await ws.send_json({"type": "error", "content": "生成提示失败，请重试"})

            else:
                await ws.send_json({"type": "error", "content": f"未知消息类型: {msg_type}"})

    except WebSocketDisconnect:
        print("[WS] 客户端断开连接")
    except Exception as e:
        logger.exception("WebSocket 错误: %s", e)
        try:
            await ws.send_json({"type": "error", "content": "服务器内部错误"})
        except Exception:
            pass


# ============================================================
# v2.0 统筹智能体 (AGENT_PLAN.md)
#   独立 WS 通道 /ws/assistant: 与 /ws/chat 互不干扰, 面试进行中也能用。
#   会话/消息/设置/记忆走 REST; 对话流走 WS。
# ============================================================

_assistant_graph = None
_assistant_active_sessions = set()


def _assistant_waiting(snapshot) -> bool:
    return bool(snapshot.values.get("pending_action")
                and any(task.interrupts for task in snapshot.tasks))


def _assistant_decision(pending: dict, msg: dict) -> dict:
    from assistant.tools.actions import validate_proposal_edit
    action = msg.get("action")
    args = msg.get("args", {})
    if action not in ("approve", "edit", "reject") or not isinstance(args, dict):
        raise ValueError("确认动作或参数格式无效")
    if not isinstance(msg.get("reason", ""), str):
        raise ValueError("拒绝理由必须为文本")
    kind = pending.get("kind")
    if action == "edit" and kind == "tool_call_approval":
        raise ValueError("工具审批不支持修改参数")
    effective = dict(pending.get("args") or {})
    if action == "edit":
        allowed = {field["field"] for field in pending.get("editable_fields", [])}
        if set(args) - allowed:
            raise ValueError("包含不可编辑的字段")
        effective.update(args)
    if action in ("approve", "edit") and kind in ("interview", "kb_session"):
        error = validate_proposal_edit(kind, effective)
        if error:
            raise ValueError(error)
    return {"action": action, "args": args if action == "edit" else {},
            "reason": msg.get("reason", "")}


def _assistant_cancelled_calls(snapshot) -> list:
    """Complete interrupted tool batches before accepting a new human message."""
    from langchain_core.messages import AIMessage, ToolMessage
    messages = snapshot.values.get("messages") or []
    paired = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    return [ToolMessage(content='{"ok": false, "message": "操作已停止，未重放"}',
                        tool_call_id=c["id"], name=c["name"], status="error")
            for m in messages if isinstance(m, AIMessage)
            for c in m.tool_calls if c["id"] not in paired]


async def get_assistant_graph():
    """懒加载编译 assistant 图, 与面试图共用同一个 checkpointer 单例。"""
    global _assistant_graph
    if _assistant_graph is None:
        saver = await persistence.get_shared_saver()
        _assistant_graph = build_assistant_graph().compile(checkpointer=saver)
    return _assistant_graph


def _assistant_final_text(values: dict) -> str:
    """取本轮最后一条 AIMessage 的正文, 用于落 assistant_messages 表。"""
    from langchain_core.messages import AIMessage
    for msg in reversed(values.get("messages") or []):
        if isinstance(msg, AIMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


def _user_has_ongoing_interview(username: str) -> bool:
    return any(
        sess.get("username") == username and sess.get("status") == "ongoing"
        for sess in _sessions.values()
    )


async def _run_assistant_turn(ws, graph, payload, cfg, session_id, username):
    """跑一轮 assistant 图并转发 custom 事件; 结束后落消息表。
    作为独立 task 运行, 使 interrupt_turn 能在轮中取消它。"""
    final_values: dict = {}
    parts, trace = [], []
    persisted = False

    def persist_output():
        nonlocal persisted
        if persisted:
            return
        persisted = True
        # Store exactly this invocation's visible output, including intermediate
        # tool narration. A resume without new output must not copy old history.
        if parts or trace:
            assistant_db.append_message(session_id, "assistant", "".join(parts), trace)
        assistant_db.touch_session(session_id)

    try:
        await ws.send_json({"type": assistant_ev.TURN_START,
                            "session_id": session_id})
        async for mode, item in graph.astream(
            payload, cfg, stream_mode=["custom", "values"]
        ):
            if mode == "custom" and isinstance(item, dict):
                if item.get("type") == assistant_ev.ASSISTANT_DELTA:
                    parts.append(item.get("text", ""))
                elif item.get("type") == assistant_ev.TOOL_CALL:
                    trace.append({"name": item.get("name"),
                                  "callId": item.get("call_id"), "ok": None})
                elif item.get("type") == assistant_ev.TOOL_RESULT:
                    entry = next((t for t in trace if t["callId"] == item.get("call_id")), None)
                    if entry is None:
                        entry = {"name": item.get("name"), "callId": item.get("call_id")}
                        trace.append(entry)
                    entry.update(ok=item.get("ok"), ms=item.get("ms", 0))
                await ws.send_json(item)
            elif mode == "values" and isinstance(item, dict):
                final_values = item
        persist_output()
        snapshot = await graph.aget_state(cfg)
        if not _assistant_waiting(snapshot):
            try:
                from assistant.context_compression import maybe_compress_session
                await maybe_compress_session(
                    graph, cfg, username, session_id, snapshot=snapshot
                )
            except Exception as exc:
                # Compression is maintenance work; a summary outage must not turn
                # a successful user response into a failed assistant turn.
                logger.warning("assistant 上下文压缩失败 (session=%s): %s",
                               session_id, exc)
        reason = (assistant_ev.END_BUDGET
                  if final_values.get("budget_exceeded")
                  else assistant_ev.END_NORMAL)
        await ws.send_json({"type": assistant_ev.TURN_END, "reason": reason,
                            "session_id": session_id,
                            "awaiting_confirm": _assistant_waiting(snapshot)})
    except asyncio.CancelledError:
        persist_output()
        try:
            await ws.send_json({"type": assistant_ev.TURN_END,
                                "reason": assistant_ev.END_CANCELLED,
                                "session_id": session_id})
        except (WebSocketDisconnect, RuntimeError):
            pass
    except Exception as exc:
        persist_output()
        logger.exception("assistant 轮次失败 (session=%s): %s", session_id, exc)
        try:
            await ws.send_json({"type": assistant_ev.ERROR, "code": "turn_error",
                                "message": "助手处理失败, 请重试",
                                "retryable": True})
            await ws.send_json({"type": assistant_ev.TURN_END,
                                "reason": assistant_ev.END_NORMAL,
                                "session_id": session_id})
        except (WebSocketDisconnect, RuntimeError):
            pass
    finally:
        _assistant_active_sessions.discard((username, session_id))


@app.websocket("/ws/assistant")
async def ws_assistant(ws: WebSocket):
    user = ws_authenticate(ws)
    if user is None:
        await ws.close(code=4401)
        return
    await ws.accept()
    username = user["username"]
    session_id: Optional[int] = None
    turn_task: Optional[asyncio.Task] = None

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": assistant_ev.ERROR,
                                    "code": "bad_json",
                                    "message": "无效的 JSON 格式"})
                continue
            if not isinstance(msg, dict):
                await ws.send_json({"type": assistant_ev.ERROR,
                                    "code": "bad_shape",
                                    "message": "消息必须是 JSON 对象"})
                continue
            mtype = msg.get("type", "")

            if mtype == assistant_ev.INTERRUPT_TURN:
                if turn_task is not None and not turn_task.done():
                    turn_task.cancel()
                    await turn_task
                else:
                    await ws.send_json({"type": assistant_ev.TURN_END,
                                        "reason": assistant_ev.END_CANCELLED,
                                        "session_id": session_id})
                continue

            if turn_task is not None and not turn_task.done():
                await ws.send_json({"type": assistant_ev.ERROR,
                                    "code": "busy",
                                    "message": "上一轮还在进行, 请先等待或发送 interrupt_turn"})
                continue

            if mtype == assistant_ev.USER_MESSAGE:
                text = msg.get("text", "")
                if not isinstance(text, str):
                    await ws.send_json({"type": assistant_ev.ERROR, "code": "bad_shape",
                                        "message": "消息正文必须为文本"})
                    continue
                text = text.strip()
                if not text:
                    await ws.send_json({"type": assistant_ev.ERROR,
                                        "code": "empty_text",
                                        "message": "消息不能为空"})
                    continue
                if len(text) > 5000:
                    await ws.send_json({"type": assistant_ev.ERROR,
                                        "code": "too_long",
                                        "message": "单条消息不能超过 5000 字"})
                    continue
                requested = msg.get("session_id")
                if requested is not None and (type(requested) is not int or requested < 1):
                    await ws.send_json({"type": assistant_ev.ERROR, "code": "no_session",
                                        "message": "会话编号无效"})
                    continue
                session = (assistant_db.get_session(username, requested)
                           if requested else None)
                if requested and session is None:
                    await ws.send_json({"type": assistant_ev.ERROR,
                                        "code": "no_session",
                                        "message": "会话不存在或无权访问"})
                    continue
                if session is None:
                    session = assistant_db.create_session(username, text[:20])
                session_id = session["id"]
                key = (username, session_id)
                if key in _assistant_active_sessions:
                    await ws.send_json({"type": assistant_ev.ERROR, "code": "busy",
                                        "message": "该会话正在另一连接中执行"})
                    continue
                _assistant_active_sessions.add(key)
                thread_id = persistence.assistant_thread_id(username, session_id)
                try:
                    graph = await get_assistant_graph()
                    cfg = {"configurable": {"thread_id": thread_id}}
                    snapshot = await graph.aget_state(cfg)
                    if _assistant_waiting(snapshot):
                        _assistant_active_sessions.discard(key)
                        await ws.send_json({"type": assistant_ev.ERROR, "code": "awaiting_confirm",
                                            "message": "请先处理当前待确认操作"})
                        continue
                    assistant_db.append_message(session_id, "user", text)
                except Exception:
                    _assistant_active_sessions.discard(key)
                    raise
                payload = {
                    "messages": _assistant_cancelled_calls(snapshot) + [_AssistantHumanMessage(content=text)],
                    "username": username,
                    "session_id": session_id,
                    "thread_id": thread_id,
                    "env_ongoing_interview": _user_has_ongoing_interview(username),
                }
                turn_task = asyncio.create_task(_run_assistant_turn(
                    ws, graph, payload, cfg, session_id, username))

            elif mtype == assistant_ev.PROPOSAL_DECISION:
                requested = msg.get("session_id")
                if type(requested) is not int or not assistant_db.get_session(username, requested):
                    await ws.send_json({"type": assistant_ev.ERROR,
                                        "code": "no_session",
                                        "message": "会话不存在或无权访问"})
                    continue
                session_id = requested
                key = (username, session_id)
                if key in _assistant_active_sessions:
                    await ws.send_json({"type": assistant_ev.ERROR, "code": "busy",
                                        "message": "该会话正在执行"})
                    continue
                _assistant_active_sessions.add(key)
                thread_id = persistence.assistant_thread_id(username, session_id)
                try:
                    graph = await get_assistant_graph()
                    cfg = {"configurable": {"thread_id": thread_id}}
                    snapshot = await graph.aget_state(cfg)
                    pending = snapshot.values.get("pending_action") or {}
                    if (not _assistant_waiting(snapshot) or not msg.get("operation_id")
                            or msg.get("operation_id") != pending.get("operation_id")):
                        raise ValueError("操作已失效或与当前待确认操作不匹配")
                    decision = _assistant_decision(pending, msg)
                    # handoff 出站: 用户批准面试提案 → 登记意图, 等面试引擎消费
                    if (decision["action"] in ("approve", "edit")
                            and pending.get("kind") == "interview"):
                        from assistant import handoff as assistant_handoff
                        assistant_handoff.record_intent(
                            username,
                            {**(pending.get("args") or {}),
                             **(decision.get("args") or {})},
                            pending.get("operation_id", ""))
                except ValueError as exc:
                    _assistant_active_sessions.discard(key)
                    await ws.send_json({"type": assistant_ev.ERROR, "code": "invalid_decision",
                                        "message": str(exc), "retryable": True})
                    continue
                except Exception:
                    _assistant_active_sessions.discard(key)
                    raise
                turn_task = asyncio.create_task(_run_assistant_turn(
                    ws, graph, Command(resume=decision), cfg,
                    session_id, username))

            else:
                await ws.send_json({"type": assistant_ev.ERROR,
                                    "code": "unknown_type",
                                    "message": f"未知消息类型: {mtype}"})

    except WebSocketDisconnect:
        logger.info("[WS/assistant] 客户端断开 (user=%s)", username)
    except Exception as exc:
        logger.exception("[WS/assistant] 错误: %s", exc)
        try:
            await ws.send_json({"type": assistant_ev.ERROR, "code": "internal",
                                "message": "服务器内部错误"})
        except Exception:
            pass
    finally:
        if turn_task is not None and not turn_task.done():
            turn_task.cancel()
            await turn_task


# ---------- assistant REST: 会话 / 设置 / 记忆 / 健康 ----------

class AssistantSessionRename(BaseModel):
    title: str


class AssistantSettingsBody(BaseModel):
    auto_accept_level: Optional[str] = None
    memory_enabled: Optional[bool] = None


@app.get("/api/assistant/sessions")
def api_assistant_sessions(user: dict = Depends(get_current_user)):
    return {"success": True,
            "sessions": assistant_db.list_sessions(user["username"])}


@app.post("/api/assistant/sessions")
def api_assistant_create_session(user: dict = Depends(get_current_user)):
    return {"success": True,
            "session": assistant_db.create_session(user["username"])}


@app.get("/api/assistant/sessions/{session_id}")
async def api_assistant_session_detail(session_id: int,
                                      user: dict = Depends(get_current_user)):
    session = assistant_db.get_session(user["username"], session_id)
    if not session:
        return JSONResponse(status_code=404,
                            content={"success": False, "message": "会话不存在"})
    graph = await get_assistant_graph()
    snapshot = await graph.aget_state({"configurable": {
        "thread_id": persistence.assistant_thread_id(user["username"], session_id)}})
    waiting = _assistant_waiting(snapshot)
    active = (user["username"], session_id) in _assistant_active_sessions
    return {"success": True, "session": session,
            "messages": assistant_db.list_messages(user["username"], session_id),
            "phase": "thinking" if active else "awaiting_confirm" if waiting else "idle",
            "awaiting_confirm": waiting,
            "pending_action": snapshot.values.get("pending_action") if waiting else None}


@app.patch("/api/assistant/sessions/{session_id}")
def api_assistant_rename_session(session_id: int, body: AssistantSessionRename,
                                 user: dict = Depends(get_current_user)):
    ok = assistant_db.rename_session(user["username"], session_id, body.title)
    return {"success": ok}


@app.delete("/api/assistant/sessions/{session_id}")
async def api_assistant_delete_session(session_id: int,
                                       user: dict = Depends(get_current_user)):
    """删除级联三步: 消息表 + 会话表 + checkpointer thread (§5.12)。
    删不干净比没有记忆更糟, 所以第三级失败也要报出来。"""
    username = user["username"]
    if not assistant_db.get_session(username, session_id):
        return JSONResponse(status_code=404,
                            content={"success": False, "message": "会话不存在"})
    key = (username, session_id)
    if key in _assistant_active_sessions:
        return JSONResponse(status_code=409,
                            content={"success": False, "message": "会话正在执行，请先停止"})
    _assistant_active_sessions.add(key)
    try:
        saver = await persistence.get_shared_saver()
        thread_id = persistence.assistant_thread_id(username, session_id)
        await saver.adelete_thread(thread_id)
        assistant_db.delete_session(username, session_id)
    except Exception as exc:
        logger.warning("删除 checkpointer thread 失败: %s", exc)
        return JSONResponse(status_code=500,
                            content={"success": False, "message": "删除断点失败，请重试"})
    finally:
        _assistant_active_sessions.discard(key)
    return {"success": True, "checkpoint_thread_deleted": True}


@app.get("/api/assistant/settings")
def api_assistant_get_settings(user: dict = Depends(get_current_user)):
    return {"success": True, "settings": assistant_db.get_settings(user["username"])}


@app.put("/api/assistant/settings")
def api_assistant_put_settings(body: AssistantSettingsBody,
                               user: dict = Depends(get_current_user)):
    try:
        settings = assistant_db.put_settings(
            user["username"], body.auto_accept_level, body.memory_enabled)
    except ValueError as exc:
        return JSONResponse(status_code=400,
                            content={"success": False, "message": str(exc)})
    return {"success": True, "settings": settings}


@app.get("/api/assistant/memories")
def api_assistant_memories(kind: str = "", user: dict = Depends(get_current_user)):
    return {"success": True,
            "memories": assistant_db.list_memories(user["username"], kind=kind)}


@app.delete("/api/assistant/memories/{memory_id}")
def api_assistant_delete_memory(memory_id: int,
                                user: dict = Depends(get_current_user)):
    from assistant import vector_index
    ok = assistant_db.delete_memory(user["username"], memory_id)
    if not ok:
        return JSONResponse(status_code=404,
                            content={"success": False, "message": "记忆不存在"})
    vector_index.delete(memory_id, user["username"])
    return {"success": True}


@app.delete("/api/assistant/memories")
def api_assistant_clear_memories(user: dict = Depends(get_current_user)):
    from assistant import vector_index
    removed = assistant_db.clear_memories(user["username"])
    vector_index.clear(user["username"])
    return {"success": True, "removed": removed}


@app.get("/healthz")
def healthz():
    """存活探针: 进程在即 200, 不碰任何外部依赖。"""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """就绪探针: 缺 LLM key / 库不可写时 503 并给修复指引
    (interview-prep-app app.py:107-132 的做法)。"""
    problems = []
    if not config.LLM_API_KEY:
        problems.append("未配置 LLM_API_KEY: 请在 backend/.env 写入")
    for path in (config.ASSISTANT_DB_PATH, config.KB_DB_PATH):
        directory = os.path.dirname(os.path.abspath(path))
        if not os.access(directory, os.W_OK):
            problems.append(f"目录不可写: {directory}")
    if problems:
        return JSONResponse(status_code=503,
                            content={"status": "not_ready", "problems": problems})
    return {"status": "ready"}


@app.on_event("shutdown")
async def _close_shared_checkpointer():
    """不关 aiosqlite 连接会让 graph hang (checkpoint/sqlite/aio.py:53-61)。"""
    await persistence.close_shared_saver()


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
