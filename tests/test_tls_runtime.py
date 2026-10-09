"""HTTPS fail-closed request-policy tests (not a real certificate/handshake test)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app
from core import access_control as auth
from core import tls_policy
from core.secure_server import prepare_direct_tls


class DirectTlsPolicyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for p in (
            patch.dict(os.environ, {
                "AJAN_HALI_AUTH_MODE": "workspace",
                "AJAN_HALI_DEPLOYMENT_MODE": "direct-tls",
                "AJAN_HALI_TLS_HOST": "factory.example.com",
                "AJAN_HALI_TLS_PORT": "8443",
            }),
            patch.object(auth, "AUTH_DB_PATH", self.root / "auth.sqlite3"),
            patch.object(auth, "WORKSPACE_ROOT", self.root / "workspaces"),
        ):
            p.start()
            self.addCleanup(p.stop)
        auth.create_workspace("firm_one", "Company One")
        auth.create_user("firm_admin", "a-strong-password-123", "ADMIN", "firm_one")
        self.http = TestClient(app, base_url="http://factory.example.com:8443")
        self.https = TestClient(app, base_url="https://factory.example.com:8443")
        self.addCleanup(self.http.close)
        self.addCleanup(self.https.close)

    def test_plaintext_and_host_spoofing_are_rejected(self):
        self.assertEqual(self.http.get("/api/v1/health").status_code, 403)
        self.assertEqual(self.http.post("/api/v1/auth/login",
            json={"username": "firm_admin", "password": "a-strong-password-123"}).status_code, 403)
        self.assertEqual(self.https.get("/api/v1/health",
            headers={"Host": "evil.example.com"}).status_code, 403)
        self.assertEqual(self.https.get("/api/v1/health",
            headers={"Host": "factory.example.com"}).status_code, 403)
        self.assertEqual(self.https.get("/api/v1/health",
            headers={"X-Forwarded-Proto": "https"}).status_code, 403)
        self.assertEqual(self.https.get("/api/v1/health",
            headers={"Forwarded": "for=127.0.0.1;proto=https"}).status_code, 403)

    def test_trusted_origin_secure_session_and_headers(self):
        blocked = self.https.get("/api/v1/health",
                                 headers={"Origin": "https://evil.example.com"})
        self.assertEqual(blocked.status_code, 403)
        healthy = self.https.get("/api/v1/health")
        self.assertEqual(healthy.status_code, 200)
        self.assertEqual(healthy.headers["strict-transport-security"], "max-age=31536000")
        self.assertEqual(healthy.headers["cache-control"], "no-store")
        self.assertEqual(healthy.headers["x-content-type-options"], "nosniff")
        logged = self.https.post("/api/v1/auth/login",
            json={"username": "firm_admin", "password": "a-strong-password-123"},
            headers={"Origin": "https://factory.example.com:8443"})
        self.assertEqual(logged.status_code, 200, logged.text)
        self.assertIn("secure", logged.headers["set-cookie"].lower())
        self.assertIn("httponly", logged.headers["set-cookie"].lower())
        self.assertIn("samesite=strict", logged.headers["set-cookie"].lower())
        self.assertEqual(self.https.get("/api/v1/auth/session").json()["workspace_id"], "firm_one")
        denied = self.https.put("/api/v1/settings", json={"revision": 0, "company_name": "Test"})
        self.assertEqual(denied.status_code, 403)
        accepted = self.https.put("/api/v1/settings",
            headers={"X-CSRF-Token": logged.json()["csrf_token"]},
            json={"revision": 0, "company_name": "Test Company"})
        self.assertEqual(accepted.status_code, 200, accepted.text)

    def test_invalid_environment_is_denied(self):
        for bad in ["", "localhost", "127.0.0.1", "0.0.0.0", "*.example.com", "evil..com"]:
            with self.subTest(host=bad), patch.dict(os.environ, {"AJAN_HALI_TLS_HOST": bad}):
                with self.assertRaises(RuntimeError):
                    tls_policy.tls_config()
        with patch.dict(os.environ, {"AJAN_HALI_AUTH_MODE": "local"}):
            self.assertEqual(self.https.get("/api/v1/health").status_code, 403)
            with self.assertRaises(ValueError):
                prepare_direct_tls(host="factory.example.com", bind="192.0.2.4",
                    port=8443, certfile="none", keyfile="none")
        with patch.dict(os.environ, {"AJAN_HALI_DEPLOYMENT_MODE": "unexpected"}):
            with self.assertRaises(RuntimeError):
                tls_policy.deployment_mode()


if __name__ == "__main__":
    unittest.main()
