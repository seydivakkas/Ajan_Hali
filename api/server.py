"""
FastAPI REST API Server for Carpet CAD & Yarn Optimization Platform
"""
import os
import shutil
import tempfile
from typing import Optional
import json
import re
from pathlib import Path
from pydantic import ValidationError, BaseModel, Field
from typing import Literal
import sqlite3
import hashlib
import secrets
import logging
from datetime import datetime, timezone
import uuid
import asyncio
import io
from starlette.concurrency import run_in_threadpool
from PIL import Image
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.models import LoomConfig, ImagePreprocessingParams, AnalysisPipelineResult
from core.pipeline import CarpetAnalysisPipeline
from core.factory_settings import FactorySettings, load_settings, save_settings
from core.demo_data import change_demo_inventory, mark_demo_result
from core.supplier_catalog import SupplierCatalog, append_catalog, catalog_view, validate_matching_conditions
from core.preflight import PreflightResult, evaluate_preflight
from core import evidence_registry as evidence
from core import access_control as auth
from core import tls_policy
from core import security_audit
from core import job_runtime

app = FastAPI(
    title="Industrial Carpet AI: Competitor Photo to CAD & Yarn Recipe API",
    version="1.0.0",
    description="End-to-end Computer Vision, CIEDE2000 Color Matching, CAD DXF & Loom CAM Engine"
)

# The service remains loopback-only; opt-in local session auth is not remote deployment.
# CORS alone cannot prevent cross-site form submissions, so also reject requests
# that carry an untrusted browser Origin (including mutations).
TRUSTED_BROWSER_ORIGINS = (
    "http://127.0.0.1:8001",
    "http://localhost:8001",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(*TRUSTED_BROWSER_ORIGINS,
                   *([tls_policy.public_origin()] if tls_policy.deployment_mode() == "direct-tls" else [])),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def enforce_local_browser_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if tls_policy.deployment_mode() == "direct-tls":
        if not tls_policy.origin_allowed(origin):
            return JSONResponse(status_code=403, content={"detail": "Untrusted HTTPS Origin."})
    elif origin is not None and origin not in TRUSTED_BROWSER_ORIGINS:
        return JSONResponse(status_code=403, content={"detail": "Bu yerel API başka bir web kökeninden kullanılamaz."})
    return await call_next(request)


@app.middleware("http")
async def protect_local_data(request: Request, call_next):
    # Network peer and Host both matter: Host filtering defends DNS rebinding,
    # the peer check defends accidental --host 0.0.0.0 exposure.
    direct_tls = tls_policy.deployment_mode() == "direct-tls"
    if direct_tls:
        if auth.mode() != "workspace":
            return JSONResponse(status_code=403, content={"detail": "TLS requires workspace authentication."})
        if request.url.scheme != "https":
            return JSONResponse(status_code=403, content={"detail": "HTTPS required."})
        if not tls_policy.host_allowed(request.headers.get("host", "")):
            return JSONResponse(status_code=403, content={"detail": "Untrusted TLS Host."})
        # This profile terminates TLS directly. Do not trust forwarding headers.
        if any(k.startswith("x-forwarded-") or k == "forwarded" for k in request.headers):
            return JSONResponse(status_code=403, content={"detail": "Forwarded headers are not trusted."})
    else:
        if not auth.is_loopback_client(request.client.host if request.client else None):
            return JSONResponse(status_code=403, content={"detail": "API yalnızca yerel bilgisayarda kullanılabilir."})
        if not auth.is_local_host_header(request.headers.get("host", "")):
            return JSONResponse(status_code=403, content={"detail": "Güvenilmeyen Host başlığı."})

    async def response_with_security():
        result = await call_next(request)
        if (auth.mode() == "workspace" and getattr(request.state, "principal", None)
                and getattr(request.state, "audit_enabled", False)):
            # Explicit RESULT paired with a durable ATTEMPT. No request secrets
            # or query strings are ever retained in the audit database.
            security_audit.write_event(
                jobs_dir=active_output_dir(), username=request.state.principal["username"],
                role=request.state.principal["role"], method=request.method,
                path=request.url.path, phase="RESULT", status=result.status_code)
        if direct_tls:
            result.headers["Strict-Transport-Security"] = "max-age=31536000"
            result.headers["X-Content-Type-Options"] = "nosniff"
            result.headers["Referrer-Policy"] = "no-referrer"
            if request.url.path.startswith(("/api/", "/static/")):
                result.headers["Cache-Control"] = "no-store"
        return result

    if auth.mode() == "local":
        return await response_with_security()

    path = request.url.path
    if request.method == "OPTIONS" or path in {"/", "/api/v1/health", "/api/v1/auth/login",
                                               "/openapi.json", "/docs", "/redoc"} or path.startswith("/assets/"):
        return await response_with_security()

    principal = auth.resolve_session(request.cookies.get(auth.SESSION_COOKIE))
    if principal is None:
        return JSONResponse(status_code=401, content={"detail": "Oturum açılması gerekiyor."})
    request.state.principal = principal

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not secrets.compare_digest(csrf, principal["csrf_token"]):
            return JSONResponse(status_code=403, content={"detail": "CSRF doğrulaması başarısız."})

    permitted = path == "/api/v1/auth/logout" or auth.role_allows(
        principal["role"], request.method, path)
    if auth.mode() == "workspace":
        workspace_id = principal.get("workspace_id")
        if not workspace_id:
            return JSONResponse(status_code=403, content={"detail": "Firma alanı atanmamış."})
        token = auth.set_workspace_context(workspace_id)
        try:
            # Audit successful and denied sensitive operations within the same
            # workspace. Invalid paths cannot inject free-form log contents.
            auditable = (request.method in {"POST", "PUT", "PATCH", "DELETE"}
                         or "/download/" in path or path.startswith("/static/"))
            auditable = auditable and path.startswith(("/api/v1/", "/static/"))
            auditable = auditable and len(path) <= 256 and bool(
                re.fullmatch(r"/[A-Za-z0-9_./-]*", path))
            if auditable:
                security_audit.write_event(jobs_dir=active_output_dir(),
                    username=principal["username"], role=principal["role"],
                    method=request.method, path=path, phase="ATTEMPT")
                request.state.audit_enabled = True
            if not permitted:
                if auditable:
                    security_audit.write_event(jobs_dir=active_output_dir(),
                        username=principal["username"], role=principal["role"],
                        method=request.method, path=path, phase="RESULT", status=403)
                return JSONResponse(status_code=403, content={"detail": "Bu işlem için yetki yok."})
            return await response_with_security()
        finally:
            auth.clear_workspace_context(token)
    if not permitted:
        return JSONResponse(status_code=403, content={"detail": "Bu işlem için yetki yok."})
    return await response_with_security()


# Output directory setup
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
os.makedirs(OUTPUT_DIR, exist_ok=True)


def active_output_dir() -> Path:
    """The request's data root, never selected from HTTP route/query/body."""
    if auth.mode() == "workspace":
        root = auth.workspace_directory() / "jobs"
        if root.is_symlink():
            raise RuntimeError("Workspace job directory cannot be a symlink.")
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink():
            raise RuntimeError("Workspace job directory cannot be a symlink.")
        return root
    return Path(OUTPUT_DIR)


PALETTE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "palette", "factory_palette.json"))



@app.get("/api/v1/health")
def health_check():
    return {
        "status": "online",
        "engine": "Carpet CAD & Yarn Recipe Optimizer v1.0",
        "license": "All Rights Reserved - Seydi Eryılmaz (@seydivakkas)"
    }


@app.get("/api/v1/auth/session")
def auth_session(request: Request):
    if auth.mode() == "local":
        return {"authenticated": True, "username": "local", "role": "ADMIN",
                "csrf_token": None, "mode": "local", "workspace_id": None}
    principal = request.state.principal
    return {"authenticated": True, "username": principal["username"],
            "role": principal["role"], "csrf_token": principal["csrf_token"],
            "mode": auth.mode(), "workspace_id": principal.get("workspace_id")}


@app.post("/api/v1/auth/login")
def auth_login(credentials: auth.LoginPayload, response: Response):
    if auth.mode() == "local":
        raise HTTPException(409, "Yerel oturum doğrulaması etkin değil.")
    retry_after = auth.login_retry_after(credentials.username)
    if retry_after:
        raise HTTPException(429, "Çok fazla hatalı giriş. Daha sonra tekrar deneyin.",
                            headers={"Retry-After": str(retry_after)})
    principal = auth.authenticate(credentials.username, credentials.password)
    if not principal:
        auth.record_failed_login(credentials.username)
        raise HTTPException(401, "Kullanıcı adı veya parola hatalı.")
    auth.clear_login_failures(credentials.username)
    token, csrf = auth.new_session(principal)
    response.set_cookie(auth.SESSION_COOKIE, token, httponly=True, samesite="strict",
                        secure=tls_policy.deployment_mode() == "direct-tls",
                        path="/", max_age=auth.SESSION_SECONDS)
    return {"authenticated": True, "username": principal["username"],
            "role": principal["role"], "csrf_token": csrf,
            "mode": auth.mode(), "workspace_id": principal.get("workspace_id")}


@app.post("/api/v1/auth/logout")
def auth_logout(request: Request, response: Response):
    auth.end_session(request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE, path="/", httponly=True, samesite="strict",
                           secure=tls_policy.deployment_mode() == "direct-tls")
    return {"authenticated": False}


@app.get("/api/v1/palette")
def get_factory_palette():
    return [item.model_dump() for item in load_settings().yarns]


@app.get("/api/v1/settings", response_model=FactorySettings)
def get_settings():
    return load_settings()


@app.put("/api/v1/settings", response_model=FactorySettings)
def put_settings(settings: FactorySettings):
    try:
        return save_settings(settings)
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.get("/api/v1/jobs/demo")
def removed_demo():
    raise HTTPException(410, "Demo veri devre dışı bırakıldı.")


class DemoChange(BaseModel):
    revision: int = Field(ge=0)


@app.post('/api/v1/demo/inventory')
def install_demo_inventory(request: DemoChange):
    try:
        return change_demo_inventory(request.revision)
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.delete('/api/v1/demo/inventory')
def remove_demo_inventory(request: DemoChange):
    try:
        return change_demo_inventory(request.revision, remove=True)
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.delete('/api/v1/demo/jobs')
def remove_demo_jobs():
    removed = 0
    for path in active_output_dir().glob('*/analysis_report.json'):
        try:
            report = AnalysisPipelineResult.model_validate_json(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if report.data_source != 'DEMO_SYNTHETIC':
            continue
        target = job_directory(report.job_id)
        if path.parent.is_symlink() or target != path.parent.resolve():
            continue
        # job_directory verifies the resolved target is directly beneath OUTPUT_DIR.
        shutil.rmtree(target)
        connection = review_connection()
        try:
            with connection:
                connection.execute('DELETE FROM reviews WHERE job_id=?', (report.job_id,))
        finally:
            connection.close()
        removed += 1
    return {'removed': removed}


@app.get('/api/v1/catalog')
def get_supplier_catalog():
    return catalog_view()


@app.post('/api/v1/catalog', status_code=201)
def add_supplier_records(records: SupplierCatalog):
    try:
        return catalog_view(append_catalog(records))
    except ValueError as error:
        raise HTTPException(422, str(error))


@app.post('/api/v1/catalog/import', status_code=201)
async def import_supplier_catalog(file: UploadFile = File(...)):
    content = await file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, 'Katalog dosyası en fazla 2 MB olabilir.')
    try:
        return catalog_view(append_catalog(SupplierCatalog.model_validate_json(content)))
    except ValueError as error:
        raise HTTPException(422, str(error))


def job_directory(job_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id):
        raise HTTPException(400, "Geçersiz analiz kimliği")
    root = active_output_dir().resolve()
    target = (root / job_id).resolve()
    if target.parent != root:
        raise HTTPException(400, "Geçersiz analiz yolu")
    return target


@app.get("/api/v1/jobs")
def list_jobs():
    items = []
    for path in active_output_dir().glob("*/analysis_report.json"):
        try:
            report = AnalysisPipelineResult.model_validate_json(path.read_text(encoding="utf-8"))
            if report.data_source not in {"USER_FACTORY_INPUT", "DEMO_SYNTHETIC"}:
                continue
            if job_directory(report.job_id) != path.parent.resolve():
                continue
            items.append({"job_id": report.job_id, "created_at": report.created_at, "data_source": report.data_source,
                          "dimensions": report.carpet_dimensions_cm,
                          "status": report.audit.status, "cost_tl": report.total_order_cost_tl,
                          "modified": path.stat().st_mtime})
        except (ValueError, OSError, HTTPException):
            continue
    return sorted(items, key=lambda item: item["modified"], reverse=True)[:100]


@app.get("/api/v1/jobs/{job_id}", response_model=AnalysisPipelineResult)
def get_job(job_id: str):
    status = job_runtime.get_status(active_output_dir(), job_id)
    if status is not None and status.state != "SUCCEEDED":
        raise HTTPException(409, "Analiz tamamlanmadı; işin durumunu kontrol edin.")
    path = job_directory(job_id) / "analysis_report.json"
    if not path.is_file():
        raise HTTPException(404, "Analiz bulunamadı")
    try:
        report = AnalysisPipelineResult.model_validate_json(path.read_text(encoding="utf-8"))
        if report.job_id != job_id:
            raise HTTPException(409, "Kaynak rapor kimliği istenen analizle uyuşmuyor.")
        if report.data_source not in {"USER_FACTORY_INPUT", "DEMO_SYNTHETIC"}:
            raise HTTPException(410, "Şirket kaynağı doğrulanmamış eski analiz erişime kapalı.")
        return report
    except ValueError:
        raise HTTPException(409, "Analiz raporu okunamıyor")


@app.post("/api/v1/jobs/{job_id}/quote")
def quote_current_prices(job_id: str):
    from core.yarn_recipe import calculate_yarn_recipe
    result = get_job(job_id)
    settings = load_settings()
    if result.loom_config is None:
        raise HTTPException(409, "Bu analizde üretim parametreleri yok.")
    palette = [y.model_dump() for y in settings.yarns]
    codes = {y["code"] for y in palette}
    missing = [c.palette_code for c in result.color_mappings if c.palette_code not in codes]
    if missing:
        raise HTTPException(409, "Güncel envanterde eksik iplik kodları: " + ", ".join(missing))
    statistics = [{"palette_code": c.palette_code, "yarn_name": c.yarn_name,
                   "area_percentage": c.pixel_count / (result.grid_resolution_cells[0] * result.grid_resolution_cells[1]) * 100}
                  for c in result.color_mappings]
    recipe, summary = calculate_yarn_recipe(result.loom_config, statistics, palette)
    return {"recipe": recipe, "summary": summary, "revision": settings.revision,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "bobbins": sum(r.bobbin_count_required for r in recipe), "source": "DEMO_SYNTHETIC" if any(y.is_demo for y in settings.yarns) or result.data_source == 'DEMO_SYNTHETIC' else "USER_FACTORY_INPUT"}


class DesignReview(BaseModel):
    reviewer: str = Field(min_length=2, max_length=100, pattern=r".*\S.*")
    decision: Literal["DESIGN_ACCEPTED", "CHANGES_REQUESTED"]
    note: str = Field(min_length=3, max_length=2000, pattern=r".*\S.*")


def review_connection():
    connection = sqlite3.connect(str(active_output_dir() / "reviews.sqlite3"))
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, job_id TEXT, created_at TEXT, reviewer TEXT, decision TEXT, note TEXT, report_sha256 TEXT)")
    return connection


@app.get("/api/v1/jobs/{job_id}/reviews")
def get_reviews(job_id: str):
    get_job(job_id)
    connection = review_connection()
    try:
        return [dict(row) for row in connection.execute("SELECT * FROM reviews WHERE job_id=? ORDER BY created_at DESC", (job_id,))]
    finally:
        connection.close()


@app.post("/api/v1/jobs/{job_id}/reviews", status_code=201)
def save_review(job_id: str, review: DesignReview):
    get_job(job_id)
    report = (job_directory(job_id) / "analysis_report.json").read_bytes()
    record = dict(id=uuid.uuid4().hex, job_id=job_id, created_at=datetime.now(timezone.utc).isoformat(),
                  reviewer=review.reviewer.strip(), decision=review.decision, note=review.note.strip(),
                  report_sha256=hashlib.sha256(report).hexdigest())
    connection = review_connection()
    try:
        with connection:
            connection.execute("INSERT INTO reviews VALUES (:id,:job_id,:created_at,:reviewer,:decision,:note,:report_sha256)", record)
    finally:
        connection.close()
    return record


@app.get("/api/v1/jobs/{job_id}/download/{file_type}")
def download_job_artifact(job_id: str, file_type: str):
    """
    Download experimental design/review outputs (NOT validated production CAM):
    - dxf: AutoCAD DXF
    - svg: Scalable Vector Graphics
    - loom: Jacquard Loom Machine Instruction Matrix
    - report: JSON Analysis and Recipe Report
    """
    report = get_job(job_id)
    job_dir = str(job_directory(job_id))
    if not os.path.isdir(job_dir):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    file_mapping = {
        "dxf": (f"{job_id}_production.dxf", "application/dxf"),
        "svg": (f"{job_id}_vector.svg", "image/svg+xml"),
        "loom": (f"{job_id}_loom_matrix.txt", "text/plain"),
        "matrix": (f"{job_id}_loom_matrix.txt", "text/plain"),
        "vdw": (f"{job_id}_vdw_pattern.ep", "application/octet-stream"),
        "ep": (f"{job_id}_vdw_pattern.ep", "application/octet-stream"),
        "staubli": (f"{job_id}_staubli.jc5", "text/plain"),
        "jc5": (f"{job_id}_staubli.jc5", "text/plain"),
        "report": ("analysis_report.json", "application/json"),
        "json": ("analysis_report.json", "application/json")
    }

    key = file_type.lower()
    if key not in file_mapping:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{file_type}'. Choose: dxf, svg, loom, vdw, staubli, report")

    filename, media_type = file_mapping[key]
    file_path = os.path.join(job_dir, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File {filename} does not exist for job {job_id}")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=('DEMO_' if report.data_source == 'DEMO_SYNTHETIC' else '') + filename
    )


@app.get("/static/{job_id}/{filename}")
def job_image(job_id: str, filename: str):
    get_job(job_id)
    if filename not in {"00_input.png", "01_rectified.png", "02_completed_pattern.png", "03_quantized_palette.png", "02_repair_mask.png", f"{job_id}_vector.svg"}:
        raise HTTPException(404, "Görsel bulunamadı")
    path = job_directory(job_id) / filename
    if not path.is_file():
        raise HTTPException(404, "Görsel bulunamadı")
    return FileResponse(path)


@app.get("/api/v1/erp/inventory")
def get_erp_inventory():
    settings = load_settings()
    return {"status": "MANUAL_INPUT", "system": settings.erp_system or "ERP bağlı değil",
            "updated_at": settings.updated_at, "inventory": [y.model_dump() for y in settings.yarns]}


@app.post("/api/v1/erp/reserve")
@app.post("/api/v1/erp/purchase-requisition")
def erp_not_connected():
    raise HTTPException(503, "Doğrulanmış ERP bağlantısı kurulmadı; işlem yapılmadı.")


# --- FAZ 3: Spektrofotometre (X-Rite / Datacolor) Entegrasyonu ---
from core.measurements import parse_explicit_lab


@app.post("/api/v1/spectro/import")
async def import_spectrophotometer_file(file: UploadFile = File(...)):
    content = await file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "Ölçüm dosyası en fazla 2 MB olabilir.")
    filename = (file.filename or "").lower()
    if not filename.endswith((".cxf", ".xml", ".qtx")):
        raise HTTPException(415, "QTX veya CXF dosyası seçin.")
    samples = parse_explicit_lab(content.decode("utf-8", errors="replace"), filename)
    if not samples:
        raise HTTPException(422, "Açık Lab ölçümü bulunamadı.")
    return {"samples": samples, "registered_to_palette": [], "status": "PREVIEW_ONLY"}


@app.post("/api/v1/loom/dispatch")
def dispatch_to_loom_console():
    raise HTTPException(409, "Kontrolör adaptörü ve CAM uyumluluğu doğrulanmadı; dosya gönderilmedi.")


@app.post("/api/v1/analyze", response_model=AnalysisPipelineResult)
async def analyze_carpet_photo(
    file: UploadFile = File(..., description="Competitor carpet photo (JPG/PNG)"),
    width_cm: float = Form(...),
    length_cm: float = Form(...),
    reed_density: int = Form(...),
    pick_density: int = Form(...),
    pile_height_mm: float = Form(...),
    max_colors: int = Form(...),
    order_quantity: int = Form(...),
    waste_coefficient: float = Form(...),
    weave_structure_factor: float = Form(...),
    anchor_length_mm: float = Form(...),
    enable_symmetry: bool = Form(True),
    enable_sam: bool = Form(True),
    enable_dereflection: bool = Form(True),
    symmetry_mode: str = Form("QUADRANT_4FOLD"),
    manual_corners: str = Form("null"),
    repair_regions: str = Form("[]")
):
    """
    Takes an unconstrained competitor carpet photo and loom parameters,
    runs FastSAM background isolation, dereflection, generative inpainting,
    CIEDE2000 factory yarn matching, consumption estimates, and unverified prototype DXF, SVG, Van de Wiele (.EP) & Stäubli (.JC5) exports.
    """
    settings = load_settings()
    if not settings.yarns or (not settings.company_name and not any(y.is_demo for y in settings.yarns)):
        raise HTTPException(422, "Önce Fabrika Ayarları ekranında şirket adını ve gerçek iplik bilgilerini kaydedin.")
    try:
        validate_matching_conditions(settings.yarns)
    except ValueError as error:
        raise HTTPException(422, str(error))
    suffix = os.path.splitext(file.filename or "")[1].lower()
    if suffix not in {".jpg", ".jpeg", ".png"}:
        raise HTTPException(415, "Yalnızca JPG veya PNG yükleyin.")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "Fotoğraf en fazla 20 MB olabilir.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        try:
            with Image.open(tmp_path) as photo:
                if photo.format not in {"JPEG", "PNG"} or photo.width * photo.height > 25_000_000:
                    raise ValueError("Görsel JPG/PNG ve en fazla 25 megapiksel olmalıdır.")
                photo.verify()
        except Exception:
            raise HTTPException(422, "Geçerli bir JPG/PNG yükleyin (en fazla 25 megapiksel).")
        loom_cfg = LoomConfig(
            width_cm=width_cm,
            length_cm=length_cm,
            reed_density=reed_density,
            pick_density=pick_density,
            pile_height_mm=pile_height_mm,
            max_colors=max_colors,
            order_quantity=order_quantity,
            waste_coefficient=waste_coefficient,
            weave_structure_factor=weave_structure_factor,
            anchor_length_mm=anchor_length_mm
        )

        try:
            corners_data = json.loads(manual_corners)
            regions_data = json.loads(repair_regions)
        except (ValueError, TypeError):
            raise HTTPException(422, "Köşe ve maske verisi geçerli JSON olmalıdır.")
        params = ImagePreprocessingParams(
            manual_corners=corners_data,
            repair_regions=regions_data,
            enable_symmetry_completion=enable_symmetry,
            enable_sam_segmentation=enable_sam,
            enable_dereflection=enable_dereflection,
            symmetry_mode=symmetry_mode
        )

        try:
            job_runtime.check_limits(width_cm=loom_cfg.width_cm, length_cm=loom_cfg.length_cm,
                                     reed=loom_cfg.reed_density, pick=loom_cfg.pick_density)
        except ValueError as error:
            raise HTTPException(422, str(error))
        worker = CarpetAnalysisPipeline(output_base_dir=str(active_output_dir()), palette=[y.model_dump() for y in settings.yarns])
        result = await run_in_threadpool(
            worker.process, image_input=tmp_path, loom_cfg=loom_cfg, params=params,
            persist_report=False
        )
        job_runtime.check_output(active_output_dir(), result.job_id)
        mark_demo_result(result, settings.yarns)
        result.factory_settings_revision = settings.revision
        result.company_name = settings.company_name
        report_path = job_directory(result.job_id) / "analysis_report.json"
        temporary = report_path.with_suffix('.tmp')
        temporary.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporary, report_path)
        return result

    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(422, detail="; ".join(error["msg"] for error in e.errors()))
    except Exception:
        logging.exception('Unexpected carpet analysis failure')
        raise HTTPException(status_code=500, detail='Analiz sırasında beklenmeyen bir sunucu hatası oluştu.')
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


from core import designer_studio as studio


@app.get('/api/v1/jobs/{job_id}/studio')
def get_studio(job_id: str):
    report = get_job(job_id)
    directory = job_directory(job_id)
    try:
        history = studio.revisions(directory)
        latest = studio.read_revision(directory, history[0]['revision']) if history else None
        return {'job_id':job_id, 'revision':history[0]['revision'] if history else 0,
                'document':latest['document'] if latest else studio.initial_document(directory,report).model_dump(),
                'palette':report.palette_snapshot, 'data_source':report.data_source,
                'loom_config':report.loom_config.model_dump() if report.loom_config else None,
                'history':history, 'evaluation':latest['evaluation'] if latest else None}
    except ValueError as error:
        raise HTTPException(422,str(error))


@app.post('/api/v1/jobs/{job_id}/studio/revisions', status_code=201)
def save_studio_revision(job_id: str, request: studio.RevisionRequest):
    report = get_job(job_id)
    try:
        return studio.save_revision(job_directory(job_id), report, request)
    except ValueError as error:
        raise HTTPException(409,str(error))


@app.get('/api/v1/jobs/{job_id}/studio/revisions/{revision}')
def get_studio_revision(job_id: str, revision: int):
    get_job(job_id)
    try:
        return studio.read_revision(job_directory(job_id),revision)
    except ValueError as error:
        raise HTTPException(404,str(error))


@app.post('/api/v1/jobs/{job_id}/evidence', status_code=201, response_model=evidence.EvidenceRecord)
async def upload_job_evidence(job_id: str, request: Request, file: UploadFile = File(...),
                              metadata: str = Form(...)):
    """Record a source file and measurements, WITHOUT declaring them independently verified."""
    report = get_job(job_id)
    if len(metadata) > 32768:
        raise HTTPException(413, 'Kanıt üstverisi en fazla 32 KB olabilir.')
    try:
        submission = evidence.EvidenceSubmission.model_validate_json(metadata)
    except ValueError as error:
        raise HTTPException(422, str(error))
    ext = Path((file.filename or '').replace('\\', '/')).suffix.lower()
    if ext not in {'.pdf', '.png', '.jpg', '.jpeg', '.cxf', '.qtx', '.xml', '.txt'}:
        raise HTTPException(415, 'Yalnızca PDF, JPG, PNG, CXF, QTX, XML veya TXT kanıtı yükleyin.')
    data = await file.read(evidence.MAX_EVIDENCE_BYTES + 1)
    if not data or len(data) > evidence.MAX_EVIDENCE_BYTES:
        raise HTTPException(413, 'Kanıt dosyası 1 bayt ile 5 MB arasında olmalıdır.')

    job_dir = job_directory(job_id)
    report_digest = hashlib.sha256((job_dir / 'analysis_report.json').read_bytes()).hexdigest()
    studio_digest = None
    if submission.studio_revision is not None:
        from core import designer_studio as studio
        try:
            saved = studio.read_revision(job_dir, submission.studio_revision)
        except ValueError as error:
            raise HTTPException(409, str(error))
        if saved.get('job_id') != job_id or saved.get('revision') != submission.studio_revision:
            raise HTTPException(409, 'Stüdyo revizyonu bu analize ait değil.')
        studio_digest = saved['evaluation']['grid_sha256']

    if submission.color_observation and submission.color_observation.yarn_code not in {
            p.get('code') for p in report.palette_snapshot}:
        raise HTTPException(422, 'Ölçülen iplik kodu bu analizde bulunmuyor.')

    username = getattr(getattr(request.state, 'principal', None), 'username', None)
    if auth.mode() != 'local':
        username = request.state.principal['username']
    else:
        username = 'LOCAL_UNAUTHENTICATED'

    try:
        return evidence.record_evidence(job_dir, submission, data,
            real_report_sha256=report_digest, studio_grid_sha256=studio_digest,
            submitted_by=username)
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.get('/api/v1/jobs/{job_id}/evidence', response_model=list[evidence.EvidenceRecord])
def list_job_evidence(job_id: str):
    get_job(job_id)
    try:
        return evidence.list_records(job_directory(job_id))
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.get('/api/v1/jobs/{job_id}/evidence/{evidence_id}/download')
def download_job_evidence(job_id: str, evidence_id: str):
    get_job(job_id)
    try:
        record, path = evidence.find_record(job_directory(job_id), evidence_id)
    except FileNotFoundError:
        raise HTTPException(404, 'Kanıt kaydı bulunamadı.')
    except ValueError as error:
        raise HTTPException(409, str(error))
    return FileResponse(path, filename=record.evidence_id + '.bin',
                        media_type='application/octet-stream',
                        headers={'X-Content-Type-Options': 'nosniff'})


@app.get('/api/v1/jobs/{job_id}/preflight', response_model=PreflightResult)
def get_production_preflight(job_id: str, studio_revision: int | None = Query(default=None, ge=1)):
    """Evidence report for an immutable analysis or a saved studio revision.

    No pre-flight response is a manufacturer or authorized production approval.
    """
    report = get_job(job_id)
    raw_report = (job_directory(job_id) / 'analysis_report.json').read_bytes()
    report_sha = hashlib.sha256(raw_report).hexdigest()
    evaluation = None
    if studio_revision is not None:
        from core import designer_studio as studio
        try:
            saved = studio.read_revision(job_directory(job_id), studio_revision)
        except ValueError as error:
            raise HTTPException(404, str(error))
        if saved.get('job_id') != job_id or saved.get('revision') != studio_revision:
            raise HTTPException(409, 'Stüdyo revizyonu analizle uyuşmuyor.')
        evaluation = saved['evaluation']
    try:
        matched = evidence.records_for_scope(evidence.list_records(job_directory(job_id)),
                         report_sha, studio_revision,
                         evaluation.get('grid_sha256') if evaluation else None)
    except ValueError as error:
        raise HTTPException(409, str(error))
    return evaluate_preflight(report, report_sha,
                              studio_revision=studio_revision, studio_evaluation=evaluation,
                              evidence_records=[r.model_dump(mode='json') for r in matched])


# Mount frontend dist if built
FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
