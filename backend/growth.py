"""能力成长档案: 跨面试报告的确定性聚合。

只读 reports/*.json, 按用户隔离; 不调用 LLM, 输出全部可由报告原文复核。
聚合口径:
- timeline: 每场报告一行 (时间正序), 含四维分, 供前端画走势与雷达叠加;
- categories: 跨场聚合到题目粒度 (score 直接取自 questions[].score),
  弱项按均分升序排列, delta = 最近一次得分 - 第一次得分;
- summary: 总览指标与近期趋势 (最近 3 场均分 - 之前 3 场均分, 少于 6 场为 null,
  保证"之前 3 场"确实存在; 口径统一为已评分题)。
"""

import json
import os
from typing import List, Optional

LOW_SCORE_THRESHOLD = 6
DIMENSION_KEYS = ("accuracy", "completeness", "depth", "clarity")


def _parse_date(timestamp: str) -> str:
    ts = str(timestamp or "")
    if len(ts) >= 8 and ts[:8].isdigit():
        return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
    return ""


def _question_score(q: dict) -> Optional[float]:
    try:
        return float(q.get("score"))
    except (TypeError, ValueError):
        return None


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_or_zero(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def load_user_reports(reports_dir: str, username: str) -> List[dict]:
    """读取某用户的全部报告 JSON, 按时间正序; 无效文件跳过。"""
    reports: List[dict] = []
    if not os.path.isdir(reports_dir):
        return reports
    for fn in os.listdir(reports_dir):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(reports_dir, fn), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if (data.get("username") or "admin") != username:
            continue
        data.setdefault("report_id", fn[:-5])
        reports.append(data)
    reports.sort(key=lambda d: (str(d.get("timestamp") or d.get("report_id") or "")))
    return reports


def _timeline(reports: List[dict]) -> List[dict]:
    items = []
    for d in reports:
        dims = d.get("dimensions") or {}
        items.append({
            "report_id": d.get("report_id", ""),
            "date": _parse_date(d.get("timestamp", "")),
            "role_title": d.get("role_title", ""),
            "difficulty_label": d.get("difficulty_label", ""),
            "avg_score": _num(d.get("avg_score")),
            "total_questions": _int_or_zero(d.get("total_questions")),
            "dimensions": {k: round(_num(dims.get(k)), 1) for k in DIMENSION_KEYS},
        })
    return items


def _categories(reports: List[dict]) -> List[dict]:
    stats: dict = {}
    for d in reports:
        date = _parse_date(d.get("timestamp", ""))
        for q in d.get("questions", []) or []:
            cat = str(q.get("category") or "").strip()
            if not cat:
                continue
            score = _question_score(q)
            if score is None:
                continue
            s = stats.setdefault(cat, {
                "name": cat, "count": 0, "score_sum": 0.0, "low_count": 0,
                "first_score": None, "first_date": "", "last_score": None,
                "last_date": "",
            })
            s["count"] += 1
            s["score_sum"] += score
            if score < LOW_SCORE_THRESHOLD:
                s["low_count"] += 1
            if s["first_score"] is None:
                s["first_score"] = score
                s["first_date"] = date
            s["last_score"] = score
            s["last_date"] = date
    out = []
    for s in stats.values():
        count = s["count"]
        avg = round(s["score_sum"] / count, 1) if count else 0.0
        first = s["first_score"] if s["first_score"] is not None else 0.0
        last = s["last_score"] if s["last_score"] is not None else 0.0
        out.append({
            "name": s["name"],
            "count": count,
            "avg_score": avg,
            "low_count": s["low_count"],
            "low_rate": round(s["low_count"] / count, 2) if count else 0.0,
            "first_score": first,
            "last_score": last,
            "delta": round(last - first, 1),
            "last_date": s["last_date"],
        })
    # 弱项置顶: 均分升序, 同分按题量多者优先
    out.sort(key=lambda c: (c["avg_score"], -c["count"]))
    return out


def _difficulty_distribution(reports: List[dict]) -> dict:
    dist = {"1": 0, "2": 0, "3": 0}
    for d in reports:
        for q in d.get("questions", []) or []:
            try:
                lvl = int(q.get("difficulty_at_time"))
            except (TypeError, ValueError):
                continue
            if str(lvl) in dist:
                dist[str(lvl)] += 1
    return dist


def _recent_delta(scores: List[float]) -> Optional[float]:
    """最近 3 场均分 - 之前 3 场均分; 少于 6 场时"之前 3 场"不成立, 返回 None。"""
    if len(scores) < 6:
        return None
    recent = scores[-3:]
    prev = scores[-6:-3]
    return round(sum(recent) / len(recent) - sum(prev) / len(prev), 1)


def build_growth(reports_dir: str, username: str) -> dict:
    reports = load_user_reports(reports_dir, username)
    timeline = _timeline(reports)
    categories = _categories(reports)

    all_scores: List[float] = []
    followups = 0
    hints = 0
    for d in reports:
        for q in d.get("questions", []) or []:
            score = _question_score(q)
            if score is None:
                continue  # 未评分题不进任何口径, 保证分子分母同源
            all_scores.append(score)
            if q.get("had_followup"):
                followups += 1
            hints += _int_or_zero(q.get("hints_used"))

    dates = [t["date"] for t in timeline if t["date"]]
    overall_avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0.0
    weakest = categories[0] if categories else None
    best = categories[-1] if categories else None
    summary = {
        "total_reports": len(reports),
        "total_questions": len(all_scores),
        "overall_avg": overall_avg,
        "followup_rate": round(followups / len(all_scores), 2) if all_scores else 0.0,
        "hints_used_total": hints,
        "first_date": dates[0] if dates else "",
        "last_date": dates[-1] if dates else "",
        "recent_delta": _recent_delta([t["avg_score"] for t in timeline]),
        "weakest_category": weakest,
        "best_category": best,
    }
    return {
        "summary": summary,
        "timeline": timeline,
        "categories": categories,
        "difficulty_distribution": _difficulty_distribution(reports),
    }
