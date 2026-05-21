import uuid
from datetime import date, datetime
from pydantic import BaseModel, field_validator


class AuditProgramCreate(BaseModel):
    program_year: int
    audit_type: str
    scope: str
    criteria: str

    @field_validator("audit_type")
    @classmethod
    def validate_audit_type(cls, v: str) -> str:
        if v not in ("system", "process", "product"):
            raise ValueError('audit_type must be one of "system", "process", "product"')
        return v


class AuditProgramUpdate(BaseModel):
    program_year: int | None = None
    audit_type: str | None = None
    scope: str | None = None
    criteria: str | None = None
    status: str | None = None

    @field_validator("audit_type")
    @classmethod
    def validate_audit_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("system", "process", "product"):
            raise ValueError('audit_type must be one of "system", "process", "product"')
        return v


class AuditProgramResponse(BaseModel):
    program_id: uuid.UUID
    program_year: int
    audit_type: str
    scope: str
    criteria: str
    status: str
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditProgramListResponse(BaseModel):
    items: list[AuditProgramResponse]
    total: int
    page: int
    page_size: int


class AuditPlanCreate(BaseModel):
    program_id: uuid.UUID
    audit_scope: str
    audit_criteria: str
    planned_date: date
    lead_auditor: uuid.UUID | None = None
    team_members: list | None = None
    checklist: list | None = None


class AuditPlanUpdate(BaseModel):
    audit_scope: str | None = None
    audit_criteria: str | None = None
    planned_date: date | None = None
    actual_date: date | None = None
    lead_auditor: uuid.UUID | None = None
    team_members: list | None = None
    checklist: list | None = None
    status: str | None = None


class AuditPlanResponse(BaseModel):
    audit_id: uuid.UUID
    program_id: uuid.UUID
    audit_scope: str
    audit_criteria: str
    planned_date: date
    actual_date: date | None
    lead_auditor: uuid.UUID | None
    team_members: list
    checklist: list
    status: str
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditPlanListResponse(BaseModel):
    items: list[AuditPlanResponse]
    total: int
    page: int
    page_size: int


class AuditFindingCreate(BaseModel):
    audit_id: uuid.UUID
    clause_ref: str | None = None
    finding_type: str
    description: str
    root_cause: str | None = None
    correction: str | None = None
    corrective_action: str | None = None
    due_date: date | None = None

    @field_validator("finding_type")
    @classmethod
    def validate_finding_type(cls, v: str) -> str:
        if v not in ("major_nc", "minor_nc", "ofi", "observation"):
            raise ValueError('finding_type must be one of "major_nc", "minor_nc", "ofi", "observation"')
        return v


class AuditFindingUpdate(BaseModel):
    clause_ref: str | None = None
    finding_type: str | None = None
    description: str | None = None
    root_cause: str | None = None
    correction: str | None = None
    corrective_action: str | None = None
    status: str | None = None
    due_date: date | None = None

    @field_validator("finding_type")
    @classmethod
    def validate_finding_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("major_nc", "minor_nc", "ofi", "observation"):
            raise ValueError('finding_type must be one of "major_nc", "minor_nc", "ofi", "observation"')
        return v


class AuditFindingResponse(BaseModel):
    finding_id: uuid.UUID
    audit_id: uuid.UUID
    clause_ref: str | None
    finding_type: str
    description: str
    root_cause: str | None
    correction: str | None
    corrective_action: str | None
    capa_ref_id: uuid.UUID | None
    status: str
    due_date: date | None
    closed_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditFindingListResponse(BaseModel):
    items: list[AuditFindingResponse]
    total: int
    page: int
    page_size: int


class AuditorInfoUpdate(BaseModel):
    is_auditor: bool
    qualifications: list[str]
    last_qualification_date: str | None = None


class AuditChecklistTemplate(BaseModel):
    audit_type: str
    name: str
    items: list[dict]


class AuditStatsResponse(BaseModel):
    program_count: int
    planned_count: int
    in_progress_count: int
    completed_count: int
    open_findings: int
    major_nc_count: int
