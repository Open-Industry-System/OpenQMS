# Control Plan Intelligent Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rule-based control plan validation system using a two-table model (`findings` for stable identity + `occurrences` for per-run history), with a frontend panel for viewing and managing findings.

**Architecture:** Backend: SQLAlchemy models for runs/findings/occurrences + pure-function rule engine + orchestrator engine. `findings` holds stable identity (hash based on stable business keys, not volatile item UUIDs) and inherited user state; `occurrences` records each run's snapshot. Frontend: React sidebar panel with polling-based status updates. Auto-triggered on CP save via asyncio background task with isolated DB session.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Pydantic v2, pytest, httpx AsyncClient. React 18, TypeScript 5.6, Ant Design 5, Axios.

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
- `backend/app/models/__init__.py` — Register new models
- `backend/app/main.py` — Register router
- `backend/app/services/control_plan_service.py` — Add auto-trigger hook
- `frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx` — Embed panel
- `frontend/src/pages/planning/control-plan/ControlPlanListPage.tsx` — Add badge column

---

### Task 1: Data Models

**Files:**
- Create: `backend/app/models/cp_validation.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write the model file**

```python
import uuid
import hashlib
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text, Boolean, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CPValidationRun(Base):
    __tablename__ = "cp_validation_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_cpvrn_status",
        ),
        CheckConstraint(
            "trigger IN ('manual', 'auto_on_save', 'fmea_change')",
            name="ck_cpvrn_trigger",
        ),
    )

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

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'accepted', 'rejected', 'resolved')",
            name="ck_cvf_status",
        ),
        CheckConstraint(
            "severity IN ('error', 'warning', 'info')",
            name="ck_cvf_severity",
        ),
        CheckConstraint(
            "category IN ('coverage', 'consistency', 'completeness', 'risk', 'optimization')",
            name="ck_cvf_category",
        ),
    )

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

    __table_args__ = (
        CheckConstraint(
            "validation_type IN ('rule', 'llm', 'recommendation')",
            name="ck_cvo_validation_type",
        ),
    )

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


def compute_finding_hash(rule_id: str, stable_key: str, key_content: str) -> str:
    """Generate SHA256 hash using stable business keys (NOT volatile item UUIDs).

    stable_key: fmea_node_id|characteristic if available, else step_no|characteristic.
    This ensures the same business issue survives item UUID regeneration on CP save,
    and distinguishes different CP items that share the same FMEA ProcessStep.
    """
    payload = f"{rule_id}|{stable_key}|{key_content}"
    return hashlib.sha256(payload.encode()).hexdigest()
```

- [ ] **Step 2: Register models in `__init__.py`**

Add to `backend/app/models/__init__.py` after the last import line:

```python
from app.models.cp_validation import CPValidationRun, CPValidationFinding, CPValidationOccurrence
```

And add to `__all__`:
```python
    "CPValidationRun", "CPValidationFinding", "CPValidationOccurrence",
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/cp_validation.py backend/app/models/__init__.py
git commit -m "feat(cp-validation): add two-table model with CHECK constraints and stable hash"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/20260610_add_cp_validation_tables.py`

- [ ] **Step 1: Find current head**

```bash
cd backend && alembic history --verbose 2>/dev/null | head -5
```

Set the `down_revision` variable to the current head revision ID.

- [ ] **Step 2: Write the migration**

```python
"""Add cp validation tables.

Revision ID: 20260610_add_cp_validation
Revises: <SET_FROM_HEAD>
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260610_add_cp_validation"
down_revision = None  # SET THIS to current head
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
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_cpvrn_status"),
        sa.CheckConstraint("trigger IN ('manual', 'auto_on_save', 'fmea_change')", name="ck_cpvrn_trigger"),
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
        sa.CheckConstraint("status IN ('open', 'accepted', 'rejected', 'resolved')", name="ck_cvf_status"),
        sa.CheckConstraint("severity IN ('error', 'warning', 'info')", name="ck_cvf_severity"),
        sa.CheckConstraint("category IN ('coverage', 'consistency', 'completeness', 'risk', 'optimization')", name="ck_cvf_category"),
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
        sa.CheckConstraint("validation_type IN ('rule', 'llm', 'recommendation')", name="ck_cvo_validation_type"),
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

- [ ] **Step 3: Test the migration**

```bash
cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

Expected: No errors in either direction.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/20260610_add_cp_validation_tables.py
git commit -m "feat(cp-validation): add alembic migration with CHECK constraints"
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

**Files:**
- Create: `backend/app/services/cp_validation/rule_engine.py`

**Key design decisions:**
- `key_content` encodes the specific field/condition (e.g. "control_method_empty"), not item identity
- `stable_key` is `fmea_node_id|characteristic` if available, else `step_no|characteristic|sort_order` — never `item_id`
- Rule failures are collected in `failed_rules` list alongside returned findings

- [ ] **Step 1: Write the rule engine**

```python
"""Rule-based validation engine for Control Plans.

All rules are pure functions: (items, fmea_graph) -> (list[ValidationFinding], list[failed_rule_id]).
No database access. Fast synchronous execution.

Key design: finding_hash uses stable business keys (source_fmea_node_id or step_no),
NOT volatile item UUIDs that change on every CP save (update_control_plan deletes +
recreates items).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationFinding:
    rule_id: str
    severity: str
    category: str
    title: str
    description: str
    stable_key: str = ""
    key_content: str = ""
    item_id: str | None = None


_PLACEHOLDER_METHODS = {"", "见sop", "见 sop", "无", "待定", "tbd", "暂无", "暂不", "n/a", "na"}
_PLACEHOLDER_REACTIONS = {"", "无", "待定", "tbd", "暂无", "暂不", "n/a", "na"}


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _is_placeholder(val: str | None, placeholders: set[str]) -> bool:
    return _norm(val) in placeholders


def _stable_key(item: Any) -> str:
    """Business-stable identifier: FMEA node id + characteristic, else step_no + characteristic."""
    base = item.source_fmea_node_id or item.step_no or ""
    char = item.product_characteristic or item.process_characteristic or ""
    if char:
        return f"{base}|{char}"
    # Fallback for items without characteristic text
    order = str(getattr(item, "sort_order", 0))
    return f"{base}|#{order}"



# ─── Rule R001: Control method coverage ────────────────────────────────────

def rule_r001_control_method(items: list[Any]) -> tuple[list[ValidationFinding], list[str]]:
    findings = []
    for item in items:
        if _is_placeholder(item.control_method, _PLACEHOLDER_METHODS):
            sk = _stable_key(item)
            findings.append(ValidationFinding(
                rule_id="R001",
                severity="error",
                category="completeness",
                title="控制方法缺失",
                description=f"工序 {item.step_no or '?'}/{item.process_name or '?'} 的控制方法为空或仅含占位符",
                stable_key=sk,
                key_content="control_method_empty",
                item_id=str(item.item_id),
            ))
    return findings, []


# ─── Rule R002: Reaction plan completeness ─────────────────────────────────

def rule_r002_reaction_plan(items: list[Any]) -> tuple[list[ValidationFinding], list[str]]:
    findings = []
    for item in items:
        if _is_placeholder(item.reaction_plan, _PLACEHOLDER_REACTIONS):
            sk = _stable_key(item)
            findings.append(ValidationFinding(
                rule_id="R002",
                severity="error",
                category="completeness",
                title="反应计划缺失",
                description=f"工序 {item.step_no or '?'}/{item.process_name or '?'} 的反应计划为空或仅含占位符",
                stable_key=sk,
                key_content="reaction_plan_empty",
                item_id=str(item.item_id),
            ))
    return findings, []


# ─── Rule R003: Process step consistency with FMEA ─────────────────────────

def rule_r003_fmea_consistency(items: list[Any], fmea_graph: dict | None) -> tuple[list[ValidationFinding], list[str]]:
    if not fmea_graph:
        return [], []

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
                stable_key=_stable_key(item),
                key_content="node_deleted",
                item_id=str(item.item_id),
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
                stable_key=_stable_key(item),
                key_content="mismatch",
                item_id=str(item.item_id),
            ))

    return findings, []


# ─── Rule R004: Special class annotation check ─────────────────────────────

def rule_r004_special_class(items: list[Any]) -> tuple[list[ValidationFinding], list[str]]:
    findings = []
    for item in items:
        sc = _norm(item.special_class)
        if sc not in ("cc", "sc"):
            continue
        missing = []
        if _is_placeholder(item.evaluation_method, _PLACEHOLDER_METHODS):
            missing.append("evaluation_method")
        if _is_placeholder(item.control_method, _PLACEHOLDER_METHODS):
            missing.append("control_method")
        if missing:
            sk = _stable_key(item)
            findings.append(ValidationFinding(
                rule_id="R004",
                severity="warning",
                category="coverage",
                title="特殊特性控制不完整",
                description=f"工序 {item.step_no or '?'} 标记为 {item.special_class}，但{','.join(missing)}为空",
                stable_key=sk,
                key_content=f"special_class_{sc}",
                item_id=str(item.item_id),
            ))
    return findings, []


# ─── Rule registry ─────────────────────────────────────────────────────────

RULE_REGISTRY: list = [
    ("R001", rule_r001_control_method),
    ("R002", rule_r002_reaction_plan),
    ("R003", rule_r003_fmea_consistency),
    ("R004", rule_r004_special_class),
]


def run_all_rules(cp: Any, items: list[Any], fmea_graph: dict | None) -> tuple[list[ValidationFinding], list[str]]:
    """Execute all rules and return (merged_findings, failed_rule_ids)."""
    all_findings: list[ValidationFinding] = []
    failed_rules: list[str] = []

    for rule_id, rule_fn in RULE_REGISTRY:
        try:
            if rule_id == "R003":
                findings, _ = rule_fn(items, fmea_graph)
            else:
                findings, _ = rule_fn(items)
            all_findings.extend(findings)
        except Exception:
            failed_rules.append(rule_id)

    return all_findings, failed_rules
```

- [ ] **Step 2: Write the tests**

Create `backend/tests/test_cp_validation_rules.py`:

```python
"""Unit tests for cp_validation rule engine."""
import uuid
import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.cp_validation.rule_engine import (
    rule_r001_control_method,
    rule_r002_reaction_plan,
    rule_r003_fmea_consistency,
    rule_r004_special_class,
    run_all_rules,
    _stable_key,
)


class FakeItem:
    def __init__(self, **kwargs):
        self.item_id = kwargs.get("item_id", uuid.uuid4())
        self.step_no = kwargs.get("step_no", "")
        self.process_name = kwargs.get("process_name", "")
        self.control_method = kwargs.get("control_method", "")
        self.reaction_plan = kwargs.get("reaction_plan", "")
        self.special_class = kwargs.get("special_class", "")
        self.evaluation_method = kwargs.get("evaluation_method", "")
        self.source_fmea_node_id = kwargs.get("source_fmea_node_id", None)
        self.product_characteristic = kwargs.get("product_characteristic", "")
        self.process_characteristic = kwargs.get("process_characteristic", "")
        self.sort_order = kwargs.get("sort_order", 0)


# ─── stable_key ─────────────────────────────────────────────────────────────

def test_stable_key_uses_fmea_node_id_and_characteristic():
    item = FakeItem(source_fmea_node_id="node-1", step_no="10", product_characteristic="尺寸A")
    assert _stable_key(item) == "node-1|尺寸A"


def test_stable_key_falls_back_to_step_no_and_sort_order():
    item = FakeItem(source_fmea_node_id=None, step_no="20", sort_order=3)
    assert _stable_key(item) == "20|#3"


def test_stable_key_distinguishes_same_fmea_node_different_characteristic():
    """Two CP items sharing the same FMEA ProcessStep but different characteristics
    must produce different stable_key (and thus different findings)."""
    item_a = FakeItem(source_fmea_node_id="node-1", product_characteristic="尺寸A", control_method="")
    item_b = FakeItem(source_fmea_node_id="node-1", product_characteristic="尺寸B", control_method="")
    assert _stable_key(item_a) != _stable_key(item_b)

    findings_a, _ = rule_r001_control_method([item_a])
    findings_b, _ = rule_r001_control_method([item_b])
    assert len(findings_a) == 1
    assert len(findings_b) == 1
    assert findings_a[0].stable_key != findings_b[0].stable_key


# ─── R001 ───────────────────────────────────────────────────────────────────

def test_r001_detects_empty_control_method():
    items = [FakeItem(source_fmea_node_id="n1", control_method="")]
    findings, failed = rule_r001_control_method(items)
    assert len(findings) == 1
    assert findings[0].rule_id == "R001"
    assert findings[0].severity == "error"
    assert findings[0].stable_key == "n1|#0"


def test_r001_ignores_valid_control_method():
    items = [FakeItem(control_method="X-bar R chart")]
    findings, _ = rule_r001_control_method(items)
    assert len(findings) == 0


def test_r001_detects_placeholder_sop():
    items = [FakeItem(source_fmea_node_id="n1", control_method="见SOP")]
    findings, _ = rule_r001_control_method(items)
    assert len(findings) == 1


# ─── R002 ───────────────────────────────────────────────────────────────────

def test_r002_detects_empty_reaction_plan():
    items = [FakeItem(source_fmea_node_id="n1", reaction_plan="")]
    findings, _ = rule_r002_reaction_plan(items)
    assert len(findings) == 1
    assert findings[0].rule_id == "R002"


# ─── R003 ───────────────────────────────────────────────────────────────────

def test_r003_detects_deleted_fmea_node():
    items = [FakeItem(step_no="10", process_name="焊接", source_fmea_node_id="node-1")]
    fmea_graph = {"nodes": [], "edges": []}
    findings, _ = rule_r003_fmea_consistency(items, fmea_graph)
    assert len(findings) == 1
    assert findings[0].title == "FMEA源工序已删除"


def test_r003_detects_name_mismatch():
    items = [FakeItem(step_no="10", process_name="旧名称", source_fmea_node_id="node-1")]
    fmea_graph = {
        "nodes": [{"id": "node-1", "type": "ProcessStep", "process_number": "10", "name": "新名称"}],
        "edges": [],
    }
    findings, _ = rule_r003_fmea_consistency(items, fmea_graph)
    assert len(findings) == 1
    assert "不一致" in findings[0].title


def test_r003_passes_matching():
    items = [FakeItem(step_no="10", process_name="焊接", source_fmea_node_id="node-1")]
    fmea_graph = {
        "nodes": [{"id": "node-1", "type": "ProcessStep", "process_number": "10", "name": "焊接"}],
        "edges": [],
    }
    findings, _ = rule_r003_fmea_consistency(items, fmea_graph)
    assert len(findings) == 0


def test_r003_empty_graph_returns_empty():
    findings, _ = rule_r003_fmea_consistency([FakeItem(source_fmea_node_id="n1")], None)
    assert len(findings) == 0


# ─── R004 ───────────────────────────────────────────────────────────────────

def test_r004_detects_cc_missing_methods():
    items = [FakeItem(step_no="10", special_class="CC", evaluation_method="", control_method="")]
    findings, _ = rule_r004_special_class(items)
    assert len(findings) == 1
    assert "CC" in findings[0].description


def test_r004_passes_when_methods_present():
    items = [FakeItem(special_class="CC", evaluation_method="目视检查", control_method="SPC")]
    findings, _ = rule_r004_special_class(items)
    assert len(findings) == 0


def test_r004_ignores_non_special():
    items = [FakeItem(special_class="", evaluation_method="", control_method="")]
    findings, _ = rule_r004_special_class(items)
    assert len(findings) == 0


# ─── run_all_rules ──────────────────────────────────────────────────────────

def test_run_all_rules_returns_all_findings():
    items = [
        FakeItem(step_no="10", control_method="", reaction_plan="", special_class="CC"),
    ]
    findings, failed = run_all_rules(None, items, None)
    assert len(findings) == 3  # R001 + R002 + R004
    assert failed == []
```

- [ ] **Step 3: Run tests**

```bash
cd backend && SECRET_KEY=test python -m pytest tests/test_cp_validation_rules.py -v
```

Expected: 15 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/cp_validation/rule_engine.py backend/tests/test_cp_validation_rules.py
git commit -m "feat(cp-validation): add rule engine with stable business-key hashing and tests"
```

---

### Task 5: Validation Engine (Orchestrator)

**Files:**
- Create: `backend/app/services/cp_validation/engine.py`
- Create: `backend/app/services/cp_validation/__init__.py`

**Key design decisions:**
- Finding hash uses `stable_key` (not item UUID) for cross-save identity
- No `present=False` occurrences — only record what IS found (absent = no occurrence)
- Stale running runs (>5 min) are auto-marked `failed` before creating new run
- `failed_rules` populated from rule engine return
- `IntegrityError` on running constraint → raise custom `ValidationAlreadyRunning` exception

- [ ] **Step 1: Write package init**

```python
# backend/app/services/cp_validation/__init__.py
from .engine import CPValidationEngine, ValidationAlreadyRunning

__all__ = ["CPValidationEngine", "ValidationAlreadyRunning"]
```

- [ ] **Step 2: Write the engine**

```python
"""Control Plan Validation Engine — orchestrates rule execution with two-table persistence.

findings  = stable identity (hash uses business keys) + inherited user state
occurrences = per-run snapshot of what was detected (only present=true records)
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

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

STALE_RUN_TIMEOUT = timedelta(minutes=5)


class ValidationAlreadyRunning(Exception):
    """Raised when a validation run is already in progress for this CP."""
    pass


class CPValidationEngine:

    async def validate(
        self,
        db: AsyncSession,
        cp_id: uuid.UUID,
        user_id: uuid.UUID,
        trigger: str = "manual",
    ) -> CPValidationRun:
        # 1. Handle stale running runs (crashed worker, OOM, etc.)
        await self._fail_stale_runs(db, cp_id)

        # 2. Create run (may raise IntegrityError if concurrent)
        run = CPValidationRun(
            cp_id=cp_id,
            trigger=trigger,
            status="running",
            created_by=user_id,
        )
        db.add(run)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise ValidationAlreadyRunning(f"Validation already running for CP {cp_id}")

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

    async def _fail_stale_runs(self, db: AsyncSession, cp_id: uuid.UUID) -> None:
        """Mark runs that have been 'running' for >5 min as failed."""
        cutoff = datetime.now(timezone.utc) - STALE_RUN_TIMEOUT
        result = await db.execute(
            select(CPValidationRun).where(
                CPValidationRun.cp_id == cp_id,
                CPValidationRun.status == "running",
                CPValidationRun.started_at < cutoff,
            )
        )
        stale = result.scalars().all()
        for run in stale:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.failed_rules = (run.failed_rules or []) + ["timeout"]
            logger.warning("Marked stale run %s as failed", run.run_id)

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

        findings, failed_rules = run_all_rules(cp, items, fmea_graph)

        # Load existing findings for this CP
        existing_result = await db.execute(
            select(CPValidationFinding).where(CPValidationFinding.cp_id == cp_id)
        )
        existing_by_hash = {row.finding_hash: row for row in existing_result.scalars().all()}

        error_count = 0
        warning_count = 0
        info_count = 0

        for finding in findings:
            h = compute_finding_hash(finding.rule_id, finding.stable_key, finding.key_content)

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

            # Create occurrence (always present=true — we only record what IS found)
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

            if finding.severity == "error":
                error_count += 1
            elif finding.severity == "warning":
                warning_count += 1
            else:
                info_count += 1

        run.status = "completed"
        run.rule_count = len(findings)
        run.error_count = error_count
        run.warning_count = warning_count
        run.info_count = info_count
        run.failed_rules = failed_rules
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
```

- [ ] **Step 3: Write and run the engine test**

Create `backend/tests/test_cp_validation_engine.py`:

```python
"""Unit tests for CPValidationEngine orchestrator (two-table model)."""
import uuid
import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import select, func

from app.services.cp_validation.engine import CPValidationEngine, ValidationAlreadyRunning
from app.models.cp_validation import (
    CPValidationRun, CPValidationFinding, CPValidationOccurrence, compute_finding_hash,
)
from app.models.control_plan import ControlPlanItem


@pytest.mark.asyncio
async def test_validate_creates_run_and_occurrences(db, admin_user):
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
        source_fmea_node_id="pfmea-step-1",
        control_method="",
        reaction_plan="",
    )
    db.add(item)
    await db.flush()

    engine = CPValidationEngine()
    run = await engine.validate(db, cp.cp_id, admin_user.user_id, trigger="manual")

    assert run.status == "completed"
    assert run.error_count >= 2
    assert run.failed_rules == []

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
    """Same finding_hash (from stable business key) creates one finding, two occurrences."""
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate

    cp_data = ControlPlanCreate(
        title="Test CP Dedup",
        document_no=f"CP-DEDUP-{uuid.uuid4().hex[:8]}",
        product_line_code="DC-DC-100",
    )
    cp = await create_control_plan(db, cp_data, admin_user.user_id)

    item = ControlPlanItem(
        item_id=uuid.uuid4(),
        cp_id=cp.cp_id,
        step_no="10",
        source_fmea_node_id="pfmea-step-1",
        control_method="",
    )
    db.add(item)
    await db.flush()

    engine = CPValidationEngine()
    run1 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result_f = await db.execute(
        select(func.count()).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    finding_count = result_f.scalar()

    # Second run with same data — stable_key unchanged so finding reused
    run2 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result_f2 = await db.execute(
        select(func.count()).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    assert result_f2.scalar() == finding_count  # no new findings

    result_o2 = await db.execute(
        select(func.count()).where(CPValidationOccurrence.run_id == run2.run_id)
    )
    assert result_o2.scalar() >= 1  # new occurrences for run2


@pytest.mark.asyncio
async def test_finding_survives_item_uuid_change(db, admin_user):
    """When update_control_plan deletes+recreates items with new UUIDs,
    the finding_hash (based on source_fmea_node_id) remains stable."""
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate

    cp_data = ControlPlanCreate(
        title="Test Stable Hash",
        document_no=f"CP-HASH-{uuid.uuid4().hex[:8]}",
        product_line_code="DC-DC-100",
    )
    cp = await create_control_plan(db, cp_data, admin_user.user_id)

    # Run 1: item with UUID-A, source_fmea_node_id="pfmea-step-1"
    item1 = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10",
        source_fmea_node_id="pfmea-step-1", control_method="",
    )
    db.add(item1)
    await db.flush()

    engine = CPValidationEngine()
    run1 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result1 = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    findings_before = result1.scalars().all()
    assert len(findings_before) >= 1

    # Simulate what update_control_plan does: delete old item, create new with new UUID
    await db.delete(item1)
    await db.flush()
    item2 = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10",
        source_fmea_node_id="pfmea-step-1", control_method="",  # same business identity
    )
    db.add(item2)
    await db.flush()

    # Run 2: new item UUID but same source_fmea_node_id
    run2 = await engine.validate(db, cp.cp_id, admin_user.user_id)

    result2 = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.cp_id == cp.cp_id)
    )
    findings_after = result2.scalars().all()
    # Same number of findings — no duplicates because hash is stable
    assert len(findings_after) == len(findings_before)


@pytest.mark.asyncio
async def test_stale_run_auto_failed(db, admin_user):
    """A run stuck in 'running' for >5 min should be auto-failed on next validate."""
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate
    from datetime import datetime, timedelta, timezone

    cp_data = ControlPlanCreate(
        title="Stale Run Test",
        document_no=f"CP-STALE-{uuid.uuid4().hex[:8]}",
        product_line_code="DC-DC-100",
    )
    cp = await create_control_plan(db, cp_data, admin_user.user_id)

    # Manually create a stale running run
    stale_run = CPValidationRun(
        cp_id=cp.cp_id, trigger="auto_on_save", status="running",
        created_by=admin_user.user_id,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db.add(stale_run)
    await db.flush()

    item = ControlPlanItem(
        item_id=uuid.uuid4(), cp_id=cp.cp_id, step_no="10",
        source_fmea_node_id="pfmea-step-1", control_method="",
    )
    db.add(item)
    await db.flush()

    engine = CPValidationEngine()
    run = await engine.validate(db, cp.cp_id, admin_user.user_id, trigger="manual")

    assert run.status == "completed"

    # Verify the stale run was marked failed
    await db.refresh(stale_run)
    assert stale_run.status == "failed"
```

- [ ] **Step 4: Run tests**

```bash
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/openqms_test SECRET_KEY=test python -m pytest tests/test_cp_validation_engine.py -v
```

Note: If `openqms_test` DB doesn't exist:
```bash
docker compose exec db psql -U postgres -c "CREATE DATABASE openqms_test;"
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/cp_validation/
git add backend/tests/test_cp_validation_engine.py
git commit -m "feat(cp-validation): add validation engine with stale-run recovery and stable hashing"
```

---

### Task 6: API Routes

**Files:**
- Create: `backend/app/api/cp_validation.py`

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
from app.services.cp_validation import CPValidationEngine, ValidationAlreadyRunning

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
    """List validation results for latest run (join occurrences + findings)."""
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
    """Manually trigger a validation run. Synchronous — waits for completion."""
    engine = CPValidationEngine()
    try:
        run = await engine.validate(db, cp_id, user.user_id, trigger="manual")
    except ValidationAlreadyRunning:
        raise HTTPException(status_code=409, detail="该控制计划的校验正在运行中")
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
    """List validation run history for a control plan."""
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
    """Get summary of the latest validation run."""
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


async def _get_finding(db: AsyncSession, finding_id: uuid.UUID) -> CPValidationFinding:
    result = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.finding_id == finding_id)
    )
    finding = result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail="校验结果不存在")
    return finding


async def _get_latest_occurrence(db: AsyncSession, finding_id: uuid.UUID) -> CPValidationOccurrence:
    result = await db.execute(
        select(CPValidationOccurrence)
        .where(CPValidationOccurrence.finding_id == finding_id)
        .order_by(desc(CPValidationOccurrence.created_at))
        .limit(1)
    )
    return result.scalar_one()


async def _find_and_respond(db: AsyncSession, finding_id: uuid.UUID) -> ValidationResultItem:
    finding = await _get_finding(db, finding_id)
    occ = await _get_latest_occurrence(db, finding_id)
    return _row_to_result_item(occ, finding)


@router.post("/validation-results/{finding_id}/reject", response_model=ValidationResultItem)
async def reject_validation_result(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    """Reject a validation finding."""
    finding = await _get_finding(db, finding_id)
    finding.status = "rejected"
    finding.resolved_by = user.user_id
    finding.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return await _find_and_respond(db, finding_id)


@router.post("/validation-results/{finding_id}/resolve", response_model=ValidationResultItem)
async def resolve_validation_result(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    """Mark a validation finding as resolved."""
    finding = await _get_finding(db, finding_id)
    finding.status = "resolved"
    finding.resolved_by = user.user_id
    finding.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return await _find_and_respond(db, finding_id)


@router.post("/validation-results/{finding_id}/reopen", response_model=ValidationResultItem)
async def reopen_validation_result(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    """Reopen a rejected or resolved validation finding."""
    finding = await _get_finding(db, finding_id)
    if finding.status not in ("rejected", "resolved"):
        raise HTTPException(status_code=400, detail="只能重新打开已拒绝或已解决的项目")
    finding.status = "open"
    finding.resolved_by = None
    finding.resolved_at = None
    await db.commit()
    return await _find_and_respond(db, finding_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/cp_validation.py
git commit -m "feat(cp-validation): add API routes with 409 for concurrent runs"
```

---

### Task 7: Register Router

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add import**

Find the existing control_plan router import:
```python
from app.api.control_plan import router as control_plan_router
```

Add below it:
```python
from app.api.cp_validation import router as cp_validation_router
```

- [ ] **Step 2: Register the router**

Find where control_plan router is included:
```python
app.include_router(control_plan_router)
```

Add below it:
```python
app.include_router(cp_validation_router)
```

- [ ] **Step 3: Verify server starts**

```bash
cd backend && SECRET_KEY=test uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 2
curl -s http://localhost:8000/docs | grep -q "cp-validation" && echo "Router registered" || echo "Router NOT found"
kill %1 2>/dev/null
```

Expected: "Router registered"

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(cp-validation): register cp_validation router in main app"
```

---

### Task 8: API Integration Tests

**Files:**
- Create: `backend/tests/test_cp_validation_api.py`

**Pattern:** Use `httpx.AsyncClient` + `ASGITransport` + `dependency_overrides`, matching `test_capa_draft_api.py`.

- [ ] **Step 1: Write API tests**

```python
"""Integration tests for cp_validation API endpoints."""
import uuid
import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import status
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db
from app.core.permissions import get_current_user, Module, PermissionLevel
from app.models.user import User


@pytest.fixture
def override_dependencies():
    """Inject mock DB and authenticated user with PLANNING + EDIT permission."""
    async def mock_get_db():
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        db.get = AsyncMock(return_value=None)
        return db

    async def mock_get_current_user():
        user = MagicMock(spec=User)
        user.user_id = uuid.uuid4()
        user.username = "engineer"
        user.role = "quality_engineer"
        user.role_id = uuid.uuid4()
        user.is_active = True
        user.role_definition = MagicMock()
        user.role_definition.bypass_row_level_security = True
        return user

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)):
        yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_dependencies_view():
    """Same but with VIEW-only permission."""
    async def mock_get_db():
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        return db

    async def mock_get_current_user():
        user = MagicMock(spec=User)
        user.user_id = uuid.uuid4()
        user.username = "viewer"
        user.role = "viewer"
        user.role_id = uuid.uuid4()
        user.is_active = True
        user.role_definition = MagicMock()
        user.role_definition.bypass_row_level_security = False
        return user

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.VIEW)):
        yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_dependencies_results():
    """Mock DB returning rows for list-results + finding + occurrence (reject/resolve)."""
    from datetime import datetime, timezone

    fake_finding_id = uuid.uuid4()
    fake_occ_id = uuid.uuid4()
    fake_run_id = uuid.uuid4()
    fake_cp_id = uuid.uuid4()

    # Fake ORM objects (reject/resolve need these, not just row dicts)
    fake_finding = MagicMock()
    fake_finding.finding_id = fake_finding_id
    fake_finding.cp_id = fake_cp_id
    fake_finding.finding_hash = "abc123"
    fake_finding.rule_id = "R001"
    fake_finding.severity = "error"
    fake_finding.category = "completeness"
    fake_finding.status = "open"
    fake_finding.resolved_by = None
    fake_finding.resolved_at = None
    fake_finding.created_at = datetime.now(timezone.utc)

    fake_occ = MagicMock()
    fake_occ.occurrence_id = fake_occ_id
    fake_occ.run_id = fake_run_id
    fake_occ.finding_id = fake_finding_id
    fake_occ.cp_id = fake_cp_id
    fake_occ.validation_type = "rule"
    fake_occ.title = "控制方法缺失"
    fake_occ.description = "test"
    fake_occ.affected_items = []
    fake_occ.fmea_node_ids = []
    fake_occ.suggestion = None
    fake_occ.suggestion_data = None
    fake_occ.present = True
    fake_occ.created_at = datetime.now(timezone.utc)

    # Row for list-results join query (mappings)
    mock_row = MagicMock()
    mock_row.finding_id = fake_finding_id
    mock_row.occurrence_id = fake_occ_id
    mock_row.rule_id = "R001"
    mock_row.severity = "error"
    mock_row.status = "open"
    mock_row.title = "控制方法缺失"
    mock_row.description = "test"
    mock_row.present = True
    mock_row.fmea_node_ids = []

    # Different result objects per call type
    list_result = MagicMock()
    list_result.mappings.return_value = [mock_row]

    finding_result = MagicMock()
    finding_result.scalar_one_or_none.return_value = fake_finding

    occ_result = MagicMock()
    occ_result.scalar_one.return_value = fake_occ

    call_count = 0

    async def mock_execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Call 1 (list-results): join query -> mappings
        # Call 2+ (reject/resolve): finding select -> scalar_one_or_none
        # Call 3+ (reject/resolve): occurrence select -> scalar_one
        # We distinguish by checking if the SQL contains CPValidationFinding vs CPValidationOccurrence
        sql_str = str(args[0]) if args else ""
        if "cp_validation_findings" in sql_str and "cp_validation_occurrences" not in sql_str:
            return finding_result
        if "cp_validation_occurrences" in sql_str and "ORDER BY" in sql_str:
            return occ_result
        return list_result

    async def mock_get_db():
        db = MagicMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.execute = AsyncMock(side_effect=mock_execute)
        db.get = AsyncMock(return_value=None)
        return db

    async def mock_get_current_user():
        user = MagicMock(spec=User)
        user.user_id = uuid.uuid4()
        user.username = "engineer"
        user.role = "quality_engineer"
        user.role_id = uuid.uuid4()
        user.is_active = True
        user.role_definition = MagicMock()
        user.role_definition.bypass_row_level_security = True
        return user

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)):
        yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_validate_unauthenticated():
    """POST /control-plans/{id}/validate without auth → 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/control-plans/{uuid.uuid4()}/validate")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_results_unauthenticated():
    """GET /control-plans/{id}/validation-results without auth → 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/control-plans/{uuid.uuid4()}/validation-results")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_summary_unauthenticated():
    """GET /control-plans/{id}/validation-summary without auth → 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/control-plans/{uuid.uuid4()}/validation-summary")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_validate_returns_200(override_dependencies):
    """POST /validate with auth — mock engine to assert 200 response structure."""
    from unittest.mock import patch as mock_patch
    mock_run = MagicMock()
    mock_run.run_id = uuid.uuid4()
    mock_run.cp_id = uuid.uuid4()
    mock_run.trigger = "manual"
    mock_run.status = "completed"
    mock_run.rule_count = 4
    mock_run.error_count = 1
    mock_run.warning_count = 0
    mock_run.info_count = 0
    mock_run.started_at = "2026-06-10T12:00:00"
    mock_run.completed_at = "2026-06-10T12:00:01"
    mock_run.failed_rules = []
    mock_run.created_by = None

    with mock_patch(
        "app.services.cp_validation.engine.CPValidationEngine.validate",
        new=AsyncMock(return_value=mock_run),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(f"/api/control-plans/{uuid.uuid4()}/validate")

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["status"] == "completed"
    assert body["error_count"] == 1


@pytest.mark.asyncio
async def test_validate_returns_409_when_already_running(override_dependencies):
    """POST /validate when a run is already in progress → 409."""
    from unittest.mock import patch as mock_patch
    from app.services.cp_validation.engine import ValidationAlreadyRunning

    with mock_patch(
        "app.services.cp_validation.engine.CPValidationEngine.validate",
        new=AsyncMock(side_effect=ValidationAlreadyRunning()),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(f"/api/control-plans/{uuid.uuid4()}/validate")

    assert resp.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_results_returns_200(override_dependencies_results):
    """GET /validation-results with auth — assert response is { items, total }."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/api/control-plans/{uuid.uuid4()}/validation-results")

    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 0


@pytest.mark.asyncio
async def test_reject_finding_returns_200(override_dependencies_results):
    """POST /validation-results/{id}/reject → 200."""
    finding_id = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/validation-results/{finding_id}/reject")
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_resolve_finding_returns_200(override_dependencies_results):
    """POST /validation-results/{id}/resolve → 200."""
    finding_id = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/validation-results/{finding_id}/resolve")
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_viewer_cannot_validate(override_dependencies_view):
    """POST /validate with VIEW-only permission → 403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/api/control-plans/{uuid.uuid4()}/validate")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
```

- [ ] **Step 2: Run tests**

```bash
cd backend && SECRET_KEY=test python -m pytest tests/test_cp_validation_api.py -v
```

Expected: 9 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_cp_validation_api.py
git commit -m "test(cp-validation): add API integration tests with mock dependencies"
```

---

### Task 9: Frontend Types

**Files:**
- Create: `frontend/src/types/cpValidation.ts`

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
git commit -m "feat(cp-validation): add frontend TypeScript types"
```

---

### Task 10: Frontend API Client

**Files:**
- Create: `frontend/src/api/cpValidation.ts`

- [ ] **Step 1: Write the API client**

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

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/cpValidation.ts
git commit -m "feat(cp-validation): add frontend API client"
```

---

### Task 11: Frontend Components

**Files:**
- Create: `frontend/src/components/control-plan/ValidationCard.tsx`
- Create: `frontend/src/components/control-plan/ValidationPanel.tsx`
- Create: `frontend/src/components/control-plan/ValidationBadge.tsx`

- [ ] **Step 1: Write ValidationCard**

```tsx
import { Card, Tag, Button, Space, Typography } from "antd";
import {
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import type { ValidationResult } from "../../types/cpValidation";

const { Text } = Typography;

const severityConfig = {
  error: { color: "red", icon: <CloseCircleOutlined />, label: "错误" },
  warning: { color: "orange", icon: <ExclamationCircleOutlined />, label: "警告" },
  info: { color: "blue", icon: <InfoCircleOutlined />, label: "提示" },
};

interface Props {
  result: ValidationResult;
  onReject: (findingId: string) => void;
  onResolve: (findingId: string) => void;
  onReopen: (findingId: string) => void;
  loading?: boolean;
}

export default function ValidationCard({ result, onReject, onResolve, onReopen, loading }: Props) {
  const config = severityConfig[result.severity] || severityConfig.info;

  return (
    <Card
      size="small"
      style={{ marginBottom: 8, borderLeft: `3px solid ${config.color}` }}
      bodyStyle={{ padding: 12 }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        <span style={{ color: config.color, fontSize: 16, marginTop: 2 }}>{config.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Text strong>{result.title}</Text>
            <Tag color={config.color}>{config.label}</Tag>
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {result.description}
          </Text>
          {result.suggestion && (
            <div style={{ marginTop: 4, padding: 6, background: "#f6ffed", borderRadius: 4 }}>
              <Text type="success" style={{ fontSize: 12 }}>
                建议: {result.suggestion}
              </Text>
            </div>
          )}
          <div style={{ marginTop: 8, display: "flex", justifyContent: "flex-end" }}>
            {result.status === "open" && (
              <Space size="small">
                <Button size="small" onClick={() => onResolve(result.finding_id)} loading={loading}>
                  标记已解决
                </Button>
                <Button size="small" danger onClick={() => onReject(result.finding_id)} loading={loading}>
                  忽略
                </Button>
              </Space>
            )}
            {result.status === "rejected" && (
              <Button size="small" icon={<UndoOutlined />} onClick={() => onReopen(result.finding_id)} loading={loading}>
                恢复
              </Button>
            )}
            {result.status === "resolved" && (
              <Tag color="green">已解决</Tag>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Write ValidationPanel**

```tsx
import { useState, useEffect, useCallback } from "react";
import { Card, Button, Spin, Empty, Alert, Badge, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import ValidationCard from "./ValidationCard";
import {
  getValidationResults,
  getValidationSummary,
  triggerValidation,
  rejectValidationResult,
  resolveValidationResult,
  reopenValidationResult,
} from "../../api/cpValidation";
import type { ValidationResult, ValidationSummary } from "../../types/cpValidation";

const { Text } = Typography;

interface Props {
  cpId: string;
}

const POLL_INTERVAL = 2000;
const MAX_POLLS = 30;

export default function ValidationPanel({ cpId }: Props) {
  const [results, setResults] = useState<ValidationResult[]>([]);
  const [summary, setSummary] = useState<ValidationSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [pollCount, setPollCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [resList, sum] = await Promise.all([
        getValidationResults(cpId),
        getValidationSummary(cpId),
      ]);
      setResults(resList.items);
      setSummary(sum);
      setError(null);
      return sum.status;
    } catch (e) {
      setError("加载校验结果失败");
      return null;
    }
  }, [cpId]);

  const handleTrigger = async () => {
    setLoading(true);
    setError(null);
    try {
      await triggerValidation(cpId);
      setPolling(true);
      setPollCount(0);
    } catch (e) {
      setError("触发校验失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!polling) return;

    const timer = setInterval(async () => {
      const status = await fetchData();
      setPollCount((c) => c + 1);

      if (status === "completed" || status === "failed" || pollCount >= MAX_POLLS) {
        setPolling(false);
      }
    }, POLL_INTERVAL);

    return () => clearInterval(timer);
  }, [polling, cpId, pollCount, fetchData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleAction = async (action: (id: string) => Promise<unknown>, id: string) => {
    setLoading(true);
    try {
      await action(id);
      await fetchData();
    } catch (e) {
      setError("操作失败");
    } finally {
      setLoading(false);
    }
  };

  const errorCount = summary?.error_count || 0;
  const warningCount = summary?.warning_count || 0;

  return (
    <Card
      title={
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>
            智能校验
            {errorCount > 0 && <Badge count={errorCount} style={{ backgroundColor: "#ff4d4f", marginLeft: 8 }} />}
            {errorCount === 0 && warningCount > 0 && <Badge count={warningCount} style={{ backgroundColor: "#faad14", marginLeft: 8 }} />}
          </span>
          <Button
            size="small"
            icon={<ReloadOutlined spin={polling} />}
            onClick={handleTrigger}
            loading={loading}
            disabled={polling}
          >
            {polling ? "校验中..." : "重新校验"}
          </Button>
        </div>
      }
      size="small"
      style={{ width: 360 }}
    >
      {error && <Alert message={error} type="error" showIcon style={{ marginBottom: 12 }} />}

      {polling && results.length === 0 && (
        <div style={{ textAlign: "center", padding: 24 }}>
          <Spin />
          <Text type="secondary" style={{ display: "block", marginTop: 8 }}>正在执行校验...</Text>
        </div>
      )}

      {!polling && results.length === 0 && !error && (
        <Empty description="暂无校验结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}

      {results.length > 0 && (
        <div style={{ maxHeight: "calc(100vh - 300px)", overflowY: "auto" }}>
          {results.map((r) => (
            <ValidationCard
              key={r.occurrence_id}
              result={r}
              onReject={(id) => handleAction(rejectValidationResult, id)}
              onResolve={(id) => handleAction(resolveValidationResult, id)}
              onReopen={(id) => handleAction(reopenValidationResult, id)}
              loading={loading}
            />
          ))}
        </div>
      )}

      {summary && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #f0f0f0", fontSize: 12 }}>
          <Text type="secondary">
            共 {summary.total} 项:{" "}
            <span style={{ color: "#ff4d4f" }}>{summary.error_count} 错误</span>,{" "}
            <span style={{ color: "#faad14" }}>{summary.warning_count} 警告</span>,{" "}
            <span style={{ color: "#1890ff" }}>{summary.info_count} 提示</span>
            {" | "}
            {summary.open_count} 待处理, {summary.resolved_count} 已解决, {summary.rejected_count} 已忽略
          </Text>
        </div>
      )}
    </Card>
  );
}
```

- [ ] **Step 3: Write ValidationBadge**

```tsx
import { Badge, Tooltip } from "antd";

interface Props {
  errorCount: number;
  warningCount: number;
  total: number;
}

export default function ValidationBadge({ errorCount, warningCount, total }: Props) {
  if (total === 0) {
    return <Tooltip title="未校验"><Badge status="default" /></Tooltip>;
  }
  if (errorCount > 0) {
    return <Tooltip title={`${errorCount} 个错误待处理`}><Badge status="error" /></Tooltip>;
  }
  if (warningCount > 0) {
    return <Tooltip title={`${warningCount} 个警告`}><Badge status="warning" /></Tooltip>;
  }
  return <Tooltip title="全部通过"><Badge status="success" /></Tooltip>;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/control-plan/
git commit -m "feat(cp-validation): add ValidationPanel, ValidationCard, ValidationBadge components"
```

---

### Task 12: Embed ValidationPanel in ControlPlanEditorPage

**Files:**
- Modify: `frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx`

- [ ] **Step 1: Add import**

Add near the top of the file:
```tsx
import ValidationPanel from "../../../components/control-plan/ValidationPanel";
```

- [ ] **Step 2: Add panel to layout**

Find the main layout's `Row`/`Col` structure in the return statement. Adjust to add a right sidebar:

```tsx
// Find existing layout, typically:
// <Row gutter={[16, 16]}>
//   <Col span={24}> ... main content ... </Col>
// </Row>

// Change to:
<Row gutter={[16, 16]}>
  <Col span={18}> {/* reduce from span={24} */}
    {/* existing main content */}
  </Col>
  <Col span={6}>
    {cp?.cp_id && <ValidationPanel cpId={cp.cp_id} />}
  </Col>
</Row>
```

If the page doesn't use `Row`/`Col` for the outer wrapper, wrap the main content and the panel in a flex container:

```tsx
<div style={{ display: "flex", gap: 16 }}>
  <div style={{ flex: 1 }}>
    {/* existing main content */}
  </div>
  <div style={{ width: 360, flexShrink: 0 }}>
    {cp?.cp_id && <ValidationPanel cpId={cp.cp_id} />}
  </div>
</div>
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/planning/control-plan/ControlPlanEditorPage.tsx
git commit -m "feat(cp-validation): embed ValidationPanel in ControlPlanEditorPage"
```

---

### Task 13: Auto-trigger on CP Save

**Files:**
- Modify: `backend/app/services/control_plan_service.py`

- [ ] **Step 1: Add imports at top of file**

```python
import asyncio
from app.services.cp_validation.engine import CPValidationEngine
from app.database import async_session
```

- [ ] **Step 2: Add background helper function**

Add this function near the top of the file, after the import block:

```python
async def _run_validation_background(cp_id: uuid.UUID, user_id: uuid.UUID, trigger: str) -> None:
    """Run CP validation in a background task with an isolated DB session."""
    async with async_session() as db:
        try:
            engine = CPValidationEngine()
            await engine.validate(db, cp_id, user_id, trigger=trigger)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Background CP validation failed for %s", cp_id)
```

- [ ] **Step 3: Hook into update_control_plan**

Find `async def update_control_plan(...)`. After the final `await db.commit()` and just before the `return cp`, add:

```python
    # Trigger background validation after successful update
    asyncio.create_task(
        _run_validation_background(cp.cp_id, user_id, trigger="auto_on_save")
    )
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/control_plan_service.py
git commit -m "feat(cp-validation): auto-trigger validation on CP save with isolated session"
```

---

### Task 14: Add ValidationBadge to List Page

**Files:**
- Modify: `frontend/src/pages/planning/control-plan/ControlPlanListPage.tsx`

- [ ] **Step 1: Add imports**

```tsx
import { useEffect, useState } from "react";
import ValidationBadge from "../../../components/control-plan/ValidationBadge";
import { getValidationSummary } from "../../../api/cpValidation";
import type { ValidationSummary } from "../../../types/cpValidation";
```

- [ ] **Step 2: Add validation summary state**

In the list page component, add:

```tsx
const [validationMap, setValidationMap] = useState<Record<string, ValidationSummary>>({});
```

- [ ] **Step 3: Fetch summaries when control plans load**

Add a `useEffect` that fetches summaries after `data` is available:

```tsx
useEffect(() => {
  if (!data?.length) return;
  const fetchSummaries = async () => {
    const map: Record<string, ValidationSummary> = {};
    await Promise.all(
      data.map(async (cp: ControlPlan) => {
        try {
          const summary = await getValidationSummary(cp.cp_id);
          map[cp.cp_id] = summary;
        } catch {
          // ignore fetch errors for individual CPs
        }
      })
    );
    setValidationMap(map);
  };
  fetchSummaries();
}, [data]);
```

- [ ] **Step 4: Add column to Table**

Find the `columns` array in the Table component. Add:

```tsx
{
  title: "校验状态",
  key: "validation",
  width: 80,
  align: "center" as const,
  render: (_: unknown, record: ControlPlan) => {
    const summary = validationMap[record.cp_id];
    return (
      <ValidationBadge
        errorCount={summary?.error_count || 0}
        warningCount={summary?.warning_count || 0}
        total={summary?.total || 0}
      />
    );
  },
}
```

- [ ] **Step 5: Verify build**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/planning/control-plan/ControlPlanListPage.tsx
git commit -m "feat(cp-validation): add validation status badge to ControlPlanListPage"
```

---

### Final Verification

- [ ] **Step 1: Run all backend tests**

```bash
cd backend && SECRET_KEY=test python -m pytest tests/test_cp_validation_rules.py tests/test_cp_validation_engine.py tests/test_cp_validation_api.py -v
```

Expected: All tests PASS (15 + 4 + 9 = 28 total).

- [ ] **Step 2: Run frontend build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: No errors.

---

## Self-Review

### Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| `cp_validation_runs` table with CHECK constraints | Task 1 |
| `cp_validation_findings` stable identity table | Task 1 |
| `cp_validation_occurrences` per-run snapshot (present=true only) | Task 1 |
| Stable hash using business keys (not volatile UUIDs) | Task 4 |
| Finding state inherited across runs | Task 5 |
| No `present=False` — absent = no occurrence | Task 5 |
| Stale run recovery (>5 min auto-failed) | Task 5 |
| `ValidationAlreadyRunning` exception + 409 response | Tasks 5, 6 |
| `failed_rules` populated from rule engine | Tasks 4, 5 |
| Models registered in `__init__.py` | Task 1 |
| CHECK constraints in migration | Task 2 |
| API endpoints with 409 for concurrent runs | Task 6 |
| API tests using httpx + dependency_overrides pattern | Task 8 |
| Frontend components using `finding_id` | Task 11 |
| Auto-trigger with isolated session | Task 13 |

### Placeholder Scan

- No "TBD", "TODO", "implement later", "previous plan".
- All 14 tasks contain complete, runnable code.
- Test commands include expected output.
- No references to external files or prior plan versions.

### Type Consistency Check

- `ValidationFinding.stable_key` → `compute_finding_hash(rule_id, stable_key, key_content)` → `CPValidationFinding.finding_hash`.
- API `ValidationResultItem.finding_id` → frontend `ValidationResult.finding_id` → `onReject(result.finding_id)`.
- `run_all_rules` returns `(findings, failed_rules)` → engine stores `failed_rules` in run.
- `ValidationAlreadyRunning` exception → API catches and returns 409.

---

*Plan version: v3.0 — stable hashing, no present=false, stale run recovery, CHECK constraints, model registration, self-contained*
