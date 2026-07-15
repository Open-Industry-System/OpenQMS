"""Pydantic schemas for US-E2E-01.7 D8 doc update gate endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DeferRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    owner_id: str
    deadline: str  # ISO date YYYY-MM-DD


class WaiverItemRequest(BaseModel):
    """One blocked_modify keypoint to waive (CP item_id absent from latest)."""
    doc_type: str = Field(..., pattern="^control_plan$")
    doc_id: str
    target_key: str = Field(..., min_length=1)
    field: str = Field(..., min_length=1)


class WaiverRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    items: list[WaiverItemRequest] = Field(..., min_length=1)


class DocGateDecisionResponse(BaseModel):
    decision: str | None = None
    no_affected_confirmed: bool = False
    version_snapshot: list = []
    revision: int | None = None
    defer_reason: str | None = None
    defer_owner: str | None = None
    defer_deadline: str | None = None
    waiver_reason: str | None = None
    waiver_items: list | None = None
    decided_at: str | None = None
