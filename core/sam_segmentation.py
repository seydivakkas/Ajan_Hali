"""
Deep Learning Carpet Segmentation & Defect Detection using Segment Anything (SAM / FastSAM)
Telif Hakkı (c) 2026 Seydi Eryılmaz (@seydivakkas) - ÖZEL LİSANS / TÜM HAKLAR SAKLIDIR
"""
import os
import logging
from typing import Tuple, Optional, List
import cv2
import numpy as np

logger = logging.getLogger("CarpetSAM")

# Global cached model
_SAM_MODEL_INSTANCE = None


def get_sam_model(model_name: str = "FastSAM-s.pt"):
    """Loads and caches the FastSAM model instance."""
    global _SAM_MODEL_INSTANCE
    if _SAM_MODEL_INSTANCE is not None:
        return _SAM_MODEL_INSTANCE

    try:
        import torch
        from ultralytics import FastSAM

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading FastSAM model '{model_name}' on device '{device}'...")

        # If model_name is relative, check project root or download
        model_path = model_name
        if not os.path.isabs(model_path):
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            cand = os.path.join(project_root, model_name)
            if os.path.exists(cand):
                model_path = cand

        _SAM_MODEL_INSTANCE = FastSAM(model_path)
        logger.info("FastSAM model initialized successfully.")
        return _SAM_MODEL_INSTANCE
    except Exception as e:
        logger.warning(f"Failed to initialize FastSAM model: {e}")
        return None


def order_quad_points(pts: np.ndarray) -> np.ndarray:
    """Sort quad corner points into standard order: [top-left, top-right, bottom-right, bottom-left]."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left
    rect[2] = pts[np.argmax(s)]  # bottom-right

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect


def extract_quad_corners_from_mask(mask: np.ndarray) -> Optional[np.ndarray]:
    """
    Finds the 4 prominent corners of the quadrilateral carpet boundary
    from a binary segmentation mask.
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Get the largest contour representing the carpet boundary
    largest_contour = max(contours, key=cv2.contourArea)
    hull = cv2.convexHull(largest_contour)
    peri = cv2.arcLength(hull, True)

    # Multi-step polygon approximation to converge to 4 corners
    for eps in np.linspace(0.015, 0.08, 20):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            pts = approx.reshape(4, 2)
            return order_quad_points(pts)

    # If exact 4 corners not found via DP, use minAreaRect
    min_rect = cv2.minAreaRect(hull)
    box = cv2.boxPoints(min_rect)
    return order_quad_points(box)


class CarpetSAMSegmentor:
    """
    High-precision zero-shot carpet boundary and occlusion segmenter using FastSAM.
    """

    def __init__(self, model_name: str = "FastSAM-s.pt", conf_threshold: float = 0.35):
        self.model_name = model_name
        self.conf_threshold = conf_threshold
        self.model = get_sam_model(model_name)

    @property
    def is_available(self) -> bool:
        return self.model is not None

    def segment_carpet(
        self,
        image_bgr: np.ndarray
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], float]:
        """
        Runs FastSAM to segment the carpet from its background floor/room.
        Returns:
            - carpet_mask: (H, W) uint8 binary mask (255 inside carpet, 0 outside)
            - corners: (4, 2) float32 ordered coordinates [TL, TR, BR, BL]
            - confidence: float score (0.0 to 1.0)
        """
        if not self.is_available:
            return None, None, 0.0

        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

            h, w = image_bgr.shape[:2]
            img_area = h * w

            results = self.model(
                image_bgr,
                device=device,
                retina_masks=True,
                imgsz=max(h, w, 1024),
                conf=self.conf_threshold,
                iou=0.85,
                verbose=False
            )

            if not results or results[0].masks is None:
                logger.warning("FastSAM detected no masks in image.")
                return None, None, 0.0

            masks_tensor = results[0].masks.data.cpu().numpy()
            if len(masks_tensor) == 0:
                return None, None, 0.0

            # Resize masks if needed to match original image shape
            resized_masks = []
            for m in masks_tensor:
                if m.shape[:2] != (h, w):
                    m_resized = cv2.resize(m.astype(np.float32), (w, h), interpolation=cv2.INTER_NEAREST)
                else:
                    m_resized = m
                resized_masks.append(m_resized > 0.5)

            # Filter masks by area and central proximity (carpet usually occupies > 15% of frame)
            candidates = []
            for m in resized_masks:
                area = np.sum(m)
                if area > 0.15 * img_area:
                    candidates.append((area, m))

            if not candidates:
                # Take the largest detected mask overall
                candidates = [(np.sum(m), m) for m in resized_masks]

            candidates.sort(key=lambda x: x[0], reverse=True)
            best_mask = (candidates[0][1] * 255).astype(np.uint8)

            # Morphological smoothing to clean fringes and edges
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
            cleaned_mask = cv2.morphologyEx(best_mask, cv2.MORPH_CLOSE, kernel)

            # Extract corners
            corners = extract_quad_corners_from_mask(cleaned_mask)
            if corners is None:
                return cleaned_mask, None, 0.65

            # Calculate confidence based on coverage and geometric rectangularity
            mask_area = np.sum(cleaned_mask > 0)
            coverage_ratio = mask_area / float(img_area)
            confidence = min(0.98, max(0.75, 0.70 + (coverage_ratio * 0.3)))

            return cleaned_mask, corners, float(confidence)

        except Exception as e:
            logger.error(f"Error during FastSAM carpet segmentation: {e}", exc_info=True)
            return None, None, 0.0

    def detect_occlusion_defects(
        self,
        image_bgr: np.ndarray,
        carpet_mask: np.ndarray
    ) -> np.ndarray:
        """
        Detects foreign objects sitting on top of the carpet (table legs, shoes, labels)
        by finding isolated internal segmentation masks.
        """
        h, w = image_bgr.shape[:2]
        defect_mask = np.zeros((h, w), dtype=np.uint8)

        if not self.is_available:
            return defect_mask

        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

            results = self.model(
                image_bgr,
                device=device,
                retina_masks=True,
                imgsz=max(h, w, 1024),
                conf=0.25,  # lower threshold to catch small foreign objects
                iou=0.7,
                verbose=False
            )

            if not results or results[0].masks is None:
                return defect_mask

            masks_tensor = results[0].masks.data.cpu().numpy()
            carpet_bool = carpet_mask > 0

            for m in masks_tensor:
                if m.shape[:2] != (h, w):
                    m = cv2.resize(m.astype(np.float32), (w, h), interpolation=cv2.INTER_NEAREST)
                m_bool = m > 0.5
                area = np.sum(m_bool)

                # If object is inside the carpet and small/medium (0.1% to 12% of image), it's likely an occlusion/defect
                overlap = np.sum(m_bool & carpet_bool)
                if area > 100 and area < (0.12 * h * w) and (overlap / float(area)) > 0.80:
                    defect_mask[m_bool] = 255

            return defect_mask

        except Exception as e:
            logger.warning(f"SAM defect detection fallback: {e}")
            return defect_mask
