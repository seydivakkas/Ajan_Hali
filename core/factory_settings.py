"""User-maintained factory data. No example stock, prices or network targets."""
import json
import os
import threading
from pathlib import Path
from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Annotated, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

Finite = Annotated[float, Field(allow_inf_nan=False)]
class YarnSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    is_demo: bool = False
    code: str = Field(min_length=1, max_length=40, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=100)
    material: str = Field(min_length=1, max_length=100)
    dtex: Annotated[Finite, Field(gt=0, le=100000)]
    catalog_product_id: str | None = None
    catalog_color_id: str | None = None
    catalog_snapshot: dict | None = None
    rgb: tuple[Annotated[int, Field(ge=0,le=255)], Annotated[int, Field(ge=0,le=255)], Annotated[int, Field(ge=0,le=255)]]
    lab: tuple[Annotated[Finite, Field(ge=0,le=100)], Annotated[Finite, Field(ge=-160,le=160)], Annotated[Finite, Field(ge=-160,le=160)]]
    color_source: Literal['MEASURED_LAB', 'RGB_ESTIMATE', 'DEMO_SYNTHETIC']
    cost_per_kg_tl: Annotated[Finite, Field(ge=0)]
    bobbin_weight_kg: Annotated[Finite, Field(gt=0)]
    stock_kg: Annotated[Finite, Field(ge=0)]

    @model_validator(mode='after')
    def preview_from_measurement(self):
        if self.color_source == 'DEMO_SYNTHETIC':
            self.is_demo = True
        if self.color_source in {'MEASURED_LAB', 'DEMO_SYNTHETIC'}:
            import numpy as np
            from core.color_quantizer import lab_to_srgb
            self.rgb = tuple(int(v) for v in lab_to_srgb(np.array(self.lab, dtype=float)))
        return self

class LoomSettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    controller_model: str = Field(min_length=1, max_length=100)
    ip: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: Literal['FTP','SFTP','SMB'] | None = None
    @model_validator(mode='after')
    def check_ip(self):
        if self.ip:
            ip_address(self.ip)
        return self

class FactorySettings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    revision: int = Field(default=0, ge=0)
    updated_at: str | None = None
    company_name: str = Field(default='', max_length=150)
    erp_system: str = Field(default='', max_length=100)
    attio_company_record_id: str = Field(default='', max_length=100)
    yarns: list[YarnSettings] = Field(default_factory=list, max_length=256)
    looms: list[LoomSettings] = Field(default_factory=list, max_length=100)
    @model_validator(mode='after')
    def unique_codes(self):
        codes = [item.code.casefold() for item in self.yarns]
        if len(codes) != len(set(codes)):
            raise ValueError('İplik kodları benzersiz olmalıdır.')
        return self

_lock = threading.Lock()
SETTINGS_PATH = Path(__file__).resolve().parents[1] / 'factory_settings.json'


def active_settings_path() -> Path:
    from core import access_control as auth
    if auth.mode() == 'workspace':
        return auth.workspace_directory() / 'factory_settings.json'
    return SETTINGS_PATH


def load_settings():
    path = active_settings_path()
    if not path.exists():
        return FactorySettings()
    return FactorySettings.model_validate_json(path.read_text(encoding='utf-8'))

def save_settings(settings):
    with _lock:
        current = load_settings()
        if settings.revision != current.revision:
            raise ValueError('Ayarlar başka bir oturumda değişti. Yenileyip tekrar kaydedin.')
        from core.supplier_catalog import validate_yarn_sources
        validate_yarn_sources(settings.yarns)
        updated = settings.model_copy(update={'revision': current.revision+1, 'updated_at':datetime.now(timezone.utc).isoformat()})
        path = active_settings_path()
        temporary = path.with_suffix('.tmp')
        temporary.write_text(updated.model_dump_json(indent=2), encoding='utf-8')
        os.replace(temporary, path)
        return updated
