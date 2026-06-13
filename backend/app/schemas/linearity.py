import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class LinearityStudyCreate(BaseModel):
    title: str
    gauge_id: uuid.UUID | None = None
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None = None
    unit: str | None = None
    tolerance_upper: float | None = None
    tolerance_lower: float | None = None
    sample_size_per_reference: int = 5
    study_date: date | None = None

    @field_validator("title", "characteristic_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class LinearityStudyUpdate(BaseModel):
    title: str | None = None
    gauge_id: uuid.UUID | None = None
    characteristic_name: str | None = None
    spc_characteristic_id: uuid.UUID | None = None
    unit: str | None = None
    tolerance_upper: float | None = None
    tolerance_lower: float | None = None
    sample_size_per_reference: int | None = None
    study_date: date | None = None


class LinearityStudyResponse(BaseModel):
    study_id: uuid.UUID
    study_no: str
    title: str
    gauge_id: uuid.UUID | None
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None
    unit: str | None
    tolerance_upper: float | None
    tolerance_lower: float | None
    sample_size_per_reference: int
    status: str
    study_date: date | None
    accepted_by: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LinearityStudyListResponse(BaseModel):
    items: list[LinearityStudyResponse]
    total: int
    page: int
    page_size: int


class LinearityMeasurementUpsert(BaseModel):
    reference_value: float
    measured_value: float
    sequence_no: int


class LinearityMeasurementBulkUpsert(BaseModel):
    measurements: list[LinearityMeasurementUpsert]


class LinearityResultResponse(BaseModel):
    result_id: uuid.UUID
    study_id: uuid.UUID
    slope: float
    intercept: float
    r_squared: float
    linearity: float
    linearity_percent: float | None
    bias_at_lower: float | None
    bias_at_upper: float | None
    conclusion: str
    created_at: datetime

    model_config = {"from_attributes": True}
