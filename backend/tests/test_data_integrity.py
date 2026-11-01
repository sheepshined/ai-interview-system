"""题库数据完整性测试 — 防止标准答案损坏(为空/句首缺失/异常短)或 id 重复。

背景: 2026-08-11 发现 py_015 的 A 字段以全角逗号开头(句首缺失), 该内容会原样写入
ChromaDB 并流入评分/报告, 因此加此回归测试, 复用 kb_builder 的解析逻辑。
"""
import os
import re

import config
from retrieval.kb_builder import parse_questions_from_file


# 句首缺失的特征: 答案以全角标点(或冒号)开头
LEADING_PUNCTUATION = re.compile(r"^[\s]*[，。、；：！？]")

# 正常答案最短也有 ~100 字, 40 字以下视为异常偏短(防止"只剩半句"的数据损坏)
MIN_ANSWER_LENGTH = 40


def _load_all_questions():
    questions = []
    for filename in sorted(os.listdir(config.DATA_DIR)):
        if not filename.endswith(".md"):
            continue
        questions.extend(
            parse_questions_from_file(os.path.join(config.DATA_DIR, filename))
        )
    return questions


def test_every_role_bank_has_questions():
    """config.ROLES 里的每个岗位都应有对应的题库文件且至少 1 题。"""
    for role_key, role_info in config.ROLES.items():
        path = os.path.join(config.DATA_DIR, role_info["file"])
        assert os.path.isfile(path), f"缺少题库文件: {role_info['file']}"
        questions = parse_questions_from_file(path)
        assert len(questions) >= 1, f"{role_key} 题库为空"


def test_all_questions_have_non_empty_q_and_a():
    """Q 与 A 字段必须存在且非空。"""
    for q in _load_all_questions():
        assert q["question"] and q["question"].strip(), f"{q['id']} 题目文本为空"
        assert q["answer"] and q["answer"].strip(), f"{q['id']} 标准答案为空"


def test_answer_does_not_start_with_punctuation():
    """标准答案不能以全角标点开头(句首缺失的损坏特征, 如 py_015 历史问题)。"""
    for q in _load_all_questions():
        assert not LEADING_PUNCTUATION.match(q["answer"]), (
            f"{q['id']} 标准答案疑似句首缺失: {q['answer'][:40]!r}"
        )


def test_answer_is_not_suspiciously_short():
    """标准答案长度不应异常偏短。"""
    for q in _load_all_questions():
        assert len(q["answer"]) >= MIN_ANSWER_LENGTH, (
            f"{q['id']} 标准答案过短({len(q['answer'])}字): {q['answer'][:40]!r}"
        )


def test_question_ids_are_unique():
    """所有题目 id 必须唯一。"""
    ids = [q["id"] for q in _load_all_questions()]
    assert len(ids) == len(set(ids)), f"存在重复题目 id: {[i for i in ids if ids.count(i) > 1]}"


def test_scenario_questions_have_scenario_and_followups():
    """场景题(type=scenario)必须提供场景描述和至少 2 条预设追问方向。"""
    scenario_questions = [q for q in _load_all_questions() if q.get("type") == "scenario"]
    for q in scenario_questions:
        assert q.get("scenario", "").strip(), f"{q['id']} 场景题缺少 SCENARIO 字段"
        assert len(q.get("followup_directions", [])) >= 2, (
            f"{q['id']} 场景题应提供至少 2 条预设追问方向(FOLLOWUP)"
        )


def test_scenario_questions_have_adequate_scoring_points():
    """场景题评分要点应至少 3 条, 覆盖多个合理方案维度。"""
    scenario_questions = [q for q in _load_all_questions() if q.get("type") == "scenario"]
    for q in scenario_questions:
        assert len(q.get("scoring_points", [])) >= 3, (
            f"{q['id']} 场景题评分要点应至少 3 条"
        )
