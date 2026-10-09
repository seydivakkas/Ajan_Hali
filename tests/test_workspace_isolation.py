"""P0 workspace isolation: cross-company request, storage and IDOR regressions."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core import access_control as auth
from core import factory_settings as settings_module
from core import supplier_catalog as catalog_module


class WorkspaceIsolationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        patches = [
            patch.object(auth, "AUTH_DB_PATH", root / "auth.sqlite3"),
            patch.object(auth, "WORKSPACE_ROOT", root / "workspaces"),
            patch.object(settings_module, "SETTINGS_PATH", root / "legacy_settings.json"),
            patch.object(catalog_module, "CATALOG_PATH", root / "legacy_catalog.json"),
            patch.dict(os.environ, {"AJAN_HALI_AUTH_MODE": "workspace"}),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.root = root
        auth.create_workspace("alpha_co", "Company Alpha")
        auth.create_workspace("beta_co", "Company Beta")
        auth.create_user("alpha_admin", "alpha-password-strong", "ADMIN", "alpha_co")
        auth.create_user("beta_admin", "beta-password-strong", "ADMIN", "beta_co")
        auth.create_user("beta_operator", "beta-operator-strong", "OPERATOR", "beta_co")
        auth.create_user("old_local", "legacy-password-strong", "ADMIN")
        self.alpha = TestClient(app)
        self.beta = TestClient(app)
        self.addCleanup(self.alpha.close)
        self.addCleanup(self.beta.close)
        self.a_csrf = self.login(self.alpha, "alpha_admin", "alpha-password-strong", "alpha_co")
        self.b_csrf = self.login(self.beta, "beta_admin", "beta-password-strong", "beta_co")

    def login(self, client, username, password, expected_workspace):
        result = client.post("/api/v1/auth/login",
                             json={"username": username, "password": password})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["workspace_id"], expected_workspace)
        self.assertEqual(result.json()["mode"], "workspace")
        return result.json()["csrf_token"]

    @staticmethod
    def fake_report(text):
        source = json.loads(text)
        return SimpleNamespace(
            job_id=source["job_id"], data_source="USER_FACTORY_INPUT",
            created_at="2026-10-09T00:00:00Z", carpet_dimensions_cm=(50, 80),
            audit=SimpleNamespace(status="REVIEW_REQUIRED"), total_order_cost_tl=25,
        )

    def write_job(self, tenant, job_id, marker):
        directory = auth.WORKSPACE_ROOT / tenant / "jobs" / job_id
        directory.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"job_id": job_id, "marker": marker}).encode()
        (directory / "analysis_report.json").write_bytes(content)
        (directory / "00_input.png").write_bytes(marker.encode())
        return content

    def test_no_login_or_unassigned_legacy_user_cannot_enter_workspace(self):
        with TestClient(app) as anonymous:
            self.assertEqual(anonymous.get("/api/v1/settings").status_code, 401)
            self.assertEqual(anonymous.get("/api/v1/jobs").status_code, 401)
            self.assertEqual(anonymous.get("/api/v1/erp/inventory").status_code, 401)
            self.assertEqual(anonymous.post("/api/v1/auth/login", json={
                "username": "old_local", "password": "legacy-password-strong",
            }).status_code, 401)
        self.assertEqual(self.alpha.get("/api/v1/auth/session").json()["workspace_id"], "alpha_co")
        self.assertEqual(self.beta.get("/api/v1/auth/session").json()["workspace_id"], "beta_co")
        # No firm selector exists in query, body or user-supplied request headers.
        self.assertEqual(self.alpha.get("/api/v1/auth/session",
            headers={"X-Workspace-ID": "beta_co"},
            params={"workspace_id": "beta_co"}).json()["workspace_id"], "alpha_co")

    def test_settings_stock_and_catalog_are_isolated(self):
        for client, name, csrf in [
            (self.alpha, "Alpha Ltd", self.a_csrf), (self.beta, "Beta Ltd", self.b_csrf),
        ]:
            result = client.put("/api/v1/settings",
                headers={"X-CSRF-Token": csrf},
                json={"revision": 0, "company_name": name})
            self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.alpha.get("/api/v1/settings").json()["company_name"], "Alpha Ltd")
        self.assertEqual(self.beta.get("/api/v1/settings").json()["company_name"], "Beta Ltd")
        self.assertEqual(self.alpha.get("/api/v1/erp/inventory").json()["status"], "MANUAL_INPUT")
        self.assertEqual(self.alpha.get("/api/v1/erp/inventory").json()["inventory"], [])
        self.assertEqual(self.alpha.get("/api/v1/settings",
            headers={"X-Workspace-ID": "beta_co"}).json()["company_name"], "Alpha Ltd")
        product = {
            "id": "PR1", "supplier": "Alpha supplier", "product_code": "AC-1",
            "material": "PP", "count_value": 1800, "count_unit": "dtex",
            "count_basis": "FINISHED_YARN", "source_ref": "Company Alpha test source",
        }
        self.assertEqual(self.alpha.post("/api/v1/catalog",
            headers={"X-CSRF-Token": self.a_csrf},
            json={"products": [product]}).status_code, 201)
        self.assertEqual(self.beta.get("/api/v1/catalog").json()["products"], [])
        self.assertEqual(self.alpha.get("/api/v1/catalog").json()["products"][0]["id"], "PR1")
        self.assertFalse(settings_module.SETTINGS_PATH.exists())
        self.assertFalse(catalog_module.CATALOG_PATH.exists())
        self.assertTrue((auth.WORKSPACE_ROOT / "alpha_co" / "factory_settings.json").is_file())
        self.assertTrue((auth.WORKSPACE_ROOT / "alpha_co" / "supplier_catalog.json").is_file())
        self.assertTrue((auth.WORKSPACE_ROOT / "beta_co" / "factory_settings.json").is_file())

    def test_cross_workspace_job_ids_downloads_reviews_and_evidence(self):
        a_same = self.write_job("alpha_co", "JOB-SAME", "ALPHA-REPORT")
        b_same = self.write_job("beta_co", "JOB-SAME", "BETA-REPORT")
        self.write_job("beta_co", "JOB-PRIVATE", "BETA-SECRET")
        with patch("api.server.AnalysisPipelineResult.model_validate_json", side_effect=self.fake_report):
            a_jobs = self.alpha.get("/api/v1/jobs")
            b_jobs = self.beta.get("/api/v1/jobs")
            self.assertEqual([r["job_id"] for r in a_jobs.json()], ["JOB-SAME"])
            self.assertEqual({r["job_id"] for r in b_jobs.json()}, {"JOB-SAME", "JOB-PRIVATE"})
            for route in [
                "/api/v1/jobs/JOB-PRIVATE/download/report",
                "/api/v1/jobs/JOB-PRIVATE/studio",
                "/api/v1/jobs/JOB-PRIVATE/preflight",
                "/api/v1/jobs/JOB-PRIVATE/reviews",
                "/api/v1/jobs/JOB-PRIVATE/evidence",
                "/static/JOB-PRIVATE/00_input.png",
            ]:
                with self.subTest(route=route):
                    self.assertEqual(self.alpha.get(route).status_code, 404)
            self.assertEqual(self.alpha.get("/api/v1/jobs/JOB-SAME/download/report").content, a_same)
            self.assertEqual(self.beta.get("/api/v1/jobs/JOB-SAME/download/report").content, b_same)
            self.assertEqual(self.alpha.get("/static/JOB-SAME/00_input.png").content, b"ALPHA-REPORT")
            self.assertEqual(self.beta.get("/static/JOB-SAME/00_input.png").content, b"BETA-REPORT")

            review = {"reviewer": "Factory QA", "decision": "DESIGN_ACCEPTED", "note": "Reviewed in company"}
            created = self.alpha.post("/api/v1/jobs/JOB-SAME/reviews",
                headers={"X-CSRF-Token": self.a_csrf}, json=review)
            self.assertEqual(created.status_code, 201, created.text)
            self.assertEqual(len(self.alpha.get("/api/v1/jobs/JOB-SAME/reviews").json()), 1)
            self.assertEqual(self.beta.get("/api/v1/jobs/JOB-SAME/reviews").json(), [])

            evidence_metadata = {"expected_report_sha256": hashlib.sha256(a_same).hexdigest(),
                "kind": "REPEAT_TEST", "source_reference": "Local QA document 1",
                "note": "Uploaded unverified in Alpha"}
            uploaded = self.alpha.post("/api/v1/jobs/JOB-SAME/evidence",
                headers={"X-CSRF-Token": self.a_csrf},
                data={"metadata": json.dumps(evidence_metadata)},
                files={"file": ("proof.pdf", b"%PDF company alpha", "application/pdf")})
            self.assertEqual(uploaded.status_code, 201, uploaded.text)
            evidence_id = uploaded.json()["evidence_id"]
            self.assertEqual(len(self.alpha.get("/api/v1/jobs/JOB-SAME/evidence").json()), 1)
            self.assertEqual(self.beta.get("/api/v1/jobs/JOB-SAME/evidence").json(), [])
            self.assertEqual(self.beta.get(
                f"/api/v1/jobs/JOB-SAME/evidence/{evidence_id}/download").status_code, 404)
            self.assertEqual(self.alpha.get(
                f"/api/v1/jobs/JOB-SAME/evidence/{evidence_id}/download").content,
                b"%PDF company alpha")

        self.assertNotEqual(
            (auth.WORKSPACE_ROOT / "alpha_co" / "jobs" / "reviews.sqlite3").read_bytes(),
            (auth.WORKSPACE_ROOT / "beta_co" / "jobs" / "reviews.sqlite3").read_bytes()
            if (auth.WORKSPACE_ROOT / "beta_co" / "jobs" / "reviews.sqlite3").exists() else b""
        )

    def test_context_does_not_leak_between_parallel_clients(self):
        self.alpha.put("/api/v1/settings", headers={"X-CSRF-Token": self.a_csrf},
                       json={"revision": 0, "company_name": "Alpha Parallel"})
        self.beta.put("/api/v1/settings", headers={"X-CSRF-Token": self.b_csrf},
                      json={"revision": 0, "company_name": "Beta Parallel"})

        def fetch(index):
            client = self.alpha if index % 2 == 0 else self.beta
            return client.get("/api/v1/settings").json()["company_name"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            result = list(pool.map(fetch, range(40)))
        for i, name in enumerate(result):
            self.assertEqual(name, "Alpha Parallel" if i % 2 == 0 else "Beta Parallel")

    def test_cannot_escape_workspace_with_symlink(self):
        directory = auth.WORKSPACE_ROOT / "alpha_co"
        # A local filesystem attacker cannot redirect a company directory to another.
        external = auth.WORKSPACE_ROOT / "beta_co"
        with tempfile.TemporaryDirectory() as temporary:
            fake_root = Path(temporary) / "root"
            fake_root.mkdir()
            try:
                (fake_root / "alpha_co").symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink creation unavailable.")
            with patch.object(auth, "WORKSPACE_ROOT", fake_root):
                token = auth.set_workspace_context("alpha_co")
                try:
                    with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                        auth.workspace_directory()
                finally:
                    auth.clear_workspace_context(token)

    def test_workspace_root_fails_closed_without_context(self):
        with self.assertRaisesRegex(RuntimeError, "No authenticated workspace"):
            auth.workspace_directory()


if __name__ == "__main__":
    unittest.main()
