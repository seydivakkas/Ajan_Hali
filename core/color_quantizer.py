"""
Color Space Conversion, CIEDE2000 Metric & Production Color Quantization Engine
"""
import math
import numpy as np
from typing import List, Tuple, Dict, Any
from sklearn.cluster import KMeans
from scipy.ndimage import median_filter


def srgb_to_xyz(rgb: np.ndarray) -> np.ndarray:
    """
    Convert sRGB (0-255) to CIE XYZ (D65 illuminant, 2° observer).
    Applies standard sRGB gamma decoding (inverse companding).
    """
    rgb_norm = rgb.astype(np.float64) / 255.0
    # Inverse sRGB companding
    mask = rgb_norm > 0.04045
    rgb_linear = np.empty_like(rgb_norm)
    rgb_linear[mask] = ((rgb_norm[mask] + 0.055) / 1.055) ** 2.4
    rgb_linear[~mask] = rgb_norm[~mask] / 12.92

    # sRGB to XYZ transform matrix (D65)
    matrix = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041]
    ])
    xyz = np.dot(rgb_linear, matrix.T)
    return xyz * 100.0


def xyz_to_lab(xyz: np.ndarray) -> np.ndarray:
    """
    Convert CIE XYZ to CIE L*a*b* using D65 reference white.
    Xn = 95.0489, Yn = 100.0, Zn = 108.8840
    """
    ref_white = np.array([95.0489, 100.000, 108.8840], dtype=np.float64)
    norm = xyz / ref_white

    delta = 6.0 / 29.0
    delta_sq = delta ** 2
    delta_cb = delta ** 3

    mask = norm > delta_cb
    f = np.empty_like(norm)
    f[mask] = norm[mask] ** (1.0 / 3.0)
    f[~mask] = (norm[~mask] / (3.0 * delta_sq)) + (4.0 / 29.0)

    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])

    return np.stack([L, a, b], axis=-1)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """End-to-end sRGB array to CIE Lab array conversion."""
    return xyz_to_lab(srgb_to_xyz(rgb))


def lab_to_xyz(lab: np.ndarray) -> np.ndarray:
    """Convert CIE L*a*b* back to CIE XYZ."""
    ref_white = np.array([95.0489, 100.000, 108.8840], dtype=np.float64)
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = (lab[..., 1] / 500.0) + fy
    fz = fy - (lab[..., 2] / 200.0)

    delta = 6.0 / 29.0
    xyz = np.empty_like(lab)

    # x
    mask_x = fx > delta
    xyz[..., 0] = np.where(mask_x, fx ** 3, 3.0 * (delta ** 2) * (fx - 4.0 / 29.0)) * ref_white[0]

    # y
    mask_y = fy > delta
    xyz[..., 1] = np.where(mask_y, fy ** 3, 3.0 * (delta ** 2) * (fy - 4.0 / 29.0)) * ref_white[1]

    # z
    mask_z = fz > delta
    xyz[..., 2] = np.where(mask_z, fz ** 3, 3.0 * (delta ** 2) * (fz - 4.0 / 29.0)) * ref_white[2]

    return xyz


def xyz_to_srgb(xyz: np.ndarray) -> np.ndarray:
    """Convert CIE XYZ back to sRGB (0-255)."""
    xyz_norm = xyz / 100.0
    matrix_inv = np.array([
        [ 3.2404542, -1.5371385, -0.4985314],
        [-0.9692660,  1.8760108,  0.0415560],
        [ 0.0556434, -0.2040259,  1.0572252]
    ])
    rgb_linear = np.dot(xyz_norm, matrix_inv.T)
    rgb_linear = np.clip(rgb_linear, 0.0, 1.0)

    mask = rgb_linear > 0.0031308
    rgb_companded = np.empty_like(rgb_linear)
    rgb_companded[mask] = 1.055 * (rgb_linear[mask] ** (1.0 / 2.4)) - 0.055
    rgb_companded[~mask] = 12.92 * rgb_linear[~mask]

    return np.clip(np.round(rgb_companded * 255.0), 0, 255).astype(np.uint8)


def lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    return xyz_to_srgb(lab_to_xyz(lab))


def ciede2000_single(lab1: np.ndarray, lab2: np.ndarray, kl: float = 1.0, kc: float = 1.0, kh: float = 1.0) -> float:
    """
    Calculate CIEDE2000 color difference between two Lab points.
    Implements ISO/CIE 11664-6:2014 Standard.
    """
    L1, a1, b1 = lab1[0], lab1[1], lab1[2]
    L2, a2, b2 = lab2[0], lab2[1], lab2[2]

    C1 = math.sqrt(a1 * a1 + b1 * b1)
    C2 = math.sqrt(a2 * a2 + b2 * b2)
    C_bar = 0.5 * (C1 + C2)

    C_bar7 = C_bar ** 7
    G = 0.5 * (1.0 - math.sqrt(C_bar7 / (C_bar7 + 6103515625.0)))  # 25^7 = 6103515625

    a1_prime = (1.0 + G) * a1
    a2_prime = (1.0 + G) * a2

    C1_prime = math.sqrt(a1_prime * a1_prime + b1 * b1)
    C2_prime = math.sqrt(a2_prime * a2_prime + b2 * b2)

    h1_prime = math.degrees(math.atan2(b1, a1_prime)) % 360.0
    h2_prime = math.degrees(math.atan2(b2, a2_prime)) % 360.0

    delta_L_prime = L2 - L1
    delta_C_prime = C2_prime - C1_prime

    if C1_prime * C2_prime == 0:
        delta_h_prime = 0.0
    else:
        diff_h = h2_prime - h1_prime
        if abs(diff_h) <= 180.0:
            delta_h_prime = diff_h
        elif diff_h > 180.0:
            delta_h_prime = diff_h - 360.0
        else:
            delta_h_prime = diff_h + 360.0

    delta_H_prime = 2.0 * math.sqrt(C1_prime * C2_prime) * math.sin(math.radians(delta_h_prime / 2.0))

    L_bar_prime = 0.5 * (L1 + L2)
    C_bar_prime = 0.5 * (C1_prime + C2_prime)

    if C1_prime * C2_prime == 0:
        h_bar_prime = h1_prime + h2_prime
    else:
        diff_h = abs(h1_prime - h2_prime)
        if diff_h <= 180.0:
            h_bar_prime = 0.5 * (h1_prime + h2_prime)
        elif (h1_prime + h2_prime) < 360.0:
            h_bar_prime = 0.5 * (h1_prime + h2_prime + 360.0)
        else:
            h_bar_prime = 0.5 * (h1_prime + h2_prime - 360.0)

    T = (1.0 - 0.17 * math.cos(math.radians(h_bar_prime - 30.0))
             + 0.24 * math.cos(math.radians(2.0 * h_bar_prime))
             + 0.32 * math.cos(math.radians(3.0 * h_bar_prime + 6.0))
             - 0.20 * math.cos(math.radians(4.0 * h_bar_prime - 63.0)))

    delta_theta = 30.0 * math.exp(-(((h_bar_prime - 275.0) / 25.0) ** 2))
    C_bar_prime7 = C_bar_prime ** 7
    RC = 2.0 * math.sqrt(C_bar_prime7 / (C_bar_prime7 + 6103515625.0))
    RT = -math.sin(math.radians(2.0 * delta_theta)) * RC

    L_term = (L_bar_prime - 50.0) ** 2
    SL = 1.0 + (0.015 * L_term) / math.sqrt(20.0 + L_term)
    SC = 1.0 + 0.045 * C_bar_prime
    SH = 1.0 + 0.015 * C_bar_prime * T

    term_L = delta_L_prime / (kl * SL)
    term_C = delta_C_prime / (kc * SC)
    term_H = delta_H_prime / (kh * SH)

    delta_E = math.sqrt(term_L * term_L + term_C * term_C + term_H * term_H + RT * term_C * term_H)
    return float(delta_E)


class CarpetColorQuantizer:
    """
    Industrial carpet color quantization and factory yarn assignment engine.
    Supports Mode A (Free k-means in Lab) and Mode B (Forced Factory Palette Mapping).
    """

    def __init__(self, factory_palette: List[Dict[str, Any]]):
        self.palette = factory_palette
        self.palette_labs = np.array([item["lab"] for item in factory_palette], dtype=np.float64)
        self.palette_rgbs = np.array([item["rgb"] for item in factory_palette], dtype=np.uint8)
        self.palette_codes = [item["code"] for item in factory_palette]

    def quantize_and_map(
        self,
        image_rgb: np.ndarray,
        max_colors: int = 8,
        mode: str = "FORCED_PALETTE",
        clean_islands: bool = True,
        min_island_pixels: int = 4
    ) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]], Dict[str, float]]:
        """
        Executes color quantization and factory yarn assignment.
        Returns:
            - quantized_rgb (H, W, 3)
            - index_map (H, W) indices of mapped palette colors
            - color_statistics (list of stats per color)
            - audit_metrics (avg, max, p95 DeltaE)
        """
        h, w, _ = image_rgb.shape
        flat_rgb = image_rgb.reshape(-1, 3)

        # 1. Convert sample or all pixels to LAB
        # Use subsampling for fast k-means if image is large
        flat_lab = srgb_to_lab(flat_rgb)

        if mode == "FREE_QUANTIZATION":
            # Mode A: K-means clustering in Lab space
            kmeans = KMeans(n_clusters=max_colors, random_state=42, n_init=5)
            cluster_labels = kmeans.fit_predict(flat_lab)
            cluster_centers_lab = kmeans.cluster_centers_

            # Convert centers back to sRGB
            centers_rgb = lab_to_srgb(cluster_centers_lab)
            quant_rgb_flat = centers_rgb[cluster_labels]
            index_flat = cluster_labels
            selected_palette = [
                {
                    "code": f"FREE-{i+1}",
                    "name": f"Cluster Renk {i+1}",
                    "material": "Bilinmeyen",
                    "dtex": 1800,
                    "rgb": centers_rgb[i].tolist(),
                    "lab": cluster_centers_lab[i].tolist(),
                    "cost_per_kg_tl": 150.0,
                    "bobbin_weight_kg": 4.5,
                    "stock_kg": 999.0
                }
                for i in range(max_colors)
            ]
        else:
            # Mode B: Forced Factory Palette Mapping
            # First reduce to intermediate k clusters (e.g. 24 or 32) or directly map centroids
            n_intermediate = min(32, max(max_colors * 2, 16))
            kmeans = KMeans(n_clusters=n_intermediate, random_state=42, n_init=4)
            intermediate_labels = kmeans.fit_predict(flat_lab)
            intermediate_centers = kmeans.cluster_centers_

            # Map each intermediate centroid to the best factory palette color via CIEDE2000
            center_to_palette_idx = []
            for c_lab in intermediate_centers:
                best_idx = 0
                min_de = float("inf")
                for p_idx, p_lab in enumerate(self.palette_labs):
                    de = ciede2000_single(c_lab, p_lab)
                    if de < min_de:
                        min_de = de
                        best_idx = p_idx
                center_to_palette_idx.append(best_idx)

            center_to_palette_idx = np.array(center_to_palette_idx)
            mapped_indices = center_to_palette_idx[intermediate_labels]

            # If unique factory colors exceed max_colors, prune least frequent colors
            unique_indices, counts = np.unique(mapped_indices, return_counts=True)
            if len(unique_indices) > max_colors:
                # Keep top max_colors most frequent
                sorted_by_freq = unique_indices[np.argsort(-counts)]
                allowed_indices = set(sorted_by_freq[:max_colors])

                # Remap the pruned indices to the closest allowed palette color
                allowed_list = list(allowed_indices)
                allowed_labs = self.palette_labs[allowed_list]

                for p_idx in unique_indices:
                    if p_idx not in allowed_indices:
                        # Find closest in allowed
                        target_lab = self.palette_labs[p_idx]
                        best_sub_idx = allowed_list[np.argmin([
                            ciede2000_single(target_lab, al_lab) for al_lab in allowed_labs
                        ])]
                        mapped_indices[mapped_indices == p_idx] = best_sub_idx

            index_flat = mapped_indices
            quant_rgb_flat = self.palette_rgbs[index_flat]
            selected_palette = self.palette

        quant_rgb = quant_rgb_flat.reshape(h, w, 3)
        index_map = index_flat.reshape(h, w)

        # 3. Morphological smoothing to remove isolated 1-2 knot pixel noise
        if clean_islands:
            # Apply median filter to index map to prevent loom yarn jump defects
            index_map = median_filter(index_map, size=3)
            # Re-update quantized rgb from smoothed index map
            if mode == "FREE_QUANTIZATION":
                quant_rgb = centers_rgb[index_map]
            else:
                quant_rgb = self.palette_rgbs[index_map]

        # 4. Color statistics & DeltaE calculation
        unique_colors, pixel_counts = np.unique(index_map, return_counts=True)
        total_pixels = h * w
        stats = []
        all_delta_es = []

        for c_idx, count in zip(unique_colors, pixel_counts):
            pct = (count / total_pixels) * 100.0
            p_item = selected_palette[c_idx] if c_idx < len(selected_palette) else self.palette[0]

            # Compute DeltaE on pixels assigned to this color
            mask = (index_map == c_idx)
            sample_orig_lab = flat_lab.reshape(h, w, 3)[mask]
            # Take representative sample (up to 200 points)
            if len(sample_orig_lab) > 200:
                indices_sub = np.random.choice(len(sample_orig_lab), 200, replace=False)
                sample_orig_lab = sample_orig_lab[indices_sub]

            target_lab = np.array(p_item["lab"], dtype=np.float64)
            color_des = [ciede2000_single(px_lab, target_lab) for px_lab in sample_orig_lab]

            de_avg = float(np.mean(color_des)) if color_des else 0.0
            de_max = float(np.max(color_des)) if color_des else 0.0
            all_delta_es.extend(color_des)

            stats.append({
                "palette_index": int(c_idx),
                "palette_code": p_item["code"],
                "yarn_name": p_item["name"],
                "material": p_item["material"],
                "dtex": p_item["dtex"],
                "cost_per_kg_tl": p_item.get("cost_per_kg_tl", 150.0),
                "bobbin_weight_kg": p_item.get("bobbin_weight_kg", 4.5),
                "stock_kg": p_item.get("stock_kg", 500.0),
                "mapped_rgb": p_item["rgb"],
                "pixel_count": int(count),
                "area_percentage": round(float(pct), 2),
                "ciede2000_delta_e_avg": round(de_avg, 2),
                "ciede2000_delta_e_max": round(de_max, 2)
            })

        # Sort stats by area percentage descending
        stats.sort(key=lambda x: x["area_percentage"], reverse=True)

        audit_metrics = {
            "delta_e_avg": round(float(np.mean(all_delta_es)), 2) if all_delta_es else 0.0,
            "delta_e_max": round(float(np.max(all_delta_es)), 2) if all_delta_es else 0.0,
            "delta_e_p95": round(float(np.percentile(all_delta_es, 95)), 2) if all_delta_es else 0.0,
        }

        return quant_rgb, index_map, stats, audit_metrics
