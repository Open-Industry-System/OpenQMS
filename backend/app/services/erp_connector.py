"""ERP Connector adapter layer.

Provides:
- ERPConnector: abstract base class defining the ERP integration interface
- MockERPConnector: simulation connector generating realistic DC-DC-100 test data
- RESTERPConnector: full HTTP implementation with retry, pagination, auth
"""

import asyncio
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from app.services.erp_crypto import decrypt_credential


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class ERPConnector(ABC):
    """Abstract base class for ERP integrations."""

    @abstractmethod
    async def fetch_suppliers(self, since: datetime) -> list[dict]:
        """Fetch suppliers updated since `since`."""
        ...

    @abstractmethod
    async def fetch_customers(self, since: datetime) -> list[dict]:
        """Fetch customers updated since `since`."""
        ...

    @abstractmethod
    async def fetch_materials(self, since: datetime) -> list[dict]:
        """Fetch materials updated since `since`."""
        ...

    @abstractmethod
    async def fetch_locations(self, since: datetime) -> list[dict]:
        """Fetch warehouse locations updated since `since`."""
        ...

    @abstractmethod
    async def fetch_purchase_orders(self, since: datetime) -> list[dict]:
        """Fetch purchase orders updated since `since`."""
        ...

    @abstractmethod
    async def fetch_sales_orders(self, since: datetime) -> list[dict]:
        """Fetch sales orders updated since `since`."""
        ...

    @abstractmethod
    async def fetch_inventory_balances(self, since: datetime) -> list[dict]:
        """Fetch inventory balances updated since `since`."""
        ...

    @abstractmethod
    async def fetch_shipments(self, since: datetime) -> list[dict]:
        """Fetch shipment records updated since `since`."""
        ...

    @abstractmethod
    async def fetch_cost_records(self, since: datetime) -> list[dict]:
        """Fetch cost records updated since `since`."""
        ...


# ---------------------------------------------------------------------------
# Mock connector
# ---------------------------------------------------------------------------


class MockERPConnector(ERPConnector):
    """Generate realistic DC-DC-100 ERP data for testing."""

    def __init__(self, config: dict):
        self.config = config
        self._rng = random.Random(42)

    async def fetch_suppliers(self, since: datetime) -> list[dict]:
        return [
            {
                "external_id": f"ERP-SUP-{i:03d}",
                "supplier_code": f"SUP-{i:03d}",
                "name": [
                    "深圳电子",
                    "东莞五金",
                    "苏州塑胶",
                    "上海芯片",
                    "北京线缆",
                ][i],
                "status": "active",
                "payment_terms": "T/T 30 days",
                "currency": "CNY",
                "tax_id": f"91310000{i:08d}X",
                "bank_info": {
                    "bank": "中国银行",
                    "account": f"6222{i:012d}",
                },
            }
            for i in range(5)
        ]

    async def fetch_customers(self, since: datetime) -> list[dict]:
        return [
            {
                "external_id": f"ERP-CUST-{i:03d}",
                "customer_code": f"CUST-{i:03d}",
                "name": [
                    "比亚迪",
                    "宁德时代",
                    "蔚来汽车",
                    "理想汽车",
                ][i],
                "status": "active",
                "region": "华东",
                "customer_level": "A",
                "tax_id": f"91440000{i:08d}Y",
            }
            for i in range(4)
        ]

    async def fetch_materials(self, since: datetime) -> list[dict]:
        return [
            {
                "external_id": f"ERP-MAT-{i:03d}",
                "material_code": f"MAT-{i:03d}",
                "name": name,
                "unit": "PC",
                "material_type": mtype,
                "is_purchased": isp,
                "is_manufactured": not isp,
                "status": "active",
            }
            for i, (name, mtype, isp) in enumerate(
                [
                    ("PCB板 DC-DC-100", "raw_material", True),
                    ("MOSFET N沟道", "raw_material", True),
                    ("电感 47uH", "raw_material", True),
                    ("电容 100uF", "raw_material", True),
                    ("DC-DC模块半成品", "semi_product", False),
                    ("DC-DC-100 成品", "finished_good", False),
                ]
            )
        ]

    async def fetch_locations(self, since: datetime) -> list[dict]:
        return [
            {
                "external_id": f"ERP-LOC-{i:03d}",
                "location_code": code,
                "warehouse_code": "WH-01",
                "zone_code": zone,
                "location_type": ltype,
                "is_enabled": True,
            }
            for i, (code, zone, ltype) in enumerate(
                [
                    ("RCV-01", "接收区", "receiving"),
                    ("IQC-01", "检验区", "inspection"),
                    ("QAR-01", "隔离区", "quarantine"),
                    ("FRZ-01", "冻结区", "frozen"),
                    ("SCR-01", "报废区", "scrap"),
                    ("STK-A1", "A区", "normal"),
                    ("STK-B1", "B区", "normal"),
                    ("STK-C1", "C区", "normal"),
                ]
            )
        ]

    async def fetch_purchase_orders(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {
                "external_id": f"ERP-PO-{i:03d}",
                "po_number": f"PO-2026-{i + 1:03d}",
                "line_number": "1",
                "supplier_code": f"SUP-{self._rng.randint(0, 4):03d}",
                "material_code": f"MAT-{self._rng.randint(0, 5):03d}",
                "quantity": self._rng.randint(100, 1000),
                "unit_price": round(self._rng.uniform(1, 100), 2),
                "currency": "CNY",
                "delivery_date": (
                    now + timedelta(days=self._rng.randint(7, 30))
                ).strftime("%Y-%m-%d"),
                "received_quantity": 0,
                "status": "approved",
                "lot_no": f"LOT-{i + 1:03d}",
            }
            for i in range(15)
        ]

    async def fetch_sales_orders(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {
                "external_id": f"ERP-SO-{i:03d}",
                "so_number": f"SO-2026-{i + 1:03d}",
                "line_number": "1",
                "customer_code": f"CUST-{self._rng.randint(0, 3):03d}",
                "material_code": "MAT-005",
                "quantity": self._rng.randint(50, 500),
                "unit_price": round(self._rng.uniform(100, 500), 2),
                "delivery_date": (
                    now + timedelta(days=self._rng.randint(7, 30))
                ).strftime("%Y-%m-%d"),
                "status": "confirmed",
            }
            for i in range(8)
        ]

    async def fetch_inventory_balances(self, since: datetime) -> list[dict]:
        return [
            {
                "external_id": f"ERP-INV-{i:03d}",
                "material_code": f"MAT-{self._rng.randint(0, 5):03d}",
                "location_code": f"STK-{chr(65 + self._rng.randint(0, 2))}1",
                "lot_no": (
                    f"LOT-{i + 1:03d}" if self._rng.random() > 0.3 else ""
                ),
                "supplier_lot_no": (
                    f"SUP-LOT-{i + 1:03d}"
                    if self._rng.random() > 0.5
                    else None
                ),
                "quantity": self._rng.randint(50, 200),
                "unit": "PC",
                "inventory_status": self._rng.choice(
                    ["available", "frozen", "quarantine", "inspection"]
                ),
                "snapshot_at": datetime.now(timezone.utc).isoformat(),
            }
            for i in range(20)
        ]

    async def fetch_shipments(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {
                "external_id": f"ERP-SHIP-{i:03d}",
                "shipment_number": f"DN-2026-{i + 1:03d}",
                "line_number": "1",
                "so_number": f"SO-2026-{self._rng.randint(1, 8):03d}",
                "customer_code": f"CUST-{self._rng.randint(0, 3):03d}",
                "material_code": "MAT-005",
                "lot_no": f"FG-LOT-{i + 1:03d}",
                "quantity": self._rng.randint(10, 100),
                "shipment_date": (
                    now - timedelta(days=self._rng.randint(1, 14))
                ).strftime("%Y-%m-%d"),
            }
            for i in range(5)
        ]

    async def fetch_cost_records(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        records = []
        # Detail records
        for i in range(25):
            records.append(
                {
                    "external_id": f"ERP-COST-D-{i:03d}",
                    "record_type": "detail",
                    "cost_category": self._rng.choice(
                        ["internal_failure", "external_failure"]
                    ),
                    "cost_type": self._rng.choice(
                        ["scrap", "rework", "claim", "complaint"]
                    ),
                    "amount": round(self._rng.uniform(100, 10000), 2),
                    "currency": "CNY",
                    "source_document_no": f"DOC-{i + 1:03d}",
                    "material_code": f"MAT-{self._rng.randint(0, 5):03d}",
                    "supplier_code": (
                        f"SUP-{self._rng.randint(0, 4):03d}"
                        if self._rng.random() > 0.5
                        else None
                    ),
                    "cost_date": (
                        now - timedelta(days=self._rng.randint(1, 30))
                    ).strftime("%Y-%m-%d"),
                    "description": "Auto-generated cost record",
                }
            )
        # Period summary records
        for cat in ["prevention", "appraisal"]:
            records.append(
                {
                    "external_id": f"summary_{cat}_inspection_2026-05",
                    "record_type": "period_summary",
                    "cost_category": cat,
                    "cost_type": (
                        "inspection" if cat == "appraisal" else "prevention"
                    ),
                    "amount": round(self._rng.uniform(5000, 20000), 2),
                    "currency": "CNY",
                    "period_month": "2026-05",
                    "cost_center": "QC-01",
                    "cost_date": "2026-05-31",
                    "description": f"Monthly {cat} cost summary",
                }
            )
        return records


# ---------------------------------------------------------------------------
# REST connector
# ---------------------------------------------------------------------------


class RESTERPConnector(ERPConnector):
    """Full HTTP ERP connector with retry, pagination, auth."""

    def __init__(self, config: dict):
        self.config = config
        self.base_url = config["base_url"].rstrip("/")
        self.timeout = config.get("timeout", 30)
        self.retry_config = config.get(
            "retry", {"max_retries": 3, "backoff_seconds": [1, 2, 4]}
        )
        self.endpoints = config.get("endpoints", {})
        self.field_mapping = config.get("field_mapping", {})
        self.auth_type = config.get("auth_type", "none")
        self.auth_config = config.get("auth_config", {})
        self._client: httpx.AsyncClient | None = None

    def _get_auth_headers(self) -> dict:
        headers: dict[str, str] = {}
        if self.auth_type == "bearer":
            token = decrypt_credential(
                self.auth_config.get("token_encrypted", "")
            )
            headers["Authorization"] = f"Bearer {token}"
        elif self.auth_type == "api_key":
            key = decrypt_credential(
                self.auth_config.get("outbound_api_key_encrypted", "")
            )
            headers["X-API-Key"] = key
        elif self.auth_type == "basic":
            import base64

            user = self.auth_config.get("username", "")
            pwd = decrypt_credential(
                self.auth_config.get("password_encrypted", "")
            )
            creds = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"
        return headers

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        headers = self._get_auth_headers()
        headers.update(kwargs.pop("headers", {}))

        max_retries = self.retry_config.get("max_retries", 3)
        backoff = self.retry_config.get("backoff_seconds", [1, 2, 4])

        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)

        for attempt in range(max_retries + 1):
            try:
                response = await self._client.request(
                    method, url, headers=headers, **kwargs
                )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.ConnectError):
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(
                    backoff[min(attempt, len(backoff) - 1)]
                )

        # Unreachable, but satisfy type checker
        return {}

    def _map_fields(self, item: dict) -> dict:
        mapped = {}
        for target_key, source_key in self.field_mapping.items():
            mapped[target_key] = item.get(source_key)
        for key, value in item.items():
            if key not in mapped:
                mapped[key] = value
        return mapped

    async def _fetch_paginated(
        self, endpoint_name: str, since: datetime
    ) -> list[dict]:
        ep = self.endpoints.get(endpoint_name)
        if not ep:
            return []
        path = ep["path"]
        method = ep.get("method", "GET")
        params: dict[str, str] = {}
        if ep.get("cursor_field"):
            params[ep["cursor_field"]] = since.isoformat()

        data = await self._request(method, path, params=params)
        response_path = ep.get("response_path", "")
        if response_path:
            for part in response_path.split("."):
                data = data.get(part, {})
        items = data if isinstance(data, list) else data.get("items", [])
        return [self._map_fields(item) for item in items]

    async def fetch_suppliers(self, since: datetime) -> list[dict]:
        return await self._fetch_paginated("suppliers", since)

    async def fetch_customers(self, since: datetime) -> list[dict]:
        return await self._fetch_paginated("customers", since)

    async def fetch_materials(self, since: datetime) -> list[dict]:
        return await self._fetch_paginated("materials", since)

    async def fetch_locations(self, since: datetime) -> list[dict]:
        return await self._fetch_paginated("locations", since)

    async def fetch_purchase_orders(self, since: datetime) -> list[dict]:
        return await self._fetch_paginated("purchase_orders", since)

    async def fetch_sales_orders(self, since: datetime) -> list[dict]:
        return await self._fetch_paginated("sales_orders", since)

    async def fetch_inventory_balances(self, since: datetime) -> list[dict]:
        return await self._fetch_paginated("inventory_balances", since)

    async def fetch_shipments(self, since: datetime) -> list[dict]:
        return await self._fetch_paginated("shipments", since)

    async def fetch_cost_records(self, since: datetime) -> list[dict]:
        return await self._fetch_paginated("cost_records", since)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ---------------------------------------------------------------------------
# Connector factory
# ---------------------------------------------------------------------------


def get_erp_connector(connection) -> ERPConnector:
    """Return an ERPConnector instance for the given connection."""
    if connection.connector_type == "mock":
        return MockERPConnector(connection.config)
    if connection.connector_type == "rest":
        return RESTERPConnector(connection.config)
    raise ValueError(
        f"Unsupported connector_type: {connection.connector_type}"
    )


def get_erp_connector_by_config(
    connector_type: str, config: dict
) -> ERPConnector:
    """Return an ERPConnector instance from raw type + config dict."""
    if connector_type == "mock":
        return MockERPConnector(config)
    if connector_type == "rest":
        return RESTERPConnector(config)
    raise ValueError(f"Unsupported connector_type: {connector_type}")


async def test_erp_connection(
    connector_type: str, config: dict
) -> dict:
    """Lightweight connectivity test: fetch one supplier."""
    connector = get_erp_connector_by_config(connector_type, config)
    try:
        suppliers = await connector.fetch_suppliers(
            datetime(2000, 1, 1, tzinfo=timezone.utc)
        )
        return {
            "ok": True,
            "error": None,
            "message": f"Connected. Fetched {len(suppliers)} suppliers.",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if isinstance(connector, RESTERPConnector):
            await connector.close()
