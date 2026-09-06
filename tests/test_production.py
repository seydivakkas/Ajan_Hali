import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from fastapi.testclient import TestClient
from pydantic import ValidationError
from core.models import LoomConfig, ImagePreprocessingParams
from core.pipeline import CarpetAnalysisPipeline
from core.loom_protocols import remap_creel, dispatch_cam_file_to_loom
from core.yarn_recipe import calculate_yarn_recipe
from api.server import app

ROOT = Path(__file__).resolve().parents[1]

class ProductionRegressionTests(unittest.TestCase):
    def test_invalid_configs(self):
        for values in ({'width_cm': 0}, {'max_colors': 17}, {'order_quantity': -1},
                       {'pile_height_mm': float('nan')}, {'width_cm': 1000, 'length_cm': 3000}):
            with self.assertRaises(ValidationError):
                LoomConfig(**values)

    def test_sparse_creel(self):
        grid = np.array([[12, 3], [3, 12]])
        actual = remap_creel(grid, [{'palette_index': 3}, {'palette_index': 12}])
        np.testing.assert_array_equal(actual, [[1, 0], [0, 1]])
        with self.assertRaises(ValueError):
            remap_creel(grid, [{'palette_index': 3}])

    def test_recipe_discrete_knots(self):
        cfg = LoomConfig(width_cm=101, length_cm=101, reed_density=51, pick_density=51, order_quantity=1)
        palette = json.loads((ROOT / 'palette/factory_palette.json').read_text(encoding='utf-8'))['colors']
        color = palette[0]
        recipe, _ = calculate_yarn_recipe(cfg, [{'palette_code': color['code'], 'yarn_name': color['name'], 'area_percentage': 100}], palette)
        expected = 52 * 52 * (2 * .0115 * 1.18 + .0032)
        self.assertEqual(recipe[0].yarn_length_m_per_carpet, round(expected, 1))

    def test_pipeline_history_and_input_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = CarpetAnalysisPipeline(str(ROOT / 'palette/factory_palette.json'), directory)
            rng = np.random.default_rng(42)
            photo = rng.integers(0, 255, (48, 48, 3), dtype=np.uint8)
            result = pipeline.process(photo, LoomConfig(width_cm=10, length_cm=10, reed_density=100, pick_density=100, order_quantity=3),
                                      ImagePreprocessingParams(target_width_px=32, enable_sam_segmentation=False, enable_dereflection=False, manual_corners=[[0,0],[1,0],[1,1],[0,1]], repair_regions=[[.1,.1,.25,.25]]), 'TEST-JOB')
            self.assertTrue(Path(result.input_image_path).is_file())
            from core.utils import imread_safe
            repair_mask = imread_safe(result.repair_mask_path)[:,:,0]
            self.assertGreater(np.count_nonzero(repair_mask), 0)
            self.assertLess(np.count_nonzero(repair_mask), repair_mask.size / 4)
            self.assertEqual(result.preprocessing_metadata["segmentation_engine"], "MANUAL_CORNERS")
            self.assertEqual(sum(c.pixel_count for c in result.color_mappings), 100)
            self.assertEqual(result.loom_config.order_quantity, 3)
            self.assertEqual(result.total_bobbins_required, sum(r.bobbin_count_required for r in result.yarn_recipe))
            self.assertEqual(dispatch_cam_file_to_loom(result.vdw_ep_export_path, '127.0.0.1')['status'], 'SIMULATED')
            result.data_source = 'USER_FACTORY_INPUT'
            Path(directory, 'TEST-JOB', 'analysis_report.json').write_text(result.model_dump_json(), encoding='utf-8')
            with patch('api.server.OUTPUT_DIR', directory):
                client = TestClient(app)
                self.assertEqual(client.get('/api/v1/jobs').json()[0]['job_id'], 'TEST-JOB')
                self.assertEqual(client.get('/api/v1/jobs/TEST-JOB').json()['loom_config']['order_quantity'], 3)
                self.assertEqual(client.get('/api/v1/jobs/TEST-JOB/download/report').status_code, 200)
                self.assertEqual(client.get('/api/v1/jobs/invalid.id').status_code, 400)
                review = client.post('/api/v1/jobs/TEST-JOB/reviews', json={'reviewer':'Test Designer','decision':'CHANGES_REQUESTED','note':'Renk kontrol edilmeli.'})
                self.assertEqual(review.status_code, 201)
                self.assertEqual(len(review.json()['report_sha256']), 64)
                self.assertEqual(len(client.get('/api/v1/jobs/TEST-JOB/reviews').json()), 1)
                self.assertEqual(client.post('/api/v1/jobs/MISSING/reviews', json={'reviewer':'Test','decision':'DESIGN_ACCEPTED','note':'Test note'}).status_code, 404)

    def test_manual_geometry_validation(self):
        for corners in ([[0,0],[1,1],[1,0],[0,1]], [[0,0]]*4, [[0,0],[2,0],[1,1],[0,1]]):
            with self.assertRaises(ValidationError):
                ImagePreprocessingParams(manual_corners=corners)
        with self.assertRaises(ValidationError):
            ImagePreprocessingParams(repair_regions=[[.8,.2,.1,.4]])
        with self.assertRaises(ValidationError):
            ImagePreprocessingParams(repair_regions=[[.1,.1,.2,.2]], enable_symmetry_completion=False)

    def test_manual_homography_and_mask(self):
        from core.preprocessing import preprocess_carpet_image
        import cv2
        photo = np.zeros((101, 101, 3), dtype=np.uint8)
        corners = [[.2,.2],[.8,.2],[.8,.8],[.2,.8]]
        _, _, meta = preprocess_carpet_image(photo, 61, 1, False, False, corners)
        self.assertEqual(meta['segmentation_engine'], 'MANUAL_CORNERS')
        mapped = cv2.perspectiveTransform(np.array([[[20.,20.],[80.,80.]]], dtype=np.float32), np.array(meta['homography_matrix']))
        np.testing.assert_allclose(mapped, [[[0,0],[60,60]]], atol=.001)

    def test_vertical_symmetry_uses_vertical_source(self):
        from core.inpainting import complete_pattern_with_symmetry
        photo = np.zeros((10,10,3), dtype=np.uint8)
        photo[2,7] = [255,0,0]
        photo[7,2] = [0,255,0]
        mask = np.zeros((10,10), dtype=np.uint8)
        mask[2,2] = 255
        result, _, _ = complete_pattern_with_symmetry(photo, mask, 'VERTICAL')
        np.testing.assert_array_equal(result[2,2], [0,255,0])

    def test_upload_rejection(self):
        client = TestClient(app)
        self.assertEqual(client.get('/api/v1/jobs/demo').status_code, 410)
        self.assertEqual(client.get('/api/v1/erp/inventory').json()['status'], 'MANUAL_INPUT')
        self.assertEqual(client.post('/api/v1/erp/reserve').status_code, 503)
        self.assertEqual(client.post('/api/v1/loom/dispatch').status_code, 409)
        response = client.post('/api/v1/analyze', files={'file': ('bad.png', b'hello')})
        self.assertEqual(response.status_code, 422)

    def test_company_settings_require_real_fields(self):
        from core.factory_settings import FactorySettings, YarnSettings, save_settings, load_settings
        item = dict(code='TEST',name='Test input',material='test fiber',dtex=1800,rgb=[0,0,0],lab=[50,0,0],color_source='MEASURED_LAB',cost_per_kg_tl=10,bobbin_weight_kg=2,stock_kg=0)
        with self.assertRaises(ValidationError):
            YarnSettings(**{k:v for k,v in item.items() if k != 'stock_kg'})
        with self.assertRaises(ValidationError):
            FactorySettings(yarns=[item,item])
        with self.assertRaises(ValidationError):
            YarnSettings(**dict(item, cost_per_kg_tl=-1))
        with self.assertRaises(ValidationError):
            FactorySettings(looms=[dict(name='Test',controller_model='Test',ip='invalid')])
        with tempfile.TemporaryDirectory() as directory, patch('core.factory_settings.SETTINGS_PATH', Path(directory)/'settings.json'):
            self.assertEqual(load_settings().yarns, [])
            saved = save_settings(FactorySettings(company_name='Unit test',yarns=[item]))
            self.assertEqual(saved.revision, 1)
            self.assertEqual(load_settings().yarns[0].stock_kg, 0)
            with self.assertRaises(ValueError):
                save_settings(FactorySettings())

    def test_live_upload_and_reprice_use_saved_factory_data(self):
        import cv2
        from core.factory_settings import FactorySettings, save_settings
        from core.preprocessing import preprocess_carpet_image
        item = dict(code='CUSTOM',name='Test input',material='test fiber',dtex=1800,rgb=[0,0,0],lab=[50,0,0],color_source='MEASURED_LAB',cost_per_kg_tl=10,bobbin_weight_kg=2,stock_kg=0)
        fields = dict(width_cm='10',length_cm='10',reed_density='100',pick_density='100',pile_height_mm='10',max_colors='1',order_quantity='5',waste_coefficient='0.1',weave_structure_factor='1.2',anchor_length_mm='3',enable_sam='false',enable_dereflection='false',enable_symmetry='false')
        def small_preprocess(**kwargs):
            kwargs['target_width_px'] = 32
            return preprocess_carpet_image(**kwargs)
        with tempfile.TemporaryDirectory() as directory, patch('core.factory_settings.SETTINGS_PATH', Path(directory)/'settings.json'), patch('api.server.OUTPUT_DIR', directory), patch('core.pipeline.preprocess_carpet_image', side_effect=small_preprocess):
            client = TestClient(app)
            self.assertEqual(client.get('/api/v1/settings').json()['yarns'], [])
            settings = save_settings(FactorySettings(company_name='Unit test only',yarns=[item]))
            photo = np.random.default_rng(22).integers(0,255,(48,48,3),dtype=np.uint8)
            image_bytes = cv2.imencode('.png',photo)[1].tobytes()
            response = client.post('/api/v1/analyze',data=fields,files={'file':('input.png',image_bytes,'image/png')})
            self.assertEqual(response.status_code, 200, response.text)
            report = response.json()
            self.assertEqual(report['data_source'], 'USER_FACTORY_INPUT')
            self.assertEqual(report['factory_settings_revision'], 1)
            self.assertEqual(report['palette_snapshot'][0]['stock_kg'], 0)
            self.assertFalse(report['yarn_recipe'][0]['is_stock_sufficient'])
            job_id = report['job_id']
            original = Path(directory,job_id,'analysis_report.json').read_bytes()
            first = client.post(f'/api/v1/jobs/{job_id}/quote').json()
            settings.yarns[0].cost_per_kg_tl = 20
            save_settings(settings)
            second = client.post(f'/api/v1/jobs/{job_id}/quote').json()
            self.assertEqual(second['revision'], 2)
            self.assertAlmostEqual(second['summary']['total_order_cost_tl'], first['summary']['total_order_cost_tl']*2, delta=.02)
            self.assertEqual(Path(directory,job_id,'analysis_report.json').read_bytes(), original)
            legacy = dict(report, data_source='UNVERIFIED_LEGACY')
            Path(directory,job_id,'analysis_report.json').write_text(json.dumps(legacy),encoding='utf-8')
            self.assertEqual(client.get('/api/v1/jobs').json(), [])
            self.assertEqual(client.get(f'/static/{job_id}/00_input.png').status_code, 410)
            self.assertEqual(client.get(f'/api/v1/jobs/{job_id}/download/report').status_code, 410)

    def test_missing_lab_does_not_generate_measurements(self):
        from core.measurements import parse_explicit_lab
        self.assertEqual(parse_explicit_lab('<Sample Name="Test"><CIELab><L>50</L></CIELab></Sample>', 'x.cxf'), [])
        self.assertEqual(parse_explicit_lab('NAME: Test\nSPECTRUM: 1 2 3', 'x.qtx'), [])
        samples = parse_explicit_lab('<Sample Name="Test"><CIELab><L>50</L><A>1</A><B>2</B></CIELab></Sample>', 'x.cxf')
        self.assertEqual(samples[0]['lab'], [50,1,2])

if __name__ == '__main__':
    unittest.main()
