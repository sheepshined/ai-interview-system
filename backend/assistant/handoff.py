"""handoff.py — 统筹助手与面试引擎之间的交接编排。

方向:
  出站 (assistant -> interview): 用户批准面试提案后, server 调
    record_intent 登记; 面试引擎下一次收到 config 时 consume_intent
    单次消费, 把 focus 注入 first_topic_hint 实现定向开考。
  回流 (interview -> assistant): 面试报告生成后 server 调
    record_completion 写事件; 助手下一轮 load_context 用
    drain_events_for_prompt 注入 system prompt 并自动 ack。

两张表都在 assistant/db.py, 这里只做业务编排, 保持 server 钩子极薄。
"""
import json
import logging
import os
from typing import Optional

import config
from assistant import db

logger = logging.getLogger(__name__)

_INTENT_TTL_SECONDS = 1800  # 批准后 30 分钟内开考有效


def record_intent(username: str, args: dict, operation_id: str) -> None:
    """面试提案被批准时登记 handoff 意图 (server 钩子)。"""
    focus = str((args or {}).get("focus", "")).strip()
    role = str((args or {}).get("role", "llm_app")).strip() or "llm_app"
    try:
        db.create_handoff_intent(username, focus, role, operation_id)
    except Exception:
        logger.warning("handoff intent 登记失败 (user=%s)", username, exc_info=True)


def consume_intent(username: str) -> Optional[dict]:
    """面试引擎 config 时消费最新有效意图; 无则 None。"""
    try:
        return db.consume_handoff_intent(username, _INTENT_TTL_SECONDS)
    except Exception:
        logger.warning("handoff intent 消费失败 (user=%s)", username, exc_info=True)
        return None


def record_completion(username: str, report_id: str, focus: str) -> None:
    """面试报告生成后回流事件 (server 钩子)。平均分从报告 JSON 读。"""
    avg_score, role_title = 0.0, ""
    try:
        path = os.path.join(config.REPORTS_DIR, f"{report_id}.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        avg_score = float(data.get("avg_score", 0))
        role_title = str(data.get("role_title", ""))
    except Exception:
        logger.warning("handoff 报告读取失败 (%s)", report_id, exc_info=True)
    try:
        db.create_handoff_event(username, report_id, focus, avg_score, role_title)
    except Exception:
        logger.warning("handoff event 写入失败 (user=%s)", username, exc_info=True)


def drain_events_for_prompt(username: str) -> str:
    """取出未读回流事件, ack 并格式化成 prompt 文本; 无事件返回空串。"""
    try:
        events = db.drain_handoff_events(username)
    except Exception:
        logger.warning("handoff events 读取失败 (user=%s)", username, exc_info=True)
        return ""
    lines = []
    for ev in events:
        focus_part = f", 定向主题「{ev['focus']}」" if ev.get("focus") else ""
        lines.append(
            f"- 报告 {ev['report_id']} ({ev.get('role_title') or '面试'}): "
            f"平均分 {ev.get('avg_score', 0)}{focus_part}"
        )
    return "\n".join(lines)
