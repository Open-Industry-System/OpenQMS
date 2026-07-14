"""Pydantic schemas for US-E2E-01.7 D8 doc update gate endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DeferRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    owner_id: str
    deadline: str  # ISO date YYYY-MM-DD


class DocGateDecisionResponse(BaseModel):
    decision: str | None = None
    no_affected_confirmed: bool = False
    version_snapshot: list = []
    revision: int | None = None
    defer_reason: str | None = None
    defer_owner: str | None = None
    defer_deadline: str | None = None
    decided_at: str | None = None
