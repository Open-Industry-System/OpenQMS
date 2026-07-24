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

    # When the body is the current (done) artifact but a newer failed/superseded
    # attempt exists (is_current=false), these carry that attempt's status/error so
    # the UI can surface "最近一次重试失败" without losing the still-valid current data.
    # Populated by the GET endpoint; None when there is no newer failed attempt.
    latest_attempt_status: Literal["done", "failed", "superseded"] | None = None
    latest_attempt_error: str | None = None

    model_config = {"from_attributes": True}


class D3ReportRunningResponse(BaseModel):
    """Response body for POST /d3/report when a report is already running."""

    report_id: uuid.UUID
    status: Literal["running"]


class ProvenanceEntry(BaseModel):
    """Provenance entry for an advice item."""

    source_type: str  # inventory, shipment, iqc, spc, report
    snapshot_id: uuid.UUID | None = None
    record_key: str  # Always non-null
    stage: str = "llm_advice"


class D3AdviceItem(BaseModel):
    """Single advice item with provenance."""

    advice_id: uuid.UUID
    advice_type: str  # recall, isolate, notify_customer, strict_inspection, alternative
    advice_text: str
    source_provenance: list[ProvenanceEntry]
    target_batch_refs: list[str] | None = None
    adoption_status: str | None = None  # From capa_d3_advice_adoption if exists


class D3AdviceRunningResponse(BaseModel):
    """Response body for POST /d3/advice when generation is already running."""

    generation_id: uuid.UUID
    status: Literal["running"]


class D3AdviceResponse(BaseModel):
    """Response body for POST/GET /d3/advice.

    `status` distinguishes a successful "done" generation (advice may be empty
    if the LLM returned no usable items) from a "failed" generation (LLM error,
    schema mismatch, or all-provenance-mapping-failed). `error` carries the
    failure code when status is "failed".
    """

    advice: list[D3AdviceItem]
    status: Literal["done", "failed"] = "done"
    error: str | None = None
    # When `status` reflects the current (done) generation but a newer failed
    # attempt exists (is_current=false), these carry that attempt's status/error so
    # the UI can surface "最近一次重试失败" without losing the still-valid current advice.
    latest_attempt_status: Literal["done", "failed"] | None = None
    latest_attempt_error: str | None = None


class D3AdviceRequest(BaseModel):
    """Request body for POST /d3/advice (empty - no parameters needed)."""

    pass


class D3DecisionRequest(BaseModel):
    """Request body for POST /d3/advice/{advice_id}/decision."""

    decision: Literal["adopted", "rejected"]
    adopted_text: str | None = None


class D3AdoptionResponse(BaseModel):
    """Response item for GET /d3/adoptions."""

    adoption_id: uuid.UUID
    advice_id: uuid.UUID
    factory_id: uuid.UUID
    decision: str
    adopted_text: str | None
    advice_type: str
    source_provenance: list
    decided_by: uuid.UUID
    decided_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class D3ExecutionRequest(BaseModel):
    """Request body for POST /d3/execution."""

    source: Literal["manual", "adopted"]
    advice_id: uuid.UUID | None = None
    measure_text: str
    result_status: Literal["completed", "in_progress", "pending", "failed"] = "in_progress"
    evidence_refs: list[dict] | None = None


class D3ExecutionUpdateRequest(BaseModel):
    """Request body for PATCH /d3/execution/{id}."""

    result_status: Literal["completed", "in_progress", "pending", "failed"] | None = None
    measure_text: str | None = None
    evidence_refs: list[dict] | None = None


class D3ExecutionResponse(BaseModel):
    """Response body for POST/PATCH /d3/execution."""

    execution_id: uuid.UUID
    source: str
    advice_id: uuid.UUID | None = None
    generation_id: uuid.UUID | None = None
    result_status: str
    measure_text: str | None = None
    evidence_refs: list = []

    model_config = {"from_attributes": True}
