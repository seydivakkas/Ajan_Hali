"""
Carpet Structural Analysis: Repeat Periodicity, Border-Field Decomposition & Loom Grid Transformation
"""
import cv2
import numpy as np
from typing import Tuple, Dict, Any, Optional
from scipy.signal import correlate2d


def detect_tile_repeat_period(image_rgb: np.ndarray) -> Tuple[Optional[Tuple[int, int]], float]:
    """
    Detect fundamental repeat pitch (dx, dy) using 2D spatial autocorrelation.
    Useful for modern all-over geometric, runner, and transitional repeating patterns.
    """
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape

    # Downsample for computational efficiency in 2D autocorrelation
    scale = 200.0 / max(h, w)
    small_gray = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    norm_gray = small_gray.astype(np.float32) - np.mean(small_gray)

    # 2D cross-correlation with itself
    corr = correlate2d(norm_gray, norm_gray, mode="same")
    mid_y, mid_x = corr.shape[0] // 2, corr.shape[1] // 2

    # Zero out the central peak
    win = 10
    corr[mid_y - win : mid_y + win + 1, mid_x - win : mid_x + win + 1] = 0

    # Find secondary peaks indicating periodicity
    peak_y, peak_x = np.unravel_index(np.argmax(corr), corr.shape)
    dy_scaled = abs(peak_y - mid_y)
    dx_scaled = abs(peak_x - mid_x)

    if scale > 0 and (dx_scaled > 5 or dy_scaled > 5):
        dx_orig = int(round(dx_scaled / scale))
        dy_orig = int(round(dy_scaled / scale))
        confidence = float(np.max(corr) / (np.std(corr) * corr.size + 1e-6))
        confidence = min(1.0, max(0.2, confidence / 50.0))
        return (dx_orig, dy_orig), confidence

    return None, 0.0


def segment_border_and_field(image_rgb: np.ndarray, border_ratio_estimate: float = 0.12) -> Dict[str, Any]:
    """
    Segment carpet into Outer Border (Bordür) and Inner Field (Zemin / Hav Alanı).
    Standard Oriental/Classic carpets feature a border width between 10% to 18% of total width.
    """
    h, w, _ = image_rgb.shape
    border_px_x = int(round(w * border_ratio_estimate))
    border_px_y = int(round(h * border_ratio_estimate))

    field_mask = np.zeros((h, w), dtype=np.uint8)
    field_mask[border_px_y : h - border_px_y, border_px_x : w - border_px_x] = 255

    border_mask = 255 - field_mask

    border_area_pct = (np.sum(border_mask > 0) / (h * w)) * 100.0
    field_area_pct = (np.sum(field_mask > 0) / (h * w)) * 100.0

    return {
        "border_mask": border_mask,
        "field_mask": field_mask,
        "border_width_x_px": border_px_x,
        "border_width_y_px": border_px_y,
        "border_area_pct": round(border_area_pct, 2),
        "field_area_pct": round(field_area_pct, 2)
    }


def compute_loom_grid_dimensions(
    carpet_width_cm: float,
    carpet_length_cm: float,
    reed_density_reeds_per_m: int,
    pick_density_picks_per_m: int
) -> Tuple[int, int, float]:
    """
    Calculate the exact number of knot cells (warp columns x weft rows)
    on the industrial Jacquard weaving machine.

    Formula:
        Total Warp Knots (Columns) = (Carpet Width in meters) * Reed Density
        Total Weft Knots (Rows)    = (Carpet Length in meters) * Pick Density
        Loom Knot Aspect Ratio     = Reed Density / Pick Density (Anisotropic ratio)
    """
    width_m = carpet_width_cm / 100.0
    length_m = carpet_length_cm / 100.0

    num_warp_cols = int(round(width_m * reed_density_reeds_per_m))
    num_weft_rows = int(round(length_m * pick_density_picks_per_m))

    # Anisotropic ratio: if 500 / 800 = 0.625, each knot is taller than it is wide
    knot_aspect_ratio = reed_density_reeds_per_m / float(pick_density_picks_per_m)

    return num_warp_cols, num_weft_rows, knot_aspect_ratio


def resample_to_loom_grid(
    index_map: np.ndarray,
    num_warp_cols: int,
    num_weft_rows: int
) -> np.ndarray:
    """
    Resample the quantized color index map into the precise discrete grid of the Jacquard loom.
    Uses Nearest Neighbor interpolation to strictly preserve discrete palette indices.
    """
    loom_grid = cv2.resize(
        index_map.astype(np.uint8),
        (num_warp_cols, num_weft_rows),
        interpolation=cv2.INTER_NEAREST
    )
    return loom_grid
