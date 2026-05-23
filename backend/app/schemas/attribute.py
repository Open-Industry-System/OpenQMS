import uuid
from datetime import datetime, date
from pydantic import BaseModel, field_validator


class AttributeStudyCreate(BaseModel):
    title: str
    gauge_id: uuid.UUID | None = None
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None = None
    method: str = "risk_analysis"
    sample_size: int = 50
    known_standard_count: int | None = None
    study_date: date | None = None

    @field_validator("title", "characteristic_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        if v not in ("risk_analysis", "signal_detection", "analytic"):
            raise ValueError('method must be risk_analysis, signal_detection, or analytic')
        return v


class AttributeStudyUpdate(BaseModel):
    title: str | None = None
    gauge_id: uuid.UUID | None = None
    characteristic_name: str | None = None
    spc_characteristic_id: uuid.UUID | None = None
    method: str | None = None
    sample_size: int | None = None
    known_standard_count: int | None = None
    study_date: date | None = None


class AttributeStudyResponse(BaseModel):
    study_id: uuid.UUID
    study_no: str
    title: str
    gauge_id: uuid.UUID | None
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None
    method: str
    sample_size: int
    known_standard_count: int | None
    status: str
    study_date: date | None
    accepted_by: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AttributeStudyListResponse(BaseModel):
    items: list[AttributeStudyResponse]
    total: int
    page: int
    page_size: int


class AttributeMeasurementUpsert(BaseModel):
    appraiser_name: str
    part_no: str
    known_standard: str
    appraiser_decision: str
    trial_no: int = 1


class AttributeMeasurementBulkUpsert(BaseModel):
    measurements: list[AttributeMeasurementUpsert]


class AttributeResultResponse(BaseModel):
    result_id: uuid.UUID
    study_id: uuid.UUID
    effectiveness: float
    miss_rate: float
    false_alarm_rate: float
    kappa_within: float | None
    kappa_vs_standard: float | None
    kappa_between: float | None
    conclusion: str
    created_at: datetime

    model_config = {"from_attributes": True}
