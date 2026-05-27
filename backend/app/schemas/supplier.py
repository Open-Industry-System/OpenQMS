import uuid
from datetime import datetime, date
from typing import List
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


# ─── PPAP (DEPRECATED) ───
# 这些旧 PPAP schema 已被 schemas/ppap.py 取代，保留以兼容已有模型引用。
# 新 PPAP 模块请使用 schemas/ppap.py。
# DEPRECATED: 迁移至 schemas/ppap.py

class PPAPElementCreate(BaseModel):
    element_no: int
    element_name: str
    status: str = "pending"
    notes: str | None = None
    sort_order: int = 0


class PPAPElementResponse(BaseModel):
    element_id: uuid.UUID
    submission_id: uuid.UUID
    element_no: int
    element_name: str
    status: str
    notes: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class PPAPSubmissionCreate(BaseModel):
    part_no: str
    part_name: str
    submission_level: int
    submission_date: date | None = None
    notes: str | None = None
    elements: list[PPAPElementCreate] = []


class PPAPSubmissionResponse(BaseModel):
    submission_id: uuid.UUID
    supplier_id: uuid.UUID
    part_no: str
    part_name: str
    submission_level: int
    submission_date: date | None
    status: str
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    notes: str | None
    elements: list[PPAPElementResponse] = []
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PPAPSubmissionListResponse(BaseModel):
    items: list[PPAPSubmissionResponse]


# DEPRECATED: 以下 SCAR schemas 已被 app.schemas.scar 替代，保留仅供 trigger-scar 兼容，后续清理
# ─── SCAR ───

class SCARCreate(BaseModel):
    source_type: str
    source_id: uuid.UUID | None = None
    description: str
    requested_action: str | None = None
    issued_date: date | None = None
    due_date: date | None = None


class SCARUpdate(BaseModel):
    supplier_response: str | None = None
    status: str | None = None


class SCARResponse(BaseModel):
    scar_id: uuid.UUID
    scar_no: str
    supplier_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID | None
    description: str
    requested_action: str | None
    supplier_response: str | None
    status: str
    issued_by: uuid.UUID | None
    issued_date: date | None
    due_date: date | None
    closed_date: date | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SCARListResponse(BaseModel):
    items: list[SCARResponse]


# ─── IQC ───

class IqcInspectionCreate(BaseModel):
    part_no: str | None = None
    part_name: str | None = None
    lot_no: str | None = None
    lot_qty: int | None = None
    sample_qty: int | None = None
    inspection_result: str = "pending"
    defect_qty: int = 0
    defect_description: str | None = None
    linked_capa_id: uuid.UUID | None = None
    inspection_date: date | None = None
    inspected_by: uuid.UUID | None = None


class IqcInspectionUpdate(BaseModel):
    part_no: str | None = None
    part_name: str | None = None
    lot_no: str | None = None
    lot_qty: int | None = None
    sample_qty: int | None = None
    inspection_result: str | None = None
    defect_qty: int | None = None
    defect_description: str | None = None
    linked_capa_id: uuid.UUID | None = None
    inspection_date: date | None = None
    inspected_by: uuid.UUID | None = None


class IqcInspectionResponse(BaseModel):
    inspection_id: uuid.UUID
    inspection_no: str
    supplier_id: uuid.UUID
    part_no: str | None
    part_name: str | None
    lot_no: str | None
    lot_qty: int | None
    sample_qty: int | None
    inspection_result: str
    defect_qty: int
    defect_description: str | None
    linked_capa_id: uuid.UUID | None
    inspection_date: date | None
    inspected_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IqcInspectionListResponse(BaseModel):
    items: list[IqcInspectionResponse]
    total: int
    page: int
    page_size: int


# ─── Quality Dashboard ───

class QualityKPI(BaseModel):
    total_suppliers: int
    overall_ppm: float
    batch_acceptance_rate: float
    open_scar_count: int


class PPMTrendPoint(BaseModel):
    month: str
    ppm: float


class GradeDistribution(BaseModel):
    A: int
    B: int
    C: int
    D: int


class SupplierRankingItem(BaseModel):
    supplier_id: uuid.UUID
    supplier_no: str
    name: str
    grade: str
    ppm: float
    batch_acceptance_rate: float
    delivery_rate: float
    open_scar_count: int

    model_config = {"from_attributes": True}


class QualityDashboardResponse(BaseModel):
    kpi: QualityKPI
    ppm_trend: List[PPMTrendPoint]
    grade_distribution: GradeDistribution
    ranking: List[SupplierRankingItem]


class SupplierQualityStats(BaseModel):
    grade: str
    total_score: float
    quality_score: float
    delivery_score: float
    service_score: float
    ppm: float
    batch_acceptance_rate: float
    total_inspections: int
    accepted_count: int
    scar_count: int
    open_scar_count: int


class SupplierQualityDetailResponse(BaseModel):
    supplier: SupplierResponse
    stats: SupplierQualityStats
    ppm_trend: List[PPMTrendPoint]
    acceptance_trend: List[dict]


class SupplierCompareItem(BaseModel):
    supplier_id: uuid.UUID
    name: str
    supplier_no: str
    grade: str
    ppm: float
    batch_acceptance_rate: float
    delivery_rate: float
    open_scar_count: int
    quality_score: float
    delivery_score: float
    service_score: float

    model_config = {"from_attributes": True}


class SupplierCompareResponse(BaseModel):
    suppliers: List[SupplierCompareItem]
    ppm_trends: dict
