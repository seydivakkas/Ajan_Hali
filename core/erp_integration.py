"""
ERP & MES Industrial Integration Layer: SAP, CANIAS & SQL Inventory Sync
Telif Hakkı (c) 2026 Seydi Eryılmaz (@seydivakkas) - ÖZEL LİSANS / TÜM HAKLAR SAKLIDIR
"""
import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("ERPIntegration")


class BaseERPProvider(ABC):
    """Abstract interface for Textile Enterprise Resource Planning (ERP) systems."""

    @abstractmethod
    def fetch_live_inventory(self) -> List[Dict[str, Any]]:
        """Fetch current yarn stock balances, dtex, and unit costs from warehouse."""
        pass

    @abstractmethod
    def check_stock_availability(self, yarn_code: str, required_kg: float) -> Dict[str, Any]:
        """Check if required yarn weight is available without negative stock."""
        pass

    @abstractmethod
    def reserve_yarn_for_order(self, job_id: str, recipe: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Locks yarn bobbins/weight in ERP for the planned carpet batch."""
        pass

    @abstractmethod
    def create_purchase_requisition(self, shortages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Triggers automated purchase order / requisition for shortage yarns."""
        pass


class MockERPProvider(BaseERPProvider):
    """
    Standard industrial mock provider connected directly to the local factory palette
    with real-time simulated reservation and stock updates.
    """

    def __init__(self, palette_json_path: str):
        self.palette_json_path = palette_json_path
        self._load_palette()

    def _load_palette(self):
        with open(self.palette_json_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    def fetch_live_inventory(self) -> List[Dict[str, Any]]:
        self._load_palette()
        return self.data.get("colors", [])

    def check_stock_availability(self, yarn_code: str, required_kg: float) -> Dict[str, Any]:
        self._load_palette()
        for item in self.data.get("colors", []):
            if item["code"] == yarn_code:
                available = float(item.get("stock_kg", 0.0))
                shortage = max(0.0, required_kg - available)
                return {
                    "yarn_code": yarn_code,
                    "yarn_name": item["name"],
                    "available_kg": available,
                    "required_kg": required_kg,
                    "is_sufficient": shortage <= 0.0,
                    "shortage_kg": round(shortage, 2),
                    "timestamp": datetime.now().isoformat()
                }
        return {"error": f"Yarn {yarn_code} not found in ERP"}

    def reserve_yarn_for_order(self, job_id: str, recipe: List[Dict[str, Any]]) -> Dict[str, Any]:
        self._load_palette()
        reservations = []
        for r in recipe:
            code = r.get("yarn_code") or r.get("code")
            needed = r.get("total_weight_kg_gross_with_waste", 0.0)
            reservations.append({
                "yarn_code": code,
                "reserved_kg": needed,
                "status": "SIMULATED"
            })
        return {
            "erp_status": "SIMULATED",
            "reservation_id": f"RES-{job_id}",
            "system": "MOCK-MES-2026",
            "reservations": reservations,
            "timestamp": datetime.now().isoformat()
        }

    def create_purchase_requisition(self, shortages: List[Dict[str, Any]]) -> Dict[str, Any]:
        pr_id = f"PR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        items = []
        total_estimated_cost = 0.0
        for s in shortages:
            qty = s.get("stock_shortage_kg", 0.0)
            cost = qty * s.get("unit_cost_tl", 150.0)
            total_estimated_cost += cost
            items.append({
                "material_code": s.get("yarn_code"),
                "quantity_kg": qty,
                "urgency": "HIGH",
                "estimated_cost_tl": round(cost, 2)
            })

        return {
            "purchase_requisition_id": pr_id,
            "status": "SIMULATED",
            "items": items,
            "total_estimated_cost_tl": round(total_estimated_cost, 2),
            "timestamp": datetime.now().isoformat()
        }


class SAPERPProvider(BaseERPProvider):
    """SAP S/4HANA & ECC Connector via RFC BAPI / OData REST Services."""

    def __init__(self, endpoint_url: str = "https://sap.factory.local/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV"):
        self.endpoint_url = endpoint_url

    def fetch_live_inventory(self) -> List[Dict[str, Any]]:
        # In production, queries SAP OData /A_MaterialStock endpoint
        logger.info(f"Querying SAP endpoint: {self.endpoint_url}")
        return []

    def check_stock_availability(self, yarn_code: str, required_kg: float) -> Dict[str, Any]:
        # Calls BAPI_MATERIAL_AVAILABILITY
        return {"erp": "SAP", "yarn_code": yarn_code, "status": "SIMULATED_SAP_OK"}

    def reserve_yarn_for_order(self, job_id: str, recipe: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Calls BAPI_RESERVATION_CREATE1
        return {"erp": "SAP", "reservation_id": f"SAP-RES-{job_id}", "status": "SIMULATED"}

    def create_purchase_requisition(self, shortages: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Calls BAPI_PR_CREATE
        return {"erp": "SAP", "pr_number": "100045892", "status": "SIMULATED"}


class CaniasERPProvider(BaseERPProvider):
    """CANIAS ERP TROIA Web Services SOAP/REST Connector."""

    def __init__(self, wsdl_url: str = "http://canias.factory.local/troia/services"):
        self.wsdl_url = wsdl_url

    def fetch_live_inventory(self) -> List[Dict[str, Any]]:
        logger.info(f"Querying CANIAS TROIA: {self.wsdl_url}")
        return []

    def check_stock_availability(self, yarn_code: str, required_kg: float) -> Dict[str, Any]:
        return {"erp": "CANIAS", "yarn_code": yarn_code, "status": "TROIA_OK"}

    def reserve_yarn_for_order(self, job_id: str, recipe: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"erp": "CANIAS", "order_id": job_id, "status": "SIMULATED"}

    def create_purchase_requisition(self, shortages: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"erp": "CANIAS", "pr_doc": "SAT-2026-001", "status": "SIMULATED"}
