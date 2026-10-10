"""Durable, content-free per-workspace security audit events.

This is an application audit trail, not an immutable or independently signed
ledger. Never record credentials, cookies, CSRF tokens, request bodies or query
strings. An operator with OS write access can tamper with the SQLite database.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    event_id: str
    timestamp: str
    username: str
    role: str
    method: str
    resource: str
    phase: str
    status: int | None


def _db_path(jobs_dir: Path) -> Path:
    if jobs_dir.is_symlink():
        raise ValueError("Unsafe audit workspace directory.")
    jobs_dir.mkdir(parents=True, exist_ok=True)
    return jobs_dir / "reviews.sqlite3"


def write_event(*, jobs_dir: Path, username: str, role: str, method: str,
                path: str, phase: str, status: int | None = None) -> str:
    """Append a bounded event. No free-form HTTP content is persisted."""
    if phase not in {"ATTEMPT", "RESULT"} or method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError("Invalid audit action.")
    if status is not None and not 100 <= status <= 599:
        raise ValueError("Invalid HTTP status.")
    # Only the route path, never any query or header data. Job IDs remain
    # visible for authorized operator audit/reconstruction.
    if len(path) > 256 or not re.fullmatch(r"/[A-Za-z0-9_./-]*", path):
        raise ValueError("Invalid audit path.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", username):
        raise ValueError("Invalid audit username.")
    if role not in {"ADMIN", "DESIGNER", "OPERATOR"}:
        raise ValueError("Invalid role.")
    event_id = uuid.uuid4().hex
    db = sqlite3.connect(_db_path(jobs_dir), timeout=15)
    try:
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS security_audit (
                event_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
                username TEXT NOT NULL, role TEXT NOT NULL,
                method TEXT NOT NULL, resource TEXT NOT NULL,
                phase TEXT NOT NULL, status INTEGER
            )""")
            db.execute("""INSERT INTO security_audit
                (event_id,timestamp,username,role,method,resource,phase,status)
                VALUES(?,?,?,?,?,?,?,?)""",
                (event_id, datetime.now(timezone.utc).isoformat(), username,
                 role, method, path, phase, status))
    finally:
        db.close()
    return event_id


def list_events(jobs_dir: Path, *, limit: int = 100) -> list[AuditEvent]:
    """Used by local admin tooling; never exposed in an unauthenticated API."""
    if not 1 <= limit <= 1000:
        raise ValueError("Audit limit must be 1-1000.")
    path = jobs_dir / "reviews.sqlite3"
    if not path.is_file() or path.is_symlink():
        return []
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        db.row_factory = sqlite3.Row
        try:
            rows = db.execute("""SELECT event_id,timestamp,username,role,method,
                                resource,phase,status FROM security_audit
                                ORDER BY rowid DESC LIMIT ?""", (limit,)).fetchall()
        except sqlite3.OperationalError as error:
            if "no such table" in str(error):
                return []
            raise
    finally:
        db.close()
    return [AuditEvent.model_validate(dict(row)) for row in rows]
