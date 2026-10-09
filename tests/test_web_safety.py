"""Regression checks for browser-origin protection and SVG output escaping."""
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from fastapi.testclient import TestClient

from api.server import app
from core.cad_export import export_svg


class BrowserOriginTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_untrusted_origin_cannot_read_or_mutate_local_api(self):
        headers = {"Origin": "https://malicious.example"}
        self.assertEqual(self.client.get("/api/v1/health", headers=headers).status_code, 403)
        self.assertEqual(self.client.delete("/api/v1/demo/jobs", headers=headers).status_code, 403)

    def test_trusted_dev_origin_and_nonbrowser_clients(self):
        origin = "http://localhost:5173"
        preflight = self.client.options(
            "/api/v1/settings",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(preflight.status_code, 200)
        self.assertEqual(preflight.headers.get("access-control-allow-origin"), origin)
        self.assertEqual(self.client.get("/api/v1/health", headers={"Origin": origin}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/erp/reserve").status_code, 503)


class SvgEscapingTests(unittest.TestCase):
    def test_yarn_label_is_xml_data_not_markup(self):
        injected = 'Red" onclick="alert(1)" <script>alert(1)</script> & White'
        stats = [{
            "palette_index": 0,
            "palette_code": "SAFE_CODE",
            "yarn_name": injected,
            "mapped_rgb": [100, 125, 150],
        }]
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "sample.svg"
            export_svg(np.zeros((6, 6), dtype=np.uint8), stats, str(file_path))
            content = file_path.read_text(encoding="utf-8")
            self.assertIn("&quot;", content)
            self.assertIn("&lt;script&gt;", content)
            self.assertIn("&amp;", content)

            root = ElementTree.parse(file_path).getroot()
            group = root.find("{http://www.w3.org/2000/svg}g")
            self.assertIsNotNone(group)
            self.assertEqual(group.attrib["data-yarn"], injected)
            self.assertEqual(set(group.attrib), {"id", "data-yarn", "fill", "stroke", "stroke-width"})
            self.assertFalse(list(root.iter("{http://www.w3.org/2000/svg}script")))


if __name__ == "__main__":
    unittest.main()
