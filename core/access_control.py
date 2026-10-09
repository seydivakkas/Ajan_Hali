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
from typing import Literal

from pydantic import BaseModel, Field


AUTH_DB_PATH = Path(__file__).resolve().parents[1] / "output" / "auth.sqlite3"
SESSION_SECONDS = 8 * 3600
SESSION_COOKIE = "ajan_session"
Role = Literal["ADMIN", "DESIGNER", "OPERATOR"]


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


def mode() -> str:
    configured = os.getenv("AJAN_HALI_AUTH_MODE", "local").lower().strip()
    if configured not in {"local", "session"}:
        raise RuntimeError("AJAN_HALI_AUTH_MODE must be local or session.")
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
    db.execute("""CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY COLLATE NOCASE,
        salt BLOB NOT NULL,
        password_hash BLOB NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('ADMIN','DESIGNER','OPERATOR')),
        disabled INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS sessions (
        token_sha256 TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        csrf_token TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        FOREIGN KEY (username) REFERENCES users(username)
    )""")
    return db


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


def create_user(username: str, password: str, role: Role) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", username):
        raise ValueError("Username must be 3–64 letters, digits, _ or -.")
    if len(password) < 12 or len(password) > 1024:
        raise ValueError("Password must have 12–1024 characters.")
    if role not in {"ADMIN", "DESIGNER", "OPERATOR"}:
        raise ValueError("Invalid role.")
    salt = secrets.token_bytes(16)
    digest = _password_hash(password, salt)
    db = connection()
    try:
        with db:
            db.execute("INSERT INTO users (username,salt,password_hash,role) VALUES (?,?,?,?)",
                       (username, salt, digest, role))
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
    return {"username": row["username"], "role": row["role"]}


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
        row = db.execute("""SELECT s.username, s.csrf_token, s.expires_at, u.role
            FROM sessions s JOIN users u ON u.username=s.username
            WHERE s.token_sha256=? AND u.disabled=0""", (digest,)).fetchone()
    finally:
        db.close()
    if not row or row["expires_at"] <= int(time.time()):
        return None
    return {"username": row["username"], "role": row["role"], "csrf_token": row["csrf_token"]}


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
    if role == "ADMIN":
        return True
    if method in {"GET", "HEAD"}:
        if role == "DESIGNER":
            return True
        return path == "/api/v1/jobs" or path.startswith("/api/v1/jobs/") or path.startswith("/static/")
    if role == "DESIGNER" and method == "POST":
        if path == "/api/v1/analyze" or path == "/api/v1/spectro/import":
            return True
        if re.fullmatch(r"/api/v1/jobs/[A-Za-z0-9_-]{1,80}/(?:quote|reviews|studio/revisions)", path):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage localhost-only Studio users")
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("add-user")
    add.add_argument("username")
    add.add_argument("--role", choices=("ADMIN", "DESIGNER", "OPERATOR"), required=True)
    disabled = sub.add_parser("disable-user")
    disabled.add_argument("username")
    args = parser.parse_args()
    if args.action == "disable-user":
        disable_user(args.username)
        print("User disabled and sessions revoked.")
    else:
        pw = getpass.getpass("Password (at least 12 characters): ")
        confirm = getpass.getpass("Confirm password: ")
        if pw != confirm:
            parser.error("Passwords do not match.")
        create_user(args.username, pw, args.role)
        print(f"Created {args.role} user {args.username}.")


if __name__ == "__main__":
    main()
