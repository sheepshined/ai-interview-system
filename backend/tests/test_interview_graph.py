import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import config
from agent.graph import build_interview_graph


def score_json(score: int) -> str:
    return json.dumps({
        "score": score,
        "max_score": 10,
        "score_breakdown": {
            "accuracy": score,
            "completeness": score,
            "depth": score,
            "clarity": score,
        },
        "hit_points": ["正确要点"] if score >= 5 else [],
        "missed_points": [] if score >= 5 else ["关键遗漏点"],
        "feedback": f"测试评分 {score}",
        "is_correct": score >= 5,
    }, ensure_ascii=False)


class FakeRetriever:
    def __init__(self):
        self.questions = [
            {
                "id": "q_001",
                "question": "请解释 Python 事件循环。",
                "category": "基础",
                "difficulty": 2,
            },
            {
                "id": "q_002",
                "question": "请说明数据库索引的作用。",
                "category": "基础",
                "difficulty": 2,
            },
        ]

    def get_categories(self, role=None):
        return ["基础"]

    def get_question(
        self,
        topic,
        role=None,
        category=None,
        difficulty=None,
        exclude_ids=None,
        top_k=5,
    ):
        excluded = set(exclude_ids or [])
        return [q.copy() for q in self.questions if q["id"] not in excluded][:top_k]

    def get_random_question(self, role=None, difficulty=None, exclude_ids=None):
        candidates = self.get_question("", role, exclude_ids=exclude_ids, top_k=1)
        return candidates[0] if candidates else None

    def get_question_by_id(self, question_id):
        """v0.9: graph 的演示首题路径会调用, fake 检索器返回 None 走正常检索"""
        return next((q.copy() for q in self.questions if q["id"] == question_id), None)

    def get_answer(self, question_id):
        question = next((q for q in self.questions if q["id"] == question_id), None)
        if not question:
            return None
        return {
            "id": question_id,
            "question": question["question"],
            "standard_answer": f"{question['question']}的标准答案",
            "scoring_points": ["关键遗漏点", "正确要点"],
            "category": question["category"],
            "difficulty": question["difficulty"],
            "max_score": 10,
        }


@pytest.fixture(autouse=True)
def _single_sample_scoring(monkeypatch):
    """v0.9 评分自一致性默认采样 3 次, 会打乱 FakeListChatModel 的响应序列;
    流程类测试只关心单次评分行为, 这里固定为 1。采样合并逻辑单独在
    test_scoring_samples_median 中验证。"""
    monkeypatch.setattr(config, "SCORING_SAMPLES", 1)


async def collect_events(graph, graph_input, cfg):
    custom = []
    async for mode, payload in graph.astream(
        graph_input,
        cfg,
        stream_mode=["custom", "values"],
    ):
        if mode == "custom":
            custom.append(payload)
    return custom


def stream_ends(events, stream_type):
    return [
        event for event in events
        if event.get("type") == "stream_end"
        and event.get("stream_type") == stream_type
    ]


@pytest.fixture
def output_dirs(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    records = tmp_path / "records"
    monkeypatch.setattr(config, "REPORTS_DIR", str(reports))
    monkeypatch.setattr(config, "INTERVIEW_RECORDS_DIR", str(records))
    return reports, records


@pytest.mark.asyncio
async def test_low_score_followup_is_combined_and_question_is_not_reemitted(output_dirs):
    fast_llm = FakeListChatModel(responses=[
        "欢迎参加面试。",
        "第一题：请解释 Python 事件循环。",
        score_json(4),
        "你遗漏了关键点，请补充事件循环如何调度任务？",
        score_json(8),
        "第二题：请说明数据库索引的作用。",
        score_json(7),
        "本次面试结束，感谢参加。",
    ])
    strong_llm = FakeListChatModel(responses=["## 总体评价\n表现稳定。"])
    graph = build_interview_graph(FakeRetriever(), fast_llm, strong_llm).compile(
        checkpointer=MemorySaver()
    )
    cfg = {"configurable": {"thread_id": "test-followup"}}

    first_events = await collect_events(graph, {
        "thread_id": "test-followup",
        "role_key": "python_dev",
        "difficulty": 2,
        "total_count": 2,
        "resume_context": "",
        "resume_skills": [],
    }, cfg)
    assert [e["question_id"] for e in stream_ends(first_events, "question")] == ["q_001"]
    assert graph.get_state(cfg).values["phase"] == "await_answer"

    followup_events = await collect_events(
        graph,
        Command(resume={"action": "answer", "content": "不知道"}),
        cfg,
    )
    assert stream_ends(followup_events, "question") == []
    assert len(stream_ends(followup_events, "followup")) == 1
    assert graph.get_state(cfg).values["phase"] == "await_followup"

    second_question_events = await collect_events(
        graph,
        Command(resume={"action": "answer", "content": "任务由事件循环调度"}),
        cfg,
    )
    assert [e["question_id"] for e in stream_ends(second_question_events, "question")] == ["q_002"]
    state = graph.get_state(cfg).values
    assert state["main_question_count"] == 1
    assert state["question_id"] == "q_002"
    assert state["initial_score"] == 0
    assert len(state["records"]) == 1
    assert state["records"][0]["question_id"] == "q_001"
    assert state["records"][0]["initial_score"] == 4
    assert state["records"][0]["score"] == 8
    assert state["records"][0]["followup_answer"] == "任务由事件循环调度"

    closing_events = await collect_events(
        graph,
        Command(resume={"action": "answer", "content": "索引加速数据查询"}),
        cfg,
    )
    assert stream_ends(closing_events, "question") == []
    assert len(stream_ends(closing_events, "closing")) == 1
    ended = [e for e in closing_events if e.get("type") == "interview_ended"]
    assert ended[0]["answered_count"] == 2
    assert graph.get_state(cfg).values["phase"] == "await_report"

    report_events = await collect_events(
        graph,
        Command(resume={"action": "report", "content": ""}),
        cfg,
    )
    ready = [e for e in report_events if e.get("type") == "report_ready"]
    assert len(ready) == 1
    report_id = ready[0]["report_id"]
    reports_dir, _ = output_dirs
    assert (reports_dir / f"{report_id}.md").is_file()
    radar = json.loads((reports_dir / f"{report_id}.json").read_text(encoding="utf-8"))
    assert [q["question_id"] for q in radar["questions"]] == ["q_001", "q_002"]
    assert radar["questions"][0]["initial_score"] == 4
    assert radar["questions"][0]["score"] == 8
    assert radar["questions"][0]["had_followup"] is True
    assert graph.get_state(cfg).values["phase"] == "completed"


@pytest.mark.asyncio
async def test_early_end_does_not_create_fake_answer_or_score(output_dirs):
    fast_llm = FakeListChatModel(responses=[
        "欢迎参加面试。",
        "第一题：请解释 Python 事件循环。",
        "面试已提前结束。",
    ])
    strong_llm = FakeListChatModel(responses=["不会被调用"])
    graph = build_interview_graph(FakeRetriever(), fast_llm, strong_llm).compile(
        checkpointer=MemorySaver()
    )
    cfg = {"configurable": {"thread_id": "test-early-end"}}
    await collect_events(graph, {
        "thread_id": "test-early-end",
        "role_key": "python_dev",
        "difficulty": 2,
        "total_count": 3,
        "resume_context": "",
        "resume_skills": [],
    }, cfg)

    end_events = await collect_events(
        graph,
        Command(resume={"action": "end", "content": ""}),
        cfg,
    )
    assert stream_ends(end_events, "question") == []
    assert len(stream_ends(end_events, "closing")) == 1
    state = graph.get_state(cfg).values
    assert state["phase"] == "await_report"
    assert state["main_question_count"] == 0
    assert state["records"] == []

    report_events = await collect_events(
        graph,
        Command(resume={"action": "report", "content": ""}),
        cfg,
    )
    assert len([e for e in report_events if e.get("type") == "report_ready"]) == 1


@pytest.mark.asyncio
async def test_zero_or_low_score_skips_followup(output_dirs):
    """完全不会(1-2分)的回答不再触发追问, 直接进入下一题。"""
    fast_llm = FakeListChatModel(responses=[
        "欢迎参加面试。",
        "第一题：请解释 Python 事件循环。",
        score_json(2),
        "第二题：请说明数据库索引的作用。",
        score_json(7),
        "本次面试结束，感谢参加。",
    ])
    strong_llm = FakeListChatModel(responses=["不会被调用"])
    graph = build_interview_graph(FakeRetriever(), fast_llm, strong_llm).compile(
        checkpointer=MemorySaver()
    )
    cfg = {"configurable": {"thread_id": "test-skip-followup"}}

    await collect_events(graph, {
        "thread_id": "test-skip-followup",
        "role_key": "python_dev",
        "difficulty": 2,
        "total_count": 2,
        "resume_context": "",
        "resume_skills": [],
    }, cfg)

    # 初始分 2 (<3): 追问不触发, 直接出下一题
    second_events = await collect_events(
        graph,
        Command(resume={"action": "answer", "content": "不知道"}),
        cfg,
    )
    assert stream_ends(second_events, "followup") == []
    assert [e["question_id"] for e in stream_ends(second_events, "question")] == ["q_002"]
    state = graph.get_state(cfg).values
    assert state["main_question_count"] == 1
    assert len(state["records"]) == 1
    assert state["records"][0]["question_id"] == "q_001"
    assert state["records"][0]["initial_score"] == 2
    assert state["records"][0]["score"] == 2
    assert state["records"][0].get("followup_question") == ""
    assert state["records"][0].get("followup_answer") == ""
    assert state["phase"] == "await_answer"

    # 完整走完: 下一题正常评分, 收尾, 报告可生成
    closing_events = await collect_events(
        graph,
        Command(resume={"action": "answer", "content": "索引加速数据查询"}),
        cfg,
    )
    assert stream_ends(closing_events, "followup") == []
    assert len(stream_ends(closing_events, "closing")) == 1
    assert graph.get_state(cfg).values["phase"] == "await_report"

    report_events = await collect_events(
        graph,
        Command(resume={"action": "report", "content": ""}),
        cfg,
    )
    assert len([e for e in report_events if e.get("type") == "report_ready"]) == 1


# ============================================================
# 反幻觉: 出题/收尾衔接不可把标准答案或 scorer hit_points 安到候选人头上
# ============================================================

from agent.graph import _build_prev_context  # noqa: E402


def _make_record(score, user_answer, hit_points=None, missed_points=None, question="Q"):
    return {
        "question": question,
        "user_answer": user_answer,
        "score": score,
        "hit_points": hit_points or [],
        "missed_points": missed_points or [],
    }


def test_build_prev_context_low_score_isolates_user_answer():
    """低分(完全不会)时: 不传 hit/missed 内容, 只给"未答出"信号, 防止 LLM
    拿标准答案知识点复述成"候选人提到过"。"""
    state = {"records": [_make_record(
        score=1,
        user_answer="不知道",
        hit_points=["前序遍历"],          # scorer 可能误判的幻觉点
        missed_points=["层序遍历用队列"],  # 标准答案里的遗漏点
        question="二叉树遍历有哪些?",
    )]}
    ctx = _build_prev_context(state)

    # 候选人原文必须原样出现(垃圾回答就是"不知道", LLM 一眼能判别)
    assert "不知道" in ctx
    # 低分提示: 不可虚构
    assert "过短" in ctx or "跑题" in ctx
    assert "严禁" in ctx or "不要" in ctx
    # hit_points 内容不得出现(避免强 LLM 拿来复述成"候选人提到过")
    assert "前序遍历" not in ctx
    # missed_points(标准答案遗漏点)内容不得出现
    assert "层序遍历用队列" not in ctx
    # 不再有"候选人回答要点"这个幻觉字段
    assert "候选人回答要点" not in ctx


def test_build_prev_context_normal_score_no_low_score_note():
    """正常分数: 不出现低分提示, 候选人原文独立呈现, 且不回流传评分的 hit/missed。"""
    state = {"records": [_make_record(
        score=7,
        user_answer="前序是根左右, 用递归实现",
        hit_points=["前序遍历"],       # 评分产出, 不应回流出题链
        missed_points=["层序遍历"],     # 评分产出, 不应回流出题链
    )]}
    ctx = _build_prev_context(state)
    # 候选人原文呈现
    assert "前序是根左右" in ctx
    # 无低分提示
    assert "过短" not in ctx and "跑题" not in ctx
    # 数据契约(②): 评分产出(hit/missed)不得回流出题链
    assert "前序遍历" not in ctx
    assert "层序遍历" not in ctx
    assert "命中得分点" not in ctx
    assert "可衔接方向" not in ctx


def test_build_prev_context_first_question():
    """第一题(无 records): 返回第一题提示。"""
    ctx = _build_prev_context({"records": []})
    assert "第一题" in ctx


# ============================================================
# v0.9 评分自一致性: 三次采样取中位
# ============================================================

def _mk_score(score: int, hit=None, miss=None):
    from agent.models import ScoreResult, ScoreBreakdown
    return ScoreResult(
        score=score, max_score=10,
        score_breakdown=ScoreBreakdown(accuracy=score, completeness=score, depth=score, clarity=score),
        hit_points=hit or [], missed_points=miss or [],
        feedback=f"测试评分 {score}", is_correct=score >= 5,
    )


def test_scoring_samples_median_merges_correctly():
    """三次采样: 总分/四维取中位, 得分点按过半采样归并, 反馈取中位那份。"""
    from agent.graph import _merge_score_samples

    merged = _merge_score_samples([
        _mk_score(7, hit=["概念正确", "提到了overlap"], miss=["没讲分块"]),
        _mk_score(6, hit=["概念正确"], miss=["没讲分块", "漏了embedding"]),
        _mk_score(8, hit=["概念正确", "提到了overlap", "举了例子"], miss=[]),
    ])
    assert merged.score == 7                      # 中位数 (6,7,8)
    assert merged.score_breakdown.depth == 7      # (6,7,8) → 7
    hit_text = " ".join(merged.hit_points)
    assert "概念正确" in hit_text                  # 3/3 采样命中
    assert "overlap" in hit_text                  # 2/3 过半命中
    assert not any("embedding" in p for p in merged.hit_points)   # 1/3 不过半


def test_scoring_samples_single_and_empty():
    """单采样直通; 空采样安全兜底。"""
    from agent.graph import _merge_score_samples

    single = _merge_score_samples([_mk_score(5, hit=["x"], miss=["y"])])
    assert single.score == 5 and single.hit_points == ["x"]

    empty = _merge_score_samples([])
    assert empty.score == 0 and empty.feedback


def test_configure_role_fallback_is_llm_app():
    """专场化后非法角色回退到大模型应用开发, 不再是已移除的 general_hr。"""
    assert "general_hr" not in config.ROLES
    assert config.ROLES["llm_app"]["title"] == "大模型应用开发工程师"
