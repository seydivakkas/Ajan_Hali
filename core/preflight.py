"""Evidence-aware, fail-closed production pre-flight. No automatic approval.

This module evaluates *recorded* facts only. It deliberately does not infer
physical colour, machine compatibility or approval from a photograph or score.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


CheckStatus = Literal["PASS", "WARN", "FAIL", "NOT_VERIFIED"]
GateStatus = Literal["BLOCKED", "REVIEW_REQUIRED", "APPROVED"]
RULE_VERSION = "preflight-v1.2-preview.1"


class PreflightCheck(BaseModel):
    id: str
    status: CheckStatus
    description: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    reason: str
    observed_at: str
    rule_version: str = RULE_VERSION


class PreflightResult(BaseModel):
    job_id: str
    source_report_sha256: str
    source_revision: int | None
    studio_revision: int | None
    studio_grid_sha256: str | None
    checked_at: str
    rule_version: str = RULE_VERSION
    checks: list[PreflightCheck]
    gate: GateStatus
    approved: bool = False
    approval_id: None = None


def evaluate_preflight(report, report_sha256: str, *, studio_revision: int | None = None,
                       studio_evaluation: dict[str, Any] | None = None) -> PreflightResult:
    """Evaluate immutable analysis or studio-revision metadata.

    The caller must obtain the report and digest from disk, not the request body.
    A saved studio revision is used only when explicitly selected.
    """
    now = datetime.now(timezone.utc).isoformat()
    checks: list[PreflightCheck] = []

    def add(check_id: str, status: CheckStatus, description: str, reason: str,
            **evidence: Any) -> None:
        checks.append(PreflightCheck(id=check_id, status=status, description=description,
                                     reason=reason, evidence=evidence, observed_at=now))

    palette = report.palette_snapshot
    loom = report.loom_config
    colors = report.color_mappings
    recipe = report.yarn_recipe
    cells = (report.grid_resolution_cells[0] * report.grid_resolution_cells[1])
    studio_counts = studio_evaluation.get("color_counts") if studio_evaluation else None

    if report.data_source == "DEMO_SYNTHETIC" or any(
        yarn.get("is_demo") or yarn.get("color_source") == "DEMO_SYNTHETIC" for yarn in palette
    ):
        add("provenance", "FAIL", "Production source authenticity",
            "Demo input is not admissible for production.", source=report.data_source)
    elif report.data_source == "USER_FACTORY_INPUT" and palette:
        add("provenance", "PASS", "Production source authenticity",
            "Source is declared company data; independent accuracy is checked separately.",
            source=report.data_source, palette_entries=len(palette))
    else:
        add("provenance", "FAIL", "Production source authenticity",
            "Source provenance or recorded palette is missing.", source=report.data_source)

    active = studio_counts if studio_counts is not None else [
        {"palette_code": c.palette_code, "pixel_count": c.pixel_count} for c in colors
    ]
    color_total = sum(int(c.get("pixel_count", 0)) for c in active)
    if not loom or cells <= 0 or color_total != cells:
        add("loom_grid", "FAIL", "Loom-grid metadata integrity",
            "Recorded colour cell counts do not match grid dimensions.",
            width=report.grid_resolution_cells[0], height=report.grid_resolution_cells[1],
            expected=cells, counted=color_total)
    else:
        add("loom_grid", "PASS", "Loom-grid metadata integrity",
            "Recorded dimensions match colour counts; machine layout is not verified.",
            width=report.grid_resolution_cells[0], height=report.grid_resolution_cells[1],
            expected=cells, counted=color_total, validation="METADATA_ONLY")

    used = {c.get("palette_code") for c in active if int(c.get("pixel_count", 0)) > 0}
    capacity = loom.max_colors if loom else None
    if capacity is None or len(used) > capacity or not used:
        add("creel", "FAIL", "Creel colour capacity",
            "Active colours are empty or exceed the configured capacity.",
            active_colors=len(used), configured_capacity=capacity)
    else:
        add("creel", "PASS", "Creel colour capacity",
            "Active colours fit the configured capacity; physical creel is not inspected.",
            active_colors=len(used), configured_capacity=capacity)

    # When a studio master is selected, use *its* recalculated recipe. Never
    # reuse a stale analysis recipe as evidence for the edited grid.
    effective_recipe = studio_evaluation.get("recipe", []) if studio_evaluation else recipe
    shortages = [
        {"yarn_code": (r.get("yarn_code") if isinstance(r, dict) else r.yarn_code),
         "shortage_kg": (r.get("stock_shortage_kg") if isinstance(r, dict)
                         else r.stock_shortage_kg)}
        for r in effective_recipe
        if not (r.get("is_stock_sufficient") if isinstance(r, dict) else r.is_stock_sufficient)
    ]
    add("stock_snapshot", "FAIL" if shortages else ("PASS" if effective_recipe else "NOT_VERIFIED"),
        "Recorded yarn stock against estimated consumption",
        "Shortage in recorded snapshot." if shortages else
        ("Recorded stock covers estimated consumption; this is not live ERP stock."
         if effective_recipe else "No recorded consumption evidence."),
        shortages=shortages, live_erp_verified=False)

    conditions = []
    for yarn in palette:
        measured = yarn.get("catalog_snapshot") or {}
        color = measured.get("color") or {}
        if color:
            conditions.append({"code": yarn.get("code"),
                               "illuminant": color.get("illuminant"),
                               "observer": color.get("observer")})
    incompatible = [c for c in conditions if c["illuminant"] != "D65" or str(c["observer"]) != "2"]
    add("color_measurement", "FAIL" if incompatible else "NOT_VERIFIED",
        "Colour measurement and target/sample Delta E",
        "Recorded measurement conditions contradict the comparison engine."
        if incompatible else "No traceable, post-design target/sample measurement and colour tolerance evidence.",
        catalog_conditions=conditions, incompatible_conditions=incompatible,
        photo_estimate_is_physical_measurement=False)

    add("lot_traceability", "NOT_VERIFIED", "Yarn lot traceability",
        "No verified physical-lot reservation with measurement provenance.",
        recorded_catalog_lots=[
            {"code": p.get("code"), "dye_lot": ((p.get("catalog_snapshot") or {}).get("color") or {}).get("dye_lot")}
            for p in palette if (p.get("catalog_snapshot") or {}).get("color")
        ])
    add("calibration", "NOT_VERIFIED", "Camera and colour-card calibration",
        "Versioned reference chart, device and illuminant evidence are unavailable.")
    add("repeat", "NOT_VERIFIED", "Full motif-repeat compatibility",
        "Opposing edge values or image heuristics do not certify weaving repeat.")
    add("loom_profile", "NOT_VERIFIED", "Machine controller and firmware profile",
        "No validated controller/firmware configuration for this job.")
    add("cam_format", "NOT_VERIFIED", "Manufacturer-validated CAM encoding",
        "Prototype EP/JC5 exports are not manufacturer certified.",
        declared_compatibility=report.cam_compatibility)
    add("operator_approval", "NOT_VERIFIED", "Authorized production release",
        "No cryptographically bound authorized operator approval for this source.")

    # A PASS in some metadata-only checks is never an overall approval.
    gate: GateStatus = "BLOCKED" if any(c.status == "FAIL" for c in checks) else "REVIEW_REQUIRED"
    return PreflightResult(
        job_id=report.job_id, source_report_sha256=report_sha256,
        source_revision=report.factory_settings_revision,
        studio_revision=studio_revision,
        studio_grid_sha256=studio_evaluation.get("grid_sha256") if studio_evaluation else None,
        checked_at=now, checks=checks, gate=gate,
    )
