"""Durable job execution and fail-closed asynchronous API regressions."""
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

from api.server import app
from core import job_runtime
from core.factory_settings import FactorySettings, save_settings
from core.preprocessing import preprocess_carpet_image


class AnalysisQueueTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def add(self, key="request_key_one", digest="0"*64):
        return job_runtime.enqueue(self.root, key, digest)

    def test_idempotency_conflicts_and_queue_limit(self):
        first, created = self.add()
        self.assertTrue(created)
        repeat, created = self.add()
        self.assertFalse(created)
        self.assertEqual(first.job_id, repeat.job_id)
        with self.assertRaisesRegex(ValueError, "different input"):
            self.add(digest="1"*64)
        for i in range(job_runtime.MAX_QUEUE-1):
            self.add(f"request_{i:06}")
        with self.assertRaises(OverflowError):
            self.add("request_overflow")
        self.assertEqual(job_runtime.cancel(self.root, first.job_id).state, "CANCELLED")
        replaced, created = self.add("request_after_cancel")
        self.assertTrue(created)
        self.assertEqual(replaced.state, "QUEUED")

    def test_restart_converts_orphan_jobs_to_failed(self):
        queued, _ = self.add()
        affected = job_runtime.recover_interrupted(self.root, force=True)
        self.assertEqual(affected, 1)
        result = job_runtime.get_status(self.root, queued.job_id)
        self.assertEqual(result.state, "FAILED")
        self.assertEqual(result.error_code, "INTERRUPTED_ON_RESTART")
        self.assertEqual(self.add()[1], False)
        new, created = self.add("request_retry_new")
        self.assertTrue(created)
        self.assertNotEqual(new.job_id, queued.job_id)

    def test_worker_stages_failure_and_cancel(self):
        first, _ = self.add()
        checkpoints = []
        job_runtime.run_bounded(self.root,first.job_id,
            lambda callback: (callback("RECTIFICATION", 15),
                              checkpoints.append("completed")))
        self.assertEqual(checkpoints, ["completed"])
        self.assertEqual(job_runtime.get_status(self.root, first.job_id).state, "SUCCEEDED")
        failed, _ = self.add("request_failure")
        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            job_runtime.run_bounded(self.root, failed.job_id,
                lambda callback: (_ for _ in ()).throw(RuntimeError("synthetic")))
        self.assertEqual(job_runtime.get_status(self.root, failed.job_id).state, "FAILED")
        self.assertEqual(job_runtime.get_status(self.root, failed.job_id).error_code,
                         "PROCESSING_FAILED")
        cancelled, _ = self.add("request_cancellation")
        def cancel_while_running(callback):
            callback("RECTIFICATION", 15)
            self.assertEqual(job_runtime.cancel(self.root, cancelled.job_id).state,
                             "CANCEL_REQUESTED")
            callback("COLOR", 50)
        with self.assertRaises(job_runtime.JobCancelled):
            job_runtime.run_bounded(self.root, cancelled.job_id, cancel_while_running)
        self.assertEqual(job_runtime.get_status(self.root, cancelled.job_id).state,
                         "CANCELLED")

    def test_explicit_grid_and_disk_boundaries(self):
        self.assertLessEqual(job_runtime.check_limits(
            width_cm=4, length_cm=4, reed=100, pick=100), 16)
        with self.assertRaises(ValueError):
            job_runtime.check_limits(
                width_cm=1000, length_cm=3000, reed=5000, pick=5000)
        test_dir=self.root/"JOB-FAKE"
        test_dir.mkdir()
        (test_dir/"big.bin").write_bytes(b"x"*40)
        with patch.object(job_runtime,"MAX_OUTPUT_BYTES",20):
            with self.assertRaisesRegex(ValueError, "512 MiB"):
                job_runtime.check_output(self.root,"JOB-FAKE")

    def test_company_specific_registry_roots(self):
        a=self.root/"company_a"
        b=self.root/"company_b"
        one,_=job_runtime.enqueue(a,"same_request_key","1"*64)
        two,_=job_runtime.enqueue(b,"same_request_key","2"*64)
        self.assertNotEqual(one.job_id,two.job_id)
        self.assertIsNone(job_runtime.get_status(a,two.job_id))
        self.assertIsNone(job_runtime.get_status(b,one.job_id))

    def test_end_to_end_background_response_and_completed_report(self):
        item=dict(code='ASYNC',name='Test Yarn',material='test fiber',
            dtex=1800,rgb=[1,1,1],lab=[50,0,0],color_source='MEASURED_LAB',
            cost_per_kg_tl=10,bobbin_weight_kg=2,stock_kg=100)
        from core import factory_settings as settings_module
        fields=dict(
            idempotency_key="async_fixture_request_1",
            loom_config=dict(width_cm=10,length_cm=10,
                reed_density=100,pick_density=100,pile_height_mm=10,
                max_colors=1,order_quantity=1,waste_coefficient=.1,
                weave_structure_factor=1.2,anchor_length_mm=3),
            preprocessing_config=dict(enable_sam_segmentation=False,
                enable_dereflection=False,enable_symmetry_completion=False),
        )
        image=np.random.default_rng(3).integers(0,255,(48,48,3),dtype=np.uint8)
        picture=cv2.imencode(".png",image)[1].tobytes()
        def small_preprocess(**kwargs):
            kwargs["target_width_px"]=32
            return preprocess_carpet_image(**kwargs)
        with patch.object(settings_module, "SETTINGS_PATH", self.root/"settings.json"), \
             patch("api.server.OUTPUT_DIR", str(self.root)), \
             patch("core.pipeline.preprocess_carpet_image",side_effect=small_preprocess):
            save_settings(FactorySettings(company_name="Queue Fixture",yarns=[item]))
            with TestClient(app) as client:
                response=client.post("/api/v1/analyze/jobs",
                    data={"config":json.dumps(fields)},
                    files={"file":("photo.png",picture,"image/png")})
                self.assertEqual(response.status_code,202,response.text)
                identifier=response.json()["job_id"]
                self.assertEqual(response.json()["state"],"QUEUED")
                # The report can only become visible after the worker is done.
                duplicate=client.post("/api/v1/analyze/jobs",
                    data={"config":json.dumps(fields)},
                    files={"file":("photo.png",picture,"image/png")})
                self.assertEqual(duplicate.status_code,202,duplicate.text)
                self.assertEqual(duplicate.json()["job_id"],identifier)
                state=None
                for _ in range(120):
                    state=client.get(f"/api/v1/jobs/{identifier}/status").json()
                    if state["state"] in {"SUCCEEDED","FAILED","CANCELLED"}:
                        break
                    time.sleep(.05)
                self.assertEqual(state["state"],"SUCCEEDED",state)
                report=client.get(f"/api/v1/jobs/{identifier}")
                self.assertEqual(report.status_code,200,report.text)
                self.assertEqual(report.json()["data_source"],"USER_FACTORY_INPUT")
                self.assertEqual(report.json()["job_id"],identifier)
                self.assertEqual(
                    client.get(f"/api/v1/jobs/{identifier}/download/report").status_code,200)
                changed=dict(fields,idempotency_key="async_fixture_request_1",
                             loom_config=dict(fields["loom_config"],order_quantity=2))
                conflict=client.post("/api/v1/analyze/jobs",
                    data={"config":json.dumps(changed)},
                    files={"file":("photo.png",picture,"image/png")})
                self.assertEqual(conflict.status_code,409)
                self.assertEqual(
                    client.get("/api/v1/jobs/JOB-FFFFFFFFFFFF/status").status_code,404)


if __name__ == "__main__":
    unittest.main()
