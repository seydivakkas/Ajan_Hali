"""User-supplied, source-attributed yarn products and measured colour lots."""
import json
import os
import threading
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(allow_inf_nan=False)]
Text = Annotated[str, Field(min_length=1, max_length=200)]
Identifier = Annotated[str, Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')]


class CatalogModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class SupplierProduct(CatalogModel):
    id: Identifier
    supplier: Text
    product_code: Text
    material: Annotated[str, Field(min_length=1, max_length=100)]
    count_value: Annotated[Number, Field(gt=0)]
    count_unit: Literal['dtex', 'tex', 'denier', 'Nm']
    count_basis: Literal['FINISHED_YARN']
    source_ref: Annotated[str, Field(min_length=1, max_length=1000)]

    @property
    def dtex(self):
        factors = {'dtex': 1, 'tex': 10, 'denier': 10 / 9}
        return round(10000 / self.count_value if self.count_unit == 'Nm'
                     else self.count_value * factors[self.count_unit], 6)

    @model_validator(mode='after')
    def valid_count(self):
        if not 0 < self.dtex <= 100000:
            raise ValueError('Dönüştürülen dtex 0–100000 aralığında olmalıdır.')
        return self


class MeasuredColor(CatalogModel):
    id: Identifier
    product_id: Identifier
    color_code: Text
    name: Annotated[str, Field(min_length=1, max_length=100)]
    dye_lot: Text
    lab: tuple[Annotated[Number, Field(ge=0, le=100)],
               Annotated[Number, Field(ge=-160, le=160)],
               Annotated[Number, Field(ge=-160, le=160)]]
    illuminant: Literal['D50', 'D65', 'A', 'F11']
    observer: Literal['2', '10']
    device: Text
    measured_at: date
    source_ref: Annotated[str, Field(min_length=1, max_length=1000)]


class SupplierCatalog(CatalogModel):
    products: list[SupplierProduct] = Field(default_factory=list, max_length=2000)
    colors: list[MeasuredColor] = Field(default_factory=list, max_length=10000)

    @model_validator(mode='after')
    def unique_records(self):
        for records in (self.products, self.colors):
            ids = [record.id.casefold() for record in records]
            if len(ids) != len(set(ids)):
                raise ValueError('Katalog kayıt kimlikleri benzersiz olmalıdır.')
        return self


CATALOG_PATH = Path(__file__).resolve().parents[1] / 'supplier_catalog.json'
_lock = threading.Lock()


def load_catalog():
    if not CATALOG_PATH.exists():
        return SupplierCatalog()
    return SupplierCatalog.model_validate_json(CATALOG_PATH.read_text(encoding='utf-8'))


def append_catalog(incoming: SupplierCatalog):
    with _lock:
        current = load_catalog()
        if not incoming.products and not incoming.colors:
            raise ValueError('Dosyada katalog kaydı bulunamadı.')
        combined = SupplierCatalog(products=current.products + incoming.products,
                                   colors=current.colors + incoming.colors)
        product_ids = {product.id for product in combined.products}
        if any(color.product_id not in product_ids for color in combined.colors):
            raise ValueError('Kartela kaydının product_id alanı mevcut bir ipliğe bağlanmalıdır.')
        temporary = CATALOG_PATH.with_suffix('.tmp')
        temporary.write_text(combined.model_dump_json(indent=2), encoding='utf-8')
        os.replace(temporary, CATALOG_PATH)
        return combined


def catalog_view(catalog=None):
    catalog = catalog or load_catalog()
    return {'products': [dict(p.model_dump(mode='json'), dtex=p.dtex) for p in catalog.products],
            'colors': [c.model_dump(mode='json') for c in catalog.colors]}


def source_snapshot(product_id, color_id):
    if not product_id:
        if color_id:
            raise ValueError('Önce tedarikçi ipliği seçilmelidir.')
        return None
    catalog = load_catalog()
    product = next((p for p in catalog.products if p.id == product_id), None)
    if product is None:
        raise ValueError('Seçilen tedarikçi ipliği katalogda bulunamadı.')
    color = next((c for c in catalog.colors if c.id == color_id), None) if color_id else None
    if color_id and (color is None or color.product_id != product.id):
        raise ValueError('Seçilen renk kartelası bu tedarikçi ipliğine ait değil.')
    return {'product': dict(product.model_dump(mode='json'), dtex=product.dtex),
            'color': color.model_dump(mode='json') if color else None}


def validate_yarn_sources(yarns):
    for yarn in yarns:
        snapshot = source_snapshot(yarn.catalog_product_id, yarn.catalog_color_id)
        if snapshot:
            product, color = snapshot['product'], snapshot['color']
            if abs(yarn.dtex - product['dtex']) > 0.000001 or yarn.material != product['material']:
                raise ValueError('dtex/malzeme katalogla uyuşmuyor. Manuel düzenleme için katalog bağını kaldırın.')
            if color and (list(yarn.lab) != color['lab'] or yarn.name != color['name']
                          or yarn.color_source != 'MEASURED_LAB'):
                raise ValueError('Renk bilgisi kartelayla uyuşmuyor. Manuel düzenleme için kartela bağını kaldırın.')
        yarn.catalog_snapshot = snapshot


def validate_matching_conditions(yarns):
    for yarn in yarns:
        color = (yarn.catalog_snapshot or {}).get('color')
        if color and (color['illuminant'] != 'D65' or color['observer'] != '2'):
            raise ValueError(f"{yarn.code}: kartela {color['illuminant']}/{color['observer']}°, "
                             'mevcut fotoğraf renk motoru D65/2° kullanıyor. Aynı koşulda ölçüm gerekli.')
