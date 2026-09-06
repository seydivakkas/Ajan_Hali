"""
Carpet Pattern Completion & Occlusion Inpainting with Confidence Mapping
"""
import cv2
import numpy as np
from typing import Tuple, Dict, Any, Optional


def detect_occlusions_and_defects(
    image_rgb: np.ndarray,
    user_mask: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    Detect missing, blurry, or low-contrast occluded regions (e.g. furniture, feet, tags).
    Returns a binary mask (uint8) where 255 = region to be inpainted/completed, 0 = valid.
    """
    h, w, _ = image_rgb.shape
    if user_mask is not None:
        return user_mask

    # Detect extreme saturation/darkness anomalies or uniform patches
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)

    # 1. Local variance / texture deficit (occluding solid objects lack carpet pile texture)
    mean_val = cv2.blur(gray.astype(np.float32), (15, 15))
    sq_mean = cv2.blur((gray.astype(np.float32)) ** 2, (15, 15))
    variance = np.maximum(0, sq_mean - (mean_val ** 2))
    std_dev = np.sqrt(variance)

    # Carpet texture typically has high micro-contrast; flat obstacles have very low std_dev
    flat_mask = (std_dev < 3.5).astype(np.uint8) * 255

    # Filter out natural large solid background borders by looking at boundaries
    # Remove small speckles
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    cleaned_mask = cv2.morphologyEx(flat_mask, cv2.MORPH_OPEN, kernel)

    return cleaned_mask


def complete_pattern_with_symmetry(
    image_rgb: np.ndarray,
    defect_mask: np.ndarray,
    symmetry_mode: str = "QUADRANT_4FOLD"  # 'HORIZONTAL', 'VERTICAL', 'QUADRANT_4FOLD'
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    Exploits classical oriental and modern carpet symmetries (bilateral or 4-fold quadrant)
    to repair occlusions and complete cropped borders with ground-truth texture from opposing clean sections.

    Returns:
        - completed_rgb: repaired image
        - confidence_map: (H, W) float32 in [0.0, 1.0] (1.0 = observed, 0.85 = symmetry mirrored, 0.60 = inpainting)
        - metadata: statistics on completed areas
    """
    if symmetry_mode == "ABSTRACT_GENERATIVE":
        from core.generative_inpaint import complete_abstract_carpet_pattern
        return complete_abstract_carpet_pattern(image_rgb, defect_mask)

    h, w, _ = image_rgb.shape
    completed = image_rgb.copy()
    confidence_map = np.ones((h, w), dtype=np.float32)

    # Baseline: Observed valid areas have confidence 1.0, defect areas start at 0.0
    defect_indices = (defect_mask > 0)
    confidence_map[defect_indices] = 0.0

    half_h = h // 2
    half_w = w // 2

    # Horizontal reflection (Left <-> Right)
    h_flipped = cv2.flip(image_rgb, 1)
    h_defect_flipped = cv2.flip(defect_mask, 1)

    # Vertical reflection (Top <-> Bottom)
    v_flipped = cv2.flip(image_rgb, 0)
    v_defect_flipped = cv2.flip(defect_mask, 0)

    # Central/Diagonal 180° reflection
    diag_flipped = cv2.flip(image_rgb, -1)
    diag_defect_flipped = cv2.flip(defect_mask, -1)

    # Step 1: Quadrant / Horizontal symmetry transfer
    repaired_by_symmetry = 0
    total_defect_pixels = np.sum(defect_indices)

    if total_defect_pixels > 0:
        # Check if horizontal mirror is clean
        can_h = (defect_mask > 0) & (h_defect_flipped == 0) & (symmetry_mode in ("HORIZONTAL", "QUADRANT_4FOLD"))
        completed[can_h] = h_flipped[can_h]
        confidence_map[can_h] = 0.88
        repaired_by_symmetry += np.sum(can_h)

        # Check if vertical mirror is clean
        remaining_defect = (confidence_map == 0.0)
        can_v = remaining_defect & (v_defect_flipped == 0) & (symmetry_mode in ("VERTICAL", "QUADRANT_4FOLD"))
        completed[can_v] = v_flipped[can_v]
        confidence_map[can_v] = 0.88
        repaired_by_symmetry += np.sum(can_v)

        # Check diagonal mirror
        remaining_defect = (confidence_map == 0.0)
        can_diag = remaining_defect & (diag_defect_flipped == 0) & (symmetry_mode == "QUADRANT_4FOLD")
        completed[can_diag] = diag_flipped[can_diag]
        confidence_map[can_diag] = 0.82
        repaired_by_symmetry += np.sum(can_diag)

    # Step 2: Fallback Inpainting for regions where all 4 mirror quadrants are occluded
    still_missing = (confidence_map == 0.0).astype(np.uint8) * 255
    inpainted_count = 0
    if np.sum(still_missing) > 0:
        # Fast Marching Method (Telea) or Navier-Stokes Inpainting
        bgr_temp = cv2.cvtColor(completed, cv2.COLOR_RGB2BGR)
        inpaint_bgr = cv2.inpaint(bgr_temp, still_missing, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
        inpaint_rgb = cv2.cvtColor(inpaint_bgr, cv2.COLOR_BGR2RGB)

        inpaint_mask_bool = (still_missing > 0)
        completed[inpaint_mask_bool] = inpaint_rgb[inpaint_mask_bool]
        confidence_map[inpaint_mask_bool] = 0.60
        inpainted_count = np.sum(inpaint_mask_bool)

    overall_confidence = float(np.mean(confidence_map))
    missing_ratio = float(total_defect_pixels) / (h * w) if (h * w) > 0 else 0.0

    metadata = {
        "total_defect_pixels": int(total_defect_pixels),
        "missing_ratio_pct": round(missing_ratio * 100.0, 2),
        "repaired_by_symmetry_pixels": int(repaired_by_symmetry),
        "repaired_by_generative_inpaint_pixels": int(inpainted_count),
        "mean_confidence": round(overall_confidence, 3),
        "symmetry_mode_applied": symmetry_mode
    }

    return completed, confidence_map, metadata
