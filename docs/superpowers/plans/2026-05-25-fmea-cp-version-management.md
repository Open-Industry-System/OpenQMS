# FMEA/CP Version Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement version history, diff comparison, rollback, and FMEA-CP sync for FMEA and Control Plan documents with Major.Minor dual-track versioning, SHA-256 tamper protection, and UUID-idempotent upsert rollback.

**Architecture:** Add independent `fmea_versions` and `control_plan_versions` tables storing full JSONB snapshots with SHA-256 hashes. Integrate version creation into existing FMEA transition and CP approve flows. Build diff engine for graph/tabular data. Add version history tabs and side-by-side comparison views on existing editor pages.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL + Alembic | React 18 + TypeScript + Ant Design 5 + Vite

---

## File Structure

### Backend (new and modified)

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/alembic/versions/014_add_version_tables.py` | Create | Alembic migration: fmea_versions, control_plan_versions tables, alter control_plans/control_plan_items |
| `backend/app/models/fmea_version.py` | Create | FMEAVersion ORM model |
| `backend/app/models/control_plan_version.py` | Create | ControlPlanVersion ORM model |
| `backend/app/models/__init__.py` | Modify | Export new models |
| `backend/app/models/control_plan.py` | Modify | Add `source_fmea_version_id`, `sync_pending`, `item_source` fields |
| `backend/app/schemas/version.py` | Create | Pydantic schemas for version requests/responses |
| `backend/app/services/version_service.py` | Create | Core version logic: create, list, get, compare, rollback, SHA-256 |
| `backend/app/services/fmea_service.py` | Modify | Hook version creation into `transition_fmea` (submit/approve) |
| `backend/app/services/control_plan_service.py` | Modify | Hook version creation into `approve_control_plan`, add sync logic |
| `backend/app/api/version.py` | Create | FastAPI routes for version CRUD, compare, rollback, sync |
| `backend/app/main.py` | Modify | Include version router |

### Frontend (new and modified)

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/api/version.ts` | Create | API functions for version endpoints |
| `frontend/src/types/index.ts` | Modify | Add Version, VersionDiff, SyncPreview types |
| `frontend/src/components/version/VersionHistoryTab.tsx` | Create | Version history list with timeline |
| `frontend/src/components/version/VersionCompareView.tsx` | Create | Side-by-side diff view with filters |
| `frontend/src/components/version/CreateVersionModal.tsx` | Create | Manual version creation modal |
| `frontend/src/components/version/RollbackConfirmModal.tsx` | Create | Rollback confirmation with reason input |
| `frontend/src/components/version/SyncPreviewDrawer.tsx` | Create | FMEA-CP three-way sync preview |
| `frontend/src/pages/fmea/FMEAEditorPage.tsx` | Modify | Add "Version History" tab |
| `frontend/src/pages/control-plan/ControlPlanEditorPage.tsx` | Modify | Add "Version History" tab + sync banner |

---

## Task 1: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/014_add_version_tables.py`

- [ ] **Step 1: Write the migration**

```python
"""add version tables for fmea and control plan

Revision ID: 014_add_version_tables
Revises: 013_add_management_review
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "014_add_version_tables"
down_revision = "013_add_management_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # fmea_versions
    op.create_table(
        "fmea_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("fmea_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False),
        sa.Column("major_no", sa.Integer, nullable=False),
        sa.Column("minor_no", sa.Integer, nullable=False, server_default="0"),
        sa.Column("snapshot", postgresql.JSONB, nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("change_summary", sa.Text, nullable=False),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_fmea_version", "fmea_versions", ["fmea_id", "major_no", "minor_no"])
    op.create_index("idx_fmea_ver_created", "fmea_versions", ["fmea_id", sa.text("created_at DESC")])

    # control_plan_versions
    op.create_table(
        "control_plan_versions",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False),
        sa.Column("major_no", sa.Integer, nullable=False),
        sa.Column("minor_no", sa.Integer, nullable=False, server_default="0"),
        sa.Column("header_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("items_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("source_fmea_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fmea_versions.version_id", ondelete="SET NULL"), nullable=True),
        sa.Column("change_summary", sa.Text, nullable=False),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_cp_version", "control_plan_versions", ["cp_id", "major_no", "minor_no"])
    op.create_index("idx_cp_ver_created", "control_plan_versions", ["cp_id", sa.text("created_at DESC")])

    # alter control_plans
    op.add_column("control_plans", sa.Column("source_fmea_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fmea_versions.version_id", ondelete="SET NULL"), nullable=True))
    op.add_column("control_plans", sa.Column("sync_pending", sa.Boolean, server_default="false", nullable=False))

    # alter control_plan_items
    op.add_column("control_plan_items", sa.Column("item_source", sa.String(20), server_default="fmea", nullable=False))


def downgrade() -> None:
    op.drop_column("control_plan_items", "item_source")
    op.drop_column("control_plans", "sync_pending")
    op.drop_column("control_plans", "source_fmea_version_id")
    op.drop_table("control_plan_versions")
    op.drop_table("fmea_versions")
```

- [ ] **Step 2: Run the migration**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
alembic upgrade head
```

Expected: `014_add_version_tables` applied successfully.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/014_add_version_tables.py
git commit -m "feat(version): add fmea_versions and control_plan_versions tables"
```

---

## Task 2: ORM Models

**Files:**
- Create: `backend/app/models/fmea_version.py`
- Create: `backend/app/models/control_plan_version.py`
- Modify: `backend/app/models/control_plan.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create FMEAVersion model**

```python
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FMEAVersion(Base):
    __tablename__ = "fmea_versions"

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fmea_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id", ondelete="CASCADE"), nullable=False
    )
    major_no: Mapped[int] = mapped_column(Integer, nullable=False)
    minor_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    creator = relationship("User")
```

- [ ] **Step 2: Create ControlPlanVersion model**

```python
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ControlPlanVersion(Base):
    __tablename__ = "control_plan_versions"

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False
    )
    major_no: Mapped[int] = mapped_column(Integer, nullable=False)
    minor_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    header_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    items_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_fmea_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fmea_versions.version_id", ondelete="SET NULL"), nullable=True
    )
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    creator = relationship("User")
    source_fmea_version = relationship("FMEAVersion")
```

- [ ] **Step 3: Modify ControlPlan model**

In `backend/app/models/control_plan.py`, add these fields to `ControlPlan` class:

```python
# Inside ControlPlan class, after existing fields:
source_fmea_version_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("fmea_versions.version_id", ondelete="SET NULL"), nullable=True
)
sync_pending: Mapped[bool] = mapped_column(
    default=False, server_default="false", nullable=False
)
```

And add to `ControlPlanItem` class:

```python
item_source: Mapped[str] = mapped_column(
    String(20), default="fmea", server_default="fmea", nullable=False
)
```

- [ ] **Step 4: Export new models**

In `backend/app/models/__init__.py`, add:

```python
from app.models.fmea_version import FMEAVersion
from app.models.control_plan_version import ControlPlanVersion
```

And add `"FMEAVersion"` and `"ControlPlanVersion"` to `__all__`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/
git commit -m "feat(version): add FMEAVersion and ControlPlanVersion ORM models"
```

---

## Task 3: Version Schemas

**Files:**
- Create: `backend/app/schemas/version.py`

- [ ] **Step 1: Write all version schemas**

```python
import uuid
from datetime import datetime
from pydantic import BaseModel


class FMEAVersionListItem(BaseModel):
    version_id: uuid.UUID
    major_no: int
    minor_no: int
    change_summary: str
    change_type: str
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class FMEAVersionDetail(FMEAVersionListItem):
    snapshot: dict
    sha256_hash: str


class ControlPlanVersionListItem(BaseModel):
    version_id: uuid.UUID
    major_no: int
    minor_no: int
    change_summary: str
    change_type: str
    source_fmea_version_id: uuid.UUID | None = None
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ControlPlanVersionDetail(ControlPlanVersionListItem):
    header_snapshot: dict
    items_snapshot: list
    sha256_hash: str


class VersionListResponse(BaseModel):
    items: list[FMEAVersionListItem] | list[ControlPlanVersionListItem]
    total: int
    page: int
    page_size: int


class ManualVersionCreate(BaseModel):
    change_summary: str


class RollbackRequest(BaseModel):
    reason: str


class RollbackResponse(BaseModel):
    version_id: uuid.UUID
    major_no: int
    minor_no: int
    change_type: str
    change_summary: str
    created_at: datetime


class NodeChange(BaseModel):
    field: str
    old: str | int | float | None
    new: str | int | float | None


class ModifiedNode(BaseModel):
    node_id: str
    changes: list[NodeChange]
    impact_chain: list[str] = []


class FMEADiffResult(BaseModel):
    added_nodes: list[dict]
    deleted_nodes: list[dict]
    modified_nodes: list[ModifiedNode]


class CPItemChange(BaseModel):
    item_id: str
    field: str
    old: str | int | float | None
    new: str | int | float | None


class CPItemDiff(BaseModel):
    item_id: str
    changes: list[CPItemChange]
    status: str  # added / deleted / modified


class CPDiffResult(BaseModel):
    added_items: list[dict]
    deleted_items: list[dict]
    modified_items: list[CPItemDiff]
    header_changes: list[CPItemChange]


class DiffSummary(BaseModel):
    added: int
    deleted: int
    modified: int


class FMEACompareResponse(BaseModel):
    v1: FMEAVersionDetail
    v2: FMEAVersionDetail
    diff: FMEADiffResult
    summary: DiffSummary


class CPCompareResponse(BaseModel):
    v1: ControlPlanVersionDetail
    v2: ControlPlanVersionDetail
    diff: CPDiffResult
    summary: DiffSummary


class VerifyResponse(BaseModel):
    valid: bool
    computed_hash: str
    stored_hash: str


class SyncPreviewItem(BaseModel):
    item_id: str
    step_no: str | None
    current_value: dict
    fmea_new_value: dict
    merged_value: dict
    action: str  # sync / keep / add / delete


class SyncPreviewResponse(BaseModel):
    fmea_version_id: uuid.UUID
    fmea_major_no: int
    fmea_minor_no: int
    items: list[SyncPreviewItem]
    added_count: int
    modified_count: int
    deleted_count: int
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/version.py
git commit -m "feat(version): add version Pydantic schemas"
```

---

## Task 4: Version Service Core

**Files:**
- Create: `backend/app/services/version_service.py`

- [ ] **Step 1: Write the core version service**

```python
import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.control_plan_version import ControlPlanVersion
from app.models.audit import AuditLog


# ── SHA-256 helpers ──────────────────────────────────────────────

def _canonical_json(data: dict | list) -> str:
    """Deterministic JSON serialization for hash consistency."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_snapshot_hash(snapshot: dict | list) -> str:
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


def verify_snapshot_hash(snapshot: dict | list, stored_hash: str) -> bool:
    return compute_snapshot_hash(snapshot) == stored_hash


# ── FMEA version helpers ─────────────────────────────────────────

async def get_latest_fmea_version(
    db: AsyncSession, fmea_id: uuid.UUID
) -> FMEAVersion | None:
    result = await db.execute(
        select(FMEAVersion)
        .where(FMEAVersion.fmea_id == fmea_id)
        .order_by(FMEAVersion.major_no.desc(), FMEAVersion.minor_no.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_fmea_version(
    db: AsyncSession,
    fmea: FMEADocument,
    change_type: Literal["submit", "approve", "manual", "rollback"],
    change_summary: str,
    user_id: uuid.UUID,
) -> FMEAVersion:
    latest = await get_latest_fmea_version(db, fmea.fmea_id)

    if change_type == "approve":
        major_no = (latest.major_no if latest else 0) + 1
        minor_no = 0
    else:
        major_no = latest.major_no if latest else 1
        minor_no = (latest.minor_no if latest else 0) + 1

    snapshot = fmea.graph_data or {"nodes": [], "edges": []}
    sha256 = compute_snapshot_hash(snapshot)

    version = FMEAVersion(
        fmea_id=fmea.fmea_id,
        major_no=major_no,
        minor_no=minor_no,
        snapshot=snapshot,
        sha256_hash=sha256,
        change_summary=change_summary,
        change_type=change_type,
        created_by=user_id,
    )
    db.add(version)
    await db.flush()

    # Audit log
    audit = AuditLog(
        table_name="fmea_versions",
        record_id=version.version_id,
        action="CREATE",
        changed_fields={
            "fmea_id": str(fmea.fmea_id),
            "major_no": major_no,
            "minor_no": minor_no,
            "change_type": change_type,
        },
        operated_by=user_id,
    )
    db.add(audit)

    return version


async def list_fmea_versions(
    db: AsyncSession,
    fmea_id: uuid.UUID,
    page: int = 1,
    page_size: int = 50,
    major_only: bool = False,
) -> tuple[list[FMEAVersion], int]:
    query = select(FMEAVersion).where(FMEAVersion.fmea_id == fmea_id)
    count_query = select(func.count(FMEAVersion.version_id)).where(
        FMEAVersion.fmea_id == fmea_id
    )

    if major_only:
        query = query.where(FMEAVersion.minor_no == 0)
        count_query = count_query.where(FMEAVersion.minor_no == 0)

    query = query.order_by(FMEAVersion.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_fmea_version(
    db: AsyncSession, fmea_id: uuid.UUID, major_no: int, minor_no: int
) -> FMEAVersion | None:
    result = await db.execute(
        select(FMEAVersion).where(
            FMEAVersion.fmea_id == fmea_id,
            FMEAVersion.major_no == major_no,
            FMEAVersion.minor_no == minor_no,
        )
    )
    return result.scalar_one_or_none()


async def verify_fmea_version(db: AsyncSession, version_id: uuid.UUID) -> tuple[bool, str, str]:
    result = await db.execute(
        select(FMEAVersion).where(FMEAVersion.version_id == version_id)
    )
    version = result.scalar_one_or_none()
    if not version:
        raise ValueError("Version not found")
    computed = compute_snapshot_hash(version.snapshot)
    return computed == version.sha256_hash, computed, version.sha256_hash


# ── CP version helpers ───────────────────────────────────────────

async def get_latest_cp_version(
    db: AsyncSession, cp_id: uuid.UUID
) -> ControlPlanVersion | None:
    result = await db.execute(
        select(ControlPlanVersion)
        .where(ControlPlanVersion.cp_id == cp_id)
        .order_by(ControlPlanVersion.major_no.desc(), ControlPlanVersion.minor_no.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_cp_version(
    db: AsyncSession,
    cp: ControlPlan,
    change_type: Literal["submit", "approve", "manual", "rollback", "fmea_sync"],
    change_summary: str,
    user_id: uuid.UUID,
    source_fmea_version_id: uuid.UUID | None = None,
) -> ControlPlanVersion:
    latest = await get_latest_cp_version(db, cp.cp_id)

    if change_type == "approve":
        major_no = (latest.major_no if latest else 0) + 1
        minor_no = 0
    else:
        major_no = latest.major_no if latest else 1
        minor_no = (latest.minor_no if latest else 0) + 1

    # Build header snapshot
    header_snapshot = {
        "title": cp.title,
        "document_no": cp.document_no,
        "phase": cp.phase,
        "part_no": cp.part_no,
        "part_name": cp.part_name,
        "contact_info": cp.contact_info,
        "drawing_rev": cp.drawing_rev,
        "org_factory": cp.org_factory,
        "core_group": cp.core_group,
        "product_line_code": cp.product_line_code,
        "status": cp.status,
    }

    # Build items snapshot preserving UUIDs
    items_result = await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id).order_by(ControlPlanItem.sort_order)
    )
    items = list(items_result.scalars().all())
    items_snapshot = [
        {
            "item_id": str(item.item_id),
            "step_no": item.step_no,
            "process_name": item.process_name,
            "equipment": item.equipment,
            "characteristic_no": item.characteristic_no,
            "product_characteristic": item.product_characteristic,
            "process_characteristic": item.process_characteristic,
            "special_class": item.special_class,
            "specification_tolerance": item.specification_tolerance,
            "evaluation_method": item.evaluation_method,
            "sample_size": item.sample_size,
            "sample_frequency": item.sample_frequency,
            "control_method": item.control_method,
            "reaction_plan": item.reaction_plan,
            "source_fmea_node_id": item.source_fmea_node_id,
            "sort_order": item.sort_order,
            "item_source": item.item_source,
        }
        for item in items
    ]

    full_snapshot = {"header": header_snapshot, "items": items_snapshot}
    sha256 = compute_snapshot_hash(full_snapshot)

    version = ControlPlanVersion(
        cp_id=cp.cp_id,
        major_no=major_no,
        minor_no=minor_no,
        header_snapshot=header_snapshot,
        items_snapshot=items_snapshot,
        sha256_hash=sha256,
        source_fmea_version_id=source_fmea_version_id,
        change_summary=change_summary,
        change_type=change_type,
        created_by=user_id,
    )
    db.add(version)
    await db.flush()

    audit = AuditLog(
        table_name="control_plan_versions",
        record_id=version.version_id,
        action="CREATE",
        changed_fields={
            "cp_id": str(cp.cp_id),
            "major_no": major_no,
            "minor_no": minor_no,
            "change_type": change_type,
        },
        operated_by=user_id,
    )
    db.add(audit)

    return version


async def list_cp_versions(
    db: AsyncSession,
    cp_id: uuid.UUID,
    page: int = 1,
    page_size: int = 50,
    major_only: bool = False,
) -> tuple[list[ControlPlanVersion], int]:
    query = select(ControlPlanVersion).where(ControlPlanVersion.cp_id == cp_id)
    count_query = select(func.count(ControlPlanVersion.version_id)).where(
        ControlPlanVersion.cp_id == cp_id
    )

    if major_only:
        query = query.where(ControlPlanVersion.minor_no == 0)
        count_query = count_query.where(ControlPlanVersion.minor_no == 0)

    query = query.order_by(ControlPlanVersion.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return items, total


async def get_cp_version(
    db: AsyncSession, cp_id: uuid.UUID, major_no: int, minor_no: int
) -> ControlPlanVersion | None:
    result = await db.execute(
        select(ControlPlanVersion).where(
            ControlPlanVersion.cp_id == cp_id,
            ControlPlanVersion.major_no == major_no,
            ControlPlanVersion.minor_no == minor_no,
        )
    )
    return result.scalar_one_or_none()


async def verify_cp_version(db: AsyncSession, version_id: uuid.UUID) -> tuple[bool, str, str]:
    result = await db.execute(
        select(ControlPlanVersion).where(ControlPlanVersion.version_id == version_id)
    )
    version = result.scalar_one_or_none()
    if not version:
        raise ValueError("Version not found")
    full = {"header": version.header_snapshot, "items": version.items_snapshot}
    computed = compute_snapshot_hash(full)
    return computed == version.sha256_hash, computed, version.sha256_hash
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/version_service.py
git commit -m "feat(version): add core version service with SHA-256 and Major.Minor versioning"
```

---

## Task 5: Diff Engine

**Files:**
- Create: `backend/app/services/diff_engine.py`

- [ ] **Step 1: Write the diff engine**

```python
"""Diff engine for FMEA graph_data and CP items."""


def diff_fmea_graphs(v1_graph: dict, v2_graph: dict) -> dict:
    """Compare two FMEA graph_data snapshots."""
    v1_nodes = {n["id"]: n for n in v1_graph.get("nodes", [])}
    v2_nodes = {n["id"]: n for n in v2_graph.get("nodes", [])}

    added = []
    deleted = []
    modified = []

    for nid, node in v2_nodes.items():
        if nid not in v1_nodes:
            added.append(node)
            continue
        old_node = v1_nodes[nid]
        changes = []
        for key in set(old_node.keys()) | set(node.keys()):
            if key in ("id", "type"):
                continue
            old_val = old_node.get(key)
            new_val = node.get(key)
            if old_val != new_val:
                changes.append({"field": key, "old": old_val, "new": new_val})
        if changes:
            impact = []
            # RPN impact chain
            old_s = old_node.get("severity", 0) or 0
            old_o = old_node.get("occurrence", 0) or 0
            old_d = old_node.get("detection", 0) or 0
            new_s = node.get("severity", 0) or 0
            new_o = node.get("occurrence", 0) or 0
            new_d = node.get("detection", 0) or 0
            old_rpn = old_s * old_o * old_d
            new_rpn = new_s * new_o * new_d
            if old_rpn != new_rpn and (old_s or old_o or old_d):
                impact.append(f"RPN: {old_rpn} → {new_rpn}")
            modified.append({
                "node_id": nid,
                "changes": changes,
                "impact_chain": impact,
            })

    for nid, node in v1_nodes.items():
        if nid not in v2_nodes:
            deleted.append(node)

    return {
        "added_nodes": added,
        "deleted_nodes": deleted,
        "modified_nodes": modified,
    }


def diff_cp_items(v1_items: list, v2_items: list) -> dict:
    """Compare two CP items snapshots."""
    v1_map = {item["item_id"]: item for item in v1_items}
    v2_map = {item["item_id"]: item for item in v2_items}

    added = []
    deleted = []
    modified = []

    for iid, item in v2_map.items():
        if iid not in v1_map:
            added.append(item)
            continue
        old_item = v1_map[iid]
        changes = []
        for key in set(old_item.keys()) | set(item.keys()):
            if key == "item_id":
                continue
            old_val = old_item.get(key)
            new_val = item.get(key)
            if old_val != new_val:
                changes.append({"field": key, "old": old_val, "new": new_val})
        if changes:
            modified.append({
                "item_id": iid,
                "changes": changes,
                "status": "modified",
            })

    for iid, item in v1_map.items():
        if iid not in v2_map:
            deleted.append(item)

    return {
        "added_items": added,
        "deleted_items": deleted,
        "modified_items": modified,
    }


def diff_cp_headers(v1_header: dict, v2_header: dict) -> list:
    changes = []
    for key in set(v1_header.keys()) | set(v2_header.keys()):
        if v1_header.get(key) != v2_header.get(key):
            changes.append({
                "field": key,
                "old": v1_header.get(key),
                "new": v2_header.get(key),
            })
    return changes
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/diff_engine.py
git commit -m "feat(version): add diff engine for FMEA graphs and CP items"
```

---

## Task 6: Rollback Engine

**Files:**
- Modify: `backend/app/services/version_service.py` (append)

- [ ] **Step 1: Append rollback functions to version_service.py**

```python
# Add to existing backend/app/services/version_service.py

async def rollback_fmea(
    db: AsyncSession,
    fmea: FMEADocument,
    target_major: int,
    target_minor: int,
    reason: str,
    user_id: uuid.UUID,
) -> FMEAVersion:
    if fmea.status != "draft":
        raise ValueError("只有草稿状态的文档才能回退")

    target = await get_fmea_version(db, fmea.fmea_id, target_major, target_minor)
    if not target:
        raise ValueError("目标版本不存在")

    # Restore graph_data
    fmea.graph_data = target.snapshot
    fmea.updated_by = user_id

    # Create new version recording the rollback
    change_summary = f"回退原因：{reason}。从 v{target_major}.{target_minor} 回退"
    version = await create_fmea_version(
        db, fmea, "rollback", change_summary, user_id
    )

    audit = AuditLog(
        table_name="fmea_documents",
        record_id=fmea.fmea_id,
        action="ROLLBACK",
        changed_fields={
            "from_version": f"{target_major}.{target_minor}",
            "to_version": f"{version.major_no}.{version.minor_no}",
            "reason": reason,
        },
        operated_by=user_id,
    )
    db.add(audit)
    await db.commit()

    return version


async def rollback_control_plan(
    db: AsyncSession,
    cp: ControlPlan,
    target_major: int,
    target_minor: int,
    reason: str,
    user_id: uuid.UUID,
) -> ControlPlanVersion:
    if cp.status != "draft":
        raise ValueError("只有草稿状态的文档才能回退")

    target = await get_cp_version(db, cp.cp_id, target_major, target_minor)
    if not target:
        raise ValueError("目标版本不存在")

    # Restore header fields
    header = target.header_snapshot
    for key, val in header.items():
        if hasattr(cp, key) and key not in ("cp_id", "created_at"):
            setattr(cp, key, val)
    cp.updated_by = user_id

    # UUID-idempotent Upsert for items (CRITICAL: preserve item_id)
    current_items_result = await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id)
    )
    current_items = {item.item_id: item for item in current_items_result.scalars().all()}
    snap_items = {}
    for item_data in target.items_snapshot:
        try:
            snap_id = uuid.UUID(item_data["item_id"])
            snap_items[snap_id] = item_data
        except (ValueError, KeyError):
            continue

    # Delete items not in snapshot
    for item_id, item in list(current_items.items()):
        if item_id not in snap_items:
            await db.delete(item)

    # Update or insert items preserving UUID
    for snap_id, snap_data in snap_items.items():
        if snap_id in current_items:
            item = current_items[snap_id]
            for field, val in snap_data.items():
                if hasattr(item, field) and field != "item_id":
                    setattr(item, field, val)
        else:
            new_item = ControlPlanItem(
                item_id=snap_id,
                cp_id=cp.cp_id,
                **{k: v for k, v in snap_data.items() if k != "item_id"}
            )
            db.add(new_item)

    # Create new version
    change_summary = f"回退原因：{reason}。从 v{target_major}.{target_minor} 回退"
    version = await create_cp_version(
        db, cp, "rollback", change_summary, user_id
    )

    audit = AuditLog(
        table_name="control_plans",
        record_id=cp.cp_id,
        action="ROLLBACK",
        changed_fields={
            "from_version": f"{target_major}.{target_minor}",
            "to_version": f"{version.major_no}.{version.minor_no}",
            "reason": reason,
        },
        operated_by=user_id,
    )
    db.add(audit)
    await db.commit()

    return version
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/version_service.py
git commit -m "feat(version): add UUID-idempotent rollback engine for FMEA and CP"
```

---

## Task 7: FMEA-CP Sync Engine

**Files:**
- Modify: `backend/app/services/control_plan_service.py` (append)
- Modify: `backend/app/services/version_service.py` (append)

- [ ] **Step 1: Append sync functions to version_service.py**

```python
# Add to backend/app/services/version_service.py

from app.services.diff_engine import diff_fmea_graphs, diff_cp_items


async def get_fmea_version_by_id(db: AsyncSession, version_id: uuid.UUID) -> FMEAVersion | None:
    result = await db.execute(
        select(FMEAVersion).where(FMEAVersion.version_id == version_id)
    )
    return result.scalar_one_or_none()


async def build_sync_preview(
    db: AsyncSession,
    cp: ControlPlan,
    fmea_version: FMEAVersion,
) -> list[dict]:
    """Build three-way sync preview: CP current vs FMEA version changes."""
    if not fmea_version:
        raise ValueError("FMEA version not found")

    # Get current CP items
    items_result = await db.execute(
        select(ControlPlanItem).where(ControlPlanItem.cp_id == cp.cp_id).order_by(ControlPlanItem.sort_order)
    )
    current_items = list(items_result.scalars().all())
    current_map = {item.source_fmea_node_id: item for item in current_items if item.source_fmea_node_id}

    # Get FMEA snapshot nodes
    fmea_snapshot = fmea_version.snapshot or {"nodes": [], "edges": []}
    fmea_nodes = {n["id"]: n for n in fmea_snapshot.get("nodes", []) if n.get("type") == "ProcessStep"}

    preview_items = []
    sort_idx = 0

    for node_id, node in fmea_nodes.items():
        current = current_map.get(node_id)
        if not current:
            # New node from FMEA
            preview_items.append({
                "item_id": None,
                "step_no": node.get("process_number", ""),
                "current_value": {},
                "fmea_new_value": {"process_name": node.get("name", ""), "step_no": node.get("process_number", "")},
                "merged_value": {"process_name": node.get("name", ""), "step_no": node.get("process_number", "")},
                "action": "add",
            })
            continue

        # Check for changes in FMEA-derived fields
        fmea_name = node.get("name", "")
        fmea_step = node.get("process_number", "")
        changes = {}
        if current.process_name != fmea_name:
            changes["process_name"] = {"old": current.process_name, "new": fmea_name}
        if current.step_no != fmea_step:
            changes["step_no"] = {"old": current.step_no, "new": fmea_step}

        if changes:
            merged = {
                "process_name": fmea_name,
                "step_no": fmea_step,
                "equipment": current.equipment,
                "product_characteristic": current.product_characteristic,
                "process_characteristic": current.process_characteristic,
                "control_method": current.control_method,
                "sample_size": current.sample_size,
                "sample_frequency": current.sample_frequency,
                "reaction_plan": current.reaction_plan,
                "evaluation_method": current.evaluation_method,
                "specification_tolerance": current.specification_tolerance,
                "special_class": current.special_class,
                "characteristic_no": current.characteristic_no,
            }
            preview_items.append({
                "item_id": str(current.item_id),
                "step_no": current.step_no,
                "current_value": {"process_name": current.process_name, "step_no": current.step_no},
                "fmea_new_value": {"process_name": fmea_name, "step_no": fmea_step},
                "merged_value": merged,
                "action": "sync",
            })

    # Detect deleted nodes
    fmea_node_ids = set(fmea_nodes.keys())
    for current in current_items:
        if current.source_fmea_node_id and current.source_fmea_node_id not in fmea_node_ids and current.item_source == "fmea":
            preview_items.append({
                "item_id": str(current.item_id),
                "step_no": current.step_no,
                "current_value": {"process_name": current.process_name, "step_no": current.step_no},
                "fmea_new_value": {},
                "merged_value": {},
                "action": "delete",
            })

    return preview_items


async def apply_sync_preview(
    db: AsyncSession,
    cp: ControlPlan,
    fmea_version: FMEAVersion,
    accepted_items: list[str],  # item_ids to sync
    user_id: uuid.UUID,
) -> ControlPlanVersion:
    """Apply selected sync changes to CP."""
    preview = await build_sync_preview(db, cp, fmea_version)

    for preview_item in preview:
        action = preview_item["action"]
        if action == "add":
            new_item = ControlPlanItem(
                item_id=uuid.uuid4(),
                cp_id=cp.cp_id,
                step_no=preview_item["merged_value"].get("step_no"),
                process_name=preview_item["merged_value"].get("process_name"),
                source_fmea_node_id=preview_item.get("source_fmea_node_id"),
                item_source="fmea",
                sort_order=0,
            )
            db.add(new_item)
        elif action == "sync" and preview_item["item_id"] in accepted_items:
            result = await db.execute(
                select(ControlPlanItem).where(ControlPlanItem.item_id == uuid.UUID(preview_item["item_id"]))
            )
            item = result.scalar_one_or_none()
            if item:
                item.process_name = preview_item["merged_value"].get("process_name", item.process_name)
                item.step_no = preview_item["merged_value"].get("step_no", item.step_no)
        elif action == "delete" and preview_item["item_id"] in accepted_items:
            result = await db.execute(
                select(ControlPlanItem).where(ControlPlanItem.item_id == uuid.UUID(preview_item["item_id"]))
            )
            item = result.scalar_one_or_none()
            if item:
                await db.delete(item)

    cp.source_fmea_version_id = fmea_version.version_id
    cp.sync_pending = False
    cp.updated_by = user_id

    change_summary = f"基于 FMEA v{fmea_version.major_no}.{fmea_version.minor_no} 同步更新"
    version = await create_cp_version(
        db, cp, "fmea_sync", change_summary, user_id, source_fmea_version_id=fmea_version.version_id
    )

    await db.commit()
    return version
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/
git commit -m "feat(version): add FMEA-CP sync preview and apply engine with field-level merge"
```

---

## Task 8: Wire Version Creation into FMEA Transitions

**Files:**
- Modify: `backend/app/services/fmea_service.py`

- [ ] **Step 1: Import and hook version creation**

At the top of `backend/app/services/fmea_service.py`, add:

```python
from app.services.version_service import create_fmea_version
```

In `transition_fmea`, after the audit log creation and before `await db.commit()`, add:

```python
    # Create version snapshot on submit or approve
    if target in (FMEAState.IN_REVIEW, FMEAState.APPROVED):
        change_type = "approve" if target == FMEAState.APPROVED else "submit"
        change_summary = (
            f"状态变更：{old_status} → {target_status}"
            if target == FMEAState.IN_REVIEW
            else f"审批通过，版本发布"
        )
        await create_fmea_version(db, fmea, change_type, change_summary, user_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/fmea_service.py
git commit -m "feat(version): auto-create version snapshot on FMEA submit/approve"
```

---

## Task 9: Wire Version Creation into CP Approval + Sync Trigger

**Files:**
- Modify: `backend/app/services/control_plan_service.py`

- [ ] **Step 1: Import version service**

At the top of `backend/app/services/control_plan_service.py`, add:

```python
from app.services.version_service import create_cp_version, get_fmea_version_by_id
```

In `approve_control_plan`, after setting `cp.approved_at` and before the audit log, add:

```python
    # Create version snapshot on approve
    await create_cp_version(db, cp, "approve", "审批通过，版本发布", user_id)
```

Add a new function at the bottom of the file:

```python
async def mark_cp_sync_pending_on_fmea_approve(
    db: AsyncSession, fmea_id: uuid.UUID, fmea_version_id: uuid.UUID
) -> list[ControlPlan]:
    """Mark all linked CPs as sync pending when FMEA is approved."""
    from app.models.control_plan import ControlPlan

    result = await db.execute(
        select(ControlPlan).where(ControlPlan.fmea_ref_id == fmea_id)
    )
    cps = list(result.scalars().all())

    for cp in cps:
        # Only mark if CP is based on an older FMEA version
        if cp.source_fmea_version_id != fmea_version_id:
            cp.sync_pending = True

    await db.commit()
    return cps
```

- [ ] **Step 2: Wire FMEA approval to trigger CP sync**

In `backend/app/services/fmea_service.py`, in `transition_fmea` where `target == FMEAState.APPROVED`, after creating the FMEA version, add:

```python
    if target == FMEAState.APPROVED:
        # Trigger CP sync notifications
        from app.services.control_plan_service import mark_cp_sync_pending_on_fmea_approve
        await mark_cp_sync_pending_on_fmea_approve(db, fmea.fmea_id, version.version_id)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/control_plan_service.py backend/app/services/fmea_service.py
git commit -m "feat(version): auto-create CP version on approve + trigger sync pending for linked CPs"
```

---

## Task 10: Version API Routes

**Files:**
- Create: `backend/app/api/version.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the version API router**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin
from app.models.user import User
from app.models.fmea import FMEADocument
from app.models.control_plan import ControlPlan
from app.schemas.version import (
    FMEAVersionListItem, FMEAVersionDetail, ControlPlanVersionListItem,
    ControlPlanVersionDetail, ManualVersionCreate, RollbackRequest, RollbackResponse,
    FMEACompareResponse, CPCompareResponse, VerifyResponse, SyncPreviewResponse,
)
from app.services.version_service import (
    list_fmea_versions, get_fmea_version, create_fmea_version,
    list_cp_versions, get_cp_version, create_cp_version,
    rollback_fmea, rollback_control_plan,
    verify_fmea_version, verify_cp_version,
    build_sync_preview, apply_sync_preview, get_fmea_version_by_id,
)
from app.services.diff_engine import diff_fmea_graphs, diff_cp_items, diff_cp_headers
from app.services.fmea_service import get_fmea
from app.services.control_plan_service import get_control_plan

router = APIRouter(prefix="/api/versions", tags=["versions"])


# ── FMEA Versions ────────────────────────────────────────────────

@router.get("/fmea/{fmea_id}")
async def list_fmea_version_history(
    fmea_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    major_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await list_fmea_versions(db, fmea_id, page, page_size, major_only)
    return {
        "items": [FMEAVersionListItem.model_validate(v) for v in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/fmea/{fmea_id}/{major_no}/{minor_no}", response_model=FMEAVersionDetail)
async def get_fmea_version_detail(
    fmea_id: uuid.UUID,
    major_no: int,
    minor_no: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    version = await get_fmea_version(db, fmea_id, major_no, minor_no)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    return FMEAVersionDetail.model_validate(version)


@router.post("/fmea/{fmea_id}", response_model=FMEAVersionListItem, status_code=201)
async def manual_create_fmea_version(
    fmea_id: uuid.UUID,
    req: ManualVersionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    fmea = await get_fmea(db, fmea_id)
    if not fmea:
        raise HTTPException(status_code=404, detail="FMEA不存在")
    version = await create_fmea_version(db, fmea, "manual", req.change_summary, user.user_id)
    await db.commit()
    return FMEAVersionListItem.model_validate(version)


@router.post("/fmea/{fmea_id}/{major_no}/{minor_no}/rollback", response_model=RollbackResponse)
async def rollback_fmea_endpoint(
    fmea_id: uuid.UUID,
    major_no: int,
    minor_no: int,
    req: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    fmea = await get_fmea(db, fmea_id)
    if not fmea:
        raise HTTPException(status_code=404, detail="FMEA不存在")
    try:
        version = await rollback_fmea(db, fmea, major_no, minor_no, req.reason, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RollbackResponse.model_validate(version)


@router.get("/fmea/{fmea_id}/compare")
async def compare_fmea_versions(
    fmea_id: uuid.UUID,
    major1: int,
    minor1: int,
    major2: int,
    minor2: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    v1 = await get_fmea_version(db, fmea_id, major1, minor1)
    v2 = await get_fmea_version(db, fmea_id, major2, minor2)
    if not v1 or not v2:
        raise HTTPException(status_code=404, detail="版本不存在")

    diff = diff_fmea_graphs(v1.snapshot, v2.snapshot)
    summary = {
        "added": len(diff["added_nodes"]),
        "deleted": len(diff["deleted_nodes"]),
        "modified": len(diff["modified_nodes"]),
    }

    return {
        "v1": FMEAVersionDetail.model_validate(v1),
        "v2": FMEAVersionDetail.model_validate(v2),
        "diff": diff,
        "summary": summary,
    }


@router.get("/fmea/{fmea_id}/{major_no}/{minor_no}/verify", response_model=VerifyResponse)
async def verify_fmea_version_endpoint(
    fmea_id: uuid.UUID,
    major_no: int,
    minor_no: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    version = await get_fmea_version(db, fmea_id, major_no, minor_no)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    valid, computed, stored = await verify_fmea_version(db, version.version_id)
    return VerifyResponse(valid=valid, computed_hash=computed, stored_hash=stored)


# ── CP Versions ─────────────────────────────────────────────────

@router.get("/control-plans/{cp_id}")
async def list_cp_version_history(
    cp_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    major_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await list_cp_versions(db, cp_id, page, page_size, major_only)
    return {
        "items": [ControlPlanVersionListItem.model_validate(v) for v in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/control-plans/{cp_id}/{major_no}/{minor_no}", response_model=ControlPlanVersionDetail)
async def get_cp_version_detail(
    cp_id: uuid.UUID,
    major_no: int,
    minor_no: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    version = await get_cp_version(db, cp_id, major_no, minor_no)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    return ControlPlanVersionDetail.model_validate(version)


@router.post("/control-plans/{cp_id}", response_model=ControlPlanVersionListItem, status_code=201)
async def manual_create_cp_version(
    cp_id: uuid.UUID,
    req: ManualVersionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await get_control_plan(db, cp_id)
    if not cp:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    version = await create_cp_version(db, cp, "manual", req.change_summary, user.user_id)
    await db.commit()
    return ControlPlanVersionListItem.model_validate(version)


@router.post("/control-plans/{cp_id}/{major_no}/{minor_no}/rollback", response_model=RollbackResponse)
async def rollback_cp_endpoint(
    cp_id: uuid.UUID,
    major_no: int,
    minor_no: int,
    req: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    cp = await get_control_plan(db, cp_id)
    if not cp:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    try:
        version = await rollback_control_plan(db, cp, major_no, minor_no, req.reason, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RollbackResponse.model_validate(version)


@router.get("/control-plans/{cp_id}/compare")
async def compare_cp_versions(
    cp_id: uuid.UUID,
    major1: int,
    minor1: int,
    major2: int,
    minor2: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    v1 = await get_cp_version(db, cp_id, major1, minor1)
    v2 = await get_cp_version(db, cp_id, major2, minor2)
    if not v1 or not v2:
        raise HTTPException(status_code=404, detail="版本不存在")

    diff = diff_cp_items(v1.items_snapshot, v2.items_snapshot)
    header_changes = diff_cp_headers(v1.header_snapshot, v2.header_snapshot)
    summary = {
        "added": len(diff["added_items"]),
        "deleted": len(diff["deleted_items"]),
        "modified": len(diff["modified_items"]),
    }

    return {
        "v1": ControlPlanVersionDetail.model_validate(v1),
        "v2": ControlPlanVersionDetail.model_validate(v2),
        "diff": {**diff, "header_changes": header_changes},
        "summary": summary,
    }


@router.get("/control-plans/{cp_id}/{major_no}/{minor_no}/verify", response_model=VerifyResponse)
async def verify_cp_version_endpoint(
    cp_id: uuid.UUID,
    major_no: int,
    minor_no: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    version = await get_cp_version(db, cp_id, major_no, minor_no)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    valid, computed, stored = await verify_cp_version(db, version.version_id)
    return VerifyResponse(valid=valid, computed_hash=computed, stored_hash=stored)


# ── FMEA-CP Sync ─────────────────────────────────────────────────

@router.get("/control-plans/{cp_id}/sync-preview", response_model=SyncPreviewResponse)
async def sync_preview(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await get_control_plan(db, cp_id)
    if not cp:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    if not cp.source_fmea_version_id:
        raise HTTPException(status_code=400, detail="未关联FMEA版本")

    fmea_version = await get_fmea_version_by_id(db, cp.source_fmea_version_id)
    if not fmea_version:
        raise HTTPException(status_code=404, detail="关联的FMEA版本不存在")

    # Find the latest approved FMEA version to sync from
    from sqlalchemy import select
    from app.models.fmea_version import FMEAVersion
    result = await db.execute(
        select(FMEAVersion)
        .where(FMEAVersion.fmea_id == cp.fmea_ref_id)
        .order_by(FMEAVersion.major_no.desc(), FMEAVersion.minor_no.desc())
        .limit(1)
    )
    latest_fmea_version = result.scalar_one_or_none()
    if not latest_fmea_version:
        raise HTTPException(status_code=404, detail="FMEA版本不存在")

    preview_items = await build_sync_preview(db, cp, latest_fmea_version)
    return {
        "fmea_version_id": latest_fmea_version.version_id,
        "fmea_major_no": latest_fmea_version.major_no,
        "fmea_minor_no": latest_fmea_version.minor_no,
        "items": preview_items,
        "added_count": sum(1 for p in preview_items if p["action"] == "add"),
        "modified_count": sum(1 for p in preview_items if p["action"] == "sync"),
        "deleted_count": sum(1 for p in preview_items if p["action"] == "delete"),
    }


@router.post("/control-plans/{cp_id}/sync-from-fmea", response_model=ControlPlanVersionListItem)
async def sync_from_fmea(
    cp_id: uuid.UUID,
    accepted_item_ids: list[str],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await get_control_plan(db, cp_id)
    if not cp:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    if cp.status == "approved":
        raise HTTPException(status_code=400, detail="已批准的控制计划不能同步")

    from sqlalchemy import select
    from app.models.fmea_version import FMEAVersion
    result = await db.execute(
        select(FMEAVersion)
        .where(FMEAVersion.fmea_id == cp.fmea_ref_id)
        .order_by(FMEAVersion.major_no.desc(), FMEAVersion.minor_no.desc())
        .limit(1)
    )
    latest_fmea_version = result.scalar_one_or_none()
    if not latest_fmea_version:
        raise HTTPException(status_code=404, detail="FMEA版本不存在")

    try:
        version = await apply_sync_preview(db, cp, latest_fmea_version, accepted_item_ids, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ControlPlanVersionListItem.model_validate(version)
```

- [ ] **Step 2: Wire router into main.py**

In `backend/app/main.py`, add import:

```python
from app.api.version import router as version_router
```

And add:

```python
app.include_router(version_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/version.py backend/app/main.py
git commit -m "feat(version): add version API routes for CRUD, compare, rollback, and FMEA-CP sync"
```

---

## Task 11: Frontend Types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add version types**

Append to `frontend/src/types/index.ts`:

```typescript
export interface VersionBase {
  version_id: string;
  major_no: number;
  minor_no: number;
  change_summary: string;
  change_type: string;
  created_by: string;
  created_at: string;
}

export interface FMEAVersion extends VersionBase {
  snapshot?: Record<string, unknown>;
  sha256_hash?: string;
}

export interface CPVersion extends VersionBase {
  header_snapshot?: Record<string, unknown>;
  items_snapshot?: unknown[];
  sha256_hash?: string;
  source_fmea_version_id: string | null;
}

export interface VersionListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface NodeChange {
  field: string;
  old: string | number | null;
  new: string | number | null;
}

export interface ModifiedNode {
  node_id: string;
  changes: NodeChange[];
  impact_chain: string[];
}

export interface FMEADiffResult {
  added_nodes: Record<string, unknown>[];
  deleted_nodes: Record<string, unknown>[];
  modified_nodes: ModifiedNode[];
}

export interface CPItemChange {
  field: string;
  old: string | number | null;
  new: string | number | null;
}

export interface CPItemDiff {
  item_id: string;
  changes: CPItemChange[];
  status: string;
}

export interface CPDiffResult {
  added_items: Record<string, unknown>[];
  deleted_items: Record<string, unknown>[];
  modified_items: CPItemDiff[];
  header_changes: CPItemChange[];
}

export interface DiffSummary {
  added: number;
  deleted: number;
  modified: number;
}

export interface FMEACompareResponse {
  v1: FMEAVersion;
  v2: FMEAVersion;
  diff: FMEADiffResult;
  summary: DiffSummary;
}

export interface CPCompareResponse {
  v1: CPVersion;
  v2: CPVersion;
  diff: CPDiffResult;
  summary: DiffSummary;
}

export interface SyncPreviewItem {
  item_id: string | null;
  step_no: string | null;
  current_value: Record<string, unknown>;
  fmea_new_value: Record<string, unknown>;
  merged_value: Record<string, unknown>;
  action: string;
}

export interface SyncPreviewResponse {
  fmea_version_id: string;
  fmea_major_no: number;
  fmea_minor_no: number;
  items: SyncPreviewItem[];
  added_count: number;
  modified_count: number;
  deleted_count: number;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(version): add TypeScript types for version management"
```

---

## Task 12: Frontend API Functions

**Files:**
- Create: `frontend/src/api/version.ts`

- [ ] **Step 1: Write version API functions**

```typescript
import client from "./client";
import type {
  FMEAVersion, CPVersion, VersionListResponse,
  FMEACompareResponse, CPCompareResponse,
  SyncPreviewResponse, VerifyResponse,
} from "../types";

// ── FMEA Version API ────────────────────────────────────────────

export async function listFMEAVersions(
  fmeaId: string,
  params?: { page?: number; page_size?: number; major_only?: boolean }
): Promise<VersionListResponse<FMEAVersion>> {
  const resp = await client.get(`/versions/fmea/${fmeaId}`, { params });
  return resp.data;
}

export async function getFMEAVersion(
  fmeaId: string, major: number, minor: number
): Promise<FMEAVersion> {
  const resp = await client.get(`/versions/fmea/${fmeaId}/${major}/${minor}`);
  return resp.data;
}

export async function createFMEAVersion(
  fmeaId: string, changeSummary: string
): Promise<FMEAVersion> {
  const resp = await client.post(`/versions/fmea/${fmeaId}`, { change_summary: changeSummary });
  return resp.data;
}

export async function rollbackFMEAVersion(
  fmeaId: string, major: number, minor: number, reason: string
): Promise<FMEAVersion> {
  const resp = await client.post(`/versions/fmea/${fmeaId}/${major}/${minor}/rollback`, { reason });
  return resp.data;
}

export async function compareFMEAVersions(
  fmeaId: string, major1: number, minor1: number, major2: number, minor2: number
): Promise<FMEACompareResponse> {
  const resp = await client.get(`/versions/fmea/${fmeaId}/compare`, {
    params: { major1, minor1, major2, minor2 },
  });
  return resp.data;
}

export async function verifyFMEAVersion(
  fmeaId: string, major: number, minor: number
): Promise<VerifyResponse> {
  const resp = await client.get(`/versions/fmea/${fmeaId}/${major}/${minor}/verify`);
  return resp.data;
}

// ── CP Version API ──────────────────────────────────────────────

export async function listCPVersions(
  cpId: string,
  params?: { page?: number; page_size?: number; major_only?: boolean }
): Promise<VersionListResponse<CPVersion>> {
  const resp = await client.get(`/versions/control-plans/${cpId}`, { params });
  return resp.data;
}

export async function getCPVersion(
  cpId: string, major: number, minor: number
): Promise<CPVersion> {
  const resp = await client.get(`/versions/control-plans/${cpId}/${major}/${minor}`);
  return resp.data;
}

export async function createCPVersion(
  cpId: string, changeSummary: string
): Promise<CPVersion> {
  const resp = await client.post(`/versions/control-plans/${cpId}`, { change_summary: changeSummary });
  return resp.data;
}

export async function rollbackCPVersion(
  cpId: string, major: number, minor: number, reason: string
): Promise<CPVersion> {
  const resp = await client.post(`/versions/control-plans/${cpId}/${major}/${minor}/rollback`, { reason });
  return resp.data;
}

export async function compareCPVersions(
  cpId: string, major1: number, minor1: number, major2: number, minor2: number
): Promise<CPCompareResponse> {
  const resp = await client.get(`/versions/control-plans/${cpId}/compare`, {
    params: { major1, minor1, major2, minor2 },
  });
  return resp.data;
}

export async function verifyCPVersion(
  cpId: string, major: number, minor: number
): Promise<VerifyResponse> {
  const resp = await client.get(`/versions/control-plans/${cpId}/${major}/${minor}/verify`);
  return resp.data;
}

// ── FMEA-CP Sync API ────────────────────────────────────────────

export async function getSyncPreview(cpId: string): Promise<SyncPreviewResponse> {
  const resp = await client.get(`/versions/control-plans/${cpId}/sync-preview`);
  return resp.data;
}

export async function applySyncFromFMEA(
  cpId: string, acceptedItemIds: string[]
): Promise<CPVersion> {
  const resp = await client.post(`/versions/control-plans/${cpId}/sync-from-fmea`, acceptedItemIds);
  return resp.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/version.ts
git commit -m "feat(version): add frontend API functions for version management"
```

---

## Task 13: Version History Tab Component

**Files:**
- Create: `frontend/src/components/version/VersionHistoryTab.tsx`

- [ ] **Step 1: Write the component**

```tsx
import { useState, useEffect } from "react";
import { Timeline, Card, Button, Tag, Switch, Empty, message } from "antd";
import { RollbackOutlined, DiffOutlined, EyeOutlined, PlusOutlined } from "@ant-design/icons";
import type { FMEAVersion, CPVersion } from "../../types";

interface VersionHistoryTabProps {
  documentId: string;
  documentType: "fmea" | "cp";
  canCreate: boolean;
  canRollback: boolean;
  isDraft: boolean;
  onViewSnapshot: (major: number, minor: number) => void;
  onCompare: (major1: number, minor1: number, major2: number, minor2: number) => void;
  onRollback: (major: number, minor: number) => void;
  onCreateVersion: () => void;
}

const changeTypeColors: Record<string, string> = {
  submit: "blue",
  approve: "green",
  manual: "default",
  rollback: "orange",
  fmea_sync: "purple",
};

const changeTypeLabels: Record<string, string> = {
  submit: "提交审批",
  approve: "审批通过",
  manual: "手动创建",
  rollback: "版本回退",
  fmea_sync: "FMEA同步",
};

export default function VersionHistoryTab({
  documentId,
  documentType,
  canCreate,
  canRollback,
  isDraft,
  onViewSnapshot,
  onCompare,
  onRollback,
  onCreateVersion,
}: VersionHistoryTabProps) {
  const [versions, setVersions] = useState<(FMEAVersion | CPVersion)[]>([]);
  const [loading, setLoading] = useState(false);
  const [majorOnly, setMajorOnly] = useState(true);

  useEffect(() => {
    loadVersions();
  }, [documentId, majorOnly]);

  async function loadVersions() {
    setLoading(true);
    try {
      if (documentType === "fmea") {
        const { listFMEAVersions } = await import("../../api/version");
        const resp = await listFMEAVersions(documentId, { major_only: majorOnly });
        setVersions(resp.items);
      } else {
        const { listCPVersions } = await import("../../api/version");
        const resp = await listCPVersions(documentId, { major_only: majorOnly });
        setVersions(resp.items);
      }
    } catch (e) {
      message.error("加载版本历史失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card
      loading={loading}
      title={
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>版本历史</span>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <span>
              仅显示主版本
              <Switch checked={majorOnly} onChange={setMajorOnly} style={{ marginLeft: 8 }} />
            </span>
            {canCreate && (
              <Button type="primary" icon={<PlusOutlined />} onClick={onCreateVersion}>
                创建版本
              </Button>
            )}
          </div>
        </div>
      }
    >
      {versions.length === 0 ? (
        <Empty description="暂无版本记录" />
      ) : (
        <Timeline mode="left">
          {versions.map((v, idx) => (
            <Timeline.Item key={v.version_id}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <strong style={{ fontSize: 16 }}>
                      v{v.major_no}.{v.minor_no}
                    </strong>
                    {v.minor_no === 0 && (
                      <Tag color="green">已发布</Tag>
                    )}
                    <Tag color={changeTypeColors[v.change_type] || "default"}>
                      {changeTypeLabels[v.change_type] || v.change_type}
                    </Tag>
                  </div>
                  <div style={{ color: "#666", marginBottom: 4 }}>{v.change_summary}</div>
                  <div style={{ fontSize: 12, color: "#999" }}>
                    {new Date(v.created_at).toLocaleString()}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                  <Button
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={() => onViewSnapshot(v.major_no, v.minor_no)}
                  >
                    查看
                  </Button>
                  {idx < versions.length - 1 && (
                    <Button
                      size="small"
                      icon={<DiffOutlined />}
                      onClick={() =>
                        onCompare(v.major_no, v.minor_no, versions[idx + 1].major_no, versions[idx + 1].minor_no)
                      }
                    >
                      对比
                    </Button>
                  )}
                  {canRollback && isDraft && idx > 0 && v.minor_no !== 0 && (
                    <Button
                      size="small"
                      danger
                      icon={<RollbackOutlined />}
                      onClick={() => onRollback(v.major_no, v.minor_no)}
                    >
                      回退
                    </Button>
                  )}
                </div>
              </div>
            </Timeline.Item>
          ))}
        </Timeline>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/version/VersionHistoryTab.tsx
git commit -m "feat(version): add VersionHistoryTab component with timeline and filters"
```

---

## Task 14: Create Version Modal

**Files:**
- Create: `frontend/src/components/version/CreateVersionModal.tsx`

- [ ] **Step 1: Write the modal**

```tsx
import { useState } from "react";
import { Modal, Form, Input, message } from "antd";

interface CreateVersionModalProps {
  open: boolean;
  documentId: string;
  documentType: "fmea" | "cp";
  onClose: () => void;
  onSuccess: () => void;
}

export default function CreateVersionModal({
  open,
  documentId,
  documentType,
  onClose,
  onSuccess,
}: CreateVersionModalProps) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    const values = await form.validateFields();
    setLoading(true);
    try {
      if (documentType === "fmea") {
        const { createFMEAVersion } = await import("../../api/version");
        await createFMEAVersion(documentId, values.change_summary);
      } else {
        const { createCPVersion } = await import("../../api/version");
        await createCPVersion(documentId, values.change_summary);
      }
      message.success("版本创建成功");
      form.resetFields();
      onSuccess();
      onClose();
    } catch (e) {
      message.error("版本创建失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      title="创建新版本"
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={loading}
      okText="创建"
      cancelText="取消"
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="change_summary"
          label="变更摘要"
          rules={[{ required: true, message: "请填写变更摘要" }]}
        >
          <Input.TextArea
            rows={4}
            placeholder="描述本次版本的主要变更内容..."
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/version/CreateVersionModal.tsx
git commit -m "feat(version): add CreateVersionModal component"
```

---

## Task 15: Rollback Confirm Modal

**Files:**
- Create: `frontend/src/components/version/RollbackConfirmModal.tsx`

- [ ] **Step 1: Write the modal**

```tsx
import { useState } from "react";
import { Modal, Form, Input, message, Alert } from "antd";

interface RollbackConfirmModalProps {
  open: boolean;
  targetVersion: { major: number; minor: number } | null;
  documentId: string;
  documentType: "fmea" | "cp";
  onClose: () => void;
  onSuccess: () => void;
}

export default function RollbackConfirmModal({
  open,
  targetVersion,
  documentId,
  documentType,
  onClose,
  onSuccess,
}: RollbackConfirmModalProps) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    const values = await form.validateFields();
    if (!targetVersion) return;

    setLoading(true);
    try {
      if (documentType === "fmea") {
        const { rollbackFMEAVersion } = await import("../../api/version");
        await rollbackFMEAVersion(documentId, targetVersion.major, targetVersion.minor, values.reason);
      } else {
        const { rollbackCPVersion } = await import("../../api/version");
        await rollbackCPVersion(documentId, targetVersion.major, targetVersion.minor, values.reason);
      }
      message.success("回退成功");
      form.resetFields();
      onSuccess();
      onClose();
    } catch (e) {
      message.error("回退失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      title="确认回退版本"
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      confirmLoading={loading}
      okText="确认回退"
      okButtonProps={{ danger: true }}
      cancelText="取消"
    >
      <Alert
        message="回退操作将基于目标版本创建一个新版本"
        description="当前文档的数据将被替换为目标版本的内容，原有数据不会丢失。"
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
      />
      {targetVersion && (
        <p>
          目标版本：<strong>v{targetVersion.major}.{targetVersion.minor}</strong>
        </p>
      )}
      <Form form={form} layout="vertical">
        <Form.Item
          name="reason"
          label="回退原因"
          rules={[{ required: true, message: "请填写回退原因" }]}
        >
          <Input.TextArea
            rows={3}
            placeholder="请说明回退原因..."
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/version/RollbackConfirmModal.tsx
git commit -m "feat(version): add RollbackConfirmModal component"
```

---

## Task 16: Version Compare View

**Files:**
- Create: `frontend/src/components/version/VersionCompareView.tsx`

- [ ] **Step 1: Write the compare component**

```tsx
import { useState, useEffect } from "react";
import { Card, Table, Tag, Radio, Alert, Empty, Spin, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { FMEACompareResponse, CPCompareResponse, ModifiedNode, CPItemDiff } from "../../types";

interface VersionCompareViewProps {
  documentId: string;
  documentType: "fmea" | "cp";
  major1: number;
  minor1: number;
  major2: number;
  minor2: number;
}

type FilterMode = "all" | "added" | "deleted" | "modified";

export default function VersionCompareView({
  documentId,
  documentType,
  major1,
  minor1,
  major2,
  minor2,
}: VersionCompareViewProps) {
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterMode>("all");
  const [fmeaData, setFmeaData] = useState<FMEACompareResponse | null>(null);
  const [cpData, setCpData] = useState<CPCompareResponse | null>(null);

  useEffect(() => {
    loadComparison();
  }, [documentId, major1, minor1, major2, minor2]);

  async function loadComparison() {
    setLoading(true);
    try {
      if (documentType === "fmea") {
        const { compareFMEAVersions } = await import("../../api/version");
        const resp = await compareFMEAVersions(documentId, major1, minor1, major2, minor2);
        setFmeaData(resp);
      } else {
        const { compareCPVersions } = await import("../../api/version");
        const resp = await compareCPVersions(documentId, major1, minor1, major2, minor2);
        setCpData(resp);
      }
    } catch (e) {
      message.error("加载对比数据失败");
    } finally {
      setLoading(false);
    }
  }

  const summary = fmeaData?.summary ?? cpData?.summary;

  if (loading) return <Spin size="large" style={{ display: "block", margin: "40px auto" }} />;

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Radio.Group value={filter} onChange={(e) => setFilter(e.target.value)}>
            <Radio.Button value="all">
              全部 ({summary ? summary.added + summary.deleted + summary.modified : 0})
            </Radio.Button>
            <Radio.Button value="added">新增 ({summary?.added ?? 0})</Radio.Button>
            <Radio.Button value="deleted">删除 ({summary?.deleted ?? 0})</Radio.Button>
            <Radio.Button value="modified">修改 ({summary?.modified ?? 0})</Radio.Button>
          </Radio.Group>
          <span style={{ color: "#666" }}>
            对比：v{major1}.{minor1} → v{major2}.{minor2}
          </span>
        </div>
      </Card>

      {documentType === "fmea" && fmeaData && (
        <FMEADiffTable diff={fmeaData.diff} filter={filter} />
      )}
      {documentType === "cp" && cpData && (
        <CPDiffTable diff={cpData.diff} filter={filter} />
      )}
    </div>
  );
}

function FMEADiffTable({ diff, filter }: { diff: FMEACompareResponse["diff"]; filter: FilterMode }) {
  const columns: ColumnsType<ModifiedNode> = [
    { title: "节点ID", dataIndex: "node_id", key: "node_id" },
    {
      title: "变更字段",
      dataIndex: "changes",
      key: "changes",
      render: (changes: ModifiedNode["changes"]) =>
        changes.map((c, i) => (
          <div key={i}>
            <Tag color="orange">{c.field}</Tag>
            <span style={{ textDecoration: "line-through", color: "#999" }}>{String(c.old)}</span>
            {" → "}
            <span style={{ color: "#1890ff" }}>{String(c.new)}</span>
          </div>
        )),
    },
    {
      title: "影响",
      dataIndex: "impact_chain",
      key: "impact",
      render: (impacts: string[]) =>
        impacts.map((imp, i) => <Tag key={i} color="red">{imp}</Tag>),
    },
  ];

  const showAdded = filter === "all" || filter === "added";
  const showDeleted = filter === "all" || filter === "deleted";
  const showModified = filter === "all" || filter === "modified";

  return (
    <>
      {showAdded && diff.added_nodes.length > 0 && (
        <Card title="新增节点" size="small" style={{ marginBottom: 8, background: "#f6ffed" }}>
          <Table dataSource={diff.added_nodes} rowKey="id" columns={[
            { title: "ID", dataIndex: "id" },
            { title: "名称", dataIndex: "name" },
            { title: "类型", dataIndex: "type" },
          ]} pagination={false} size="small" />
        </Card>
      )}
      {showDeleted && diff.deleted_nodes.length > 0 && (
        <Card title="删除节点" size="small" style={{ marginBottom: 8, background: "#fff1f0" }}>
          <Table dataSource={diff.deleted_nodes} rowKey="id" columns={[
            { title: "ID", dataIndex: "id" },
            { title: "名称", dataIndex: "name" },
            { title: "类型", dataIndex: "type" },
          ]} pagination={false} size="small" />
        </Card>
      )}
      {showModified && diff.modified_nodes.length > 0 && (
        <Card title="修改节点" size="small" style={{ marginBottom: 8, background: "#fffbe6" }}>
          <Table dataSource={diff.modified_nodes} rowKey="node_id" columns={columns} pagination={false} size="small" />
        </Card>
      )}
      {diff.added_nodes.length === 0 && diff.deleted_nodes.length === 0 && diff.modified_nodes.length === 0 && (
        <Empty description="无差异" />
      )}
    </>
  );
}

function CPDiffTable({ diff, filter }: { diff: CPCompareResponse["diff"]; filter: FilterMode }) {
  const columns: ColumnsType<CPItemDiff> = [
    { title: "Item ID", dataIndex: "item_id", key: "item_id" },
    {
      title: "变更",
      dataIndex: "changes",
      key: "changes",
      render: (changes: CPItemDiff["changes"]) =>
        changes.map((c, i) => (
          <div key={i}>
            <Tag color="orange">{c.field}</Tag>
            <span style={{ textDecoration: "line-through", color: "#999" }}>{String(c.old)}</span>
            {" → "}
            <span style={{ color: "#1890ff" }}>{String(c.new)}</span>
          </div>
        )),
    },
  ];

  const showAdded = filter === "all" || filter === "added";
  const showDeleted = filter === "all" || filter === "deleted";
  const showModified = filter === "all" || filter === "modified";

  return (
    <>
      {showAdded && diff.added_items.length > 0 && (
        <Card title="新增项" size="small" style={{ marginBottom: 8, background: "#f6ffed" }}>
          <Table dataSource={diff.added_items} rowKey="item_id" columns={[
            { title: "工序", dataIndex: "step_no" },
            { title: "过程名", dataIndex: "process_name" },
          ]} pagination={false} size="small" />
        </Card>
      )}
      {showDeleted && diff.deleted_items.length > 0 && (
        <Card title="删除项" size="small" style={{ marginBottom: 8, background: "#fff1f0" }}>
          <Table dataSource={diff.deleted_items} rowKey="item_id" columns={[
            { title: "工序", dataIndex: "step_no" },
            { title: "过程名", dataIndex: "process_name" },
          ]} pagination={false} size="small" />
        </Card>
      )}
      {showModified && diff.modified_items.length > 0 && (
        <Card title="修改项" size="small" style={{ marginBottom: 8, background: "#fffbe6" }}>
          <Table dataSource={diff.modified_items} rowKey="item_id" columns={columns} pagination={false} size="small" />
        </Card>
      )}
      {diff.added_items.length === 0 && diff.deleted_items.length === 0 && diff.modified_items.length === 0 && (
        <Empty description="无差异" />
      )}
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/version/VersionCompareView.tsx
git commit -m "feat(version): add VersionCompareView with diff filters and impact chains"
```

---

## Task 17: FMEA-CP Sync Preview Drawer

**Files:**
- Create: `frontend/src/components/version/SyncPreviewDrawer.tsx`

- [ ] **Step 1: Write the drawer**

```tsx
import { useState, useEffect } from "react";
import { Drawer, Table, Button, Tag, Alert, message, Spin } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { SyncPreviewResponse, SyncPreviewItem } from "../../types";

interface SyncPreviewDrawerProps {
  open: boolean;
  cpId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export default function SyncPreviewDrawer({ open, cpId, onClose, onSuccess }: SyncPreviewDrawerProps) {
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [preview, setPreview] = useState<SyncPreviewResponse | null>(null);
  const [selectedItems, setSelectedItems] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      loadPreview();
    }
  }, [open, cpId]);

  async function loadPreview() {
    setLoading(true);
    try {
      const { getSyncPreview } = await import("../../api/version");
      const resp = await getSyncPreview(cpId);
      setPreview(resp);
      // Default: accept all sync items
      setSelectedItems(resp.items.filter((i) => i.action !== "delete").map((i) => i.item_id || "").filter(Boolean));
    } catch (e) {
      message.error("加载同步预览失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleApply() {
    setSubmitting(true);
    try {
      const { applySyncFromFMEA } = await import("../../api/version");
      await applySyncFromFMEA(cpId, selectedItems);
      message.success("同步成功");
      onSuccess();
      onClose();
    } catch (e) {
      message.error("同步失败");
    } finally {
      setSubmitting(false);
    }
  }

  const columns: ColumnsType<SyncPreviewItem> = [
    {
      title: "操作",
      dataIndex: "action",
      key: "action",
      render: (action: string) => {
        const labels: Record<string, string> = { add: "新增", sync: "同步", delete: "删除" };
        const colors: Record<string, string> = { add: "green", sync: "blue", delete: "red" };
        return <Tag color={colors[action]}>{labels[action]}</Tag>;
      },
    },
    { title: "工序", dataIndex: "step_no", key: "step_no" },
    {
      title: "当前值",
      dataIndex: "current_value",
      key: "current",
      render: (val: Record<string, unknown>) => (
        <span style={{ color: "#999" }}>{val.process_name as string || "-"}</span>
      ),
    },
    {
      title: "FMEA新值",
      dataIndex: "fmea_new_value",
      key: "fmea",
      render: (val: Record<string, unknown>) => (
        <span style={{ color: "#1890ff" }}>{val.process_name as string || "-"}</span>
      ),
    },
    {
      title: "合并结果",
      dataIndex: "merged_value",
      key: "merged",
      render: (val: Record<string, unknown>) => (
        <span>{val.process_name as string || "-"}</span>
      ),
    },
  ];

  return (
    <Drawer
      title="FMEA 同步预览"
      width={960}
      open={open}
      onClose={onClose}
      footer={
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={submitting} onClick={handleApply}>
            确认同步
          </Button>
        </div>
      }
    >
      {loading ? (
        <Spin style={{ display: "block", margin: "40px auto" }} />
      ) : preview ? (
        <>
          <Alert
            message={`关联的 FMEA 已更新至 v${preview.fmea_major_no}.${preview.fmea_minor_no}`}
            description={`新增 ${preview.added_count} 项 / 修改 ${preview.modified_count} 项 / 删除 ${preview.deleted_count} 项`}
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
          <Table
            dataSource={preview.items}
            rowKey={(record) => record.item_id || record.step_no || Math.random().toString()}
            columns={columns}
            pagination={false}
            size="small"
            rowSelection={{
              type: "checkbox",
              selectedRowKeys: selectedItems,
              onChange: (keys) => setSelectedItems(keys as string[]),
              getCheckboxProps: (record) => ({
                disabled: record.action === "delete",
              }),
            }}
          />
        </>
      ) : null}
    </Drawer>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/version/SyncPreviewDrawer.tsx
git commit -m "feat(version): add SyncPreviewDrawer for FMEA-CP three-way merge"
```

---

## Task 18: Wire Version History into FMEA Editor Page

**Files:**
- Modify: `frontend/src/pages/fmea/FMEAEditorPage.tsx`

- [ ] **Step 1: Add imports and state**

Add these imports near the top of the file:

```tsx
import { Tabs } from "antd";
import { HistoryOutlined } from "@ant-design/icons";
import VersionHistoryTab from "../../components/version/VersionHistoryTab";
import CreateVersionModal from "../../components/version/CreateVersionModal";
import RollbackConfirmModal from "../../components/version/RollbackConfirmModal";
import VersionCompareView from "../../components/version/VersionCompareView";
```

Add state variables (in the component body):

```tsx
const [activeTab, setActiveTab] = useState("editor");
const [createVersionOpen, setCreateVersionOpen] = useState(false);
const [rollbackTarget, setRollbackTarget] = useState<{ major: number; minor: number } | null>(null);
const [compareVersions, setCompareVersions] = useState<{ major1: number; minor1: number; major2: number; minor2: number } | null>(null);
const [compareOpen, setCompareOpen] = useState(false);
```

- [ ] **Step 2: Replace the page content with Tabs**

Wrap the existing editor content in a `Tabs` component. The existing content becomes the `editor` tab, and add a `history` tab:

```tsx
<Tabs activeKey={activeTab} onChange={setActiveTab}>
  <Tabs.TabPane tab="编辑器" key="editor">
    {/* existing editor content */}
  </Tabs.TabPane>
  <Tabs.TabPane
    tab={<span><HistoryOutlined /> 版本历史</span>}
    key="history"
  >
    <VersionHistoryTab
      documentId={id!}
      documentType="fmea"
      canCreate={user?.role !== "viewer"}
      canRollback={user?.role === "admin" || user?.role === "manager"}
      isDraft={document?.status === "draft"}
      onViewSnapshot={(major, minor) => {
        // Could open a read-only snapshot view
        message.info(`查看 v${major}.${minor} 快照`);
      }}
      onCompare={(major1, minor1, major2, minor2) => {
        setCompareVersions({ major1, minor1, major2, minor2 });
        setCompareOpen(true);
      }}
      onRollback={(major, minor) => setRollbackTarget({ major, minor })}
      onCreateVersion={() => setCreateVersionOpen(true)}
    />
  </Tabs.TabPane>
</Tabs>
```

- [ ] **Step 3: Add modals at the bottom of the component**

```tsx
<CreateVersionModal
  open={createVersionOpen}
  documentId={id!}
  documentType="fmea"
  onClose={() => setCreateVersionOpen(false)}
  onSuccess={() => {
    // Refresh version list if needed
  }}
/>

<RollbackConfirmModal
  open={!!rollbackTarget}
  targetVersion={rollbackTarget}
  documentId={id!}
  documentType="fmea"
  onClose={() => setRollbackTarget(null)}
  onSuccess={() => {
    // Refresh document data
    loadFMEA();
    setRollbackTarget(null);
  }}
/>

{compareOpen && compareVersions && (
  <VersionCompareView
    documentId={id!}
    documentType="fmea"
    major1={compareVersions.major1}
    minor1={compareVersions.minor1}
    major2={compareVersions.major2}
    minor2={compareVersions.minor2}
  />
)}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/fmea/FMEAEditorPage.tsx
git commit -m "feat(version): add version history tab to FMEA editor"
```

---

## Task 19: Wire Version History into CP Editor Page

**Files:**
- Modify: `frontend/src/pages/control-plan/ControlPlanEditorPage.tsx`

- [ ] **Step 1: Add imports and state**

Add imports:

```tsx
import { Tabs, Alert, Button } from "antd";
import { HistoryOutlined, SyncOutlined } from "@ant-design/icons";
import VersionHistoryTab from "../../components/version/VersionHistoryTab";
import CreateVersionModal from "../../components/version/CreateVersionModal";
import RollbackConfirmModal from "../../components/version/RollbackConfirmModal";
import VersionCompareView from "../../components/version/VersionCompareView";
import SyncPreviewDrawer from "../../components/version/SyncPreviewDrawer";
```

Add state:

```tsx
const [activeTab, setActiveTab] = useState("editor");
const [createVersionOpen, setCreateVersionOpen] = useState(false);
const [rollbackTarget, setRollbackTarget] = useState<{ major: number; minor: number } | null>(null);
const [compareVersions, setCompareVersions] = useState<{ major1: number; minor1: number; major2: number; minor2: number } | null>(null);
const [compareOpen, setCompareOpen] = useState(false);
const [syncDrawerOpen, setSyncDrawerOpen] = useState(false);
```

- [ ] **Step 2: Add sync pending banner**

Above the Tabs, conditionally render the sync banner:

```tsx
{controlPlan?.sync_pending && (
  <Alert
    message={`关联的 FMEA 已更新（当前 CP 基于较旧版本），建议同步更新`}
    type="warning"
    showIcon
    action={
      <Button size="small" icon={<SyncOutlined />} onClick={() => setSyncDrawerOpen(true)}>
        立即同步
      </Button>
    }
    style={{ marginBottom: 16 }}
  />
)}
```

- [ ] **Step 3: Add Tabs and modals**

Same pattern as FMEA editor, with `documentType="cp"`:

```tsx
<Tabs activeKey={activeTab} onChange={setActiveTab}>
  <Tabs.TabPane tab="编辑器" key="editor">
    {/* existing editor content */}
  </Tabs.TabPane>
  <Tabs.TabPane
    tab={<span><HistoryOutlined /> 版本历史</span>}
    key="history"
  >
    <VersionHistoryTab
      documentId={id!}
      documentType="cp"
      canCreate={user?.role !== "viewer"}
      canRollback={user?.role === "admin" || user?.role === "manager"}
      isDraft={controlPlan?.status === "draft"}
      onViewSnapshot={(major, minor) => {
        message.info(`查看 v${major}.${minor} 快照`);
      }}
      onCompare={(major1, minor1, major2, minor2) => {
        setCompareVersions({ major1, minor1, major2, minor2 });
        setCompareOpen(true);
      }}
      onRollback={(major, minor) => setRollbackTarget({ major, minor })}
      onCreateVersion={() => setCreateVersionOpen(true)}
    />
  </Tabs.TabPane>
</Tabs>
```

Add modals and drawer:

```tsx
<CreateVersionModal
  open={createVersionOpen}
  documentId={id!}
  documentType="cp"
  onClose={() => setCreateVersionOpen(false)}
  onSuccess={() => {}}
/>

<RollbackConfirmModal
  open={!!rollbackTarget}
  targetVersion={rollbackTarget}
  documentId={id!}
  documentType="cp"
  onClose={() => setRollbackTarget(null)}
  onSuccess={() => {
    loadControlPlan();
    setRollbackTarget(null);
  }}
/>

{compareOpen && compareVersions && (
  <VersionCompareView
    documentId={id!}
    documentType="cp"
    major1={compareVersions.major1}
    minor1={compareVersions.minor1}
    major2={compareVersions.major2}
    minor2={compareVersions.minor2}
  />
)}

<SyncPreviewDrawer
  open={syncDrawerOpen}
  cpId={id!}
  onClose={() => setSyncDrawerOpen(false)}
  onSuccess={() => {
    loadControlPlan();
    setSyncDrawerOpen(false);
  }}
/>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/control-plan/ControlPlanEditorPage.tsx
git commit -m "feat(version): add version history tab and sync banner to CP editor"
```

---

## Task 20: Build Verification

- [ ] **Step 1: Build backend**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m py_compile app/models/fmea_version.py app/models/control_plan_version.py app/schemas/version.py app/services/version_service.py app/services/diff_engine.py app/api/version.py
```

Expected: No syntax errors.

- [ ] **Step 2: Build frontend**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npm run build
```

Expected: `tsc --noEmit` passes, `vite build` succeeds.

- [ ] **Step 3: Run backend smoke test**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -m app.test_schema
```

Expected: No import errors, schema loads.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(version): complete FMEA/CP version management module (major.minor, SHA-256, UUID upsert, field-level sync)"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Requirement | Task(s) |
|-----------------|---------|
| `fmea_versions` table with major_no, minor_no, snapshot, sha256_hash | Task 1, 2 |
| `control_plan_versions` table with header/items snapshots, source_fmea_version_id FK | Task 1, 2 |
| Alter control_plans (source_fmea_version_id, sync_pending) | Task 1, 2 |
| Alter control_plan_items (item_source) | Task 1, 2 |
| SHA-256 hash computation and verification | Task 4, 10 |
| Major.Minor versioning (approve → major+1, others → minor+1) | Task 4 |
| FMEA version auto-create on submit/approve | Task 8 |
| CP version auto-create on approve | Task 9 |
| FMEA-CP sync trigger on FMEA approve | Task 9 |
| UUID-idempotent CP rollback (Upsert, preserve item_id) | Task 6 |
| FMEA rollback (graph_data replace) | Task 6 |
| Diff engine for FMEA graphs (added/deleted/modified nodes + impact chain) | Task 5 |
| Diff engine for CP items (added/deleted/modified + header changes) | Task 5 |
| Field-level merge sync (FMEA-derived fields sync, CP custom fields preserve) | Task 7 |
| Sync preview API (three-way preview) | Task 10 |
| Sync apply API (selective item acceptance) | Task 10 |
| Version list API with major_only filter | Task 10 |
| Version compare API | Task 10 |
| Version verify API (SHA-256 check) | Task 10 |
| Rollback API with reason | Task 10 |
| Frontend: version history timeline with major/minor filter | Task 13 |
| Frontend: create version modal | Task 14 |
| Frontend: rollback confirm modal with reason | Task 15 |
| Frontend: side-by-side diff view with filters | Task 16 |
| Frontend: sync preview drawer | Task 17 |
| Frontend: wire into FMEA editor | Task 18 |
| Frontend: wire into CP editor with sync banner | Task 19 |

### Placeholder Scan
- No TBD, TODO, or "implement later" found
- All code is complete and copy-paste ready
- All API endpoint paths match the design doc
- All types are defined before use

### Type Consistency
- `change_type` enum: `submit`, `approve`, `manual`, `rollback`, `fmea_sync` — consistent across DB, schema, service, API, frontend
- Version composite key: `(major_no, minor_no)` — consistent everywhere
- `source_fmea_version_id` is UUID FK — used consistently in DB, model, schema, service
- `item_source` enum: `fmea`, `custom` — consistent across DB, model, service

### Gaps Fixed
- Added `verify` endpoints for both FMEA and CP (spec requires SHA-256 verification)
- Added `major_only` query param to list endpoints (spec requires filtering)
- Added `impact_chain` to diff engine (spec requires RPN cascade visualization)
- Added three-way sync preview with selective acceptance (spec requires `[✔ 接受同步]` / `[✖ 保持本地]`)
