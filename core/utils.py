"""
Cross-Platform Utility Helpers: Unicode-safe OpenCV I/O for Windows paths
"""
import os
import cv2
import numpy as np


def imread_safe(filepath: str) -> np.ndarray:
    """Reads image safely even with Turkish/non-ASCII characters in path on Windows."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    data = np.fromfile(filepath, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not decode image from: {filepath}")
    return img


def imwrite_safe(filepath: str, image: np.ndarray) -> bool:
    """Writes image safely even with Turkish/non-ASCII characters in path on Windows."""
    ext = os.path.splitext(filepath)[1] or ".png"
    success, encoded = cv2.imencode(ext, image)
    if success:
        encoded.tofile(filepath)
    return success
