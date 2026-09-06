import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from pydantic import ValidationError
from api.server import app
from core import designer_studio as studio
from core.demo_data import demo_yarns
from core.models import LoomConfig


class DesignerStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.report=SimpleNamespace(job_id='STUDIO_TEST',grid_resolution_cells=(4,3),
            palette_snapshot=[y.model_dump() for y in demo_yarns()],data_source='DEMO_SYNTHETIC',
            loom_config=LoomConfig(width_cm=4,length_cm=3,reed_density=100,pick_density=100,max_colors=4))
        self.document=studio.StudioDocument(width=4,height=3,colorway=[0,1,2,3],layers=[studio.Layer(
            id='base',name='Base',role='BASE',visible=True,x=0,y=0,width=4,height=3,cells=[0]*12)])

    def request(self,document=None,parent=0,kind='DRAFT'):
        return studio.RevisionRequest(document=document or self.document,parent_revision=parent,author='Test designer',note='Unit test',kind=kind)

    def test_overlay_transparency_colorway_and_recipe_counts(self):
        document=self.document.model_copy(deep=True)
        document.layers.append(studio.Layer(id='motif',name='Motif',x=1,y=1,width=2,height=2,cells=[1,-1,1,1]))
        document.colorway=[0,2,1,3]
        expected=np.array([[0,0,0,0],[0,2,0,0],[0,2,2,0]])
        np.testing.assert_array_equal(studio.compose(document,self.report),expected)
        result=studio.evaluate(document,self.report)
        self.assertEqual([c['pixel_count'] for c in result['color_counts']],[9,3])
        self.assertAlmostEqual(sum(c['area_percentage'] for c in result['color_counts']),100)
        self.assertEqual(result['gate']['status'],'BLOCKED')
        self.assertFalse(result['gate']['approved'])
        self.assertEqual(result['delta_e_status'],'NOT_REMEASURED_AFTER_EDIT')
        document.layers[1].visible=False
        self.assertEqual(np.count_nonzero(studio.compose(document,self.report)),0)

    def test_immutable_revisions_conflict_and_master_candidate(self):
        first=studio.save_revision(self.root,self.report,self.request(kind='MASTER_CANDIDATE'))
        self.assertEqual(first['revision'],1)
        old=studio.read_revision(self.root,1)
        changed=self.document.model_copy(deep=True)
        changed.layers[0].cells[0]=1
        with self.assertRaises(ValueError):
            studio.save_revision(self.root,self.report,self.request(changed,parent=0))
        self.assertEqual(len(studio.revisions(self.root)),1)
        second=studio.save_revision(self.root,self.report,self.request(changed,parent=1))
        self.assertNotEqual(first['evaluation']['grid_sha256'],second['evaluation']['grid_sha256'])
        self.assertEqual(studio.read_revision(self.root,1),old)
        self.assertNotEqual(first['sha256'],second['sha256'])

    def test_invalid_geometry_palette_and_capacity(self):
        raw=self.document.model_dump()
        raw['layers'][0]['cells'][0]=-1
        with self.assertRaises(ValidationError):studio.StudioDocument(**raw)
        raw=self.document.model_dump()
        raw['layers'][0]['x']=1
        with self.assertRaises(ValidationError):studio.StudioDocument(**raw)
        raw=self.document.model_dump()
        raw['layers'][0]['cells'][0]=1.5
        with self.assertRaises(ValidationError):studio.StudioDocument(**raw)
        bad=self.document.model_copy(deep=True)
        bad.colorway[0]=20
        with self.assertRaises(ValueError):studio.evaluate(bad,self.report)
        self.report.data_source='USER_FACTORY_INPUT'
        self.report.loom_config.max_colors=1
        bad=self.document.model_copy(deep=True)
        bad.layers[0].cells[0]=1
        self.assertEqual(studio.evaluate(bad,self.report)['gate']['status'],'BLOCKED')

    def test_api_roundtrip_source_matrix_unchanged(self):
        job=self.root/self.report.job_id
        job.mkdir()
        matrix=job/f'{self.report.job_id}_loom_matrix.txt'
        matrix.write_text('# HEADER\n0 0 2 2\n0 0 2 2\n0 0 2 2\n')
        before=matrix.read_bytes()
        client=TestClient(app)
        with patch('api.server.get_job',return_value=self.report),patch('api.server.OUTPUT_DIR',str(self.root)):
            url=f'/api/v1/jobs/{self.report.job_id}/studio'
            initial=client.get(url)
            self.assertEqual(initial.status_code,200,initial.text)
            document=studio.StudioDocument(**initial.json()['document'])
            self.assertEqual(document.layers[0].cells,[0,0,2,2]*3)
            saved=client.post(url+'/revisions',json=self.request(document).model_dump())
            self.assertEqual(saved.status_code,201,saved.text)
            self.assertEqual(client.get(url).json()['revision'],1)
            self.assertEqual(client.get(url+'/revisions/1').json()['document'],document.model_dump())
            self.assertEqual(client.get(url+'/revisions/999').status_code,404)
            self.assertEqual(client.post(url+'/revisions',json=self.request(document).model_dump()).status_code,409)
        self.assertEqual(matrix.read_bytes(),before)
