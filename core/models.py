"""
Domain Models for Carpet CAD & Yarn Recipe Generation System
"""
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field, model_validator
from typing import Literal


class FactoryPaletteItem(BaseModel):
    code: str = Field(..., description="İplik fabrika stok kodu (örn. YRN-01)")
    name: str = Field(..., description="Renk adı (örn. Krem Ekru)")
    material: str = Field(default="PP Heatset BCF", description="Hammadde tipi")
    dtex: float = Field(default=1800, description="İplik numarası dtex (g / 10.000m)")
    rgb: List[int] = Field(..., description="sRGB [R, G, B] (0-255)")
    lab: List[float] = Field(..., description="CIE L*a*b* değerleri")
    cost_per_kg_tl: float = Field(default=150.0, description="Birim kg maliyeti (TL)")
    bobbin_weight_kg: float = Field(default=4.5, description="Tek bobin net ağırlığı (kg)")
    stock_kg: float = Field(default=500.0, description="Depodaki hazır stok miktarı (kg)")


class LoomConfig(BaseModel):
    reed_density: int = Field(default=500, gt=0, le=5000, description="Tarak sıklığı (tel / metre veya reed/m)")
    pick_density: int = Field(default=800, gt=0, le=5000, description="Atkı vuruş sıklığı (picks / metre)")
    pile_height_mm: float = Field(default=11.5, gt=0, le=100, description="Hav yüksekliği (mm)")
    max_colors: int = Field(default=8, ge=1, le=16, description="Maksimum tezgâh cağlık rengi (örn. 8, 12, 16)")
    waste_coefficient: float = Field(default=0.07, ge=0, le=1, description="Üretim zayiat ve fire katsayısı (%7 = 0.07)")
    weave_structure_factor: float = Field(default=1.18, gt=0, le=5, description="Düğüm altı jüt/pamuk kırım uzama faktörü")
    anchor_length_mm: float = Field(default=3.2, ge=0, le=100, allow_inf_nan=False)
    width_cm: float = Field(default=160.0, ge=1, le=1000, description="Üretilecek halı eni (cm)")
    length_cm: float = Field(default=230.0, ge=1, le=3000, description="Üretilecek halı boyu (cm)")
    order_quantity: int = Field(default=50, ge=1, le=100000, description="Sipariş adedi (parça)")

    @model_validator(mode="after")
    def validate_grid(self):
        warp = round(self.width_cm / 100 * self.reed_density)
        weft = round(self.length_cm / 100 * self.pick_density)
        if warp < 1 or weft < 1 or warp * weft > 20_000_000:
            raise ValueError("Tezgâh matrisi 1–20.000.000 hücre arasında olmalıdır.")
        return self


class ImagePreprocessingParams(BaseModel):
    manual_corners: Optional[List[Tuple[float, float]]] = None
    repair_regions: List[Tuple[float, float, float, float]] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_manual_geometry(self):
        import math
        if self.manual_corners is not None:
            points = self.manual_corners
            if len(points) != 4 or any(not math.isfinite(v) or not 0 <= v <= 1 for p in points for v in p):
                raise ValueError("Dört köşe 0–1 aralığında olmalıdır.")
            cross = []
            for i in range(4):
                a, b, c = points[i], points[(i+1)%4], points[(i+2)%4]
                cross.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
            if not all(v > 0.0001 for v in cross):
                raise ValueError("Köşeleri sol üst, sağ üst, sağ alt, sol alt sırasıyla seçin; alan dışbükey olmalıdır.")
        for x1, y1, x2, y2 in self.repair_regions:
            if any(not math.isfinite(v) or not 0 <= v <= 1 for v in (x1,y1,x2,y2)) or x2 <= x1 or y2 <= y1:
                raise ValueError("Onarım bölgeleri pozitif alanlı ve görsel sınırları içinde olmalıdır.")
        if self.repair_regions and not self.enable_symmetry_completion:
            raise ValueError("Manuel maske kullanmak için onarımı etkinleştirin.")
        return self

    enable_auto_crop: bool = True
    enable_homography_rectify: bool = True
    enable_shadow_removal: bool = True
    enable_symmetry_completion: bool = True
    enable_generative_inpaint: bool = True
    enable_sam_segmentation: bool = True
    sam_model_name: str = "FastSAM-s.pt"
    enable_dereflection: bool = True
    symmetry_mode: Literal["QUADRANT_4FOLD", "ABSTRACT_GENERATIVE", "HORIZONTAL", "VERTICAL"] = "QUADRANT_4FOLD"  # 'QUADRANT_4FOLD' | 'ABSTRACT_GENERATIVE' | 'HORIZONTAL' | 'VERTICAL'
    target_width_px: int = 800
    target_height_px: int = 1150


class ColorMappingItem(BaseModel):
    palette_code: str
    yarn_name: str
    material: str
    mapped_rgb: List[int]
    pixel_count: int
    area_percentage: float
    ciede2000_delta_e_avg: float
    ciede2000_delta_e_max: float


class YarnConsumptionItem(BaseModel):
    yarn_code: str
    yarn_name: str
    material: str
    dtex: float
    area_percentage: float
    surface_area_sqm_per_carpet: float
    total_surface_area_sqm: float
    yarn_length_m_per_carpet: float
    total_yarn_length_km: float
    yarn_weight_kg_per_carpet: float
    total_weight_kg_net: float
    total_weight_kg_gross_with_waste: float
    bobbin_count_required: int
    stock_available_kg: float
    stock_shortage_kg: float
    unit_cost_tl: float
    total_cost_tl: float
    is_stock_sufficient: bool
    alternative_yarn_code: Optional[str] = None


class ProductionAuditScore(BaseModel):
    overall_readiness_score: float = Field(..., description="0 - 100 arası üretim hazır olma skoru")
    input_quality_score: float
    segmentation_confidence: float
    completion_confidence: float
    color_fidelity_score: float
    delta_e_avg: float
    delta_e_p95: float
    delta_e_max: float
    status: str = Field(..., description="READY | READY_WITH_WARNING | REVIEW_REQUIRED | NOT_PRODUCTION_SAFE")
    risk_flags: List[str]
    technical_recommendations: List[str]


class AnalysisPipelineResult(BaseModel):
    job_id: str
    data_source: str = "UNVERIFIED_LEGACY"
    factory_settings_revision: Optional[int] = None
    company_name: Optional[str] = None
    created_at: Optional[str] = None
    loom_config: Optional[LoomConfig] = None
    preprocessing_config: Optional[ImagePreprocessingParams] = None
    palette_snapshot: List[Dict[str, Any]] = Field(default_factory=list)
    total_bobbins_required: int = 0
    cam_compatibility: str = "UNVERIFIED_PROTOTYPE"
    input_image_path: str
    repair_mask_path: Optional[str] = None
    preprocessing_metadata: Dict[str, Any] = Field(default_factory=dict)
    rectified_image_path: str
    completed_pattern_path: str
    quantized_preview_path: str
    dxf_export_path: Optional[str] = None
    svg_export_path: Optional[str] = None
    jacquard_grid_path: Optional[str] = None
    vdw_ep_export_path: Optional[str] = None
    staubli_jc5_export_path: Optional[str] = None
    carpet_dimensions_cm: Tuple[float, float]
    total_area_sqm: float
    loom_aspect_ratio: float
    grid_resolution_cells: Tuple[int, int]
    color_mappings: List[ColorMappingItem]
    yarn_recipe: List[YarnConsumptionItem]
    total_order_yarn_kg: float
    total_order_cost_tl: float
    audit: ProductionAuditScore

    # Dual alias compatibility for frontend & external reporting
    total_gross_yarn_weight_kg: Optional[float] = None
    total_production_cost_tl: Optional[float] = None
    production_audit: Optional[ProductionAuditScore] = None

    def model_post_init(self, __context: Any) -> None:
        self.total_bobbins_required = sum(r.bobbin_count_required for r in self.yarn_recipe)
        if self.total_gross_yarn_weight_kg is None:
            self.total_gross_yarn_weight_kg = self.total_order_yarn_kg
        if self.total_production_cost_tl is None:
            self.total_production_cost_tl = self.total_order_cost_tl
        if self.production_audit is None:
            self.production_audit = self.audit
