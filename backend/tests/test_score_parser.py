from agent.chains import RobustScoreParser


def test_score_parser_clamps_and_tolerates_string_values():
    result = RobustScoreParser().parse(
        """{
          "score": "12",
          "max_score": "10",
          "score_breakdown": {
            "accuracy": "9", "completeness": 20,
            "depth": "bad", "clarity": 8.7
          },
          "hit_points": ["命中"], "missed_points": [],
          "feedback": "测试", "is_correct": true
        }"""
    )
    assert result.score == 10
    assert result.score_breakdown.accuracy == 9
    assert result.score_breakdown.completeness == 10
    assert result.score_breakdown.depth == 10
    assert result.score_breakdown.clarity == 8


def test_score_parser_returns_zero_for_empty_output():
    result = RobustScoreParser().parse("")
    assert result.score == 0
    assert result.is_correct is False


# ============================================================
# 总分校准: 顶层 score 与四维均值偏差>2 时以均值为准
# ============================================================

def test_score_parser_calibrates_score_when_breakdown_contradicts():
    """LLM 自相矛盾(score=0 但四维全 1)时, 总分采用四维均值=1。
    复现垃圾输入测试中 Q1 的不一致(评分维度=1,1,1,1 但 final_score=0)。"""
    result = RobustScoreParser().parse(
        """{
          "score": 0,
          "max_score": 10,
          "score_breakdown": {
            "accuracy": 1, "completeness": 1, "depth": 1, "clarity": 1
          },
          "hit_points": [], "missed_points": ["全部"],
          "feedback": "完全不会", "is_correct": false
        }"""
    )
    assert result.score_breakdown.accuracy == 1
    assert result.score == 1  # 均值(1+1+1+1)/4=1, 偏差>2 触发校准
    assert result.is_correct is False


def test_score_parser_keeps_score_when_within_tolerance():
    """顶层 score 与四维均值偏差≤2 时保留顶层 score(不误校准)。"""
    result = RobustScoreParser().parse(
        """{
          "score": 7,
          "max_score": 10,
          "score_breakdown": {
            "accuracy": 8, "completeness": 7, "depth": 7, "clarity": 8
          },
          "hit_points": ["要点"], "missed_points": [],
          "feedback": "基本正确", "is_correct": true
        }"""
    )
    # 均值=(8+7+7+8)/4=7.5→8, 顶层7, 偏差1≤2, 保留顶层
    assert result.score == 7
    assert result.is_correct is True


def test_score_parser_calibrates_high_score_contradiction():
    """反向矛盾: score=9 但四维全 5(均值5), 偏差4>2, 校准为 5。
    防止追问分档被虚高 score 误判为"已答好"而跳过追问。"""
    result = RobustScoreParser().parse(
        """{
          "score": 9,
          "max_score": 10,
          "score_breakdown": {
            "accuracy": 5, "completeness": 5, "depth": 5, "clarity": 5
          },
          "hit_points": [], "missed_points": ["多处遗漏"],
          "feedback": "部分正确", "is_correct": true
        }"""
    )
    assert result.score == 5  # 校准为均值
    assert result.is_correct is True  # is_correct 仍由原值>=5 判定, 不受校准影响
