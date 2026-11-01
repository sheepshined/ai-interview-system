"""db.py — assistant.db 的表与 CRUD (AGENT_PLAN §5.12 / §5.7)。

约定照 knowledge.py 的既有风格 (knowledge.py:29-32,117-122):
  - 每函数 _connect() 即开即用, 不跨线程复用连接;
  - sqlite3.connect(timeout=10) 的 busy timeout 与现有 REST 端点同强度;
  - WAL 让抽屉的高频读不被偶发写阻塞。
删除会话必须三处级联 (表 + 消息 + checkpointer thread), 最后一级在 server 层做,
这里只负责两张表, 见 delete_session 的注释。
"""
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

import config

_DB_PATH = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = "") -> None:
    """建表并记录库路径。server 启动与测试 conftest 各调一次。"""
    global _DB_PATH
    _DB_PATH = db_path or config.ASSISTANT_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(_DB_PATH)), exist_ok=True)
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assistant_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '新对话',
                summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_asst_sessions_user "
            "ON assistant_sessions(username)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assistant_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_trace TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                compacted INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        columns = {
            row["name"] for row in conn.execute(
                "PRAGMA table_info(assistant_messages)"
            ).fetchall()
        }
        if "compacted" not in columns:
            conn.execute(
                "ALTER TABLE assistant_messages "
                "ADD COLUMN compacted INTEGER NOT NULL DEFAULT 0"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_asst_messages_session "
            "ON assistant_messages(session_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS handoff_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                focus TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '',
                operation_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                consumed_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_handoff_intents_user "
            "ON handoff_intents(username, consumed_at)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS handoff_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                report_id TEXT NOT NULL DEFAULT '',
                focus TEXT NOT NULL DEFAULT '',
                avg_score REAL NOT NULL DEFAULT 0,
                role_title TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                acked INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_handoff_events_user "
            "ON handoff_events(username, acked)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assistant_settings (
                username TEXT PRIMARY KEY,
                auto_accept_level TEXT NOT NULL DEFAULT 'read_auto',
                memory_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                kind TEXT NOT NULL,
                origin TEXT NOT NULL,
                text TEXT NOT NULL,
                importance INTEGER NOT NULL DEFAULT 6,
                source_ref TEXT NOT NULL DEFAULT '',
                trigger_keywords TEXT NOT NULL DEFAULT '',
                ts TEXT NOT NULL,
                last_recalled_at TEXT,
                recall_count INTEGER NOT NULL DEFAULT 0,
                superseded INTEGER NOT NULL DEFAULT 0,
                supersession_key TEXT NOT NULL DEFAULT '',
                cooldown_s INTEGER NOT NULL DEFAULT 86400,
                expires_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_asst_memory_user "
            "ON agent_memory(username)"
        )


# ============================================================
# 会话
# ============================================================

def create_session(username: str, title: str = "新对话") -> dict:
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO assistant_sessions(username, title, created_at, updated_at) "
            "VALUES (?,?,?,?)",
            (username, title, now, now),
        )
        sid = cur.lastrowid
    return {"id": sid, "username": username, "title": title,
            "summary": "", "created_at": now, "updated_at": now}


def list_sessions(username: str) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, username, title, summary, created_at, updated_at "
            "FROM assistant_sessions WHERE username=? ORDER BY updated_at DESC",
            (username,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_session(username: str, session_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, title, summary, created_at, updated_at "
            "FROM assistant_sessions WHERE id=? AND username=?",
            (session_id, username),
        ).fetchone()
    return dict(row) if row else None


def rename_session(username: str, session_id: int, title: str) -> bool:
    title = (title or "").strip()
    if not title:
        return False
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE assistant_sessions SET title=?, updated_at=? "
            "WHERE id=? AND username=?",
            (title[:60], _now_iso(), session_id, username),
        )
    return cur.rowcount > 0


def touch_session(session_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE assistant_sessions SET updated_at=? WHERE id=?",
            (_now_iso(), session_id),
        )


def delete_session(username: str, session_id: int) -> bool:
    """只删两张表。checkpointer thread 的级联在 server 层做
    (它持有 saver 实例), 见 server.py 的 DELETE /api/assistant/sessions/{id}。"""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM assistant_messages WHERE session_id=? AND session_id IN "
            "(SELECT id FROM assistant_sessions WHERE username=?)",
            (session_id, username),
        )
        cur = conn.execute(
            "DELETE FROM assistant_sessions WHERE id=? AND username=?",
            (session_id, username),
        )
    return cur.rowcount > 0


# ============================================================
# 消息
# ============================================================

def append_message(session_id: int, role: str, content: str,
                   tool_trace: Optional[list] = None) -> int:
    import json
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO assistant_messages(session_id, role, content, tool_trace, "
            "created_at) VALUES (?,?,?,?,?)",
            (session_id, role, content,
             json.dumps(tool_trace or [], ensure_ascii=False), _now_iso()),
        )
        return cur.lastrowid


def list_messages(username: str, session_id: int) -> List[dict]:
    import json
    if not get_session(username, session_id):
        return []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, session_id, role, content, tool_trace, created_at "
            "FROM assistant_messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["tool_trace"] = json.loads(d["tool_trace"] or "[]")
        except ValueError:
            d["tool_trace"] = []
        out.append(d)
    return out


def list_context_messages(username: str, session_id: int) -> List[dict]:
    """Return only messages that still belong in the model context."""
    import json
    if not get_session(username, session_id):
        return []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, session_id, role, content, tool_trace, created_at "
            "FROM assistant_messages WHERE session_id=? AND compacted=0 ORDER BY id",
            (session_id,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["tool_trace"] = json.loads(item["tool_trace"] or "[]")
        except ValueError:
            item["tool_trace"] = []
        out.append(item)
    return out


def count_messages(session_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM assistant_messages WHERE session_id=?",
            (session_id,),
        ).fetchone()
    return int(row["n"])


def set_session_summary(session_id: int, summary: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE assistant_sessions SET summary=? WHERE id=?",
            (summary, session_id),
        )


def compact_messages(username: str, session_id: int, message_ids: List[int],
                     summary: str) -> int:
    """Atomically store a summary and retire selected rows from model context."""
    if not message_ids or not get_session(username, session_id):
        return 0
    marks = ",".join("?" for _ in message_ids)
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE assistant_messages SET compacted=1 "
            f"WHERE session_id=? AND compacted=0 AND id IN ({marks})",
            [session_id, *message_ids],
        )
        conn.execute(
            "UPDATE assistant_sessions SET summary=?, updated_at=? "
            "WHERE id=? AND username=?",
            (summary, now, session_id, username),
        )
    return cur.rowcount


# ============================================================
# 设置
# ============================================================

VALID_LEVELS = ("all_confirm", "read_auto", "exec_only")


def get_settings(username: str) -> dict:
    with _connect() as conn:
        row = conn.execute(
            "SELECT auto_accept_level, memory_enabled FROM assistant_settings "
            "WHERE username=?",
            (username,),
        ).fetchone()
    if row:
        return {"auto_accept_level": row["auto_accept_level"],
                "memory_enabled": bool(row["memory_enabled"])}
    return {"auto_accept_level": "read_auto", "memory_enabled": True}


def put_settings(username: str, auto_accept_level: Optional[str] = None,
                 memory_enabled: Optional[bool] = None) -> dict:
    cur_s = get_settings(username)
    level = auto_accept_level or cur_s["auto_accept_level"]
    if level not in VALID_LEVELS:
        raise ValueError(f"非法 auto_accept_level: {level}")
    mem = cur_s["memory_enabled"] if memory_enabled is None else bool(memory_enabled)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO assistant_settings(username, auto_accept_level, "
            "memory_enabled, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(username) DO UPDATE SET auto_accept_level=excluded."
            "auto_accept_level, memory_enabled=excluded.memory_enabled, "
            "updated_at=excluded.updated_at",
            (username, level, int(mem), _now_iso()),
        )
    return {"auto_accept_level": level, "memory_enabled": mem}


# ============================================================
# 长期记忆 (AGENT_PLAN §5.7)
# ============================================================

def insert_memory(username: str, kind: str, origin: str, text: str,
                  importance: int, source_ref: str = "",
                  trigger_keywords: str = "", supersession_key: str = "",
                  expires_at: Optional[str] = None) -> int:
    with _connect() as conn:
        if supersession_key:
            # 冲突走 supersede 就地取代, 绝不并存矛盾事实 (context-handbook:495-504)
            conn.execute(
                "UPDATE agent_memory SET superseded=1 WHERE username=? "
                "AND supersession_key=? AND superseded=0",
                (username, supersession_key),
            )
        cur = conn.execute(
            "INSERT INTO agent_memory(username, kind, origin, text, importance, "
            "source_ref, trigger_keywords, ts, supersession_key, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (username, kind, origin, text, importance, source_ref,
             trigger_keywords, _now_iso(), supersession_key, expires_at),
        )
        return cur.lastrowid


def find_active_by_key(username: str, supersession_key: str) -> Optional[dict]:
    if not supersession_key:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM agent_memory WHERE username=? AND supersession_key=? "
            "AND superseded=0 LIMIT 1",
            (username, supersession_key),
        ).fetchone()
    return dict(row) if row else None


def list_memories(username: str, kind: str = "", include_superseded: bool = False,
                  limit: int = 200) -> List[dict]:
    sql = "SELECT * FROM agent_memory WHERE username=?"
    args: list = [username]
    if not include_superseded:
        sql += " AND superseded=0"
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with _connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def get_memory(username: str, memory_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM agent_memory WHERE id=? AND username=?",
            (memory_id, username),
        ).fetchone()
    return dict(row) if row else None


def delete_memory(username: str, memory_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM agent_memory WHERE id=? AND username=?",
            (memory_id, username),
        )
    return cur.rowcount > 0


def clear_memories(username: str) -> int:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM agent_memory WHERE username=?", (username,))
    return cur.rowcount


def mark_recalled(memory_ids: List[int]) -> None:
    if not memory_ids:
        return
    now = _now_iso()
    marks = ",".join("?" for _ in memory_ids)
    with _connect() as conn:
        conn.execute(
            f"UPDATE agent_memory SET last_recalled_at=?, "
            f"recall_count=recall_count+1 WHERE id IN ({marks})",
            [now, *memory_ids],
        )


# ============================================================
# handoff: 统筹助手 -> 面试引擎 -> 结果回流 (双 runtime 协作)
# ============================================================

def create_handoff_intent(username: str, focus: str, role: str,
                          operation_id: str) -> int:
    """助手侧面试提案被用户批准后登记, 等面试引擎下次 config 时消费。"""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO handoff_intents (username, focus, role, operation_id,"
            " created_at) VALUES (?,?,?,?,?)",
            (username, focus, role, operation_id, _now_iso()),
        )
        return int(cur.lastrowid)


def consume_handoff_intent(username: str, ttl_seconds: int = 1800) -> Optional[dict]:
    """面试引擎 config 时取走最新一条未消费且未过期的意图 (单次消费)。"""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM handoff_intents WHERE username=? AND consumed_at=''"
            " ORDER BY id DESC LIMIT 1",
            (username,),
        ).fetchone()
        if not row:
            return None
        created = datetime.fromisoformat(row["created_at"])
        age = (datetime.now(timezone.utc) - created).total_seconds()
        if age > ttl_seconds:
            return None
        conn.execute(
            "UPDATE handoff_intents SET consumed_at=? WHERE id=?",
            (_now_iso(), row["id"]),
        )
        return dict(row)


def create_handoff_event(username: str, report_id: str, focus: str,
                         avg_score: float, role_title: str) -> int:
    """面试引擎完成报告后回流事件, 等助手下一轮注入并简报。"""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO handoff_events (username, report_id, focus, avg_score,"
            " role_title, created_at) VALUES (?,?,?,?,?,?)",
            (username, report_id, focus, avg_score, role_title, _now_iso()),
        )
        return int(cur.lastrowid)


def drain_handoff_events(username: str) -> List[dict]:
    """取出并标记已读 (ack), 保证同一事件只注入一次。"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM handoff_events WHERE username=? AND acked=0"
            " ORDER BY id ASC",
            (username,),
        ).fetchall()
        if rows:
            conn.execute(
                f"UPDATE handoff_events SET acked=1 WHERE id IN "
                f"({','.join('?' for _ in rows)})",
                [row["id"] for row in rows],
            )
        return [dict(row) for row in rows]
