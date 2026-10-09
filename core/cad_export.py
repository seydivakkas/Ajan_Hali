"""
CAD & Jacquard CAM Export Engine: DXF, SVG and Loom Instruction Matrix (.EP / .DAT / .TXT)
"""
import os
from html import escape
import cv2
import numpy as np
from typing import List, Dict, Any, Tuple


def export_dxf(
    loom_grid: np.ndarray,
    color_stats: List[Dict[str, Any]],
    output_dxf_path: str,
    carpet_width_mm: float = 1600.0,
    carpet_length_mm: float = 2300.0
) -> str:
    """
    Generates a production-compliant ASCII DXF (Release 12 / AC1009) file.
    Creates layered vector polygons for each yarn color code and technical dimension bounding box.
    """
    h_grid, w_grid = loom_grid.shape
    cell_w_mm = carpet_width_mm / float(w_grid)
    cell_h_mm = carpet_length_mm / float(h_grid)

    dxf_lines = [
        "0", "SECTION",
        "2", "HEADER",
        "9", "$ACADVER",
        "1", "AC1009",
        "9", "$INSUNITS",
        "70", "4",  # Millimeters
        "0", "ENDSEC",
        "0", "SECTION",
        "2", "TABLES",
        "0", "TABLE",
        "2", "LAYER",
        "70", str(len(color_stats) + 2),
    ]

    # Define CAD layers for each color
    layer_aci_colors = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    for idx, stat in enumerate(color_stats):
        layer_name = f"YARN_{stat['palette_code']}"
        aci = layer_aci_colors[idx % len(layer_aci_colors)]
        dxf_lines.extend([
            "0", "LAYER",
            "2", layer_name,
            "70", "0",
            "62", str(aci),
            "6", "CONTINUOUS"
        ])

    # Outer border layer
    dxf_lines.extend([
        "0", "LAYER",
        "2", "BORDER_OUTLINE",
        "70", "0",
        "62", "7",  # White
        "6", "CONTINUOUS",
        "0", "ENDTAB",
        "0", "ENDSEC",
        "0", "SECTION",
        "2", "ENTITIES"
    ])

    # 1. Add outer boundary rectangle polyline
    dxf_lines.extend([
        "0", "POLYLINE",
        "8", "BORDER_OUTLINE",
        "66", "1",
        "70", "1",  # Closed polyline
        "0", "VERTEX", "8", "BORDER_OUTLINE", "10", "0.0", "20", "0.0", "30", "0.0",
        "0", "VERTEX", "8", "BORDER_OUTLINE", "10", str(carpet_width_mm), "20", "0.0", "30", "0.0",
        "0", "VERTEX", "8", "BORDER_OUTLINE", "10", str(carpet_width_mm), "20", str(carpet_length_mm), "30", "0.0",
        "0", "VERTEX", "8", "BORDER_OUTLINE", "10", "0.0", "20", str(carpet_length_mm), "30", "0.0",
        "0", "SEQEND"
    ])

    # 2. Extract contour boundaries for each color layer to make a crisp vector drawing
    for stat in color_stats:
        p_idx = stat["palette_index"]
        layer_name = f"YARN_{stat['palette_code']}"
        binary_mask = (loom_grid == p_idx).astype(np.uint8) * 255

        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_TC89_KCOS)

        for cnt in contours:
            if cv2.contourArea(cnt) < 2.0:
                continue

            # Simplify polyline
            approx = cv2.approxPolyDP(cnt, 1.2, True)
            if len(approx) < 3:
                continue

            dxf_lines.extend([
                "0", "POLYLINE",
                "8", layer_name,
                "66", "1",
                "70", "1"
            ])

            for pt in approx:
                gx, gy = pt[0][0], pt[0][1]
                # Convert grid coords to physical mm
                x_mm = gx * cell_w_mm
                # DXF Y goes upwards; image Y goes downwards
                y_mm = (h_grid - gy) * cell_h_mm
                dxf_lines.extend([
                    "0", "VERTEX",
                    "8", layer_name,
                    "10", f"{x_mm:.2f}",
                    "20", f"{y_mm:.2f}",
                    "30", "0.0"
                ])

            dxf_lines.extend(["0", "SEQEND"])

    dxf_lines.extend(["0", "ENDSEC", "0", "EOF"])

    os.makedirs(os.path.dirname(os.path.abspath(output_dxf_path)), exist_ok=True)
    with open(output_dxf_path, "w", encoding="utf-8") as f:
        f.write("\n".join(dxf_lines))

    return output_dxf_path


def export_svg(
    loom_grid: np.ndarray,
    color_stats: List[Dict[str, Any]],
    output_svg_path: str,
    carpet_width_mm: float = 1600.0,
    carpet_length_mm: float = 2300.0
) -> str:
    """
    Export scalable vector graphic (SVG) with color groups and vector paths.
    """
    h_grid, w_grid = loom_grid.shape
    scale_x = carpet_width_mm / float(w_grid)
    scale_y = carpet_length_mm / float(h_grid)

    svg_header = f"""<svg xmlns="http://www.w3.org/2000/svg" 
     viewBox="0 0 {carpet_width_mm} {carpet_length_mm}" 
     width="{carpet_width_mm}mm" height="{carpet_length_mm}mm">
  <desc>Merinos Industrial Textile Weave Map - Size: {carpet_width_mm}x{carpet_length_mm}mm - Grid: {w_grid}x{h_grid}</desc>
  <rect width="100%" height="100%" fill="#1a1a1a"/>
"""
    svg_body = []

    for stat in color_stats:
        p_idx = stat["palette_index"]
        code = stat["palette_code"]
        name = escape(stat["yarn_name"], quote=True)
        rgb = stat["mapped_rgb"]
        rgb_hex = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

        svg_body.append(f'  <g id="layer_{code}" data-yarn="{name}" fill="{rgb_hex}" stroke="#222" stroke-width="0.3">')

        binary_mask = (loom_grid == p_idx).astype(np.uint8) * 255
        contours, _ = cv2.findContours(binary_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            if cv2.contourArea(cnt) < 3.0:
                continue
            approx = cv2.approxPolyDP(cnt, 1.0, True)
            if len(approx) < 3:
                continue

            path_d = []
            for i, pt in enumerate(approx):
                px = pt[0][0] * scale_x
                py = pt[0][1] * scale_y
                cmd = "M" if i == 0 else "L"
                path_d.append(f"{cmd} {px:.1f} {py:.1f}")
            path_d.append("Z")
            svg_body.append(f'    <path d="{" ".join(path_d)}"/>')

        svg_body.append("  </g>")

    svg_footer = "</svg>"

    os.makedirs(os.path.dirname(os.path.abspath(output_svg_path)), exist_ok=True)
    with open(output_svg_path, "w", encoding="utf-8") as f:
        f.write(svg_header + "\n".join(svg_body) + "\n" + svg_footer)

    return output_svg_path


def export_jacquard_matrix(
    loom_grid: np.ndarray,
    color_stats: List[Dict[str, Any]],
    output_jacquard_path: str
) -> str:
    """
    Exports Electronic Jacquard Machine Instruction Matrix (.DAT / .EP / .TXT).
    First section contains metadata headers (reed, pick, colors).
    Second section contains row-by-row palette index strings for the jacquard controller.
    """
    h_rows, w_cols = loom_grid.shape
    lines = [
        "# MERINOS INDUSTRIAL JACQUARD WEAVING MATRIX",
        f"# WARP_COLUMNS: {w_cols}",
        f"# WEFT_ROWS: {h_rows}",
        f"# PALETTE_COLOR_COUNT: {len(color_stats)}",
        "# PALETTE_ASSIGNMENTS:"
    ]

    for stat in color_stats:
        lines.append(f"# {stat['palette_index']}: CODE={stat['palette_code']} NAME={stat['yarn_name']} DTEX={stat['dtex']} RGB={stat['mapped_rgb']}")

    lines.append("# DATA_START")

    # Write each row as comma-separated or space-separated indices
    for row in loom_grid:
        lines.append(" ".join(map(str, row)))

    lines.append("# DATA_END")

    os.makedirs(os.path.dirname(os.path.abspath(output_jacquard_path)), exist_ok=True)
    with open(output_jacquard_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_jacquard_path
