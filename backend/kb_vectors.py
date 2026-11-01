"""
kb_vectors.py — 知识库独立向量库 (v0.8 批次B)

与面试题库 (interview_questions 集合) 完全隔离的 Chroma 集合 kb_notes:
  - 嵌入文本 = 标题 + 分类 + 内容前 800 字 (网址笔记嵌入标题+描述, 保证描述可检索)
  - 全部 metadata 带 username, 检索时 where 过滤 → 天然按用户隔离
  - 写入时机: 笔记 create/update/delete 时同步 (失败只 log 不阻断主流程)
  - 语义关联 rebuild: 全量嵌入一次, 两两余弦相似度 > 阈值写 sem_links 表
"""
import logging
from typing import Dict, List, Optional

import numpy as np

import config
import knowledge

logger = logging.getLogger(__name__)

KB_COLLECTION = "kb_notes"
# 语义边阈值: 余弦相似度 ≥ 该值才连虚线边
# 0.68: 垂直同质语料(同主题笔记)相似度普遍偏高, 阈值要更高才能只保留
# "同一子主题(RAG↔RAG)"而过滤掉"只是都属于大模型话题"的跨主题弱关联
SEM_LINK_THRESHOLD = 0.66
# 每篇笔记只保留相似度最高的 N 条语义边 (kNN 截断, 防止跨簇桥接过多把团拉散)
SEM_LINK_TOP_K = 3
# 检索相关度预警阈值: top1 < 该值视为知识库缺相关内容
SPARSE_THRESHOLD = 0.35

_embedding_cache: List = []      # [embeddings_instance]
_collection_cache: List = []     # [chroma_collection]


def _embeddings():
    if not _embedding_cache:
        from retrieval.embeddings import get_embeddings
        _embedding_cache.append(get_embeddings())
    return _embedding_cache[0]


def _collection():
    """懒加载 kb_notes 集合 (持久化目录与题库同级的 kb_chroma 子目录)。"""
    if not _collection_cache:
        import chromadb
        path = config.KB_CHROMA_PATH
        client = chromadb.PersistentClient(path=path)
        _collection_cache.append(
            client.get_or_create_collection(
                name=KB_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        )
    return _collection_cache[0]


def _embed_text(note: dict) -> str:
    """笔记 → 用于嵌入的文本。"""
    parts = [note["title"]]
    if note.get("category"):
        parts.append(f"分类: {note['category']}")
    content = (note.get("content") or "")[:800]
    if content:
        parts.append(content)
    return "\n".join(parts)


def _vec_id(username: str, note_id: int) -> str:
    return f"{username}__{note_id}"


# ============================================================
# 写同步
# ============================================================

def upsert_note(username: str, note: dict) -> None:
    """笔记创建/更新后同步向量。失败只记日志 (笔记为主, 向量可重建)。"""
    try:
        text = _embed_text(note)
        vector = _embeddings().embed_query(text)
        _collection().upsert(
            ids=[_vec_id(username, note["id"])],
            embeddings=[vector],
            documents=[text],
            metadatas=[{
                "username": username,
                "note_id": note["id"],
                "title": note["title"],
                "note_type": note.get("note_type", "note"),
                "category": note.get("category", ""),
                "source_url": note.get("source_url", ""),
            }],
        )
    except Exception as exc:
        logger.warning("笔记向量同步失败 (note=%s): %s", note.get("id"), exc)


def delete_note(username: str, note_id: int) -> None:
    try:
        _collection().delete(ids=[_vec_id(username, note_id)])
    except Exception as exc:
        logger.warning("笔记向量删除失败 (note=%s): %s", note_id, exc)


# ============================================================
# 检索
# ============================================================

def search(username: str, query: str, top_k: int = 5) -> List[dict]:
    """向量检索该用户知识库, 返回按相关度降序的结果。

    Returns:
        [{note_id, title, note_type, category, source_url, score, excerpt}]
        失败返回 [] (服务端降级, 不抛)。
    """
    query = (query or "").strip()
    if not query:
        return []
    try:
        vector = _embeddings().embed_query(query)
        result = _collection().query(
            query_embeddings=[vector],
            n_results=max(1, min(top_k, 10)),
            where={"username": username},
        )
    except Exception as exc:
        logger.warning("知识库检索失败: %s", exc)
        return []

    ids = (result.get("ids") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]

    out = []
    for i, meta in enumerate(metas):
        # cosine 空间: distance = 1 - similarity
        score = 1.0 - float(dists[i])
        # 向量库只存了前 800 字摘要, 解读类问题需要拉取笔记全文作上下文
        excerpt = (docs[i] or "")[:120]
        try:
            full = knowledge.get_note(username, meta.get("note_id"))
            if full:
                excerpt = (full.get("content") or "")[:4000] or excerpt
        except Exception:
            pass
        out.append({
            "note_id": meta.get("note_id"),
            "title": meta.get("title", ""),
            "note_type": meta.get("note_type", "note"),
            "category": meta.get("category", ""),
            "source_url": meta.get("source_url", ""),
            "score": round(score, 3),
            "excerpt": excerpt,
        })
    return out


def is_sparse(results: List[dict]) -> bool:
    """top1 相关度低于阈值 → 知识库缺内容。"""
    return not results or results[0]["score"] < SPARSE_THRESHOLD


# ============================================================
# 全量重建 (向量 + 语义关联)
# ============================================================

def rebuild(username: str) -> dict:
    """重建该用户的全部向量与语义关联表。

    Returns:
        {"notes": n, "sem_links": m}
    """
    notes = knowledge.list_notes(username)
    # 列表视图 content 是摘要, 重建需全文 → 逐条 get
    vectors: Dict[str, list] = {}
    count = 0
    for item in notes:
        note = knowledge.get_note(username, item["id"])
        if not note:
            continue
        upsert_note(username, note)
        try:
            vectors[note["title"]] = _embeddings().embed_query(_embed_text(note))
        except Exception:
            continue
        count += 1

    # 两两余弦相似度 → 每节点收集候选邻居
    titles = list(vectors.keys())
    neighbors: Dict[str, list] = {t: [] for t in titles}
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            a, b = titles[i], titles[j]
            va, vb = np.array(vectors[a]), np.array(vectors[b])
            denom = (np.linalg.norm(va) * np.linalg.norm(vb)) or 1e-9
            score = float(np.dot(va, vb) / denom)
            if score >= SEM_LINK_THRESHOLD:
                neighbors[a].append((score, b))
                neighbors[b].append((score, a))

    # kNN 截断: 每个节点只保留相似度最高的 SEM_LINK_TOP_K 个邻居;
    # 取并集(A 选了 B 或 B 选了 A 都连边), 避免高相似对被单边截断误删
    link_pairs: Dict[tuple, float] = {}
    for title, candidates in neighbors.items():
        for score, other in sorted(candidates, key=lambda x: x[0], reverse=True)[:SEM_LINK_TOP_K]:
            lo, hi = (title, other) if title < other else (other, title)
            # 同一对可能从两个方向入选, 保留较高分
            link_pairs[(lo, hi)] = max(link_pairs.get((lo, hi), 0.0), score)
    links = [(lo, hi, score) for (lo, hi), score in link_pairs.items()]

    with knowledge._connect() as conn:
        conn.execute("DELETE FROM sem_links WHERE username = ?", (username,))
        for a, b, score in links:
            conn.execute(
                "INSERT OR REPLACE INTO sem_links (username, title_a, title_b, score, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, a, b, score, knowledge._now_iso()),
            )
    return {"notes": count, "sem_links": len(links)}


def collection_empty() -> bool:
    try:
        return _collection().count() == 0
    except Exception:
        return True
