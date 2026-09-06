"""
Spectrophotometer Color Import Engine: X-Rite (.CXF) & Datacolor (.QTX)
Telif Hakkı (c) 2026 Seydi Eryılmaz (@seydivakkas) - ÖZEL LİSANS / TÜM HAKLAR SAKLIDIR
"""
import os
import json
import xml.etree.ElementTree as ET
import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("SpectroImport")

# CIE 1964 10-degree Standard Observer weights for D65 illuminant (400nm to 700nm in 10nm steps, 31 points)
# Values tabulated per ASTM E308 (normalized so Y = 100.0 for perfect diffuser)
D65_10DEG_WEIGHTS = {
    "wavelengths": list(range(400, 710, 10)),
    "Wx": [
        0.043, 0.203, 0.814, 2.146, 4.318, 5.617, 4.887, 3.197, 1.831, 1.050,
        0.755, 0.999, 1.942, 3.659, 6.096, 8.847, 11.233, 12.639, 12.784, 11.758,
        9.897, 7.643, 5.385, 3.498, 2.073, 1.139, 0.584, 0.285, 0.134, 0.061, 0.027
    ],
    "Wy": [
        0.003, 0.016, 0.068, 0.201, 0.528, 1.050, 1.890, 3.090, 4.717, 6.786,
        9.120, 11.455, 13.344, 14.372, 14.288, 12.986, 10.840, 8.411, 6.136, 4.195,
        2.671, 1.583, 0.880, 0.457, 0.222, 0.103, 0.046, 0.020, 0.008, 0.003, 0.001
    ],
    "Wz": [
        0.187, 0.893, 3.626, 9.774, 20.252, 27.648, 25.753, 18.232, 11.393, 7.026,
        5.279, 7.151, 14.004, 26.230, 42.690, 58.740, 68.618, 68.969, 60.015, 43.899,
        27.930, 15.353, 7.378, 3.091, 1.144, 0.380, 0.116, 0.033, 0.009, 0.002, 0.000
    ]
}


def spectral_to_xyz_d65(reflectance_values: List[float]) -> Tuple[float, float, float]:
    """
    Computes CIE Tristimulus Values X, Y, Z from 400nm-700nm reflectance spectrum (0.0 to 1.0 or 0 to 100).
    Uses CIE D65 10° Standard Observer tables.
    """
    refl = np.array(reflectance_values, dtype=np.float64)
    if np.max(refl) > 2.0:
        refl = refl / 100.0  # Normalize percentage to 0.0 - 1.0

    if len(refl) != 31:
        # Interpolate to 31 points (400-700 nm, 10nm step)
        x_orig = np.linspace(400, 700, len(refl))
        x_target = np.array(D65_10DEG_WEIGHTS["wavelengths"], dtype=np.float64)
        refl = np.interp(x_target, x_orig, refl)

    wx = np.array(D65_10DEG_WEIGHTS["Wx"], dtype=np.float64)
    wy = np.array(D65_10DEG_WEIGHTS["Wy"], dtype=np.float64)
    wz = np.array(D65_10DEG_WEIGHTS["Wz"], dtype=np.float64)

    X = float(np.sum(refl * wx))
    Y = float(np.sum(refl * wy))
    Z = float(np.sum(refl * wz))

    # Normalize so Y white point is ~100
    sum_wy = np.sum(wy)
    X = (X / sum_wy) * 100.0
    Y = (Y / sum_wy) * 100.0
    Z = (Z / sum_wy) * 100.0

    return X, Y, Z


def xyz_to_lab_d65(X: float, Y: float, Z: float) -> Tuple[float, float, float]:
    """Converts CIE XYZ to CIE L*a*b* using D65/10° reference white point (Xn=94.811, Yn=100.0, Zn=107.304)."""
    Xn, Yn, Zn = 94.811, 100.0, 107.304

    def f(t: float) -> float:
        delta = 6.0 / 29.0
        if t > delta ** 3:
            return t ** (1.0 / 3.0)
        return (t / (3.0 * delta ** 2)) + (4.0 / 29.0)

    fx = f(X / Xn)
    fy = f(Y / Yn)
    fz = f(Z / Zn)

    L = max(0.0, min(100.0, (116.0 * fy) - 16.0))
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)

    return round(L, 2), round(a, 2), round(b, 2)


def lab_to_srgb(L: float, a: float, b: float) -> List[int]:
    """Converts CIE L*a*b* back to sRGB [R, G, B] (0-255) for monitor preview."""
    # Lab to XYZ
    fy = (L + 16.0) / 116.0
    fx = (a / 500.0) + fy
    fz = fy - (b / 200.0)

    delta = 6.0 / 29.0
    Xn, Yn, Zn = 94.811, 100.0, 107.304

    x = Xn * (fx ** 3 if fx > delta else (fx - 16.0 / 116.0) * 3.0 * (delta ** 2))
    y = Yn * (fy ** 3 if fy > delta else (fy - 16.0 / 116.0) * 3.0 * (delta ** 2))
    z = Zn * (fz ** 3 if fz > delta else (fz - 16.0 / 116.0) * 3.0 * (delta ** 2))

    # XYZ to linear sRGB
    x_n, y_n, z_n = x / 100.0, y / 100.0, z / 100.0
    r_lin = 3.2406 * x_n - 1.5372 * y_n - 0.4986 * z_n
    g_lin = -0.9689 * x_n + 1.8758 * y_n + 0.0415 * z_n
    b_lin = 0.0557 * x_n - 0.2040 * y_n + 1.0570 * z_n

    def gamma(v: float) -> float:
        if v <= 0.0031308:
            return 12.92 * v
        return 1.055 * (v ** (1.0 / 2.4)) - 0.055

    r = int(np.clip(round(gamma(max(0.0, r_lin)) * 255.0), 0, 255))
    g = int(np.clip(round(gamma(max(0.0, g_lin)) * 255.0), 0, 255))
    b = int(np.clip(round(gamma(max(0.0, b_lin)) * 255.0), 0, 255))
    return [r, g, b]


def parse_datacolor_qtx(content_str: str) -> List[Dict[str, Any]]:
    """
    Parses Datacolor .QTX (Quality Control) spectrophotometer files.
    Extracts sample name, CIE Lab coordinates or raw spectral reflectance.
    """
    samples = []
    lines = content_str.splitlines()
    current_sample = {}
    reading_spectrum = False
    reflectances = []

    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue

        if line_s.startswith("NAME:"):
            if current_sample and ("lab" in current_sample or reflectances):
                if reflectances and "lab" not in current_sample:
                    X, Y, Z = spectral_to_xyz_d65(reflectances)
                    current_sample["lab"] = list(xyz_to_lab_d65(X, Y, Z))
                    current_sample["rgb"] = lab_to_srgb(*current_sample["lab"])
                samples.append(current_sample)
            current_sample = {
                "name": line_s.replace("NAME:", "").strip(),
                "device": "Datacolor Spectro",
                "format": "QTX"
            }
            reflectances = []
            reading_spectrum = False

        elif line_s.startswith("CIELAB:"):
            # Format: CIELAB: 85.2 2.1 14.5
            parts = line_s.replace("CIELAB:", "").strip().split()
            if len(parts) >= 3:
                L = float(parts[0])
                a = float(parts[1])
                b = float(parts[2])
                current_sample["lab"] = [L, a, b]
                current_sample["rgb"] = lab_to_srgb(L, a, b)

        elif "SPECTRUM:" in line_s or "[STD_DATA]" in line_s:
            reading_spectrum = True

        elif reading_spectrum:
            # Parse floating point reflectance values
            parts = line_s.split()
            for p in parts:
                try:
                    val = float(p)
                    reflectances.append(val)
                except ValueError:
                    reading_spectrum = False
                    break

    if current_sample:
        if reflectances and "lab" not in current_sample:
            X, Y, Z = spectral_to_xyz_d65(reflectances)
            current_sample["lab"] = list(xyz_to_lab_d65(X, Y, Z))
            current_sample["rgb"] = lab_to_srgb(*current_sample["lab"])
        samples.append(current_sample)

    return samples


def parse_xrite_cxf(xml_content_str: str) -> List[Dict[str, Any]]:
    """
    Parses X-Rite / ISO 17972 Color Exchange Format (.CXF / .CXF3) XML files.
    """
    samples = []
    try:
        root = ET.fromstring(xml_content_str)
        # Handle namespaces if present
        for sample_elem in root.iter():
            if sample_elem.tag.endswith("ColorSample") or sample_elem.tag.endswith("Sample"):
                name = sample_elem.attrib.get("Name", "X-Rite Yarn Sample")
                # Look for CIELab values
                for lab_elem in sample_elem.iter():
                    if lab_elem.tag.endswith("CIELab"):
                        L = float(lab_elem.findtext(".//L", "50.0"))
                        a = float(lab_elem.findtext(".//A", "0.0"))
                        b = float(lab_elem.findtext(".//B", "0.0"))
                        samples.append({
                            "name": name,
                            "device": "X-Rite Spectrophotometer",
                            "format": "CXF3",
                            "lab": [round(L, 2), round(a, 2), round(b, 2)],
                            "rgb": lab_to_srgb(L, a, b)
                        })
                        break
    except Exception as e:
        logger.error(f"Error parsing CXF XML: {e}")

    return samples


def add_spectro_yarn_to_palette(
    yarn_name: str,
    lab: List[float],
    material: str = "PP Heatset BCF",
    dtex: int = 1800,
    cost_per_kg: float = 150.0,
    palette_json_path: str = "palette/factory_palette.json"
) -> Dict[str, Any]:
    """
    Registers the newly spectrophotometer-measured dye lot into the factory palette.
    """
    if not os.path.exists(palette_json_path):
        raise FileNotFoundError(f"Palette file {palette_json_path} not found")

    with open(palette_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_colors = data.get("colors", [])
    next_id = len(existing_colors) + 1
    new_code = f"YRN-{next_id:02d}"

    rgb = lab_to_srgb(lab[0], lab[1], lab[2])

    new_yarn = {
        "code": new_code,
        "name": yarn_name,
        "material": material,
        "dtex": dtex,
        "rgb": rgb,
        "lab": [round(lab[0], 2), round(lab[1], 2), round(lab[2], 2)],
        "cost_per_kg_tl": cost_per_kg,
        "bobbin_weight_kg": 4.5,
        "stock_kg": 500.0
    }

    existing_colors.append(new_yarn)
    data["colors"] = existing_colors

    with open(palette_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Added new spectrophotometer measured yarn: {new_code} ({yarn_name}) to {palette_json_path}")
    return new_yarn
