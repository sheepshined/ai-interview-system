"""User-scoped application tracking store."""
import json
import hashlib
import os
import sqlite3
from datetime import datetime

import config

_DB_PATH = os.environ.get("APPLICATION_DB_PATH", os.path.join(config.BASE_DIR, "applications.db"))
STAGES = ("saved", "applied", "screening", "interview", "offer", "rejected", "withdrawn")


class JdVersionConflict(ValueError):
    pass


def _connect():
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path=None):
    global _DB_PATH
    if path:
        _DB_PATH = path
    os.makedirs(os.path.dirname(os.path.abspath(_DB_PATH)), exist_ok=True)
    with _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
            company TEXT NOT NULL, role_title TEXT NOT NULL, job_url TEXT NOT NULL DEFAULT '',
            jd_text TEXT NOT NULL DEFAULT '', stage TEXT NOT NULL DEFAULT 'saved',
            resume_id INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_app_user_updated ON applications(username, archived, updated_at);
        CREATE TABLE IF NOT EXISTS application_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER NOT NULL,
            username TEXT NOT NULL, kind TEXT NOT NULL, stage TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '', report_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS application_outcomes (
            application_id INTEGER PRIMARY KEY, username TEXT NOT NULL,
            result TEXT NOT NULL DEFAULT '', feedback TEXT NOT NULL DEFAULT '',
            reflection TEXT NOT NULL DEFAULT '', next_steps TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL,
            FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS application_interviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER NOT NULL,
            username TEXT NOT NULL, report_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
            FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS application_jd_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER NOT NULL,
            username TEXT NOT NULL, version INTEGER NOT NULL,
            source_url TEXT NOT NULL, jd_text TEXT NOT NULL, content_hash TEXT NOT NULL,
            source TEXT NOT NULL, created_at TEXT NOT NULL, restored_from INTEGER,
            UNIQUE(application_id, version),
            FOREIGN KEY(application_id) REFERENCES applications(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_jd_owned ON application_jd_versions(username, application_id, version);
        """)
        conn.execute("BEGIN IMMEDIATE")
        # Backfill once without replacing the existing application or its history.
        rows = conn.execute("""SELECT * FROM applications a
            WHERE (a.jd_text<>'' OR a.job_url<>'') AND NOT EXISTS
            (SELECT 1 FROM application_jd_versions v WHERE v.application_id=a.id)""").fetchall()
        for row in rows:
            _append_jd_version(conn, row, row["jd_text"], row["job_url"], row["updated_at"], "migration")


def _latest_jd(conn, username, application_id):
    return conn.execute("""SELECT * FROM application_jd_versions
        WHERE username=? AND application_id=? ORDER BY version DESC LIMIT 1""",
        (username, application_id)).fetchone()


def _jd_metadata(row):
    return {key: row[key] for key in ("id", "version", "source_url", "content_hash", "source", "created_at", "restored_from")} if row else None


def _append_jd_version(conn, current, text, url, now, source="manual", restored_from=None):
    latest = _latest_jd(conn, current["username"], current["id"])
    if latest and latest["jd_text"] == text and latest["source_url"] == url and restored_from is None:
        return False
    if not latest and not text and not url:
        return False
    version = latest["version"] + 1 if latest else 1
    conn.execute("""INSERT INTO application_jd_versions
        (application_id,username,version,source_url,jd_text,content_hash,source,created_at,restored_from)
        VALUES(?,?,?,?,?,?,?,?,?)""", (current["id"], current["username"], version, url, text,
        hashlib.sha256(text.encode("utf-8")).hexdigest(), source, now, restored_from))
    return True


def _decode(row):
    if not row:
        return None
    item = dict(row)
    item["archived"] = bool(item["archived"])
    item["events"] = []
    item["interviews"] = []
    item["outcome"] = None
    return item


def get(username, application_id):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM applications WHERE username=? AND id=?", (username, application_id)).fetchone()
        item = _decode(row)
        if not item:
            return None
        item["jd_version"] = _jd_metadata(_latest_jd(conn, username, application_id))
        item["events"] = [dict(r) for r in conn.execute(
            "SELECT * FROM application_events WHERE username=? AND application_id=? ORDER BY id", (username, application_id))]
        item["interviews"] = [dict(r) for r in conn.execute(
            "SELECT report_id,created_at FROM application_interviews WHERE username=? AND application_id=? ORDER BY id", (username, application_id))]
        outcome = conn.execute("SELECT * FROM application_outcomes WHERE username=? AND application_id=?", (username, application_id)).fetchone()
        if outcome:
            item["outcome"] = dict(outcome)
            item["outcome"]["tags"] = json.loads(item["outcome"]["tags"])
        return item


def list_all(username, include_archived=False):
    sql = "SELECT * FROM applications WHERE username=?"
    if not include_archived:
        sql += " AND archived=0"
    sql += " ORDER BY updated_at DESC, id DESC"
    with _connect() as conn:
        rows = conn.execute(sql, (username,)).fetchall()
    return [get(username, row["id"]) for row in rows]


def create(username, data):
    now = datetime.now().isoformat(timespec="seconds")
    stage = data.get("stage", "saved")
    with _connect() as conn:
        cur = conn.execute("INSERT INTO applications(username,company,role_title,job_url,jd_text,stage,resume_id,created_at,updated_at,applied_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (username, data["company"], data["role_title"], data.get("job_url", ""), data.get("jd_text", ""), stage, data.get("resume_id"), now, now, now if stage == "applied" else ""))
        aid = cur.lastrowid
        _append_jd_version(conn, {"id": aid, "username": username}, data.get("jd_text", ""), data.get("job_url", ""), now)
        conn.execute("INSERT INTO application_events(application_id,username,kind,stage,note,created_at) VALUES(?,?,?,?,?,?)", (aid, username, "created", stage, "创建投递档案", now))
    return get(username, aid)


def update(username, application_id, data):
    now = datetime.now().isoformat(timespec="seconds")
    fields = ("company", "role_title", "job_url", "jd_text", "resume_id", "stage")
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM applications WHERE username=? AND id=? AND archived=0", (username, application_id)).fetchone()
        if not current:
            return None
        latest = _latest_jd(conn, username, application_id)
        if "expected_jd_version" in data:
            _check_jd_version(latest, data["expected_jd_version"])
        values = {key: data.get(key, current[key]) for key in fields}
        jd_changed = values["jd_text"] != current["jd_text"] or values["job_url"] != current["job_url"]
        if jd_changed and data.get("expected_jd_version") is None:
            raise JdVersionConflict("修改 JD 正文或来源必须携带当前版本号，请刷新档案后重试")
        conn.execute("UPDATE applications SET company=?,role_title=?,job_url=?,jd_text=?,resume_id=?,stage=?,updated_at=?,applied_at=CASE WHEN ?='applied' AND applied_at='' THEN ? ELSE applied_at END WHERE username=? AND id=?",
            (*[values[k] for k in fields], now, values["stage"], now, username, application_id))
        _append_jd_version(conn, current, values["jd_text"], values["job_url"], now)
        if values["stage"] != current["stage"]:
            conn.execute("INSERT INTO application_events(application_id,username,kind,stage,note,created_at) VALUES(?,?,?,?,?,?)", (application_id, username, "stage_changed", values["stage"], f"阶段更新为 {values['stage']}", now))
    return get(username, application_id)


def _check_jd_version(latest, expected_version):
    if (latest["version"] if latest else 0) != expected_version:
        raise JdVersionConflict("JD 已在其他页面更新，请刷新版本后重试；当前草稿未保存")


def list_jd_versions(username, application_id):
    with _connect() as conn:
        if not conn.execute("SELECT 1 FROM applications WHERE username=? AND id=?", (username, application_id)).fetchone():
            return None
        return [_jd_metadata(row) for row in conn.execute("""SELECT * FROM application_jd_versions
            WHERE username=? AND application_id=? ORDER BY version DESC""", (username, application_id))]


def get_jd_version(username, application_id, version_id):
    with _connect() as conn:
        row = conn.execute("""SELECT * FROM application_jd_versions
            WHERE username=? AND application_id=? AND id=?""", (username, application_id, version_id)).fetchone()
        return dict(row) if row else None


def save_jd(username, application_id, text, url, expected_version, restore_id=None):
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM applications WHERE username=? AND id=? AND archived=0", (username, application_id)).fetchone()
        if not current:
            return None
        _check_jd_version(_latest_jd(conn, username, application_id), expected_version)
        if restore_id is not None:
            restored = conn.execute("""SELECT * FROM application_jd_versions
                WHERE username=? AND application_id=? AND id=?""", (username, application_id, restore_id)).fetchone()
            if not restored:
                return None
            text, url = restored["jd_text"], restored["source_url"]
        changed = _append_jd_version(conn, current, text, url, now, "restore" if restore_id else "manual", restore_id)
        if changed:
            conn.execute("UPDATE applications SET jd_text=?,job_url=?,updated_at=? WHERE id=? AND username=?", (text, url, now, application_id, username))
            conn.execute("""INSERT INTO application_events(application_id,username,kind,stage,note,created_at)
                VALUES(?,?,?,?,?,?)""", (application_id, username, "jd_restored" if restore_id else "jd_updated", current["stage"],
                "恢复 JD 历史版本" if restore_id else "更新 JD 内容与来源", now))
    return get(username, application_id)


def add_event(username, application_id, note, kind="note", report_id=""):
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        row = conn.execute("SELECT stage FROM applications WHERE id=? AND username=?", (application_id, username)).fetchone()
        if not row:
            return None
        conn.execute("INSERT INTO application_events(application_id,username,kind,stage,note,report_id,created_at) VALUES(?,?,?,?,?,?,?)", (application_id, username, kind, row["stage"], note, report_id, now))
        conn.execute("UPDATE applications SET updated_at=? WHERE id=? AND username=?", (now, application_id, username))
    return get(username, application_id)


def save_outcome(username, application_id, data):
    if not get(username, application_id):
        return None
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute("INSERT INTO application_outcomes(application_id,username,result,feedback,reflection,next_steps,tags,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(application_id) DO UPDATE SET result=excluded.result,feedback=excluded.feedback,reflection=excluded.reflection,next_steps=excluded.next_steps,tags=excluded.tags,updated_at=excluded.updated_at",
            (application_id, username, data.get("result", ""), data.get("feedback", ""), data.get("reflection", ""), data.get("next_steps", ""), json.dumps(data.get("tags", []), ensure_ascii=False), now))
    return get(username, application_id)


def attach_interview(username, application_id, report_id):
    report_id = str(report_id or "").strip()
    if not report_id:
        return False
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM applications WHERE id=? AND username=?", (application_id, username)).fetchone():
            return False
        existing = conn.execute(
            "SELECT application_id, username FROM application_interviews WHERE report_id=?",
            (report_id,),
        ).fetchone()
        if existing:
            # 报告关联是幂等的，但一个报告不能跨档案或跨用户重挂。
            return bool(
                existing["application_id"] == application_id
                and existing["username"] == username
            )
        conn.execute("INSERT INTO application_interviews(application_id,username,report_id,created_at) VALUES(?,?,?,?)", (application_id, username, report_id, now))
        conn.execute("UPDATE applications SET updated_at=? WHERE id=? AND username=?", (now, application_id, username))
    return True


def archive(username, application_id):
    with _connect() as conn:
        cur = conn.execute("UPDATE applications SET archived=1,updated_at=? WHERE username=? AND id=?", (datetime.now().isoformat(timespec="seconds"), username, application_id))
    return cur.rowcount > 0
