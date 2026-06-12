from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class HeatmapCell(BaseModel):
    key: str
    value: Optional[float] = None
    risk_index: Optional[float] = None
    level: Optional[str] = None
    diff: Optional[float] = None
    source: str


class HeatmapColumn(BaseModel):
    key: str
    label: str
    type: str  # "score" | "percent" | "number" | "count" | "risk"
    polarity: str  # "higher_is_risk" | "lower_is_risk" | "neutral_exposure"


class HeatmapRow(BaseModel):
    supplier_id: UUID
    supplier_name: str
    cells: list[HeatmapCell]


class HeatmapResponse(BaseModel):
    period: str
    prev_period: Optional[str] = None
    product_line_code: Optional[str] = None
    columns: list[HeatmapColumn]
    rows: list[HeatmapRow]


class TimelineResponse(BaseModel):
    periods: list[str]
    current_period: str
    supplier_count: int


class DimensionDetail(BaseModel):
    raw_value: Optional[float] = None
    risk_index: Optional[float] = None
    polarity: str
    source: str


class SupplierDimensionTrend(BaseModel):
    period: str
    risk_score: float
    quality_score: float
    delivery_score: float
    compliance_score: float


class SupplierDetailResponse(BaseModel):
    supplier_id: UUID
    supplier_name: str
    product_line_code: Optional[str] = None
    period: str
    dimensions: dict[str, DimensionDetail]
    trend: list[SupplierDimensionTrend]


class ComparisonSupplier(BaseModel):
    supplier_id: UUID
    supplier_name: str
    dimensions: dict[str, DimensionDetail]


class ComparisonResponse(BaseModel):
    period: str
    suppliers: list[ComparisonSupplier]


class SnapshotGenerateResponse(BaseModel):
    snapshot_count: int
    period: str


class SupplierCompareRequest(BaseModel):
    supplier_ids: list[UUID]