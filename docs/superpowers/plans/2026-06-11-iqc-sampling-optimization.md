# IQC 抽样方案智能优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dynamic AQL recommendation engine that adjusts inspection sampling plans based on historical quality data, supplier performance, and SCAR/complaint history — with multi-level approval before changes take effect.

**Architecture:** New backend service (`iqc_aql_service.py`) with rule engine, quality snapshot calculator, profile manager, and recommendation manager. Four new DB tables + two new columns on `iqc_inspections`. Frontend: 4 new pages under `/iqc/aql-optimization`. Existing `create_inspection` auto-injects dynamic AQL; existing `judge_inspection` triggers rule evaluation.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 async + Pydantic v2 | React 18 + TypeScript + Ant Design 5 + @ant-design/charts | PostgreSQL 15 + Alembic

**Spec:** `docs/superpowers/specs/2026-06-11-iqc-sampling-optimization-design.md`

---

## File Structure

### Backend — New Files
| File | Responsibility |
|---|---|
| `backend/app/models/iqc_aql_profile.py` | ORM: IqcAqlProfile |
| `backend/app/models/iqc_aql_recommendation.py` | ORM: IqcAqlRecommendation |
| `backend/app/models/iqc_aql_quality_snapshot.py` | ORM: IqcAqlQualitySnapshot |
| `backend/app/models/iqc_aql_config.py` | ORM: IqcAqlConfig |
| `backend/app/schemas/iqc_aql.py` | Pydantic request/response schemas |
| `backend/app/services/iqc_aql_service.py` | Core business logic (rule engine, snapshot, profile, recommendation, config) |
| `backend/tests/test_iqc_aql.py` | Unit + integration tests |

### Backend — Modified Files
| File | Change |
|---|---|
| `backend/app/models/__init__.py` | Import + export new models |
| `backend/app/models/iqc_inspection.py` | Add `has_safety_defect`, `linked_customer_complaint_id` fields |
| `backend/app/schemas/iqc.py` | Extend `IqcInspectionJudge` with `has_safety_defect`, `linked_customer_complaint_id` |
| `backend/app/api/iqc.py` | Add ~20 new AQL optimization endpoints |
| `backend/app/services/iqc_inspection_service.py` | Trigger rule eval after judge; inject dynamic AQL on create |
| `backend/app/main.py` | Register AQL expiry cleanup coroutine |

### Frontend — New Files
| File | Responsibility |
|---|---|
| `frontend/src/pages/iqc/AqlOptimizationPage.tsx` | 建议列表主页面 |
| `frontend/src/pages/iqc/AqlProfileListPage.tsx` | 档案管理列表 |
| `frontend/src/pages/iqc/AqlProfileDetailPage.tsx` | 档案详情/质量画像 |
| `frontend/src/pages/iqc/AqlConfigPage.tsx` | 规则参数配置 (admin) |
| `frontend/src/api/iqcAql.ts` | API client functions |
| `frontend/src/components/iqc/AqlRecommendationDrawer.tsx` | 建议详情 Drawer |
| `frontend/src/components/iqc/AqlQualityChart.tsx` | AQL+PPM 趋势图 |

### Frontend — Modified Files
| File | Change |
|---|---|
| `frontend/src/types/index.ts` | Add AQL optimization interfaces |
| `frontend/src/App.tsx` | Add 4 new routes |
| `frontend/src/components/layout/AppLayout.tsx` | Add sidebar menu item |

### Database
| File | Change |
|---|---|
| `backend/alembic/versions/*merge*` | Merge two 032 heads into single head |
| `backend/alembic/versions/033_add_iqc_aql_optimization.py` | 4 new tables + 2 new columns on iqc_inspections + config seed data |

---

## Task 0: Alembic Merge — Resolve Two Heads at 032

**Files:**
- Create: `backend/alembic/versions/032_merge_heads.py`

The repo currently has two heads: `032_add_erp_tables` and `032_lessons_learned_cache`. Before the 033 migration can run, these must be merged into a single head.

- [ ] **Step 1: Create merge migration**

Run: `cd backend && alembic merge -m "merge_032_heads" 032_add_erp_tables 032_lessons_learned_cache`

This generates a file like `032_merge_heads.py` with a unique revision ID. Note the generated revision ID — it will be used as `down_revision` in Task 1.

- [ ] **Step 2: Verify heads are merged**

Run: `cd backend && alembic heads`
Expected: Single head (the merge revision)

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/*merge*
git commit -m "chore(alembic): merge 032 heads"
```

---

## Task 1: Alembic Migration — 4 New Tables + Inspection Columns

**Files:**
- Create: `backend/alembic/versions/033_add_iqc_aql_optimization.py`

- [ ] **Step 1: Write migration file**

```python
"""Add IQC AQL optimization tables

Revision ID: 033_add_iqc_aql_optimization
Revises: 032_add_erp_tables
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "033_add_iqc_aql_optimization"
down_revision = "<MERGE_REVISION_ID>"  # Set to revision ID from Task 0 merge
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extend iqc_inspections ──
    op.add_column("iqc_inspections", sa.Column("has_safety_defect", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("iqc_inspections", sa.Column(
        "linked_customer_complaint_id", UUID(as_uuid=True),
        sa.ForeignKey("customer_complaints.complaint_id", ondelete="SET NULL"),
        nullable=True,
    ))

    # ── iqc_aql_profiles ──
    op.create_table(
        "iqc_aql_profiles",
        sa.Column("profile_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_id", UUID(as_uuid=True), sa.ForeignKey("iqc_materials.material_id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_aql", sa.Float(), nullable=False),
        sa.Column("current_aql", sa.Float(), nullable=False),
        sa.Column("min_aql", sa.Float(), nullable=True),
        sa.Column("max_aql", sa.Float(), nullable=True),
        sa.Column("inspection_level", sa.String(10), server_default="II", nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("frozen_until", sa.Date(), nullable=True),
        sa.Column("frozen_reason", sa.String(50), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_inspection_id", UUID(as_uuid=True), sa.ForeignKey("iqc_inspections.inspection_id"), nullable=True),
        sa.Column("product_line_code", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("supplier_id", "material_id"),
    )
    op.create_index("ix_aql_profiles_product_line", "iqc_aql_profiles", ["product_line_code"])
    op.create_index("ix_aql_profiles_state", "iqc_aql_profiles", ["state"])

    # ── iqc_aql_recommendations ──
    op.create_table(
        "iqc_aql_recommendations",
        sa.Column("recommendation_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("profile_id", UUID(as_uuid=True), sa.ForeignKey("iqc_aql_profiles.profile_id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", UUID(as_uuid=True), nullable=False),
        sa.Column("current_aql", sa.Float(), nullable=False),
        sa.Column("recommended_aql", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("trigger_rules", JSONB(), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("approval_level", sa.String(20), nullable=False),
        sa.Column("engineer_decision", sa.String(20), nullable=True),
        sa.Column("engineer_decided_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("engineer_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manager_decision", sa.String(20), nullable=True),
        sa.Column("manager_decided_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("manager_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_aql_rec_profile_status", "iqc_aql_recommendations", ["profile_id", "status"])
    op.create_index("ix_aql_rec_sm_created", "iqc_aql_recommendations", ["supplier_id", "material_id", "created_at"])
    op.create_index("ix_aql_rec_status_expires", "iqc_aql_recommendations", ["status", "expires_at"])

    # ── iqc_aql_quality_snapshots ──
    op.create_table(
        "iqc_aql_quality_snapshots",
        sa.Column("snapshot_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", UUID(as_uuid=True), nullable=False),
        sa.Column("material_id", UUID(as_uuid=True), nullable=False),
        sa.Column("inspection_id", UUID(as_uuid=True), sa.ForeignKey("iqc_inspections.inspection_id"), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_batches", sa.Integer(), nullable=False),
        sa.Column("consecutive_accepted", sa.Integer(), nullable=False),
        sa.Column("consecutive_rejected", sa.Integer(), nullable=False),
        sa.Column("last_30d_batch_count", sa.Integer(), nullable=False),
        sa.Column("last_30d_ppm", sa.Float(), nullable=True),
        sa.Column("last_90d_ppm", sa.Float(), nullable=True),
        sa.Column("open_scar_count", sa.Integer(), nullable=False),
        sa.Column("supplier_rating", sa.String(1), nullable=True),
        sa.Column("has_safety_defect", sa.Boolean(), nullable=False),
        sa.Column("linked_customer_complaint", sa.Boolean(), nullable=False),
        sa.Column("calculated_state", sa.String(20), nullable=True),
    )
    op.create_index("ix_aql_snap_sm_time", "iqc_aql_quality_snapshots", ["supplier_id", "material_id", "snapshot_at"])

    # ── iqc_aql_configs ──
    op.create_table(
        "iqc_aql_configs",
        sa.Column("config_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("config_key", sa.String(50), nullable=False),
        sa.Column("config_value", sa.String(255), nullable=False),
        sa.Column("value_type", sa.String(20), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("product_line_code", sa.String(20), nullable=True),
        sa.Column("is_editable", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Partial unique indexes: NULL in product_line_code breaks standard unique constraint
    op.create_index(
        "uq_config_key_product_line", "iqc_aql_configs",
        ["config_key", "product_line_code"], unique=True,
        postgresql_where=sa.text("product_line_code IS NOT NULL"),
    )
    op.create_index(
        "uq_config_key_global", "iqc_aql_configs",
        ["config_key"], unique=True,
        postgresql_where=sa.text("product_line_code IS NULL"),
    )

    # ── Seed default config parameters ──
    import uuid as _uuid
    config_table = sa.table(
        "iqc_aql_configs",
        sa.column("config_id", UUID(as_uuid=True)),
        sa.column("config_key", sa.String()),
        sa.column("config_value", sa.String()),
        sa.column("value_type", sa.String()),
        sa.column("description", sa.String()),
        sa.column("is_editable", sa.Boolean()),
    )
    configs = [
        ("consecutive_accepted_for_reduce_1", "5", "int", "放宽一级所需连续合格批次"),
        ("consecutive_accepted_for_reduce_2", "10", "int", "放宽两级所需连续合格批次"),
        ("consecutive_rejected_for_tighten_1", "1", "int", "加严一级所需连续不合格批次"),
        ("consecutive_rejected_for_tighten_2", "2", "int", "加严两级所需连续不合格批次"),
        ("ppm_threshold_high", "5000", "float", "PPM加严阈值 (parts per million)"),
        ("ppm_threshold_low", "1000", "float", "PPM放宽阈值 (parts per million)"),
        ("recommendation_expiry_days", "7", "int", "建议过期天数"),
        ("max_aql_default", "2.5", "float", "默认最大AQL"),
        ("min_aql_default", "0.40", "float", "默认最小AQL"),
        ("safety_defect_freeze_days", "90", "int", "安全缺陷冻结天数"),
        ("default_inspection_level", "II", "string", "默认检验水平"),
        ("default_aql_fallback", "1.0", "float", "物料默认AQL为NULL时的回退值"),
    ]
    op.bulk_insert(
        config_table,
        [
            {
                "config_id": _uuid.uuid4(),
                "config_key": key,
                "config_value": val,
                "value_type": typ,
                "description": desc,
                "is_editable": True,
            }
            for key, val, typ, desc in configs
        ],
    )


def downgrade() -> None:
    op.drop_table("iqc_aql_configs")
    op.drop_table("iqc_aql_quality_snapshots")
    op.drop_table("iqc_aql_recommendations")
    op.drop_table("iqc_aql_profiles")
    op.drop_column("iqc_inspections", "linked_customer_complaint_id")
    op.drop_column("iqc_inspections", "has_safety_defect")
```

- [ ] **Step 2: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: No errors, 4 new tables created

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/033_add_iqc_aql_optimization.py
git commit -m "feat(iqc-aql): add migration for AQL optimization tables"
```

---

## Task 2: ORM Models

**Files:**
- Create: `backend/app/models/iqc_aql_profile.py`
- Create: `backend/app/models/iqc_aql_recommendation.py`
- Create: `backend/app/models/iqc_aql_quality_snapshot.py`
- Create: `backend/app/models/iqc_aql_config.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/iqc_inspection.py`

- [ ] **Step 1: Create `iqc_aql_profile.py`**

```python
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Float, Date, DateTime, ForeignKey, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IqcAqlProfile(Base):
    __tablename__ = "iqc_aql_profiles"

    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iqc_materials.material_id", ondelete="CASCADE"), nullable=False)
    base_aql: Mapped[float] = mapped_column(Float, nullable=False)
    current_aql: Mapped[float] = mapped_column(Float, nullable=False)
    min_aql: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_aql: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inspection_level: Mapped[str] = mapped_column(String(10), nullable=False, default="II")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    frozen_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    frozen_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    state_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    baseline_inspection_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("iqc_inspections.inspection_id"), nullable=True)
    product_line_code: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

- [ ] **Step 2: Create `iqc_aql_recommendation.py`**

```python
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Float, DateTime, ForeignKey, Date, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IqcAqlRecommendation(Base):
    __tablename__ = "iqc_aql_recommendations"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("iqc_aql_profiles.profile_id", ondelete="CASCADE"), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    current_aql: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_aql: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    approval_level: Mapped[str] = mapped_column(String(20), nullable=False)
    engineer_decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    engineer_decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    engineer_decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    manager_decision: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    manager_decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    manager_decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 3: Create `iqc_aql_quality_snapshot.py`**

```python
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IqcAqlQualitySnapshot(Base):
    __tablename__ = "iqc_aql_quality_snapshots"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    inspection_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("iqc_inspections.inspection_id"), nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_batches: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_accepted: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_rejected: Mapped[int] = mapped_column(Integer, nullable=False)
    last_30d_batch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_30d_ppm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_90d_ppm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_scar_count: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_rating: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)
    has_safety_defect: Mapped[bool] = mapped_column(Boolean, nullable=False)
    linked_customer_complaint: Mapped[bool] = mapped_column(Boolean, nullable=False)
    calculated_state: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
```

- [ ] **Step 4: Create `iqc_aql_config.py`**

```python
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IqcAqlConfig(Base):
    __tablename__ = "iqc_aql_configs"
    __table_args__ = (
        UniqueConstraint("config_key", "product_line_code", name="uq_config_key_product_line"),
        # Note: partial indexes for NULL product_line_code created in migration
    )

    config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_key: Mapped[str] = mapped_column(String(50), nullable=False)
    config_value: Mapped[str] = mapped_column(String(255), nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

- [ ] **Step 5: Add `has_safety_defect` and `linked_customer_complaint_id` to `IqcInspection`**

Add to `backend/app/models/iqc_inspection.py` after `judged_at`:

```python
    has_safety_defect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    linked_customer_complaint_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_complaints.complaint_id", ondelete="SET NULL"), nullable=True
    )
```

- [ ] **Step 6: Update `backend/app/models/__init__.py`**

Add imports and `__all__` entries for `IqcAqlProfile`, `IqcAqlRecommendation`, `IqcAqlQualitySnapshot`, `IqcAqlConfig`.

- [ ] **Step 7: Verify models load**

Run: `cd backend && python -c "from app.models import IqcAqlProfile, IqcAqlRecommendation, IqcAqlQualitySnapshot, IqcAqlConfig; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/iqc_aql_profile.py backend/app/models/iqc_aql_recommendation.py backend/app/models/iqc_aql_quality_snapshot.py backend/app/models/iqc_aql_config.py backend/app/models/__init__.py backend/app/models/iqc_inspection.py
git commit -m "feat(iqc-aql): add ORM models for AQL optimization"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/iqc_aql.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/schemas/iqc.py` — extend `IqcInspectionJudge` with safety/complaint fields

- [ ] **Step 1: Write all schemas**

Create `backend/app/schemas/iqc_aql.py` with request/response schemas for:
- `AqlProfileCreate`, `AqlProfileUpdate`, `AqlProfileResponse`, `AqlProfileListResponse`
- `AqlRecommendationResponse`, `AqlRecommendationListResponse`
- `AqlQualitySnapshotResponse`, `AqlQualitySnapshotTrendResponse`
- `AqlConfigResponse`, `AqlConfigUpdate`
- `AqlRecommendationApproveRequest`, `AqlRecommendationRejectRequest`
- `AqlTriggerRequest`, `AqlPreviewRequest`, `AqlPreviewResponse`

All schemas use `model_config = {"from_attributes": True}`. Fields match the spec exactly (Section 3 & 6).

- [ ] **Step 2: Extend `IqcInspectionJudge` in `backend/app/schemas/iqc.py`**

Add two optional fields to `IqcInspectionJudge` (after `sample_qty`):

```python
class IqcInspectionJudge(BaseModel):
    inspection_result: str
    defect_qty: int = 0
    defect_description: str | None = None
    sample_qty: int | None = None
    has_safety_defect: bool = False
    linked_customer_complaint_id: uuid.UUID | None = None
```

This allows the judge endpoint to receive safety defect and customer complaint linkage data, which the rule engine needs to trigger FREEZE_SAFETY_DEFECT and TIGHTEN_CUSTOMER_COMPLAINT rules.

- [ ] **Step 3: Update `backend/app/schemas/__init__.py`**

Add `from app.schemas import iqc_aql` at end of file (after `from app.schemas import quality_trend`).

- [ ] **Step 4: Verify schemas load**

Run: `cd backend && python -c "from app.schemas.iqc_aql import AqlProfileResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/iqc_aql.py backend/app/schemas/iqc.py backend/app/schemas/__init__.py
git commit -m "feat(iqc-aql): add Pydantic schemas for AQL optimization"
```

---

## Task 4: Core Service — Rule Engine + AQL Calculation

**Files:**
- Create: `backend/app/services/iqc_aql_service.py` (first section: constants, AqlContext, rule engine, AQL calculation)

- [ ] **Step 1: Write `iqc_aql_service.py` with rule engine core**

Implement in this file:
1. `AqlContext` dataclass (all fields from spec Section 7.2)
2. `AQL_RULES` list (all 10 rules from spec Section 4.2, with `frozen_aql_policy` and `aql_steps`)
3. `get_aql_by_state()` function (spec Section 4.1, with `current_aql` param for frozen)
4. `RuleEngine` class with `evaluate()` method (spec Section 4.3 execution flow)
5. `QualitySnapshotCalculator` class with `calculate()` method
6. `ProfileManager` class with `get_profile()`, `get_or_create_profile()`, `apply_recommendation()` methods
7. `RecommendationManager` class with `generate_recommendation()`, `approve()`, `reject()`, `forward()`, `expire_stale()` methods
8. `AqlConfigManager` class with `get()`, `get_int()`, `get_float()`, `set()` methods
9. `AqlService` facade class with `on_inspection_judged()`, `get_profile()`, and `expire_stale_recommendations()` methods (delegates to `RecommendationManager.expire_stale()`)

All methods follow the spec's execution flow (Section 4.3), approval state machine (Section 5), and data flow (Section 7.4).

- [ ] **Step 2: Verify service loads**

Run: `cd backend && python -c "from app.services.iqc_aql_service import AqlService, RuleEngine, RecommendationManager; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/iqc_aql_service.py
git commit -m "feat(iqc-aql): add core service with rule engine and AQL calculation"
```

---

## Task 5: API Routes

**Files:**
- Modify: `backend/app/api/iqc.py`
- Modify: `backend/app/services/iqc_inspection_service.py`

- [ ] **Step 1: Update `judge_inspection` service to accept and persist new fields**

In `backend/app/services/iqc_inspection_service.py`, add parameters to `judge_inspection()`:

```python
async def judge_inspection(
    db: AsyncSession,
    inspection_id: uuid.UUID,
    inspection_result: str,
    defect_qty: int,
    defect_description: str | None,
    sample_qty: int | None,
    user_id: uuid.UUID,
    has_safety_defect: bool = False,
    linked_customer_complaint_id: uuid.UUID | None = None,
) -> IqcInspection:
```

After the existing `inspection.judged_at = datetime.now(timezone.utc)` line, add:

```python
    inspection.has_safety_defect = has_safety_defect
    if linked_customer_complaint_id:
        inspection.linked_customer_complaint_id = linked_customer_complaint_id
```

- [ ] **Step 2: Update `judge_inspection` API route to pass new fields**

In `backend/app/api/iqc.py`, update the judge endpoint call:

```python
    inspection = await iqc_inspection_service.judge_inspection(
        db, inspection_id, req.inspection_result, req.defect_qty,
        req.defect_description, req.sample_qty, user.user_id,
        has_safety_defect=req.has_safety_defect,
        linked_customer_complaint_id=req.linked_customer_complaint_id,
    )
```

- [ ] **Step 3: Add AQL optimization endpoints to `iqc.py`**

Add the following route groups (all under existing `router = APIRouter(prefix="/api/iqc")`):

**Profile routes** (5 endpoints):
- `GET /aql-profiles` — list profiles (paginated, filterable by state/supplier/product_line)
- `POST /aql-profiles` — create profile
- `GET /aql-profiles/{id}` — profile detail
- `PUT /aql-profiles/{id}` — update profile params
- `GET /aql-profiles/{id}/history` — quality snapshot trend

**Recommendation routes** (10 endpoints):
- `GET /aql-recommendations` — list recommendations (paginated, filterable by status/direction)
- `GET /aql-recommendations/{id}` — recommendation detail
- `POST /aql-recommendations/{id}/engineer-approve` — engineer approve (非放宽 only)
- `POST /aql-recommendations/{id}/engineer-reject` — engineer reject
- `POST /aql-recommendations/{id}/forward` — forward to manager (放宽 only)
- `POST /aql-recommendations/{id}/manager-approve` — manager approve
- `POST /aql-recommendations/{id}/manager-reject` — manager reject
- `POST /aql-recommendations/{id}/expired` — mark as expired (engineer)
- `POST /aql-recommendations/trigger` — manual trigger rule evaluation
- `POST /aql-recommendations/preview` — preview recommendation (no DB write)

**Quality snapshot routes** (2 endpoints):
- `GET /aql-quality-snapshot/{supplier_id}/{material_id}` — current snapshot
- `GET /aql-quality-snapshot/{supplier_id}/{material_id}/trend` — historical trend

**Config routes** (3 endpoints):
- `GET /aql-config` — list all configs
- `PUT /aql-config/{key}` — update config (admin only)
- `POST /aql-config/reset` — reset to defaults (admin only)

Permission guards use `require_permission(Module.IQC, ...)` with appropriate levels.

- [ ] **Step 4: Verify routes register**

Run: `cd backend && python -c "from app.api.iqc import router; print(len(router.routes), 'routes')"`
Expected: Route count increased by ~20

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/iqc.py backend/app/services/iqc_inspection_service.py
git commit -m "feat(iqc-aql): add API endpoints for AQL optimization and judge field passthrough"
```

---

## Task 6: Integration — Trigger + AQL Injection + Expiry Cleanup

**Files:**
- Modify: `backend/app/services/iqc_inspection_service.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add dynamic AQL injection to `create_inspection`**

In `iqc_inspection_service.create_inspection()`, replace the AQL auto-calculate block with:

```python
    # Dynamic AQL injection from optimization profile
    if not aql_level and material_id and supplier_id:
        from app.services.iqc_aql_service import AqlService
        aql_svc = AqlService()
        try:
            profile = await aql_svc.get_profile(db, supplier_id, material_id)
            if profile:
                # frozen 状态继续使用 profile.current_aql，不降级
                aql_level = profile.current_aql
        except Exception:
            pass  # Fall through to material default

    # Fallback: load material and use default_aql if no profile set AQL
    if not aql_level and material_id:
        from app.models.iqc_material import IqcMaterial
        material = await db.get(IqcMaterial, material_id)
        if material and material.default_aql:
            aql_level = material.default_aql
```

- [ ] **Step 2: Add rule evaluation trigger to `judge_inspection`**

At the end of `iqc_inspection_service.judge_inspection()`, after the audit log commit:

```python
    # Trigger AQL rule evaluation after judgment
    if inspection.material_id:
        try:
            from app.services.iqc_aql_service import AqlService
            aql_svc = AqlService()
            await aql_svc.on_inspection_judged(db, inspection.supplier_id, inspection.material_id, inspection_id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("AQL rule evaluation failed: %s", e)
```

- [ ] **Step 3: Add expiry cleanup coroutine to `main.py` lifespan**

Add after the ERP sync loop, before `yield`:

```python
    # Start AQL recommendation expiry cleanup loop (daily)
    from app.services.iqc_aql_service import AqlService

    async def _aql_expiry_loop():
        while True:
            await asyncio.sleep(86400)
            try:
                async with async_session() as db:
                    expired = await AqlService.expire_stale_recommendations(db)
                    if expired > 0:
                        logger.info("[aql_optimization] expired %d stale recommendations", expired)
            except Exception as e:
                logger.error("[aql_optimization] expiry error: %s", e)

    aql_expiry_task = asyncio.create_task(_aql_expiry_loop())
```

Where `AqlService.expire_stale_recommendations()` is a `@staticmethod` that delegates to `RecommendationManager.expire_stale()`:

```python
class AqlService:
    @staticmethod
    async def expire_stale_recommendations(db) -> int:
        return await RecommendationManager.expire_stale(db)
```

Add `aql_expiry_task` to the cancellation block at the end of lifespan.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/iqc_inspection_service.py backend/app/main.py
git commit -m "feat(iqc-aql): integrate dynamic AQL injection and rule evaluation trigger"
```

---

## Task 7: Backend Tests

**Files:**
- Create: `backend/tests/test_iqc_aql.py`

- [ ] **Step 1: Write unit tests**

Test the following scenarios in `backend/tests/test_iqc_aql.py`:

1. **`test_get_aql_by_state`** — normal/tightened/reduced/frozen with various base_aql values
2. **`test_get_aql_by_state_frozen_returns_current`** — frozen returns current_aql, not base_aql
3. **`test_get_aql_by_state_aql_steps`** — aql_steps=2 moves 2 ladder positions
4. **`test_get_aql_by_state_boundary`** — min_aql/max_aql constraints applied
5. **`test_rule_engine_safety_defect`** — has_safety_defect → frozen with tighten policy
6. **`test_rule_engine_scar_unresolved`** — open SCAR + reduced → frozen with current policy
7. **`test_rule_engine_1_reject`** — 1 reject → tightened
8. **`test_rule_engine_2_rejects`** — 2 rejects → tightened with aql_steps=2
9. **`test_rule_engine_return_to_normal`** — tightened + 5 accepted → normal
10. **`test_rule_engine_reduce_1`** — normal + 5 accepted → reduced
11. **`test_rule_engine_reduce_2`** — normal + 10 accepted + rating A → reduced aql_steps=2
12. **`test_rule_engine_no_skip_to_reduce`** — tightened + 5 accepted does NOT trigger reduce
13. **`test_rule_engine_keep`** — no matching rule → keep
14. **`test_config_manager`** — get/set with product_line override
15. **`test_approval_flow_engineer_approve`** — engineer approves tighten → approved
16. **`test_approval_flow_forward_to_manager`** — engineer forwards reduce → forwarded → manager approves
17. **`test_approval_flow_reject`** — reject transitions
18. **`test_idempotent_recommendation`** — duplicate (profile+target_state+recommended_aql) suppressed

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_iqc_aql.py -v`
Expected: All 18 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_iqc_aql.py
git commit -m "test(iqc-aql): add unit tests for rule engine and approval flow"
```

---

## Task 8: Frontend Types + API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/iqcAql.ts`

- [ ] **Step 1: Add TypeScript interfaces to `types/index.ts`**

Add at end of file, before last export:

```typescript
// ─── IQC AQL Optimization Types ───

export interface AqlProfile {
  profile_id: string;
  supplier_id: string;
  material_id: string;
  base_aql: number;
  current_aql: number;
  min_aql: number | null;
  max_aql: number | null;
  inspection_level: string;
  state: 'normal' | 'tightened' | 'reduced' | 'frozen';
  frozen_until: string | null;
  frozen_reason: string | null;
  effective_from: string;
  approved_by: string | null;
  approved_at: string | null;
  state_changed_at: string | null;
  product_line_code: string;
  created_at: string;
  updated_at: string;
}

export interface AqlRecommendation {
  recommendation_id: string;
  profile_id: string;
  supplier_id: string;
  material_id: string;
  current_aql: number;
  recommended_aql: number;
  direction: 'keep' | 'reduce' | 'tighten' | 'freeze';
  trigger_rules: { rule_id: string; reason: string }[];
  evidence: Record<string, unknown>;
  status: 'pending' | 'forwarded' | 'approved' | 'effective' | 'rejected' | 'expired';
  approval_level: 'engineer' | 'manager';
  engineer_decision: string | null;
  manager_decision: string | null;
  effective_from: string | null;
  expires_at: string;
  created_at: string;
}

export interface AqlQualitySnapshot {
  snapshot_id: string;
  supplier_id: string;
  material_id: string;
  total_batches: number;
  consecutive_accepted: number;
  consecutive_rejected: number;
  last_30d_ppm: number | null;
  last_90d_ppm: number | null;
  open_scar_count: number;
  supplier_rating: string | null;
  has_safety_defect: boolean;
  calculated_state: string | null;
}

export interface AqlConfig {
  config_id: string;
  config_key: string;
  config_value: string;
  value_type: string;
  description: string | null;
  product_line_code: string | null;
  is_editable: boolean;
}
```

- [ ] **Step 2: Create `frontend/src/api/iqcAql.ts`**

API client with functions for all endpoints:
- `listAqlProfiles`, `createAqlProfile`, `getAqlProfile`, `updateAqlProfile`, `getAqlProfileHistory`
- `listAqlRecommendations`, `getAqlRecommendation`, `engineerApproveRecommendation`, `engineerRejectRecommendation`, `forwardRecommendation`, `managerApproveRecommendation`, `managerRejectRecommendation`, `markRecommendationExpired`, `triggerAqlEvaluation`, `previewAqlRecommendation`
- `getAqlQualitySnapshot`, `getAqlQualitySnapshotTrend`
- `listAqlConfigs`, `updateAqlConfig`, `resetAqlConfigs`

All use the existing `client` axios instance from `./client`.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors related to new types

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/iqcAql.ts
git commit -m "feat(iqc-aql): add frontend types and API client"
```

---

## Task 9: Frontend Pages

**Files:**
- Create: `frontend/src/pages/iqc/AqlOptimizationPage.tsx`
- Create: `frontend/src/pages/iqc/AqlProfileListPage.tsx`
- Create: `frontend/src/pages/iqc/AqlProfileDetailPage.tsx`
- Create: `frontend/src/pages/iqc/AqlConfigPage.tsx`
- Create: `frontend/src/components/iqc/AqlRecommendationDrawer.tsx`
- Create: `frontend/src/components/iqc/AqlQualityChart.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Create `AqlOptimizationPage.tsx`** — 建议列表主页面

Implements spec Section 8.2:
- 4 KPI stat cards (待审批/今日生成/已批准/已拒绝)
- Filter bar (status, direction, supplier search)
- Ant Design Table with columns: 供应商, 物料号, 当前AQL, 建议AQL, 方向(🔴/🟢/🔵), 触发规则, 状态, 操作
- Row click opens `AqlRecommendationDrawer`
- Approval buttons vary by user role (engineer vs manager)
- Batch approve/reject via selection

- [ ] **Step 2: Create `AqlRecommendationDrawer.tsx`** — 建议详情 Drawer

- Full evidence display (quality snapshot data)
- Trigger rules list with reasons
- Approval action buttons (engineer-approve / forward / engineer-reject / manager-approve / manager-reject)
- Mini trend chart (AQL history)

- [ ] **Step 3: Create `AqlProfileListPage.tsx`** — 档案管理列表

- Table of all AQL profiles with state badges
- Filter by state, supplier, product_line
- Click row → navigate to profile detail

- [ ] **Step 4: Create `AqlProfileDetailPage.tsx`** — 档案详情/质量画像

Implements spec Section 8.3:
- Profile overview cards (基准AQL, 当前AQL, 状态, 生效日期)
- Quality snapshot 2-column layout (检验统计, 供应商表现)
- `AqlQualityChart` — AQL + PPM dual-axis trend chart
- Historical recommendations table

- [ ] **Step 5: Create `AqlQualityChart.tsx`** — 趋势图表

- Uses `@ant-design/charts` Mix chart
- Dual Y-axis: AQL (left) + PPM (right)
- X-axis: date

- [ ] **Step 6: Create `AqlConfigPage.tsx`** — 规则参数配置 (admin only)

- Ant Design Form with all config parameters
- Product line selector for override
- Reset to defaults button
- Only visible to admin role

- [ ] **Step 7: Add routes to `App.tsx`**

Add imports and routes under the existing IQC route group:

```tsx
import AqlOptimizationPage from "./pages/iqc/AqlOptimizationPage";
import AqlProfileListPage from "./pages/iqc/AqlProfileListPage";
import AqlProfileDetailPage from "./pages/iqc/AqlProfileDetailPage";
import AqlConfigPage from "./pages/iqc/AqlConfigPage";
```

Add routes:
```tsx
<Route path="/iqc/aql-optimization" element={<ProtectedRoute requiredModule="iqc"><AqlOptimizationPage /></ProtectedRoute>} />
<Route path="/iqc/aql-optimization/profiles" element={<ProtectedRoute requiredModule="iqc"><AqlProfileListPage /></ProtectedRoute>} />
<Route path="/iqc/aql-optimization/profiles/:supplierId/:materialId" element={<ProtectedRoute requiredModule="iqc"><AqlProfileDetailPage /></ProtectedRoute>} />
<Route path="/iqc/aql-optimization/config" element={<ProtectedRoute requiredModule="iqc"><AqlConfigPage /></ProtectedRoute>} />
```

- [ ] **Step 8: Add sidebar menu item to `AppLayout.tsx`**

Add "抽样方案优化" menu item under the IQC submenu with icon and path `/iqc/aql-optimization`.

- [ ] **Step 9: Verify frontend builds**

Run: `cd frontend && npm run build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/iqc/ frontend/src/components/iqc/ frontend/src/api/iqcAql.ts frontend/src/types/index.ts frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(iqc-aql): add frontend pages for AQL optimization"
```

---

## Task 10: ROADMAP Update + Final Verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update ROADMAP.md**

Change `IQC 抽样方案智能优化` row status from `🔲 待开发` to `✅ 完成` with description:

```
基于历史质量动态调整 AQL；组合规则引擎（10 条规则）+ 多级审批（engineer/manager）+ 质量画像 + PPM/SCAR/安全缺陷触发；4 张新表 + 配置化参数；4 页前端；18 条单元测试
```

Add to Phase 4 completed section.

- [ ] **Step 2: Run full backend test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -20`
Expected: All tests pass (existing + new)

- [ ] **Step 3: Run frontend build**

Run: `cd frontend && npm run build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): mark IQC AQL optimization as completed"
```
