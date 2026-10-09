"""Offline, encrypted workspace snapshots for locally managed installations.

Passphrase-protected AES-256-GCM (scrypt KDF). Restore is only to a *new*,
provisioned, empty workspace directory. No overwrite or remote/API restore.
The application server must be stopped during backup and restore.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core import access_control as auth

MAGIC = b"AJAN-HALI-ENCRYPTED-BACKUP-V1\n"
AAD = b"ajan-hali:workspace-backup:v1"
SCHEMA = "ajan-hali-workspace-backup-v1"
MAX_ENTRIES = 15000
MAX_TOTAL_SIZE = 256 * 1024 * 1024
MAX_ARCHIVE_SIZE = 192 * 1024 * 1024


def _validate_id(workspace_id: str) -> None:
    if not auth.WORKSPACE_PATTERN.fullmatch(workspace_id):
        raise ValueError("Invalid workspace ID.")
    if not auth.workspace_enabled(workspace_id):
        raise ValueError("Workspace is not provisioned or has been disabled.")


def _workspace_path(workspace_id: str) -> Path:
    _validate_id(workspace_id)
    root = auth.WORKSPACE_ROOT
    if root.is_symlink():
        raise ValueError("Workspace root cannot be a symlink.")
    root.mkdir(parents=True, exist_ok=True)
    target = root / workspace_id
    if target.is_symlink() or target.resolve().parent != root.resolve():
        raise ValueError("Unsafe workspace path.")
    return target


def _safe_relname(value: str) -> bool:
    if not value or "\\" in value or "\x00" in value or value.startswith("/"):
        return False
    parts = value.split("/")
    return (all(re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", part) and
                part not in {".", ".."} for part in parts)
            and (value in {"factory_settings.json", "supplier_catalog.json"} or
                 (len(parts) >= 2 and parts[0] == "jobs")))


def _scan(workspace: Path) -> list[tuple[str, Path]]:
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("Workspace directory is absent or unsafe.")
    output: list[tuple[str, Path]] = []
    total = 0
    for path in workspace.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlinks are not permitted inside workspace backups.")
        if path.is_dir():
            continue
        rel = path.relative_to(workspace).as_posix()
        if not _safe_relname(rel) or not path.is_file():
            raise ValueError("Unexpected workspace file: " + rel)
        size = path.stat().st_size
        total += size
        if total > MAX_TOTAL_SIZE or size > MAX_TOTAL_SIZE:
            raise ValueError("Workspace exceeds 256 MiB offline backup limit.")
        output.append((rel, path))
        if len(output) > MAX_ENTRIES:
            raise ValueError("Workspace exceeds file count limit.")
    if not output:
        raise ValueError("Workspace has no data to back up.")
    return sorted(output)


def _derive(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or not 12 <= len(passphrase) <= 1024:
        raise ValueError("Backup passphrase must be 12-1024 characters.")
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=2**15, r=8, p=1,
                          dklen=32, maxmem=128 * 1024 * 1024)


def _manifest_bytes(workspace_id: str, records: list[dict]) -> bytes:
    return json.dumps({
        "schema": SCHEMA, "workspace_id": workspace_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": records,
    }, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def build_encrypted_snapshot(workspace_id: str, passphrase: str) -> bytes:
    """Build a bounded encrypted snapshot. Never captures the shared auth DB."""
    workspace = _workspace_path(workspace_id)
    entries = _scan(workspace)
    payloads: list[tuple[str, bytes]] = []
    records = []
    for name, path in entries:
        content = path.read_bytes()
        records.append({"name": name, "size": len(content),
                        "sha256": hashlib.sha256(content).hexdigest()})
        payloads.append((name, content))
    # Detect file changes while the snapshot was being assembled. The operator
    # must still stop the API; this is not an online consistent-snapshot system.
    if _scan(workspace) != entries:
        raise ValueError("Workspace files changed during backup.")
    for record, (_, path) in zip(records, entries):
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Workspace files changed during backup.")
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipout:
        zipout.writestr("manifest.json", _manifest_bytes(workspace_id, records))
        for name, content in payloads:
            zipout.writestr("data/" + name, content)
    plain = data.getvalue()
    if len(plain) > MAX_ARCHIVE_SIZE:
        raise ValueError("Encrypted archive would exceed 192 MiB limit.")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    sealed = AESGCM(_derive(passphrase, salt)).encrypt(nonce, plain, AAD)
    return MAGIC + salt + nonce + sealed


def backup_to_file(workspace_id: str, destination: Path, passphrase: str) -> Path:
    """Create a new encrypted file; refuses overwrite (including symlinks)."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Backup destination already exists.")
    if not destination.parent.is_dir():
        raise ValueError("Backup destination directory does not exist.")
    if destination.resolve().is_relative_to(auth.WORKSPACE_ROOT.resolve()):
        raise ValueError("Backups must be stored outside the live workspaces tree.")
    content = build_encrypted_snapshot(workspace_id, passphrase)
    # Exclusive create; owner-only permissions where supported.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def _read_snapshot(blob: bytes, passphrase: str, workspace_id: str) -> list[tuple[str, bytes]]:
    if (not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 16 + 12 + 16 or
            len(blob) > MAX_ARCHIVE_SIZE + len(MAGIC) + 16 + 12 + 16 + 1024):
        raise ValueError("Unrecognized or oversized encrypted backup.")
    salt_start = len(MAGIC)
    salt = blob[salt_start:salt_start + 16]
    nonce = blob[salt_start + 16:salt_start + 28]
    try:
        plain = AESGCM(_derive(passphrase, salt)).decrypt(nonce, blob[salt_start + 28:], AAD)
    except InvalidTag as error:
        raise ValueError("Wrong passphrase or tampered backup.") from error
    try:
        with zipfile.ZipFile(io.BytesIO(plain), "r") as archive:
            members = archive.namelist()
            if len(members) > MAX_ENTRIES + 1 or len(set(members)) != len(members):
                raise ValueError("Duplicate or oversized archive.")
            manifest = json.loads(archive.read("manifest.json", pwd=None))
            if (manifest.get("schema") != SCHEMA or
                    manifest.get("workspace_id") != workspace_id or
                    not isinstance(manifest.get("files"), list)):
                raise ValueError("Backup belongs to a different workspace or schema.")
            records = manifest["files"]
            if not records or len(records) > MAX_ENTRIES:
                raise ValueError("Invalid manifest length.")
            seen = set()
            payloads = []
            total = 0
            expected_names = {"manifest.json"}
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("Invalid backup manifest entry.")
                name, size, digest = record.get("name"), record.get("size"), record.get("sha256")
                if (not isinstance(name, str) or not _safe_relname(name) or
                        name.casefold() in seen or not isinstance(size, int) or
                        isinstance(size, bool) or not 0 <= size <= MAX_TOTAL_SIZE or
                        not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                    raise ValueError("Unsafe backup manifest.")
                seen.add(name.casefold())
                total += size
                if total > MAX_TOTAL_SIZE:
                    raise ValueError("Backup extraction exceeds 256 MiB.")
                zip_name = "data/" + name
                expected_names.add(zip_name)
                info = archive.getinfo(zip_name)
                if info.is_dir() or info.file_size != size:
                    raise ValueError("Backup manifest size mismatch.")
                with archive.open(info) as f:
                    content = f.read(size + 1)
                if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
                    raise ValueError("Backup file digest mismatch.")
                payloads.append((name, content))
            if set(members) != expected_names:
                raise ValueError("Backup contains unlisted file entries.")
            return payloads
    except (zipfile.BadZipFile, KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Corrupt backup container.") from error


def restore_new_workspace(workspace_id: str, source: Path, passphrase: str) -> Path:
    """Offline restore to a *new* provisioned workspace, with no overwrite."""
    target = _workspace_path(workspace_id)
    if target.exists() or target.is_symlink():
        raise FileExistsError("Target workspace already exists; restore will never overwrite.")
    source = Path(source)
    if not source.is_file() or source.is_symlink():
        raise ValueError("Backup file not found or unsafe.")
    with source.open("rb") as handle:
        blob = handle.read(MAX_ARCHIVE_SIZE + len(MAGIC) + 16 + 12 + 16 + 1025)
    payloads = _read_snapshot(blob, passphrase, workspace_id)
    staging = Path(tempfile.mkdtemp(prefix=".restore-", dir=target.parent))
    try:
        for name, content in payloads:
            relative = PurePosixPath(name)
            dest = staging.joinpath(*relative.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as handle:
                handle.write(content)
        # Offline SQLite validity check; any corrupt database blocks the restore.
        for sqlite_file in staging.rglob("*.sqlite3"):
            with sqlite3.connect(f"file:{sqlite_file}?mode=ro", uri=True) as db:
                result = db.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise ValueError("SQLite integrity failure in backup.")
        if target.exists():
            raise FileExistsError("Target workspace appeared during restore.")
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline encrypted workspace backup/restore")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("backup", "restore"):
        part = sub.add_parser(name)
        part.add_argument("--workspace", required=True)
        part.add_argument("--file", type=Path, required=True)
        part.add_argument("--service-stopped", action="store_true",
                          help="Confirm all Ajan Hali processes are stopped")
    args = parser.parse_args()
    if not args.service_stopped:
        parser.error("Stop all Ajan Hali processes and pass --service-stopped.")
    if auth.mode() != "workspace":
        parser.error("AJAN_HALI_AUTH_MODE=workspace is required.")
    password = getpass.getpass("Backup passphrase: ")
    if args.command == "backup":
        if password != getpass.getpass("Confirm passphrase: "):
            parser.error("Passphrases do not match.")
        result = backup_to_file(args.workspace, args.file, password)
    else:
        result = restore_new_workspace(args.workspace, args.file, password)
    print(f"{args.command} complete: {result}")


if __name__ == "__main__":
    main()
