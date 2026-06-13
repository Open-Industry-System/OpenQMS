import uuid
from datetime import date, datetime

from pydantic import BaseModel


class MsaStudyOverview(BaseModel):
    study_id: uuid.UUID
    study_no: str
    type: str
    title: str
    gauge_name: str | None
    status: str
    study_date: date | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MsaStudyOverviewListResponse(BaseModel):
    items: list[MsaStudyOverview]
    total: int
    page: int
    page_size: int


class MsaSpcCharacteristic(BaseModel):
    ic_id: uuid.UUID
    ic_code: str
    process_name: str
    characteristic_name: str
    unit: str | None
    spec_upper: float | None
    spec_lower: float | None

    model_config = {"from_attributes": True}
