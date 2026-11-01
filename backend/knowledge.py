"""
knowledge.py — 个人知识库模块 (v0.7)

Obsidian 哲学的最小实现:
  - 笔记是唯一数据源 (SQLite notes 表, 同用户标题唯一)
  - 链接写在内容里 ([[标题]] 语法), 图谱与反向链接都是**解析出来的衍生视图**
  - [[不存在的标题]] = 虚节点 (图谱灰色展示, 前端点击可创建)

联动: 面试报告薄弱点/学习建议可一键入库 (source=interview_report)。
所有数据按 username 隔离, 走 v0.6 的 JWT 鉴权。
"""
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

# [[标题]] — 不允许嵌套 [[、换行; 标题内允许空白与中英文
WIKI_LINK_RE = re.compile(r"\[\[([^\[\]\n]{1,120})\]\]")

MAX_TITLE_LEN = 120
MAX_CONTENT_LEN = 100_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


_DB_PATH = ""  # 由 init_db 设置


def init_db(db_path: str) -> None:
    """建表并记录库路径 (server 启动时调用一次)。"""
    global _DB_PATH
    _DB_PATH = db_path
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(username, title)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notes_username ON notes(username)"
        )
        # v0.8 批次A: 类型/分类/网址/文件名 字段 (旧库自动补列, 旧数据兼容)
        _migrate_columns(conn, [
            ("note_type", "TEXT NOT NULL DEFAULT 'note'"),
            ("category", "TEXT NOT NULL DEFAULT ''"),
            ("source_url", "TEXT NOT NULL DEFAULT ''"),
            ("file_name", "TEXT NOT NULL DEFAULT ''"),
            ("file_path", "TEXT NOT NULL DEFAULT ''"),
            ("raw_content", "TEXT NOT NULL DEFAULT ''"),
        ])
        # v0.8 批次C: 语义关联表 (向量相似度预计算, 图谱虚线边数据源)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sem_links (
                username TEXT NOT NULL,
                title_a TEXT NOT NULL,
                title_b TEXT NOT NULL,
                score REAL NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (username, title_a, title_b)
            )
            """
        )
        # v0.9: AI 对话会话 + 消息表
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '新对话',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON kb_chat_sessions(username)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources TEXT NOT NULL DEFAULT '[]',
                sparse INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON kb_chat_messages(session_id)"
        )


def _migrate_columns(conn: sqlite3.Connection, columns) -> None:
    """SQLite ALTER TABLE 增量加列 (已存在则跳过)。"""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(notes)")}
    for name, ddl in columns:
        if name not in existing:
            conn.execute(f"ALTER TABLE notes ADD COLUMN {name} {ddl}")


# ============================================================
# 校验
# ============================================================

def validate_note(title: str, content: str, note_type: str = "note") -> Optional[str]:
    """返回错误信息 (None 表示合法)。"""
    title = (title or "").strip()
    if not title:
        return "标题不能为空"
    if len(title) > MAX_TITLE_LEN:
        return f"标题过长 (最多 {MAX_TITLE_LEN} 字)"
    if "[[" in title or "]]" in title:
        return "标题不能包含 [[ 或 ]]"
    if len(content or "") > MAX_CONTENT_LEN:
        return f"内容过长 (最多 {MAX_CONTENT_LEN} 字)"
    if note_type == "url" and not (content or "").strip():
        return "网址笔记必须填写描述内容"
    return None


# ============================================================
# CRUD
# ============================================================

def _row_to_dict(row: sqlite3.Row, links: Optional[List[str]] = None) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "tags": [t for t in row["tags"].split(",") if t.strip()],
        "source": row["source"],
        "note_type": row["note_type"] if "note_type" in row.keys() else "note",
        "category": row["category"] if "category" in row.keys() else "",
        "source_url": row["source_url"] if "source_url" in row.keys() else "",
        "file_name": row["file_name"] if "file_name" in row.keys() else "",
        "file_path": row["file_path"] if "file_path" in row.keys() else "",
        "raw_content": row["raw_content"] if "raw_content" in row.keys() else "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "links": links if links is not None else parse_links(row["content"]),
    }


def parse_links(content: str) -> List[str]:
    """解析内容中的 [[链接]] 标题列表 (保序去重)。"""
    seen: List[str] = []
    for match in WIKI_LINK_RE.finditer(content or ""):
        title = match.group(1).strip()
        if title and title not in seen:
            seen.append(title)
    return seen


def list_notes(username: str, search: str = "", tag: str = "",
               category: str = "") -> List[dict]:
    """列出用户笔记 (标题/内容/标签 子串过滤 + 分类精确过滤), 按更新时间倒序。"""
    sql = "SELECT * FROM notes WHERE username = ?"
    params: list = [username]
    if search:
        sql += " AND (title LIKE ? OR content LIKE ?)"
        like = f"%{search}%"
        params += [like, like]
    if tag:
        sql += " AND ((',' || tags || ',') LIKE ?)"
        params += [f"%,{tag},%"]
    if category:
        sql += " AND category = ?"
        params += [category]
    sql += " ORDER BY updated_at DESC"
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    # 列表视图不返回全文, 只给摘要
    return [
        {
            **_row_to_dict(row),
            "content": row["content"][:160],
            "link_count": len(parse_links(row["content"])),
        }
        for row in rows
    ]


def list_categories(username: str) -> List[dict]:
    """聚合用户已有分类及计数 (空分类不返回)。"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) AS n FROM notes "
            "WHERE username = ? AND category != '' GROUP BY category ORDER BY n DESC",
            (username,),
        ).fetchall()
    return [{"category": r["category"], "count": r["n"]} for r in rows]


def get_note(username: str, note_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM notes WHERE id = ? AND username = ?",
            (note_id, username),
        ).fetchone()
    return _row_to_dict(row) if row else None


def find_note_by_file(username: str, file_path: str) -> Optional[dict]:
    """按存储的 file_path 查询归属用户的文件笔记 (鉴权下载用)。"""
    if not file_path:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM notes WHERE username = ? AND file_path = ? LIMIT 1",
            (username, file_path),
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_note(username: str, title: str, content: str = "",
                tags: Optional[List[str]] = None, source: str = "manual",
                note_type: str = "note", category: str = "",
                source_url: str = "", file_name: str = "",
                file_path: str = "", raw_content: str = "") -> dict:
    """创建笔记。标题冲突抛 ValueError。"""
    title = (title or "").strip()
    error = validate_note(title, content, note_type)
    if error:
        raise ValueError(error)
    if note_type not in {"note", "file", "url"}:
        raise ValueError("无效的笔记类型")
    tag_str = ",".join(sorted({(t or "").strip() for t in (tags or []) if t.strip()}))
    now = _now_iso()
    try:
        with _connect() as conn:
            cursor = conn.execute(
                "INSERT INTO notes (username, title, content, tags, source, "
                "note_type, category, source_url, file_name, file_path, raw_content, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (username, title, content or "", tag_str, source,
                 note_type, (category or "").strip()[:20],
                 (source_url or "").strip()[:500], (file_name or "").strip()[:200],
                 (file_path or "").strip()[:500],
                 (raw_content or "").strip()[:200000],
                 now, now),
            )
            note_id = cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError("已存在同名笔记") from exc
    return {"id": note_id, "title": title}


def migrate_file_paths(kb_files_dir: str) -> int:
    """将旧版绝对磁盘路径的 file_path 迁移为 /kb_files/<文件名> 静态链接。

    旧版本把上传文件存为绝对路径 (如 e:\\...\\kb_uploads\\xxx), 浏览器无法打开;
    新版文件统一存到 kb_files 目录并通过静态路由访问。若旧文件仍存在于磁盘,
    则复制到 kb_files 并改写链接。返回迁移条数。
    """
    import os
    import shutil

    migrated = 0
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, file_path, file_name FROM notes "
            "WHERE file_path IS NOT NULL AND file_path != '' "
            "AND file_path NOT LIKE '/kb_files/%'"
        ).fetchall()
        for row in rows:
            old_path = row["file_path"]
            if not os.path.isfile(old_path):
                continue
            target_name = os.path.basename(old_path)
            target_path = os.path.join(kb_files_dir, target_name)
            if not os.path.exists(target_path):
                try:
                    shutil.copy2(old_path, target_path)
                except OSError:
                    continue
            conn.execute(
                "UPDATE notes SET file_path = ? WHERE id = ?",
                (f"/kb_files/{target_name}", row["id"]),
            )
            migrated += 1
    return migrated


def update_note(username: str, note_id: int, title: str, content: str,
                tags: Optional[List[str]] = None, category: str = "") -> dict:
    title = (title or "").strip()
    error = validate_note(title, content)
    if error:
        raise ValueError(error)
    tag_str = ",".join(sorted({(t or "").strip() for t in (tags or []) if t.strip()}))
    try:
        with _connect() as conn:
            cursor = conn.execute(
                "UPDATE notes SET title = ?, content = ?, tags = ?, category = ?, updated_at = ? "
                "WHERE id = ? AND username = ?",
                (title, content or "", tag_str, (category or "").strip()[:20],
                 _now_iso(), note_id, username),
            )
            if cursor.rowcount == 0:
                raise LookupError("笔记不存在")
    except sqlite3.IntegrityError as exc:
        raise ValueError("已存在同名笔记") from exc
    return {"id": note_id, "title": title}


def delete_note(username: str, note_id: int) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM notes WHERE id = ? AND username = ?", (note_id, username)
        )
        return cursor.rowcount > 0


# ============================================================
# 图谱与反向链接 (衍生视图)
# ============================================================

def build_graph(username: str, include_semantic: bool = True,
                categories: Optional[List[str]] = None) -> dict:
    """构建知识图谱。

    节点: 已存在笔记 (degree=连接数) + 链接到的不存在标题 (virtual=True)
    边:   kind="wiki" ([[链接]] 显式边) / kind="semantic" (语义相似度边, 读 sem_links 表)
    过滤: categories 非空时只保留该分类的实体笔记 (虚节点相应丢弃)
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, tags, content, note_type, category, source_url "
            "FROM notes WHERE username = ?",
            (username,),
        ).fetchall()
        sem_rows = conn.execute(
            "SELECT title_a, title_b, score FROM sem_links WHERE username = ?",
            (username,),
        ).fetchall() if include_semantic else []

    id_by_title = {row["title"]: row["id"] for row in rows}
    degree: Dict[str, int] = {row["title"]: 0 for row in rows}
    wiki_edges = []
    virtual = set()

    for row in rows:
        for target in parse_links(row["content"]):
            # 自链不建边
            if target == row["title"]:
                continue
            wiki_edges.append({
                "kind": "wiki",
                "source": row["title"],
                "target": target,
                "virtual": target not in id_by_title,
            })
            degree[row["title"]] = degree.get(row["title"], 0) + 1
            if target in degree:
                degree[target] += 1
            else:
                degree[target] = 1
                virtual.add(target)

    # 分类过滤: 不匹配的实体笔记移除 (其 wiki 边一并丢弃; 语义边后算)
    cat_set = set(categories or [])
    if cat_set:
        rows = [r for r in rows if (r["category"] or "") in cat_set]
        keep = {r["title"] for r in rows}
        wiki_edges = [
            e for e in wiki_edges
            if e["source"] in keep and (e["target"] in keep or e["virtual"])
        ]

    nodes = [
        {
            "id": row["title"],          # 用标题作节点 id, 前端点击即知去哪
            "note_id": id_by_title[row["title"]],
            "degree": degree[row["title"]],
            "tags": [t for t in row["tags"].split(",") if t.strip()],
            "note_type": row["note_type"],
            "category": row["category"] or "",
            "source_url": row["source_url"] or "",
            "virtual": False,
        }
        for row in rows
    ] + [
        {"id": title, "note_id": None, "degree": degree[title], "tags": [],
         "note_type": "note", "category": "", "source_url": "", "virtual": True}
        for title in sorted(virtual)
        if not cat_set or any(
            e["target"] == title for e in wiki_edges
        )
    ]

    # 语义边: 两端都是实体笔记 (过滤后集合内), 且不与 wiki 边重复
    keep_titles = {n["id"] for n in nodes if not n["virtual"]}
    existing_pairs = {(e["source"], e["target"]) for e in wiki_edges} | {
        (e["target"], e["source"]) for e in wiki_edges
    }
    sem_edges = []
    for r in sem_rows:
        a, b = r["title_a"], r["title_b"]
        if a in keep_titles and b in keep_titles and (a, b) not in existing_pairs:
            sem_edges.append({
                "kind": "semantic", "source": a, "target": b,
                "score": round(r["score"], 3), "virtual": False,
            })

    return {"nodes": nodes, "edges": wiki_edges + sem_edges}


def get_backlinks(username: str, note_id: int) -> List[dict]:
    """反向链接: 哪些笔记的 [[链接]] 指向了该笔记。"""
    note = get_note(username, note_id)
    if not note:
        return []
    title = note["title"]
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at, content FROM notes WHERE username = ?",
            (username,),
        ).fetchall()
    results = []
    for row in rows:
        if row["id"] == note_id:
            continue
        if title in parse_links(row["content"]):
            results.append({
                "id": row["id"], "title": row["title"],
                "updated_at": row["updated_at"],
            })
    return results


# ============================================================
# v0.9: AI 对话会话 CRUD
# ============================================================

import json as _json


def create_chat_session(username: str, title: str = "新对话") -> dict:
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO kb_chat_sessions (username, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (username, title, now, now),
        )
        sid = cur.lastrowid
        return {"id": sid, "username": username, "title": title,
                "created_at": now, "updated_at": now}


def list_chat_sessions(username: str) -> list:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM kb_chat_sessions "
            "WHERE username = ? ORDER BY updated_at DESC",
            (username,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_chat_session(username: str, session_id: int) -> dict | None:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM kb_chat_sessions "
            "WHERE id = ? AND username = ?",
            (session_id, username),
        ).fetchone()
        return dict(row) if row else None


def rename_chat_session(username: str, session_id: int, title: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE kb_chat_sessions SET title = ?, updated_at = ? "
            "WHERE id = ? AND username = ?",
            (title[:80], _now_iso(), session_id, username),
        )
        return cur.rowcount > 0


def delete_chat_session(username: str, session_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM kb_chat_sessions WHERE id = ? AND username = ?",
            (session_id, username),
        )
        if cur.rowcount > 0:
            conn.execute("DELETE FROM kb_chat_messages WHERE session_id = ?", (session_id,))
            return True
        return False


def list_chat_messages(username: str, session_id: int) -> list:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, role, content, sources, sparse, created_at "
            "FROM kb_chat_messages WHERE session_id = ? "
            "ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["sources"] = _json.loads(d["sources"] or "[]")
            except Exception:
                d["sources"] = []
            d["sparse"] = bool(d["sparse"])
            out.append(d)
        return out


def append_chat_message(session_id: int, role: str, content: str,
                         sources: list | None = None, sparse: bool = False) -> None:
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO kb_chat_messages (session_id, role, content, sources, sparse, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, _json.dumps(sources or [], ensure_ascii=False), 1 if sparse else 0, now),
        )
        conn.execute(
            "UPDATE kb_chat_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
