import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ─── Alerts ────────────────────────────────────────────────────────────────────

class AlertListParams(BaseModel):
    page: int = 1
    page_size: int = 20
    risk_level: Optional[str] = None
    status: Optional[str] = None
    supplier_id: Optional[uuid.UUID] = None
    product_line_code: Optional[str] = None


class AlertResponse(BaseModel):
    alert_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str = ""
    supplier_no: str = ""
    risk_level: str
    risk_score: float
    quality_score: float
    delivery_score: float
    compliance_score: float
    rule_results: dict
    alert_type: str
    status: str
    handled_by: Optional[uuid.UUID]
    handled_at: Optional[datetime]
    handle_note: Optional[str]
    linked_scar_id: Optional[uuid.UUID]
    linked_capa_id: Optional[uuid.UUID]
    snapshot_date: date
    product_line_code: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    total: int
    page: int
    page_size: int


class HandleAlertRequest(BaseModel):
    action: str  # acknowledge | ignore | close
    note: Optional[str] = None


# ─── Dashboard ─────────────────────────────────────────────────────────────────

class RiskDashboardResponse(BaseModel):
    high_risk_count: int
    critical_risk_count: int
    open_alert_count: int
    avg_risk_score: float
    risk_distribution: dict  # {"low": N, "medium": N, "high": N, "critical": N}
    supplier_risk_points: list[dict]  # For scatter plot


# ─── Configs ───────────────────────────────────────────────────────────────────

class RuleConfigResponse(BaseModel):
    config_id: uuid.UUID
    rule_id: str
    enabled: bool
    thresholds: dict
    weight: float
    supplier_id: Optional[uuid.UUID]
    category: str
    product_line_code: Optional[str]
    updated_by: uuid.UUID
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RuleConfigUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    thresholds: Optional[dict] = None
    weight: Optional[float] = None


# ─── Notification Channels ─────────────────────────────────────────────────────

class ChannelCreateRequest(BaseModel):
    channel_type: str  # email | webhook
    config: dict
    min_risk_level: str = "high"
    enabled: bool = True
    supplier_id: Optional[uuid.UUID] = None
    product_line_code: Optional[str] = None


class ChannelUpdateRequest(BaseModel):
    config: Optional[dict] = None
    min_risk_level: Optional[str] = None
    enabled: Optional[bool] = None


class ChannelResponse(BaseModel):
    channel_id: uuid.UUID
    channel_type: str
    config: dict
    min_risk_level: str
    enabled: bool
    supplier_id: Optional[uuid.UUID]
    product_line_code: Optional[str]
    created_by: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Evaluation ────────────────────────────────────────────────────────────────

class EvaluationResponse(BaseModel):
    supplier_id: uuid.UUID
    risk_level: str
    risk_score: float
    quality_score: float
    delivery_score: float
    compliance_score: float
    rule_results: list[dict]
    alert_id: Optional[uuid.UUID] = None
