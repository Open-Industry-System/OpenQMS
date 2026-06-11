import uuid
from datetime import datetime, date

from pydantic import BaseModel, field_validator


class ReviewOutputCreate(BaseModel):
    category: str
    description: str
    responsible_id: uuid.UUID | None = None
    due_date: date | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in ("improvement_opportunity", "system_change", "resource_need"):
            raise ValueError("invalid category")
        return v


class ReviewOutputUpdate(BaseModel):
    category: str | None = None
    description: str | None = None
    responsible_id: uuid.UUID | None = None
    due_date: date | None = None
    status: str | None = None
    completion_notes: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v and v not in ("pending", "in_progress", "completed", "verified"):
            raise ValueError("invalid status")
        return v


class ReviewOutputVerify(BaseModel):
    verification_notes: str


class ReviewOutputResponse(BaseModel):
    output_id: uuid.UUID
    review_id: uuid.UUID
    category: str
    description: str
    responsible_id: uuid.UUID | None
    due_date: date | None
    status: str
    completion_notes: str | None
    verified_by: uuid.UUID | None
    verified_at: date | None
    verification_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ManagementReviewCreate(BaseModel):
    title: str
    review_date: date
    product_line_code: str | None = None
    location: str | None = None
    chair_person_id: uuid.UUID
    participants: list[dict] | None = None


class ManagementReviewUpdate(BaseModel):
    title: str | None = None
    review_date: date | None = None
    actual_date: date | None = None
    product_line_code: str | None = None
    location: str | None = None
    chair_person_id: uuid.UUID | None = None
    participants: list[dict] | None = None
    meeting_minutes: str | None = None
    manual_inputs: dict | None = None
    attachments: list[dict] | None = None


class ManagementReviewResponse(BaseModel):
    review_id: uuid.UUID
    doc_no: str
    title: str
    review_date: date
    actual_date: date | None
    status: str
    product_line_code: str | None
    location: str | None
    chair_person_id: uuid.UUID
    participants: list[dict] | None
    meeting_minutes: str | None
    data_package: dict | None
    manual_inputs: dict | None
    attachments: list[dict] | None
    created_by: uuid.UUID
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ManagementReviewListResponse(BaseModel):
    items: list[ManagementReviewResponse]
    total: int
    page: int
    page_size: int


class ReportSection(BaseModel):
    key: str
    title: str
    source: str
    base_text: str
    ai_analysis: str
    findings: list[str]
    recommendations: list[str]
    manual_text: str
    data_snapshot: dict | str | list | int | float | bool | None

    model_config = {"extra": "ignore"}


class ReportContent(BaseModel):
    generated_at: str
    generation_model: str
    llm_enriched: bool
    sections: list[ReportSection]
    executive_summary: str
    overall_recommendations: list[str]
    updated_at: str | None = None

    model_config = {"extra": "ignore"}


class ReportGenerateRequest(BaseModel):
    use_llm: bool = True


class ReportGenerateResponse(BaseModel):
    report_status: str
    generated_report: ReportContent


class ReportSaveDraftRequest(BaseModel):
    generated_report: ReportContent


class ReportVersionResponse(BaseModel):
    report_id: uuid.UUID
    review_id: uuid.UUID
    version_no: int
    content: ReportContent
    created_by: uuid.UUID
    finalized_by: uuid.UUID | None
    finalized_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportExportResponse(BaseModel):
    markdown: str
