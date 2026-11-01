"""
retrieval/embeddings.py — Embeddings 工厂 (独立于 agent 包)

将 get_embeddings 从 agent.llm 下沉到 retrieval, 打破 retrieval↔agent 的循环依赖:
  之前: retrieval.retriever → agent.llm (get_embeddings)，形成反向依赖
  之后: retrieval.* 自持 get_embeddings, 不再反向依赖 agent
"""
import os
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

import config


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """创建 HuggingFaceEmbeddings 实例 (本地 BGE 模型)

    使用 lru_cache 确保全局只加载一次模型。
    若配置的是本地路径但不存在, 自动回退到 Hub 名 (BAAI/bge-base-zh-v1.5)
    以保证跨平台可移植性。

    Returns:
        HuggingFaceEmbeddings 实例
    """
    model_path = config.EMBEDDING_MODEL_PATH
    # 若配置的是本地路径但不存在, 回退到 Hub 名自动下载
    is_local_path = os.path.isabs(model_path) or os.path.sep in model_path
    if is_local_path and not os.path.exists(model_path):
        fallback = "BAAI/bge-base-zh-v1.5"
        print(
            f"[WARN] 本地嵌入模型路径不存在: {model_path}\n"
            f"       回退到 Hub 自动下载: {fallback}"
        )
        model_path = fallback
    return HuggingFaceEmbeddings(model_name=model_path)
