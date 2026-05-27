import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class APQPProjectCreate(BaseModel):
    project_name: str
    product_name: str
    product_line_code: str
    customer_name: str | None = None
    description: str | None = None
    target_sop_date: date | None = None
    team_members: list[dict] | None = None
    dfmea_id: uuid.UUID | None = None
    pfmea_id: uuid.UUID | None = None
    control_plan_id: uuid.UUID | None = None
    ppap_submission_id: uuid.UUID | None = None


class APQPProjectUpdate(BaseModel):
    project_name: str | None = None
    product_name: str | None = None
    product_line_code: str | None = None
    customer_name: str | None = None
    description: str | None = None
    target_sop_date: date | None = None
    team_members: list[dict] | None = None
    dfmea_id: uuid.UUID | None = None
    pfmea_id: uuid.UUID | None = None
    control_plan_id: uuid.UUID | None = None
    ppap_submission_id: uuid.UUID | None = None


class APQPProjectResponse(BaseModel):
    project_id: uuid.UUID
    project_code: str
    project_name: str
    product_name: str
    product_line_code: str
    customer_name: str | None = None
    description: str | None = None
    target_sop_date: date | None = None
    team_members: list | None = None

    current_phase: int
    phase_name: str
    phase_status: str | None = None
    project_status: str

    phase_1_completed_at: datetime | None = None
    phase_2_completed_at: datetime | None = None
    phase_3_completed_at: datetime | None = None
    phase_4_completed_at: datetime | None = None
    phase_5_completed_at: datetime | None = None

    gate_approved_by: uuid.UUID | None = None
    gate_approved_by_name: str | None = None
    gate_approved_at: datetime | None = None
    gate_comments: str | None = None
    gate_history: list | None = None

    dfmea_id: uuid.UUID | None = None
    dfmea_document_no: str | None = None
    pfmea_id: uuid.UUID | None = None
    pfmea_document_no: str | None = None
    control_plan_id: uuid.UUID | None = None
    control_plan_document_no: str | None = None
    ppap_submission_id: uuid.UUID | None = None
    ppap_submission_part_no: str | None = None
    ppap_submission_part_name: str | None = None

    created_by: uuid.UUID
    created_by_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class APQPProjectListResponse(BaseModel):
    items: list[APQPProjectResponse]
    total: int
    page: int
    page_size: int


class APQPGateTransitionRequest(BaseModel):
    action: Literal["submit_gate", "approve_gate", "reject_gate", "cancel"]
    comments: str | None = None


class APQPProjectStatsResponse(BaseModel):
    total_projects: int
    active_count: int
    pending_approval_count: int
    completed_count: int
    cancelled_count: int
    overdue_count: int
    phase_distribution: dict[int, int]
