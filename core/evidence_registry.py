"""Immutable-by-API, revision-bound document evidence ledger.

Recording a document and computing its SHA-256 does NOT verify its physical
contents, device calibration, source authenticity, or manufacturing suitability.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_EVIDENCE_BYTES = 5 * 1024 * 1024
MAX_RECORDS_PER_JOB = 100
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
FiniteLab = Annotated[float, Field(allow_inf_nan=False)]
Category = Literal["COLOR_LAB_SAMPLE", "YARN_LOT", "CAM_VENDOR_REPORT", "LOOM_PROFILE", "CALIBRATION", "REPEAT_TEST"]
_LOCK = threading.Lock()


class ColorObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    target_lab: tuple[Annotated[FiniteLab, Field(ge=0, le=100)],
                      Annotated[FiniteLab, Field(ge=-160, le=160)],
                      Annotated[FiniteLab, Field(ge=-160, le=160)]]
    sample_lab: tuple[Annotated[FiniteLab, Field(ge=0, le=100)],
                      Annotated[FiniteLab, Field(ge=-160, le=160)],
                      Annotated[FiniteLab, Field(ge=-160, le=160)]]
    illuminant: Literal["D65", "D50", "A", "F11"]
    observer: Literal["2", "10"]
    device: str = Field(min_length=2, max_length=120)
    dye_lot: str = Field(min_length=1, max_length=100)
    yarn_code: str = Field(min_length=1, max_length=40)
    measured_on: date
    declared_max_delta_e00: Annotated[FiniteLab, Field(gt=0, le=20)]


class EvidenceSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_report_sha256: Digest
    studio_revision: int | None = Field(default=None, ge=1)
    expected_studio_grid_sha256: Digest | None = None
    kind: Category
    source_reference: str = Field(min_length=3, max_length=500)
    note: str = Field(min_length=3, max_length=1500)
    color_observation: ColorObservation | None = None

    @model_validator(mode="after")
    def coherent_scope(self):
        if (self.studio_revision is None) != (self.expected_studio_grid_sha256 is None):
            raise ValueError("Studio revision and grid hash must be provided together.")
        if (self.kind == "COLOR_LAB_SAMPLE") != (self.color_observation is not None):
            raise ValueError("Only COLOR_LAB_SAMPLE requires a complete color observation.")
        return self


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    job_id: str
    kind: Category
    source_reference: str
    note: str
    submitted_by: str
    submitted_at: datetime
    report_sha256: Digest
    studio_revision: int | None
    studio_grid_sha256: Digest | None
    file_sha256: Digest
    file_bytes: int = Field(gt=0, le=MAX_EVIDENCE_BYTES)
    color_observation: ColorObservation | None
    verification: Literal["RECORDED_NOT_INDEPENDENTLY_VERIFIED"] = "RECORDED_NOT_INDEPENDENTLY_VERIFIED"


def _folder(job_dir: Path) -> Path:
    return job_dir / "evidence"


def list_records(job_dir: Path, *, verify_files: bool = True) -> list[EvidenceRecord]:
    folder = _folder(job_dir)
    if not folder.exists():
        return []
    records = []
    paths = sorted(folder.glob("*.json"))
    if len(paths) > MAX_RECORDS_PER_JOB:
        raise ValueError("Evidence limit exceeded; manual review required.")
    for path in paths:
        if not re.fullmatch(r"[a-f0-9]{32}\.json", path.name) or path.is_symlink():
            raise ValueError("Invalid evidence manifest.")
        record = EvidenceRecord.model_validate_json(path.read_text(encoding="utf-8"))
        if record.evidence_id != path.stem or record.job_id != job_dir.name:
            raise ValueError("Evidence manifest is not bound to this job.")
        if verify_files:
            blob = folder / (record.evidence_id + ".blob")
            if blob.is_symlink() or not blob.is_file():
                raise ValueError("Evidence source document missing.")
            payload = blob.read_bytes()
            if (len(payload) != record.file_bytes or
                    hashlib.sha256(payload).hexdigest() != record.file_sha256):
                raise ValueError("Evidence source document integrity mismatch.")
        records.append(record)
    return records


def record_evidence(job_dir: Path, submission: EvidenceSubmission, content: bytes, *,
                    real_report_sha256: str, studio_grid_sha256: str | None,
                    submitted_by: str) -> EvidenceRecord:
    if not 0 < len(content) <= MAX_EVIDENCE_BYTES:
        raise ValueError("Evidence document must be between 1 byte and 5 MB.")
    if submission.expected_report_sha256 != real_report_sha256:
        raise ValueError("Report changed; refresh the preflight source hash.")
    if submission.expected_studio_grid_sha256 != studio_grid_sha256:
        raise ValueError("Studio revision hash mismatch.")
    # Unauthenticated local-mode submissions are explicitly labelled as such.
    record = EvidenceRecord(
        evidence_id=uuid.uuid4().hex, job_id=job_dir.name, kind=submission.kind,
        source_reference=submission.source_reference, note=submission.note,
        submitted_by=submitted_by,
        submitted_at=datetime.now(timezone.utc),
        report_sha256=real_report_sha256, studio_revision=submission.studio_revision,
        studio_grid_sha256=studio_grid_sha256,
        file_sha256=hashlib.sha256(content).hexdigest(), file_bytes=len(content),
        color_observation=submission.color_observation,
    )
    with _LOCK:
        existing = list_records(job_dir)
        if len(existing) >= MAX_RECORDS_PER_JOB:
            raise ValueError("Maximum 100 evidence documents per job.")
        folder = _folder(job_dir)
        folder.mkdir(parents=True, exist_ok=True)
        blob_path = folder / (record.evidence_id + ".blob")
        manifest_path = folder / (record.evidence_id + ".json")
        try:
            with blob_path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            with manifest_path.open("x", encoding="utf-8") as handle:
                handle.write(record.model_dump_json(indent=2))
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            # An incomplete pair is not made visible; no existing record is changed.
            manifest_path.unlink(missing_ok=True)
            blob_path.unlink(missing_ok=True)
            raise
    return record


def find_record(job_dir: Path, evidence_id: str) -> tuple[EvidenceRecord, Path]:
    if not re.fullmatch(r"[a-f0-9]{32}", evidence_id):
        raise ValueError("Invalid evidence ID.")
    records = list_records(job_dir)
    record = next((entry for entry in records if entry.evidence_id == evidence_id), None)
    if record is None:
        raise FileNotFoundError("Evidence record not found.")
    return record, _folder(job_dir) / (evidence_id + ".blob")


def records_for_scope(records: list[EvidenceRecord], report_sha256: str,
                      studio_revision: int | None, grid_sha256: str | None) -> list[EvidenceRecord]:
    return [entry for entry in records if entry.report_sha256 == report_sha256
            and entry.studio_revision == studio_revision and entry.studio_grid_sha256 == grid_sha256]
