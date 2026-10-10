"""Bounded single-process analysis worker registry with durable SQLite state.

Persisted work is accounted for across restarts; this is NOT a distributed
broker. Interrupted QUEUED/RUNNING work becomes FAILED, and explicit reupload
with a new idempotency key is required. No automatic silent retry.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

MAX_QUEUE = 4
MAX_CELLS = 4_000_000
MAX_OUTPUT_BYTES = 512 * 1024 * 1024
MAX_RUNTIME_SECONDS = 180
_RUN_SLOT = threading.BoundedSemaphore(value=1)
_RECOVERY_LOCK = threading.RLock()
_RECOVERED: set[Path] = set()
_TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


class JobCancelled(Exception):
    pass


class JobStatus(BaseModel):
    job_id: str
    state: str
    stage: str
    percent: int
    error_code: str | None = None
    created_at: str
    updated_at: str
    cancel_requested: bool = False


def _database(root: Path) -> sqlite3.Connection:
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("Unsafe analysis registry root.")
    db = sqlite3.connect(root / "analysis_queue.sqlite3", timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("""CREATE TABLE IF NOT EXISTS analysis_jobs (
        job_id TEXT PRIMARY KEY,
        idempotency_key TEXT NOT NULL UNIQUE,
        payload_sha256 TEXT NOT NULL,
        state TEXT NOT NULL, stage TEXT NOT NULL, percent INTEGER NOT NULL,
        error_code TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    return db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def recover_interrupted(root: Path, *, force: bool = False) -> int:
    """First access in this process, or explicit recovery at server startup."""
    canonical = root.resolve()
    with _RECOVERY_LOCK:
        if canonical in _RECOVERED and not force:
            return 0
        db = _database(root)
        try:
            with db:
                cursor = db.execute("""UPDATE analysis_jobs
                    SET state='FAILED', stage='RESTART_INTERRUPTED', percent=0,
                        error_code='INTERRUPTED_ON_RESTART', updated_at=?
                    WHERE state IN ('QUEUED','RUNNING','CANCEL_REQUESTED')""", (_now(),))
                count = cursor.rowcount
        finally:
            db.close()
        _RECOVERED.add(canonical)
        return count


def enqueue(root: Path, key: str, payload_sha: str) -> tuple[JobStatus, bool]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", key):
        raise ValueError("Idempotency key must be 8-100 ASCII letters/digits/_/-")
    if not re.fullmatch(r"[0-9a-f]{64}", payload_sha):
        raise ValueError("Invalid request digest.")
    recover_interrupted(root)
    db = _database(root)
    try:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT * FROM analysis_jobs WHERE idempotency_key=?", (key,)).fetchone()
        if previous:
            db.commit()
            if previous["payload_sha256"] != payload_sha:
                raise ValueError("Idempotency key reused with different input.")
            return _parse(previous), False
        active = db.execute("""SELECT COUNT(*) FROM analysis_jobs
            WHERE state IN ('QUEUED','RUNNING','CANCEL_REQUESTED')""").fetchone()[0]
        if active >= MAX_QUEUE:
            db.rollback()
            raise OverflowError("Analysis queue is full.")
        identifier = "JOB-" + uuid.uuid4().hex[:12].upper()
        stamp = _now()
        db.execute("""INSERT INTO analysis_jobs
            (job_id,idempotency_key,payload_sha256,state,stage,percent,created_at,updated_at)
            VALUES (?,?,?,'QUEUED','WAITING',0,?,?)""", (identifier,key,payload_sha,stamp,stamp))
        db.commit()
        return get_status(root,identifier), True
    finally:
        db.close()


def _parse(row: sqlite3.Row) -> JobStatus:
    return JobStatus(job_id=row["job_id"], state=row["state"],
        stage=row["stage"], percent=row["percent"], error_code=row["error_code"],
        created_at=row["created_at"], updated_at=row["updated_at"],
        cancel_requested=bool(row["cancel_requested"]))


def get_status(root: Path, job_id: str) -> JobStatus | None:
    recover_interrupted(root)
    db = _database(root)
    try:
        row = db.execute("SELECT * FROM analysis_jobs WHERE job_id=?", (job_id,)).fetchone()
        return _parse(row) if row else None
    finally:
        db.close()


def _update(root: Path, job_id: str, *, state: str, stage: str,
            percent: int, error_code: str | None = None) -> None:
    db = _database(root)
    try:
        with db:
            db.execute("""UPDATE analysis_jobs SET state=?,stage=?,percent=?,
                error_code=?,updated_at=? WHERE job_id=?""",
                (state,stage,percent,error_code,_now(),job_id))
    finally:
        db.close()


def _finish_if_active(root: Path, job_id: str) -> None:
    """Atomically resolve the race between final completion and cancellation."""
    db = _database(root)
    try:
        with db:
            updated = db.execute("""UPDATE analysis_jobs SET
                state='SUCCEEDED',stage='COMPLETED',percent=100,
                error_code=NULL,updated_at=?
                WHERE job_id=? AND state='RUNNING' AND cancel_requested=0""",
                (_now(),job_id)).rowcount
            if updated != 1:
                raise JobCancelled("Cancellation won the completion race.")
    finally:
        db.close()


def cancel(root: Path, job_id: str) -> JobStatus | None:
    db = _database(root)
    try:
        with db:
            row = db.execute("SELECT * FROM analysis_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                return None
            if row["state"] not in _TERMINAL:
                db.execute("""UPDATE analysis_jobs SET
                    cancel_requested=1,
                    state=CASE WHEN state='QUEUED' THEN 'CANCELLED' ELSE 'CANCEL_REQUESTED' END,
                    stage='CANCELLATION_REQUESTED', updated_at=?
                    WHERE job_id=?""", (_now(),job_id))
    finally:
        db.close()
    return get_status(root,job_id)


def run_bounded(root: Path, job_id: str, work) -> None:
    """Worker runs in a thread; cooperative stage cancellation and deadline."""
    with _RUN_SLOT:
        status = get_status(root,job_id)
        if status is None or status.cancel_requested or status.state=="CANCELLED":
            return
        started = time.monotonic()
        _update(root,job_id,state="RUNNING",stage="STARTING",percent=1)

        def checkpoint(stage: str, percent: int) -> None:
            current = get_status(root,job_id)
            if current is None or current.cancel_requested:
                raise JobCancelled("Cancellation was requested.")
            if time.monotonic()-started > MAX_RUNTIME_SECONDS:
                raise TimeoutError("Cooperative runtime deadline exceeded.")
            if (root / job_id).exists():
                check_output(root, job_id)
            _update(root,job_id,state="RUNNING",stage=stage,percent=percent)

        try:
            work(checkpoint)
            checkpoint("FINALIZING", 99)
            _finish_if_active(root, job_id)
        except JobCancelled:
            import shutil
            shutil.rmtree(root / job_id, ignore_errors=True)
            _update(root,job_id,state="CANCELLED",stage="CANCELLED",percent=0,
                    error_code="USER_CANCELLED")
            raise
        except Exception as error:
            import shutil
            shutil.rmtree(root / job_id, ignore_errors=True)
            _update(root,job_id,state="FAILED",stage="FAILED",percent=0,
                    error_code="COOPERATIVE_DEADLINE" if isinstance(error, TimeoutError)
                    else "RESOURCE_LIMIT" if isinstance(error, ValueError)
                    else "PROCESSING_FAILED")
            raise


def check_limits(*, width_cm: float, length_cm: float, reed: int, pick: int) -> int:
    from core.pattern_analysis import compute_loom_grid_dimensions
    import math
    if not all(math.isfinite(x) for x in (width_cm,length_cm)):
        raise ValueError("Loom dimensions must be finite.")
    cells_x,cells_y,_ = compute_loom_grid_dimensions(width_cm,length_cm,reed,pick)
    cells = cells_x*cells_y
    if cells < 1 or cells > MAX_CELLS:
        raise ValueError("Grid exceeds the configured limit of four million cells.")
    return cells


def check_output(root: Path, job_id: str) -> None:
    folder=root/job_id
    total=0
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlink in analysis output.")
        if path.is_file():
            total += path.stat().st_size
            if total > MAX_OUTPUT_BYTES:
                raise ValueError("Analysis output exceeds 512 MiB limit.")
