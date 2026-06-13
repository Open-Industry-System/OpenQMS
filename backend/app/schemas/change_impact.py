import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AffectedNode(BaseModel):
    node_id: str
    node_type: str
    name: str
    path: list[str]
    impact_type: str  # "upstream" | "downstream" | "direct"
    hop_distance: int
    risk_change: dict | None


class ImpactSummary(BaseModel):
    total_affected: int
    failure_modes_affected: int
    controls_affected: int
    ap_upgraded_count: int
    max_hop_distance: int


class ChangeImpactResult(BaseModel):
    """Repository 返回的纯分析结果，不含评分（评分由 Service 单点计算）"""
    affected_nodes: list[AffectedNode]
    summary: ImpactSummary


class ChangeImpactAnalyzeRequest(BaseModel):
    fmea_id: uuid.UUID
    node_id: str
    node_type: str
    node_name: str
    change_type: Literal["attribute", "structural"]
    field_name: str | None = None
    new_value: str | None = None


class ChangeImpactAnalysisResponse(BaseModel):
    id: uuid.UUID
    fmea_id: uuid.UUID
    product_line_code: str
    node_id: str
    node_type: str
    node_name: str
    change_type: str
    field_name: str | None
    old_value: str | None
    new_value: str | None
    scope: str
    status: str
    impact_score: int
    impact_result: ChangeImpactResult
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
