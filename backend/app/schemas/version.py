"""Pydantic schemas for FMEA / Control Plan version management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# FMEA version schemas
# ---------------------------------------------------------------------------

class FMEAVersionListItem(BaseModel):
    version_id: uuid.UUID
    fmea_id: uuid.UUID
    major_no: int
    minor_no: int
    change_type: str | None = None
    change_summary: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FMEAVersionDetail(FMEAVersionListItem):
    snapshot: dict
    sha256_hash: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Control Plan version schemas
# ---------------------------------------------------------------------------

class ControlPlanVersionListItem(BaseModel):
    version_id: uuid.UUID
    cp_id: uuid.UUID
    major_no: int
    minor_no: int
    source_fmea_version_id: uuid.UUID | None = None
    change_type: str | None = None
    change_summary: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ControlPlanVersionDetail(ControlPlanVersionListItem):
    header_snapshot: dict
    items_snapshot: list[dict]
    sha256_hash: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Shared list response
# ---------------------------------------------------------------------------

class VersionListResponse(BaseModel):
    items: list[FMEAVersionListItem | ControlPlanVersionListItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ManualVersionCreate(BaseModel):
    change_summary: str | None = None


class RollbackRequest(BaseModel):
    reason: str


class RollbackResponse(BaseModel):
    version_id: uuid.UUID
    major_no: int
    minor_no: int
    change_type: str | None = None
    change_summary: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Diff schemas
# ---------------------------------------------------------------------------

class NodeChange(BaseModel):
    field: str
    old: Any = None
    new: Any = None


class ModifiedNode(BaseModel):
    node_id: str
    changes: list[NodeChange]
    impact_chain: list[str] = []


class FMEADiffResult(BaseModel):
    added_nodes: list[dict]
    deleted_nodes: list[dict]
    modified_nodes: list[ModifiedNode]


class CPItemChange(BaseModel):
    field: str
    old: Any = None
    new: Any = None


class CPItemDiff(BaseModel):
    item_id: str
    changes: list[CPItemChange]


class CPDiffResult(BaseModel):
    header_changes: list[CPItemChange]
    added_items: list[dict]
    deleted_items: list[dict]
    modified_items: list[CPItemDiff]


class DiffSummary(BaseModel):
    added_count: int
    deleted_count: int
    modified_count: int


class FMEACompareResponse(BaseModel):
    diff: FMEADiffResult
    summary: DiffSummary


class CPCompareResponse(BaseModel):
    diff: CPDiffResult
    summary: DiffSummary


# ---------------------------------------------------------------------------
# Verify response
# ---------------------------------------------------------------------------

class VerifyResponse(BaseModel):
    is_valid: bool
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Sync schemas
# ---------------------------------------------------------------------------

class SyncPreviewItem(BaseModel):
    item_id: str
    source_fmea_node_id: str
    step_no: str | None = None
    action: str
    current_value: dict | None = None
    fmea_new_value: dict | None = None
    merged_value: dict | None = None


class SyncSummary(BaseModel):
    add_count: int
    update_count: int
    delete_count: int


class SyncPreviewResponse(BaseModel):
    fmea_version: str
    items: list[SyncPreviewItem]
    summary: SyncSummary
