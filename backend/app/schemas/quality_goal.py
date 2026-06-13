import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class QualityGoalCreate(BaseModel):
    parent_id: uuid.UUID | None = None
    level: int
    product_line_code: str | None = None
    name: str
    target_value: str
    unit: str
    period: str
    owner_id: uuid.UUID
    description: str | None = None

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: int) -> int:
        if v not in (1, 2, 3):
            raise ValueError("level must be 1, 2, or 3")
        return v

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        if v not in ("月度", "季度", "年度"):
            raise ValueError('period must be one of "月度", "季度", "年度"')
        return v


class QualityGoalUpdate(BaseModel):
    name: str | None = None
    target_value: str | None = None
    actual_value: str | None = None
    unit: str | None = None
    period: str | None = None
    owner_id: uuid.UUID | None = None
    description: str | None = None

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("月度", "季度", "年度"):
            raise ValueError('period must be one of "月度", "季度", "年度"')
        return v


class QualityGoalResponse(BaseModel):
    goal_id: uuid.UUID
    doc_no: str
    parent_id: uuid.UUID | None
    level: int
    product_line_code: str | None
    name: str
    target_value: str
    actual_value: str | None
    unit: str
    period: str
    owner_id: uuid.UUID
    status: str
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    reject_reason: str | None
    description: str | None
    data_source_formula: str | None = None
    factory_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QualityGoalListResponse(BaseModel):
    items: list[QualityGoalResponse]
    total: int
    page: int
    page_size: int


class QualityGoalRejectRequest(BaseModel):
    reject_reason: str
