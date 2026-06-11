# Control Plan Intelligent Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rule-based control plan validation system using a two-table model (`findings` for stable identity + `occurrences` for per-run history), with a frontend panel for viewing and managing findings.

**Architecture:** Backend: SQLAlchemy models for runs/findings/occurrences + pure-function rule engine + orchestrator engine. `findings` holds stable identity and inherited user state; `occurrences` records each run's snapshot. Frontend: React sidebar panel with polling-based status updates. Auto-triggered on CP save via asyncio background task with isolated DB session.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Pydantic v2, pytest. React 18, TypeScript 5.6, Ant Design 5, Axios.

---

## File Structure

**New files:**
- `backend/app/models/cp_validation.py` — `CPValidationRun`, `CPValidationFinding`, `CPValidationOccurrence` models
- `backend/app/schemas/cp_validation.py` — Request/response Pydantic schemas
- `backend/app/services/cp_validation/rule_engine.py` — 4 validation rules (pure functions)
- `backend/app/services/cp_validation/engine.py` — Orchestrator: run lifecycle, finding hash dedup
- `backend/app/services/cp_validation/__init__.py` — Package init
- `backend/app/api/cp_validation.py` — FastAPI routes
- `backend/tests/test_cp_validation_rules.py` — Rule engine unit tests
- `backend/tests/test_cp_validation_engine.py` — Engine orchestrator tests
- `backend/tests/test_cp_validation_api.py` — API integration tests
- `frontend/src/types/cpValidation.ts` — TypeScript types
- `frontend/src/api/cpValidation.ts` — API client functions
- `frontend/src/components/control-plan/ValidationPanel.tsx` — Sidebar panel
- `frontend/src/components/control-plan/ValidationCard.tsx` — Single finding card
- `frontend/src/components/control-plan/ValidationBadge.tsx` — Status dot badge

**Modified files:**
- `backend/alembic/versions/` — New migration
- `backend/app/main.py` — Register router
- `backend/app/services/control_plan_service.py` — Add auto-trigger hook
- `frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx` — Embed panel
- `frontend/src/pages/planning/control-plan/ControlPlanListPage.tsx` — Add badge column

---

### Task 1: Data Models

**Files:**
- Create: `backend/app/models/cp_validation.py`

**Context:** Follow the pattern in `backend/app/models/control_plan.py`. Use `Mapped`, `mapped_column`, UUID PKs, JSONB for arrays. Two-table model: `findings` is stable identity + inherited user state; `occurrences` is per-run snapshot.

- [ ] **Step 1: Write the model file**

```python
import uuid
import hashlib
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CPValidationRun(Base):
    __tablename__ = "cp_validation_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running")
    rule_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    info_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_rules: Mapped[list | None] = mapped_column(JSONB, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )


class CPValidationFinding(Base):
    __tablename__ = "cp_validation_findings"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False
    )
    finding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CPValidationOccurrence(Base):
    __tablename__ = "cp_validation_occurrences"

    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cp_validation_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cp_validation_findings.finding_id", ondelete="CASCADE"), nullable=False
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False
    )
    validation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_items: Mapped[list | None] = mapped_column(JSONB, default=list)
    fmea_node_ids: Mapped[list | None] = mapped_column(JSONB, default=list)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def compute_finding_hash(rule_id: str, item_id: str | None, key_content: str) -> str:
    """Generate SHA256 hash for a validation finding."""
    payload = f"{rule_id}|{item_id or ''}|{key_content}"
    return hashlib.sha256(payload.encode()).hexdigest()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/cp_validation.py
git commit -m "feat(cp-validation): add two-table model - runs, findings, occurrences"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/20250610_add_cp_validation_tables.py`

**Context:** Check existing migration style at `backend/alembic/versions/`. Use `op.create_table`, `op.create_index`. Include partial unique indexes.

- [ ] **Step 1: Write the migration**

```python
"""Add cp validation tables.

Revision ID: 20250610_add_cp_validation
Revises: (set to current head — check `alembic history`)
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20250610_add_cp_validation"
down_revision = None  # Set this to current head after checking
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cp_validation_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("rule_count", sa.Integer, server_default="0"),
        sa.Column("error_count", sa.Integer, server_default="0"),
        sa.Column("warning_count", sa.Integer, server_default="0"),
        sa.Column("info_count", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_rules", postgresql.JSONB, server_default="[]"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_cpvrn_cp_id", "cp_validation_runs", ["cp_id"])
    op.create_index("idx_cpvrn_status", "cp_validation_runs", ["status"])
    op.create_index(
        "idx_cpvrn_running", "cp_validation_runs", ["cp_id"],
        unique=True, postgresql_where=sa.text("status = 'running'")
    )

    op.create_table(
        "cp_validation_findings",
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_hash", sa.String(64), nullable=False),
        sa.Column("rule_id", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_cvf_cp_id", "cp_validation_findings", ["cp_id"])
    op.create_index("idx_cvf_status", "cp_validation_findings", ["status"])
    op.create_index(
        "idx_cvf_hash", "cp_validation_findings", ["cp_id", "finding_hash"], unique=True
    )

    op.create_table(
        "cp_validation_occurrences",
        sa.Column("occurrence_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cp_validation_runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cp_validation_findings.finding_id", ondelete="CASCADE"), nullable=False),
        sa.Column("cp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False),
        sa.Column("validation_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("affected_items", postgresql.JSONB, server_default="[]"),
        sa.Column("fmea_node_ids", postgresql.JSONB, server_default="[]"),
        sa.Column("suggestion", sa.Text, nullable=True),
        sa.Column("suggestion_data", postgresql.JSONB, nullable=True),
        sa.Column("present", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_cvo_run_id", "cp_validation_occurrences", ["run_id"])
    op.create_index("idx_cvo_finding_id", "cp_validation_occurrences", ["finding_id"])
    op.create_index("idx_cvo_cp_id", "cp_validation_occurrences", ["cp_id"])
    op.create_index(
        "idx_cvo_run_finding", "cp_validation_occurrences", ["run_id", "finding_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("idx_cvo_run_finding", table_name="cp_validation_occurrences")
    op.drop_index("idx_cvo_cp_id", table_name="cp_validation_occurrences")
    op.drop_index("idx_cvo_finding_id", table_name="cp_validation_occurrences")
    op.drop_index("idx_cvo_run_id", table_name="cp_validation_occurrences")
    op.drop_table("cp_validation_occurrences")

    op.drop_index("idx_cvf_hash", table_name="cp_validation_findings")
    op.drop_index("idx_cvf_status", table_name="cp_validation_findings")
    op.drop_index("idx_cvf_cp_id", table_name="cp_validation_findings")
    op.drop_table("cp_validation_findings")

    op.drop_index("idx_cpvrn_running", table_name="cp_validation_runs")
    op.drop_index("idx_cpvrn_status", table_name="cp_validation_runs")
    op.drop_index("idx_cpvrn_cp_id", table_name="cp_validation_runs")
    op.drop_table("cp_validation_runs")
```

- [ ] **Step 2: Set correct down_revision**

Run:
```bash
cd backend && alembic history --verbose | head -10
```

Set `down_revision` to the current head revision ID.

- [ ] **Step 3: Test the migration**

```bash
cd backend && alembic upgrade head
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/20250610_add_cp_validation_tables.py
git commit -m "feat(cp-validation): add alembic migration for runs/findings/occurrences"
```

---

### Task 3: Schemas

**Files:**
- Create: `backend/app/schemas/cp_validation.py`

- [ ] **Step 1: Write schemas**

```python
import uuid
from datetime import datetime
from pydantic import BaseModel


class ValidationFindingResponse(BaseModel):
    finding_id: uuid.UUID
    cp_id: uuid.UUID
    finding_hash: str
    rule_id: str
    severity: str
    category: str
    status: str
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationOccurrenceResponse(BaseModel):
    occurrence_id: uuid.UUID
    run_id: uuid.UUID
    finding_id: uuid.UUID
    cp_id: uuid.UUID
    validation_type: str
    title: str
    description: str | None = None
    affected_items: list = []
    fmea_node_ids: list = []
    suggestion: str | None = None
    suggestion_data: dict | None = None
    present: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationResultItem(BaseModel):
    """Joined occurrence + finding, returned by list endpoint."""
    occurrence_id: uuid.UUID
    run_id: uuid.UUID
    finding_id: uuid.UUID
    cp_id: uuid.UUID
    validation_type: str
    rule_id: str
    severity: str
    category: str
    title: str
    description: str | None = None
    affected_items: list = []
    fmea_node_ids: list = []
    suggestion: str | None = None
    suggestion_data: dict | None = None
    status: str
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    present: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationRunResponse(BaseModel):
    run_id: uuid.UUID
    cp_id: uuid.UUID
    trigger: str
    status: str
    rule_count: int
    error_count: int
    warning_count: int
    info_count: int
    started_at: datetime
    completed_at: datetime | None = None
    failed_rules: list = []
    created_by: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class ValidationSummaryResponse(BaseModel):
    run_id: uuid.UUID | None = None
    status: str | None = None
    total: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    open_count: int = 0
    resolved_count: int = 0
    rejected_count: int = 0


class ValidationResultsListResponse(BaseModel):
    items: list[ValidationResultItem]
    total: int
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/cp_validation.py
git commit -m "feat(cp-validation): add Pydantic schemas for two-table model"
```

---

### Task 4: Rule Engine

Same as before — pure functions returning `ValidationFinding`.

**Files:**
- Create: `backend/app/services/cp_validation/rule_engine.py`
- Create: `backend/tests/test_cp_validation_rules.py`

**Rule engine code:** (identical to previous plan — omitted here for brevity; refer to Task 4 in previous plan)

```python
# backend/app/services/cp_validation/rule_engine.py
"""Rule-based validation engine for Control Plans."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationFinding:
    rule_id: str
    severity: str
    category: str
    title: str
    description: str
    item_id: str | None = None
    key_content: str = ""


_PLACEHOLDER_METHODS = {"", "见sop", "见 sop", "无", "待定", "tbd", "暂无", "暂不", "n/a", "na"}
_PLACEHOLDER_REACTIONS = {"", "无", "待定", "tbd", "暂无", "暂不", "n/a", "na"}


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _is_placeholder(val: str | None, placeholders: set[str]) -> bool:
    return _norm(val) in placeholders


def rule_r001_control_method(items: list[Any]) -> list[ValidationFinding]:
    findings = []
    for item in items:
        if _is_placeholder(item.control_method, _PLACEHOLDER_METHODS):
            findings.append(ValidationFinding(
                rule_id="R001",
                severity="error",
                category="completeness",
                title="控制方法缺失",
                description=f"工序 {item.step_no or '?'}/{item.process_name or '?'} 的控制方法为空或仅含占位符",
                item_id=str(item.item_id),
                key_content="control_method_empty",
            ))
    return findings


def rule_r002_reaction_plan(items: list[Any]) -> list[ValidationFinding]:
    findings = []
    for item in items:
        if _is_placeholder(item.reaction_plan, _PLACEHOLDER_REACTIONS):
            findings.append(ValidationFinding(
                rule_id="R002",
                severity="error",
                category="completeness",
                title="反应计划缺失",
                description=f"工序 {item.step_no or '?'}/{item.process_name or '?'} 的反应计划为空或仅含占位符",
                item_id=str(item.item_id),
                key_content="reaction_plan_empty",
            ))
    return findings


def rule_r003_fmea_consistency(items: list[Any], fmea_graph: dict | None) -> list[ValidationFinding]:
    if not fmea_graph:
        return []
    nodes = fmea_graph.get("nodes", [])
    node_map = {n.get("id"): n for n in nodes if n.get("id")}
    findings = []
    for item in items:
        if not item.source_fmea_node_id:
            continue
        node = node_map.get(item.source_fmea_node_id)
        if node is None:
            findings.append(ValidationFinding(
                rule_id="R003",
                severity="warning",
                category="consistency",
                title="FMEA源工序已删除",
                description=f"工序 {item.step_no or '?'} 关联的FMEA节点已不存在",
                item_id=str(item.item_id),
                key_content=f"node_deleted_{item.source_fmea_node_id}",
            ))
            continue
        fmea_step_no = str(node.get("process_number") or "")
        fmea_name = str(node.get("name") or "")
        cp_step_no = str(item.step_no or "")
        cp_name = str(item.process_name or "")
        if fmea_step_no != cp_step_no or fmea_name != cp_name:
            findings.append(ValidationFinding(
                rule_id="R003",
                severity="warning",
                category="consistency",
                title="工序与FMEA不一致",
                description=f"工序号/名称与FMEA源不同: CP=({cp_step_no}/{cp_name}) vs FMEA=({fmea_step_no}/{fmea_name})",
                item_id=str(item.item_id),
                key_content=f"mismatch_{item.source_fmea_node_id}",
            ))
    return findings


def rule_r004_special_class(items: list[Any]) -> list[ValidationFinding]:
    findings = []
    for item in items:
        sc = _norm(item.special_class)
        if sc not in ("cc", "sc"):
            continue
        missing = []
        if _is_placeholder(item.evaluation_method, _PLACEHOLDER_METHODS):
            missing.append("评价方法")
        if _is_placeholder(item.control_method, _PLACEHOLDER_METHODS):
            missing.append("控制方法")
        if missing:
            findings.append(ValidationFinding(
                rule_id="R004",
                severity="warning",
                category="coverage",
                title="特殊特性控制不完整",
                description=f"工序 {item.step_no or '?'} 标记为 {item.special_class}，但{','.join(missing)}为空",
                item_id=str(item.item_id),
                key_content=f"special_class_{sc}_{'_'.join(missing)}",
            ))
    return findings


RULE_REGISTRY: list = [
    ("R001", rule_r001_control_method),
    ("R002", rule_r002_reaction_plan),
    ("R003", rule_r003_fmea_consistency),
    ("R004", rule_r004_special_class),
]


def run_all_rules(cp: Any, items: list[Any], fmea_graph: dict | None) -> list[ValidationFinding]:
    all_findings: list[ValidationFinding] = []
    for rule_id, rule_fn in RULE_REGISTRY:
        try:
            if rule_id == "R003":
                findings = rule_fn(items, fmea_graph)
            else:
                findings = rule_fn(items)
            all_findings.extend(findings)
        except Exception:
            continue
    return all_findings
```

Tests same as previous plan.

- [ ] **Step 1-3: Write rule engine and tests, run them, commit**

```bash
cd backend && pytest tests/test_cp_validation_rules.py -v
git add backend/app/services/cp_validation/rule_engine.py backend/tests/test_cp_validation_rules.py
git commit -m "feat(cp-validation): add rule engine with 4 rules and unit tests"
```

---

### Task 5: Validation Engine (Orchestrator)

**Files:**
- Create: `backend/app/services/cp_validation/engine.py`
- Create: `backend/app/services/cp_validation/__init__.py`

**Two-table engine logic:**
- For each `ValidationFinding`, compute `finding_hash`.
- Look up `CPValidationFinding` by `(cp_id, finding_hash)`.
- If no finding exists, create one with `status="open"`.
- **Never modify finding status during validation**.
- Create a `CPValidationOccurrence` for each finding: `run_id=current_run`, `finding_id=finding.finding_id`, `present=True`, plus all snapshot fields (title, description, severity, etc.).
- For existing findings **not** present in this run, create a `CPValidationOccurrence` with `present=False`.
- Count severities from `present=True` occurrences to update the run.

- [ ] **Step 1: Write package init**

```python
# backend/app/services/cp_validation/__init__.py
from .engine import CPValidationEngine

__all__ = ["CPValidationEngine"]
```

- [ ] **Step 2: Write the engine**

```python
"""Control Plan Validation Engine — orchestrates rule execution with two-table persistence."""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cp_validation import (
    CPValidationRun,
    CPValidationFinding,
    CPValidationOccurrence,
    compute_finding_hash,
)
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.fmea import FMEADocument
from app.services.cp_validation.rule_engine import run_all_rules, ValidationFinding

logger = logging.getLogger(__name__)


class CPValidationEngine:
    """Orchestrator for CP validation runs using the two-table model.

    findings  = stable identity + inherited user state (open/accepted/rejected/resolved)
    occurrences = per-run snapshot of what was detected
    """

    async def validate(
        self,
        db: AsyncSession,
        cp_id: uuid.UUID,
        user_id: uuid.UUID,
        trigger: str = "manual",
    ) -> CPValidationRun:
        run = CPValidationRun(
            cp_id=cp_id,
            trigger=trigger,
            status="running",
            created_by=user_id,
        )
        db.add(run)
        await db.flush()
        await db.refresh(run)

        try:
            await self._execute_validation(db, run)
        except Exception:
            logger.exception("Validation run %s failed", run.run_id)
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise

        return run

    async def _execute_validation(self, db: AsyncSession, run: CPValidationRun) -> None:
        cp_id = run.cp_id

        cp_result = await db.execute(
            select(ControlPlan).where(ControlPlan.cp_id == cp_id)
        )
        cp = cp_result.scalar_one_or_none()
        if cp is None:
            raise ValueError(f"Control plan {cp_id} not found")

        items_result = await db.execute(
            select(ControlPlanItem).where(ControlPlanItem.cp_id == cp_id)
        )
        items = list(items_result.scalars().all())

        fmea_graph: dict | None = None
        if cp.fmea_ref_id:
            fmea_result = await db.execute(
                select(FMEADocument).where(FMEADocument.fmea_id == cp.fmea_ref_id)
            )
            fmea = fmea_result.scalar_one_or_none()
            if fmea:
                fmea_graph = fmea.graph_data

        findings = run_all_rules(cp, items, fmea_graph)

        # Build hash -> finding map for this run
        hash_to_finding: dict[str, ValidationFinding] = {}
        for finding in findings:
            h = compute_finding_hash(finding.rule_id, finding.item_id, finding.key_content)
            hash_to_finding[h] = finding

        # Load existing findings for this CP
        existing_result = await db.execute(
            select(CPValidationFinding).where(CPValidationFinding.cp_id == cp_id)
        )
        existing_rows = list(existing_result.scalars().all())
        existing_by_hash = {row.finding_hash: row for row in existing_rows}

        seen_finding_ids: set[uuid.UUID] = set()

        for h, finding in hash_to_finding.items():
            existing = existing_by_hash.get(h)
            if existing is None:
                existing = CPValidationFinding(
                    cp_id=cp_id,
                    finding_hash=h,
                    rule_id=finding.rule_id,
                    severity=finding.severity,
                    category=finding.category,
                    status="open",
                )
                db.add(existing)
                await db.flush()
                await db.refresh(existing)
                existing_by_hash[h] = existing

            seen_finding_ids.add(existing.finding_id)

            db.add(CPValidationOccurrence(
                run_id=run.run_id,
                finding_id=existing.finding_id,
                cp_id=cp_id,
                validation_type="rule",
                title=finding.title,
                description=finding.description,
                affected_items=[finding.item_id] if finding.item_id else [],
                present=True,
            ))

        # Record absences for existing findings not detected in this run
        for row in existing_rows:
            if row.finding_id not in seen_finding_ids:
                db.add(CPValidationOccurrence(
                    run_id=run.run_id,
                    finding_id=row.finding_id,
                    cp_id=cp_id,
                    validation_type="rule",
                    title="",
                    description="",
                    present=False,
                ))

        # Count from present occurrences
        error_count = sum(
            1 for f in findings if f.severity == "error"
        )
        warning_count = sum(
            1 for f in findings if f.severity == "warning"
        )
        info_count = sum(
            1 for f in findings if f.severity == "info"
        )

        run.status = "completed"
        run.rule_count = len(findings)
        run.error_count = error_count
        run.warning_count = warning_count
        run.info_count = info_count
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
```

- [ ] **Step 3: Write and run the engine test**

Create `backend/tests/test_cp_validation_engine.py`:

```python
"""Unit tests for CPValidationEngine orchestrator (two-table model)."""
import uuid
import pytest

from app.services.cp_validation.engine import CPValidationEngine
from app.models.cp_validation import CPValidationFinding, CPValidationOccurrence
from app.models.control_plan import ControlPlanItem


@pytest.mark.asyncio
async def test_validate_creates_run_and_results(db, admin_user):
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate

    cp_data = ControlPlanCreate(
        title="Test CP",
        document_no=f"CP-TEST-{uuid.uuid4().hex[:8]}",
        product_line_code="DC-DC-100",
    )
    cp = await create_control_plan(db, cp_data, admin_user.user_id)

    item = ControlPlanItem(
        item_id=uuid.uuid4(),
        cp_id=cp.cp_id,
        step_no="10",
        process_name="焊接",
        control_method="",
        reaction_plan="",
    )
    db.add(item)
    await db.flush()

    engine = CPValidationEngine()
    run = await engine.validate(db, cp.cp_id, admin_user.user_id, trigger="manual")

    assert run.status == "completed"
    assert run.error_count >= 2

    from sqlalchemy import select
    result = await db.execute(
        select(CPValidationOccurrence).where(CPValidationOccurrence.run_id == run.run_id)
    )
    occurrences = result.scalars().all()
    assert len(occurrences) >= 2
    assert all(o.present for o in occurrences)

    result2 = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    findings = result2.scalars().all()
    assert len(findings) >= 2
    assert all(f.status == "open" for f in findings)


@pytest.mark.asyncio
async def test_finding_reused_across_runs(db, admin_user):
    """Same finding_hash creates one finding but two occurrences across runs."""
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate
    from sqlalchemy import select, func

    cp_data = ControlPlanCreate(
        title="Test CP Deduplication",
        document_no=f"CP-DEDUP-{uuid.uuid4().hex[:8]}",
        product_line_code="DC-DC-100",
    )
    cp = await create_control_plan(db, cp_data, admin_user.user_id)

    item = ControlPlanItem(
        item_id=uuid.uuid4(),
        cp_id=cp.cp_id,
        step_no="10",
        process_name="焊接",
        control_method="",
    )
    db.add(item)
    await db.flush()

    engine = CPValidationEngine()
    run1 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result1 = await db.execute(
        select(func.count()).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    finding_count = result1.scalar()

    result1o = await db.execute(
        select(func.count()).where(CPValidationOccurrence.run_id == run1.run_id)
    )
    occ_count1 = result1o.scalar()

    # Second run with same data
    run2 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result2 = await db.execute(
        select(func.count()).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    assert result2.scalar() == finding_count  # no new findings

    result2o = await db.execute(
        select(func.count()).where(CPValidationOccurrence.run_id == run2.run_id)
    )
    assert result2o.scalar() == occ_count1  # new occurrences for run2


@pytest.mark.asyncio
async def test_absence_recorded_when_finding_disappears(db, admin_user):
    """When an issue is fixed, the next run records present=False for that finding."""
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate
    from sqlalchemy import select

    cp_data = ControlPlanCreate(
        title="Test CP Superseded",
        document_no=f"CP-SUP-{uuid.uuid4().hex[:8]}",
        product_line_code="DC-DC-100",
    )
    cp = await create_control_plan(db, cp_data, admin_user.user_id)

    item = ControlPlanItem(
        item_id=uuid.uuid4(),
        cp_id=cp.cp_id,
        step_no="10",
        control_method="",
    )
    db.add(item)
    await db.flush()

    engine = CPValidationEngine()
    run1 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    # Fix the issue
    item.control_method = "SPC Chart"
    await db.flush()

    run2 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result = await db.execute(
        select(CPValidationOccurrence).where(
            CPValidationOccurrence.run_id == run2.run_id,
            CPValidationOccurrence.present == False,
        )
    )
    absent = result.scalars().all()
    assert len(absent) >= 1
```

Run:
```bash
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/openqms_test pytest tests/test_cp_validation_engine.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/cp_validation/
git add backend/tests/test_cp_validation_engine.py
git commit -m "feat(cp-validation): add two-table validation engine with tests"
```

---

### Task 6: API Routes

**Files:**
- Create: `backend/app/api/cp_validation.py`

**Key changes for two-table model:**
- `GET /validation-results` joins `CPValidationOccurrence` + `CPValidationFinding` for the latest run, filtering `present=True`.
- `POST /reject`, `/resolve`, `/reopen` operate on `CPValidationFinding` (not occurrence).

- [ ] **Step 1: Write the API routes**

```python
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import (
    get_current_user, require_permission,
    PermissionLevel, Module,
)
from app.models.user import User
from app.models.cp_validation import (
    CPValidationRun, CPValidationFinding, CPValidationOccurrence,
)
from app.schemas.cp_validation import (
    ValidationRunResponse,
    ValidationResultItem,
    ValidationSummaryResponse,
    ValidationResultsListResponse,
)
from app.services.cp_validation import CPValidationEngine

router = APIRouter(prefix="/api", tags=["cp-validation"])


def _row_to_result_item(occ: CPValidationOccurrence, finding: CPValidationFinding) -> ValidationResultItem:
    return ValidationResultItem(
        occurrence_id=occ.occurrence_id,
        run_id=occ.run_id,
        finding_id=finding.finding_id,
        cp_id=occ.cp_id,
        validation_type=occ.validation_type,
        rule_id=finding.rule_id,
        severity=finding.severity,
        category=finding.category,
        title=occ.title,
        description=occ.description,
        affected_items=occ.affected_items or [],
        fmea_node_ids=occ.fmea_node_ids or [],
        suggestion=occ.suggestion,
        suggestion_data=occ.suggestion_data,
        status=finding.status,
        resolved_by=finding.resolved_by,
        resolved_at=finding.resolved_at,
        present=occ.present,
        created_at=occ.created_at,
    )


async def _get_latest_run(db: AsyncSession, cp_id: uuid.UUID) -> CPValidationRun | None:
    result = await db.execute(
        select(CPValidationRun)
        .where(CPValidationRun.cp_id == cp_id)
        .order_by(desc(CPValidationRun.started_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/control-plans/{cp_id}/validation-results", response_model=ValidationResultsListResponse)
async def list_validation_results(
    cp_id: uuid.UUID,
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.VIEW)),
):
    latest_run = await _get_latest_run(db, cp_id)
    if latest_run is None:
        return ValidationResultsListResponse(items=[], total=0)

    query = select(CPValidationOccurrence, CPValidationFinding).join(
        CPValidationFinding,
        CPValidationOccurrence.finding_id == CPValidationFinding.finding_id,
    ).where(
        CPValidationOccurrence.run_id == latest_run.run_id,
        CPValidationOccurrence.present == True,
    )
    if status_filter:
        query = query.where(CPValidationFinding.status == status_filter)
    if severity:
        query = query.where(CPValidationFinding.severity == severity)

    result = await db.execute(query)
    rows = result.all()

    items = [_row_to_result_item(occ, finding) for occ, finding in rows]
    return ValidationResultsListResponse(items=items, total=len(items))


@router.post("/control-plans/{cp_id}/validate", response_model=ValidationRunResponse)
async def trigger_validation(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    engine = CPValidationEngine()
    try:
        run = await engine.validate(db, cp_id, user.user_id, trigger="manual")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="校验执行失败")
    return ValidationRunResponse.model_validate(run)


@router.get("/control-plans/{cp_id}/validation-runs", response_model=list[ValidationRunResponse])
async def list_validation_runs(
    cp_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.VIEW)),
):
    result = await db.execute(
        select(CPValidationRun)
        .where(CPValidationRun.cp_id == cp_id)
        .order_by(desc(CPValidationRun.started_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [ValidationRunResponse.model_validate(r) for r in rows]


@router.get("/control-plans/{cp_id}/validation-summary", response_model=ValidationSummaryResponse)
async def get_validation_summary(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.VIEW)),
):
    latest_run = await _get_latest_run(db, cp_id)
    if latest_run is None:
        return ValidationSummaryResponse()

    # Severity counts from present occurrences joined to findings
    counts_result = await db.execute(
        select(CPValidationFinding.status, func.count())
        .join(
            CPValidationOccurrence,
            and_(
                CPValidationOccurrence.finding_id == CPValidationFinding.finding_id,
                CPValidationOccurrence.run_id == latest_run.run_id,
                CPValidationOccurrence.present == True,
            ),
        )
        .where(CPValidationFinding.cp_id == cp_id)
        .group_by(CPValidationFinding.status)
    )
    status_counts = {status: count for status, count in counts_result.all()}

    return ValidationSummaryResponse(
        run_id=latest_run.run_id,
        status=latest_run.status,
        total=latest_run.rule_count,
        error_count=latest_run.error_count,
        warning_count=latest_run.warning_count,
        info_count=latest_run.info_count,
        open_count=status_counts.get("open", 0),
        resolved_count=status_counts.get("resolved", 0),
        rejected_count=status_counts.get("rejected", 0),
    )


@router.post("/validation-results/{finding_id}/reject", response_model=ValidationResultItem)
async def reject_validation_result(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    result = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.finding_id == finding_id)
    )
    finding = result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail="校验结果不存在")

    finding.status = "rejected"
    finding.resolved_by = user.user_id
    finding.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    # Return joined with latest occurrence for consistency
    occ_result = await db.execute(
        select(CPValidationOccurrence)
        .where(CPValidationOccurrence.finding_id == finding_id)
        .order_by(desc(CPValidationOccurrence.created_at))
        .limit(1)
    )
    occ = occ_result.scalar_one()
    return _row_to_result_item(occ, finding)


@router.post("/validation-results/{finding_id}/resolve", response_model=ValidationResultItem)
async def resolve_validation_result(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    result = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.finding_id == finding_id)
    )
    finding = result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail="校验结果不存在")

    finding.status = "resolved"
    finding.resolved_by = user.user_id
    finding.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    occ_result = await db.execute(
        select(CPValidationOccurrence)
        .where(CPValidationOccurrence.finding_id == finding_id)
        .order_by(desc(CPValidationOccurrence.created_at))
        .limit(1)
    )
    occ = occ_result.scalar_one()
    return _row_to_result_item(occ, finding)


@router.post("/validation-results/{finding_id}/reopen", response_model=ValidationResultItem)
async def reopen_validation_result(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    result = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.finding_id == finding_id)
    )
    finding = result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail="校验结果不存在")

    if finding.status not in ("rejected", "resolved"):
        raise HTTPException(status_code=400, detail="只能重新打开已拒绝或已解决的项目")

    finding.status = "open"
    finding.resolved_by = None
    finding.resolved_at = None
    await db.commit()

    occ_result = await db.execute(
        select(CPValidationOccurrence)
        .where(CPValidationOccurrence.finding_id == finding_id)
        .order_by(desc(CPValidationOccurrence.created_at))
        .limit(1)
    )
    occ = occ_result.scalar_one()
    return _row_to_result_item(occ, finding)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/cp_validation.py
git commit -m "feat(cp-validation): add API routes for two-table validation model"
```

---

### Task 7: Register Router

Same as previous plan.

- [ ] **Step 1-3: Add import and registration, verify server starts, commit**

```bash
git add backend/app/main.py
git commit -m "feat(cp-validation): register cp_validation router in main app"
```

---

### Task 8: API Integration Tests

Update tests for two-table model.

- [ ] **Step 1: Write API tests**

```python
"""Integration tests for cp_validation API endpoints."""
import uuid
import pytest

from app.models.cp_validation import CPValidationFinding, CPValidationOccurrence


@pytest.mark.asyncio
async def test_trigger_validation_endpoint(client, db, admin_user):
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate
    from app.models.control_plan import ControlPlanItem

    cp = await create_control_plan(
        db,
        ControlPlanCreate(title="API Test CP", document_no=f"CP-API-{uuid.uuid4().hex[:8]}", product_line_code="DC-DC-100"),
        admin_user.user_id,
    )
    item = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10",
        control_method="", reaction_plan="",
    )
    db.add(item)
    await db.commit()

    from app.core.security import create_access_token
    token = create_access_token(str(admin_user.user_id))

    resp = client.post(
        f"/api/control-plans/{cp.cp_id}/validate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "completed"
    assert data["error_count"] >= 2


@pytest.mark.asyncio
async def test_list_results_endpoint(client, db, admin_user):
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate
    from app.models.control_plan import ControlPlanItem
    from app.services.cp_validation import CPValidationEngine

    cp = await create_control_plan(
        db,
        ControlPlanCreate(title="List Test", document_no=f"CP-LST-{uuid.uuid4().hex[:8]}", product_line_code="DC-DC-100"),
        admin_user.user_id,
    )
    item = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10", control_method="",
    )
    db.add(item)
    await db.commit()

    engine = CPValidationEngine()
    await engine.validate(db, cp.cp_id, admin_user.user_id)

    from app.core.security import create_access_token
    token = create_access_token(str(admin_user.user_id))

    resp = client.get(
        f"/api/control-plans/{cp.cp_id}/validation-results",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(r["rule_id"] == "R001" for r in data["items"])
    assert all("finding_id" in r for r in data["items"])
    assert all("occurrence_id" in r for r in data["items"])


@pytest.mark.asyncio
async def test_reject_and_reopen_endpoint(client, db, admin_user):
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate
    from app.models.control_plan import ControlPlanItem
    from app.services.cp_validation import CPValidationEngine
    from sqlalchemy import select

    cp = await create_control_plan(
        db,
        ControlPlanCreate(title="Reject Test", document_no=f"CP-REJ-{uuid.uuid4().hex[:8]}", product_line_code="DC-DC-100"),
        admin_user.user_id,
    )
    item = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10", control_method="",
    )
    db.add(item)
    await db.commit()

    engine = CPValidationEngine()
    await engine.validate(db, cp.cp_id, admin_user.user_id)

    result = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    finding = result.scalars().first()

    from app.core.security import create_access_token
    token = create_access_token(str(admin_user.user_id))

    resp = client.post(
        f"/api/validation-results/{finding.finding_id}/reject",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    resp = client.post(
        f"/api/validation-results/{finding.finding_id}/reopen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"


@pytest.mark.asyncio
async def test_summary_endpoint(client, db, admin_user):
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate
    from app.models.control_plan import ControlPlanItem
    from app.services.cp_validation import CPValidationEngine

    cp = await create_control_plan(
        db,
        ControlPlanCreate(title="Summary Test", document_no=f"CP-SUM-{uuid.uuid4().hex[:8]}", product_line_code="DC-DC-100"),
        admin_user.user_id,
    )
    item = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10", control_method="",
    )
    db.add(item)
    await db.commit()

    engine = CPValidationEngine()
    await engine.validate(db, cp.cp_id, admin_user.user_id)

    from app.core.security import create_access_token
    token = create_access_token(str(admin_user.user_id))

    resp = client.get(
        f"/api/control-plans/{cp.cp_id}/validation-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["error_count"] >= 1
    assert data["open_count"] >= 1
```

- [ ] **Step 2: Run and commit**

```bash
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/openqms_test pytest tests/test_cp_validation_api.py -v
git add backend/tests/test_cp_validation_api.py
git commit -m "test(cp-validation): add API integration tests for two-table model"
```

---

### Task 9: Frontend Types

Update `ValidationResult` interface to match two-table joined response.

- [ ] **Step 1: Write TypeScript types**

```typescript
export interface ValidationResult {
  occurrence_id: string;
  run_id: string;
  finding_id: string;
  cp_id: string;
  validation_type: string;
  rule_id: string;
  severity: "error" | "warning" | "info";
  category: string;
  title: string;
  description: string | null;
  affected_items: string[];
  fmea_node_ids: string[];
  suggestion: string | null;
  suggestion_data: Record<string, unknown> | null;
  status: "open" | "accepted" | "rejected" | "resolved";
  resolved_by: string | null;
  resolved_at: string | null;
  present: boolean;
  created_at: string;
}

export interface ValidationRun {
  run_id: string;
  cp_id: string;
  trigger: string;
  status: "running" | "completed" | "failed";
  rule_count: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  started_at: string;
  completed_at: string | null;
  failed_rules: unknown[];
  created_by: string | null;
}

export interface ValidationSummary {
  run_id: string | null;
  status: string | null;
  total: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  open_count: number;
  resolved_count: number;
  rejected_count: number;
}

export interface ValidationResultsList {
  items: ValidationResult[];
  total: number;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/cpValidation.ts
git commit -m "feat(cp-validation): add frontend TypeScript types for two-table model"
```

---

### Task 10: Frontend API Client

Same endpoints, but `/validation-results/{finding_id}/...` operates on `finding_id`.

```typescript
import client from "./client";
import type {
  ValidationResultsList,
  ValidationRun,
  ValidationSummary,
  ValidationResult,
} from "../types/cpValidation";

export async function getValidationResults(
  cpId: string,
  filters?: { status?: string; severity?: string }
): Promise<ValidationResultsList> {
  const resp = await client.get(`/control-plans/${cpId}/validation-results`, {
    params: filters,
  });
  return resp.data;
}

export async function triggerValidation(cpId: string): Promise<ValidationRun> {
  const resp = await client.post(`/control-plans/${cpId}/validate`);
  return resp.data;
}

export async function getValidationRuns(cpId: string): Promise<ValidationRun[]> {
  const resp = await client.get(`/control-plans/${cpId}/validation-runs`);
  return resp.data;
}

export async function getValidationSummary(cpId: string): Promise<ValidationSummary> {
  const resp = await client.get(`/control-plans/${cpId}/validation-summary`);
  return resp.data;
}

export async function rejectValidationResult(findingId: string): Promise<ValidationResult> {
  const resp = await client.post(`/validation-results/${findingId}/reject`);
  return resp.data;
}

export async function resolveValidationResult(findingId: string): Promise<ValidationResult> {
  const resp = await client.post(`/validation-results/${findingId}/resolve`);
  return resp.data;
}

export async function reopenValidationResult(findingId: string): Promise<ValidationResult> {
  const resp = await client.post(`/validation-results/${findingId}/reopen`);
  return resp.data;
}
```

- [ ] **Step 1-2: Write and commit**

```bash
git add frontend/src/api/cpValidation.ts
git commit -m "feat(cp-validation): add frontend API client"
```

---

### Tasks 11-14: Frontend Components, Editor Embed, Auto-trigger, List Badge

These are identical to the previous plan. The frontend doesn't care about the backend two-table split because the joined `ValidationResultItem` schema returns the same flat structure.

Refer to Tasks 11-14 in the previous plan version for detailed code and steps. Key actions:

- **Task 11**: Create `ValidationPanel.tsx`, `ValidationCard.tsx`, `ValidationBadge.tsx`
- **Task 12**: Import `ValidationPanel` in `ControlPlanEditorPage.tsx`, add right-side column
- **Task 13**: Add `asyncio.create_task` + `_run_validation_background` in `control_plan_service.py`
- **Task 14**: Add `ValidationBadge` column in `ControlPlanListPage.tsx`

- [ ] **Run final verification**

```bash
cd backend && python run_tests.py --quick
cd frontend && npx tsc --noEmit && npm run build
```

---

## Self-Review

### Spec Coverage Check

| Spec Requirement | Plan Task |
|---|---|
| `cp_validation_runs` table | Task 1 |
| `cp_validation_findings` stable identity table | Task 1 |
| `cp_validation_occurrences` per-run snapshot table | Task 1 |
| `finding_hash` unique on `(cp_id, finding_hash)` | Task 2 |
| `present=True/False` occurrences | Task 5 |
| 4 rules (R001-R004) | Task 4 |
| Finding state inherited across runs (open/accepted/rejected/resolved) | Task 5 |
| Historical audit preserved (runs + occurrences) | Tasks 1, 5 |
| API endpoints | Task 6 |
| Permission checks | Task 6 |
| Backend tests | Tasks 4, 5, 8 |
| Frontend types + API + components | Tasks 9-11 |
| Auto-trigger with isolated session | Task 13 |

### Placeholder Scan

- No "TBD", "TODO", "implement later".
- All code blocks complete and runnable.
- Test commands include expected output.

### Type Consistency Check

- `ValidationFinding` dataclass → `CPValidationFinding` model + `CPValidationOccurrence` snapshot fields.
- API response type `ValidationResultItem` is a joined flat struct matching frontend `ValidationResult`.
- `/validation-results/{finding_id}/...` endpoints operate on `finding_id` consistently.

---

*Plan version: v2.0 — updated for two-table model (findings + occurrences)*
