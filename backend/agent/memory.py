"""
agent/memory.py — 面试对话记忆管理

使用 LangChain ChatMessageHistory 管理对话历史,
并实现基于摘要的上下文压缩 (ConversationSummaryBuffer 模式)。

核心能力:
  1. 存储面试对话消息 (Human/AI/System)
  2. 超过阈值时自动压缩旧消息为摘要
  3. 提供 history 参数供 LCEL Chain 使用
"""
import logging
from typing import List, Dict, Optional

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    BaseMessage,
)
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.language_models import BaseChatModel

import config

logger = logging.getLogger(__name__)


class InterviewMemory:
    """面试对话记忆管理器

    使用 LangChain InMemoryChatMessageHistory 存储消息,
    当对话超过阈值时, 调用 LLM 将旧消息压缩为摘要。

    属性:
        history:       LangChain ChatMessageHistory 实例
        summary:       历史对话的摘要文本
        llm:           用于压缩摘要的 LLM 实例
        threshold:     触发压缩的字符数阈值
        window_size:   压缩时保留的最近消息数
    """

    def __init__(self, llm: BaseChatModel, threshold: int = None, window_size: int = None):
        self.history = InMemoryChatMessageHistory()
        self.summary: str = ""
        self.llm = llm
        self.threshold = threshold or config.MEMORY_COMPRESS_THRESHOLD
        self.window_size = window_size or config.MEMORY_WINDOW_SIZE

    def add_user_message(self, content: str):
        """添加用户消息"""
        self.history.add_user_message(content)

    def add_ai_message(self, content: str):
        """添加 AI 消息"""
        self.history.add_ai_message(content)

    def add_system_message(self, content: str):
        """添加系统消息"""
        self.history.add_message(SystemMessage(content=content))

    def get_messages(self) -> List[BaseMessage]:
        """获取所有消息 (LangChain BaseMessage 列表)"""
        return self.history.messages

    def get_history_for_chain(self) -> List[BaseMessage]:
        """获取用于 LCEL Chain 的历史消息

        返回最近 window_size 条消息,
        如果有摘要则前置一条 SystemMessage。
        """
        messages: List[BaseMessage] = []

        # 如果有压缩摘要, 加入上下文
        if self.summary:
            messages.append(SystemMessage(content=f"[之前对话摘要] {self.summary}"))

        # 加入最近的消息 (不超过 window_size 条)
        recent = self.history.messages[-self.window_size :] if len(self.history.messages) > self.window_size else self.history.messages
        messages.extend(recent)

        return messages

    def get_total_chars(self) -> int:
        """计算当前所有消息的总字符数"""
        return sum(len(str(m.content)) for m in self.history.messages)

    def maybe_compress(self):
        """当对话超过阈值时, 压缩旧消息为摘要

        策略:
          1. 计算总字符数
          2. 如果超过阈值, 保留最近 window_size 条消息
          3. 将旧消息发送给 LLM 生成摘要
          4. 用摘要 + 最近消息替换完整历史
        """
        total = self.get_total_chars()
        if total < self.threshold:
            return

        all_msgs = self.history.messages
        if len(all_msgs) <= self.window_size:
            return

        # 分割: 旧消息 → 压缩; 最近消息 → 保留
        split = max(len(all_msgs) - self.window_size, 0)
        old_msgs = all_msgs[:split]
        recent_msgs = all_msgs[split:]

        if not old_msgs:
            return

        # 构建压缩请求
        from agent.prompts import compress_prompt

        old_text = "\n".join(
            f"[{m.type}]: {str(m.content)[:300]}" for m in old_msgs
        )

        try:
            chain = compress_prompt | self.llm
            result = chain.invoke({"conversation_text": old_text})
            self.summary = result.content.strip() if hasattr(result, "content") else str(result).strip()

            # 用摘要 + 最近消息重建历史
            self.history = InMemoryChatMessageHistory()
            for m in recent_msgs:
                self.history.add_message(m)

        except Exception as e:
            # 压缩失败时, 直接截断保留最近消息
            logger.warning("对话摘要压缩失败, 截断保留最近消息: %s", e)
            self.history = InMemoryChatMessageHistory()
            for m in recent_msgs:
                self.history.add_message(m)

    def clear(self):
        """清空所有记忆"""
        self.history = InMemoryChatMessageHistory()
        self.summary = ""
