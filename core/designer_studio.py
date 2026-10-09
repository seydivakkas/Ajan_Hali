"""Versioned, palette-indexed loom documents. Masters are candidates, never CAM approval."""
import hashlib
import json
import sqlite3
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from core.yarn_recipe import calculate_yarn_recipe

Cell = Annotated[int, Field(strict=True, ge=-1, le=255)]
MAX_CELLS = 2_000_000


class Layer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    role: Literal['BASE', 'MOTIF', 'BORDER', 'FIELD', 'MEDALLION'] = 'MOTIF'
    visible: bool = True
    x: int = Field(ge=0, le=10000)
    y: int = Field(ge=0, le=10000)
    width: int = Field(ge=1, le=10000)
    height: int = Field(ge=1, le=10000)
    cells: list[Cell] = Field(max_length=MAX_CELLS)


class StudioDocument(BaseModel):
    model_config = ConfigDict(extra='forbid')
    width: int = Field(ge=1, le=10000)
    height: int = Field(ge=1, le=10000)
    layers: list[Layer] = Field(min_length=1, max_length=16)
    colorway: list[Annotated[int, Field(strict=True, ge=0, le=255)]] = Field(min_length=1, max_length=256)

    @model_validator(mode='after')
    def geometry(self):
        if self.width*self.height > MAX_CELLS or sum(len(l.cells) for l in self.layers) > 4*MAX_CELLS:
            raise ValueError('V1.1 belge sınırı: 2 milyon düğüm, toplam 8 milyon katman hücresi.')
        if len({l.id for l in self.layers}) != len(self.layers):
            raise ValueError('Katman kimlikleri benzersiz olmalı.')
        for layer in self.layers:
            if len(layer.cells) != layer.width*layer.height or layer.x+layer.width > self.width or layer.y+layer.height > self.height:
                raise ValueError('Katman boyutu veya konumu matrisle uyuşmuyor.')
            if any(c >= len(self.colorway) for c in layer.cells):
                raise ValueError('Katmanda bilinmeyen iplik indeksi var.')
        base = self.layers[0]
        if not base.visible or base.x or base.y or base.width != self.width or base.height != self.height or -1 in base.cells or base.role != 'BASE':
            raise ValueError('İlk katman tüm matrisi kaplayan görünür, opak BASE olmalı.')
        return self


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    parent_revision: int = Field(ge=0)
    author: str = Field(min_length=2, max_length=100)
    note: str = Field(min_length=3, max_length=1000)
    kind: Literal['DRAFT', 'MASTER_CANDIDATE'] = 'DRAFT'
    document: StudioDocument


def initial_document(directory: Path, report):
    width, height = report.grid_resolution_cells
    if width*height > MAX_CELLS:
        raise ValueError('V1.1 Studio en fazla 2 milyon düğüm açar; matris küçültülmedi.')
    if not report.palette_snapshot or not report.loom_config:
        raise ValueError('Bu analizde kaynak palet veya tezgâh parametreleri yok; yeniden analiz edin.')
    path = directory / f'{report.job_id}_loom_matrix.txt'
    if not path.is_file():
        raise ValueError('Kaynak düğüm matrisi bulunamadı.')
    grid = np.loadtxt(path, comments='#', dtype=np.int32, ndmin=2)
    if grid.shape != (height,width):
        raise ValueError('Kaynak matris boyutu raporla uyuşmuyor.')
    return StudioDocument(width=width,height=height,colorway=list(range(len(report.palette_snapshot))),
                          layers=[Layer(id='base',name='AI taslak',role='BASE',x=0,y=0,width=width,height=height,cells=grid.ravel().tolist())])


def compose(document: StudioDocument, report):
    if (document.width,document.height) != tuple(report.grid_resolution_cells):
        raise ValueError('Belge boyutu kaynak tezgâh matrisiyle aynı olmalı.')
    if len(document.colorway) != len(report.palette_snapshot) or any(c >= len(report.palette_snapshot) for c in document.colorway):
        raise ValueError('Colorway kaynak palete ait olmalı.')
    grid = np.zeros((document.height,document.width),dtype=np.int32)
    for layer in document.layers:
        if layer.visible:
            cells = np.asarray(layer.cells,dtype=np.int32).reshape(layer.height,layer.width)
            target = grid[layer.y:layer.y+layer.height,layer.x:layer.x+layer.width]
            mask = cells >= 0
            target[mask] = cells[mask]
    return np.asarray(document.colorway,dtype=np.int32)[grid]


def evaluate(document, report):
    grid = compose(document,report)
    colors, counts = np.unique(grid,return_counts=True)
    stats = [{'palette_code':report.palette_snapshot[int(c)]['code'],
              'yarn_name':report.palette_snapshot[int(c)]['name'],
              'pixel_count':int(n),'area_percentage':int(n)/grid.size*100} for c,n in zip(colors,counts)]
    recipe, summary = calculate_yarn_recipe(report.loom_config,stats,report.palette_snapshot)
    blocked = []
    if report.data_source == 'DEMO_SYNTHETIC' or any(p.get('is_demo') or p.get('color_source') == 'DEMO_SYNTHETIC' for p in report.palette_snapshot):
        blocked.append('Demo kaynak: üretimde kullanılamaz.')
    if len(colors) > report.loom_config.max_colors:
        blocked.append('Aktif renk sayısı cağlık kapasitesini aşıyor.')
    if any(not r.is_stock_sufficient for r in recipe):
        blocked.append('Kaynak stok anlık görüntüsünde iplik eksikliği var.')
    return {'recipe':[r.model_dump(mode='json') for r in recipe], 'summary':summary,
            'color_counts':stats, 'grid_sha256':hashlib.sha256(grid.astype('<u2').tobytes()).hexdigest(),
            'seam':{'left_right_mismatch_cells':int(np.count_nonzero(grid[:,0]!=grid[:,-1])),
                    'top_bottom_mismatch_cells':int(np.count_nonzero(grid[0,:]!=grid[-1,:])),
                    'note':'Karşılıklı kenar indeks farkı; tek başına raport uygunluk testi değildir.'},
            'gate':{'status':'BLOCKED' if blocked else 'REVIEW_REQUIRED', 'reasons':blocked,
                    'pending':['Düzenleme sonrası hedef/numune renk ölçümü', 'Raport ve desinatör kontrolü',
                               'Güncel lot/stok doğrulaması', 'Tezgâh profili ve üretici CAM doğrulaması'],
                    'approved':False},
            'source':'Kaynak analizdeki palet, fiyat ve stok anlık görüntüsü; gerçek tüketimle kalibre edilmedi.',
            'delta_e_status':'NOT_REMEASURED_AFTER_EDIT'}


def connection(directory):
    db=sqlite3.connect(directory/'studio.sqlite3',timeout=15)
    db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS revisions (revision INTEGER PRIMARY KEY, parent_revision INTEGER, created_at TEXT, author TEXT, note TEXT, kind TEXT, payload BLOB, sha256 TEXT)')
    return db


def revisions(directory):
    with connection(directory) as db:
        result=[dict(r) for r in db.execute('SELECT revision,parent_revision,created_at,author,note,kind,sha256 FROM revisions ORDER BY revision DESC')]
    db.close()
    return result


def read_revision(directory, revision):
    with connection(directory) as db:
        row=db.execute('SELECT payload, sha256 FROM revisions WHERE revision=?',(revision,)).fetchone()
    db.close()
    if row is None:
        raise ValueError('Revizyon bulunamadı.')
    raw = zlib.decompress(row['payload'])
    if hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise ValueError('Stüdyo revizyonunun bütünlük doğrulaması başarısız.')
    return json.loads(raw)


def save_revision(directory, report, request):
    evaluation=evaluate(request.document,report)
    db=connection(directory)
    try:
        db.execute('BEGIN IMMEDIATE')
        latest=db.execute('SELECT COALESCE(MAX(revision),0) FROM revisions').fetchone()[0]
        if latest!=request.parent_revision:
            raise ValueError('Başka bir oturum revizyon kaydetti. Taslağınızı indirin ve güncel revizyonu açın.')
        revision=latest+1
        payload={'job_id':report.job_id,'revision':revision,'parent_revision':latest,
                 'created_at':datetime.now(timezone.utc).isoformat(),'author':request.author,'note':request.note,
                 'kind':request.kind,'data_source':report.data_source,
                 'document':request.document.model_dump(),'palette':report.palette_snapshot,
                 'loom_config':report.loom_config.model_dump(),'evaluation':evaluation}
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        digest=hashlib.sha256(raw).hexdigest()
        db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?)',
                   (revision,latest,payload['created_at'],request.author,request.note,request.kind,zlib.compress(raw),digest))
        db.commit()
        return {**payload,'sha256':digest}
    finally:
        db.close()
