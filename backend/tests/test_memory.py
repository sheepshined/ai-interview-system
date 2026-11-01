"""InterviewMemory 接线验证: add → get_history_for_chain → maybe_compress 链路。

① history 接入的核心能力测试。memory.py 是 HEAD 恢复的成熟实现,
这里验证它经 graph 接线后所依赖的行为契约仍成立。
"""
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from agent.memory import InterviewMemory
import config


def test_memory_add_and_get_history():
    """add_user/ai_message 后, get_history_for_chain 返回按序消息, 无摘要时无 SystemMessage。"""
    mem = InterviewMemory(llm=FakeListChatModel(responses=["摘要"]))
    mem.add_ai_message("你好，开始面试。")
    mem.add_user_message("好的。")

    history = mem.get_history_for_chain()
    # 无摘要: 不应前置 SystemMessage
    assert not any(m.type == "system" for m in history)
    # 两条消息按序: AI 在前, Human 在后
    assert len(history) == 2
    assert history[0].type == "ai"
    assert history[1].type == "human"
    assert "开始面试" in history[0].content
    assert "好的" in history[1].content


def test_memory_compress_prepends_summary_system_message():
    """超阈值压缩后: 旧消息被摘要替换, get_history_for_chain 前置 [之前对话摘要] SystemMessage,
    保留最近 window_size 条。"""
    # 用极小阈值/窗口便于触发
    mem = InterviewMemory(
        llm=FakeListChatModel(responses=["之前聊了二叉树遍历和动态规划两个话题。"]),
        threshold=50,   # 50 字符即触发
        window_size=2,  # 只保留最近 2 条
    )
    # 加 4 条消息, 总字符超 50, 且条数 > window_size
    mem.add_ai_message("第一题：请说明二叉树的前序中序后序遍历。")
    mem.add_user_message("前序是根左右，中序左根右，后序左右根。")
    mem.add_ai_message("回答正确。第二题：什么是动态规划？")
    mem.add_user_message("用于最优子结构和重叠子问题的方法。")

    mem.maybe_compress()

    # 压缩后: history 应 = 1 摘要 SystemMessage + 最近 window_size 条原始消息
    history = mem.get_history_for_chain()
    assert history[0].type == "system"
    assert "[之前对话摘要]" in history[0].content
    # 最近 2 条被保留(后两条: ai + human)
    assert len(history[1:]) == 2
    assert history[1].type == "ai"
    assert "动态规划" in history[1].content


def test_memory_no_compress_below_threshold():
    """未超阈值: maybe_compress 不触发, 消息全保留, 无摘要。"""
    mem = InterviewMemory(
        llm=FakeListChatModel(responses=["不该被调用"]),
        threshold=10000,
        window_size=10,
    )
    mem.add_ai_message("短消息")
    mem.add_user_message("嗯")

    mem.maybe_compress()

    history = mem.get_history_for_chain()
    assert len(history) == 2
    assert not any(m.type == "system" for m in history)


def test_memory_compress_failure_falls_back_to_truncation():
    """压缩 LLM 抛异常时: fallback 为硬截断(保留最近 window_size 条), 不崩。"""
    class BoomLLM(FakeListChatModel):
        def invoke(self, *args, **kwargs):
            raise RuntimeError("压缩 LLM 挂了")

    mem = InterviewMemory(
        llm=BoomLLM(responses=[]),
        threshold=50,
        window_size=2,
    )
    mem.add_ai_message("第一题：说明快排原理。" * 3)
    mem.add_user_message("分治选基准分区。")
    mem.add_ai_message("第二题：哈希冲突如何解决？")
    mem.add_user_message("链地址法。")

    # 不应抛异常
    mem.maybe_compress()
    # fallback: 保留最近 2 条, 无摘要(压缩失败 summary 保持空)
    history = mem.get_history_for_chain()
    assert len(history) == 2
    assert not any(m.type == "system" for m in history)
    assert "哈希冲突" in history[0].content


def test_memory_uses_config_defaults():
    """不传 threshold/window_size 时, 使用 config.MEMORY_* 默认值。"""
    mem = InterviewMemory(llm=FakeListChatModel(responses=["x"]))
    assert mem.threshold == config.MEMORY_COMPRESS_THRESHOLD
    assert mem.window_size == config.MEMORY_WINDOW_SIZE
