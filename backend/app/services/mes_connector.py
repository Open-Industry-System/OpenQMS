"""MES Connector adapter layer.

Provides:
- MESConnector: abstract base class defining the MES integration interface
- MockMESConnector: simulation connector generating realistic test data
- RESTMESConnector: full HTTP implementation with retry, pagination, auth
"""

import asyncio
import random
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.spc import InspectionCharacteristic
from app.schemas.mes import (
    MESIngestEquipmentStatus,
    MESIngestMeasurement,
    MESIngestProductionOrder,
    MESIngestScrapRecord,
)
from app.services.mes_crypto import decrypt_credential


# ---------------------------------------------------------------------------
# Schema mapping for validation
# ---------------------------------------------------------------------------

_SCHEMA_MAP = {
    "production_orders": MESIngestProductionOrder,
    "equipment_status": MESIngestEquipmentStatus,
    "scrap_records": MESIngestScrapRecord,
    "measurements": MESIngestMeasurement,
}


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class MESConnector(ABC):
    """Abstract base class for MES integrations."""

    @abstractmethod
    async def fetch_production_orders(self, since: datetime) -> list[dict]:
        """Fetch production orders updated since `since`."""
        ...

    @abstractmethod
    async def fetch_equipment_status(self) -> list[dict]:
        """Fetch current equipment status."""
        ...

    @abstractmethod
    async def fetch_scrap_records(self, since: datetime) -> list[dict]:
        """Fetch scrap records updated since `since`."""
        ...

    @abstractmethod
    async def fetch_measurements(self, since: datetime) -> list[dict]:
        """Fetch measurement data updated since `since`."""
        ...

    @abstractmethod
    async def push_quality_event(
        self, event_type: str, data: dict, event_id: str | None = None
    ) -> dict:
        """Push a quality event to the MES."""
        ...


# ---------------------------------------------------------------------------
# Mock connector
# ---------------------------------------------------------------------------

class MockMESConnector(MESConnector):
    """Simulation connector that generates realistic MES data."""

    _ORDER_STATUSES = ["planned", "in_progress", "completed", "closed"]
    _EQUIPMENT_DEFS = [
        {"code": "EQ-001", "name": "注塑机"},
        {"code": "EQ-002", "name": "焊接机"},
        {"code": "EQ-003", "name": "组装线"},
    ]
    _EQUIPMENT_STATUSES = ["running", "idle", "maintenance", "down"]
    _DEFECT_TYPES = ["尺寸超差", "外观缺陷", "功能不良", "材料异常"]
    _DEFECT_CATEGORIES = ["来料问题", "过程异常", "设备故障", "操作失误"]

    async def fetch_production_orders(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        count = random.randint(2, 5)
        orders = []
        for i in range(count):
            seq = random.randint(1, 999)
            status = random.choice(self._ORDER_STATUSES)
            orders.append(
                {
                    "order_no": f"WO-2026-{seq:03d}",
                    "product_model": f"DC-DC-100-{random.choice(['A', 'B', 'C'])}",
                    "process_route": random.choice(["冲压-注塑-组装", "SMT-焊接-测试"]),
                    "planned_qty": random.randint(100, 1000),
                    "actual_qty": random.randint(0, 1000) if status != "planned" else 0,
                    "status": status,
                    "started_at": now.isoformat() if status != "planned" else None,
                    "completed_at": now.isoformat() if status in ("completed", "closed") else None,
                    "source_updated_at": now.isoformat(),
                }
            )
        return orders

    async def fetch_equipment_status(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        results = []
        for eq in self._EQUIPMENT_DEFS:
            status = random.choice(self._EQUIPMENT_STATUSES)
            availability = round(random.uniform(70, 100), 2) if status == "running" else round(random.uniform(0, 60), 2)
            performance = round(random.uniform(75, 98), 2) if status == "running" else round(random.uniform(0, 50), 2)
            quality = round(random.uniform(95, 100), 2)
            oee = round(availability * performance * quality / 10000, 2)
            results.append(
                {
                    "external_id": f"{eq['code']}-{int(now.timestamp())}",
                    "equipment_code": eq["code"],
                    "equipment_name": eq["name"],
                    "status": status,
                    "availability": availability,
                    "performance": performance,
                    "quality": quality,
                    "oee": oee,
                    "downtime_reason": random.choice(["换模", "例行保养", "故障待修"]) if status in ("maintenance", "down") else None,
                    "recorded_at": now.isoformat(),
                }
            )
        return results

    async def fetch_scrap_records(self, since: datetime) -> list[dict]:
        now = datetime.now(timezone.utc)
        count = random.randint(0, 2)
        records = []
        for _ in range(count):
            defect_qty = random.randint(1, 20)
            total_qty = random.randint(defect_qty, 200)
            records.append(
                {
                    "external_id": f"SCRAP-{int(now.timestamp())}-{random.randint(1000, 9999)}",
                    "order_no": f"WO-2026-{random.randint(1, 999):03d}",
                    "equipment_code": random.choice(["EQ-001", "EQ-002", "EQ-003"]),
                    "defect_type": random.choice(self._DEFECT_TYPES),
                    "defect_category": random.choice(self._DEFECT_CATEGORIES),
                    "defect_qty": defect_qty,
                    "total_qty": total_qty,
                    "defect_description": "模拟报废记录",
                    "recorded_at": now.isoformat(),
                    "source_updated_at": now.isoformat(),
                }
            )
        return records

    async def fetch_measurements(self, since: datetime) -> list[dict]:
        """Query InspectionCharacteristic from DB and generate simulated measurements."""
        now = datetime.now(timezone.utc)
        async with async_session() as session:
            result = await session.execute(
                select(InspectionCharacteristic).where(
                    InspectionCharacteristic.product_line == "DC-DC-100"
                )
            )
            ics = result.scalars().all()

        measurements = []
        for ic in ics:
            target = float(ic.target_value) if ic.target_value is not None else (
                float(ic.spec_upper) + float(ic.spec_lower)
            ) / 2
            usl = float(ic.spec_upper)
            lsl = float(ic.spec_lower)
            sigma = (usl - lsl) / 6.0
            subgroup = ic.subgroup_size or 5

            values = [
                round(random.gauss(target, sigma), 4)
                for _ in range(subgroup)
            ]

            measurements.append(
                {
                    "external_id": f"MEAS-{ic.ic_code}-{int(now.timestamp())}-{random.randint(1000, 9999)}",
                    "order_no": f"WO-2026-{random.randint(1, 999):03d}",
                    "ic_code": ic.ic_code,
                    "batch_no": f"B-{int(now.timestamp())}-{random.randint(1000, 9999)}",
                    "values": values,
                    "sampled_at": now.isoformat(),
                    "source_updated_at": now.isoformat(),
                }
            )
        return measurements

    async def push_quality_event(
        self, event_type: str, data: dict, event_id: str | None = None
    ) -> dict:
        return {"status": "ok", "mock": True, "event_id": event_id}


# ---------------------------------------------------------------------------
# REST connector
# ---------------------------------------------------------------------------

class RESTMESConnector(MESConnector):
    """HTTP-based MES connector with retry, pagination, auth, and field mapping."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._base_url = config["base_url"].rstrip("/")
        self._timeout = config.get("timeout", 30)
        self._retry = config.get("retry", {"max_retries": 3, "backoff_seconds": [1, 2, 4]})
        self._endpoints = config.get("endpoints", {})
        self._field_mapping = config.get("field_mapping", {})
        self._auth_type = config.get("auth_type", "none")
        self._auth_config = config.get("auth_config", {})
        self._client = httpx.AsyncClient(timeout=self._timeout)

    # -- Auth helpers --

    def _resolve_auth(self) -> dict[str, str]:
        """Build headers from auth_config, decrypting encrypted fields."""
        headers: dict[str, str] = {}
        if self._auth_type == "none":
            return headers

        ac = self._auth_config
        if self._auth_type == "basic":
            # Basic auth is handled via _auth_for_httpx, not headers
            return headers
        elif self._auth_type == "bearer":
            token = ac.get("token")
            if not token and ac.get("token_encrypted"):
                token = decrypt_credential(ac["token_encrypted"])
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif self._auth_type == "api_key":
            key = ac.get("inbound_api_key") or ac.get("outbound_api_key")
            if not key and ac.get("outbound_api_key_encrypted"):
                key = decrypt_credential(ac["outbound_api_key_encrypted"])
            if key:
                headers["X-API-Key"] = key
        return headers

    def _auth_for_httpx(self) -> tuple[str, str] | None:
        """Return (username, password) for basic auth, or None."""
        if self._auth_type != "basic":
            return None
        ac = self._auth_config
        username = ac.get("username")
        if not username and ac.get("username_encrypted"):
            username = decrypt_credential(ac["username_encrypted"])
        password = ac.get("password")
        if not password and ac.get("password_encrypted"):
            password = decrypt_credential(ac["password_encrypted"])
        if username and password:
            return (username, password)
        return None

    # -- Field mapping --

    def _map_field(self, openqms_field: str, data: dict) -> Any:
        """Map OpenQMS field name to MES field name and extract value from data."""
        mes_field = self._field_mapping.get(openqms_field, openqms_field)
        return data.get(mes_field)

    def _reverse_map(self, mes_data: dict) -> dict:
        """Reverse mapping: MES field -> OpenQMS field."""
        reverse = {v: k for k, v in self._field_mapping.items()}
        return {reverse.get(k, k): v for k, v in mes_data.items()}

    # -- Response navigation --

    def _get_response_data(self, resp_json: dict, endpoint_name: str) -> list:
        """Navigate response JSON using response_path like 'data.orders'."""
        ep = self._endpoints.get(endpoint_name, {})
        path = ep.get("response_path")
        if not path:
            if isinstance(resp_json, list):
                return resp_json
            return [resp_json] if not isinstance(resp_json, dict) else []

        data = resp_json
        for key in path.split("."):
            if isinstance(data, dict):
                data = data.get(key, [])
            else:
                return []
        if isinstance(data, list):
            return data
        return [data] if data is not None else []

    # -- HTTP request with retry --

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict:
        """Execute HTTP request with retry logic."""
        url = f"{self._base_url}{path}"
        headers = self._resolve_auth()
        auth = self._auth_for_httpx()

        max_retries = self._retry.get("max_retries", 3)
        backoff = self._retry.get("backoff_seconds", [1, 2, 4])

        for attempt in range(max_retries + 1):
            try:
                resp = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    auth=auth,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (408, 429) or status >= 500:
                    if attempt < max_retries:
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after and str(retry_after).isdigit():
                            await asyncio.sleep(int(retry_after))
                        else:
                            await asyncio.sleep(backoff[min(attempt, len(backoff) - 1)])
                        continue
                raise
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout):
                if attempt < max_retries:
                    await asyncio.sleep(backoff[min(attempt, len(backoff) - 1)])
                    continue
                raise

        # Should never reach here, but satisfy type checker
        raise RuntimeError("Unexpected end of retry loop")

    # -- Pagination --

    async def _fetch_paginated(
        self, endpoint_name: str, since: datetime | None = None
    ) -> list[dict]:
        """Fetch all pages for an endpoint."""
        ep = self._endpoints.get(endpoint_name)
        if ep is None:
            raise ValueError(f"Endpoint '{endpoint_name}' not configured")

        path = ep["path"]
        method = ep.get("method", "GET")
        pagination = ep.get("pagination") or {"type": "none"}
        pag_type = pagination.get("type", "none")
        page_size = pagination.get("size", 100)
        cursor_field = ep.get("cursor_field")

        params: dict[str, Any] = {}
        if since is not None and cursor_field:
            params[cursor_field] = since.isoformat()

        all_items: list[dict] = []
        page_count = 0
        max_pages = 100

        while page_count < max_pages:
            page_count += 1

            if pag_type == "offset":
                params[pagination["page_param"]] = page_count
                params[pagination["size_param"]] = page_size
            elif pag_type == "cursor" and page_count > 1 and all_items:
                last_item = all_items[-1]
                cursor_value = last_item.get(pagination["cursor_response_field"])
                if cursor_value is None:
                    break
                params[pagination["cursor_param"]] = cursor_value

            resp_json = await self._request(method, path, params=params)
            items = self._get_response_data(resp_json, endpoint_name)

            if not items:
                break

            all_items.extend(items)

            if pag_type == "none":
                break

        if page_count >= max_pages:
            raise ValueError(f"Pagination exceeded max {max_pages} pages for '{endpoint_name}'")

        return all_items

    # -- Validation --

    def _validate_items(self, endpoint_name: str, raw_items: list[dict]) -> list[dict]:
        """Validate raw items using Pydantic schemas."""
        schema_cls = _SCHEMA_MAP.get(endpoint_name)
        if schema_cls is None:
            raise ValueError(f"No validation schema for endpoint '{endpoint_name}'")

        validated = []
        for item in raw_items:
            mapped = self._reverse_map(item)

            # All incremental types require source_updated_at
            if endpoint_name in ("production_orders", "scrap_records", "measurements"):
                if not mapped.get("source_updated_at"):
                    raise ValueError(
                        f"Missing source_updated_at in item for '{endpoint_name}'"
                    )

            validated_item = schema_cls(**mapped)
            validated.append(validated_item.model_dump(mode="json"))

        return validated

    # -- Public fetch methods --

    async def fetch_production_orders(self, since: datetime) -> list[dict]:
        raw = await self._fetch_paginated("production_orders", since)
        return self._validate_items("production_orders", raw)

    async def fetch_equipment_status(self) -> list[dict]:
        raw = await self._fetch_paginated("equipment_status")
        return self._validate_items("equipment_status", raw)

    async def fetch_scrap_records(self, since: datetime) -> list[dict]:
        raw = await self._fetch_paginated("scrap_records", since)
        return self._validate_items("scrap_records", raw)

    async def fetch_measurements(self, since: datetime) -> list[dict]:
        raw = await self._fetch_paginated("measurements", since)
        return self._validate_items("measurements", raw)

    async def push_quality_event(
        self, event_type: str, data: dict, event_id: str | None = None
    ) -> dict:
        ep = self._endpoints.get("push_event")
        if ep is None:
            raise ValueError("push_event endpoint not configured")

        payload = dict(data)
        if event_id:
            payload["event_id"] = event_id
        payload["event_type"] = event_type

        return await self._request(ep["method"], ep["path"], json_body=payload)

    async def close(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Connector factory
# ---------------------------------------------------------------------------

def get_mes_connector(
    connection, db: AsyncSession | None = None
) -> MESConnector:
    """Return an MESConnector instance for the given connection."""
    if connection.connector_type == "mock":
        return MockMESConnector(db)
    if connection.connector_type == "rest":
        return RESTMESConnector(connection.config)
    raise ValueError(f"Unsupported connector_type: {connection.connector_type}")


def get_mes_connector_by_config(
    connector_type: str, config: dict, db: AsyncSession | None = None
) -> MESConnector:
    """Return an MESConnector instance from raw type + config dict."""
    if connector_type == "mock":
        return MockMESConnector(db)
    if connector_type == "rest":
        return RESTMESConnector(config)
    raise ValueError(f"Unsupported connector_type: {connector_type}")


async def test_mes_connection(
    connection, db: AsyncSession | None = None
) -> dict:
    """Lightweight connectivity test: fetch one production order."""
    connector = get_mes_connector(connection, db)
    try:
        if isinstance(connector, RESTMESConnector):
            # Temporarily reduce page size to 1 for a lightweight test
            connector._endpoints = dict(connector._endpoints)
            po_ep = connector._endpoints.get("production_orders", {})
            if po_ep:
                po_ep = dict(po_ep)
                pag = dict(po_ep.get("pagination") or {"type": "none"})
                pag["size"] = 1
                po_ep["pagination"] = pag
                connector._endpoints["production_orders"] = po_ep
        await connector.fetch_production_orders(datetime.now(timezone.utc))
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if isinstance(connector, RESTMESConnector):
            await connector.close()
