import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class BiasStudyCreate(BaseModel):
    title: str
    gauge_id: uuid.UUID | None = None
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None = None
    unit: str | None = None
    reference_value: float
    sample_size: int = 10
    study_date: date | None = None

    @field_validator("title", "characteristic_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class BiasStudyUpdate(BaseModel):
    title: str | None = None
    gauge_id: uuid.UUID | None = None
    characteristic_name: str | None = None
    spc_characteristic_id: uuid.UUID | None = None
    unit: str | None = None
    reference_value: float | None = None
    sample_size: int | None = None
    study_date: date | None = None


class BiasStudyResponse(BaseModel):
    study_id: uuid.UUID
    study_no: str
    title: str
    gauge_id: uuid.UUID | None
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None
    unit: str | None
    reference_value: float
    sample_size: int
    status: str
    study_date: date | None
    accepted_by: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BiasStudyListResponse(BaseModel):
    items: list[BiasStudyResponse]
    total: int
    page: int
    page_size: int


class BiasMeasurementUpsert(BaseModel):
    value: float
    sequence_no: int


class BiasMeasurementBulkUpsert(BaseModel):
    measurements: list[BiasMeasurementUpsert]


class BiasResultResponse(BaseModel):
    result_id: uuid.UUID
    study_id: uuid.UUID
    mean: float
    bias: float
    bias_percent: float | None
    std_dev: float
    t_statistic: float
    p_value: float
    lower_ci: float | None
    upper_ci: float | None
    conclusion: str
    created_at: datetime

    model_config = {"from_attributes": True}
