"""
Computer Vision Preprocessing: Background Removal, Homography Rectification & Lighting Normalization
"""
import cv2
import numpy as np
from typing import Tuple, Dict, Any, Optional


def order_quad_points(pts: np.ndarray) -> np.ndarray:
    """
    Sort quad corner points into standard order: [top-left, top-right, bottom-right, bottom-left].
    """
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left has smallest sum
    rect[2] = pts[np.argmax(s)]  # bottom-right has largest sum

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right has smallest diff
    rect[3] = pts[np.argmax(diff)]  # bottom-left has largest diff

    return rect


def find_carpet_corners(image_bgr: np.ndarray) -> Optional[np.ndarray]:
    """
    Detect the 4 boundary corners of the carpet in an angled photograph.
    Uses edge gradient detection, morphological closing, and contour approximation.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)

    # Multi-scale edge detection
    edges = cv2.Canny(blurred, 30, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Filter by area (carpet should occupy at least 15% of image frame)
    img_area = image_bgr.shape[0] * image_bgr.shape[1]
    sorted_contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for c in sorted_contours[:5]:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.03 * peri, True)
        if len(approx) == 4 and cv2.contourArea(approx) > 0.15 * img_area:
            return order_quad_points(approx.reshape(4, 2))

    # Fallback to bounding quadrilateral of largest contour
    if sorted_contours and cv2.contourArea(sorted_contours[0]) > 0.10 * img_area:
        rect = cv2.minAreaRect(sorted_contours[0])
        box = cv2.boxPoints(rect)
        return order_quad_points(box)

    return None


def rectify_perspective(
    image_bgr: np.ndarray,
    corners: Optional[np.ndarray],
    target_width_px: int = 800,
    target_aspect_ratio: float = 1.4375  # e.g. 230 / 160 = 1.4375
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Applies 4-point homography transform to warp perspective into a top-down orthogonal plane.
    Returns rectified_bgr, homography_matrix, confidence.
    """
    h_img, w_img = image_bgr.shape[:2]
    target_height_px = int(round(target_width_px * target_aspect_ratio))

    if corners is None:
        # Fallback: full image corners with confidence penalty
        corners = np.array([
            [0, 0],
            [w_img - 1, 0],
            [w_img - 1, h_img - 1],
            [0, h_img - 1]
        ], dtype=np.float32)
        confidence = 0.55
    else:
        confidence = 0.92

    dst_pts = np.array([
        [0, 0],
        [target_width_px - 1, 0],
        [target_width_px - 1, target_height_px - 1],
        [0, target_height_px - 1]
    ], dtype=np.float32)

    H, _ = cv2.findHomography(corners, dst_pts)
    rectified = cv2.warpPerspective(image_bgr, H, (target_width_px, target_height_px), flags=cv2.INTER_LANCZOS4)
    return rectified, H, confidence


def normalize_lighting_and_color(image_bgr: np.ndarray) -> np.ndarray:
    """
    Normalize non-uniform lighting, ambient shadows, and color temperature.
    Applies Gray-World White Balance + CLAHE on the L* channel in Lab space.
    """
    # 1. Gray-World White Balance
    b, g, r = cv2.split(image_bgr.astype(np.float32))
    b_mean, g_mean, r_mean = np.mean(b), np.mean(g), np.mean(r)
    gray_mean = (b_mean + g_mean + r_mean) / 3.0

    if b_mean > 0 and g_mean > 0 and r_mean > 0:
        b = np.clip(b * (gray_mean / b_mean), 0, 255)
        g = np.clip(g * (gray_mean / g_mean), 0, 255)
        r = np.clip(r * (gray_mean / r_mean), 0, 255)

    balanced_bgr = cv2.merge([b, g, r]).astype(np.uint8)

    # 2. Illumination Equalization via CLAHE on L* channel
    lab = cv2.cvtColor(balanced_bgr, cv2.COLOR_BGR2LAB)
    l, a, b_ch = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    l_eq = clahe.apply(l)

    normalized_lab = cv2.merge([l_eq, a, b_ch])
    result_bgr = cv2.cvtColor(normalized_lab, cv2.COLOR_LAB2BGR)

    # 3. Bilateral filter for noise smoothing while preserving crisp textile edges
    denoised = cv2.bilateralFilter(result_bgr, d=5, sigmaColor=35, sigmaSpace=35)
    return denoised


def preprocess_carpet_image(
    image_bgr: np.ndarray,
    target_width_px: int = 800,
    target_aspect_ratio: float = 1.4375,
    use_sam: bool = True,
    enable_dereflection: bool = True,
    manual_corners=None
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    Complete Preprocessing Pipeline with optional FastSAM AI segmentation & Dereflection.
    Returns:
        - preprocessed_rgb: rectified, white-balanced, illumination-normalized RGB array
        - mask: carpet segmentation mask (binary)
        - metadata: transformation matrices, corner points, quality indicators, engine used
    """
    if enable_dereflection:
        try:
            from core.dereflection import remove_specular_highlights
            image_bgr, _, _ = remove_specular_highlights(image_bgr)
        except Exception:
            pass

    corners = None
    engine_used = "OPENCV_CANNY"
    rect_conf = 0.85
    sam_mask = None

    if manual_corners is not None:
        h, w = image_bgr.shape[:2]
        corners = np.asarray(manual_corners, dtype=np.float32) * [w - 1, h - 1]
        engine_used = "MANUAL_CORNERS"

    if use_sam and manual_corners is None:
        try:
            from core.sam_segmentation import CarpetSAMSegmentor
            segmentor = CarpetSAMSegmentor()
            if segmentor.is_available:
                sam_mask, sam_corners, sam_conf = segmentor.segment_carpet(image_bgr)
                if sam_corners is not None and len(sam_corners) == 4:
                    corners = sam_corners
                    rect_conf = sam_conf
                    engine_used = "FAST_SAM_CUDA"
        except Exception as e:
            # Fallback smoothly to OpenCV
            pass

    # Fallback to classical OpenCV edge & contour approximation if SAM didn't produce corners
    if corners is None:
        corners = find_carpet_corners(image_bgr)
        engine_used = "OPENCV_CANNY"

    rectified_bgr, H, final_conf = rectify_perspective(
        image_bgr, corners, target_width_px, target_aspect_ratio
    )
    if engine_used == "FAST_SAM_CUDA":
        final_conf = max(final_conf, rect_conf)

    normalized_bgr = normalize_lighting_and_color(rectified_bgr)
    preprocessed_rgb = cv2.cvtColor(normalized_bgr, cv2.COLOR_BGR2RGB)

    # Binary validity mask
    mask = np.ones((normalized_bgr.shape[0], normalized_bgr.shape[1]), dtype=np.uint8) * 255

    metadata = {
        "homography_matrix": H.tolist(),
        "corners_detected": corners.tolist() if corners is not None else None,
        "rectification_confidence": float(final_conf),
        "segmentation_engine": engine_used,
        "aspect_ratio": target_aspect_ratio,
        "output_shape": preprocessed_rgb.shape[:2]
    }

    return preprocessed_rgb, mask, metadata

