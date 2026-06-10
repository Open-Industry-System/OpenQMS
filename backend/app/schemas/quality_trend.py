from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "insufficient_data"]


class QualityTrendEvidence(BaseModel):
    id: str
    label: str
    value: int | float
    trend: str
    severity: Literal["info", "warning", "critical", "none"]


class QualityTrendAction(BaseModel):
    priority: Literal["low", "medium", "high"]
    text: str


class QualityTrendMetadata(BaseModel):
    omitted_modules: list[str] = Field(default_factory=list)
    available_modules: list[str] = Field(default_factory=list)
    scope_description: str = ""
    selected_product_line: str | None = None


class QualityTrendSummary(BaseModel):
    risk_level: RiskLevel
    headline: str
    evidence: list[QualityTrendEvidence]
    actions: list[QualityTrendAction]
    data_window_days: int = 30
    generated_at: str
    evidence_hash: str
    scope_hash: str
    ai_available: bool
    metadata: QualityTrendMetadata = Field(default_factory=QualityTrendMetadata)


class QualityTrendInterpretation(BaseModel):
    summary: str
    possible_causes: list[str]
    impact_scope: list[str]
    recommended_actions: list[dict]
    evidence_refs: list[str]
    confidence: Literal["low", "medium", "high"]
    model: str
    evidence_hash: str
    scope_hash: str
    generated_at: str
    cached: bool = False
