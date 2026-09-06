"""
Master End-to-End Pipeline Engine for Carpet Image to DXF/Jakar CAD and Yarn Recipe
"""
import os
import json
import uuid
from datetime import datetime, timezone
import cv2
import numpy as np
from typing import Dict, Any, Optional

from core.models import (
    LoomConfig, ImagePreprocessingParams, AnalysisPipelineResult,
    ColorMappingItem, YarnConsumptionItem
)
from core.preprocessing import preprocess_carpet_image
from core.inpainting import detect_occlusions_and_defects, complete_pattern_with_symmetry
from core.pattern_analysis import compute_loom_grid_dimensions, resample_to_loom_grid, detect_tile_repeat_period
from core.color_quantizer import CarpetColorQuantizer
from core.yarn_recipe import calculate_yarn_recipe
from core.cad_export import export_dxf, export_svg, export_jacquard_matrix
from core.quality_scorer import audit_production_readiness


from core.utils import imread_safe, imwrite_safe

class CarpetAnalysisPipeline:
    """
    Orchestrates the entire technical transition from competitor carpet photo
    to production-ready DXF/Jakar CAD files and yarn recipes.
    """

    def __init__(self, palette_json_path: str | None = None, output_base_dir: str = "output", palette=None):
        self.palette_json_path = palette_json_path
        self.output_base_dir = output_base_dir

        if palette is not None:
            self.palette = palette
        elif palette_json_path is not None:
            with open(palette_json_path, "r", encoding="utf-8") as f:
                self.palette = json.load(f)["colors"]
        else:
            raise ValueError("Fabrika paleti girilmelidir.")
        if not self.palette:
            raise ValueError("En az bir iplik rengi girilmelidir.")

        self.quantizer = CarpetColorQuantizer(self.palette)

    def process(
        self,
        image_input: Any,  # file path str or numpy array
        loom_cfg: LoomConfig,
        params: ImagePreprocessingParams,
        job_id: Optional[str] = None
    ) -> AnalysisPipelineResult:
        """Runs the entire end-to-end processing pipeline."""
        if job_id is None:
            job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"

        job_dir = os.path.join(self.output_base_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)

        # 1. Load Image
        if isinstance(image_input, str):
            image_bgr = imread_safe(image_input)
            input_image_path = image_input
        else:
            image_bgr = image_input
            input_image_path = os.path.join(job_dir, "00_input.png")
            imwrite_safe(input_image_path, image_bgr)

        input_image_path = os.path.join(job_dir, "00_input.png")
        imwrite_safe(input_image_path, image_bgr)

        # 2. Stage 1: Preprocessing & Rectification (with FastSAM AI & Dereflection)
        target_aspect = loom_cfg.length_cm / float(loom_cfg.width_cm)
        rectified_rgb, mask, rect_meta = preprocess_carpet_image(
            image_bgr=image_bgr,
            target_width_px=params.target_width_px,
            target_aspect_ratio=target_aspect,
            use_sam=params.enable_sam_segmentation,
            enable_dereflection=params.enable_dereflection,
            manual_corners=params.manual_corners
        )
        rectified_path = os.path.join(job_dir, "01_rectified.png")
        imwrite_safe(rectified_path, cv2.cvtColor(rectified_rgb, cv2.COLOR_RGB2BGR))

        # 3. Stage 2: Pattern Inpainting & Symmetry / Generative Completion
        user_mask = None
        if params.repair_regions:
            source_mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
            source_h, source_w = source_mask.shape
            for x1, y1, x2, y2 in params.repair_regions:
                cv2.rectangle(source_mask, (round(x1*(source_w-1)), round(y1*(source_h-1))),
                              (round(x2*(source_w-1)), round(y2*(source_h-1))), 255, -1)
            user_mask = cv2.warpPerspective(source_mask, np.asarray(rect_meta["homography_matrix"]),
                                            (rectified_rgb.shape[1], rectified_rgb.shape[0]), flags=cv2.INTER_NEAREST)
        defect_mask = detect_occlusions_and_defects(rectified_rgb, user_mask=user_mask)
        repair_mask_path = os.path.join(job_dir, "02_repair_mask.png")
        imwrite_safe(repair_mask_path, defect_mask)
        if params.enable_symmetry_completion:
            completed_rgb, conf_map, inpaint_meta = complete_pattern_with_symmetry(
                rectified_rgb, defect_mask, symmetry_mode=params.symmetry_mode
            )
        else:
            completed_rgb = rectified_rgb
            conf_map = np.ones((rectified_rgb.shape[0], rectified_rgb.shape[1]), dtype=np.float32)
            inpaint_meta = {"missing_ratio_pct": 0.0, "mean_confidence": 1.0}

        completed_path = os.path.join(job_dir, "02_completed_pattern.png")
        imwrite_safe(completed_path, cv2.cvtColor(completed_rgb, cv2.COLOR_RGB2BGR))

        # 4. Stage 3 & 4: Color Space Conversion, CIEDE2000 Quantization
        quant_rgb, index_map, color_stats, color_metrics = self.quantizer.quantize_and_map(
            image_rgb=completed_rgb,
            max_colors=loom_cfg.max_colors,
            mode="FORCED_PALETTE",
            clean_islands=True
        )
        quant_preview_path = os.path.join(job_dir, "03_quantized_palette.png")
        imwrite_safe(quant_preview_path, cv2.cvtColor(quant_rgb, cv2.COLOR_RGB2BGR))

        # 5. Stage 5: Loom Grid & CAM Resampling
        n_warp, n_weft, knot_aspect = compute_loom_grid_dimensions(
            loom_cfg.width_cm, loom_cfg.length_cm, loom_cfg.reed_density, loom_cfg.pick_density
        )
        loom_grid = resample_to_loom_grid(index_map, n_warp, n_weft)

        # Reconcile recipe and export palette against the actual discrete loom cells.
        color_stats = [dict(s, pixel_count=int(np.count_nonzero(loom_grid == s["palette_index"])),
                            area_percentage=float(np.count_nonzero(loom_grid == s["palette_index"])) / loom_grid.size * 100)
                       for s in color_stats if np.any(loom_grid == s["palette_index"])]

        # 6. Stage 6: Textile Physics & Yarn Consumption Calculation
        recipe_items, yarn_summary = calculate_yarn_recipe(
            loom_cfg=loom_cfg,
            color_statistics=color_stats,
            palette_inventory=self.palette
        )

        # 7. Stage 7: Technical CAD & Direct Loom CAM File Generation
        dxf_path = os.path.join(job_dir, f"{job_id}_production.dxf")
        svg_path = os.path.join(job_dir, f"{job_id}_vector.svg")
        jacquard_path = os.path.join(job_dir, f"{job_id}_loom_matrix.txt")
        vdw_path = os.path.join(job_dir, f"{job_id}_vdw_pattern.ep")
        staubli_path = os.path.join(job_dir, f"{job_id}_staubli.jc5")

        export_dxf(loom_grid, color_stats, dxf_path, loom_cfg.width_cm * 10.0, loom_cfg.length_cm * 10.0)
        export_svg(loom_grid, color_stats, svg_path, loom_cfg.width_cm * 10.0, loom_cfg.length_cm * 10.0)
        export_jacquard_matrix(loom_grid, color_stats, jacquard_path)

        # Van de Wiele & Stäubli Direct Loom CAM protocols
        from core.loom_protocols import export_van_de_wiele_ep, export_staubli_jc5
        export_van_de_wiele_ep(
            loom_grid=loom_grid,
            color_stats=color_stats,
            output_ep_path=vdw_path,
            reed_density=loom_cfg.reed_density,
            pick_density=loom_cfg.pick_density,
            carpet_width_cm=loom_cfg.width_cm,
            carpet_length_cm=loom_cfg.length_cm
        )
        export_staubli_jc5(
            loom_grid=loom_grid,
            color_stats=color_stats,
            output_jc5_path=staubli_path,
            reed_density=loom_cfg.reed_density,
            pick_density=loom_cfg.pick_density
        )

        # 8. Stage 8: Quality Scorer & Production Audit
        audit = audit_production_readiness(
            raw_image_rgb=cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB),
            rect_metadata=rect_meta,
            inpaint_metadata=inpaint_meta,
            color_metrics=color_metrics,
            yarn_recipe=recipe_items
        )

        # Build ColorMappingItem objects
        color_mapping_items = [
            ColorMappingItem(
                palette_code=s["palette_code"],
                yarn_name=s["yarn_name"],
                material=s["material"],
                mapped_rgb=s["mapped_rgb"],
                pixel_count=s["pixel_count"],
                area_percentage=s["area_percentage"],
                ciede2000_delta_e_avg=s["ciede2000_delta_e_avg"],
                ciede2000_delta_e_max=s["ciede2000_delta_e_max"]
            )
            for s in color_stats
        ]

        result = AnalysisPipelineResult(
            job_id=job_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            loom_config=loom_cfg,
            preprocessing_config=params,
            palette_snapshot=self.palette,
            input_image_path=input_image_path,
            rectified_image_path=rectified_path,
            repair_mask_path=repair_mask_path,
            preprocessing_metadata=rect_meta,
            completed_pattern_path=completed_path,
            quantized_preview_path=quant_preview_path,
            dxf_export_path=dxf_path,
            svg_export_path=svg_path,
            jacquard_grid_path=jacquard_path,
            vdw_ep_export_path=vdw_path,
            staubli_jc5_export_path=staubli_path,
            carpet_dimensions_cm=(loom_cfg.width_cm, loom_cfg.length_cm),
            total_area_sqm=yarn_summary["total_order_area_sqm"],
            loom_aspect_ratio=round(knot_aspect, 4),
            grid_resolution_cells=(n_warp, n_weft),
            color_mappings=color_mapping_items,
            yarn_recipe=recipe_items,
            total_order_yarn_kg=yarn_summary["total_order_yarn_kg"],
            total_order_cost_tl=yarn_summary["total_order_cost_tl"],
            audit=audit
        )

        # Save result JSON for inspection
        result_json_path = os.path.join(job_dir, "analysis_report.json")
        with open(result_json_path + ".tmp", "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
        os.replace(result_json_path + ".tmp", result_json_path)

        return result
