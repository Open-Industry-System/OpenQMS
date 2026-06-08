"""PLM Connector adapter layer.

Provides:
- PLMConnector: abstract base class defining the PLM integration interface
- MockPLMConnector: simulation connector generating deterministic DC-DC-100 demo data
- RESTPLMConnector: skeleton HTTP connector (TODO: full implementation)
- test_plm_connection: lightweight connectivity test
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

try:
    from app.models.plm import PLMConnection as PLMConnectionType
except ImportError:
    PLMConnectionType = Any  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ConnectorConfigError(Exception):
    """Raised when a connector receives invalid or unsupported configuration."""


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class PLMConnector(ABC):
    """Abstract base class for PLM integrations.

    Each method returns raw dicts suitable for PLMIngestionService to process.
    Connectors do NOT write to the database.
    """

    @abstractmethod
    async def fetch_parts(self, since: datetime) -> list[dict]:
        """Fetch parts updated since `since`."""
        ...

    @abstractmethod
    async def fetch_boms(self, since: datetime) -> list[dict]:
        """Fetch BOM records updated since `since`."""
        ...

    @abstractmethod
    async def fetch_change_orders(self, since: datetime) -> list[dict]:
        """Fetch engineering change orders updated since `since`."""
        ...

    @abstractmethod
    async def push_change_status(
        self, change_number: str, status: str, data: dict
    ) -> dict:
        """Push a change order status update to the PLM system."""
        ...

    async def close(self) -> None:
        """Release any resources (HTTP clients, etc.). Default no-op."""


# ---------------------------------------------------------------------------
# Mock connector -- deterministic DC-DC-100 demo data
# ---------------------------------------------------------------------------

# 5 demo parts
_DEMO_PARTS = [
    {
        "external_id": "PLM-P001",
        "part_number": "DC-DC-100-ASM",
        "name": "DC-DC转换器总成",
        "revision": "B",
        "material": "铝合金",
        "specification": "输入24V/输出12V, 100W",
        "status": "active",
        "is_safety_related": True,
        "is_key_characteristic": True,
    },
    {
        "external_id": "PLM-P002",
        "part_number": "PCBA-MAIN-01",
        "name": "主控PCBA板",
        "revision": "C",
        "material": "FR-4",
        "specification": "主功率板, 4层PCB",
        "status": "active",
        "is_safety_related": False,
        "is_key_characteristic": True,
    },
    {
        "external_id": "PLM-P003",
        "part_number": "HOUSING-TOP-01",
        "name": "上壳体",
        "revision": "A",
        "material": "ADC12",
        "specification": "压铸件, 表面阳极氧化",
        "status": "active",
        "is_safety_related": False,
        "is_key_characteristic": False,
    },
    {
        "external_id": "PLM-P004",
        "part_number": "HEATSINK-01",
        "name": "散热器",
        "revision": "A",
        "material": "AL6063",
        "specification": "挤压型材, 黑色阳极氧化",
        "status": "active",
        "is_safety_related": False,
        "is_key_characteristic": False,
    },
    {
        "external_id": "PLM-P005",
        "part_number": "CAP-CER-100UF",
        "name": "100uF陶瓷电容",
        "revision": "A",
        "material": "X7R陶瓷",
        "specification": "100uF/50V, 1210封装",
        "status": "active",
        "is_safety_related": False,
        "is_key_characteristic": False,
    },
]

# 3-level BOM: assembly -> sub-assembly -> component
_DEMO_BOMS = [
    # Level 1: top assembly
    {
        "external_id": "BOM-001",
        "parent_part_number": "DC-DC-100-ASM",
        "parent_revision": "B",
        "child_part_number": "PCBA-MAIN-01",
        "child_revision": "C",
        "quantity": Decimal("1"),
        "bom_revision": "B",
        "level": 1,
    },
    {
        "external_id": "BOM-002",
        "parent_part_number": "DC-DC-100-ASM",
        "parent_revision": "B",
        "child_part_number": "HOUSING-TOP-01",
        "child_revision": "A",
        "quantity": Decimal("1"),
        "bom_revision": "B",
        "level": 1,
    },
    {
        "external_id": "BOM-003",
        "parent_part_number": "DC-DC-100-ASM",
        "parent_revision": "B",
        "child_part_number": "HEATSINK-01",
        "child_revision": "A",
        "quantity": Decimal("1"),
        "bom_revision": "B",
        "level": 1,
    },
    # Level 2: sub-assembly -> component
    {
        "external_id": "BOM-004",
        "parent_part_number": "PCBA-MAIN-01",
        "parent_revision": "C",
        "child_part_number": "CAP-CER-100UF",
        "child_revision": "A",
        "quantity": Decimal("4"),
        "bom_revision": "C",
        "level": 2,
    },
    # Level 3: capacitor bank sub-component (non-circular, no back-reference to parent)
    {
        "external_id": "BOM-005",
        "parent_part_number": "CAP-CER-100UF",
        "parent_revision": "A",
        "child_part_number": "CAP-CER-082UF",
        "child_revision": "A",
        "quantity": Decimal("2"),
        "bom_revision": "A",
        "level": 3,
    },
]

# 2 demo ECNs
_DEMO_CHANGE_ORDERS = [
    {
        "external_id": "PLM-ECN-001",
        "change_number": "ECN-2026-001",
        "title": "散热器材料升级",
        "description": "将散热器材料从AL6063升级为AL6061以提高散热效率",
        "change_type": "design_change",
        "status": "approved",
        "priority": "high",
        "affected_part_numbers": ["HEATSINK-01", "DC-DC-100-ASM"],
        "proposed_changes": {
            "old_material": "AL6063",
            "new_material": "AL6061",
            "reason": "散热效率提升15%",
        },
        "requested_by": "eng_zhang",
        "approved_by": "mgr_li",
    },
    {
        "external_id": "PLM-ECN-002",
        "change_number": "ECN-2026-002",
        "title": "陶瓷电容容值调整",
        "description": "将主控板上100uF电容替换为120uF以降低纹波",
        "change_type": "component_change",
        "status": "draft",
        "priority": "normal",
        "affected_part_numbers": ["CAP-CER-100UF", "PCBA-MAIN-01"],
        "proposed_changes": {
            "old_value": "100uF",
            "new_value": "120uF",
            "reason": "输出纹波降低20%",
        },
        "requested_by": "eng_wang",
        "approved_by": None,
    },
]


class MockPLMConnector(PLMConnector):
    """Simulation connector that generates deterministic DC-DC-100 demo data."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self._db = db

    async def fetch_parts(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {
                **part,
                "source_updated_at": now.isoformat(),
            }
            for part in _DEMO_PARTS
        ]

    async def fetch_boms(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {
                **bom,
                "quantity": float(bom["quantity"]),
                "source_updated_at": now.isoformat(),
            }
            for bom in _DEMO_BOMS
        ]

    async def fetch_change_orders(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        return [
            {
                **co,
                "planned_implementation_date": now.isoformat(),
                "actual_implementation_date": None,
                "source_updated_at": now.isoformat(),
            }
            for co in _DEMO_CHANGE_ORDERS
        ]

    async def push_change_status(
        self, change_number: str, status: str, data: dict
    ) -> dict:
        return {"status": "ok", "mock": True, "change_number": change_number}


# ---------------------------------------------------------------------------
# REST connector skeleton
# ---------------------------------------------------------------------------

class RESTPLMConnector(PLMConnector):
    """HTTP-based PLM connector with retry, pagination, auth.

    TODO: Full implementation pending.
    TODO: Implement _request() with retry/backoff.
    TODO: Implement _fetch_paginated() with cursor/offset pagination.
    TODO: Implement _resolve_auth() for bearer/basic/api_key.
    TODO: Map PLM REST API responses to dict structures.
    TODO: Implement field mapping from config.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._base_url = config.get("base_url", "").rstrip("/")
        self._timeout = float(config.get("timeout", 30))
        self._retry = config.get("retry", {"max_retries": 3, "backoff_seconds": [1, 2, 4]})
        self._endpoints = config.get("endpoints", {})
        self._auth_type = config.get("auth_type", "none")
        self._auth_config = config.get("auth_config", {})
        self._client: httpx.AsyncClient | None = httpx.AsyncClient(timeout=self._timeout)

    async def fetch_parts(self, since: datetime) -> list[dict]:
        # TODO: Implement REST call to PLM parts endpoint
        raise NotImplementedError("REST PLM connector not yet implemented")

    async def fetch_boms(self, since: datetime) -> list[dict]:
        # TODO: Implement REST call to PLM BOMs endpoint
        raise NotImplementedError("REST PLM connector not yet implemented")

    async def fetch_change_orders(self, since: datetime) -> list[dict]:
        # TODO: Implement REST call to PLM change orders endpoint
        raise NotImplementedError("REST PLM connector not yet implemented")

    async def push_change_status(
        self, change_number: str, status: str, data: dict
    ) -> dict:
        # TODO: Implement REST call to push change status
        raise NotImplementedError("REST PLM connector not yet implemented")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ---------------------------------------------------------------------------
# Connector factory
# ---------------------------------------------------------------------------

def get_plm_connector(
    connection: PLMConnectionType, db: AsyncSession | None = None
) -> PLMConnector:
    """Return a PLMConnector instance for the given PLMConnection."""
    if connection.connector_type == "mock":
        return MockPLMConnector(db)
    if connection.connector_type in ("rest", "siemens_tc", "dassault_enovia", "ptc_windchill"):
        return RESTPLMConnector(connection.config)
    raise ConnectorConfigError(f"Unsupported PLM connector_type: {connection.connector_type}")


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

async def test_plm_connection(
    conn: PLMConnectionType, db: AsyncSession | None = None
) -> dict:
    """Lightweight connectivity test: fetch parts since epoch start.

    Returns {"status": "ok", "parts_count": n} on success,
    or {"status": "error", "error": "...", "error_class": "..."} on failure.
    """
    connector = get_plm_connector(conn, db)
    try:
        epoch_start = datetime(2000, 1, 1, tzinfo=timezone.utc)
        parts = await connector.fetch_parts(epoch_start)
        return {"status": "ok", "parts_count": len(parts)}
    except Exception as e:
        logger.error(
            "PLM connection test failed: %s: %s", type(e).__name__, e,
        )
        return {
            "status": "error",
            "error": str(e),
            "error_class": type(e).__name__,
        }
    finally:
        await connector.close()
