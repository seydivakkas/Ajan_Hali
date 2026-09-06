"""
Textile Manufacturing Yarn Recipe & Physical Consumption Engine
"""
import math
from typing import List, Dict, Any, Optional, Tuple
from core.models import LoomConfig, FactoryPaletteItem, YarnConsumptionItem
from core.color_quantizer import ciede2000_single


def calculate_yarn_recipe(
    loom_cfg: LoomConfig,
    color_statistics: List[Dict[str, Any]],
    palette_inventory: List[Dict[str, Any]]
) -> Tuple[List[YarnConsumptionItem], Dict[str, Any]]:
    """
    Computes precise yarn length, net/gross weight (kg), bobbin counts,
    financial costs, and warehouse stock balance for each mapped color.
    """
    width_m = loom_cfg.width_cm / 100.0
    length_m = loom_cfg.length_cm / 100.0
    carpet_area_sqm = width_m * length_m
    total_order_area_sqm = carpet_area_sqm * loom_cfg.order_quantity

    # 1. Total knots in one woven carpet
    total_knots_per_carpet = round(width_m * loom_cfg.reed_density) * round(length_m * loom_cfg.pick_density)

    # 2. Yarn consumed per individual knot (U-loop cut pile + anchoring base)
    # 2 * pile_height * take-up + 3.2mm back anchor
    pile_m = loom_cfg.pile_height_mm / 1000.0
    loop_length_m = (2.0 * pile_m * loom_cfg.weave_structure_factor) + loom_cfg.anchor_length_mm / 1000.0

    # Map inventory by code
    inv_map = {item["code"]: item for item in palette_inventory}

    recipe_items: List[YarnConsumptionItem] = []
    total_order_weight_kg = 0.0
    total_order_cost_tl = 0.0
    has_any_shortage = False

    for stat in color_statistics:
        code = stat["palette_code"]
        inv_item = inv_map[code]
        dtex = inv_item["dtex"]
        cost_kg = inv_item["cost_per_kg_tl"]
        bobbin_weight = inv_item["bobbin_weight_kg"]
        stock_kg = inv_item["stock_kg"]
        mat = inv_item["material"]

        pct = stat["area_percentage"]
        area_ratio = pct / 100.0

        # Surface area for this color
        surf_sqm_carpet = carpet_area_sqm * area_ratio
        total_surf_sqm = total_order_area_sqm * area_ratio

        # Yarn length per carpet (m)
        knots_for_color = total_knots_per_carpet * area_ratio
        yarn_len_single_m = knots_for_color * loop_length_m
        yarn_len_order_km = (yarn_len_single_m * loom_cfg.order_quantity) / 1000.0

        # Mass (kg) = length (m) * (dtex / 10^7)
        # dtex is grams per 10,000 meters -> 1 dtex = 1e-7 kg/m
        net_weight_single_kg = yarn_len_single_m * (dtex * 1e-7)
        net_weight_order_kg = net_weight_single_kg * loom_cfg.order_quantity

        # Gross weight including waste/fire factor
        gross_weight_order_kg = net_weight_order_kg * (1.0 + loom_cfg.waste_coefficient)

        # Bobbin requirement
        bobbin_count = int(math.ceil(gross_weight_order_kg / bobbin_weight)) if bobbin_weight > 0 else 1

        # Stock comparison
        is_sufficient = (stock_kg >= gross_weight_order_kg)
        shortage_kg = max(0.0, gross_weight_order_kg - stock_kg)

        alt_yarn = None
        if not is_sufficient:
            has_any_shortage = True
            # Find closest alternative in stock via CIEDE2000
            current_lab = inv_item.get("lab", [50, 0, 0])
            best_alt = None
            min_alt_de = float("inf")
            for other_item in palette_inventory:
                if other_item["code"] != code and other_item.get("stock_kg", 0) >= gross_weight_order_kg:
                    de = ciede2000_single(current_lab, other_item["lab"])
                    if de < min_alt_de:
                        min_alt_de = de
                        best_alt = other_item["code"]
            alt_yarn = best_alt

        cost_for_color = gross_weight_order_kg * cost_kg
        total_order_weight_kg += gross_weight_order_kg
        total_order_cost_tl += cost_for_color

        recipe_items.append(YarnConsumptionItem(
            yarn_code=code,
            yarn_name=stat["yarn_name"],
            material=mat,
            dtex=dtex,
            area_percentage=round(pct, 2),
            surface_area_sqm_per_carpet=round(surf_sqm_carpet, 4),
            total_surface_area_sqm=round(total_surf_sqm, 2),
            yarn_length_m_per_carpet=round(yarn_len_single_m, 1),
            total_yarn_length_km=round(yarn_len_order_km, 2),
            yarn_weight_kg_per_carpet=round(net_weight_single_kg, 3),
            total_weight_kg_net=round(net_weight_order_kg, 2),
            total_weight_kg_gross_with_waste=round(gross_weight_order_kg, 2),
            bobbin_count_required=bobbin_count,
            stock_available_kg=round(stock_kg, 1),
            stock_shortage_kg=round(shortage_kg, 2),
            unit_cost_tl=round(cost_kg, 2),
            total_cost_tl=round(cost_for_color, 2),
            is_stock_sufficient=is_sufficient,
            alternative_yarn_code=alt_yarn
        ))

    summary = {
        "carpet_dimensions_cm": [loom_cfg.width_cm, loom_cfg.length_cm],
        "carpet_area_sqm": round(carpet_area_sqm, 3),
        "order_quantity": loom_cfg.order_quantity,
        "total_order_area_sqm": round(total_order_area_sqm, 2),
        "total_order_yarn_kg": round(total_order_weight_kg, 2),
        "total_order_cost_tl": round(sum(item.total_cost_tl for item in recipe_items), 2),
        "average_cost_per_carpet_tl": round(total_order_cost_tl / max(1, loom_cfg.order_quantity), 2),
        "yarn_weight_per_sqm_kg": round(total_order_weight_kg / max(0.01, total_order_area_sqm), 3),
        "has_stock_shortage": has_any_shortage
    }

    return recipe_items, summary
