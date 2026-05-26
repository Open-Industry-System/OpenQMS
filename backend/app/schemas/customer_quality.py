import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


VALID_CATEGORIES = {"safety", "function", "appearance", "delivery"}
VALID_SEVERITIES = {"致命", "严重", "一般", "轻微"}
VALID_COMPLAINT_STATUSES = {"open", "investigating", "responded", "closed", "cancelled"}
VALID_RMA_STATUSES = {"open", "analysis", "action_pending", "closed", "cancelled"}
VALID_RESPONSIBILITIES = {"supplier", "internal", "transport", "customer_misuse", "unknown"}


class CustomerCreate(BaseModel):
    customer_code: str
    name: str
    segment: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    csr_list: list | None = None
    ppm_target: float | None = None
    annual_shipment_qty: int | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    customer_code: str | None = None
    name: str | None = None
    segment: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    csr_list: list | None = None
    ppm_target: float | None = None
    annual_shipment_qty: int | None = None
    notes: str | None = None


class CustomerResponse(BaseModel):
    customer_id: uuid.UUID
    customer_code: str
    name: str
    segment: str | None
    contact_name: str | None
    contact_email: str | None
    contact_phone: str | None
    csr_list: list | None
    ppm_target: float | None
    annual_shipment_qty: int | None
    notes: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
    total: int
    page: int
    page_size: int


class CustomerSummaryResponse(BaseModel):
    customer_id: uuid.UUID
    customer_code: str
    name: str
    segment: str | None = None
    complaint_count: int
    open_complaint_count: int
    overdue_count: int
    open_fatal_count: int
    rma_count: int
    independent_rma_qty: int
    impact_qty: int
    ppm: float | None
    ppm_target: float | None
    risk_light: str


class ComplaintCreate(BaseModel):
    complaint_no: str
    product_line_code: str
    customer_id: uuid.UUID
    product_id: str | None = None
    batch_no: str | None = None
    serial_number: str | None = None
    category: str
    severity: str
    defect_desc: str
    impact_qty: int = 0
    occurred_date: date | None = None
    received_date: date
    due_date: date | None = None
    status: str = "open"
    fmea_ref_id: uuid.UUID | None = None
    capa_ref_id: uuid.UUID | None = None
    has_rma: bool = False
    preliminary_response: str | None = None
    root_cause: str | None = None
    corrective_action: str | None = None
    attachments: list | None = None
    assignee_id: uuid.UUID | None = None
    supplier_responsibility: bool = False
    scar_ref_id: uuid.UUID | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        if value not in VALID_CATEGORIES:
            raise ValueError("invalid category")
        return value

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        if value not in VALID_SEVERITIES:
            raise ValueError("invalid severity")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in VALID_COMPLAINT_STATUSES:
            raise ValueError("invalid status")
        return value


class ComplaintUpdate(BaseModel):
    complaint_no: str | None = None
    product_line_code: str | None = None
    customer_id: uuid.UUID | None = None
    product_id: str | None = None
    batch_no: str | None = None
    serial_number: str | None = None
    category: str | None = None
    severity: str | None = None
    defect_desc: str | None = None
    impact_qty: int | None = None
    occurred_date: date | None = None
    received_date: date | None = None
    due_date: date | None = None
    status: str | None = None
    fmea_ref_id: uuid.UUID | None = None
    capa_ref_id: uuid.UUID | None = None
    has_rma: bool | None = None
    preliminary_response: str | None = None
    root_cause: str | None = None
    corrective_action: str | None = None
    attachments: list | None = None
    assignee_id: uuid.UUID | None = None
    supplier_responsibility: bool | None = None
    scar_ref_id: uuid.UUID | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_CATEGORIES:
            raise ValueError("invalid category")
        return value

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_SEVERITIES:
            raise ValueError("invalid severity")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_COMPLAINT_STATUSES:
            raise ValueError("invalid status")
        return value


class ComplaintResponse(BaseModel):
    complaint_id: uuid.UUID
    complaint_no: str
    product_line_code: str
    customer_id: uuid.UUID
    product_id: str | None
    batch_no: str | None
    serial_number: str | None
    category: str
    severity: str
    defect_desc: str
    impact_qty: int
    occurred_date: date | None
    received_date: date
    due_date: date | None
    status: str
    fmea_ref_id: uuid.UUID | None
    capa_ref_id: uuid.UUID | None
    has_rma: bool
    preliminary_response: str | None
    root_cause: str | None
    corrective_action: str | None
    attachments: list | None
    assignee_id: uuid.UUID | None
    supplier_responsibility: bool
    scar_ref_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class ComplaintListResponse(BaseModel):
    items: list[ComplaintResponse]
    total: int
    page: int
    page_size: int


class RMARecordCreate(BaseModel):
    rma_no: str
    product_line_code: str
    customer_id: uuid.UUID
    complaint_id: uuid.UUID | None = None
    product_id: str | None = None
    batch_no: str | None = None
    serial_number: str | None = None
    return_qty: int
    defect_type: str
    responsibility: str | None = None
    analysis_result: str | None = None
    corrective_action: str | None = None
    status: str = "open"
    fmea_ref_id: uuid.UUID | None = None
    capa_ref_id: uuid.UUID | None = None
    scar_ref_id: uuid.UUID | None = None
    attachments: list | None = None
    assignee_id: uuid.UUID | None = None
    tracking_number: str | None = None
    received_date: date | None = None

    @field_validator("responsibility")
    @classmethod
    def validate_responsibility(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_RESPONSIBILITIES:
            raise ValueError("invalid responsibility")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in VALID_RMA_STATUSES:
            raise ValueError("invalid status")
        return value


class RMARecordUpdate(BaseModel):
    rma_no: str | None = None
    product_line_code: str | None = None
    customer_id: uuid.UUID | None = None
    complaint_id: uuid.UUID | None = None
    product_id: str | None = None
    batch_no: str | None = None
    serial_number: str | None = None
    return_qty: int | None = None
    defect_type: str | None = None
    responsibility: str | None = None
    analysis_result: str | None = None
    corrective_action: str | None = None
    status: str | None = None
    fmea_ref_id: uuid.UUID | None = None
    capa_ref_id: uuid.UUID | None = None
    scar_ref_id: uuid.UUID | None = None
    attachments: list | None = None
    assignee_id: uuid.UUID | None = None
    tracking_number: str | None = None
    received_date: date | None = None
    closed_at: datetime | None = None

    @field_validator("responsibility")
    @classmethod
    def validate_responsibility(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_RESPONSIBILITIES:
            raise ValueError("invalid responsibility")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_RMA_STATUSES:
            raise ValueError("invalid status")
        return value


class RMARecordResponse(BaseModel):
    rma_id: uuid.UUID
    rma_no: str
    product_line_code: str
    customer_id: uuid.UUID
    complaint_id: uuid.UUID | None
    product_id: str | None
    batch_no: str | None
    serial_number: str | None
    return_qty: int
    defect_type: str
    responsibility: str | None
    analysis_result: str | None
    corrective_action: str | None
    status: str
    fmea_ref_id: uuid.UUID | None
    capa_ref_id: uuid.UUID | None
    scar_ref_id: uuid.UUID | None
    attachments: list | None
    assignee_id: uuid.UUID | None
    tracking_number: str | None
    received_date: date | None
    closed_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RMARecordListResponse(BaseModel):
    items: list[RMARecordResponse]
    total: int
    page: int
    page_size: int


class CustomerQualityDashboardResponse(BaseModel):
    kpi: dict
    customers: list[CustomerSummaryResponse]
    trend: list[dict]
    complaints_by_status: dict[str, int]
    complaints_by_severity: dict[str, int]
    rma_by_status: dict[str, int]
    rma_by_responsibility: dict[str, int]
