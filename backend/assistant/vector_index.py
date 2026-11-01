"""vector_index.py — 长期记忆的向量索引。

模式镜像 kb_parent.py:75-86 (PersistentClient + get_or_create_collection +
hnsw:space=cosine), embedding 复用现成的 retrieval.embeddings.get_embeddings,
全项目只保留一条 embedding 栈 (AGENT_PLAN §5.7 的取舍)。
"""
import logging
from typing import List, Optional

import config

logger = logging.getLogger(__name__)

COLLECTION = "agent_memory"

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        import chromadb
        _client = chromadb.PersistentClient(path=config.ASSISTANT_CHROMA_PATH)
        _collection = _client.get_or_create_collection(
            name=COLLECTION, metadata={"hnsw:space": "cosine"}
        )
    return _collection


def _embed(text: str) -> List[float]:
    from retrieval.embeddings import get_embeddings
    return get_embeddings().embed_query(text)


def upsert(memory_id: int, username: str, text: str, kind: str) -> None:
    try:
        _get_collection().upsert(
            ids=[f"mem_{username}_{memory_id}"],
            embeddings=[_embed(text)],
            documents=[text],
            metadatas=[{"username": username, "kind": kind, "mid": memory_id}],
        )
    except Exception as exc:  # 索引失败不阻塞记忆落表, 降级为关键词检索
        logger.warning("记忆向量 upsert 失败 (mid=%s): %s", memory_id, exc)


def delete(memory_id: int, username: str) -> None:
    try:
        _get_collection().delete(ids=[f"mem_{username}_{memory_id}"])
    except Exception as exc:
        logger.warning("记忆向量 delete 失败 (mid=%s): %s", memory_id, exc)


def clear(username: str) -> None:
    try:
        coll = _get_collection()
        coll.delete(where={"username": username})
    except Exception as exc:
        logger.warning("记忆向量 clear 失败 (user=%s): %s", username, exc)


def search(username: str, query: str, top_k: int = 10) -> List[dict]:
    """返回 [{mid, text, cosine}]。cosine = 1 - distance (chroma cosine 距离)。"""
    try:
        coll = _get_collection()
        if coll.count() == 0:
            return []
        res = coll.query(
            query_embeddings=[_embed(query)],
            n_results=top_k,
            where={"username": username},
        )
    except Exception as exc:
        logger.warning("记忆向量检索失败: %s", exc)
        return []
    out = []
    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    for vid, doc, dist in zip(ids, docs, dists):
        try:
            mid = int(vid.rsplit("_", 1)[1])
        except (ValueError, IndexError):
            continue
        out.append({"mid": mid, "text": doc or "",
                    "cosine": max(0.0, 1.0 - float(dist))})
    return out


def available() -> bool:
    """索引是否可用 (模型/目录缺失时上层降级为纯关键词)。"""
    try:
        _get_collection()
        return True
    except Exception:
        return False


def reset_for_tests() -> None:
    global _client, _collection
    _client, _collection = None, None
