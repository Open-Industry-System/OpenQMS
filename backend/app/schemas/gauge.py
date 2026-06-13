import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class GaugeCreate(BaseModel):
    gauge_no: str
    name: str
    model: str | None = None
    manufacturer: str | None = None
    resolution: float | None = None
    measuring_range: str | None = None
    department: str | None = None
    location: str | None = None
    calibration_cycle_days: int | None = None
    next_calibration_date: date | None = None

    @field_validator("gauge_no", "name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class GaugeUpdate(BaseModel):
    gauge_no: str | None = None
    name: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    resolution: float | None = None
    measuring_range: str | None = None
    department: str | None = None
    location: str | None = None
    status: str | None = None
    calibration_cycle_days: int | None = None
    next_calibration_date: date | None = None

    @field_validator("gauge_no", "name")
    @classmethod
    def not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("active", "inactive", "calibrating", "scrapped"):
            raise ValueError("status must be active, inactive, calibrating, or scrapped")
        return v


class GaugeResponse(BaseModel):
    gauge_id: uuid.UUID
    gauge_no: str
    name: str
    model: str | None
    manufacturer: str | None
    resolution: float | None
    measuring_range: str | None
    department: str | None
    location: str | None
    status: str
    calibration_cycle_days: int | None
    next_calibration_date: date | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GaugeListResponse(BaseModel):
    items: list[GaugeResponse]
    total: int
    page: int
    page_size: int


class GaugeCalibrationCreate(BaseModel):
    calibration_date: date
    result: str
    certificate_no: str | None = None
    calibrated_by: str | None = None
    notes: str | None = None
    next_calibration_date: date | None = None

    @field_validator("result")
    @classmethod
    def validate_result(cls, v: str) -> str:
        if v not in ("pass", "fail"):
            raise ValueError('result must be "pass" or "fail"')
        return v


class GaugeCalibrationResponse(BaseModel):
    calibration_id: uuid.UUID
    gauge_id: uuid.UUID
    calibration_date: date
    result: str
    certificate_no: str | None
    calibrated_by: str | None
    notes: str | None
    next_calibration_date: date | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GaugeCalibrationListResponse(BaseModel):
    items: list[GaugeCalibrationResponse]
