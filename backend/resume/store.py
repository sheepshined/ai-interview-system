"""User-isolated resume persistence and evidence validation."""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import config

_DB_PATH = ""
CONTENT_FIELDS = (
    "name", "phone", "email", "location", "summary",
    "skills", "experience", "projects", "education",
)
SCALAR_FIELDS = {field for field in CONTENT_FIELDS if field != "skills"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str = "") -> None:
    global _DB_PATH
    _DB_PATH = path or config.RESUME_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(_DB_PATH)), exist_ok=True)
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'upload',
                file_name TEXT NOT NULL DEFAULT '',
                parsed_data TEXT NOT NULL,
                content_json TEXT NOT NULL DEFAULT '{}',
                evidence_json TEXT NOT NULL DEFAULT '[]',
                parse_status TEXT NOT NULL DEFAULT 'text_ready',
                is_master INTEGER NOT NULL DEFAULT 0,
                parent_resume_id INTEGER,
                import_review TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_resumes_user_updated "
            "ON resumes(username, updated_at DESC)"
        )


def _clean_content(content: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field in CONTENT_FIELDS:
        value = content.get(field, [] if field == "skills" else "")
        if field == "skills":
            if not isinstance(value, list):
                raise ValueError("skills 必须是文本数组")
            values = []
            for item in value:
                if not isinstance(item, str):
                    raise ValueError("skills 必须是文本数组")
                item = item.strip()
                if item and item not in values:
                    values.append(item[:80])
            out[field] = values[:100]
        else:
            if not isinstance(value, str):
                raise ValueError(f"{field} 必须是文本")
            out[field] = value.strip()[:8000]
    return out


def build_evidence(raw_text: str, content: Dict[str, Any]) -> List[dict]:
    """Build only evidence that can be revalidated byte-for-byte."""
    evidence: List[dict] = []
    clean = _clean_content(content)
    for field in SCALAR_FIELDS:
        value = clean[field]
        if value and value in raw_text:
            evidence.append({"path": f"/{field}", "value": value, "evidence": value})
    for index, value in enumerate(clean["skills"]):
        if value in raw_text:
            evidence.append({
                "path": f"/skills/{index}", "value": value, "evidence": value,
            })
    return evidence


def validate_evidence(raw_text: str, items: Iterable[dict]) -> List[dict]:
    valid: List[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        value = item.get("value")
        evidence = item.get("evidence")
        if not all(isinstance(value_, str) for value_ in (path, value, evidence)):
            continue
        if not (path.startswith("/") and evidence in raw_text and value in evidence):
            continue
        valid.append({"path": path, "value": value, "evidence": evidence})
    return valid


def merge_empty(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Fill empty known fields without overwriting user edits or unknown fields."""
    merged = dict(existing)
    clean = _clean_content(incoming)
    for field in CONTENT_FIELDS:
        current = merged.get(field)
        if current in (None, "", []):
            merged[field] = clean[field]
    return merged


def _decode(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["content"] = json.loads(item.pop("content_json") or "{}")
    item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
    item["import_review"] = json.loads(item["import_review"] or "{}")
    item["is_master"] = bool(item["is_master"])
    return item


def create_resume(username: str, raw_text: str, content: Dict[str, Any], *,
                  title: str = "", source: str = "upload", file_name: str = "") -> dict:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        raise ValueError("简历原文不能为空")
    clean = _clean_content(content)
    evidence = build_evidence(raw_text, clean)
    now = _now()
    display_title = (title or clean.get("name") or file_name or "未命名简历").strip()[:120]
    with _connect() as conn:
        has_master = conn.execute(
            "SELECT 1 FROM resumes WHERE username=? AND is_master=1", (username,)
        ).fetchone()
        cur = conn.execute(
            """INSERT INTO resumes(
                username,title,source,file_name,parsed_data,content_json,evidence_json,
                parse_status,is_master,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (username, display_title, source, file_name, raw_text,
             json.dumps(clean, ensure_ascii=False), json.dumps(evidence, ensure_ascii=False),
             "classified", 0 if has_master else 1, now, now),
        )
        resume_id = int(cur.lastrowid)
    return get_resume(username, resume_id)


def get_resume(username: str, resume_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM resumes WHERE id=? AND username=?", (resume_id, username)
        ).fetchone()
    return _decode(row) if row else None


def latest_resume(username: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM resumes WHERE username=? ORDER BY is_master DESC, updated_at DESC LIMIT 1",
            (username,),
        ).fetchone()
    return _decode(row) if row else None


def list_resumes(username: str) -> List[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM resumes WHERE username=? ORDER BY updated_at DESC", (username,)
        ).fetchall()
    return [_decode(row) for row in rows]


def update_content(username: str, resume_id: int, content: Dict[str, Any], title: str = "") -> Optional[dict]:
    current = get_resume(username, resume_id)
    if not current:
        return None
    clean = _clean_content(content)
    evidence = build_evidence(current["parsed_data"], clean)
    with _connect() as conn:
        conn.execute(
            "UPDATE resumes SET title=?, content_json=?, evidence_json=?, "
            "parse_status='classified', import_review='{}', updated_at=? "
            "WHERE id=? AND username=?",
            ((title or current["title"]).strip()[:120], json.dumps(clean, ensure_ascii=False),
             json.dumps(evidence, ensure_ascii=False), _now(), resume_id, username),
        )
    return get_resume(username, resume_id)


def confirm_import(username: str, resume_id: int) -> Optional[dict]:
    current = get_resume(username, resume_id)
    if not current:
        return None
    review = {
        "version": 1,
        "raw_text_sha256": hashlib.sha256(current["parsed_data"].encode("utf-8")).hexdigest(),
        "confirmed_at": _now(),
    }
    with _connect() as conn:
        conn.execute(
            "UPDATE resumes SET parse_status='reviewed', import_review=?, updated_at=? "
            "WHERE id=? AND username=?",
            (json.dumps(review, ensure_ascii=False), _now(), resume_id, username),
        )
    return get_resume(username, resume_id)


def evidence_audit(resume: dict) -> List[dict]:
    content = resume.get("content") or {}
    evidence_paths = {item["path"] for item in resume.get("evidence") or []}
    checks = []
    for field in ("name", "email", "phone", "skills", "experience", "projects", "education"):
        value = content.get(field)
        present = bool(value)
        prefix = f"/{field}"
        supported = any(path == prefix or path.startswith(prefix + "/") for path in evidence_paths)
        status = "present" if present and supported else "review" if present else "unknown"
        checks.append({"field": field, "status": status})
    checks.append({"field": "layout", "status": "unknown",
                   "note": "纯文本解析无法可靠判断分栏、字号与视觉层级"})
    return checks
