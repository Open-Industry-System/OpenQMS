import uuid
from datetime import date, datetime
from pydantic import BaseModel


class CAPACreate(BaseModel):
    title: str
    document_no: str
    severity: str = "一般"
    due_date: date | None = None


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
