import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

# ─── Profile ───

class AqlProfileCreate(BaseModel):
    supplier_id: uuid.UUID
    material_id: uuid.UUID
    base_aql: float
    current_aql: float
    min_aql: float | None = None
    max_aql: float | None = None
    inspection_level: str = "II"
    product_line_code: str


class AqlProfileUpdate(BaseModel):
    min_aql: float | None = None
    max_aql: float | None = None
    inspection_level: str | None = None


class AqlProfileResponse(BaseModel):
    supplier_id: uuid.UUID
    material_id: uuid.UUID
    base_aql: float
    current_aql: float
    min_aql: Optional[float] = None
    max_aql: Optional[float] = None
    inspection_level: str
    state: str
    frozen_until: Optional[date] = None
    frozen_reason: Optional[str] = None
    effective_from: Optional[date] = None
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    state_changed_at: Optional[datetime] = None
    product_line_code: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AqlProfileListResponse(BaseModel):
    items: list[AqlProfileResponse]
    total: int
    page: int
    page_size: int


# ─── Recommendation ───

class AqlRecommendationResponse(BaseModel):
    recommendation_id: uuid.UUID
    profile_id: uuid.UUID
    supplier_id: uuid.UUID
    material_id: uuid.UUID
    current_aql: float
    recommended_aql: float
    direction: str
    trigger_rules: list[dict]
    evidence: dict
    status: str
    approval_level: str
    engineer_decision: Optional[str] = None
    engineer_decided_by: Optional[uuid.UUID] = None
    engineer_decided_at: Optional[datetime] = None
    manager_decision: Optional[str] = None
    manager_decided_by: Optional[uuid.UUID] = None
    manager_decided_at: Optional[datetime] = None
    effective_from: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AqlRecommendationListResponse(BaseModel):
    items: list[AqlRecommendationResponse]
    total: int
    page: int
    page_size: int


class AqlRecommendationApproveRequest(BaseModel):
    reason: str | None = None


class AqlRecommendationRejectRequest(BaseModel):
    reason: str


# ─── Quality Snapshot ───

class AqlQualitySnapshotResponse(BaseModel):
    snapshot_id: uuid.UUID
    supplier_id: uuid.UUID
    material_id: uuid.UUID
    total_batches: int
    consecutive_accepted: int
    consecutive_rejected: int
    last_30d_batch_count: int
    last_30d_ppm: float
    last_90d_ppm: float
    open_scar_count: int
    supplier_rating: Optional[float] = None
    has_safety_defect: bool
    linked_customer_complaint: bool
    calculated_state: str
    snapshot_at: datetime

    model_config = {"from_attributes": True}


class AqlQualitySnapshotTrendResponse(BaseModel):
    snapshots: list[AqlQualitySnapshotResponse]


# ─── Config ───

class AqlConfigResponse(BaseModel):
    config_id: uuid.UUID
    config_key: str
    config_value: str
    value_type: str
    description: Optional[str] = None
    product_line_code: str
    is_editable: bool

    model_config = {"from_attributes": True}


class AqlConfigUpdate(BaseModel):
    config_value: str


# ─── Trigger / Preview ───

class AqlTriggerRequest(BaseModel):
    supplier_id: uuid.UUID
    material_id: uuid.UUID


class AqlPreviewRequest(BaseModel):
    supplier_id: uuid.UUID
    material_id: uuid.UUID


class AqlPreviewResponse(BaseModel):
    target_state: str
    recommended_aql: float
    direction: str
    trigger_rules: list[dict]
    evidence: dict
