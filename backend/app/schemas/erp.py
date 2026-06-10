"""ERP Pydantic schemas."""
import uuid
from datetime import datetime, date
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Connection schemas
# ---------------------------------------------------------------------------

class ERPConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    connector_type: str = Field(..., pattern=r"^(mock|rest)$")
    config: dict = Field(default_factory=dict)
    product_line_code: Optional[str] = Field(default=None, min_length=1)


class ERPConnectionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    connector_type: Optional[str] = Field(default=None, pattern=r"^(mock|rest)$")
    config: Optional[dict] = None
    is_active: Optional[bool] = None
    product_line_code: Optional[str] = Field(default=None, min_length=1)


class ERPConnectionOut(BaseModel):
    connection_id: uuid.UUID
    name: str
    connector_type: str
    config: dict
    is_active: bool
    product_line_code: Optional[str]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("config", mode="before")
    @classmethod
    def _sanitize_config_output(cls, value):
        """Always return sanitized config (no api_key_hash, *_encrypted, etc.)."""
        from app.services.erp_crypto import sanitize_config

        if value is None:
            return {}
        return sanitize_config(value)


class ERPConnectionListResponse(BaseModel):
    items: list[ERPConnectionOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# REST connector nested config schemas (same structure as MES/PLM)
# ---------------------------------------------------------------------------

class RESTPaginationConfig(BaseModel):
    type: Literal["none", "offset", "cursor"] = "none"
    page_param: Optional[str] = None
    size_param: Optional[str] = None
    cursor_param: Optional[str] = None
    cursor_response_field: Optional[str] = None
    size: int = Field(default=100, ge=1)


class RESTRetryConfig(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    backoff_seconds: list[float] = Field(default=[1, 2, 4], min_length=1)

    @field_validator("backoff_seconds")
    @classmethod
    def validate_backoff(cls, v: list[float]) -> list[float]:
        if any(b < 0 for b in v):
            raise ValueError("backoff_seconds must all be >= 0")
        return v


class RESTEndpointConfig(BaseModel):
    path: str = Field(..., min_length=1)
    cursor_field: Optional[str] = None
    method: str = "GET"
    pagination: Optional[RESTPaginationConfig] = None
    response_path: Optional[str] = None


class RESTConfig(BaseModel):
    base_url: str = Field(..., pattern=r"^https?://")
    timeout: int = Field(default=30, ge=1)
    retry: Optional[RESTRetryConfig] = Field(default=None)
    auth_type: Literal["none", "basic", "bearer", "api_key"] = "none"
    auth_config: Optional[dict] = Field(default=None)
    endpoints: dict[str, RESTEndpointConfig] = Field(default_factory=dict)
    field_mapping: dict[str, str] = Field(default_factory=dict)
    retention: Optional[dict] = Field(default=None)

    @field_validator("endpoints")
    @classmethod
    def validate_endpoints(cls, v: dict[str, RESTEndpointConfig]) -> dict[str, RESTEndpointConfig]:
        if not v:
            return v
        required = {"suppliers", "customers", "materials", "locations",
                    "purchase_orders", "sales_orders", "inventory_balances",
                    "shipments", "cost_records"}
        missing = required - set(v.keys())
        if missing:
            raise ValueError(f"Missing required endpoints: {missing}")
        return v


# ---------------------------------------------------------------------------
# Ingest schemas (for push endpoint)
# ---------------------------------------------------------------------------

class ERPIngestRequest(BaseModel):
    data_type: str = Field(..., pattern=r"^(suppliers|customers|materials|locations|purchase_orders|sales_orders|inventory_balances|shipments|cost_records)$")
    connection_id: str
    items: list[dict]


# ---------------------------------------------------------------------------
# Data query schemas
# ---------------------------------------------------------------------------

class PaginatedListResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int


class SupplierOut(BaseModel):
    erp_supplier_id: uuid.UUID
    supplier_code: str
    name: str
    status: str
    link_status: str
    openqms_supplier_id: Optional[uuid.UUID]
    payment_terms: Optional[str]
    currency: Optional[str]
    tax_id: Optional[str]
    bank_info: Optional[dict | str]
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]

    model_config = {"from_attributes": True}


class CustomerOut(BaseModel):
    erp_customer_id: uuid.UUID
    customer_code: str
    name: str
    status: str
    link_status: str
    openqms_customer_id: Optional[uuid.UUID]
    region: Optional[str]
    customer_level: Optional[str]
    tax_id: Optional[str]
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]

    model_config = {"from_attributes": True}


class MaterialOut(BaseModel):
    material_id: uuid.UUID
    material_code: str
    name: str
    specification: Optional[str]
    unit: Optional[str]
    material_type: Optional[str]
    is_purchased: bool
    is_manufactured: bool
    status: str
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]

    model_config = {"from_attributes": True}


class LocationOut(BaseModel):
    location_id: uuid.UUID
    location_code: str
    warehouse_code: Optional[str]
    zone_code: Optional[str]
    location_type: str
    is_enabled: bool
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]

    model_config = {"from_attributes": True}


class PurchaseOrderOut(BaseModel):
    po_id: uuid.UUID
    po_number: str
    line_number: str
    supplier_code: Optional[str]
    material_code: Optional[str]
    quantity: Optional[float]
    unit_price: Optional[float]
    currency: Optional[str]
    delivery_date: Optional[date]
    received_quantity: Optional[float]
    status: str
    lot_no: Optional[str]
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]

    model_config = {"from_attributes": True}


class SalesOrderOut(BaseModel):
    so_id: uuid.UUID
    so_number: str
    line_number: str
    customer_code: Optional[str]
    material_code: Optional[str]
    quantity: Optional[float]
    unit_price: Optional[float]
    delivery_date: Optional[date]
    status: str
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]

    model_config = {"from_attributes": True}


class InventoryBalanceOut(BaseModel):
    balance_id: uuid.UUID
    material_code: str
    location_code: str
    lot_no: str
    supplier_lot_no: Optional[str]
    quantity: Optional[float]
    unit: Optional[str]
    inventory_status: str
    manufacture_date: Optional[date]
    expiry_date: Optional[date]
    snapshot_at: Optional[datetime]
    product_line_code: Optional[str]

    model_config = {"from_attributes": True}


class ShipmentOut(BaseModel):
    erp_shipment_id: uuid.UUID
    shipment_number: str
    line_number: str
    so_number: Optional[str]
    customer_code: Optional[str]
    material_code: Optional[str]
    lot_no: Optional[str]
    quantity: Optional[int]
    shipment_date: Optional[date]
    openqms_shipment_id: Optional[uuid.UUID]
    link_status: str
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]

    model_config = {"from_attributes": True}


class CostRecordOut(BaseModel):
    cost_id: uuid.UUID
    record_type: str
    cost_category: str
    cost_type: str
    amount: float
    currency: Optional[str]
    period_month: Optional[str]
    source_document_no: Optional[str]
    material_code: Optional[str]
    supplier_code: Optional[str]
    cost_center: Optional[str]
    cost_date: Optional[date]
    description: Optional[str]
    source_updated_at: Optional[datetime]
    product_line_code: Optional[str]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Link request schemas
# ---------------------------------------------------------------------------

class LinkSupplierRequest(BaseModel):
    supplier_id: uuid.UUID


class LinkCustomerRequest(BaseModel):
    customer_id: uuid.UUID


# ---------------------------------------------------------------------------
# Traceability schemas
# ---------------------------------------------------------------------------

class TraceabilityNode(BaseModel):
    id: str
    type: str
    label: str


class TraceabilityEdge(BaseModel):
    from_node: str = Field(..., alias="from")
    to: str
    type: str

    model_config = {"populate_by_name": True}


class TraceabilityGap(BaseModel):
    type: str
    message: str
    node_id: Optional[str] = None


class TraceabilityResponse(BaseModel):
    nodes: list[TraceabilityNode]
    edges: list[TraceabilityEdge]
    gaps: list[TraceabilityGap]


# ---------------------------------------------------------------------------
# Dashboard schemas
# ---------------------------------------------------------------------------

class DashboardKPI(BaseModel):
    label: str
    value: str | int | float
    status: Optional[str] = None  # "success" | "warning" | "error"


class ERPDashboardResponse(BaseModel):
    sync_health: list[dict]
    coq_summary: dict
    pending_actions: list[dict]
    inventory_alerts: list[dict]
    shipment_risks: list[dict]
    kpis: list[DashboardKPI]
