"""
Industrial Loom CAM Protocols: Van de Wiele (.EP) & Stäubli (.JC5) Controllers
Telif Hakkı (c) 2026 Seydi Eryılmaz (@seydivakkas) - ÖZEL LİSANS / TÜM HAKLAR SAKLIDIR
"""
import os
import struct
import logging
from typing import List, Dict, Any, Tuple
import numpy as np

logger = logging.getLogger("LoomProtocols")


def remap_creel(grid, stats):
    """Translate sparse factory palette IDs to the exported creel table order."""
    result = np.zeros(grid.shape, dtype=np.uint8)
    known = np.zeros(grid.shape, dtype=bool)
    for slot, stat in enumerate(stats):
        mask = grid == stat["palette_index"]
        result[mask] = slot
        known |= mask
    if not known.all() or len(stats) > 16:
        raise ValueError("Invalid creel palette mapping")
    return result


def export_van_de_wiele_ep(
    loom_grid: np.ndarray,
    color_stats: List[Dict[str, Any]],
    output_ep_path: str,
    reed_density: int = 500,
    pick_density: int = 800,
    carpet_width_cm: float = 160.0,
    carpet_length_cm: float = 230.0
) -> str:
    """
    Generates a local prototype binary format. Vendor compatibility is unverified.

    Binary Structure:
      - 16 bytes: Magic Header 'VDW_EP_V2026\x00\x00\x00\x00'
      - 4 bytes uint32: Warp cell count (Width)
      - 4 bytes uint32: Pick cell count (Height)
      - 2 bytes uint16: Reed density (dents/m)
      - 2 bytes uint16: Pick density (shots/m)
      - 2 bytes uint16: Number of colors in creel (M)
      - M * 16 bytes: Creel Yarn Table (Code, Material ID, RGB)
      - Width * Height bytes: Cell-by-cell 8-bit Creel Hook Index
    """
    loom_grid = remap_creel(loom_grid, color_stats)
    h_grid, w_grid = loom_grid.shape
    num_colors = len(color_stats)

    os.makedirs(os.path.dirname(os.path.abspath(output_ep_path)), exist_ok=True)

    with open(output_ep_path, "wb") as f:
        # 1. Magic Header
        magic = b"VDW_EP_V2026\x00\x00\x00\x00"
        f.write(magic)

        # 2. Dimensions & Loom Specs
        f.write(struct.pack("<IIHHH", w_grid, h_grid, reed_density, pick_density, num_colors))

        # 3. Creel Palette Table
        palette_map = {}
        for idx, col in enumerate(color_stats):
            code_bytes = col["palette_code"].encode("ascii")[:8].ljust(8, b"\x00")
            r, g, b = col["mapped_rgb"]
            # 8 bytes code + 3 bytes RGB + 5 bytes padding = 16 bytes
            entry = code_bytes + struct.pack("<BBB", r, g, b) + (b"\x00" * 5)
            f.write(entry)
            palette_map[idx] = idx

        # 4. Pattern Matrix Payload (Row by Row)
        # loom_grid contains color indices 0 to num_colors - 1
        payload = loom_grid.astype(np.uint8).tobytes()
        f.write(payload)

        # 5. Checksum (CRC32-like simple sum)
        checksum = int(np.sum(loom_grid.astype(np.uint64))) & 0xFFFFFFFF
        f.write(struct.pack("<I", checksum))

    logger.info(f"Van de Wiele .EP CAM file exported: {output_ep_path} ({os.path.getsize(output_ep_path)} bytes)")
    return output_ep_path


def export_staubli_jc5(
    loom_grid: np.ndarray,
    color_stats: List[Dict[str, Any]],
    output_jc5_path: str,
    reed_density: int = 500,
    pick_density: int = 800
) -> str:
    """
    Generates a Stäubli Jacquard Controller (.JC5 / .DAT) electronic jacquard file.
    Local prototype only; vendor controller compatibility is unverified.
    """
    loom_grid = remap_creel(loom_grid, color_stats)
    h_grid, w_grid = loom_grid.shape
    os.makedirs(os.path.dirname(os.path.abspath(output_jc5_path)), exist_ok=True)

    header_lines = [
        "%%STAUBLI_JC5_CAD_SPECIFICATION%%",
        "CONTROLLER_TYPE=STAUBLI_JC5_ELECTRONIC",
        f"GRID_WARP_POINTS={w_grid}",
        f"GRID_WEFT_PICKS={h_grid}",
        f"REED_DENSITY_PBM={reed_density}",
        f"PICK_DENSITY_PPM={pick_density}",
        f"CREEL_COLORS_COUNT={len(color_stats)}",
        "ENCODING=INDEXED_HEX_PER_PICK",
        "BEGIN_PALETTE"
    ]

    for idx, col in enumerate(color_stats):
        rgb_hex = f"#{col['mapped_rgb'][0]:02X}{col['mapped_rgb'][1]:02X}{col['mapped_rgb'][2]:02X}"
        header_lines.append(f"COLOR_{idx:02d}={col['palette_code']},{rgb_hex},{col['yarn_name']}")

    header_lines.append("END_PALETTE")
    header_lines.append("BEGIN_WEAVE_MATRIX")

    with open(output_jc5_path, "w", encoding="utf-8") as f:
        for line in header_lines:
            f.write(line + "\n")

        # Write each pick row as compact hex sequence
        for row_idx in range(h_grid):
            row = loom_grid[row_idx, :]
            hex_str = "".join(f"{val:X}" for val in row)
            f.write(f"P{row_idx+1:06d}:{hex_str}\n")

        f.write("END_WEAVE_MATRIX\n")

    logger.info(f"Stäubli .JC5 CAM file exported: {output_jc5_path} ({os.path.getsize(output_jc5_path)} bytes)")
    return output_jc5_path


def dispatch_cam_file_to_loom(
    file_path: str,
    loom_ip_address: str,
    loom_name: str = "Tezgâh-01 (Van de Wiele)",
    protocol: str = "FTP"
) -> Dict[str, Any]:
    """
    Simulates sending the generated CAM file over the factory plant network
    directly to the electronic jacquard loom console.
    """
    if not os.path.exists(file_path):
        return {"status": "ERROR", "message": f"File {file_path} not found"}

    file_size_kb = os.path.getsize(file_path) / 1024.0
    filename = os.path.basename(file_path)

    # In actual mill production, uses ftplib or smbclient to copy to loom disk
    return {
        "status": "SIMULATED",
        "loom_name": loom_name,
        "loom_ip": loom_ip_address,
        "filename": filename,
        "file_size_kb": round(file_size_kb, 2),
        "protocol": protocol,
        "message": f"{filename} ({file_size_kb:.1f} KB) {loom_name} ({loom_ip_address}) için aktarım simülasyonu; ağ üzerinden dosya gönderilmedi."
    }
