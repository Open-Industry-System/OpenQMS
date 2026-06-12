import uuid
from datetime import datetime
from pydantic import BaseModel
from typing import Literal


class SCCreate(BaseModel):
    sc_name: str
    sc_type: Literal["CC", "SC"]
    customer_symbol: str | None = None
    sc_category: str | None = None
    spec_requirement: str | None = None
    source_fmea_id: uuid.UUID | None = None
    source_node_id: str | None = None
    source_type: Literal["DFMEA", "PFMEA"] | None = None
    sop_ref: str | None = None
    product_line_code: str = "DC-DC-100"


class SCUpdate(BaseModel):
    sc_name: str | None = None
    sc_category: str | None = None
    spec_requirement: str | None = None
    sop_ref: str | None = None
    customer_symbol: str | None = None
    msa_status: str | None = None
    is_supplier_shared: bool | None = None
    supplier_code: str | None = None
    # NOTE: is_safety_related, safety_regulation_ref, safety_verification_method
    # are intentionally EXCLUDED from SCUpdate to enforce the safety approval workflow.
    # Use the dedicated safety API endpoints instead.


class SCResponse(BaseModel):
    sc_id: uuid.UUID
    sc_code: str
    sc_name: str
    sc_type: str
    customer_symbol: str | None = None
    sc_category: str | None = None
    spec_requirement: str | None = None
    parent_sc_id: uuid.UUID | None = None
    source_fmea_id: uuid.UUID | None = None
    source_fmea_title: str | None = None
    source_fmea_document_no: str | None = None
    source_node_id: str
    source_type: str
    cp_item_id: uuid.UUID | None = None
    msa_study_id: uuid.UUID | None = None
    msa_status: str | None = "PENDING"
    sop_ref: str | None = None
    product_line_code: str
    factory_id: uuid.UUID | None = None
    is_supplier_shared: bool = False
    supplier_code: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    is_safety_related: bool = False
    is_safety_suggested: bool = False
    safety_approval_status: str | None = None
    safety_submitted_by: uuid.UUID | None = None
    safety_submitted_at: datetime | None = None
    safety_approved_by: uuid.UUID | None = None
    safety_approved_at: datetime | None = None
    safety_approval_comment: str | None = None
    safety_regulation_ref: str | None = None
    safety_verification_method: str | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class SCListResponse(BaseModel):
    items: list[SCResponse]
    total: int
    page: int
    page_size: int


class MatrixRow(BaseModel):
    sc_id: uuid.UUID
    sc_code: str
    sc_name: str
    sc_type: str
    customer_symbol: str | None = None
    product_line_code: str
    is_safety_related: bool = False
    has_dfmea: bool
    has_pfmea: bool
    has_cp: bool
    msa_status: str
    has_sop: bool
    dfmea_link: str | None = None
    pfmea_link: str | None = None
    cp_link: str | None = None
    msa_link: str | None = None


class MatrixResponse(BaseModel):
    characteristics: list[MatrixRow]


class SeverityWarning(BaseModel):
    node_id: str
    node_name: str
    severity: int
    fmea_id: uuid.UUID
    fmea_title: str


class CPSyncStatusItem(BaseModel):
    item_id: uuid.UUID
    step_no: str
    process_name: str
    current_special_class: str | None
    expected_special_class: str | None
    is_out_of_sync: bool


class CPSyncStatusResponse(BaseModel):
    items: list[CPSyncStatusItem]
    total_out_of_sync: int


class SafetySubmitRequest(BaseModel):
    safety_regulation_ref: str
    safety_verification_method: str


class SafetyApprovalAction(BaseModel):
    comment: str | None = None
