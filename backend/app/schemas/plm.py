"""PLM Pydantic v2 schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


CONNECTOR_TYPE_PATTERN = r"^(mock|rest|siemens_tc|dassault_enovia|ptc_windchill)$"


class PLMConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    connector_type: str = Field(..., pattern=CONNECTOR_TYPE_PATTERN)
    config: dict[str, Any] = Field(default_factory=dict)
    product_line_code: str = Field(..., min_length=1)


class PLMConnectionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    connector_type: Optional[str] = Field(None, pattern=CONNECTOR_TYPE_PATTERN)
    config: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
    product_line_code: Optional[str] = Field(None, min_length=1)


class PLMConnectionResponse(BaseModel):
    connection_id: uuid.UUID
    name: str
    connector_type: str
    config: dict[str, Any]
    is_active: bool
    product_line_code: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PLMConnectionListResponse(BaseModel):
    items: list[PLMConnectionResponse]
    total: int
    page: int
    page_size: int

    model_config = ConfigDict(from_attributes=True)


class PLMPartResponse(BaseModel):
    part_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    part_number: str
    name: str
    revision: str
    material: Optional[str] = None
    specification: Optional[str] = None
    status: str
    is_safety_related: bool
    is_key_characteristic: bool
    source_updated_at: Optional[datetime] = None
    product_line_code: Optional[str] = None
    plm_raw_data: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class PLMBOMResponse(BaseModel):
    bom_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    parent_part_number: str
    parent_revision: str
    child_part_number: str
    child_revision: str
    quantity: float
    bom_revision: str
    level: int
    source_updated_at: Optional[datetime] = None
    product_line_code: Optional[str] = None
    plm_raw_data: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class PLMChangeOrderResponse(BaseModel):
    change_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    change_number: str
    title: str
    description: Optional[str] = None
    change_type: str
    status: str
    priority: str
    affected_part_numbers: list[str]
    proposed_changes: Optional[dict[str, Any]] = None
    requested_by: Optional[str] = None
    approved_by: Optional[str] = None
    planned_implementation_date: Optional[datetime] = None
    actual_implementation_date: Optional[datetime] = None
    source_updated_at: Optional[datetime] = None
    product_line_code: Optional[str] = None
    plm_raw_data: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class PLMChangeImpactTaskResponse(BaseModel):
    task_id: uuid.UUID
    change_id: uuid.UUID
    status: str
    retry_count: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class PLMDashboardResponse(BaseModel):
    part_count: int
    bom_count: int
    pending_ecn_count: int
    pending_sc_count: int
    recent_changes: list[PLMChangeOrderResponse]

    model_config = ConfigDict(from_attributes=True)


class BOMImportRequest(BaseModel):
    fmea_id: uuid.UUID
    overwrite: bool = False


class PLMPartLinkFMEARequest(BaseModel):
    fmea_id: uuid.UUID
    node_id: str


class PLMPartConfirmSCRequest(BaseModel):
    fmea_id: uuid.UUID
    node_id: str
    characteristic_type: Literal["safety", "key_characteristic"]
