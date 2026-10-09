"""Auditable uploaded measurement evidence; NEVER an automatic production approval."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.server import app
from core import access_control as auth
from core import evidence_registry as ledger
from core.preflight import evaluate_preflight
from test_preflight import report


HASH = hashlib.sha256(b'{"immutable":"source"}').hexdigest()
SAMPLE = {
    "target_lab": [50, 2.6772, -79.7751],
    "sample_lab": [50, 0, -82.7485],
    "illuminant": "D65", "observer": "2",
    "device": "Instrument serial 001", "dye_lot": "LOT-1", "yarn_code": "YARN_A",
    "measured_on": "2026-10-09", "declared_max_delta_e00": 3.0,
}


def metadata(**changes):
    return {
        "expected_report_sha256": HASH,
        "kind": "COLOR_LAB_SAMPLE",
        "source_reference": "Lab notebook page 17",
        "note": "Physical sample observation; independent verification pending",
        "color_observation": SAMPLE,
        **changes,
    }


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.job = self.root / "PREFLIGHT_CASE"
        self.job.mkdir()
        (self.job / "analysis_report.json").write_bytes(b'{"immutable":"source"}')
        self.example = report()

    def test_sha_and_scope_roundtrip_and_file_tampering(self):
        scope = ledger.EvidenceSubmission.model_validate(metadata())
        record = ledger.record_evidence(self.job, scope, b"unverified source content",
                                        real_report_sha256=HASH,
                                        studio_grid_sha256=None, submitted_by="tester")
        self.assertEqual(record.verification, "RECORDED_NOT_INDEPENDENTLY_VERIFIED")
        self.assertEqual(record.report_sha256, HASH)
        self.assertEqual(record.file_sha256, hashlib.sha256(b"unverified source content").hexdigest())
        self.assertEqual(len(ledger.list_records(self.job)), 1)
        matched = ledger.records_for_scope(ledger.list_records(self.job), HASH, None, None)
        self.assertEqual(len(matched), 1)
        self.assertEqual(ledger.records_for_scope(matched, "0" * 64, None, None), [])
        self.assertEqual(ledger.records_for_scope(matched, HASH, 1, "b" * 64), [])
        stored, path = ledger.find_record(self.job, record.evidence_id)
        self.assertEqual(stored.evidence_id, record.evidence_id)
        self.assertEqual(path.read_bytes(), b"unverified source content")
        path.write_bytes(b"altered")
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            ledger.list_records(self.job)

    def test_source_revision_and_schema_rejection(self):
        with self.assertRaises(ValidationError):
            ledger.EvidenceSubmission.model_validate(metadata(color_observation=None))
        with self.assertRaises(ValidationError):
            ledger.EvidenceSubmission.model_validate(metadata(studio_revision=1))
        with self.assertRaises(ValidationError):
            ledger.EvidenceSubmission.model_validate(metadata(color_observation={
                **SAMPLE, "target_lab": [float("nan"), 0, 0]
            }))
        form = ledger.EvidenceSubmission.model_validate(metadata())
        with self.assertRaisesRegex(ValueError, "Report changed"):
            ledger.record_evidence(self.job, form, b"x", real_report_sha256="0"*64,
                                   studio_grid_sha256=None, submitted_by="tester")
        with self.assertRaisesRegex(ValueError, "Studio revision hash mismatch"):
            ledger.record_evidence(self.job, form, b"x", real_report_sha256=HASH,
                                   studio_grid_sha256="0"*64, submitted_by="tester")
        self.assertEqual(ledger.list_records(self.job), [])

    def test_measured_delta_e_is_computed_and_fail_closed(self):
        doc = ledger.EvidenceSubmission.model_validate(metadata())
        recorded = ledger.record_evidence(self.job, doc, b"sample PDF", real_report_sha256=HASH,
                                          studio_grid_sha256=None, submitted_by="tester")
        base = evaluate_preflight(self.example, HASH,
                                   evidence_records=[recorded.model_dump(mode="json")])
        measurement = next(c for c in base.checks if c.id == "color_measurement")
        self.assertEqual(measurement.status, "NOT_VERIFIED")
        self.assertEqual(base.gate, "REVIEW_REQUIRED")
        self.assertFalse(base.approved)
        pair = measurement.evidence["recorded_color_pairs"][0]
        self.assertAlmostEqual(pair["delta_e00"], 2.0425, places=3)
        self.assertFalse(pair["independently_verified"])
        self.assertEqual(len(base.recorded_evidence), 1)

        too_strict = ledger.EvidenceSubmission.model_validate(metadata(color_observation={
            **SAMPLE, "declared_max_delta_e00": 1.0
        }))
        second = ledger.record_evidence(self.job, too_strict, b"second source",
                                        real_report_sha256=HASH,
                                        studio_grid_sha256=None, submitted_by="tester")
        failed = evaluate_preflight(self.example, HASH,
            evidence_records=[recorded.model_dump(mode="json"), second.model_dump(mode="json")])
        self.assertEqual(failed.gate, "BLOCKED")
        self.assertEqual(next(c for c in failed.checks if c.id == "color_measurement").status, "FAIL")

    def test_api_upload_list_preflight_and_attachment(self):
        client = TestClient(app)
        self.addCleanup(client.close)
        with patch("api.server.OUTPUT_DIR", str(self.root)), \
             patch("api.server.get_job", return_value=self.example):
            response = client.post("/api/v1/jobs/PREFLIGHT_CASE/evidence",
                                   data={"metadata": json.dumps(metadata())},
                                   files={"file": ("../../sample.pdf", b"%PDF sample", "application/pdf")})
            self.assertEqual(response.status_code, 201, response.text)
            saved = response.json()
            self.assertEqual(saved["submitted_by"], "LOCAL_UNAUTHENTICATED")
            listing = client.get("/api/v1/jobs/PREFLIGHT_CASE/evidence")
            self.assertEqual(listing.status_code, 200, listing.text)
            self.assertEqual(len(listing.json()), 1)
            preflight = client.get("/api/v1/jobs/PREFLIGHT_CASE/preflight")
            self.assertEqual(preflight.status_code, 200, preflight.text)
            self.assertEqual(preflight.json()["recorded_evidence"][0]["evidence_id"], saved["evidence_id"])
            file_response = client.get(f'/api/v1/jobs/PREFLIGHT_CASE/evidence/{saved["evidence_id"]}/download')
            self.assertEqual(file_response.content, b"%PDF sample")
            self.assertEqual(file_response.headers["x-content-type-options"], "nosniff")
            self.assertEqual(file_response.headers["content-type"], "application/octet-stream")
            stale = client.post("/api/v1/jobs/PREFLIGHT_CASE/evidence",
                                data={"metadata": json.dumps(metadata(expected_report_sha256="0"*64))},
                                files={"file": ("sample.pdf", b"one", "application/pdf")})
            self.assertEqual(stale.status_code, 409)
            missing = client.post("/api/v1/jobs/PREFLIGHT_CASE/evidence",
                                  data={"metadata": json.dumps(metadata(color_observation=None))},
                                  files={"file": ("sample.pdf", b"one", "application/pdf")})
            self.assertEqual(missing.status_code, 422)
            self.assertEqual(client.get("/api/v1/jobs/PREFLIGHT_CASE/evidence/"+"."*32+"/download").status_code, 409)

    def test_session_role_authorization(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with patch.object(auth, "AUTH_DB_PATH", Path(temporary.name)/"auth.sqlite3"), \
             patch.dict(os.environ, {"AJAN_HALI_AUTH_MODE": "session"}), \
             patch("api.server.OUTPUT_DIR", str(self.root)), \
             patch("api.server.get_job", return_value=self.example):
            auth.create_user("operator1", "operator-password-strong", "OPERATOR")
            auth.create_user("designer1", "designer-password-strong", "DESIGNER")
            with TestClient(app) as operator:
                login = operator.post("/api/v1/auth/login",
                    json={"username": "operator1", "password": "operator-password-strong"})
                self.assertEqual(login.status_code, 200)
                result = operator.post("/api/v1/jobs/PREFLIGHT_CASE/evidence",
                    headers={"X-CSRF-Token": login.json()["csrf_token"]},
                    data={"metadata": json.dumps(metadata())},
                    files={"file": ("doc.pdf", b"source")})
                self.assertEqual(result.status_code, 403)
            with TestClient(app) as designer:
                login = designer.post("/api/v1/auth/login",
                    json={"username": "designer1", "password": "designer-password-strong"})
                result = designer.post("/api/v1/jobs/PREFLIGHT_CASE/evidence",
                    headers={"X-CSRF-Token": login.json()["csrf_token"]},
                    data={"metadata": json.dumps(metadata())},
                    files={"file": ("doc.pdf", b"source")})
                self.assertEqual(result.status_code, 201, result.text)
                self.assertEqual(result.json()["submitted_by"], "designer1")


if __name__ == "__main__":
    unittest.main()
