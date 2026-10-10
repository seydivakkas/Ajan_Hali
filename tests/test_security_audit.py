"""Per-company security audit: record allowed and denied writes without secrets."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core import access_control as auth
from core import security_audit


class AuditSecurityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for p in (
            patch.object(auth, "AUTH_DB_PATH", root/"auth.sqlite3"),
            patch.object(auth, "WORKSPACE_ROOT", root/"workspaces"),
            patch.dict(os.environ, {"AJAN_HALI_AUTH_MODE": "workspace"}),
        ):
            p.start()
            self.addCleanup(p.stop)
        for tenant in ("company_alpha", "company_beta"):
            auth.create_workspace(tenant, tenant)
        auth.create_user("admin_alpha", "strong-alpha-password", "ADMIN", "company_alpha")
        auth.create_user("operator_beta", "strong-beta-password", "OPERATOR", "company_beta")
        self.alpha = TestClient(app)
        self.beta = TestClient(app)
        self.addCleanup(self.alpha.close)
        self.addCleanup(self.beta.close)
        a = self.alpha.post("/api/v1/auth/login",
                            json={"username":"admin_alpha", "password":"strong-alpha-password"})
        b = self.beta.post("/api/v1/auth/login",
                           json={"username":"operator_beta", "password":"strong-beta-password"})
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        self.csrf_a = a.json()["csrf_token"]
        self.csrf_b = b.json()["csrf_token"]
        self.alpha_db = root/"workspaces"/"company_alpha"/"jobs"
        self.beta_db = root/"workspaces"/"company_beta"/"jobs"

    def test_audits_writes_and_denials_scoped_without_passwords(self):
        changed = self.alpha.put("/api/v1/settings",
            json={"revision": 0, "company_name": "Alpha"},
            headers={"X-CSRF-Token": self.csrf_a})
        self.assertEqual(changed.status_code, 200, changed.text)
        blocked = self.beta.put("/api/v1/settings",
            json={"revision": 0, "company_name": "Beta"},
            headers={"X-CSRF-Token": self.csrf_b})
        self.assertEqual(blocked.status_code, 403)
        first = security_audit.list_events(self.alpha_db)
        second = security_audit.list_events(self.beta_db)
        self.assertEqual([x.phase for x in first], ["RESULT", "ATTEMPT"])
        self.assertEqual([x.status for x in first], [200, None])
        self.assertEqual([x.status for x in second], [403, None])
        self.assertEqual(first[0].username, "admin_alpha")
        self.assertEqual(second[0].username, "operator_beta")
        self.assertTrue(all(x.resource == "/api/v1/settings" for x in first+second))
        self.assertNotIn("strong-alpha-password", (self.alpha_db/"reviews.sqlite3").read_bytes().decode("latin1"))
        self.assertNotIn("strong-beta-password", (self.beta_db/"reviews.sqlite3").read_bytes().decode("latin1"))
        self.assertNotIn("Alpha", (self.alpha_db/"reviews.sqlite3").read_bytes().decode("latin1"))

    def test_audit_query_values_are_not_retained(self):
        ret = self.alpha.get("/api/v1/jobs/JOB-SECRET/download/report",
                             params={"password":"never_log_me"})
        self.assertEqual(ret.status_code, 404)
        events = security_audit.list_events(self.alpha_db)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].status, 404)
        self.assertEqual(events[0].resource, "/api/v1/jobs/JOB-SECRET/download/report")
        self.assertNotIn("never_log_me", (self.alpha_db/"reviews.sqlite3").read_bytes().decode("latin1"))

    def test_event_schema_blocks_malicious_paths(self):
        with self.assertRaises(ValueError):
            security_audit.write_event(jobs_dir=self.alpha_db, username="admin_alpha",
                role="ADMIN", method="POST", path="/api/v1/settings\nINJECT", phase="ATTEMPT")
        with self.assertRaises(ValueError):
            security_audit.write_event(jobs_dir=self.alpha_db, username="admin_alpha",
                role="ADMIN", method="POST", path="/api/v1/settings", phase="DONE")
        self.assertEqual(security_audit.list_events(self.alpha_db), [])


if __name__ == "__main__":
    unittest.main()
