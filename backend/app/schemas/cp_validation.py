import uuid
from datetime import datetime
from pydantic import BaseModel


class ValidationFindingResponse(BaseModel):
    finding_id: uuid.UUID
    cp_id: uuid.UUID
    finding_hash: str
    rule_id: str
    severity: str
    category: str
    status: str
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationOccurrenceResponse(BaseModel):
    occurrence_id: uuid.UUID
    run_id: uuid.UUID
    finding_id: uuid.UUID
    cp_id: uuid.UUID
    validation_type: str
    title: str
    description: str | None = None
    affected_items: list = []
    fmea_node_ids: list = []
    suggestion: str | None = None
    suggestion_data: dict | None = None
    present: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationResultItem(BaseModel):
    """Joined occurrence + finding, returned by list endpoint."""
    occurrence_id: uuid.UUID
    run_id: uuid.UUID
    finding_id: uuid.UUID
    cp_id: uuid.UUID
    validation_type: str
    rule_id: str
    severity: str
    category: str
    title: str
    description: str | None = None
    affected_items: list = []
    fmea_node_ids: list = []
    suggestion: str | None = None
    suggestion_data: dict | None = None
    status: str
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    present: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationRunResponse(BaseModel):
    run_id: uuid.UUID
    cp_id: uuid.UUID
    trigger: str
    status: str
    rule_count: int
    error_count: int
    warning_count: int
    info_count: int
    started_at: datetime
    completed_at: datetime | None = None
    failed_rules: list = []
    created_by: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class ValidationSummaryResponse(BaseModel):
    run_id: uuid.UUID | None = None
    status: str | None = None
    total: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    open_count: int = 0
    resolved_count: int = 0
    rejected_count: int = 0


class ValidationResultsListResponse(BaseModel):
    items: list[ValidationResultItem]
    total: int
