import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class SCARCreate(BaseModel):
    supplier_id: uuid.UUID
    source_type: Literal["iqc", "complaint", "rma", "manual"]
    source_id: uuid.UUID | None = None
    description: str
    product_line_code: str | None = None
    requested_action: str | None = None
    due_date: date | None = None


class SCARUpdate(BaseModel):
    description: str | None = None
    requested_action: str | None = None
    due_date: date | None = None


class SCARResponse(BaseModel):
    scar_id: uuid.UUID
    scar_no: str
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    supplier_no: str | None = None
    source_type: str
    source_id: uuid.UUID | None
    description: str
    product_line_code: str | None
    requested_action: str | None
    supplier_response: str | None
    status: str
    capa_ref_id: uuid.UUID | None
    resolution_summary: str | None
    issued_by: uuid.UUID | None
    issued_date: date | None
    due_date: date | None
    closed_date: date | None
    created_at: datetime
    updated_at: datetime


class SCARListResponse(BaseModel):
    items: list[SCARResponse]
    total: int
    page: int
    page_size: int


class SCARTransitionRequest(BaseModel):
    action: Literal["start", "respond", "verify", "reject", "close", "reopen"]
    supplier_response: str | None = None
    resolution_summary: str | None = None


class SCARLinkCAPARequest(BaseModel):
    capa_ref_id: uuid.UUID
