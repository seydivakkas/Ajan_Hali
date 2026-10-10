"""Non-blocking analysis requests with durable progress and explicit retry.

Single-server in-process worker: incomplete work is recorded as interrupted
on the next process; input bytes are never silently replayed after a crash.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from PIL import Image

from core import job_runtime
from core.demo_data import mark_demo_result
from core.factory_settings import load_settings
from core.models import LoomConfig, ImagePreprocessingParams
from core.pipeline import CarpetAnalysisPipeline
from core.supplier_catalog import validate_matching_conditions

router = APIRouter()


class QueuedAnalysisPayload(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=100)
    loom_config: LoomConfig
    preprocessing_config: ImagePreprocessingParams


def _root() -> Path:
    # Derived from the authenticated request's ContextVar; never a client ID.
    from api.server import active_output_dir
    return active_output_dir()


@router.post("/api/v1/analyze/jobs", status_code=202, response_model=job_runtime.JobStatus)
async def enqueue_analysis(file: UploadFile = File(...), config: str = Form(...)):
    settings = load_settings()
    if not settings.yarns or (not settings.company_name and not any(y.is_demo for y in settings.yarns)):
        raise HTTPException(422, "Önce gerçek fabrika iplikleri ve şirketi kaydedin.")
    try:
        validate_matching_conditions(settings.yarns)
        payload = QueuedAnalysisPayload.model_validate_json(config)
        cfg, params = payload.loom_config, payload.preprocessing_config
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", payload.idempotency_key):
            raise ValueError("Invalid idempotency key.")
        job_runtime.check_limits(width_cm=cfg.width_cm, length_cm=cfg.length_cm,
                                 reed=cfg.reed_density, pick=cfg.pick_density)
        if params.target_width_px > 1200 or params.target_height_px > 2400:
            raise ValueError("Input target processing resolution too high.")
    except (ValueError, ValidationError) as error:
        raise HTTPException(422, str(error))
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        raise HTTPException(415, "Yalnızca JPG/PNG desteklenir.")
    photo_bytes = await file.read(20 * 1024 * 1024 + 1)
    if not 0 < len(photo_bytes) <= 20 * 1024 * 1024:
        raise HTTPException(413, "Fotoğraf 1 bayt ile 20 MB arasında olmalıdır.")
    try:
        with Image.open(io.BytesIO(photo_bytes)) as photo:
            if photo.format not in {"JPEG", "PNG"} or photo.width * photo.height > 25_000_000:
                raise ValueError("Invalid photo dimensions or format.")
            photo.verify()
    except Exception:
        raise HTTPException(422, "Geçerli JPG/PNG yükleyin (en fazla 25 MP).")

    root = _root()
    digest = hashlib.sha256(photo_bytes + cfg.model_dump_json().encode() +
                            params.model_dump_json().encode() +
                            str(settings.revision).encode() +
                            settings.company_name.encode()).hexdigest()
    try:
        record, created = job_runtime.enqueue(root, payload.idempotency_key, digest)
    except OverflowError:
        raise HTTPException(429, "Analiz iş kuyruğu dolu.", headers={"Retry-After": "5"})
    except ValueError as error:
        raise HTTPException(409, str(error))
    if not created:
        return record

    job_id = record.job_id
    palette = [y.model_dump() for y in settings.yarns]
    revision = settings.revision
    company = settings.company_name

    def process(checkpoint):
        path = root / job_id
        if path.exists() or path.is_symlink():
            raise RuntimeError("New analysis directory unexpectedly already exists.")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
            temporary.write(photo_bytes)
            photo_path = temporary.name
        try:
            worker = CarpetAnalysisPipeline(output_base_dir=str(root), palette=palette)
            result = worker.process(image_input=photo_path, loom_cfg=cfg, params=params,
                                    job_id=job_id, progress_callback=checkpoint,
                                    persist_report=False)
            mark_demo_result(result, settings.yarns)
            result.factory_settings_revision = revision
            result.company_name = company
            job_runtime.check_output(root, job_id)
            checkpoint("COMMIT_REPORT", 98)
            report = root / job_id / "analysis_report.json"
            temp_report = report.with_suffix(".tmp")
            temp_report.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            os.replace(temp_report, report)
        finally:
            os.unlink(photo_path)

    def worker(checkpoint):
        try:
            process(checkpoint)
        except Exception:
            # Never expose any finalized artifacts for incomplete work.
            shutil.rmtree(root / job_id, ignore_errors=True)
            raise

    async def background():
        try:
            await run_in_threadpool(job_runtime.run_bounded, root, job_id, worker)
        except job_runtime.JobCancelled:
            pass
        except Exception:
            logging.exception("Background analysis failed; client gets generic error code.")

    asyncio.create_task(background())
    return record


@router.get("/api/v1/jobs/{job_id}/status", response_model=job_runtime.JobStatus)
def analysis_status(job_id: str):
    if not re.fullmatch(r"JOB-[A-F0-9]{12}", job_id):
        raise HTTPException(404, "İş durumu bulunamadı.")
    status = job_runtime.get_status(_root(), job_id)
    if status is None:
        raise HTTPException(404, "İş durumu bulunamadı.")
    return status


@router.post("/api/v1/jobs/{job_id}/cancel", response_model=job_runtime.JobStatus)
def cancel_analysis(job_id: str):
    if not re.fullmatch(r"JOB-[A-F0-9]{12}", job_id):
        raise HTTPException(404, "İş durumu bulunamadı.")
    result = job_runtime.cancel(_root(), job_id)
    if result is None:
        raise HTTPException(404, "İş durumu bulunamadı.")
    return result
