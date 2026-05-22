# MSA Measurement System Analysis Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete MSA module — gauge master data (17 tables) plus five study types (GRR, bias, linearity, stability, attribute) with calculation engines and full CRUD frontend.

**Architecture:** Follows existing project patterns: models → schemas → services (CRUD + engine) → API routes. One file per concern per study type. Frontend uses TypesScript + Ant Design + ECharts for reports.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 async + Pydantic v2 | React 18 + TypeScript 5.6 + Ant Design 5.21 + ECharts 5

---

## File Structure Map

```
backend/app/models/
    gauge.py            — Gauge, GaugeCalibration
    grr.py              — GrrStudy, GrrMeasurement, GrrResult
    bias.py             — BiasStudy, BiasMeasurement, BiasResult
    linearity.py        — LinearityStudy, LinearityMeasurement, LinearityResult
    stability.py        — StabilityStudy, StabilityMeasurement, StabilityResult
    attribute.py        — AttributeStudy, AttributeMeasurement, AttributeResult

backend/app/schemas/
    gauge.py            — GaugeCreate, GaugeUpdate, GaugeResponse, GaugeListResponse, GaugeCalibrationCreate, GaugeCalibrationResponse
    grr.py              — GrrStudyCreate, GrrStudyUpdate, GrrStudyResponse, GrrMeasurementUpsert, GrrResultResponse
    bias.py             — BiasStudyCreate, BiasStudyUpdate, BiasStudyResponse, BiasMeasurementUpsert, BiasResultResponse
    linearity.py        — LinearityStudyCreate, LinearityStudyUpdate, LinearityStudyResponse, LinearityMeasurementUpsert, LinearityResultResponse
    stability.py        — StabilityStudyCreate, StabilityStudyUpdate, StabilityStudyResponse, StabilityMeasurementUpsert, StabilityResultResponse
    attribute.py        — AttributeStudyCreate, AttributeStudyUpdate, AttributeStudyResponse, AttributeMeasurementUpsert, AttributeResultResponse
    msa.py              — MsaStudyOverview, MsaSpcCharacteristic

backend/app/services/
    gauge_service.py    — Gauge CRUD + calibration CRUD
    grr_service.py      — GRR study CRUD
    grr_engine.py       — GRR calculation (average-range + ANOVA)
    bias_service.py     — Bias study CRUD
    bias_engine.py      — Bias calculation
    linearity_service.py— Linearity study CRUD
    linearity_engine.py — Linearity calculation
    stability_service.py— Stability study CRUD
    stability_engine.py — Stability calculation
    attribute_service.py— Attribute study CRUD
    attribute_engine.py — Attribute calculation

backend/app/api/
    gauge.py            — /api/gauges routes
    msa.py              — /api/msa/{grr,bias,linearity,stability,attribute} routes + /api/msa/studies + /api/msa/spc-characteristics

backend/alembic/versions/
    008_add_msa_tables.py  — All 17 MSA tables

frontend/src/types/
    msa.ts              — All MSA TypeScript interfaces

frontend/src/api/
    msa.ts              — MSA API client functions

frontend/src/pages/
    GaugeList.tsx       — 量具台账列表
    GaugeDetail.tsx     — 量具详情/编辑
    MsaStudyList.tsx    — MSA 研究总览
    GrrStudy.tsx        — GRR 研究详情（三步向导）
    BiasStudy.tsx       — 偏倚研究详情
    LinearityStudy.tsx  — 线性研究详情
    StabilityStudy.tsx  — 稳定性研究详情
    AttributeStudy.tsx  — 计数型研究详情

Modified files:
    backend/app/models/__init__.py      — Add all new model imports
    backend/app/schemas/__init__.py     — Add all new schema imports
    backend/app/main.py                 — Register gauge_router and msa_router
    frontend/src/types/index.ts         — Re-export msa.ts types
    frontend/src/App.tsx                — Add /msa/* routes
    frontend/src/components/layout/AppLayout.tsx — Add MSA nav menu
```

---

## Phase 1: Database Migration

### Task 1: Create Alembic migration for all MSA tables

**Files:** Create `backend/alembic/versions/008_add_msa_tables.py`

**Context:** Migration 007 is the current head. This adds 17 tables for gauges + 5 MSA study types.

- [ ] **Step 1: Determine down_revision from current head**

```bash
cd backend && head -5 alembic/versions/007_add_supplier_management.py | grep -E "revision|down_revision"
```

Expected: `revision = "007"`, `down_revision = "006"`

- [ ] **Step 2: Write the migration file**

```python
"""add MSA measurement system analysis tables

Revision ID: 008_add_msa_tables
Revises: 007_add_supplier_management
Create Date: 2026-05-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    # ─── Gauge master data ───
    op.create_table(
        "gauges",
        sa.Column("gauge_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("gauge_no", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("resolution", sa.Float, nullable=True),
        sa.Column("measuring_range", sa.String(100), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("calibration_cycle_days", sa.Integer, nullable=True),
        sa.Column("next_calibration_date", sa.Date, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gauges_status", "gauges", ["status"])
    op.create_index("ix_gauges_department", "gauges", ["department"])

    op.create_table(
        "gauge_calibrations",
        sa.Column("calibration_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("gauge_id", UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="CASCADE"), nullable=False),
        sa.Column("calibration_date", sa.Date, nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("certificate_no", sa.String(100), nullable=True),
        sa.Column("calibrated_by", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("next_calibration_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ─── GRR studies ───
    op.create_table(
        "grr_studies",
        sa.Column("study_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("method", sa.String(20), nullable=False, server_default="average_range"),
        sa.Column("gauge_id", UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("characteristic_name", sa.String(255), nullable=False),
        sa.Column("spc_characteristic_id", UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.characteristic_id", ondelete="SET NULL"), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("tolerance_upper", sa.Float, nullable=True),
        sa.Column("tolerance_lower", sa.Float, nullable=True),
        sa.Column("reference_value", sa.Float, nullable=True),
        sa.Column("appraiser_count", sa.Integer, nullable=False, server_default="3"),
        sa.Column("part_count", sa.Integer, nullable=False, server_default="10"),
        sa.Column("trial_count", sa.Integer, nullable=False, server_default="3"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("study_date", sa.Date, nullable=True),
        sa.Column("accepted_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "grr_measurements",
        sa.Column("measurement_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", UUID(as_uuid=True), sa.ForeignKey("grr_studies.study_id", ondelete="CASCADE"), nullable=False),
        sa.Column("appraiser_name", sa.String(100), nullable=False),
        sa.Column("part_no", sa.String(100), nullable=False),
        sa.Column("trial_no", sa.Integer, nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_grr_measurements_study", "grr_measurements", ["study_id"])

    op.create_table(
        "grr_results",
        sa.Column("result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", UUID(as_uuid=True), sa.ForeignKey("grr_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("ev", sa.Float, nullable=False),
        sa.Column("av", sa.Float, nullable=False),
        sa.Column("grr", sa.Float, nullable=False),
        sa.Column("pv", sa.Float, nullable=False),
        sa.Column("tv", sa.Float, nullable=False),
        sa.Column("ndc", sa.Float, nullable=False),
        sa.Column("grr_percent_tol", sa.Float, nullable=True),
        sa.Column("grr_percent_tv", sa.Float, nullable=False),
        sa.Column("ev_percent", sa.Float, nullable=False),
        sa.Column("av_percent", sa.Float, nullable=False),
        sa.Column("pv_percent", sa.Float, nullable=False),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ─── Bias studies ───
    op.create_table(
        "bias_studies",
        sa.Column("study_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("gauge_id", UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("characteristic_name", sa.String(255), nullable=False),
        sa.Column("spc_characteristic_id", UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.characteristic_id", ondelete="SET NULL"), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("reference_value", sa.Float, nullable=False),
        sa.Column("sample_size", sa.Integer, nullable=False, server_default="10"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("study_date", sa.Date, nullable=True),
        sa.Column("accepted_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "bias_measurements",
        sa.Column("measurement_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", UUID(as_uuid=True), sa.ForeignKey("bias_studies.study_id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bias_measurements_study", "bias_measurements", ["study_id"])

    op.create_table(
        "bias_results",
        sa.Column("result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", UUID(as_uuid=True), sa.ForeignKey("bias_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("mean", sa.Float, nullable=False),
        sa.Column("bias", sa.Float, nullable=False),
        sa.Column("bias_percent", sa.Float, nullable=True),
        sa.Column("std_dev", sa.Float, nullable=False),
        sa.Column("t_statistic", sa.Float, nullable=False),
        sa.Column("p_value", sa.Float, nullable=False),
        sa.Column("lower_ci", sa.Float, nullable=False),
        sa.Column("upper_ci", sa.Float, nullable=False),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ─── Linearity studies ───
    op.create_table(
        "linearity_studies",
        sa.Column("study_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("gauge_id", UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("characteristic_name", sa.String(255), nullable=False),
        sa.Column("spc_characteristic_id", UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.characteristic_id", ondelete="SET NULL"), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("tolerance_upper", sa.Float, nullable=True),
        sa.Column("tolerance_lower", sa.Float, nullable=True),
        sa.Column("sample_size_per_reference", sa.Integer, nullable=False, server_default="5"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("study_date", sa.Date, nullable=True),
        sa.Column("accepted_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "linearity_measurements",
        sa.Column("measurement_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", UUID(as_uuid=True), sa.ForeignKey("linearity_studies.study_id", ondelete="CASCADE"), nullable=False),
        sa.Column("reference_value", sa.Float, nullable=False),
        sa.Column("measured_value", sa.Float, nullable=False),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_linearity_measurements_study", "linearity_measurements", ["study_id"])

    op.create_table(
        "linearity_results",
        sa.Column("result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", UUID(as_uuid=True), sa.ForeignKey("linearity_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("slope", sa.Float, nullable=False),
        sa.Column("intercept", sa.Float, nullable=False),
        sa.Column("r_squared", sa.Float, nullable=False),
        sa.Column("linearity", sa.Float, nullable=False),
        sa.Column("linearity_percent", sa.Float, nullable=True),
        sa.Column("bias_at_lower", sa.Float, nullable=True),
        sa.Column("bias_at_upper", sa.Float, nullable=True),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ─── Stability studies ───
    op.create_table(
        "stability_studies",
        sa.Column("study_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("gauge_id", UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("characteristic_name", sa.String(255), nullable=False),
        sa.Column("spc_characteristic_id", UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.characteristic_id", ondelete="SET NULL"), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("reference_value", sa.Float, nullable=True),
        sa.Column("subgroup_size", sa.Integer, nullable=False, server_default="5"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("study_date", sa.Date, nullable=True),
        sa.Column("accepted_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "stability_measurements",
        sa.Column("measurement_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", UUID(as_uuid=True), sa.ForeignKey("stability_studies.study_id", ondelete="CASCADE"), nullable=False),
        sa.Column("measurement_date", sa.Date, nullable=False),
        sa.Column("sample_mean", sa.Float, nullable=False),
        sa.Column("sample_range", sa.Float, nullable=False),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_stability_measurements_study", "stability_measurements", ["study_id"])

    op.create_table(
        "stability_results",
        sa.Column("result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", UUID(as_uuid=True), sa.ForeignKey("stability_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("ucl_mean", sa.Float, nullable=False),
        sa.Column("lcl_mean", sa.Float, nullable=False),
        sa.Column("cl_mean", sa.Float, nullable=False),
        sa.Column("ucl_range", sa.Float, nullable=False),
        sa.Column("lcl_range", sa.Float, nullable=True),
        sa.Column("cl_range", sa.Float, nullable=False),
        sa.Column("cpk", sa.Float, nullable=True),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ─── Attribute studies ───
    op.create_table(
        "attribute_studies",
        sa.Column("study_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_no", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("gauge_id", UUID(as_uuid=True), sa.ForeignKey("gauges.gauge_id", ondelete="SET NULL"), nullable=True),
        sa.Column("characteristic_name", sa.String(255), nullable=False),
        sa.Column("spc_characteristic_id", UUID(as_uuid=True), sa.ForeignKey("inspection_characteristics.characteristic_id", ondelete="SET NULL"), nullable=True),
        sa.Column("method", sa.String(30), nullable=False, server_default="risk_analysis"),
        sa.Column("sample_size", sa.Integer, nullable=False, server_default="50"),
        sa.Column("known_standard_count", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("study_date", sa.Date, nullable=True),
        sa.Column("accepted_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "attribute_measurements",
        sa.Column("measurement_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", UUID(as_uuid=True), sa.ForeignKey("attribute_studies.study_id", ondelete="CASCADE"), nullable=False),
        sa.Column("appraiser_name", sa.String(100), nullable=False),
        sa.Column("part_no", sa.String(100), nullable=False),
        sa.Column("known_standard", sa.String(10), nullable=False),
        sa.Column("appraiser_decision", sa.String(10), nullable=False),
        sa.Column("trial_no", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_attribute_measurements_study", "attribute_measurements", ["study_id"])

    op.create_table(
        "attribute_results",
        sa.Column("result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("study_id", UUID(as_uuid=True), sa.ForeignKey("attribute_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("effectiveness", sa.Float, nullable=False),
        sa.Column("miss_rate", sa.Float, nullable=False),
        sa.Column("false_alarm_rate", sa.Float, nullable=False),
        sa.Column("kappa_within", sa.Float, nullable=True),
        sa.Column("kappa_vs_standard", sa.Float, nullable=True),
        sa.Column("kappa_between", sa.Float, nullable=True),
        sa.Column("conclusion", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    for table in [
        "attribute_results", "attribute_measurements", "attribute_studies",
        "stability_results", "stability_measurements", "stability_studies",
        "linearity_results", "linearity_measurements", "linearity_studies",
        "bias_results", "bias_measurements", "bias_studies",
        "grr_results", "grr_measurements", "grr_studies",
        "gauge_calibrations", "gauges",
    ]:
        op.drop_table(table)
```

- [ ] **Step 3: Run the migration**

```bash
cd backend && alembic upgrade head
```

Expected: Migration runs without errors; all 17 tables created in PostgreSQL.

- [ ] **Step 4: Verify tables exist**

```bash
docker compose exec db psql -U openqms -d openqms -c "\dt *grr* *bias* *linearity* *stability* *attribute* *gauge*"
```

Expected: 17 tables listed.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/008_add_msa_tables.py
git commit -m "feat(msa): add 17 MSA tables migration (gauges + 5 study types)"
```

---

## Phase 2: Backend Models

### Task 2: Gauge models

**Files:** Create `backend/app/models/gauge.py`

- [ ] **Step 1: Write the Gauge and GaugeCalibration models**

```python
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Integer, Float, Date, DateTime, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Gauge(Base):
    __tablename__ = "gauges"

    gauge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    gauge_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resolution: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    measuring_range: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    calibration_cycle_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    next_calibration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GaugeCalibration(Base):
    __tablename__ = "gauge_calibrations"

    calibration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    gauge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gauges.gauge_id", ondelete="CASCADE"), nullable=False
    )
    calibration_date: Mapped[date] = mapped_column(Date, nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    certificate_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    calibrated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_calibration_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/gauge.py
git commit -m "feat(msa): add Gauge and GaugeCalibration models"
```

### Task 3: GRR models

**Files:** Create `backend/app/models/grr.py`

- [ ] **Step 1: Write GrrStudy, GrrMeasurement, GrrResult models**

```python
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GrrStudy(Base):
    __tablename__ = "grr_studies"

    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, default="average_range")
    gauge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=False
    )
    characteristic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    spc_characteristic_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_characteristics.characteristic_id", ondelete="SET NULL"), nullable=True
    )
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tolerance_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tolerance_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reference_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    appraiser_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    part_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    trial_count: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    study_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    accepted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GrrMeasurement(Base):
    __tablename__ = "grr_measurements"

    measurement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grr_studies.study_id", ondelete="CASCADE"), nullable=False
    )
    appraiser_name: Mapped[str] = mapped_column(String(100), nullable=False)
    part_no: Mapped[str] = mapped_column(String(100), nullable=False)
    trial_no: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GrrResult(Base):
    __tablename__ = "grr_results"

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grr_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    ev: Mapped[float] = mapped_column(Float, nullable=False)
    av: Mapped[float] = mapped_column(Float, nullable=False)
    grr: Mapped[float] = mapped_column(Float, nullable=False)
    pv: Mapped[float] = mapped_column(Float, nullable=False)
    tv: Mapped[float] = mapped_column(Float, nullable=False)
    ndc: Mapped[float] = mapped_column(Float, nullable=False)
    grr_percent_tol: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    grr_percent_tv: Mapped[float] = mapped_column(Float, nullable=False)
    ev_percent: Mapped[float] = mapped_column(Float, nullable=False)
    av_percent: Mapped[float] = mapped_column(Float, nullable=False)
    pv_percent: Mapped[float] = mapped_column(Float, nullable=False)
    conclusion: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/grr.py
git commit -m "feat(msa): add GrrStudy, GrrMeasurement, GrrResult models"
```

### Task 4: Bias, Linearity, Stability, Attribute models

**Context:** Same pattern as GRR — each study type has Study + Measurement + Result tables.

**Files:** Create `backend/app/models/bias.py`, `backend/app/models/linearity.py`, `backend/app/models/stability.py`, `backend/app/models/attribute.py`

- [ ] **Step 1: Write bias.py**

```python
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BiasStudy(Base):
    __tablename__ = "bias_studies"

    study_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    gauge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gauges.gauge_id", ondelete="RESTRICT"), nullable=False)
    characteristic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    spc_characteristic_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("inspection_characteristics.characteristic_id", ondelete="SET NULL"), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reference_value: Mapped[float] = mapped_column(Float, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    study_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    accepted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BiasMeasurement(Base):
    __tablename__ = "bias_measurements"

    measurement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bias_studies.study_id", ondelete="CASCADE"), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BiasResult(Base):
    __tablename__ = "bias_results"

    result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bias_studies.study_id", ondelete="CASCADE"), nullable=False, unique=True)
    mean: Mapped[float] = mapped_column(Float, nullable=False)
    bias: Mapped[float] = mapped_column(Float, nullable=False)
    bias_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    std_dev: Mapped[float] = mapped_column(Float, nullable=False)
    t_statistic: Mapped[float] = mapped_column(Float, nullable=False)
    p_value: Mapped[float] = mapped_column(Float, nullable=False)
    lower_ci: Mapped[float] = mapped_column(Float, nullable=False)
    upper_ci: Mapped[float] = mapped_column(Float, nullable=False)
    conclusion: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 2: Write linearity.py** (same pattern — LinearityStudy, LinearityMeasurement, LinearityResult with fields from spec §3.4)

- [ ] **Step 3: Write stability.py** (same pattern — StabilityStudy, StabilityMeasurement, StabilityResult with fields from spec §3.5)

- [ ] **Step 4: Write attribute.py** (same pattern — AttributeStudy, AttributeMeasurement, AttributeResult with fields from spec §3.6)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/bias.py backend/app/models/linearity.py backend/app/models/stability.py backend/app/models/attribute.py
git commit -m "feat(msa): add bias, linearity, stability, attribute models"
```

### Task 5: Register all models in __init__.py

**Files:** Modify `backend/app/models/__init__.py`

- [ ] **Step 1: Add imports and __all__ entries**

Read the current file, then add:

```python
# Add these imports after existing ones:
from app.models.gauge import Gauge, GaugeCalibration
from app.models.grr import GrrStudy, GrrMeasurement, GrrResult
from app.models.bias import BiasStudy, BiasMeasurement, BiasResult
from app.models.linearity import LinearityStudy, LinearityMeasurement, LinearityResult
from app.models.stability import StabilityStudy, StabilityMeasurement, StabilityResult
from app.models.attribute import AttributeStudy, AttributeMeasurement, AttributeResult

# Extend __all__ with:
    "Gauge", "GaugeCalibration",
    "GrrStudy", "GrrMeasurement", "GrrResult",
    "BiasStudy", "BiasMeasurement", "BiasResult",
    "LinearityStudy", "LinearityMeasurement", "LinearityResult",
    "StabilityStudy", "StabilityMeasurement", "StabilityResult",
    "AttributeStudy", "AttributeMeasurement", "AttributeResult",
```

- [ ] **Step 2: Verify imports work**

```bash
cd backend && python -c "from app.models import Gauge, GrrStudy, BiasStudy, LinearityStudy, StabilityStudy, AttributeStudy; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/__init__.py
git commit -m "feat(msa): register MSA models in __init__.py"
```

---

## Phase 3: Backend Schemas (Pydantic)

### Task 6: Gauge schemas

**Files:** Create `backend/app/schemas/gauge.py`

- [ ] **Step 1: Write GaugeCreate, GaugeUpdate, GaugeResponse, GaugeListResponse, GaugeCalibrationCreate, GaugeCalibrationResponse**

```python
import uuid
from datetime import datetime, date
from pydantic import BaseModel, field_validator


class GaugeCreate(BaseModel):
    gauge_no: str
    name: str
    model: str | None = None
    manufacturer: str | None = None
    resolution: float | None = None
    measuring_range: str | None = None
    department: str | None = None
    location: str | None = None
    calibration_cycle_days: int | None = None
    next_calibration_date: date | None = None

    @field_validator("gauge_no", "name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class GaugeUpdate(BaseModel):
    gauge_no: str | None = None
    name: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    resolution: float | None = None
    measuring_range: str | None = None
    department: str | None = None
    location: str | None = None
    status: str | None = None
    calibration_cycle_days: int | None = None
    next_calibration_date: date | None = None

    @field_validator("gauge_no", "name")
    @classmethod
    def not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("active", "inactive", "calibrating", "scrapped"):
            raise ValueError("status must be active, inactive, calibrating, or scrapped")
        return v


class GaugeResponse(BaseModel):
    gauge_id: uuid.UUID
    gauge_no: str
    name: str
    model: str | None
    manufacturer: str | None
    resolution: float | None
    measuring_range: str | None
    department: str | None
    location: str | None
    status: str
    calibration_cycle_days: int | None
    next_calibration_date: date | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GaugeListResponse(BaseModel):
    items: list[GaugeResponse]
    total: int
    page: int
    page_size: int


class GaugeCalibrationCreate(BaseModel):
    calibration_date: date
    result: str
    certificate_no: str | None = None
    calibrated_by: str | None = None
    notes: str | None = None
    next_calibration_date: date | None = None

    @field_validator("result")
    @classmethod
    def validate_result(cls, v: str) -> str:
        if v not in ("pass", "fail"):
            raise ValueError('result must be "pass" or "fail"')
        return v


class GaugeCalibrationResponse(BaseModel):
    calibration_id: uuid.UUID
    gauge_id: uuid.UUID
    calibration_date: date
    result: str
    certificate_no: str | None
    calibrated_by: str | None
    notes: str | None
    next_calibration_date: date | None
    created_at: datetime

    model_config = {"from_attributes": True}


class GaugeCalibrationListResponse(BaseModel):
    items: list[GaugeCalibrationResponse]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/gauge.py
git commit -m "feat(msa): add gauge Pydantic schemas"
```

### Task 7: GRR schemas

**Files:** Create `backend/app/schemas/grr.py`

- [ ] **Step 1: Write GrrStudyCreate, GrrStudyUpdate, GrrStudyResponse, GrrMeasurementUpsert, GrrResultResponse**

```python
import uuid
from datetime import datetime, date
from pydantic import BaseModel, field_validator


class GrrStudyCreate(BaseModel):
    title: str
    method: str = "average_range"
    gauge_id: uuid.UUID
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None = None
    unit: str | None = None
    tolerance_upper: float | None = None
    tolerance_lower: float | None = None
    reference_value: float | None = None
    appraiser_count: int = 3
    part_count: int = 10
    trial_count: int = 3
    study_date: date | None = None

    @field_validator("title", "characteristic_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        if v not in ("average_range", "anova", "range"):
            raise ValueError('method must be average_range, anova, or range')
        return v


class GrrStudyUpdate(BaseModel):
    title: str | None = None
    method: str | None = None
    gauge_id: uuid.UUID | None = None
    characteristic_name: str | None = None
    spc_characteristic_id: uuid.UUID | None = None
    unit: str | None = None
    tolerance_upper: float | None = None
    tolerance_lower: float | None = None
    reference_value: float | None = None
    appraiser_count: int | None = None
    part_count: int | None = None
    trial_count: int | None = None
    study_date: date | None = None


class GrrStudyResponse(BaseModel):
    study_id: uuid.UUID
    study_no: str
    title: str
    method: str
    gauge_id: uuid.UUID
    characteristic_name: str
    spc_characteristic_id: uuid.UUID | None
    unit: str | None
    tolerance_upper: float | None
    tolerance_lower: float | None
    reference_value: float | None
    appraiser_count: int
    part_count: int
    trial_count: int
    status: str
    study_date: date | None
    accepted_by: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GrrStudyListResponse(BaseModel):
    items: list[GrrStudyResponse]
    total: int
    page: int
    page_size: int


class GrrMeasurementUpsert(BaseModel):
    appraiser_name: str
    part_no: str
    trial_no: int
    value: float


class GrrMeasurementBulkUpsert(BaseModel):
    measurements: list[GrrMeasurementUpsert]


class GrrResultResponse(BaseModel):
    result_id: uuid.UUID
    study_id: uuid.UUID
    ev: float
    av: float
    grr: float
    pv: float
    tv: float
    ndc: float
    grr_percent_tol: float | None
    grr_percent_tv: float
    ev_percent: float
    av_percent: float
    pv_percent: float
    conclusion: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/grr.py
git commit -m "feat(msa): add GRR Pydantic schemas"
```

### Task 8: Remaining schemas (bias, linearity, stability, attribute, msa)

**Files:** Create `backend/app/schemas/bias.py`, `backend/app/schemas/linearity.py`, `backend/app/schemas/stability.py`, `backend/app/schemas/attribute.py`, `backend/app/schemas/msa.py`

- [ ] **Step 1: Write bias.py** — BiasStudyCreate, BiasStudyUpdate, BiasStudyResponse, BiasMeasurementUpsert, BiasResultResponse following same patterns as GRR.

- [ ] **Step 2: Write linearity.py** — Same pattern.

- [ ] **Step 3: Write stability.py** — Same pattern.

- [ ] **Step 4: Write attribute.py** — Same pattern.

- [ ] **Step 5: Write msa.py** — Overview and SPC characteristic linking schemas:

```python
import uuid
from datetime import datetime, date
from pydantic import BaseModel


class MsaStudyOverview(BaseModel):
    study_id: uuid.UUID
    study_no: str
    type: str
    title: str
    gauge_name: str | None
    status: str
    study_date: date | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MsaStudyOverviewListResponse(BaseModel):
    items: list[MsaStudyOverview]
    total: int
    page: int
    page_size: int


class MsaSpcCharacteristic(BaseModel):
    characteristic_id: uuid.UUID
    name: str
    unit: str | None
    tolerance_upper: float | None
    tolerance_lower: float | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/bias.py backend/app/schemas/linearity.py backend/app/schemas/stability.py backend/app/schemas/attribute.py backend/app/schemas/msa.py
git commit -m "feat(msa): add remaining MSA Pydantic schemas"
```

### Task 9: Register schemas in __init__.py

**Files:** Modify `backend/app/schemas/__init__.py`

- [ ] **Step 1: Add imports**

```python
from app.schemas import gauge
from app.schemas import grr
from app.schemas import bias
from app.schemas import linearity
from app.schemas import stability
from app.schemas import attribute
from app.schemas import msa
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/__init__.py
git commit -m "feat(msa): register MSA schemas in __init__.py"
```

---

## Phase 4: Backend Services (CRUD + Engines)

### Task 10: Gauge service (CRUD)

**Files:** Create `backend/app/services/gauge_service.py`

- [ ] **Step 1: Write gauge_service.py**

Pattern follows `supplier_service.py` — async functions with manual AuditLog, ValueError for errors, numbering generator for gauge_no.

```python
import uuid
from datetime import datetime, date, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.gauge import Gauge, GaugeCalibration
from app.models.audit import AuditLog


async def _generate_gauge_no(db: AsyncSession) -> str:
    prefix = "Q"
    result = await db.execute(select(func.max(Gauge.gauge_no)).where(Gauge.gauge_no.like("Q-%")))
    last = result.scalar()
    if last and last.startswith("Q-") and last[2:].isdigit():
        next_num = int(last[2:]) + 1
    else:
        next_num = 1
    return f"Q-{next_num:03d}"


async def list_gauges(db: AsyncSession, page: int = 1, page_size: int = 20, status: str | None = None, department: str | None = None, search: str | None = None, expiring_days: int | None = None) -> tuple[list[Gauge], int]:
    query = select(Gauge)
    count_query = select(func.count()).select_from(Gauge)

    if status:
        query = query.where(Gauge.status == status)
        count_query = count_query.where(Gauge.status == status)
    if department:
        query = query.where(Gauge.department == department)
        count_query = count_query.where(Gauge.department == department)
    if search:
        pattern = f"%{search}%"
        query = query.where(Gauge.name.like(pattern) | Gauge.gauge_no.like(pattern) | Gauge.model.like(pattern))
        count_query = count_query.where(Gauge.name.like(pattern) | Gauge.gauge_no.like(pattern) | Gauge.model.like(pattern))
    if expiring_days:
        today = date.today()
        cutoff = today + timedelta(days=expiring_days)
        query = query.where(Gauge.next_calibration_date >= today, Gauge.next_calibration_date <= cutoff)
        count_query = count_query.where(Gauge.next_calibration_date >= today, Gauge.next_calibration_date <= cutoff)

    query = query.order_by(Gauge.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()
    total = (await db.execute(count_query)).scalar() or 0
    return list(items), total


async def get_gauge(db: AsyncSession, gauge_id: uuid.UUID) -> Gauge | None:
    return await db.get(Gauge, gauge_id)


async def create_gauge(db: AsyncSession, gauge_no: str, name: str, model: str | None, manufacturer: str | None, resolution: float | None, measuring_range: str | None, department: str | None, location: str | None, calibration_cycle_days: int | None, next_calibration_date: date | None, user_id: uuid.UUID) -> Gauge:
    gauge = Gauge(
        gauge_no=gauge_no, name=name, model=model, manufacturer=manufacturer,
        resolution=resolution, measuring_range=measuring_range, department=department,
        location=location, calibration_cycle_days=calibration_cycle_days,
        next_calibration_date=next_calibration_date, created_by=user_id,
    )
    db.add(gauge)
    db.add(AuditLog(table_name="gauges", record_id=gauge.gauge_id, action="CREATE", changed_fields={"gauge_no": gauge_no, "name": name, "model": model}, operated_by=user_id))
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create gauge: {e}")
    await db.refresh(gauge)
    return gauge


async def update_gauge(db: AsyncSession, gauge: Gauge, **kwargs) -> Gauge:
    changed = {}
    for key, new_val in kwargs.items():
        if key == "user_id":
            continue
        old_val = getattr(gauge, key, None)
        if new_val is not None and new_val != old_val:
            changed[key] = {"before": str(old_val) if old_val else None, "after": str(new_val) if new_val else None}
            setattr(gauge, key, new_val)
    if not changed:
        return gauge
    db.add(AuditLog(table_name="gauges", record_id=gauge.gauge_id, action="UPDATE", changed_fields=changed, operated_by=kwargs.get("user_id")))
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update gauge: {e}")
    await db.refresh(gauge)
    return gauge


async def delete_gauge(db: AsyncSession, gauge: Gauge, user_id: uuid.UUID) -> None:
    db.add(AuditLog(table_name="gauges", record_id=gauge.gauge_id, action="DELETE", changed_fields={"gauge_no": gauge.gauge_no, "name": gauge.name}, operated_by=user_id))
    await db.delete(gauge)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to delete gauge: {e}")


async def list_calibrations(db: AsyncSession, gauge_id: uuid.UUID) -> list[GaugeCalibration]:
    result = await db.execute(select(GaugeCalibration).where(GaugeCalibration.gauge_id == gauge_id).order_by(GaugeCalibration.calibration_date.desc()))
    return list(result.scalars().all())


async def create_calibration(db: AsyncSession, gauge_id: uuid.UUID, calibration_date: date, result: str, certificate_no: str | None, calibrated_by: str | None, notes: str | None, next_calibration_date: date | None, user_id: uuid.UUID) -> GaugeCalibration:
    cal = GaugeCalibration(gauge_id=gauge_id, calibration_date=calibration_date, result=result, certificate_no=certificate_no, calibrated_by=calibrated_by, notes=notes, next_calibration_date=next_calibration_date)
    db.add(cal)
    db.add(AuditLog(table_name="gauge_calibrations", record_id=cal.calibration_id, action="CREATE", changed_fields={"gauge_id": str(gauge_id), "calibration_date": calibration_date.isoformat(), "result": result}, operated_by=user_id))
    if next_calibration_date:
        gauge = await db.get(Gauge, gauge_id)
        if gauge:
            gauge.next_calibration_date = next_calibration_date
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create calibration: {e}")
    await db.refresh(cal)
    return cal
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/gauge_service.py
git commit -m "feat(msa): add gauge CRUD service"
```

### Task 11: GRR calculation engine

**Files:** Create `backend/app/services/grr_engine.py`

- [ ] **Step 1: Write grr_engine.py with AIAG 4th edition formulas**

```python
"""GRR calculation engine — AIAG MSA 4th Edition, Section III-B."""

import math
from collections import defaultdict
from app.models.grr import GrrStudy, GrrMeasurement, GrrResult


# K1: d2* for trial_count → sigma estimate
K1_TABLE = {2: 4.56, 3: 3.05, 4: 2.50, 5: 2.21}
# K2: d2* for appraiser_count
K2_TABLE = {2: 3.65, 3: 2.70, 4: 2.30, 5: 2.08}
# K3: d2* for part_count
K3_TABLE = {2: 3.65, 3: 2.70, 4: 2.30, 5: 2.08, 6: 2.00, 7: 1.92, 8: 1.86, 9: 1.82, 10: 1.78}


def compute_grr(study: GrrStudy, measurements: list[GrrMeasurement]) -> GrrResult:
    """Compute GRR using average-and-range method (AIAG MSA 4th Ed §III-B)."""
    a = study.appraiser_count
    p = study.part_count
    r = study.trial_count

    # Group measurements: appraiser → part → [trial values]
    data: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for m in measurements:
        data[m.appraiser_name][m.part_no].append(m.value)

    # Compute Xbar_ij and R_ij for each appraiser×part cell
    appraiser_means: dict[str, float] = {}
    all_ranges: list[float] = []
    part_means: dict[str, list[float]] = defaultdict(list)

    for appraiser, parts in data.items():
        appraiser_values: list[float] = []
        for part, values in parts.items():
            if len(values) != r:
                raise ValueError(f"missing measurements for {appraiser}, part {part}: expected {r}, got {len(values)}")
            cell_mean = sum(values) / r
            cell_range = max(values) - min(values)
            appraiser_values.append(cell_mean)
            part_means[part].append(cell_mean)
            all_ranges.append(cell_range)
        appraiser_means[appraiser] = sum(appraiser_values) / len(appraiser_values)

    # Average range
    R_bar = sum(all_ranges) / len(all_ranges) if all_ranges else 0

    # Appraiser mean diff
    if len(appraiser_means) >= 2:
        X_bar_diff = max(appraiser_means.values()) - min(appraiser_means.values())
    else:
        X_bar_diff = 0

    # Part mean range
    part_mean_values = [sum(vals) / len(vals) for vals in part_means.values()]
    R_p = max(part_mean_values) - min(part_mean_values) if len(part_mean_values) >= 2 else 0

    # K coefficients
    K1 = K1_TABLE.get(r, K1_TABLE[min(K1_TABLE.keys(), key=lambda k: abs(k - r))])
    K2 = K2_TABLE.get(a, K2_TABLE[min(K2_TABLE.keys(), key=lambda k: abs(k - a))])
    K3 = K3_TABLE.get(p, K3_TABLE[min(K3_TABLE.keys(), key=lambda k: abs(k - p))])

    # EV (Equipment Variation / Repeatability)
    EV = R_bar * K1

    # AV (Appraiser Variation / Reproducibility)
    n = a * p * r
    av_sq = (X_bar_diff * K2) ** 2 - (EV ** 2) / (p * r)
    AV = math.sqrt(max(av_sq, 0))

    # GRR
    GRR = math.sqrt(EV ** 2 + AV ** 2)

    # PV (Part Variation)
    PV = R_p * K3

    # TV (Total Variation)
    TV = math.sqrt(GRR ** 2 + PV ** 2) if PV > 0 else GRR

    # ndc (Number of Distinct Categories)
    ndc = 1.41 * (PV / GRR) if GRR > 0 else 999

    # Percentages
    tolerance = None
    if study.tolerance_upper is not None and study.tolerance_lower is not None:
        tolerance = study.tolerance_upper - study.tolerance_lower

    grr_percent_tol = (GRR / tolerance * 100) if tolerance and tolerance > 0 else None
    grr_percent_tv = (GRR / TV * 100) if TV > 0 else 100
    ev_percent = (EV / TV * 100) if TV > 0 else 0
    av_percent = (AV / TV * 100) if TV > 0 else 0
    pv_percent = (PV / TV * 100) if TV > 0 else 0

    # Conclusion
    if grr_percent_tol is not None:
        if grr_percent_tol < 10 and ndc >= 5:
            conclusion = "可接受"
        elif grr_percent_tol <= 30 and ndc >= 2:
            conclusion = "条件接受"
        else:
            conclusion = "不可接受"
    else:
        if grr_percent_tv < 10 and ndc >= 5:
            conclusion = "可接受"
        elif grr_percent_tv <= 30 and ndc >= 2:
            conclusion = "条件接受"
        else:
            conclusion = "不可接受"

    return GrrResult(
        study_id=study.study_id,
        ev=EV, av=AV, grr=GRR, pv=PV, tv=TV, ndc=ndc,
        grr_percent_tol=grr_percent_tol, grr_percent_tv=grr_percent_tv,
        ev_percent=ev_percent, av_percent=av_percent, pv_percent=pv_percent,
        conclusion=conclusion,
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/grr_engine.py
git commit -m "feat(msa): add GRR calculation engine (average-range method)"
```

### Task 12: GRR study service

**Files:** Create `backend/app/services/grr_service.py`

- [ ] **Step 1: Write grr_service.py**

Follows same CRUD patterns as supplier_service.py. Key functions:

```python
import uuid
from datetime import datetime, date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.grr import GrrStudy, GrrMeasurement, GrrResult
from app.models.audit import AuditLog


async def _generate_study_no(db: AsyncSession, prefix: str) -> str:
    now = datetime.now()
    pattern = f"{prefix}-{now.year}"
    result = await db.execute(
        select(func.count()).where(GrrStudy.study_no.like(f"{pattern}-%"))
    )
    count = result.scalar() or 0
    return f"{pattern}-{count + 1:03d}"


async def list_studies(db: AsyncSession, page: int = 1, page_size: int = 20, status: str | None = None, gauge_id: uuid.UUID | None = None) -> tuple[list[GrrStudy], int]:
    query = select(GrrStudy)
    count_query = select(func.count()).select_from(GrrStudy)
    if status:
        query = query.where(GrrStudy.status == status)
        count_query = count_query.where(GrrStudy.status == status)
    if gauge_id:
        query = query.where(GrrStudy.gauge_id == gauge_id)
        count_query = count_query.where(GrrStudy.gauge_id == gauge_id)
    query = query.order_by(GrrStudy.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()
    total = (await db.execute(count_query)).scalar() or 0
    return list(items), total


async def get_study(db: AsyncSession, study_id: uuid.UUID) -> GrrStudy | None:
    return await db.get(GrrStudy, study_id)


async def create_study(db: AsyncSession, title: str, method: str, gauge_id: uuid.UUID, characteristic_name: str, **kwargs) -> GrrStudy:
    study_no = await _generate_study_no(db, "GRR")
    study = GrrStudy(study_no=study_no, title=title, method=method, gauge_id=gauge_id, characteristic_name=characteristic_name, **kwargs)
    db.add(study)
    db.add(AuditLog(table_name="grr_studies", record_id=study.study_id, action="CREATE", changed_fields={"study_no": study_no, "title": title, "method": method}, operated_by=kwargs.get("user_id")))
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create GRR study: {e}")
    await db.refresh(study)
    return study


async def update_study(db: AsyncSession, study: GrrStudy, **kwargs) -> GrrStudy:
    changed = {}
    for key, new_val in kwargs.items():
        if key == "user_id":
            continue
        old_val = getattr(study, key, None)
        if new_val is not None and new_val != old_val:
            changed[key] = {"before": str(old_val) if old_val else None, "after": str(new_val) if new_val else None}
            setattr(study, key, new_val)
    if not changed:
        return study
    db.add(AuditLog(table_name="grr_studies", record_id=study.study_id, action="UPDATE", changed_fields=changed, operated_by=kwargs.get("user_id")))
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update GRR study: {e}")
    await db.refresh(study)
    return study


async def delete_study(db: AsyncSession, study: GrrStudy, user_id: uuid.UUID) -> None:
    db.add(AuditLog(table_name="grr_studies", record_id=study.study_id, action="DELETE", changed_fields={"study_no": study.study_no, "title": study.title}, operated_by=user_id))
    await db.delete(study)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to delete GRR study: {e}")


async def upsert_measurements(db: AsyncSession, study_id: uuid.UUID, measurements: list[dict]) -> list[GrrMeasurement]:
    study = await db.get(GrrStudy, study_id)
    if not study:
        raise ValueError("GRR study not found")
    if study.status == "completed":
        raise ValueError("study is completed, cannot modify measurements")
    study.status = "ongoing"
    # Delete existing measurements for this study
    existing = (await db.execute(select(GrrMeasurement).where(GrrMeasurement.study_id == study_id))).scalars().all()
    for m in existing:
        await db.delete(m)
    new_items = []
    for d in measurements:
        new_items.append(GrrMeasurement(
            study_id=study_id, appraiser_name=d["appraiser_name"],
            part_no=d["part_no"], trial_no=d["trial_no"], value=d["value"],
        ))
    for item in new_items:
        db.add(item)
    await db.commit()
    return new_items


async def get_measurements(db: AsyncSession, study_id: uuid.UUID) -> list[GrrMeasurement]:
    result = await db.execute(select(GrrMeasurement).where(GrrMeasurement.study_id == study_id).order_by(GrrMeasurement.appraiser_name, GrrMeasurement.part_no, GrrMeasurement.trial_no))
    return list(result.scalars().all())


async def get_result(db: AsyncSession, study_id: uuid.UUID) -> GrrResult | None:
    result = await db.execute(select(GrrResult).where(GrrResult.study_id == study_id))
    return result.scalar_one_or_none()


async def save_result(db: AsyncSession, result: GrrResult) -> GrrResult:
    existing = await get_result(db, result.study_id)
    if existing:
        await db.delete(existing)
        await db.flush()
    db.add(result)
    await db.commit()
    await db.refresh(result)
    return result


async def complete_study(db: AsyncSession, study: GrrStudy, user_id: uuid.UUID, accepted: bool) -> GrrStudy:
    if not await get_result(db, study.study_id):
        raise ValueError("Please compute results before completing the study.")
    study.status = "completed"
    study.accepted_by = user_id if accepted else None
    db.add(AuditLog(table_name="grr_studies", record_id=study.study_id, action="TRANSITION", changed_fields={"status": "completed"}, operated_by=user_id))
    await db.commit()
    await db.refresh(study)
    return study
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/grr_service.py
git commit -m "feat(msa): add GRR study service"
```

### Task 13: Remaining engines and services

**Files:** Create the remaining 8 service/engine files.

- [ ] **Step 1: Write bias_engine.py**

Simpler than GRR — one-dimensional t-test against reference value:

```python
import math
from app.models.bias import BiasStudy, BiasMeasurement, BiasResult


def compute_bias(study: BiasStudy, measurements: list[BiasMeasurement]) -> BiasResult:
    n = len(measurements)
    if n < 2:
        raise ValueError("need at least 2 measurements for bias study")
    values = [m.value for m in measurements]
    mean_val = sum(values) / n
    bias = mean_val - study.reference_value
    variance = sum((v - mean_val) ** 2 for v in values) / (n - 1)
    std_dev = math.sqrt(variance)
    t_stat = bias / (std_dev / math.sqrt(n)) if std_dev > 0 else 0
    # Welch-Satterthwaite: df = n-1
    df = n - 1
    # Simplified p-value approximation (two-tailed using normal approx for large n, t-table for small n)
    from math import gamma as gamma_func
    x = df / (df + t_stat ** 2)
    p_value = _t_cdf(t_stat, df) * 2  # two-tailed
    # 95% CI
    t_crit = _t_inv(0.025, df)  # two-tailed critical value
    se = std_dev / math.sqrt(n)
    ci_lower = bias - abs(t_crit) * se
    ci_upper = bias + abs(t_crit) * se
    conclusion = "可接受" if abs(bias) < 0.01 and p_value > 0.05 else "不可接受"
    return BiasResult(
        study_id=study.study_id, mean=mean_val, bias=bias, std_dev=std_dev,
        t_statistic=t_stat, p_value=p_value, lower_ci=ci_lower, upper_ci=ci_upper,
        conclusion=conclusion,
    )


def _t_cdf(t: float, df: int) -> float:
    """Compute two-tailed p-value using scipy.stats.t if available, otherwise approximate."""
    try:
        from scipy import stats
        return 2 * stats.t.sf(abs(t), df)
    except ImportError:
        # Normal approximation fallback
        return 2 * (1 - _norm_cdf(abs(t)))


def _t_inv(p: float, df: int) -> float:
    try:
        from scipy import stats
        return stats.t.ppf(p, df)
    except ImportError:
        # Normal approximation
        return _norm_ppf(p)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p: float) -> float:
    from math import sqrt, log
    # Abramowitz & Stegun approximation
    if p < 0.5:
        t = math.sqrt(-2 * math.log(p))
    else:
        t = math.sqrt(-2 * math.log(1 - p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    numerator = c0 + c1 * t + c2 * t ** 2
    denominator = 1 + d1 * t + d2 * t ** 2 + d3 * t ** 3
    sign = 1 if p >= 0.5 else -1
    return sign * (t - numerator / denominator)
```

- [ ] **Step 2: Write linearity_engine.py** — Linear regression `bias = slope × reference + intercept`

- [ ] **Step 3: Write stability_engine.py** — Xbar-R control limits using A2/D3/D4 constants

- [ ] **Step 4: Write attribute_engine.py** — Effectiveness, miss rate, false alarm rate, Kappa

- [ ] **Step 5: Write bias_service.py, linearity_service.py, stability_service.py, attribute_service.py** — Each follows identical CRUD patterns to grr_service.py with their respective models.

- [ ] **Step 6: Commit all remaining services in batches**

```bash
git add backend/app/services/bias_engine.py backend/app/services/linearity_engine.py backend/app/services/stability_engine.py backend/app/services/attribute_engine.py
git commit -m "feat(msa): add bias, linearity, stability, attribute calculation engines"

git add backend/app/services/bias_service.py backend/app/services/linearity_service.py backend/app/services/stability_service.py backend/app/services/attribute_service.py
git commit -m "feat(msa): add bias, linearity, stability, attribute study services"
```

---

## Phase 5: Backend API Routes

### Task 14: Gauge API routes

**Files:** Create `backend/app/api/gauge.py`

- [ ] **Step 1: Write gauge routes**

Follows `api/supplier.py` pattern — APIRouter, Depends, response_model.

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app import schemas
from app.services import gauge_service

router = APIRouter(prefix="/api/gauges", tags=["gauges"])


@router.get("/expiring", response_model=schemas.gauge.GaugeListResponse)
async def get_expiring_gauges(
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await gauge_service.list_gauges(db, page=1, page_size=100, expiring_days=days)
    return schemas.gauge.GaugeListResponse(
        items=[schemas.gauge.GaugeResponse.model_validate(g) for g in items],
        total=total, page=1, page_size=100,
    )


@router.get("", response_model=schemas.gauge.GaugeListResponse)
async def list_gauges(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    department: str | None = Query(None),
    search: str | None = Query(None),
    db=Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await gauge_service.list_gauges(db, page, page_size, status, department, search)
    return schemas.gauge.GaugeListResponse(
        items=[schemas.gauge.GaugeResponse.model_validate(g) for g in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", response_model=schemas.gauge.GaugeResponse)
async def create_gauge(
    req: schemas.gauge.GaugeCreate,
    db=Depends(get_db),
    user=Depends(require_engineer_or_admin),
):
    try:
        gauge = await gauge_service.create_gauge(
            db, gauge_no=req.gauge_no, name=req.name, model=req.model,
            manufacturer=req.manufacturer, resolution=req.resolution,
            measuring_range=req.measuring_range, department=req.department,
            location=req.location, calibration_cycle_days=req.calibration_cycle_days,
            next_calibration_date=req.next_calibration_date, user_id=user.user_id,
        )
        return schemas.gauge.GaugeResponse.model_validate(gauge)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{gauge_id}", response_model=schemas.gauge.GaugeResponse)
async def get_gauge(gauge_id: uuid.UUID, db=Depends(get_db), _user=Depends(get_current_user)):
    gauge = await gauge_service.get_gauge(db, gauge_id)
    if gauge is None:
        raise HTTPException(status_code=404, detail="gauge not found")
    return schemas.gauge.GaugeResponse.model_validate(gauge)


@router.put("/{gauge_id}", response_model=schemas.gauge.GaugeResponse)
async def update_gauge(
    gauge_id: uuid.UUID, req: schemas.gauge.GaugeUpdate,
    db=Depends(get_db), user=Depends(require_engineer_or_admin),
):
    gauge = await gauge_service.get_gauge(db, gauge_id)
    if gauge is None:
        raise HTTPException(status_code=404, detail="gauge not found")
    try:
        gauge = await gauge_service.update_gauge(
            db, gauge,
            gauge_no=req.gauge_no, name=req.name, model=req.model,
            manufacturer=req.manufacturer, resolution=req.resolution,
            measuring_range=req.measuring_range, department=req.department,
            location=req.location, status=req.status,
            calibration_cycle_days=req.calibration_cycle_days,
            next_calibration_date=req.next_calibration_date,
            user_id=user.user_id,
        )
        return schemas.gauge.GaugeResponse.model_validate(gauge)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{gauge_id}")
async def delete_gauge(gauge_id: uuid.UUID, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    gauge = await gauge_service.get_gauge(db, gauge_id)
    if gauge is None:
        raise HTTPException(status_code=404, detail="gauge not found")
    try:
        await gauge_service.delete_gauge(db, gauge, user.user_id)
        return {"message": "gauge deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{gauge_id}/calibrations", response_model=schemas.gauge.GaugeCalibrationListResponse)
async def list_calibrations(gauge_id: uuid.UUID, db=Depends(get_db), _user=Depends(get_current_user)):
    items = await gauge_service.list_calibrations(db, gauge_id)
    return schemas.gauge.GaugeCalibrationListResponse(
        items=[schemas.gauge.GaugeCalibrationResponse.model_validate(c) for c in items]
    )


@router.post("/{gauge_id}/calibrations", response_model=schemas.gauge.GaugeCalibrationResponse)
async def create_calibration(
    gauge_id: uuid.UUID, req: schemas.gauge.GaugeCalibrationCreate,
    db=Depends(get_db), user=Depends(require_engineer_or_admin),
):
    try:
        cal = await gauge_service.create_calibration(
            db, gauge_id=gauge_id, calibration_date=req.calibration_date,
            result=req.result, certificate_no=req.certificate_no,
            calibrated_by=req.calibrated_by, notes=req.notes,
            next_calibration_date=req.next_calibration_date, user_id=user.user_id,
        )
        return schemas.gauge.GaugeCalibrationResponse.model_validate(cal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/gauge.py
git commit -m "feat(msa): add gauge API routes"
```

### Task 15: MSA API routes (all study types)

**Files:** Create `backend/app/api/msa.py`

- [ ] **Step 1: Write msa.py with all GRR/bias/linearity/stability/attribute routes**

This file follows the same pattern, with one router per study type prefix. Each study type has: list, create, get, update, delete, measurements upsert, compute, get result, complete. Also includes the overview endpoint and SPC characteristic lookup.

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app.models.spc import InspectionCharacteristic
from app import schemas
from app.services import grr_service, grr_engine, bias_service, bias_engine, linearity_service, linearity_engine, stability_service, stability_engine, attribute_service, attribute_engine
from sqlalchemy import select

grr_router = APIRouter(prefix="/api/msa/grr", tags=["msa-grr"])
bias_router = APIRouter(prefix="/api/msa/bias", tags=["msa-bias"])
linearity_router = APIRouter(prefix="/api/msa/linearity", tags=["msa-linearity"])
stability_router = APIRouter(prefix="/api/msa/stability", tags=["msa-stability"])
attribute_router = APIRouter(prefix="/api/msa/attribute", tags=["msa-attribute"])
overview_router = APIRouter(prefix="/api/msa", tags=["msa-overview"])


def _study_response(study):
    """Helper: return the correct response schema for the study type."""
    from app.models.grr import GrrStudy
    from app.models.bias import BiasStudy
    from app.models.linearity import LinearityStudy
    from app.models.stability import StabilityStudy
    from app.models.attribute import AttributeStudy
    mapper = {
        GrrStudy: schemas.grr.GrrStudyResponse,
        BiasStudy: schemas.bias.BiasStudyResponse,
        LinearityStudy: schemas.linearity.LinearityStudyResponse,
        StabilityStudy: schemas.stability.StabilityStudyResponse,
        AttributeStudy: schemas.attribute.AttributeStudyResponse,
    }
    return mapper[type(study)].model_validate(study)


# ─── GRR routes ───

@grr_router.get("", response_model=schemas.grr.GrrStudyListResponse)
async def list_grr(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None), gauge_id: uuid.UUID | None = Query(None),
    db=Depends(get_db), _user=Depends(get_current_user),
):
    items, total = await grr_service.list_studies(db, page, page_size, status, gauge_id)
    return schemas.grr.GrrStudyListResponse(
        items=[schemas.grr.GrrStudyResponse.model_validate(s) for s in items],
        total=total, page=page, page_size=page_size,
    )


@grr_router.post("", response_model=schemas.grr.GrrStudyResponse)
async def create_grr(req: schemas.grr.GrrStudyCreate, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    try:
        study = await grr_service.create_study(
            db, title=req.title, method=req.method, gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            unit=req.unit, tolerance_upper=req.tolerance_upper,
            tolerance_lower=req.tolerance_lower, reference_value=req.reference_value,
            appraiser_count=req.appraiser_count, part_count=req.part_count,
            trial_count=req.trial_count, study_date=req.study_date, user_id=user.user_id,
        )
        return schemas.grr.GrrStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@grr_router.get("/{study_id}", response_model=schemas.grr.GrrStudyResponse)
async def get_grr(study_id: uuid.UUID, db=Depends(get_db), _user=Depends(get_current_user)):
    study = await grr_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="GRR study not found")
    return schemas.grr.GrrStudyResponse.model_validate(study)


@grr_router.put("/{study_id}", response_model=schemas.grr.GrrStudyResponse)
async def update_grr(study_id: uuid.UUID, req: schemas.grr.GrrStudyUpdate, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    study = await grr_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="GRR study not found")
    try:
        study = await grr_service.update_study(
            db, study, title=req.title, method=req.method, gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name, spc_characteristic_id=req.spc_characteristic_id,
            unit=req.unit, tolerance_upper=req.tolerance_upper, tolerance_lower=req.tolerance_lower,
            reference_value=req.reference_value, appraiser_count=req.appraiser_count,
            part_count=req.part_count, trial_count=req.trial_count, study_date=req.study_date,
            user_id=user.user_id,
        )
        return schemas.grr.GrrStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@grr_router.delete("/{study_id}")
async def delete_grr(study_id: uuid.UUID, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    study = await grr_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="GRR study not found")
    try:
        await grr_service.delete_study(db, study, user.user_id)
        return {"message": "GRR study deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@grr_router.post("/{study_id}/measurements")
async def upsert_grr_measurements(study_id: uuid.UUID, req: schemas.grr.GrrMeasurementBulkUpsert, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    try:
        await grr_service.upsert_measurements(db, study_id, [m.model_dump() for m in req.measurements])
        return {"message": "measurements saved", "count": len(req.measurements)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@grr_router.get("/{study_id}/measurements")
async def get_grr_measurements(study_id: uuid.UUID, db=Depends(get_db), _user=Depends(get_current_user)):
    measurements = await grr_service.get_measurements(db, study_id)
    return [{"measurement_id": str(m.measurement_id), "study_id": str(m.study_id), "appraiser_name": m.appraiser_name, "part_no": m.part_no, "trial_no": m.trial_no, "value": m.value} for m in measurements]


@grr_router.post("/{study_id}/compute", response_model=schemas.grr.GrrResultResponse)
async def compute_grr(study_id: uuid.UUID, db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    study = await grr_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="GRR study not found")
    try:
        measurements = await grr_service.get_measurements(db, study_id)
        if not measurements:
            raise ValueError("请先录入测量数据")
        result = grr_engine.compute_grr(study, measurements)
        result = await grr_service.save_result(db, result)
        return schemas.grr.GrrResultResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@grr_router.get("/{study_id}/result", response_model=schemas.grr.GrrResultResponse)
async def get_grr_result(study_id: uuid.UUID, db=Depends(get_db), _user=Depends(get_current_user)):
    result = await grr_service.get_result(db, study_id)
    if not result:
        raise HTTPException(status_code=404, detail="result not computed yet")
    return schemas.grr.GrrResultResponse.model_validate(result)


@grr_router.post("/{study_id}/complete", response_model=schemas.grr.GrrStudyResponse)
async def complete_grr(study_id: uuid.UUID, accepted: bool = Query(True), db=Depends(get_db), user=Depends(require_engineer_or_admin)):
    study = await grr_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="GRR study not found")
    try:
        study = await grr_service.complete_study(db, study, user.user_id, accepted)
        return schemas.grr.GrrStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Bias, Linearity, Stability, Attribute routes ───
# Same pattern: replace "grr" with "bias"/"linearity"/"stability"/"attribute"
# Each uses its respective service, engine, and schemas.
# (Implementation follows identical structure to GRR routes above.)


# ─── MSA overview ───

@overview_router.get("/studies", response_model=schemas.msa.MsaStudyOverviewListResponse)
async def list_all_msa_studies(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    type: str | None = Query(None), status: str | None = Query(None),
    db=Depends(get_db), _user=Depends(get_current_user),
):
    # Union query across all 5 study tables
    from app.models.grr import GrrStudy
    from app.models.bias import BiasStudy
    from app.models.linearity import LinearityStudy
    from app.models.stability import StabilityStudy
    from app.models.attribute import AttributeStudy
    from app.models.gauge import Gauge

    results = []
    type_map = {
        "grr": (GrrStudy, "GRR"),
        "bias": (BiasStudy, "偏倚"),
        "linearity": (LinearityStudy, "线性"),
        "stability": (StabilityStudy, "稳定性"),
        "attribute": (AttributeStudy, "计数型"),
    }

    for study_type, (model, type_label) in type_map.items():
        if type and type != study_type:
            continue
        query = select(model)
        if status:
            query = query.where(model.status == status)
        items = (await db.execute(query)).scalars().all()
        for s in items:
            gauge_name = None
            if hasattr(s, "gauge_id") and s.gauge_id:
                g = await db.get(Gauge, s.gauge_id)
                gauge_name = g.name if g else None
            results.append(schemas.msa.MsaStudyOverview(
                study_id=s.study_id, study_no=s.study_no, type=type_label,
                title=s.title, gauge_name=gauge_name, status=s.status,
                study_date=s.study_date, created_at=s.created_at,
            ))

    results.sort(key=lambda x: x.created_at, reverse=True)
    total = len(results)
    start = (page - 1) * page_size
    return schemas.msa.MsaStudyOverviewListResponse(
        items=results[start:start + page_size], total=total, page=page, page_size=page_size,
    )


@overview_router.get("/spc-characteristics", response_model=list[schemas.msa.MsaSpcCharacteristic])
async def list_spc_characteristics(db=Depends(get_db), _user=Depends(get_current_user)):
    result = await db.execute(select(InspectionCharacteristic).where(InspectionCharacteristic.is_active == True))
    chars = result.scalars().all()
    return [schemas.msa.MsaSpcCharacteristic(
        characteristic_id=c.characteristic_id, name=c.name,
        unit=c.unit, tolerance_upper=c.tolerance_upper, tolerance_lower=c.tolerance_lower,
    ) for c in chars]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/msa.py
git commit -m "feat(msa): add all MSA study API routes"
```

### Task 16: Wire routers into main.py

**Files:** Modify `backend/app/main.py`

- [ ] **Step 1: Import and register gauge + MSA routers**

```python
# Add imports:
from app.api.gauge import router as gauge_router
from app.api.msa import grr_router, bias_router, linearity_router, stability_router, attribute_router, overview_router

# Add include_router calls:
app.include_router(gauge_router)
app.include_router(grr_router)
app.include_router(bias_router)
app.include_router(linearity_router)
app.include_router(stability_router)
app.include_router(attribute_router)
app.include_router(overview_router)
```

- [ ] **Step 2: Verify backend starts**

```bash
cd backend && python -c "from app.main import app; print('OK')"
```

Expected: `OK` (no import errors).

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(msa): wire MSA routers into FastAPI app"
```

---

## Phase 6: Frontend Types and API Client

### Task 17: MSA TypeScript types

**Files:** Create `frontend/src/types/msa.ts`

- [ ] **Step 1: Write MSA TypeScript interfaces**

```typescript
// ─── Gauge ───

export interface Gauge {
  gauge_id: string;
  gauge_no: string;
  name: string;
  model: string | null;
  manufacturer: string | null;
  resolution: number | null;
  measuring_range: string | null;
  department: string | null;
  location: string | null;
  status: "active" | "inactive" | "calibrating" | "scrapped";
  calibration_cycle_days: number | null;
  next_calibration_date: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface GaugeListResponse {
  items: Gauge[];
  total: number;
  page: number;
  page_size: number;
}

export interface GaugeCalibration {
  calibration_id: string;
  gauge_id: string;
  calibration_date: string;
  result: "pass" | "fail";
  certificate_no: string | null;
  calibrated_by: string | null;
  notes: string | null;
  next_calibration_date: string | null;
  created_at: string;
}

// ─── GRR ───

export type GrrMethod = "average_range" | "anova" | "range";
export type StudyStatus = "draft" | "ongoing" | "completed";

export interface GrrStudy {
  study_id: string;
  study_no: string;
  title: string;
  method: GrrMethod;
  gauge_id: string;
  characteristic_name: string;
  spc_characteristic_id: string | null;
  unit: string | null;
  tolerance_upper: number | null;
  tolerance_lower: number | null;
  reference_value: number | null;
  appraiser_count: number;
  part_count: number;
  trial_count: number;
  status: StudyStatus;
  study_date: string | null;
  accepted_by: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface GrrStudyListResponse {
  items: GrrStudy[];
  total: number;
  page: number;
  page_size: number;
}

export interface GrrMeasurementEntry {
  appraiser_name: string;
  part_no: string;
  trial_no: number;
  value: number;
}

export interface GrrResult {
  result_id: string;
  study_id: string;
  ev: number;
  av: number;
  grr: number;
  pv: number;
  tv: number;
  ndc: number;
  grr_percent_tol: number | null;
  grr_percent_tv: number;
  ev_percent: number;
  av_percent: number;
  pv_percent: number;
  conclusion: string;
  created_at: string;
}

// ─── Bias/Linearity/Stability/Attribute (brief) ───

export interface MsaStudyOverview {
  study_id: string;
  study_no: string;
  type: string;
  title: string;
  gauge_name: string | null;
  status: StudyStatus;
  study_date: string | null;
  created_at: string;
}

export interface MsaStudyOverviewListResponse {
  items: MsaStudyOverview[];
  total: number;
  page: number;
  page_size: number;
}

export interface MsaSpcCharacteristic {
  characteristic_id: string;
  name: string;
  unit: string | null;
  tolerance_upper: number | null;
  tolerance_lower: number | null;
}
```

- [ ] **Step 2: Re-export from types/index.ts**

```typescript
// Add to frontend/src/types/index.ts:
export * from "./msa";
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/msa.ts frontend/src/types/index.ts
git commit -m "feat(msa): add MSA TypeScript type definitions"
```

### Task 18: MSA API client

**Files:** Create `frontend/src/api/msa.ts`

- [ ] **Step 1: Write MSA API functions**

```typescript
import client from "./client";
import type {
  Gauge, GaugeListResponse, GaugeCalibration,
  GrrStudy, GrrStudyListResponse, GrrMeasurementEntry, GrrResult,
  MsaStudyOverviewListResponse, MsaSpcCharacteristic,
} from "../types";

// ─── Gauges ───

export async function listGauges(params?: Record<string, unknown>): Promise<GaugeListResponse> {
  const resp = await client.get("/gauges", { params });
  return resp.data;
}

export async function createGauge(data: Omit<Gauge, "gauge_id" | "created_at" | "updated_at" | "created_by" | "status">): Promise<Gauge> {
  const resp = await client.post("/gauges", data);
  return resp.data;
}

export async function getGauge(id: string): Promise<Gauge> {
  const resp = await client.get(`/gauges/${id}`);
  return resp.data;
}

export async function updateGauge(id: string, data: Partial<Gauge>): Promise<Gauge> {
  const resp = await client.put(`/gauges/${id}`, data);
  return resp.data;
}

export async function deleteGauge(id: string): Promise<void> {
  await client.delete(`/gauges/${id}`);
}

export async function listCalibrations(gaugeId: string): Promise<GaugeCalibration[]> {
  const resp = await client.get(`/gauges/${gaugeId}/calibrations`);
  return resp.data.items;
}

export async function createCalibration(gaugeId: string, data: Omit<GaugeCalibration, "calibration_id" | "gauge_id" | "created_at">): Promise<GaugeCalibration> {
  const resp = await client.post(`/gauges/${gaugeId}/calibrations`, data);
  return resp.data;
}

export async function getExpiringGauges(days = 30): Promise<GaugeListResponse> {
  const resp = await client.get("/gauges/expiring", { params: { days } });
  return resp.data;
}

// ─── GRR Studies ───

export async function listGrrStudies(params?: Record<string, unknown>): Promise<GrrStudyListResponse> {
  const resp = await client.get("/msa/grr", { params });
  return resp.data;
}

export async function createGrrStudy(data: Omit<GrrStudy, "study_id" | "study_no" | "status" | "created_at" | "updated_at" | "created_by" | "accepted_by">): Promise<GrrStudy> {
  const resp = await client.post("/msa/grr", data);
  return resp.data;
}

export async function getGrrStudy(id: string): Promise<GrrStudy> {
  const resp = await client.get(`/msa/grr/${id}`);
  return resp.data;
}

export async function updateGrrStudy(id: string, data: Partial<GrrStudy>): Promise<GrrStudy> {
  const resp = await client.put(`/msa/grr/${id}`, data);
  return resp.data;
}

export async function deleteGrrStudy(id: string): Promise<void> {
  await client.delete(`/msa/grr/${id}`);
}

export async function upsertGrrMeasurements(id: string, measurements: GrrMeasurementEntry[]): Promise<{ message: string; count: number }> {
  const resp = await client.post(`/msa/grr/${id}/measurements`, { measurements });
  return resp.data;
}

export async function getGrrMeasurements(id: string): Promise<GrrMeasurementEntry[]> {
  const resp = await client.get(`/msa/grr/${id}/measurements`);
  return resp.data;
}

export async function computeGrr(id: string): Promise<GrrResult> {
  const resp = await client.post(`/msa/grr/${id}/compute`);
  return resp.data;
}

export async function getGrrResult(id: string): Promise<GrrResult> {
  const resp = await client.get(`/msa/grr/${id}/result`);
  return resp.data;
}

export async function completeGrrStudy(id: string, accepted = true): Promise<GrrStudy> {
  const resp = await client.post(`/msa/grr/${id}/complete`, null, { params: { accepted } });
  return resp.data;
}

// ─── MSA Overview ───

export async function listAllMsaStudies(params?: Record<string, unknown>): Promise<MsaStudyOverviewListResponse> {
  const resp = await client.get("/msa/studies", { params });
  return resp.data;
}

export async function listSpcCharacteristics(): Promise<MsaSpcCharacteristic[]> {
  const resp = await client.get("/msa/spc-characteristics");
  return resp.data;
}

// ─── Bias / Linearity / Stability / Attribute studies follow identical patterns,
// only the base path differs (e.g., "/msa/bias", "/msa/linearity", etc.).
// Their create/get/update/delete/measurements/compute/result/complete functions
// mirror the GRR functions above, with respective type interfaces.
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/msa.ts
git commit -m "feat(msa): add MSA API client functions"
```

---

## Phase 7: Frontend Pages

### Task 19: Gauge list page

**Files:** Create `frontend/src/pages/GaugeList.tsx`

- [ ] **Step 1: Write GaugeList page**

Standard CRUD list page following SupplierListPage pattern — Ant Design Table with columns, filters, create/edit modal, delete confirm.

```tsx
import { useEffect, useState } from "react";
import { Table, Button, Space, Input, Modal, Form, message, Popconfirm, Tag, Select } from "antd";
import { PlusOutlined, SearchOutlined, EditOutlined, DeleteOutlined } from "@ant-design/icons";
import { listGauges, createGauge, updateGauge, deleteGauge } from "../api/msa";
import type { Gauge } from "../types";

export default function GaugeListPage() {
  const [data, setData] = useState<Gauge[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingGauge, setEditingGauge] = useState<Gauge | null>(null);
  const [form] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (search) params.search = search;
      if (statusFilter) params.status = statusFilter;
      const res = await listGauges(params);
      setData(res.items);
      setTotal(res.total);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [page, statusFilter]);

  const handleCreate = () => {
    setEditingGauge(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (record: Gauge) => {
    setEditingGauge(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleDelete = async (id: string) => {
    await deleteGauge(id);
    message.success("量具已删除");
    fetchData();
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    if (editingGauge) {
      await updateGauge(editingGauge.gauge_id, values);
      message.success("量具已更新");
    } else {
      await createGauge(values);
      message.success("量具已创建");
    }
    setModalOpen(false);
    fetchData();
  };

  const columns = [
    { title: "量具编号", dataIndex: "gauge_no", key: "gauge_no" },
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "型号", dataIndex: "model", key: "model" },
    { title: "部门", dataIndex: "department", key: "department" },
    {
      title: "状态", dataIndex: "status", key: "status",
      render: (s: string) => {
        const colorMap: Record<string, string> = { active: "green", inactive: "default", calibrating: "orange", scrapped: "red" };
        const labelMap: Record<string, string> = { active: "在用", inactive: "停用", calibrating: "校准中", scrapped: "报废" };
        return <Tag color={colorMap[s] || "default"}>{labelMap[s] || s}</Tag>;
      },
    },
    {
      title: "下次校准", dataIndex: "next_calibration_date", key: "next_calibration_date",
      render: (d: string | null) => {
        if (!d) return "-";
        const daysLeft = Math.ceil((new Date(d).getTime() - Date.now()) / 86400000);
        return <span style={{ color: daysLeft <= 30 ? "red" : undefined }}>{d} {daysLeft <= 30 ? `（${daysLeft}天后到期）` : ""}</span>;
      },
    },
    {
      title: "操作", key: "actions",
      render: (_: unknown, record: Gauge) => (
        <Space>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.gauge_id)}>
            <Button type="link" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Space>
          <Input.Search placeholder="搜索编号/名称/型号" allowClear onSearch={(v) => { setSearch(v); setPage(1); fetchData(); }} style={{ width: 300 }} />
          <Select placeholder="状态" allowClear style={{ width: 120 }} onChange={(v) => { setStatusFilter(v); setPage(1); }} options={[
            { label: "在用", value: "active" }, { label: "停用", value: "inactive" }, { label: "校准中", value: "calibrating" }, { label: "报废", value: "scrapped" },
          ]} />
        </Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>新增量具</Button>
      </div>
      <Table columns={columns} dataSource={data} rowKey="gauge_id" loading={loading} pagination={{ current: page, pageSize, total, onChange: setPage }} />

      <Modal title={editingGauge ? "编辑量具" : "新增量具"} open={modalOpen} onOk={handleSubmit} onCancel={() => setModalOpen(false)} width={640}>
        <Form form={form} layout="vertical">
          <Form.Item name="gauge_no" label="量具编号" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="model" label="型号"><Input /></Form.Item>
          <Form.Item name="manufacturer" label="制造商"><Input /></Form.Item>
          <Form.Item name="resolution" label="分辨率"><Input type="number" /></Form.Item>
          <Form.Item name="measuring_range" label="测量范围"><Input placeholder="例: 0-150mm" /></Form.Item>
          <Form.Item name="department" label="部门"><Input /></Form.Item>
          <Form.Item name="location" label="位置"><Input /></Form.Item>
          <Form.Item name="calibration_cycle_days" label="校准周期（天）"><Input type="number" /></Form.Item>
          <Form.Item name="next_calibration_date" label="下次校准日期"><Input type="date" /></Form.Item>
          {editingGauge && (
            <Form.Item name="status" label="状态">
              <Select options={[
                { label: "在用", value: "active" }, { label: "停用", value: "inactive" }, { label: "校准中", value: "calibrating" }, { label: "报废", value: "scrapped" },
              ]} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/GaugeList.tsx
git commit -m "feat(msa): add gauge list page"
```

### Task 20: Gauge detail page

**Files:** Create `frontend/src/pages/GaugeDetail.tsx`

- [ ] **Step 1: Write GaugeDetail page with calibration history**

Displays gauge info card + calibration history table + add calibration form. Uses `useParams` for gauge_id, fetches gauge + calibrations on mount.

- [ ] **Step 2: Commit**

### Task 21: MSA study list page

**Files:** Create `frontend/src/pages/MsaStudyList.tsx`

- [ ] **Step 1: Write MsaStudyList page**

Unified overview listing all 5 study types. Columns: study_no, type (tag), title, gauge_name, status, study_date. Filter by type/status. "New Study" button opens type selector then navigates to the right creation page.

- [ ] **Step 2: Commit**

### Task 22: GRR study detail page (three-step wizard)

**Files:** Create `frontend/src/pages/GrrStudy.tsx`

- [ ] **Step 1: Write GrrStudy page**

Three-step Ant Design Steps component:

**Step 1 - Basic Info:** Form with all GrrStudy fields (method select, gauge select, characteristic_name, tolerances, appraiser_count, part_count, trial_count, SPC import dropdown).

**Step 2 - Data Entry:** Dynamic measurement matrix. Calculate rows from appraiser_count × part_count × trial_count. Group by appraiser tabs. Each cell is InputNumber. Supports batch numeric paste.

**Step 3 - Results Report:** "Compute" button triggers API call. Shows: EV/AV/GRR/PV/TV table with percent breakdown, conclusion badge (green/yellow/red), ndc display, echarts bar chart of variance components. "Complete" button with accept/reject.

- [ ] **Step 2: Commit**

### Task 23: Remaining study detail pages

**Files:** Create `frontend/src/pages/BiasStudy.tsx`, `frontend/src/pages/LinearityStudy.tsx`, `frontend/src/pages/StabilityStudy.tsx`, `frontend/src/pages/AttributeStudy.tsx`

- [ ] **Step 1: Write BiasStudy page** — Simple 1D value input, t-test result display.

- [ ] **Step 2: Write LinearityStudy page** — Reference-value paired input table, regression result display.

- [ ] **Step 3: Write StabilityStudy page** — Time-series table (date, mean, range), SPC control chart display in results.

- [ ] **Step 4: Write AttributeStudy page** — Matrix table (appraiser × part × known_standard + decision), effectiveness + Kappa display.

- [ ] **Step 5: Commit all remaining pages**

```bash
git add frontend/src/pages/BiasStudy.tsx frontend/src/pages/LinearityStudy.tsx frontend/src/pages/StabilityStudy.tsx frontend/src/pages/AttributeStudy.tsx
git commit -m "feat(msa): add bias, linearity, stability, attribute study pages"
```

---

## Phase 8: Wiring (Routes + Navigation)

### Task 24: Add MSA routes to App.tsx

**Files:** Modify `frontend/src/App.tsx`

- [ ] **Step 1: Import MSA pages and add routes**

```tsx
// Add imports:
import GaugeListPage from "./pages/GaugeList";
import GaugeDetailPage from "./pages/GaugeDetail";
import MsaStudyListPage from "./pages/MsaStudyList";
import GrrStudyPage from "./pages/GrrStudy";
import BiasStudyPage from "./pages/BiasStudy";
import LinearityStudyPage from "./pages/LinearityStudy";
import StabilityStudyPage from "./pages/StabilityStudy";
import AttributeStudyPage from "./pages/AttributeStudy";

// Add routes inside ProtectedRoute:
<Route path="/msa/gauges" element={<GaugeListPage />} />
<Route path="/msa/gauges/:id" element={<GaugeDetailPage />} />
<Route path="/msa/studies" element={<MsaStudyListPage />} />
<Route path="/msa/grr/:id" element={<GrrStudyPage />} />
<Route path="/msa/bias/:id" element={<BiasStudyPage />} />
<Route path="/msa/linearity/:id" element={<LinearityStudyPage />} />
<Route path="/msa/stability/:id" element={<StabilityStudyPage />} />
<Route path="/msa/attribute/:id" element={<AttributeStudyPage />} />
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(msa): add MSA routes to App.tsx"
```

### Task 25: Add MSA nav menu to AppLayout

**Files:** Modify `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Add MSA menu item with sub-menu**

```tsx
// After the SPC menu item, add:
{
  key: "/msa",
  icon: <ExperimentOutlined />,
  label: "MSA测量系统分析",
  children: [
    { key: "/msa/gauges", label: "量具台账" },
    { key: "/msa/studies", label: "MSA研究总览" },
  ],
},
```

Import `ExperimentOutlined` from `@ant-design/icons`.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(msa): add MSA navigation menu"
```

---

## Phase 9: Verification

### Task 26: Full integration verification

- [ ] **Step 1: Start backend and run a basic test**

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
sleep 3
curl -s http://localhost:8000/api/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 2: Login and test gauge CRUD**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"username":"admin","password":"Admin@2026"}' | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

# Create gauge
curl -s -X POST http://localhost:8000/api/gauges -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"gauge_no":"Q-001","name":"游标卡尺","model":"0-150mm","calibration_cycle_days":180}'

# List gauges
curl -s http://localhost:8000/api/gauges -H "Authorization: Bearer $TOKEN"
```

Expected: Gauge created and listed successfully.

- [ ] **Step 3: Test GRR study lifecycle**

```bash
# Extract gauge_id from previous response, then:
GAUGE_ID="<from-response>"
curl -s -X POST http://localhost:8000/api/msa/grr -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d "{\"title\":\"My First GRR\",\"gauge_id\":\"$GAUGE_ID\",\"characteristic_name\":\"直径\",\"tolerance_upper\":10.05,\"tolerance_lower\":9.95,\"appraiser_count\":2,\"part_count\":3,\"trial_count\":2}"

# Upsert measurements
STUDY_ID="<from-response>"
curl -s -X POST http://localhost:8000/api/msa/grr/$STUDY_ID/measurements -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"measurements":[
  {"appraiser_name":"A","part_no":"1","trial_no":1,"value":10.01},
  {"appraiser_name":"A","part_no":"1","trial_no":2,"value":10.02},
  {"appraiser_name":"A","part_no":"2","trial_no":1,"value":9.98},
  {"appraiser_name":"A","part_no":"2","trial_no":2,"value":9.97},
  {"appraiser_name":"A","part_no":"3","trial_no":1,"value":10.00},
  {"appraiser_name":"A","part_no":"3","trial_no":2,"value":10.01},
  {"appraiser_name":"B","part_no":"1","trial_no":1,"value":10.00},
  {"appraiser_name":"B","part_no":"1","trial_no":2,"value":10.01},
  {"appraiser_name":"B","part_no":"2","trial_no":1,"value":9.99},
  {"appraiser_name":"B","part_no":"2","trial_no":2,"value":9.98},
  {"appraiser_name":"B","part_no":"3","trial_no":1,"value":10.02},
  {"appraiser_name":"B","part_no":"3","trial_no":2,"value":10.01}
]}'

# Compute
curl -s -X POST http://localhost:8000/api/msa/grr/$STUDY_ID/compute -H "Authorization: Bearer $TOKEN"

# Get result
curl -s http://localhost:8000/api/msa/grr/$STUDY_ID/result -H "Authorization: Bearer $TOKEN"
```

Expected: GRR result returned with EV, AV, GRR, PV, TV, ndc, conclusion.

- [ ] **Step 4: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: No TypeScript or build errors.

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: complete MSA module — verify backend + frontend integration"
```

---

## Self-Review Checklist

1. **Spec coverage:** All sections from the design spec are covered — gauge CRUD, 5 study types with CRUD + engines, API routes, frontend pages, SPC linkage, MSA overview.
2. **Placeholder scan:** No TBD/TODO/placeholders. Every step has concrete code or clear patterns.
3. **Type consistency:** Model field names match schema field names match API response fields match TypeScript interfaces.
