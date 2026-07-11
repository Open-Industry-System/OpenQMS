"""Pydantic schemas for D3 containment API (US-E2E-01.1 Task 6)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class D3ImportRequest(BaseModel):
    """Request body for POST /d3/import."""

    snapshot_types: list[str] = ["inventory", "shipment", "iqc", "spc"]


class D3SnapshotSummary(BaseModel):
    """Snapshot summary returned inside D3ImportResponse."""

    snapshot_id: uuid.UUID
    snapshot_type: str
    record_count: int


class D3ImportResponse(BaseModel):
    """Response body for POST /d3/import."""

    run_id: uuid.UUID
    snapshots: list[D3SnapshotSummary]
    report_status: Literal["done", "failed", "blocked", "superseded"]
    report_id: uuid.UUID | None = None
    report_error: str | None = None


class D3RunResponse(BaseModel):
    """Response body for GET /d3/runs items."""

    run_id: uuid.UUID
    capa_id: uuid.UUID
    factory_id: uuid.UUID
    is_current: bool
    status: str
    imported_types: list
    analysis_context: dict
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class D3SnapshotResponse(BaseModel):
    """Response body for GET /d3/snapshots items."""

    snapshot_id: uuid.UUID
    run_id: uuid.UUID
    factory_id: uuid.UUID
    snapshot_type: str
    payload: list
    record_count: int
    imported_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class D3ReportResponse(BaseModel):
    """Response body for GET /d3/report and POST /d3/report (done/failed/superseded)."""

    report_id: uuid.UUID
    run_id: uuid.UUID
    factory_id: uuid.UUID
    is_current: bool
    status: Literal["running", "done", "failed", "superseded"]
    risk_level: str | None
    risk_floor: str | None
    risk_explanation: str | None
    batches: list | None
    impact_qty: dict | list | None
    customer_impact: list | None
    time_window: dict | None
    llm_available: bool
    model: str | None
    stage_runs: list | None
    prompt_stats: dict | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class D3ReportRunningResponse(BaseModel):
    """Response body for POST /d3/report when a report is already running."""

    report_id: uuid.UUID
    status: Literal["running"]


class D3AdviceRequest(BaseModel):
    """Placeholder for Task 8 advice generation request."""

    pass


class D3AdviceResponse(BaseModel):
    """Placeholder for Task 8 advice generation response."""

    pass
