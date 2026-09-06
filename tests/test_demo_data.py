import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient
from api.server import app
from core.factory_settings import FactorySettings, save_settings
from core.demo_data import demo_yarns


class DemoTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name, value in [('core.factory_settings.SETTINGS_PATH', self.root/'settings.json'),
                            ('core.supplier_catalog.CATALOG_PATH', self.root/'catalog.json'),
                            ('api.server.OUTPUT_DIR', str(self.root))]:
            p = patch(name, value)
            p.start()
            self.addCleanup(p.stop)
        self.client = TestClient(app)

    def test_install_remove_preserves_company_and_real_inventory(self):
        real = demo_yarns()[0].model_copy(update={'code':'REAL', 'is_demo':False, 'color_source':'MEASURED_LAB'})
        saved = save_settings(FactorySettings(company_name='Test company', yarns=[real]))
        before = saved.yarns[0].model_dump()
        response = self.client.post('/api/v1/demo/inventory', json={'revision':saved.revision})
        self.assertEqual(response.status_code, 200, response.text)
        installed = response.json()
        self.assertEqual(len(installed['yarns']), 5)
        again = self.client.post('/api/v1/demo/inventory', json={'revision':installed['revision']})
        self.assertEqual(len(again.json()['yarns']), 5)
        self.assertEqual(self.client.request('DELETE', '/api/v1/demo/inventory', json={'revision':0}).status_code,409)
        removed = self.client.request('DELETE', '/api/v1/demo/inventory', json={'revision':installed['revision']}).json()
        self.assertEqual(removed['company_name'], 'Test company')
        self.assertEqual(removed['yarns'], [dict(before, rgb=list(before['rgb']), lab=list(before['lab']))])
        self.assertFalse((self.root/'catalog.json').exists())

    def test_demo_analysis_provenance_download_and_selective_cleanup(self):
        self.client.post('/api/v1/demo/inventory', json={'revision':0})
        from core.preprocessing import preprocess_carpet_image
        def small(**kwargs):
            kwargs['target_width_px'] = 32
            return preprocess_carpet_image(**kwargs)
        fields = dict(width_cm=10,length_cm=10,reed_density=100,pick_density=100,pile_height_mm=10,
                      max_colors=4,order_quantity=1,waste_coefficient=.07,weave_structure_factor=1,
                      anchor_length_mm=2,enable_sam='false',enable_dereflection='false',enable_symmetry='false')
        photo = np.random.default_rng(3).integers(0,255,(48,48,3),dtype=np.uint8)
        with patch('core.pipeline.preprocess_carpet_image', side_effect=small):
            res = self.client.post('/api/v1/analyze',data=fields,files={'file':('test.png',cv2.imencode('.png',photo)[1].tobytes(),'image/png')})
        self.assertEqual(res.status_code,200,res.text)
        report = res.json()
        self.assertEqual(report['data_source'],'DEMO_SYNTHETIC')
        self.assertEqual(report['production_audit']['status'],'NOT_PRODUCTION_SAFE')
        job = report['job_id']
        download = self.client.get(f'/api/v1/jobs/{job}/download/report')
        self.assertIn('DEMO_',download.headers['content-disposition'])
        # A distinct non-demo report and unrelated file must survive cleanup.
        import json
        real = self.root/'REAL_JOB'
        real.mkdir()
        (real/'analysis_report.json').write_text(json.dumps(dict(report,job_id='REAL_JOB',data_source='USER_FACTORY_INPUT')),encoding='utf-8')
        (self.root/'keep.txt').write_text('keep')
        self.assertEqual(self.client.delete('/api/v1/demo/jobs').json()['removed'],1)
        self.assertFalse((self.root/job).exists())
        self.assertTrue((real/'analysis_report.json').exists())
        self.assertTrue((self.root/'keep.txt').exists())
        self.assertEqual(self.client.delete('/api/v1/demo/jobs').json()['removed'],0)
