"""reports.py — 面试报告只读工具 (复用 reports/ 目录既有产物, 不新建数据)。

雷达 JSON 的字段清单见 agent/graph.py:1272-1321。所有工具按
runtime.state["username"] 过滤, 读不到他人报告。
"""
import asyncio
import json
import os
import re
from typing import Optional

from pydantic import BaseModel, Field

import config
from assistant import budget
from assistant.tools.base import assistant_tool
from langchain.tools import ToolRuntime

_REPORT_ID_RE = re.compile(r"^interview_report_[0-9]{8}_[0-9]{6}_[0-9a-zA-Z_-]+_[a-z0-9_]+$")


class ListReportsArgs(BaseModel):
    limit: int = Field(default=10, ge=1, le=50, description="返回条数上限")


class ReportIdArgs(BaseModel):
    report_id: str = Field(description="来自 list_reports 的报告 id")


def _radar_path(report_id: str) -> Optional[str]:
    if not _REPORT_ID_RE.match(report_id or ""):
        return None
    path = os.path.join(config.REPORTS_DIR, f"{report_id}.json")
    return path if os.path.isfile(path) else None


def _load_radar(report_id: str) -> Optional[dict]:
    path = _radar_path(report_id)
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _list_sync(limit: int, username: str) -> list:
    out = []
    try:
        names = sorted(os.listdir(config.REPORTS_DIR), reverse=True)
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        data = _load_radar(name[:-5])
        if not data or data.get("username") not in (username, ""):
            continue
        if username and data.get("username") != username:
            continue
        out.append({
            "report_id": data.get("report_id", name[:-5]),
            "role_title": data.get("role_title", ""),
            "avg_score": data.get("avg_score", 0),
            "total_questions": data.get("total_questions", 0),
            "timestamp": data.get("timestamp", ""),
            "ai_summary_mode": data.get("ai_summary_mode", ""),
        })
        if len(out) >= limit:
            break
    return out


@assistant_tool(
    name="list_reports",
    description=(
        "列出当前用户最近的面试报告 (含 report_id/岗位/平均分/时间)。"
        "任何基于报告的分析都从这里拿 report_id。"
        "不要用 read_interview_record 找分数——记录文件没有汇总分。"
        "没有报告时返回 reports=[] 且 found=false, 不是错误。"
    ),
    args_schema=ListReportsArgs,
)
async def list_reports(limit: int = 10, runtime: ToolRuntime = None) -> dict:
    username = runtime.state["username"]
    reports = await asyncio.to_thread(_list_sync, limit, username)
    return {"ok": True, "found": bool(reports), "reports": reports}


@assistant_tool(
    name="read_report_radar",
    description=(
        "读取一份报告的雷达数据: 四维均分、分类均分、逐题分、强弱项、"
        "难度变化、学习建议。用于任何基于分数的分析。"
        "不要用 read_report_md 找分数——markdown 是给报告页看的, 结构松散。"
        "report_id 来自 list_reports。不存在时 found=false。"
    ),
    args_schema=ReportIdArgs,
)
async def read_report_radar(report_id: str, runtime: ToolRuntime = None) -> dict:
    data = await asyncio.to_thread(_load_radar, report_id)
    if not data:
        return {"ok": True, "found": False,
                "message": f"报告 {report_id} 不存在或不可读"}
    if data.get("username") not in ("", runtime.state["username"]):
        return {"ok": True, "found": False, "message": "无权读取该报告"}
    data = dict(data)
    data["questions"] = (data.get("questions") or [])[:30]
    return {"ok": True, "found": True, "radar": data}


@assistant_tool(
    name="read_report_md",
    description=(
        "读取报告的 markdown 全文 (含 AI 综合评价段落)。"
        "只在用户明确要『评价原文/报告全文』时用; 要分数用 read_report_radar。"
        "过长会截断并提示。report_id 来自 list_reports。"
    ),
    args_schema=ReportIdArgs,
)
async def read_report_md(report_id: str, runtime: ToolRuntime = None) -> dict:
    path = _radar_path(report_id)
    if not path:
        return {"ok": True, "found": False, "message": "报告不存在"}
    md_path = path[:-5] + ".md"
    if not os.path.isfile(md_path):
        return {"ok": True, "found": False, "message": "报告 markdown 不存在"}

    def _read():
        with open(md_path, encoding="utf-8") as fh:
            return fh.read()

    text = await asyncio.to_thread(_read)
    shown, truncated = budget.truncate_output(text)
    return {"ok": True, "found": True, "content": shown, "truncated": truncated}


class TrendArgs(BaseModel):
    limit: int = Field(default=5, ge=1, le=20, description="纳入统计的最近报告份数")


def _weakness_trend_sync(limit: int, username: str) -> dict:
    """跨报告弱项聚合 (确定性统计, 不走 LLM)。

    输入: 最近 limit 份当前用户报告 (按文件名倒序 = 时间倒序)。
    输出:
      reports: 按时间正序的逐份概览 (供看整体走势)
      categories: 按分类聚合 count/avg/low_count/最近得分/delta, 按均分升序
        (最弱的排最前), delta = 最近得分 - 历史均分 (负 = 仍在走弱)
    """
    metas = _list_sync(limit, username)
    radars = []
    for meta in metas:
        data = _load_radar(meta["report_id"])
        if data:
            radars.append(data)
    radars.sort(key=lambda d: str(d.get("timestamp", "")))

    reports = [
        {"report_id": d.get("report_id", ""), "timestamp": d.get("timestamp", ""),
         "role_title": d.get("role_title", ""), "avg_score": d.get("avg_score", 0)}
        for d in radars
    ]

    cat_stats: dict = {}
    for d in radars:
        ts = str(d.get("timestamp", ""))
        for q in (d.get("questions") or []):
            score = q.get("score")
            if score is None:
                continue
            cat = q.get("category", "") or "未分类"
            st = cat_stats.setdefault(cat, {
                "category": cat, "count": 0, "total": 0.0, "low_count": 0,
                "recent_score": None, "recent_ts": "", "low_questions": [],
            })
            st["count"] += 1
            st["total"] += score
            if score < 5:
                st["low_count"] += 1
                if len(st["low_questions"]) < 3:
                    st["low_questions"].append(str(q.get("question", ""))[:40])
            if ts >= st["recent_ts"]:
                st["recent_ts"] = ts
                st["recent_score"] = score

    categories = []
    for st in cat_stats.values():
        avg = round(st["total"] / st["count"], 1)
        delta = (round(st["recent_score"] - avg, 1)
                 if st["recent_score"] is not None else 0.0)
        categories.append({
            "category": st["category"], "count": st["count"],
            "avg_score": avg, "low_count": st["low_count"],
            "recent_score": st["recent_score"], "delta": delta,
            "low_questions": st["low_questions"],
        })
    # 最弱优先: 均分升序, 同分低分次数多者优先
    categories.sort(key=lambda c: (c["avg_score"], -c["low_count"]))
    return {"reports": reports, "categories": categories}


@assistant_tool(
    name="get_weakness_trend",
    description=(
        "跨最近多场面试聚合弱项趋势 (确定性统计, 不走模型): "
        "逐份报告均分走势 + 按知识分类的出现次数/均分/低分次数/最近得分变化。"
        "用户问『我最近哪类题一直在弱/有没有进步』时用它, "
        "不要逐份 read_report_radar 再自己归纳。categories 已按最弱排最前。"
        "没有报告时 found=false。"
    ),
    args_schema=TrendArgs,
)
async def get_weakness_trend(limit: int = 5, runtime: ToolRuntime = None) -> dict:
    username = runtime.state["username"]
    data = await asyncio.to_thread(_weakness_trend_sync, limit, username)
    found = bool(data["reports"])
    return {"ok": True, "found": found,
            "reports_used": len(data["reports"]), **data}


@assistant_tool(
    name="read_report_weak_points",
    description=(
        "读取一份报告的薄弱点: 得分<5 的题、weaknesses、learning_suggestions。"
        "用户问『我哪里弱/该补什么』时优先用它, 比整份 radar 省 token。"
        "report_id 来自 list_reports。不存在时 found=false。"
    ),
    args_schema=ReportIdArgs,
)
async def read_report_weak_points(report_id: str, runtime: ToolRuntime = None) -> dict:
    data = await asyncio.to_thread(_load_radar, report_id)
    if not data:
        return {"ok": True, "found": False, "message": "报告不存在"}
    if data.get("username") not in ("", runtime.state["username"]):
        return {"ok": True, "found": False, "message": "无权读取该报告"}
    weak_questions = [
        {"round": q.get("round"), "question": q.get("question", ""),
         "score": q.get("score", 0), "category": q.get("category", "")}
        for q in (data.get("questions") or []) if (q.get("score") or 0) < 5
    ]
    return {
        "ok": True, "found": True,
        "weak_questions": weak_questions,
        "weaknesses": data.get("weaknesses", []),
        "learning_suggestions": data.get("learning_suggestions", []),
        "difficulty_changes": data.get("difficulty_changes", []),
    }
