"""Pre-flight outcomes are evidence-bound and never automatically approve."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core import designer_studio as studio
from core.models import LoomConfig
from core.preflight import evaluate_preflight


def report(*, demo=False, shortage=False):
    return SimpleNamespace(
        job_id="PREFLIGHT_CASE",
        data_source="DEMO_SYNTHETIC" if demo else "USER_FACTORY_INPUT",
        palette_snapshot=[{
            "code": "YARN_A", "name": "Yarn A", "material": "PP",
            "dtex": 1800, "cost_per_kg_tl": 100, "bobbin_weight_kg": 5,
            "stock_kg": 0 if shortage else 1000,
            "color_source": "DEMO_SYNTHETIC" if demo else "MEASURED_LAB",
            "is_demo": demo, "lab": [50, 0, 0],
        }],
        loom_config=LoomConfig(width_cm=4, length_cm=3,
                               reed_density=100, pick_density=100, max_colors=4,
                               order_quantity=1, pile_height_mm=8),
        grid_resolution_cells=(4, 3),
        color_mappings=[SimpleNamespace(palette_code="YARN_A", pixel_count=12)],
        yarn_recipe=[SimpleNamespace(yarn_code="YARN_A",
                                    is_stock_sufficient=not shortage,
                                    stock_shortage_kg=1 if shortage else 0)],
        factory_settings_revision=7,
        cam_compatibility="UNVERIFIED_PROTOTYPE",
    )


class PreflightTests(unittest.TestCase):
    def test_real_input_without_physical_evidence_is_review_required(self):
        result = evaluate_preflight(report(), "a" * 64)
        checks = {c.id: c for c in result.checks}
        self.assertEqual(result.gate, "REVIEW_REQUIRED")
        self.assertFalse(result.approved)
        self.assertIsNone(result.approval_id)
        self.assertEqual(result.source_revision, 7)
        self.assertEqual(checks["provenance"].status, "PASS")
        self.assertEqual(checks["loom_grid"].status, "PASS")
        self.assertEqual(checks["stock_snapshot"].status, "PASS")
        self.assertEqual(checks["cam_format"].status, "NOT_VERIFIED")
        self.assertEqual(checks["color_measurement"].status, "NOT_VERIFIED")
        self.assertEqual(checks["repeat"].status, "NOT_VERIFIED")
        self.assertEqual(checks["operator_approval"].status, "NOT_VERIFIED")
        self.assertTrue(all(c.rule_version and c.observed_at for c in result.checks))

    def test_demo_and_shortage_block(self):
        for parameters in (dict(demo=True), dict(shortage=True)):
            with self.subTest(**parameters):
                result = evaluate_preflight(report(**parameters), "b" * 64)
                self.assertEqual(result.gate, "BLOCKED")
                self.assertTrue(any(c.status == "FAIL" for c in result.checks))

    def test_mismatched_counts_fail_without_silent_correction(self):
        example = report()
        example.color_mappings[0].pixel_count = 11
        result = evaluate_preflight(example, "c" * 64)
        self.assertEqual(result.gate, "BLOCKED")
        self.assertEqual(next(c for c in result.checks if c.id == "loom_grid").status, "FAIL")

    def test_incompatible_colour_observer_fails(self):
        example = report()
        example.palette_snapshot[0]["catalog_snapshot"] = {
            "color": {"illuminant": "D65", "observer": "10", "dye_lot": "X"}
        }
        result = evaluate_preflight(example, "d" * 64)
        self.assertEqual(next(c for c in result.checks if c.id == "color_measurement").status, "FAIL")

    def test_api_digest_and_studio_revision_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job_dir = root / "PREFLIGHT_CASE"
            job_dir.mkdir()
            raw = b'{"immutable":"source"}'
            (job_dir / "analysis_report.json").write_bytes(raw)
            example = report()
            client = TestClient(app)
            document = studio.StudioDocument(width=4, height=3, colorway=[0],
                layers=[studio.Layer(id="base", name="Base", role="BASE", visible=True,
                                     x=0, y=0, width=4, height=3, cells=[0] * 12)])
            saved = studio.save_revision(job_dir, example, studio.RevisionRequest(
                document=document, parent_revision=0, author="Tester", note="Test",
                kind="DRAFT"))
            with patch("api.server.OUTPUT_DIR", str(root)), patch("api.server.get_job", return_value=example):
                base = client.get("/api/v1/jobs/PREFLIGHT_CASE/preflight")
                self.assertEqual(base.status_code, 200, base.text)
                self.assertEqual(base.json()["source_report_sha256"], hashlib.sha256(raw).hexdigest())
                self.assertIsNone(base.json()["studio_revision"])
                revision = client.get("/api/v1/jobs/PREFLIGHT_CASE/preflight?studio_revision=1")
                self.assertEqual(revision.status_code, 200, revision.text)
                self.assertEqual(revision.json()["studio_revision"], 1)
                self.assertEqual(revision.json()["studio_grid_sha256"], saved["evaluation"]["grid_sha256"])
                self.assertEqual(client.get("/api/v1/jobs/PREFLIGHT_CASE/preflight?studio_revision=2").status_code, 404)
                self.assertEqual(client.get("/api/v1/jobs/PREFLIGHT_CASE/preflight?studio_revision=0").status_code, 422)
            client.close()

    def test_tampered_studio_revision_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = report()
            doc = studio.StudioDocument(width=4, height=3, colorway=[0],
                layers=[studio.Layer(id="base", name="Base", role="BASE", visible=True,
                                     x=0, y=0, width=4, height=3, cells=[0] * 12)])
            studio.save_revision(root, example, studio.RevisionRequest(
                document=doc, parent_revision=0, author="Tester", note="Test", kind="DRAFT"))
            import sqlite3
            with sqlite3.connect(root / "studio.sqlite3") as db:
                db.execute("UPDATE revisions SET sha256 = ? WHERE revision = 1", ("0" * 64,))
            with self.assertRaisesRegex(ValueError, "bütünlük"):
                studio.read_revision(root, 1)


if __name__ == "__main__":
    unittest.main()
