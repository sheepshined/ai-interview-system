"""
agent/chains.py — LangChain LCEL Chain 定义

使用 LangChain Expression Language (LCEL) 构建 Chain:
  1. question_chain  — 出题 Chain
  2. scoring_chain   — 评分 Chain (PydanticOutputParser 结构化输出)
  3. followup_chain  — 追问 Chain
  4. summary_chain   — 总结报告 Chain (独立上下文)
  5. compress_chain  — 对话压缩 Chain

LCEL 优势:
  - 声明式组合 (prompt | llm | parser)
  - 原生支持流式输出、异步、重试
  - 可观测性 (LangSmith 追踪)
"""
import re

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser

from common import extract_json_object
from agent.prompts import (
    question_prompt,
    scorer_prompt,
    followup_prompt,
    summary_prompt,
    opening_prompt,
    closing_prompt,
    hint_prompt,
    project_question_prompt,
)
from agent.models import ScoreResult, ProjectQuestion


# ============================================================
# 自定义评分输出解析器 (带容错)
# ============================================================

class RobustScoreParser:
    """健壮的评分输出解析器

    策略:
      1. 尝试从 LLM 输出中提取 JSON 并解析为 ScoreResult
      2. 如果失败, 尝试从文本中提取分数
      3. 如果全部失败, 返回默认评分
    """

    def __init__(self):
        self._pydantic_parser_failed = False

    def parse(self, text: str) -> ScoreResult:
        """解析 LLM 输出为 ScoreResult"""
        if not text:
            return self._default_result("LLM 返回空内容")

        # Step 1-4: 公共 JSON 容错提取 (剥离代码块 → 直接解析 → 正则 → 平衡花括号)
        data = extract_json_object(text)
        if data is not None:
            return self._dict_to_result(data)

        # Step 5: 从文本中提取分数 (兜底)
        fallback_score = self._extract_score_from_text(text)
        if fallback_score > 0:
            return ScoreResult(
                score=fallback_score,
                max_score=10,
                score_breakdown={
                    "accuracy": fallback_score,
                    "completeness": fallback_score,
                    "depth": max(fallback_score - 1, 1),
                    "clarity": fallback_score,
                },
                hit_points=[],
                missed_points=["评分解析异常, 无法提取详细得分点"],
                feedback=f"评分解析异常, 已尝试提取分数({fallback_score})。LLM原始输出: {text[:200]}",
                is_correct=fallback_score >= 5,
            )

        return self._default_result(f"无法解析 LLM 输出: {text[:200]}")

    @staticmethod
    def _dict_to_result(data: dict) -> ScoreResult:
        """将字典转换为 ScoreResult, 处理字段缺失

        总分校准: 评分标准明确定义"总分为四维度平均", 但 LLM 有时会
        给出顶层 score 与 score_breakdown 自相矛盾的输出(如 score=0 却
        四维全 1)。这里以四维均值为准兜底——当顶层 score 与四维均值
        偏差超过 2 分时, 采用四维均值(四舍五入)。追问分档阈值(3-7)依赖
        这个 score, 校准后分档更可靠。
        """
        def bounded_int(value, default=0):
            try:
                return max(0, min(int(float(value)), 10))
            except (TypeError, ValueError):
                return default

        breakdown_data = data.get("score_breakdown", {})
        if not isinstance(breakdown_data, dict):
            breakdown_data = {}

        raw_score = bounded_int(data.get("score", 0))
        breakdown = {
            "accuracy": bounded_int(breakdown_data.get("accuracy", raw_score), raw_score),
            "completeness": bounded_int(breakdown_data.get("completeness", raw_score), raw_score),
            "depth": bounded_int(breakdown_data.get("depth", raw_score), raw_score),
            "clarity": bounded_int(breakdown_data.get("clarity", raw_score), raw_score),
        }

        # 总分校准: 评分标准定义"总分=四维平均", 但 LLM 偶尔给出顶层 score
        # 与四维自相矛盾的输出。两种情况以四维均值为准:
        #   1. 偏差>2 (明显矛盾, 如 score=0 四维全 3)
        #   2. 方向性矛盾: score=0 但四维均值>=1 (四维都>0 却给0分),
        #      或 score>=1 但四维均值=0 (四维全0 却给正分)
        # 正数四舍五入用 int(x+0.5), 避免 round() 的银行家舍入
        valid_dims = [v for v in breakdown.values() if isinstance(v, int)]
        if valid_dims:
            mean_score = int(sum(valid_dims) / len(valid_dims) + 0.5)
            if (
                abs(raw_score - mean_score) > 2
                or (raw_score == 0 and mean_score >= 1)
                or (raw_score >= 1 and mean_score == 0)
            ):
                score = mean_score
            else:
                score = raw_score
        else:
            score = raw_score

        return ScoreResult(
            score=score,
            max_score=max(1, bounded_int(data.get("max_score", 10), 10)),
            score_breakdown=breakdown,
            hit_points=data.get("hit_points", []) if isinstance(data.get("hit_points"), list) else [],
            missed_points=data.get("missed_points", []) if isinstance(data.get("missed_points"), list) else [],
            feedback=data.get("feedback", ""),
            is_correct=data.get("is_correct", score >= 5),
        )

    @staticmethod
    def _default_result(reason: str) -> ScoreResult:
        return ScoreResult(
            score=0,
            max_score=10,
            score_breakdown={"accuracy": 0, "completeness": 0, "depth": 0, "clarity": 0},
            hit_points=[],
            missed_points=[],
            feedback=f"评分解析失败: {reason}",
            is_correct=False,
        )

    @staticmethod
    def _extract_score_from_text(text: str) -> int:
        """从文本中提取分数"""
        patterns = [
            r'"score"\s*:\s*(\d+)',
            r"score\s*[:：]\s*(\d+)",
            r"得分\s*[:：]\s*(\d+)",
            r"评分\s*[:：]\s*(\d+)",
            r"\b(\d+)\s*/\s*10\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                score = int(match.group(1))
                if 1 <= score <= 10:
                    return score
        return 0


# ============================================================
# Chain 工厂函数
# ============================================================

def build_question_chain(llm: BaseChatModel):
    """构建出题 Chain

    Chain: question_prompt | llm | StrOutputParser

    输入参数:
        role_title, difficulty_label, question_index, total_count,
        question_text, resume_section, history
    """
    return question_prompt | llm | StrOutputParser()


def build_scoring_chain(llm: BaseChatModel):
    """构建评分 Chain

    Chain: scorer_prompt | llm | StrOutputParser | RobustScoreParser

    输入参数:
        question, standard_answer, scoring_points, candidate_answer,
        format_instructions
    """
    robust_parser = RobustScoreParser()

    def parse_score(text: str) -> ScoreResult:
        return robust_parser.parse(text)

    # 组合: prompt | llm | str_parser | robust_parser
    return scorer_prompt | llm | StrOutputParser() | parse_score


def build_followup_chain(llm: BaseChatModel):
    """构建追问 Chain

    Chain: followup_prompt | llm | StrOutputParser

    输入参数:
        current_question, missed_topic, reference_knowledge, history
    """
    return followup_prompt | llm | StrOutputParser()


def build_summary_chain(llm: BaseChatModel):
    """构建总结报告 Chain (独立上下文, 不使用 history)

    Chain: summary_prompt | llm | StrOutputParser

    输入参数:
        role_title, difficulty_label, avg_score, total_questions,
        high_score_count, low_score_count, score_details
    """
    return summary_prompt | llm | StrOutputParser()


def get_format_instructions() -> str:
    """获取 PydanticOutputParser 的格式指令 (注入到 scorer_prompt)"""
    from langchain_core.output_parsers import PydanticOutputParser
    parser = PydanticOutputParser(pydantic_object=ScoreResult)
    return parser.get_format_instructions()


# ============================================================
#  Chain: 开场 / 收尾
# ============================================================

def build_opening_chain(llm: BaseChatModel):
    """构建开场 Chain    开场白

    Chain: opening_prompt | llm | StrOutputParser

    输入参数:
        role_title, difficulty_label, total_count, candidate_name, first_direction
    """
    return opening_prompt | llm | StrOutputParser()


def build_closing_chain(llm: BaseChatModel):
    """构建收尾 Chain    收尾白 即总结最后一个问题

    Chain: closing_prompt | llm | StrOutputParser

    输入参数:
        role_title, total_count, covered_topics
    """
    return closing_prompt | llm | StrOutputParser()


# ============================================================
#  Chain: 提示 (渐进式 Hint)
# ============================================================

def build_hint_chain(llm: BaseChatModel):
    """构建提示 Chain (渐进式提示, 不泄露完整答案)

    Chain: hint_prompt | llm | StrOutputParser

    输入参数:
        question, standard_answer, hint_level (1 or 2), candidate_answer
    """
    return hint_prompt | llm | StrOutputParser()


# ============================================================
#  Chain: 项目深挖出题 (v0.9, mode=project)
# ============================================================

def build_project_question_chain(llm: BaseChatModel):
    """构建项目深挖出题 Chain

    Chain: project_question_prompt | llm | StrOutputParser

    输入参数:
        resume_context, role_title, question_index, prev_questions, jd_section, format_instructions
    """
    return project_question_prompt | llm | StrOutputParser()


def get_project_format_instructions() -> str:
    """项目深挖 JSON 格式指令"""
    from langchain_core.output_parsers import PydanticOutputParser
    parser = PydanticOutputParser(pydantic_object=ProjectQuestion)
    return parser.get_format_instructions()
