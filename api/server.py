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
import logging
from datetime import datetime, timezone
import uuid
from starlette.concurrency import run_in_threadpool
from PIL import Image
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.models import LoomConfig, ImagePreprocessingParams, AnalysisPipelineResult
from core.pipeline import CarpetAnalysisPipeline
from core.factory_settings import FactorySettings, load_settings, save_settings
from core.demo_data import change_demo_inventory, mark_demo_result
from core.supplier_catalog import SupplierCatalog, append_catalog, catalog_view, validate_matching_conditions

app = FastAPI(
    title="Industrial Carpet AI: Competitor Photo to CAD & Yarn Recipe API",
    version="1.0.0",
    description="End-to-end Computer Vision, CIEDE2000 Color Matching, CAD DXF & Loom CAM Engine"
)

# This application is intended for loopback-only use until authentication exists.
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
    allow_origins=TRUSTED_BROWSER_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def enforce_local_browser_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin is not None and origin not in TRUSTED_BROWSER_ORIGINS:
        return JSONResponse(status_code=403, content={"detail": "Bu yerel API başka bir web kökeninden kullanılamaz."})
    return await call_next(request)

# Output directory setup
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
os.makedirs(OUTPUT_DIR, exist_ok=True)


PALETTE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "palette", "factory_palette.json"))



@app.get("/api/v1/health")
def health_check():
    return {
        "status": "online",
        "engine": "Carpet CAD & Yarn Recipe Optimizer v1.0",
        "license": "All Rights Reserved - Seydi Eryılmaz (@seydivakkas)"
    }


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
    for path in Path(OUTPUT_DIR).glob('*/analysis_report.json'):
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
    root = Path(OUTPUT_DIR).resolve()
    target = (root / job_id).resolve()
    if target.parent != root:
        raise HTTPException(400, "Geçersiz analiz yolu")
    return target


@app.get("/api/v1/jobs")
def list_jobs():
    items = []
    for path in Path(OUTPUT_DIR).glob("*/analysis_report.json"):
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
    path = job_directory(job_id) / "analysis_report.json"
    if not path.is_file():
        raise HTTPException(404, "Analiz bulunamadı")
    try:
        report = AnalysisPipelineResult.model_validate_json(path.read_text(encoding="utf-8"))
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
    connection = sqlite3.connect(str(Path(OUTPUT_DIR) / "reviews.sqlite3"))
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
    Download production-ready CAD & CAM files:
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
    CIEDE2000 factory yarn matching, consumption calculations, and exports DXF, SVG, Van de Wiele (.EP) & Stäubli (.JC5) files.
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

        worker = CarpetAnalysisPipeline(output_base_dir=OUTPUT_DIR, palette=[y.model_dump() for y in settings.yarns])
        result = await run_in_threadpool(
            worker.process,
            image_input=tmp_path,
            loom_cfg=loom_cfg,
            params=params
        )
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


# Mount frontend dist if built
FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
