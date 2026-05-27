import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class PPAPCreate(BaseModel):
    supplier_id: uuid.UUID
    part_no: str
    part_name: str
    submission_level: int = Field(ge=1, le=5, default=3)
    submission_date: date | None = None
    customer_name: str | None = None
    product_line_code: str | None = None
    notes: str | None = None


class PPAPUpdate(BaseModel):
    part_no: str | None = None
    part_name: str | None = None
    submission_level: int | None = Field(ge=1, le=5, default=None)
    customer_name: str | None = None
    product_line_code: str | None = None
    notes: str | None = None


class PPAPElementUpdate(BaseModel):
    status: Literal["pending", "in_review", "approved", "not_applicable"] | None = None
    notes: str | None = None
    file_url: str | None = None


class PPAPElementResponse(BaseModel):
    element_id: uuid.UUID
    submission_id: uuid.UUID
    element_no: int
    element_name: str
    required: bool
    status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    file_url: str | None
    notes: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class PPAPResponse(BaseModel):
    submission_id: uuid.UUID
    ppap_no: str
    supplier_id: uuid.UUID
    supplier_name: str | None = None
    supplier_no: str | None = None
    part_no: str
    part_name: str
    submission_level: int
    submission_date: date | None
    customer_name: str | None
    product_line_code: str | None
    status: str
    revision: int
    rejection_reason: str | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    notes: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    elements: list[PPAPElementResponse]

    model_config = {"from_attributes": True}


class PPAPListResponse(BaseModel):
    items: list[PPAPResponse]
    total: int
    page: int
    page_size: int


class PPAPTransitionRequest(BaseModel):
    action: Literal["submit", "approve", "reject", "resubmit"]
    rejection_reason: str | None = None
