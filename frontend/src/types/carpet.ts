/**
 * Type definitions matching backend Pydantic models
 * Industrial Carpet CAD & Yarn Optimization System
 * Telif Hakkı (c) 2026 Seydi Eryılmaz (@seydivakkas)
 */

export interface ColorMappingItem {
  palette_code: string;
  yarn_name: string;
  material: string;
  mapped_rgb: [number, number, number];
  pixel_count: number;
  area_percentage: number;
  ciede2000_delta_e_avg: number;
  ciede2000_delta_e_max: number;
}

export interface YarnConsumptionItem {
  yarn_code: string;
  yarn_name: string;
  material: string;
  dtex: number;
  area_percentage: number;
  surface_area_sqm_per_carpet: number;
  total_surface_area_sqm: number;
  yarn_length_m_per_carpet: number;
  total_yarn_length_km: number;
  yarn_weight_kg_per_carpet: number;
  total_weight_kg_net: number;
  total_weight_kg_gross_with_waste: number;
  bobbin_count_required: number;
  stock_available_kg: number;
  stock_shortage_kg: number;
  unit_cost_tl: number;
  total_cost_tl: number;
  is_stock_sufficient: boolean;
  alternative_yarn_code?: string | null;
}

export interface ProductionAuditScore {
  overall_readiness_score: number;
  input_quality_score: number;
  segmentation_confidence: number;
  completion_confidence: number;
  color_fidelity_score: number;
  delta_e_avg: number;
  delta_e_p95: number;
  delta_e_max: number;
  status: "READY" | "READY_WITH_WARNING" | "REVIEW_REQUIRED" | "NOT_PRODUCTION_SAFE";
  risk_flags: string[];
  technical_recommendations: string[];
}

export interface AnalysisPipelineResult {
  data_source?: string;
  job_id: string;
  created_at?: string;
  loom_config?: LoomFormConfig | null;
  cam_compatibility?: string;
  input_image_path: string;
  repair_mask_path?: string;
  preprocessing_metadata?: { segmentation_engine?: string };
  rectified_image_path: string;
  completed_pattern_path: string;
  quantized_preview_path: string;
  dxf_export_path?: string | null;
  svg_export_path?: string | null;
  jacquard_grid_path?: string | null;
  vdw_ep_export_path?: string | null;
  staubli_jc5_export_path?: string | null;
  carpet_dimensions_cm: [number, number];
  total_area_sqm: number;
  loom_aspect_ratio: number;
  grid_resolution_cells: [number, number];
  color_mappings: ColorMappingItem[];
  yarn_recipe: YarnConsumptionItem[];
  total_production_cost_tl: number;
  total_gross_yarn_weight_kg: number;
  total_bobbins_required: number;
  production_audit: ProductionAuditScore;
}

export interface LoomFormConfig {
  weave_structure_factor: number;
  anchor_length_mm: number;
  manual_corners?: [number, number][];
  repair_regions?: [number, number, number, number][];
  width_cm: number;
  length_cm: number;
  reed_density: number;
  pick_density: number;
  pile_height_mm: number;
  max_colors: number;
  order_quantity: number;
  waste_coefficient: number;
  enable_symmetry: boolean;
  enable_sam: boolean;
  enable_dereflection: boolean;
  symmetry_mode: string;
}
