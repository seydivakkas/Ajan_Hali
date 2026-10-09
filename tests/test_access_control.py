"""Single-tenant localhost session and role regressions.

Security tests run against an isolated SQLite auth database and do not create
accounts, change credentials or grant access on the developer's machine.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core import access_control as auth


class LocalAuthTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_patch = patch.object(auth, "AUTH_DB_PATH", Path(directory.name) / "auth.sqlite3")
        db_patch.start()
        self.addCleanup(db_patch.stop)
        env_patch = patch.dict(os.environ, {"AJAN_HALI_AUTH_MODE": "session"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        auth.create_user("admin1", "strong-admin-pass-123", "ADMIN")
        auth.create_user("designer1", "strong-designer-pass-123", "DESIGNER")
        auth.create_user("operator1", "strong-operator-pass-123", "OPERATOR")

    def login(self, username, password):
        return self.client.post("/api/v1/auth/login",
                                json={"username": username, "password": password})

    def test_unauthenticated_requests_fail_closed(self):
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/settings").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/jobs").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 401)
        self.assertEqual(self.client.delete("/api/v1/demo/jobs").status_code, 401)
        self.assertEqual(self.login("admin1", "wrong").status_code, 401)

    def test_admin_session_csrf_and_logout(self):
        logged_in = self.login("admin1", "strong-admin-pass-123")
        self.assertEqual(logged_in.status_code, 200, logged_in.text)
        self.assertIn("httponly", logged_in.headers["set-cookie"].lower())
        self.assertIn("samesite=strict", logged_in.headers["set-cookie"].lower())
        token = logged_in.json()["csrf_token"]
        self.assertEqual(self.client.get("/api/v1/auth/session").json()["role"], "ADMIN")
        self.assertEqual(self.client.delete("/api/v1/demo/jobs").status_code, 403)
        # Admin is authorized but the supplied revision is invalid: endpoint validation is reached.
        result = self.client.put("/api/v1/settings", headers={"X-CSRF-Token": token}, json={})
        self.assertNotEqual(result.status_code, 401)
        self.assertNotEqual(result.status_code, 403)
        self.assertEqual(self.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 401)

    def test_designer_can_submit_design_but_not_change_settings(self):
        token = self.login("designer1", "strong-designer-pass-123").json()["csrf_token"]
        self.assertEqual(self.client.put("/api/v1/settings", headers={"X-CSRF-Token": token}, json={}).status_code, 403)
        # Authorization succeeds for designer, then nonexistent job is rejected by handler.
        result = self.client.post("/api/v1/jobs/UNKNOWN/reviews",
                                  headers={"X-CSRF-Token": token},
                                  json={"reviewer": "Designer", "decision": "DESIGN_ACCEPTED",
                                        "note": "Review text"})
        self.assertEqual(result.status_code, 404)

    def test_operator_is_readonly_and_limited(self):
        token = self.login("operator1", "strong-operator-pass-123").json()["csrf_token"]
        self.assertEqual(self.client.get("/api/v1/auth/session").json()["role"], "OPERATOR")
        self.assertEqual(self.client.get("/api/v1/settings").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/jobs").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/analyze", headers={"X-CSRF-Token": token}).status_code, 403)

    def test_disabling_user_revokes_existing_session(self):
        self.assertEqual(self.login("designer1", "strong-designer-pass-123").status_code, 200)
        auth.disable_user("designer1")
        self.assertEqual(self.client.get("/api/v1/auth/session").status_code, 401)
        self.assertEqual(self.login("designer1", "strong-designer-pass-123").status_code, 401)

    def test_bad_host_or_origin_rejected(self):
        self.assertEqual(self.client.get("/api/v1/health", headers={"Host": "bad.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/health", headers={"Origin": "https://bad.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/health", headers={"Host": "127.0.0.1:8001"}).status_code, 200)

    def test_creation_guards(self):
        with self.assertRaises(ValueError):
            auth.create_user("x", "too-short", "ADMIN")
        with self.assertRaises(ValueError):
            auth.create_user("designer1", "strong-designer-pass-123", "DESIGNER")


if __name__ == "__main__":
    unittest.main()
