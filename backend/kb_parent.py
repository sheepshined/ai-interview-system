"""
kb_parent.py — 知识库唯一检索模块 (Parent Document Retrieval, v1.0 起生效)

取代原 kb_vectors 的"整篇一条向量"模式, 成为知识库唯一检索入口:
  - Chroma 集合 kb_parent_children (目录可用 KB_PARENT_CHROMA_PATH 覆盖):
    只索引"子块", 用户隔离走 metadata username 过滤
  - SQLite parent_blocks 表 (knowledge.db 内): 存父块文本
  - 短文 (≤ LONG_DOC_THRESHOLD): 整篇 = 1 父块 + 1 子块,
    子块嵌入文本与旧模式逐字对齐 (标题 + 分类 + 前800字), 行为零退化
  - 长文 (> 阈值): 结构切父块 (~1200字, 段落/句子边界)
    → 子块 (~350字, 70字重叠) 索引; 子块命中后按笔记聚合, 返回父块
  - rebuild(): 全量索引 + sem_links 语义边重建 (图谱虚线边数据源)

对外接口 (与旧模块同名, 输出 schema 兼容):
  search / is_sparse / rebuild / sync_note / remove_note
  SEM_LINK_THRESHOLD / SPARSE_THRESHOLD / LONG_DOC_THRESHOLD
"""
import logging
import os
import re
from typing import Dict, List, Set, Tuple

import numpy as np

import config
import knowledge

logger = logging.getLogger(__name__)

PARENT_COLLECTION = "kb_parent_children"
PARENT_CHROMA_PATH = os.getenv(
    "KB_PARENT_CHROMA_PATH",
    os.path.join(config.BASE_DIR, "kb_parent_chroma"),
)

LONG_DOC_THRESHOLD = 1200
PARENT_CHUNK_SIZE = 1200
CHILD_CHUNK_SIZE = 350
CHILD_OVERLAP = 70

SEM_LINK_THRESHOLD = 0.66
SEM_LINK_TOP_K = 3
SPARSE_THRESHOLD = 0.35
_MAX_PARENTS_PER_NOTE = 4

_embedding_cache: List = []
_client_cache: List = []
_collection_cache: List = []
_store_ready: List = []

_PUNCT_RE = re.compile(r".+?[。！？!?；;]\s*|.+$", re.DOTALL)


def _ensure_kb() -> None:
    if not knowledge._DB_PATH:
        knowledge.init_db(config.KB_DB_PATH)


def _embeddings():
    if not _embedding_cache:
        from retrieval.embeddings import get_embeddings
        _embedding_cache.append(get_embeddings())
    return _embedding_cache[0]


def _embed_texts(texts: List[str]) -> List[list]:
    if not texts:
        return []
    emb = _embeddings()
    if hasattr(emb, "embed_documents"):
        return emb.embed_documents(texts)
    return [emb.embed_query(t) for t in texts]


def _collection():
    if not _collection_cache:
        import chromadb
        if not _client_cache:
            _client_cache.append(chromadb.PersistentClient(path=PARENT_CHROMA_PATH))
        _collection_cache.append(
            _client_cache[0].get_or_create_collection(
                name=PARENT_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        )
    return _collection_cache[0]


def _init_store() -> None:
    if _store_ready:
        return
    _ensure_kb()
    with knowledge._connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parent_blocks (
                username TEXT NOT NULL,
                parent_id TEXT NOT NULL,
                note_id INTEGER NOT NULL,
                parent_index INTEGER NOT NULL,
                title TEXT,
                category TEXT,
                text TEXT,
                created_at TEXT,
                PRIMARY KEY (username, parent_id)
            )
            """
        )
    _store_ready.append(True)


# ============================================================
# 结构感知切分
#
# 层级 (边界优先级): 行 (Markdown/代码友好) → 标点句 → 字符硬切。
# 保证每个自然单元 (行或句子) 不会被块边界拦腰切断。
# ============================================================

def _hard_split(text: str, size: int) -> List[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


def _break_to_size(text: str, size: int) -> List[str]:
    pieces: List[str] = []
    for line in re.split(r"\n", text):
        if not line:
            continue
        pieces.extend(
            _hard_split(line, size) if len(line) > size else [line]
        )
    return pieces


def _natural_units(text: str, size: int) -> List[str]:
    units: List[str] = []
    for line in re.split(r"\n+", text or ""):
        line = line.strip()
        if not line:
            continue
        if len(line) <= size:
            units.append(line)
            continue
        for s in _PUNCT_RE.findall(line):
            s = s.strip()
            if not s:
                continue
            if len(s) <= size:
                units.append(s)
            else:
                units.extend(p for p in _break_to_size(s, size) if p)
    return units


def _pack_units(units: List[str], size: int) -> List[str]:
    chunks: List[str] = []
    cur = ""
    for u in units:
        if cur and len(cur) + 1 + len(u) > size:
            chunks.append(cur)
            cur = u
        else:
            cur = f"{cur}\n{u}" if cur else u
    if cur:
        chunks.append(cur)
    return chunks


def split_parents(text: str, size: int = PARENT_CHUNK_SIZE) -> List[str]:
    units = _natural_units(text, size)
    return [c for c in _pack_units(units, size) if c.strip()]


def split_children(
    text: str,
    size: int = CHILD_CHUNK_SIZE,
    overlap: int = CHILD_OVERLAP,
) -> List[str]:
    if len(text or "") <= size:
        return [text] if text and text.strip() else []
    chunks: List[str] = []
    cur = ""
    for u in _natural_units(text, size):
        if cur and len(cur) + 1 + len(u) > size:
            chunks.append(cur)
            tail = cur[-overlap:]
            cur = tail if len(tail) + 1 + len(u) <= size else ""
        cur = f"{cur}\n{u}" if cur else u
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c.strip()]


# ============================================================
# 笔记级嵌入文本 (短文子块 + 语义边计算共用, 与旧模式逐字对齐)
# ============================================================

def _note_embed_text(note: dict) -> str:
    parts = [note["title"]]
    if note.get("category"):
        parts.append(f"分类: {note['category']}")
    content = (note.get("content") or "")[:800]
    if content:
        parts.append(content)
    return "\n".join(parts)


def _child_metadata(note: dict, parent_id: str, pi: int) -> dict:
    return {
        "username": note.get("_username", ""),
        "note_id": note["id"],
        "parent_id": parent_id,
        "parent_index": pi,
        "title": note["title"],
        "category": note.get("category") or "",
        "note_type": note.get("note_type", "note"),
        "source_url": note.get("source_url", ""),
    }


def _note_blocks(username: str, note: dict):
    note = dict(note)
    note["_username"] = username
    nid = note["id"]
    title = note["title"]
    category = note.get("category") or ""
    content = note.get("content") or ""
    is_long = len(content) > LONG_DOC_THRESHOLD

    parent_texts = (
        split_parents(content)
        if is_long
        else [content if content.strip() else title]
    )

    prows: List[tuple] = []
    ids: List[str] = []
    docs: List[str] = []
    metas: List[dict] = []

    prefix = f"《{title}》"
    if category:
        prefix += f"\n分类: {category}"

    for pi, ptext in enumerate(parent_texts):
        parent_id = f"{username}__{nid}__p{pi}"
        prows.append(
            (username, parent_id, nid, pi, title, category, ptext, knowledge._now_iso())
        )
        if is_long:
            for ci, ctext in enumerate(split_children(ptext)):
                ids.append(f"{parent_id}__c{ci}")
                docs.append(prefix + "\n" + ctext)
                metas.append(_child_metadata(note, parent_id, pi))
        else:
            ids.append(f"{parent_id}__c0")
            docs.append(_note_embed_text(note))
            metas.append(_child_metadata(note, parent_id, pi))

    return prows, ids, docs, metas, is_long


def _upsert_parents(rows: List[tuple]) -> None:
    if not rows:
        return
    with knowledge._connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO parent_blocks "
            "(username, parent_id, note_id, parent_index, title, category, text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def _delete_note_index(username: str, note_id: int) -> List[str]:
    with knowledge._connect() as conn:
        rows = conn.execute(
            "SELECT parent_id FROM parent_blocks WHERE username = ? AND note_id = ?",
            (username, note_id),
        ).fetchall()
        parent_ids = [r["parent_id"] for r in rows]
        conn.execute(
            "DELETE FROM parent_blocks WHERE username = ? AND note_id = ?",
            (username, note_id),
        )
    if parent_ids:
        try:
            _collection().delete(where={"parent_id": {"$in": parent_ids}})
        except Exception as exc:
            logger.warning("子块向量删除失败 (note=%s): %s", note_id, exc)
    return parent_ids


# ============================================================
# 增量同步 (笔记增删改后调用; 内部吞异常, 失败不阻断主流程)
# ============================================================

def sync_note(username: str, note: dict) -> None:
    try:
        _init_store()
        _delete_note_index(username, note["id"])
        prows, ids, docs, metas, _ = _note_blocks(username, note)
        if docs:
            vectors = _embed_texts(docs)
            _collection().upsert(
                ids=ids, embeddings=vectors, documents=docs, metadatas=metas
            )
        _upsert_parents(prows)
    except Exception as exc:
        logger.warning("父文档索引同步失败 (note=%s): %s", note.get("id"), exc)


def remove_note(username: str, note_id: int) -> None:
    try:
        _init_store()
        _delete_note_index(username, note_id)
    except Exception as exc:
        logger.warning("父文档索引删除失败 (note=%s): %s", note_id, exc)


# ============================================================
# 全量构建
# ============================================================

def _cleanup_stale(username: str, keep: Set[str]) -> int:
    with knowledge._connect() as conn:
        existing = {
            r["parent_id"]
            for r in conn.execute(
                "SELECT parent_id FROM parent_blocks WHERE username = ?",
                (username,),
            ).fetchall()
        }
        stale = list(existing - keep)
        if stale:
            conn.executemany(
                "DELETE FROM parent_blocks WHERE username = ? AND parent_id = ?",
                [(username, p) for p in stale],
            )
    if stale:
        try:
            _collection().delete(where={"parent_id": {"$in": stale}})
        except Exception as exc:
            logger.warning("清理过期子块向量失败: %s", exc)
    return len(stale)


def build_user_index(username: str, wipe: bool = False) -> dict:
    """从 notes 表全量构建该用户的父文档索引 (不触碰任何旧集合)。"""
    _init_store()
    note_rows = knowledge.list_notes(username)
    notes = [knowledge.get_note(username, m["id"]) for m in note_rows]
    notes = [n for n in notes if n]

    if wipe:
        _collection().delete(where={"username": username})
        with knowledge._connect() as conn:
            conn.execute("DELETE FROM parent_blocks WHERE username = ?", (username,))

    all_prows: List[tuple] = []
    all_ids: List[str] = []
    all_docs: List[str] = []
    all_metas: List[dict] = []
    keep_pids: Set[str] = set()
    long_count = 0

    for note in notes:
        prows, ids, docs, metas, is_long = _note_blocks(username, note)
        all_prows.extend(prows)
        all_ids.extend(ids)
        all_docs.extend(docs)
        all_metas.extend(metas)
        keep_pids.update(r[1] for r in prows)
        long_count += int(is_long)

    if all_docs:
        vectors = _embed_texts(all_docs)
        _collection().upsert(
            ids=all_ids, embeddings=vectors, documents=all_docs, metadatas=all_metas
        )
    _upsert_parents(all_prows)
    stale = _cleanup_stale(username, keep_pids)

    return {
        "notes": len(notes),
        "long_notes": long_count,
        "parents": len(all_prows),
        "children": len(all_docs),
        "stale_removed": stale,
    }


# ============================================================
# 语义边重建 (图谱虚线边; note 级嵌入两两余弦 + kNN 截断)
# ============================================================

def _rebuild_sem_links(username: str) -> int:
    note_rows = knowledge.list_notes(username)
    vectors: Dict[str, list] = {}
    for m in note_rows:
        note = knowledge.get_note(username, m["id"])
        if not note:
            continue
        try:
            vectors[note["title"]] = _embeddings().embed_query(_note_embed_text(note))
        except Exception:
            continue

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

    link_pairs: Dict[tuple, float] = {}
    for title, candidates in neighbors.items():
        for score, other in sorted(
            candidates, key=lambda x: x[0], reverse=True
        )[:SEM_LINK_TOP_K]:
            lo, hi = (title, other) if title < other else (other, title)
            link_pairs[(lo, hi)] = max(link_pairs.get((lo, hi), 0.0), score)
    links = [(lo, hi, score) for (lo, hi), score in link_pairs.items()]

    with knowledge._connect() as conn:
        conn.execute("DELETE FROM sem_links WHERE username = ?", (username,))
        for a, b, score in links:
            conn.execute(
                "INSERT OR REPLACE INTO sem_links "
                "(username, title_a, title_b, score, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, a, b, score, knowledge._now_iso()),
            )
    return len(links)


def rebuild(username: str) -> dict:
    """全量重建: 父文档索引 + 语义边。返回 {"notes", "sem_links"} (与旧 API 同形)。"""
    stats = build_user_index(username, wipe=True)
    sem_links = _rebuild_sem_links(username)
    return {"notes": stats["notes"], "sem_links": sem_links}


# ============================================================
# 检索: 子块命中 → 按笔记聚合 → 父块返回
# ============================================================

def _get_parent_texts(username: str, parent_ids: List[str]) -> List[str]:
    if not parent_ids:
        return []
    placeholders = ",".join("?" for _ in parent_ids)
    with knowledge._connect() as conn:
        rows = conn.execute(
            f"SELECT parent_index, text FROM parent_blocks "
            f"WHERE username = ? AND parent_id IN ({placeholders}) "
            f"ORDER BY parent_index",
            [username, *parent_ids],
        ).fetchall()
    return [r["text"] for r in rows]


def search(username: str, query: str, top_k: int = 5) -> List[dict]:
    """父文档检索。note 粒度返回, excerpt = 命中父块拼接 (与旧 search schema 兼容)。

    两层聚合:
      1. (笔记 × 父块) 去重取最高分 — 每个父块都有公平投票权,
         避免笔记只被靠前章节"代表"
      2. 按笔记聚合: 笔记分 = 最高父块分, excerpt 含该笔记全部命中父块
         (每笔记最多 _MAX_PARENTS_PER_NOTE 个, 控制上下文长度)
    """
    _init_store()
    query = (query or "").strip()
    if not query:
        return []

    qv = _embeddings().embed_query(query)
    n_results = min(max(top_k * 12, 30), 60)
    result = _collection().query(
        query_embeddings=[qv],
        n_results=n_results,
        where={"username": username},
        include=["metadatas", "distances"],
    )

    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    parent_best: Dict[Tuple[int, str], Tuple[float, dict]] = {}
    for meta, dist in zip(metas, dists):
        key = (meta["note_id"], meta["parent_id"])
        score = 1.0 - float(dist)
        prev = parent_best.get(key)
        if prev is None or score > prev[0]:
            parent_best[key] = (score, meta)

    notes_best: Dict[int, Tuple[float, dict, List[Tuple[float, str]]]] = {}
    for (nid, pid), (score, meta) in parent_best.items():
        prev = notes_best.get(nid)
        if prev is None:
            notes_best[nid] = (score, meta, [(score, pid)])
        else:
            top_score, top_meta, plist = prev
            if score > top_score:
                top_score, top_meta = score, meta
            plist.append((score, pid))
            notes_best[nid] = (top_score, top_meta, plist)

    ranked = sorted(notes_best.items(), key=lambda kv: kv[1][0], reverse=True)[:top_k]
    out: List[dict] = []
    for nid, (score, meta, plist) in ranked:
        keep = sorted(plist, key=lambda x: x[0], reverse=True)[:_MAX_PARENTS_PER_NOTE]
        ordered = sorted(
            (pid for _, pid in keep),
            key=lambda p: int(p.rsplit("p", 1)[1]),
        )
        texts = _get_parent_texts(username, ordered)
        out.append({
            "note_id": nid,
            "title": meta.get("title", ""),
            "note_type": meta.get("note_type", "note"),
            "category": meta.get("category", ""),
            "source_url": meta.get("source_url", ""),
            "score": round(score, 3),
            "excerpt": "\n---\n".join(texts),
            "matched_parents": len(ordered),
        })
    return out


def is_sparse(results: List[dict]) -> bool:
    """top1 相关度低于阈值 → 知识库缺内容。"""
    return not results or results[0]["score"] < SPARSE_THRESHOLD


def collection_empty() -> bool:
    try:
        return _collection().count() == 0
    except Exception:
        return True
