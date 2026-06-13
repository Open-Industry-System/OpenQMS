import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class GrrStudyCreate(BaseModel):
    title: str
    method: str = "average_range"
    gauge_id: uuid.UUID | None = None
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None = None
    unit: str | None = None
    tolerance_upper: float | None = None
    tolerance_lower: float | None = None
    reference_value: float | None = None
    appraiser_count: int = 3
    part_count: int = 10
    trial_count: int = 3
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
        if v not in ("average_range", "anova"):
            raise ValueError('method must be average_range or anova')
        return v


class GrrStudyUpdate(BaseModel):
    title: str | None = None
    method: str | None = None
    gauge_id: uuid.UUID | None = None
    characteristic_name: str | None = None
    spc_characteristic_id: uuid.UUID | None = None
    unit: str | None = None
    tolerance_upper: float | None = None
    tolerance_lower: float | None = None
    reference_value: float | None = None
    appraiser_count: int | None = None
    part_count: int | None = None
    trial_count: int | None = None
    study_date: date | None = None


class GrrStudyResponse(BaseModel):
    study_id: uuid.UUID
    study_no: str
    title: str
    method: str
    gauge_id: uuid.UUID | None
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None
    unit: str | None
    tolerance_upper: float | None
    tolerance_lower: float | None
    reference_value: float | None
    appraiser_count: int
    part_count: int
    trial_count: int
    status: str
    study_date: date | None
    accepted_by: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GrrStudyListResponse(BaseModel):
    items: list[GrrStudyResponse]
    total: int
    page: int
    page_size: int


class GrrMeasurementUpsert(BaseModel):
    appraiser_name: str
    part_no: str
    trial_no: int
    value: float


class GrrMeasurementBulkUpsert(BaseModel):
    measurements: list[GrrMeasurementUpsert]


class GrrResultResponse(BaseModel):
    result_id: uuid.UUID
    study_id: uuid.UUID
    ev: float
    av: float
    grr: float
    pv: float
    tv: float
    ndc: float
    grr_percent_tol: float
    grr_percent_tv: float
    ev_percent: float
    av_percent: float
    pv_percent: float
    conclusion: str
    created_at: datetime

    model_config = {"from_attributes": True}
