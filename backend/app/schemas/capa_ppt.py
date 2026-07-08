from datetime import datetime
from pydantic import BaseModel


class PptExportDetailResponse(BaseModel):
    export_id: str
    capa_id: str
    generated_at: datetime
    generated_by: str
    version: str
    review_status: str
    review_rounds: int
    review_report: dict | None
