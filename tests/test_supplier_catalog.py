import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.server import app
from core.factory_settings import FactorySettings, YarnSettings, save_settings, load_settings
from core.supplier_catalog import SupplierProduct, SupplierCatalog, append_catalog, validate_matching_conditions


class SupplierCatalogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        for name, value in [('core.supplier_catalog.CATALOG_PATH', root/'catalog.json'),
                            ('core.factory_settings.SETTINGS_PATH', root/'settings.json')]:
            patcher = patch(name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        # Isolated regression fixtures; never copied into live company storage.
        self.product = dict(id='P1', supplier='Test supplier', product_code='A', material='Test material',
                            count_value=180, count_unit='tex', count_basis='FINISHED_YARN', source_ref='test datasheet')
        self.color = dict(id='C1', product_id='P1', color_code='R1', name='Test measured color', dye_lot='LOT1',
                          lab=[50,1,2], illuminant='D65', observer='2', device='Test instrument',
                          measured_at='2026-01-01', source_ref='test measurement report')

    def seed(self):
        response = self.client.post('/api/v1/catalog', json={'products':[self.product], 'colors':[self.color]})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_empty_catalog_and_conversions(self):
        self.assertEqual(self.client.get('/api/v1/catalog').json(), {'products':[], 'colors':[]})
        for unit, value, expected in [('dtex',1800,1800),('tex',180,1800),('denier',1620,1800),('Nm',34,294.117647)]:
            record = SupplierProduct(**dict(self.product,count_unit=unit,count_value=value))
            self.assertAlmostEqual(record.dtex, expected, places=6)
        with self.assertRaises(ValidationError):
            SupplierProduct(**dict(self.product, count_value=0))

    def test_import_retains_sources_and_rejects_conflicts_atomically(self):
        raw = json.dumps({'products':[self.product], 'colors':[self.color]}).encode()
        response = self.client.post('/api/v1/catalog/import',files={'file':('catalog.json',raw,'application/json')})
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(response.json()['products'][0]['dtex'],1800)
        self.assertEqual(response.json()['colors'][0]['dye_lot'],'LOT1')
        original = self.client.get('/api/v1/catalog').json()
        self.assertEqual(self.client.post('/api/v1/catalog',json={'products':[self.product]}).status_code,422)
        orphan = dict(self.color, id='C2', product_id='MISSING')
        self.assertEqual(self.client.post('/api/v1/catalog',json={'colors':[orphan]}).status_code,422)
        self.assertEqual(self.client.get('/api/v1/catalog').json(),original)
        self.assertEqual(self.client.post('/api/v1/catalog/import',files={'file':('bad.json',b'{')}).status_code,422)

    def yarn(self):
        return YarnSettings(code='Y1',name=self.color['name'],material=self.product['material'],dtex=1800,
                            rgb=[0,0,0],lab=self.color['lab'],color_source='MEASURED_LAB',cost_per_kg_tl=12,
                            bobbin_weight_kg=3,stock_kg=0,catalog_product_id='P1',catalog_color_id='C1',
                            catalog_snapshot={'forged':'client-supplied'})

    def test_bound_fields_and_canonical_snapshot(self):
        self.seed()
        settings = FactorySettings(company_name='Test only',yarns=[self.yarn()])
        saved = save_settings(settings)
        snapshot = load_settings().yarns[0].catalog_snapshot
        self.assertEqual(snapshot['product']['source_ref'],'test datasheet')
        self.assertEqual(snapshot['color']['observer'],'2')
        self.assertNotIn('forged', snapshot)
        settings = FactorySettings(**saved.model_dump())
        settings.yarns[0].dtex = 2000
        with self.assertRaises(ValueError):
            save_settings(settings)
        self.assertEqual(load_settings().yarns[0].dtex,1800)
        settings.yarns[0].catalog_product_id = None
        settings.yarns[0].catalog_color_id = None
        updated = save_settings(settings)
        self.assertIsNone(updated.yarns[0].catalog_snapshot)
        self.assertEqual(updated.yarns[0].cost_per_kg_tl,12)
        self.assertEqual(updated.yarns[0].stock_kg,0)

    def test_incompatible_conditions_block_analysis(self):
        self.color['illuminant'] = 'D50'
        self.seed()
        saved = save_settings(FactorySettings(company_name='Test only',yarns=[self.yarn()]))
        with self.assertRaisesRegex(ValueError,'D50/2'):
            validate_matching_conditions(saved.yarns)
        fields = dict(width_cm=10,length_cm=10,reed_density=100,pick_density=100,pile_height_mm=10,
                      max_colors=1,order_quantity=1,waste_coefficient=0,weave_structure_factor=1,anchor_length_mm=3)
        result = self.client.post('/api/v1/analyze',data=fields,files={'file':('photo.png',b'not decoded')})
        self.assertEqual(result.status_code,422)
        self.assertIn('D50/2',result.json()['detail'])

    def test_color_cannot_belong_to_another_product(self):
        self.seed()
        append_catalog(SupplierCatalog(products=[SupplierProduct(**dict(self.product,id='P2',product_code='B'))]))
        yarn = self.yarn()
        yarn.catalog_product_id = 'P2'
        with self.assertRaisesRegex(ValueError,'ait değil'):
            save_settings(FactorySettings(company_name='Test',yarns=[yarn]))


if __name__ == '__main__':
    unittest.main()
