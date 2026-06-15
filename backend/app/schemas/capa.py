import uuid
from datetime import date, datetime

from pydantic import BaseModel


class CAPACreate(BaseModel):
    title: str
    document_no: str
    severity: str = "general"
    due_date: date | None = None
    product_line_code: str = "DC-DC-100"


class CAPAUpdate(BaseModel):
    title: str | None = None
    d1_team: list[dict] | None = None
    d2_description: str | None = None
    d3_interim: str | None = None
    d4_root_cause: str | None = None
    d5_correction: str | None = None
    d6_verification: str | None = None
    d7_prevention: str | None = None
    d8_closure: str | None = None
    severity: str | None = None
    due_date: date | None = None
    fmea_ref_id: uuid.UUID | None = None
    fmea_node_id: str | None = None
    product_line_code: str | None = None


class CAPAResponse(BaseModel):
    report_id: uuid.UUID
    document_no: str
    title: str
    product_line_code: str
    status: str
    severity: str
    d1_team: list | None = None
    d2_description: str | None = None
    d3_interim: str | None = None
    d4_root_cause: str | None = None
    d5_correction: str | None = None
    d6_verification: str | None = None
    d7_prevention: str | None = None
    d8_closure: str | None = None
    fmea_ref_id: uuid.UUID | None = None
    fmea_node_id: str | None = None
    due_date: date | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CAPAListResponse(BaseModel):
    items: list[CAPAResponse]
    total: int
    page: int
    page_size: int


class D7Recommendation(BaseModel):
    fmea_id: uuid.UUID
    fmea_document_no: str
    failure_mode_node_id: str
    failure_mode_name: str
    failure_cause_node_id: str | None = None
    failure_cause_name: str | None = None
    prevention_control_node_id: str | None = None
    prevention_control_name: str | None = None
    match_source: str  # "linked" | "keyword"
    match_reason: str
    related_d4_keywords: list[str] = []
    suggested_prevention: str | None = None


class D7RecommendationResponse(BaseModel):
    recommendations: list[D7Recommendation]


class D4Recommendation(BaseModel):
    failure_cause_node_id: str | None = None
    failure_cause_name: str
    failure_cause_desc: str | None = None
    failure_mode_node_id: str | None = None
    failure_mode_name: str | None = None
    fmea_document_no: str | None = None
    fmea_id: str | None = None
    match_source: str  # "linked" | "keyword" | "rule" | "fmea_graph" | "semantic_search" | "historical_capa" | "llm"
    match_reason: str
    related_d2_keywords: list[str] = []
    confidence: float = 0.5
    # --- 新增字段（可选，历史 CAPA 来源标识） ---
    source_capa_id: str | None = None
    source_capa_document_no: str | None = None
    source_product_line_code: str | None = None


class D4RecommendationResponse(BaseModel):
    items: list[D4Recommendation]


class D5ExistingControl(BaseModel):
    failure_mode_node_id: str | None = None
    failure_mode_name: str | None = None
    failure_cause_node_id: str | None = None
    failure_cause_name: str | None = None
    control_node_id: str
    control_name: str
    control_type: str  # "prevention" | "detection"
    match_source: str
    match_reason: str
    fmea_id: str | None = None
    fmea_document_no: str | None = None


class D5GeneralSuggestion(BaseModel):
    content: str
    category: str  # "预防措施" | "探测措施" | "纠正措施"
    basis: str
    confidence: float
    match_reason: str | None = None
    # --- 新增字段（可选，历史 CAPA 来源标识） ---
    match_source: str | None = None
    source_capa_id: str | None = None
    source_capa_document_no: str | None = None


class D5RecommendationResponse(BaseModel):
    existing_controls: list[D5ExistingControl]
    general_suggestions: list[D5GeneralSuggestion]


class AdvanceRequest(BaseModel):
    d7_skip_reasons: list[dict] | None = None
