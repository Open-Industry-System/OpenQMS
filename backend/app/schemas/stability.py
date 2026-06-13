import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class StabilityStudyCreate(BaseModel):
    title: str
    gauge_id: uuid.UUID | None = None
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None = None
    unit: str | None = None
    reference_value: float | None = None
    subgroup_size: int = 5
    study_date: date | None = None

    @field_validator("title", "characteristic_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class StabilityStudyUpdate(BaseModel):
    title: str | None = None
    gauge_id: uuid.UUID | None = None
    characteristic_name: str | None = None
    spc_characteristic_id: uuid.UUID | None = None
    unit: str | None = None
    reference_value: float | None = None
    subgroup_size: int | None = None
    study_date: date | None = None


class StabilityStudyResponse(BaseModel):
    study_id: uuid.UUID
    study_no: str
    title: str
    gauge_id: uuid.UUID | None
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None
    unit: str | None
    reference_value: float | None
    subgroup_size: int
    status: str
    study_date: date | None
    accepted_by: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StabilityStudyListResponse(BaseModel):
    items: list[StabilityStudyResponse]
    total: int
    page: int
    page_size: int


class StabilityMeasurementUpsert(BaseModel):
    measurement_date: date
    sample_mean: float
    sample_range: float
    sequence_no: int


class StabilityMeasurementBulkUpsert(BaseModel):
    measurements: list[StabilityMeasurementUpsert]


class StabilityResultResponse(BaseModel):
    result_id: uuid.UUID
    study_id: uuid.UUID
    ucl_mean: float
    lcl_mean: float | None
    cl_mean: float
    ucl_range: float
    lcl_range: float | None
    cl_range: float
    cpk: float | None
    conclusion: str
    created_at: datetime

    model_config = {"from_attributes": True}
