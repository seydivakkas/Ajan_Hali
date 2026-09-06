"""
Specular Highlight & Flash Glare Removal Engine (Dereflection)
Telif Hakkı (c) 2026 Seydi Eryılmaz (@seydivakkas) - ÖZEL LİSANS / TÜM HAKLAR SAKLIDIR
"""
import cv2
import numpy as np
from typing import Tuple, Dict, Any


def detect_specular_highlights(
    image_bgr: np.ndarray,
    luminance_thresh: int = 230,
    saturation_thresh: float = 0.18
) -> np.ndarray:
    """
    Detects harsh flash reflections and specular highlights on shiny carpet fibers
    (e.g., viscose, bamboo silk, glossy polyester).
    Returns binary mask (uint8) where 255 = highlight region, 0 = diffuse surface.
    """
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    _, s_norm, v_norm = cv2.split(hsv)

    # 1. High value (brightness) + Low saturation = wash-out white flash glare
    sat_float = s_norm.astype(np.float32) / 255.0
    val_int = v_norm.astype(np.int32)

    glare_mask = ((val_int >= luminance_thresh) & (sat_float <= saturation_thresh)).astype(np.uint8) * 255

    # 2. Add Lab L* channel extreme check
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    l_extreme = (l_ch >= 240).astype(np.uint8) * 255
    glare_mask = cv2.bitwise_or(glare_mask, l_extreme)

    # 3. Morphological dilation to encompass gradient halo around highlights
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    glare_mask = cv2.dilate(glare_mask, kernel, iterations=2)

    return glare_mask


def remove_specular_highlights(
    image_bgr: np.ndarray,
    luminance_thresh: int = 230,
    inpaint_radius: int = 5
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    Removes specular glare and camera flash reflections using Dichromatic Reflection
    chromaticity restoration and bilateral fiber diffusion.

    Returns:
        - dereflected_bgr: corrected image without harsh white specular artifacts
        - highlight_mask: detected highlight mask
        - stats: highlight area ratio and attenuation metrics
    """
    highlight_mask = detect_specular_highlights(image_bgr, luminance_thresh=luminance_thresh)
    highlight_pixels = int(np.sum(highlight_mask > 0))
    total_pixels = image_bgr.shape[0] * image_bgr.shape[1]
    highlight_ratio_pct = (highlight_pixels / float(total_pixels)) * 100.0

    if highlight_pixels == 0:
        return image_bgr.copy(), highlight_mask, {"highlight_ratio_pct": 0.0, "status": "NO_GLARE_DETECTED"}

    # 1. Calculate local ambient diffuse chromaticity via Telea inpainting on color channels
    reconstructed_bgr = cv2.inpaint(image_bgr, highlight_mask, inpaintRadius=inpaint_radius, flags=cv2.INPAINT_TELEA)

    # 2. Preserve subtle textile fiber texture by blending with local band-pass details
    gray_orig = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray_orig, (5, 5), 0)
    texture_detail = cv2.subtract(gray_orig, blurred)

    # Blend diffuse reconstruction with micro-texture
    res_bgr = reconstructed_bgr.copy().astype(np.float32)
    for c in range(3):
        # Lightly inject micro-contrast where not fully saturated
        res_bgr[:, :, c] += (texture_detail.astype(np.float32) * 0.35)

    dereflected_bgr = np.clip(res_bgr, 0, 255).astype(np.uint8)

    stats = {
        "highlight_ratio_pct": round(highlight_ratio_pct, 3),
        "highlight_pixel_count": highlight_pixels,
        "status": "GLARE_ATTENUATED" if highlight_pixels > 0 else "NO_GLARE"
    }

    return dereflected_bgr, highlight_mask, stats
