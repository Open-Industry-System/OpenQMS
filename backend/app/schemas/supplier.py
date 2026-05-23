import uuid
from datetime import datetime, date
from pydantic import BaseModel, field_validator


# ─── Supplier ───

class SupplierCreate(BaseModel):
    name: str
    short_name: str
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    address: str | None = None
    product_scope: str | None = None

    @field_validator("name", "short_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class SupplierUpdate(BaseModel):
    name: str | None = None
    short_name: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    address: str | None = None
    product_scope: str | None = None
    audit_plan_id: uuid.UUID | None = None

    @field_validator("name", "short_name")
    @classmethod
    def not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class SupplierResponse(BaseModel):
    supplier_id: uuid.UUID
    supplier_no: str
    name: str
    short_name: str
    contact_name: str | None
    contact_phone: str | None
    contact_email: str | None
    address: str | None
    product_scope: str | None
    status: str
    audit_plan_id: uuid.UUID | None
    reject_reason: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SupplierListResponse(BaseModel):
    items: list[SupplierResponse]
    total: int
    page: int
    page_size: int


# ─── Certification ───

class SupplierCertificationCreate(BaseModel):
    cert_type: str
    cert_no: str
    issued_by: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None

    @field_validator("cert_type", "cert_no")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class SupplierCertificationUpdate(BaseModel):
    cert_type: str | None = None
    cert_no: str | None = None
    issued_by: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None

    @field_validator("cert_type", "cert_no")
    @classmethod
    def not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class SupplierCertificationResponse(BaseModel):
    cert_id: uuid.UUID
    supplier_id: uuid.UUID
    cert_type: str
    cert_no: str
    issued_by: str | None
    issue_date: date | None
    expiry_date: date | None
    file_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SupplierCertificationListResponse(BaseModel):
    items: list[SupplierCertificationResponse]


# ─── Evaluation ───

class SupplierEvaluationCreate(BaseModel):
    eval_period: str
    eval_type: str
    quality_score: float
    delivery_score: float
    service_score: float
    capa_count: int | None = 0
    finding_count: int | None = 0
    premium_freight_count: int | None = 0
    customer_disruption_count: int | None = 0
    notes: str | None = None

    @field_validator("eval_type")
    @classmethod
    def validate_eval_type(cls, v: str) -> str:
        if v not in ("quarterly", "annual"):
            raise ValueError('eval_type must be "quarterly" or "annual"')
        return v

    @field_validator("quality_score", "delivery_score", "service_score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        if v < 0 or v > 100:
            raise ValueError("score must be between 0 and 100")
        return v


class SupplierEvaluationResponse(BaseModel):
    eval_id: uuid.UUID
    supplier_id: uuid.UUID
    eval_period: str
    eval_type: str
    quality_score: float
    delivery_score: float
    service_score: float
    capa_count: int
    finding_count: int
    premium_freight_count: int
    customer_disruption_count: int
    capa_penalty: float
    finding_penalty: float
    premium_freight_penalty: float
    customer_disruption_penalty: float
    total_score: float
    grade: str
    notes: str | None
    evaluated_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class SupplierEvaluationListResponse(BaseModel):
    items: list[SupplierEvaluationResponse]


# ─── Stats & Alerts ───

class SupplierStatsResponse(BaseModel):
    total_count: int
    pending_review_count: int
    approved_count: int
    cert_expiry_30d_count: int


class SupplierExpiryAlertResponse(BaseModel):
    cert_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str
    supplier_short_name: str
    cert_type: str
    cert_no: str
    expiry_date: date
    days_remaining: int
