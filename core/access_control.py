"""Opt-in, single-tenant local session authentication and server-side roles.

This is a localhost-only profile, NOT a multi-tenant or remote-access solution.
User credentials are scrypt salted and the browser holds only an HttpOnly cookie.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import sqlite3
import time
from pathlib import Path
from contextvars import ContextVar
from typing import Literal

from pydantic import BaseModel, Field


AUTH_DB_PATH = Path(__file__).resolve().parents[1] / "output" / "auth.sqlite3"
WORKSPACE_ROOT = Path(__file__).resolve().parents[1] / "output" / "workspaces"
_ACTIVE_WORKSPACE: ContextVar[str | None] = ContextVar("ajan_workspace", default=None)
WORKSPACE_PATTERN = re.compile(r"[a-z][a-z0-9_-]{2,39}\Z")
SESSION_SECONDS = 8 * 3600
SESSION_COOKIE = "ajan_session"
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5
Role = Literal["ADMIN", "DESIGNER", "OPERATOR"]


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


def mode() -> str:
    configured = os.getenv("AJAN_HALI_AUTH_MODE", "local").lower().strip()
    if configured not in {"local", "session", "workspace"}:
        raise RuntimeError("AJAN_HALI_AUTH_MODE must be local, session or workspace.")
    return configured


def is_loopback_client(host: str | None) -> bool:
    if host == "testclient":  # FastAPI TestClient, never a network peer
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def is_local_host_header(header: str) -> bool:
    # Prevent DNS rebinding via unexpected Host headers. Ports are explicit.
    return bool(re.fullmatch(r"(?:localhost|127\.0\.0\.1|\[::1\]|testserver)(?::\d{1,5})?", header.lower()))


def connection() -> sqlite3.Connection:
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(AUTH_DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout = 15000")
    db.execute("""CREATE TABLE IF NOT EXISTS workspaces (
        workspace_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY COLLATE NOCASE,
        salt BLOB NOT NULL,
        password_hash BLOB NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('ADMIN','DESIGNER','OPERATOR')),
        disabled INTEGER NOT NULL DEFAULT 0
    )""")
    # Upgrade old single-device accounts without assigning them to a company.
    if "workspace_id" not in {row["name"] for row in db.execute("PRAGMA table_info(users)")}:
        db.execute("ALTER TABLE users ADD COLUMN workspace_id TEXT")
    db.execute("""CREATE TABLE IF NOT EXISTS sessions (
        token_sha256 TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        csrf_token TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        FOREIGN KEY (username) REFERENCES users(username)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS login_failures (
        subject TEXT PRIMARY KEY,
        attempts INTEGER NOT NULL,
        started_at INTEGER NOT NULL,
        blocked_until INTEGER NOT NULL DEFAULT 0
    )""")
    return db


def _login_subject(username: str) -> str:
    # Do not persist the supplied username; store a deterministic digest.
    return hashlib.sha256(username.strip().casefold().encode("utf-8")).hexdigest()


def login_retry_after(username: str) -> int:
    """Return remaining lockout seconds, using the persistent SQLite store."""
    db = connection()
    try:
        row = db.execute("SELECT blocked_until FROM login_failures WHERE subject=?",
                         (_login_subject(username),)).fetchone()
    finally:
        db.close()
    return max(0, row["blocked_until"] - int(time.time())) if row else 0


def record_failed_login(username: str) -> int:
    """Atomically count failed attempts; applies equally to known/unknown users."""
    now = int(time.time())
    subject = _login_subject(username)
    db = connection()
    try:
        with db:
            db.execute("DELETE FROM login_failures WHERE blocked_until < ? AND started_at < ?",
                       (now, now - LOGIN_WINDOW_SECONDS))
            row = db.execute("SELECT attempts, started_at, blocked_until FROM login_failures WHERE subject=?",
                             (subject,)).fetchone()
            if row and row["blocked_until"] > now:
                return row["blocked_until"] - now
            attempts = (row["attempts"] if row and row["started_at"] > now - LOGIN_WINDOW_SECONDS else 0) + 1
            blocked_until = now + LOGIN_WINDOW_SECONDS if attempts >= LOGIN_MAX_FAILURES else 0
            db.execute("""INSERT INTO login_failures (subject, attempts, started_at, blocked_until)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(subject) DO UPDATE SET attempts=excluded.attempts,
                started_at=excluded.started_at, blocked_until=excluded.blocked_until""",
                (subject, attempts, row["started_at"] if row and
                 row["started_at"] > now - LOGIN_WINDOW_SECONDS else now, blocked_until))
            return max(0, blocked_until - now)
    finally:
        db.close()


def clear_login_failures(username: str) -> None:
    db = connection()
    try:
        with db:
            db.execute("DELETE FROM login_failures WHERE subject=?", (_login_subject(username),))
    finally:
        db.close()


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


def create_workspace(workspace_id: str, display_name: str) -> None:
    """Provision a company explicitly. Never auto-map legacy data or users."""
    if not WORKSPACE_PATTERN.fullmatch(workspace_id):
        raise ValueError("Workspace ID must be 3-40 lowercase letters, digits, _ or -, starting with a letter.")
    if not 2 <= len(display_name.strip()) <= 150:
        raise ValueError("Workspace name must contain 2-150 characters.")
    db = connection()
    try:
        with db:
            db.execute("INSERT INTO workspaces(workspace_id,display_name) VALUES (?,?)",
                       (workspace_id, display_name.strip()))
    except sqlite3.IntegrityError as error:
        raise ValueError("Workspace already exists.") from error
    finally:
        db.close()


def workspace_directory() -> Path:
    """Get the exact authenticated company's folder; never resolve a client selector."""
    if mode() != "workspace":
        raise RuntimeError("Workspace storage requires workspace mode.")
    workspace_id = _ACTIVE_WORKSPACE.get()
    if not workspace_id or not WORKSPACE_PATTERN.fullmatch(workspace_id):
        raise RuntimeError("No authenticated workspace context.")
    root = WORKSPACE_ROOT
    if root.is_symlink():
        raise RuntimeError("Workspace root cannot be a symbolic link.")
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise RuntimeError("Workspace root cannot be a symbolic link.")
    directory = root / workspace_id
    if directory.is_symlink():
        raise RuntimeError("Workspace folder cannot be a symbolic link.")
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink() or directory.resolve().parent != root.resolve():
        raise RuntimeError("Invalid workspace storage path.")
    return directory


def set_workspace_context(workspace_id: str):
    """Middleware-only binding. This is NOT an authorization API."""
    if not WORKSPACE_PATTERN.fullmatch(workspace_id):
        raise RuntimeError("Invalid workspace ID from authenticated session.")
    return _ACTIVE_WORKSPACE.set(workspace_id)


def clear_workspace_context(token) -> None:
    _ACTIVE_WORKSPACE.reset(token)


def create_user(username: str, password: str, role: Role,
                workspace_id: str | None = None) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", username):
        raise ValueError("Username must be 3–64 letters, digits, _ or -.")
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Password must have 12–1024 characters.")
    if role not in {"ADMIN", "DESIGNER", "OPERATOR"}:
        raise ValueError("Invalid role.")
    if workspace_id is not None and not WORKSPACE_PATTERN.fullmatch(workspace_id):
        raise ValueError("Invalid workspace ID.")
    salt = secrets.token_bytes(16)
    digest = _password_hash(password, salt)
    db = connection()
    try:
        with db:
            if workspace_id is not None and db.execute(
                    "SELECT 1 FROM workspaces WHERE workspace_id=? AND enabled=1",
                    (workspace_id,)).fetchone() is None:
                raise ValueError("Workspace not found or disabled.")
            db.execute("INSERT INTO users (username,salt,password_hash,role,workspace_id) VALUES (?,?,?,?,?)",
                       (username, salt, digest, role, workspace_id))
    except sqlite3.IntegrityError as error:
        raise ValueError("User already exists.") from error
    finally:
        db.close()


def disable_user(username: str) -> None:
    db = connection()
    try:
        with db:
            if db.execute("UPDATE users SET disabled=1 WHERE username=?", (username,)).rowcount != 1:
                raise ValueError("Unknown user.")
            db.execute("DELETE FROM sessions WHERE username=?", (username,))
    finally:
        db.close()


def authenticate(username: str, password: str) -> dict | None:
    db = connection()
    try:
        row = db.execute("SELECT * FROM users WHERE username=? AND disabled=0", (username,)).fetchone()
    finally:
        db.close()
    # Compute a dummy hash for unknown users to avoid an easy timing oracle.
    salt = row["salt"] if row else b"\x00" * 16
    expected = row["password_hash"] if row else b"\x00" * 32
    if not hmac.compare_digest(_password_hash(password, salt), expected) or row is None:
        return None
    if mode() == "workspace":
        if not row["workspace_id"] or not workspace_enabled(row["workspace_id"]):
            return None
    elif row["workspace_id"] is not None:
        # A bound workspace account cannot fall back to the legacy global store.
        return None
    return {"username": row["username"], "role": row["role"],
            "workspace_id": row["workspace_id"]}


def workspace_enabled(workspace_id: str) -> bool:
    db = connection()
    try:
        return db.execute("SELECT 1 FROM workspaces WHERE workspace_id=? AND enabled=1",
                          (workspace_id,)).fetchone() is not None
    finally:
        db.close()


def new_session(principal: dict) -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    db = connection()
    try:
        with db:
            db.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
            db.execute("INSERT INTO sessions (token_sha256, username, csrf_token, expires_at) VALUES (?,?,?,?)",
                       (hashlib.sha256(raw_token.encode()).hexdigest(), principal["username"], csrf,
                        int(time.time()) + SESSION_SECONDS))
    finally:
        db.close()
    return raw_token, csrf


def resolve_session(raw_token: str | None) -> dict | None:
    if not raw_token or len(raw_token) > 200:
        return None
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    db = connection()
    try:
        row = db.execute("""SELECT s.username, s.csrf_token, s.expires_at, u.role, u.workspace_id
            FROM sessions s JOIN users u ON u.username=s.username
            WHERE s.token_sha256=? AND u.disabled=0""", (digest,)).fetchone()
    finally:
        db.close()
    if not row or row["expires_at"] <= int(time.time()):
        return None
    if mode() == "workspace":
        if not row["workspace_id"] or not workspace_enabled(row["workspace_id"]):
            return None
    elif row["workspace_id"] is not None:
        return None
    return {"username": row["username"], "role": row["role"],
            "workspace_id": row["workspace_id"], "csrf_token": row["csrf_token"]}


def end_session(raw_token: str | None) -> None:
    if not raw_token:
        return
    db = connection()
    try:
        with db:
            db.execute("DELETE FROM sessions WHERE token_sha256=?",
                       (hashlib.sha256(raw_token.encode()).hexdigest(),))
    finally:
        db.close()


def role_allows(role: str, method: str, path: str) -> bool:
    if method == "GET" and path == "/api/v1/auth/session":
        return True
    if role == "ADMIN":
        return True
    if method in {"GET", "HEAD"}:
        if role == "DESIGNER":
            return True
        return path == "/api/v1/jobs" or path.startswith("/api/v1/jobs/") or path.startswith("/static/")
    if role == "DESIGNER" and method == "POST":
        if path == "/api/v1/analyze" or path == "/api/v1/spectro/import":
            return True
        if re.fullmatch(r"/api/v1/jobs/[A-Za-z0-9_-]{1,80}/(?:quote|reviews|studio/revisions|evidence)", path):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage localhost-only Studio users")
    sub = parser.add_subparsers(dest="action", required=True)
    provision = sub.add_parser("add-workspace")
    provision.add_argument("workspace_id")
    provision.add_argument("display_name")
    add = sub.add_parser("add-user")
    add.add_argument("username")
    add.add_argument("--workspace", dest="workspace_id")
    add.add_argument("--role", choices=("ADMIN", "DESIGNER", "OPERATOR"), required=True)
    disabled = sub.add_parser("disable-user")
    disabled.add_argument("username")
    args = parser.parse_args()
    if args.action == "add-workspace":
        create_workspace(args.workspace_id, args.display_name)
        print(f"Workspace created: {args.workspace_id}")
    elif args.action == "disable-user":
        disable_user(args.username)
        print("User disabled and sessions revoked.")
    else:
        if mode() == "workspace" and not args.workspace_id:
            parser.error("Workspace mode requires --workspace when creating users.")
        pw = getpass.getpass("Password (at least 12 characters): ")
        confirm = getpass.getpass("Confirm password: ")
        if pw != confirm:
            parser.error("Passwords do not match.")
        create_user(args.username, pw, args.role, workspace_id=args.workspace_id)
        print(f"Created {args.role} user {args.username}.")


if __name__ == "__main__":
    main()
