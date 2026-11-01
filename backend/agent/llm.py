"""
agent/llm.py — LangChain LLM 工厂

使用 LangChain 的 ChatOpenAI (兼容智谱/DeepSeek/OpenAI 等 OpenAI 兼容接口)。
Embeddings 工厂已下沉到 retrieval.embeddings (打破 retrieval↔agent 循环依赖),
此处保留 re-export 仅为向后兼容。
"""
from typing import Optional

from langchain_openai import ChatOpenAI

import config


def get_llm(
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
) -> ChatOpenAI:
    """创建 LangChain ChatOpenAI 实例 (兼容智谱 GLM / DeepSeek / OpenAI)

    Args:
        temperature: 采样温度, 默认使用 config.LLM_TEMPERATURE
        max_tokens:  最大输出 token 数
        model:       模型名称, 默认使用 config.LLM_MODEL
        timeout:     单次请求超时 (秒), 默认 None (使用 OpenAI 客户端默认值)

    Returns:
        ChatOpenAI 实例, 可直接用于 LCEL Chain
    """
    api_key = config.LLM_API_KEY
    if not api_key:
        raise ValueError(
            "未配置 LLM API Key, 请检查 .env 文件中的 LLM_API_KEY "
            "(或向后兼容的 DEEPSEEK_API_KEY)"
        )

    return ChatOpenAI(
        model=model or config.LLM_MODEL,
        api_key=api_key,
        base_url=config.LLM_BASE_URL,
        temperature=temperature if temperature is not None else config.LLM_TEMPERATURE,
        max_tokens=max_tokens or config.LLM_MAX_TOKENS,
        max_retries=config.LLM_MAX_RETRIES,
        timeout=timeout,
    )


def get_fast_llm(**kwargs) -> ChatOpenAI:
    """快速模型 — 出题/评分/追问/开场/收尾 (求速度, 默认 deepseek-chat)"""
    return get_llm(model=config.LLM_MODEL_FAST, **kwargs)


def get_strong_llm(**kwargs) -> ChatOpenAI:
    """强模型 — 总结报告 (求质量, 低温; 可配 deepseek-reasoner/glm-4.5)"""
    kwargs.setdefault("temperature", config.LLM_TEMPERATURE_STRONG)
    return get_llm(model=config.LLM_MODEL_STRONG, **kwargs)


# 向后兼容: embeddings 已下沉到 retrieval.embeddings, 打破 retrieval↔agent 循环依赖
from retrieval.embeddings import get_embeddings  # noqa: E402,F401
