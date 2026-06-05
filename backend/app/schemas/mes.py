import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Connection schemas
# ---------------------------------------------------------------------------

class MESConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    connector_type: str = Field(..., pattern=r"^(mock|rest)$")
    config: dict = Field(default_factory=dict)
    product_line_code: str = Field(..., min_length=1)


class MESConnectionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    connector_type: Optional[str] = Field(default=None, pattern=r"^(mock|rest)$")
    config: Optional[dict] = None
    is_active: Optional[bool] = None
    product_line_code: Optional[str] = Field(default=None, min_length=1)


class MESConnectionResponse(BaseModel):
    connection_id: uuid.UUID
    name: str
    connector_type: str
    config: dict
    is_active: bool
    product_line_code: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MESConnectionListResponse(BaseModel):
    items: list[MESConnectionResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# REST connector nested config schemas
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
    def validate_backoff_non_negative(cls, v: list[float]) -> list[float]:
        if any(b < 0 for b in v):
            raise ValueError("backoff_seconds must all be >= 0")
        return v


class RESTEndpointConfig(BaseModel):
    path: str = Field(..., min_length=1)
    cursor_field: Optional[str] = None
    method: str = "GET"
    pagination: Optional[RESTPaginationConfig] = None
    response_path: Optional[str] = None


class RESTAuthConfig(BaseModel):
    model_config = {"extra": "allow"}

    # Plaintext fields (input only)
    inbound_api_key: Optional[str] = None
    outbound_api_key: Optional[str] = None
    token: Optional[str] = None
    password: Optional[str] = None
    secret: Optional[str] = None
    username: Optional[str] = None

    # Encrypted fields (persisted)
    api_key_hash: Optional[str] = None
    token_encrypted: Optional[str] = None
    password_encrypted: Optional[str] = None
    secret_encrypted: Optional[str] = None
    username_encrypted: Optional[str] = None
    outbound_api_key_encrypted: Optional[str] = None


class MESRetentionConfig(BaseModel):
    equipment_status_days: int = Field(default=90, ge=1)
    scrap_days: int = Field(default=365, ge=1)
    closed_order_days: int = Field(default=730, ge=1)


class RESTConfig(BaseModel):
    base_url: str = Field(..., pattern=r"^https?://")
    endpoints: dict[str, RESTEndpointConfig]
    field_mapping: dict[str, str]
    auth_type: Literal["none", "basic", "bearer", "api_key"] = "none"
    auth_config: Optional[RESTAuthConfig] = None
    timeout: int = Field(default=30, ge=1)
    retry: Optional[RESTRetryConfig] = None
    retention: Optional[MESRetentionConfig] = None
    push_enabled: bool = False

    @model_validator(mode="after")
    def _check_required_endpoints(self):
        required = {"production_orders", "equipment_status", "scrap_records", "measurements"}
        missing = required - set(self.endpoints.keys())
        if missing:
            raise ValueError(f"Missing required endpoints: {sorted(missing)}")
        return self

    @model_validator(mode="after")
    def _check_cursor_fields(self):
        for name in ("production_orders", "scrap_records", "measurements"):
            ep = self.endpoints.get(name)
            if ep is not None and not ep.cursor_field:
                raise ValueError(f"endpoint '{name}' must have cursor_field")
        return self

    @model_validator(mode="after")
    def _check_source_updated_at(self):
        if not self.field_mapping.get("source_updated_at"):
            raise ValueError('field_mapping must include "source_updated_at" with non-empty value')
        return self

    @model_validator(mode="after")
    def _check_auth_credentials(self):
        if self.auth_type == "none":
            return self
        ac = self.auth_config
        if ac is None:
            raise ValueError("auth_config is required when auth_type is not 'none'")

        plaintext_present = bool(
            ac.username or ac.password or ac.token or ac.secret
            or ac.inbound_api_key or ac.outbound_api_key
        )
        encrypted_present = bool(
            ac.username_encrypted or ac.password_encrypted or ac.token_encrypted
            or ac.secret_encrypted or ac.api_key_hash or ac.outbound_api_key_encrypted
        )

        if not plaintext_present and not encrypted_present:
            raise ValueError(f"No credentials provided for auth_type '{self.auth_type}'")

        if self.auth_type == "basic" and not (ac.username or ac.username_encrypted):
            raise ValueError("auth_type 'basic' requires username")
        if self.auth_type == "basic" and not (ac.password or ac.password_encrypted):
            raise ValueError("auth_type 'basic' requires password")
        if self.auth_type == "bearer" and not (ac.token or ac.token_encrypted):
            raise ValueError("auth_type 'bearer' requires token")
        if self.auth_type == "api_key" and not (
            ac.inbound_api_key or ac.outbound_api_key
            or ac.api_key_hash or ac.outbound_api_key_encrypted
        ):
            raise ValueError("auth_type 'api_key' requires at least one api_key variant")

        return self

    @model_validator(mode="after")
    def _check_push_event(self):
        if self.push_enabled:
            ep = self.endpoints.get("push_event")
            if ep is None:
                raise ValueError("push_enabled=True requires 'push_event' endpoint")
            if ep.method.upper() != "POST":
                raise ValueError("push_event endpoint must use method='POST'")
        return self


# ---------------------------------------------------------------------------
# Entity response schemas
# ---------------------------------------------------------------------------

class MESProductionOrderResponse(BaseModel):
    order_id: uuid.UUID
    connection_id: uuid.UUID
    order_no: str
    product_model: Optional[str] = None
    process_route: Optional[str] = None
    planned_qty: Optional[int] = None
    actual_qty: Optional[int] = None
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    source_updated_at: Optional[datetime] = None
    product_line_code: Optional[str] = None
    mes_raw_data: Optional[dict] = None

    model_config = {"from_attributes": True}


class MESEquipmentStatusResponse(BaseModel):
    record_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    equipment_code: str
    equipment_name: Optional[str] = None
    status: str
    availability: Optional[float] = None
    performance: Optional[float] = None
    quality: Optional[float] = None
    oee: Optional[float] = None
    downtime_reason: Optional[str] = None
    recorded_at: datetime
    product_line_code: Optional[str] = None
    mes_raw_data: Optional[dict] = None

    model_config = {"from_attributes": True}


class MESScrapRecordResponse(BaseModel):
    scrap_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    order_no: Optional[str] = None
    order_id: Optional[uuid.UUID] = None
    equipment_code: Optional[str] = None
    defect_type: str
    defect_category: Optional[str] = None
    defect_qty: int
    total_qty: int
    defect_description: Optional[str] = None
    recorded_at: datetime
    source_updated_at: Optional[datetime] = None
    product_line_code: Optional[str] = None
    mes_raw_data: Optional[dict] = None

    model_config = {"from_attributes": True}


class MESProductionOrderListResponse(BaseModel):
    items: list[MESProductionOrderResponse]
    total: int
    page: int
    page_size: int


class MESScrapRecordListResponse(BaseModel):
    items: list[MESScrapRecordResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Ingestion request schemas
# ---------------------------------------------------------------------------

class MESIngestBase(BaseModel):
    raw_data: Optional[dict] = None


class MESIngestMeasurement(MESIngestBase):
    data_type: Literal["measurement"]
    external_id: str
    order_no: Optional[str] = None
    ic_code: str
    values: list[float]
    sampled_at: datetime
    source_updated_at: Optional[datetime] = None
    batch_no: Optional[str] = None
    product_line_code: Optional[str] = None


class MESIngestProductionOrder(MESIngestBase):
    data_type: Literal["production_order"]
    order_no: str
    product_model: Optional[str] = None
    process_route: Optional[str] = None
    planned_qty: Optional[int] = None
    actual_qty: Optional[int] = None
    status: str = "planned"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    source_updated_at: Optional[datetime] = None
    product_line_code: Optional[str] = None


class MESIngestEquipmentStatus(MESIngestBase):
    data_type: Literal["equipment_status"]
    external_id: str
    equipment_code: str
    equipment_name: Optional[str] = None
    status: str
    availability: Optional[float] = None
    performance: Optional[float] = None
    quality: Optional[float] = None
    oee: Optional[float] = None
    downtime_reason: Optional[str] = None
    recorded_at: datetime
    product_line_code: Optional[str] = None

    @field_validator("availability", "performance", "quality", "oee")
    @classmethod
    def validate_percentage(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("must be between 0 and 100")
        return v


class MESIngestScrapRecord(MESIngestBase):
    data_type: Literal["scrap_record"]
    external_id: str
    order_no: Optional[str] = None
    equipment_code: Optional[str] = None
    defect_type: str
    defect_category: Optional[str] = None
    defect_qty: int
    total_qty: int
    defect_description: Optional[str] = None
    recorded_at: datetime
    source_updated_at: Optional[datetime] = None
    product_line_code: Optional[str] = None

    @field_validator("defect_qty", "total_qty")
    @classmethod
    def validate_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @model_validator(mode="after")
    def validate_defect_le_total(self):
        if self.defect_qty > self.total_qty:
            raise ValueError("defect_qty must not exceed total_qty")
        return self


MESIngestRequest = (
    MESIngestMeasurement
    | MESIngestProductionOrder
    | MESIngestEquipmentStatus
    | MESIngestScrapRecord
)


# ---------------------------------------------------------------------------
# Dashboard schemas
# ---------------------------------------------------------------------------

class MESEquipmentSummary(BaseModel):
    equipment_code: str
    equipment_name: Optional[str] = None
    status: str
    availability: Optional[float] = None
    performance: Optional[float] = None
    quality: Optional[float] = None
    oee: Optional[float] = None


class MESDashboardResponse(BaseModel):
    equipment_summary: list[MESEquipmentSummary]
    running_count: int
    down_count: int
    total_planned: int
    total_actual: int
    scrap_by_category: dict[str, int]
    scrap_trend_7d: list[dict]


# ---------------------------------------------------------------------------
# Sync job schema
# ---------------------------------------------------------------------------

class MESSyncJobResponse(BaseModel):
    job_id: uuid.UUID
    connection_id: uuid.UUID
    data_type: str
    status: str
    checkpoint: Optional[datetime] = None
    next_run_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    consecutive_failures: int

    model_config = {"from_attributes": True}
