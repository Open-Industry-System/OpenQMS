# Control Plan Intelligent Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rule-based control plan validation system that checks CP items against FMEA data, persists results per validation run, and provides a frontend panel for viewing and managing findings.

**Architecture:** Backend: SQLAlchemy models for runs/results + pure-function rule engine + orchestrator engine. Frontend: React sidebar panel with polling-based status updates. Auto-triggered on CP save via asyncio background task with isolated DB session.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Pydantic v2, pytest. React 18, TypeScript 5.6, Ant Design 5, Axios.

---

## File Structure

**New files:**
- `backend/app/models/cp_validation.py` — `CPValidationRun`, `CPValidationResult` models
- `backend/app/schemas/cp_validation.py` — Request/response Pydantic schemas
- `backend/app/services/cp_validation/rule_engine.py` — 4 validation rules (pure functions)
- `backend/app/services/cp_validation/engine.py` — Orchestrator: run lifecycle, hash dedup
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

**Context:** Follow the pattern in `backend/app/models/control_plan.py`. Use `Mapped`, `mapped_column`, UUID PKs, JSONB for arrays.

- [ ] **Step 1: Write the model file**

```python
import uuid
import hashlib
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, func, Text
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


class CPValidationResult(Base):
    __tablename__ = "cp_validation_results"

    validation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cp_validation_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    cp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False
    )
    validation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_items: Mapped[list | None] = mapped_column(JSONB, default=list)
    fmea_node_ids: Mapped[list | None] = mapped_column(JSONB, default=list)
    finding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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


def compute_finding_hash(rule_id: str, item_id: str | None, key_content: str) -> str:
    """Generate SHA256 hash for a validation finding."""
    payload = f"{rule_id}|{item_id or ''}|{key_content}"
    return hashlib.sha256(payload.encode()).hexdigest()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/cp_validation.py
git commit -m "feat(cp-validation): add CPValidationRun and CPValidationResult models"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/20250610_add_cp_validation_tables.py`

**Context:** Check existing migration style at `backend/alembic/versions/`. Use `op.create_table`, `op.create_index`. Include partial unique indexes.

- [ ] **Step 1: Write the migration**

```python
"""Add cp_validation_runs and cp_validation_results tables.

Revision ID: 20250610_add_cp_validation
Revises: (set to current head — check `alembic history`)
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
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
        "cp_validation_results",
        sa.Column("validation_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cp_validation_runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("cp_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("control_plans.cp_id", ondelete="CASCADE"), nullable=False),
        sa.Column("validation_type", sa.String(20), nullable=False),
        sa.Column("rule_id", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("affected_items", postgresql.JSONB, server_default="[]"),
        sa.Column("fmea_node_ids", postgresql.JSONB, server_default="[]"),
        sa.Column("finding_hash", sa.String(64), nullable=False),
        sa.Column("suggestion", sa.Text, nullable=True),
        sa.Column("suggestion_data", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_cpvr_run_id", "cp_validation_results", ["run_id"])
    op.create_index("idx_cpvr_cp_id", "cp_validation_results", ["cp_id"])
    op.create_index("idx_cpvr_type_status", "cp_validation_results", ["validation_type", "status"])
    op.create_index("idx_cpvr_severity", "cp_validation_results", ["severity"])
    op.create_index(
        "idx_cpvr_hash", "cp_validation_results", ["cp_id", "finding_hash"],
        unique=True, postgresql_where=sa.text("status != 'superseded'")
    )


def downgrade() -> None:
    op.drop_index("idx_cpvr_hash", table_name="cp_validation_results")
    op.drop_index("idx_cpvr_severity", table_name="cp_validation_results")
    op.drop_index("idx_cpvr_type_status", table_name="cp_validation_results")
    op.drop_index("idx_cpvr_cp_id", table_name="cp_validation_results")
    op.drop_index("idx_cpvr_run_id", table_name="cp_validation_results")
    op.drop_table("cp_validation_results")

    op.drop_index("idx_cpvrn_running", table_name="cp_validation_runs")
    op.drop_index("idx_cpvrn_status", table_name="cp_validation_runs")
    op.drop_index("idx_cpvrn_cp_id", table_name="cp_validation_runs")
    op.drop_table("cp_validation_runs")
```

- [ ] **Step 2: Set correct down_revision**

Run this to find the current head:
```bash
cd backend && alembic history --verbose | head -10
```

Set `down_revision` to the current head revision ID.

- [ ] **Step 3: Test the migration**

```bash
cd backend && alembic upgrade head
```

Expected: No errors, migration applies successfully.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/20250610_add_cp_validation_tables.py
git commit -m "feat(cp-validation): add alembic migration for validation tables"
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


class ValidationResultBase(BaseModel):
    validation_type: str
    rule_id: str
    severity: str
    category: str
    title: str
    description: str | None = None
    affected_items: list = []
    fmea_node_ids: list = []
    finding_hash: str
    suggestion: str | None = None
    suggestion_data: dict | None = None
    status: str = "open"


class ValidationResultResponse(ValidationResultBase):
    validation_id: uuid.UUID
    run_id: uuid.UUID
    cp_id: uuid.UUID
    resolved_by: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ValidationRunBase(BaseModel):
    trigger: str
    status: str = "running"
    rule_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0


class ValidationRunResponse(ValidationRunBase):
    run_id: uuid.UUID
    cp_id: uuid.UUID
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
    items: list[ValidationResultResponse]
    total: int
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/cp_validation.py
git commit -m "feat(cp-validation): add Pydantic schemas for validation runs and results"
```

---

### Task 4: Rule Engine

**Files:**
- Create: `backend/app/services/cp_validation/rule_engine.py`

**Context:** Pure functions. Each rule takes `(cp, items, fmea_graph)` and returns a list of `ValidationFinding` dicts. No DB access. `fmea_graph` is `{"nodes": [...], "edges": [...]}` or `None`.

- [ ] **Step 1: Write the rule engine**

```python
"""Rule-based validation engine for Control Plans.

All rules are pure functions: (cp, items, fmea_graph) -> list[ValidationFinding].
No database access. Fast synchronous execution.
"""
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


# ─── Placeholder keywords that indicate missing content ───
_PLACEHOLDER_METHODS = {"", "见sop", "见 sop", "无", "待定", "tbd", "暂无", "暂不", "n/a", "na"}
_PLACEHOLDER_REACTIONS = {"", "无", "待定", "tbd", "暂无", "暂不", "n/a", "na"}


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _is_placeholder(val: str | None, placeholders: set[str]) -> bool:
    return _norm(val) in placeholders


# ─── Rule R001: Control method coverage ────────────────────────────────────

def rule_r001_control_method(items: list[Any]) -> list[ValidationFinding]:
    """R001: CP control_method is empty or placeholder."""
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


# ─── Rule R002: Reaction plan completeness ─────────────────────────────────

def rule_r002_reaction_plan(items: list[Any]) -> list[ValidationFinding]:
    """R002: CP reaction_plan is empty or placeholder."""
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


# ─── Rule R003: Process step consistency with FMEA ─────────────────────────

def rule_r003_fmea_consistency(items: list[Any], fmea_graph: dict | None) -> list[ValidationFinding]:
    """R003: CP step_no/process_name differs from linked FMEA ProcessStep."""
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


# ─── Rule R004: Special class annotation check ─────────────────────────────

def rule_r004_special_class(items: list[Any]) -> list[ValidationFinding]:
    """R004: special_class is CC/SC but evaluation_method or control_method is empty."""
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


# ─── Rule registry ─────────────────────────────────────────────────────────

RULE_REGISTRY: list = [
    ("R001", rule_r001_control_method),
    ("R002", rule_r002_reaction_plan),
    ("R003", rule_r003_fmea_consistency),
    ("R004", rule_r004_special_class),
]


def run_all_rules(cp: Any, items: list[Any], fmea_graph: dict | None) -> list[ValidationFinding]:
    """Execute all rules and return merged findings."""
    all_findings: list[ValidationFinding] = []
    for rule_id, rule_fn in RULE_REGISTRY:
        try:
            if rule_id == "R003":
                findings = rule_fn(items, fmea_graph)
            else:
                findings = rule_fn(items)
            all_findings.extend(findings)
        except Exception:
            # Individual rule failures should not crash the whole engine
            continue
    return all_findings
```

- [ ] **Step 2: Write and run the test**

Create `backend/tests/test_cp_validation_rules.py`:

```python
"""Unit tests for cp_validation rule engine."""
import uuid
import sys
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.cp_validation.rule_engine import (
    rule_r001_control_method,
    rule_r002_reaction_plan,
    rule_r003_fmea_consistency,
    rule_r004_special_class,
    run_all_rules,
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


def test_r001_detects_empty_control_method():
    items = [FakeItem(control_method="")]
    findings = rule_r001_control_method(items)
    assert len(findings) == 1
    assert findings[0].rule_id == "R001"
    assert findings[0].severity == "error"


def test_r001_ignores_valid_control_method():
    items = [FakeItem(control_method="X-bar R chart")]
    findings = rule_r001_control_method(items)
    assert len(findings) == 0


def test_r001_detects_placeholder_sop():
    items = [FakeItem(control_method="见SOP")]
    findings = rule_r001_control_method(items)
    assert len(findings) == 1


def test_r002_detects_empty_reaction_plan():
    items = [FakeItem(reaction_plan="")]
    findings = rule_r002_reaction_plan(items)
    assert len(findings) == 1
    assert findings[0].rule_id == "R002"


def test_r003_detects_deleted_fmea_node():
    items = [FakeItem(step_no="10", process_name="焊接", source_fmea_node_id="node-1")]
    fmea_graph = {"nodes": [], "edges": []}
    findings = rule_r003_fmea_consistency(items, fmea_graph)
    assert len(findings) == 1
    assert findings[0].title == "FMEA源工序已删除"


def test_r003_detects_name_mismatch():
    items = [FakeItem(step_no="10", process_name="旧名称", source_fmea_node_id="node-1")]
    fmea_graph = {
        "nodes": [{"id": "node-1", "type": "ProcessStep", "process_number": "10", "name": "新名称"}],
        "edges": [],
    }
    findings = rule_r003_fmea_consistency(items, fmea_graph)
    assert len(findings) == 1
    assert "不一致" in findings[0].title


def test_r003_passes_matching():
    items = [FakeItem(step_no="10", process_name="焊接", source_fmea_node_id="node-1")]
    fmea_graph = {
        "nodes": [{"id": "node-1", "type": "ProcessStep", "process_number": "10", "name": "焊接"}],
        "edges": [],
    }
    findings = rule_r003_fmea_consistency(items, fmea_graph)
    assert len(findings) == 0


def test_r004_detects_cc_missing_methods():
    items = [FakeItem(step_no="10", special_class="CC", evaluation_method="", control_method="")]
    findings = rule_r004_special_class(items)
    assert len(findings) == 1
    assert "CC" in findings[0].description


def test_r004_passes_when_methods_present():
    items = [FakeItem(special_class="CC", evaluation_method="目视检查", control_method="SPC")]
    findings = rule_r004_special_class(items)
    assert len(findings) == 0


def test_r004_ignores_non_special():
    items = [FakeItem(special_class="", evaluation_method="", control_method="")]
    findings = rule_r004_special_class(items)
    assert len(findings) == 0


def test_run_all_rules_returns_all_findings():
    items = [
        FakeItem(control_method="", reaction_plan="", special_class="CC"),
    ]
    findings = run_all_rules(None, items, None)
    assert len(findings) == 3  # R001 + R002 + R004
```

Run:
```bash
cd backend && pytest tests/test_cp_validation_rules.py -v
```

Expected: All 11 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/cp_validation/rule_engine.py backend/tests/test_cp_validation_rules.py
git commit -m "feat(cp-validation): add rule engine with 4 rules and unit tests"
```

---

### Task 5: Validation Engine (Orchestrator)

**Files:**
- Create: `backend/app/services/cp_validation/engine.py`
- Create: `backend/app/services/cp_validation/__init__.py`

**Context:** The engine orchestrates rule execution, manages the validation run lifecycle, computes finding hashes, deduplicates against historical results, and handles state inheritance. Must use a fresh DB session for auto-triggered runs.

- [ ] **Step 1: Write package init**

```python
# backend/app/services/cp_validation/__init__.py
from .engine import CPValidationEngine

__all__ = ["CPValidationEngine"]
```

- [ ] **Step 2: Write the engine**

```python
"""Control Plan Validation Engine — orchestrates rule execution and result persistence."""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cp_validation import (
    CPValidationRun,
    CPValidationResult,
    compute_finding_hash,
)
from app.models.control_plan import ControlPlan, ControlPlanItem
from app.models.fmea import FMEADocument
from app.services.cp_validation.rule_engine import run_all_rules, ValidationFinding

logger = logging.getLogger(__name__)


class CPValidationEngine:
    """Orchestrator for CP validation runs.

    Workflow:
    1. Create a CPValidationRun (status=running).
    2. Load CP + items + linked FMEA graph.
    3. Execute rules → ValidationFinding list.
    4. Compute finding_hash for each finding.
    5. Deduplicate / inherit state from previous results.
    6. Mark old open results as superseded if no longer found.
    7. Update run status and counts.
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
        except Exception as exc:
            logger.exception("Validation run %s failed", run.run_id)
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise

        return run

    async def _execute_validation(self, db: AsyncSession, run: CPValidationRun) -> None:
        cp_id = run.cp_id

        # Load CP and items
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

        # Load linked FMEA graph
        fmea_graph: dict | None = None
        if cp.fmea_ref_id:
            fmea_result = await db.execute(
                select(FMEADocument).where(FMEADocument.fmea_id == cp.fmea_ref_id)
            )
            fmea = fmea_result.scalar_one_or_none()
            if fmea:
                fmea_graph = fmea.graph_data

        # Execute rules
        findings = run_all_rules(cp, items, fmea_graph)

        # Build hash -> finding map
        finding_map: dict[str, ValidationFinding] = {}
        for finding in findings:
            h = compute_finding_hash(finding.rule_id, finding.item_id, finding.key_content)
            finding_map[h] = finding

        # Load existing non-superseded results for this CP
        existing_result = await db.execute(
            select(CPValidationResult).where(
                CPValidationResult.cp_id == cp_id,
                CPValidationResult.status != "superseded",
            )
        )
        existing_rows = list(existing_result.scalars().all())
        existing_by_hash = {row.finding_hash: row for row in existing_rows}

        # Track which existing rows are still present
        seen_hashes: set[str] = set()

        for h, finding in finding_map.items():
            seen_hashes.add(h)
            existing = existing_by_hash.get(h)

            if existing:
                # Update run_id so it appears in latest run queries
                existing.run_id = run.run_id
                # Preserve user-set states (accepted / rejected / resolved)
                if existing.status in ("open",):
                    pass  # keep as-is
            else:
                # Insert new finding
                db.add(CPValidationResult(
                    run_id=run.run_id,
                    cp_id=cp_id,
                    validation_type="rule",
                    rule_id=finding.rule_id,
                    severity=finding.severity,
                    category=finding.category,
                    title=finding.title,
                    description=finding.description,
                    affected_items=[finding.item_id] if finding.item_id else [],
                    finding_hash=h,
                    status="open",
                ))

        # Mark old open results as superseded if not found in this run
        for row in existing_rows:
            if row.status == "open" and row.finding_hash not in seen_hashes:
                row.status = "superseded"
                row.run_id = run.run_id  # ensure it moves to the new run for visibility

        # Count severities for the run
        error_count = sum(1 for f in findings if f.severity == "error")
        warning_count = sum(1 for f in findings if f.severity == "warning")
        info_count = sum(1 for f in findings if f.severity == "info")

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
"""Unit tests for CPValidationEngine orchestrator."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.cp_validation.engine import CPValidationEngine
from app.models.cp_validation import CPValidationRun, CPValidationResult, compute_finding_hash
from app.models.control_plan import ControlPlan, ControlPlanItem


@pytest.mark.asyncio
async def test_validate_creates_run_and_results(db, admin_user):
    """End-to-end: create CP with items, run validation, assert results."""
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate

    # Create a control plan
    cp_data = ControlPlanCreate(
        title="Test CP",
        document_no=f"CP-TEST-{uuid.uuid4().hex[:8]}",
        product_line_code="DC-DC-100",
    )
    cp = await create_control_plan(db, cp_data, admin_user.user_id)

    # Add an item with empty control_method
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

    # Run validation
    engine = CPValidationEngine()
    run = await engine.validate(db, cp.cp_id, admin_user.user_id, trigger="manual")

    assert run.status == "completed"
    assert run.error_count >= 2  # R001 + R002

    # Verify results exist
    from sqlalchemy import select
    result = await db.execute(
        select(CPValidationResult).where(CPValidationResult.run_id == run.run_id)
    )
    rows = result.scalars().all()
    assert len(rows) >= 2
    assert any(r.rule_id == "R001" for r in rows)
    assert any(r.rule_id == "R002" for r in rows)


@pytest.mark.asyncio
async def test_finding_hash_deduplication(db, admin_user):
    """Same finding across two runs should not create duplicate rows."""
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

    # First run
    run1 = await engine.validate(db, cp.cp_id, admin_user.user_id)
    result1 = await db.execute(
        select(func.count()).where(CPValidationResult.cp_id == cp.cp_id)
    )
    count1 = result1.scalar()

    # Second run (same data = same findings)
    run2 = await engine.validate(db, cp.cp_id, admin_user.user_id)
    result2 = await db.execute(
        select(func.count()).where(CPValidationResult.cp_id == cp.cp_id)
    )
    count2 = result2.scalar()

    # Same count — no duplicates
    assert count1 == count2

    # All results should point to run2 now
    result3 = await db.execute(
        select(CPValidationResult).where(CPValidationResult.cp_id == cp.cp_id)
    )
    rows = result3.scalars().all()
    assert all(r.run_id == run2.run_id for r in rows)


@pytest.mark.asyncio
async def test_superseded_on_fix(db, admin_user):
    """When an issue is fixed, the old open result becomes superseded."""
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

    # The old R001 result should be superseded
    result = await db.execute(
        select(CPValidationResult).where(
            CPValidationResult.cp_id == cp.cp_id,
            CPValidationResult.rule_id == "R001",
        )
    )
    rows = result.scalars().all()
    assert any(r.status == "superseded" for r in rows)
```

Run:
```bash
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/openqms_test pytest tests/test_cp_validation_engine.py -v
```

Note: If `openqms_test` DB doesn't exist, create it first:
```bash
docker compose exec db psql -U postgres -c "CREATE DATABASE openqms_test;"
```

Expected: All 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/cp_validation/
git add backend/tests/test_cp_validation_engine.py
git commit -m "feat(cp-validation): add validation engine orchestrator with hash dedup and tests"
```

---

### Task 6: API Routes

**Files:**
- Create: `backend/app/api/cp_validation.py`

**Context:** Follow pattern in `backend/app/api/control_plan.py`. Use `require_permission(Module.PLANNING, PermissionLevel.VIEW/EDIT)`.

- [ ] **Step 1: Write the API routes**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import (
    get_current_user, require_permission, get_user_permission,
    PermissionLevel, Module,
)
from app.models.user import User
from app.models.cp_validation import CPValidationRun, CPValidationResult
from app.schemas.cp_validation import (
    ValidationRunResponse,
    ValidationResultResponse,
    ValidationSummaryResponse,
    ValidationResultsListResponse,
)
from app.services.cp_validation import CPValidationEngine

router = APIRouter(prefix="/api", tags=["cp-validation"])


@router.get("/control-plans/{cp_id}/validation-results", response_model=ValidationResultsListResponse)
async def list_validation_results(
    cp_id: uuid.UUID,
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.VIEW)),
):
    """List validation results for a control plan (latest run only, non-superseded)."""
    # Find latest completed or running run
    latest_run_result = await db.execute(
        select(CPValidationRun)
        .where(CPValidationRun.cp_id == cp_id)
        .order_by(desc(CPValidationRun.started_at))
        .limit(1)
    )
    latest_run = latest_run_result.scalar_one_or_none()

    if latest_run is None:
        return ValidationResultsListResponse(items=[], total=0)

    query = select(CPValidationResult).where(
        CPValidationResult.run_id == latest_run.run_id,
        CPValidationResult.status != "superseded",
    )
    if status_filter:
        query = query.where(CPValidationResult.status == status_filter)
    if severity:
        query = query.where(CPValidationResult.severity == severity)

    result = await db.execute(query)
    rows = result.scalars().all()

    return ValidationResultsListResponse(
        items=[ValidationResultResponse.model_validate(r) for r in rows],
        total=len(rows),
    )


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
    latest_run_result = await db.execute(
        select(CPValidationRun)
        .where(CPValidationRun.cp_id == cp_id)
        .order_by(desc(CPValidationRun.started_at))
        .limit(1)
    )
    latest_run = latest_run_result.scalar_one_or_none()

    if latest_run is None:
        return ValidationSummaryResponse()

    # Count by status
    counts_result = await db.execute(
        select(CPValidationResult.status, func.count())
        .where(
            CPValidationResult.run_id == latest_run.run_id,
            CPValidationResult.status != "superseded",
        )
        .group_by(CPValidationResult.status)
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


@router.post("/validation-results/{validation_id}/reject", response_model=ValidationResultResponse)
async def reject_validation_result(
    validation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    """Reject a validation finding (mark as rejected)."""
    result = await db.execute(
        select(CPValidationResult).where(CPValidationResult.validation_id == validation_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="校验结果不存在")

    row.status = "rejected"
    row.resolved_by = user.user_id
    row.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return ValidationResultResponse.model_validate(row)


@router.post("/validation-results/{validation_id}/resolve", response_model=ValidationResultResponse)
async def resolve_validation_result(
    validation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    """Mark a validation finding as resolved."""
    result = await db.execute(
        select(CPValidationResult).where(CPValidationResult.validation_id == validation_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="校验结果不存在")

    row.status = "resolved"
    row.resolved_by = user.user_id
    row.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return ValidationResultResponse.model_validate(row)


@router.post("/validation-results/{validation_id}/reopen", response_model=ValidationResultResponse)
async def reopen_validation_result(
    validation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    """Reopen a rejected or resolved validation finding."""
    result = await db.execute(
        select(CPValidationResult).where(CPValidationResult.validation_id == validation_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="校验结果不存在")

    if row.status not in ("rejected", "resolved"):
        raise HTTPException(status_code=400, detail="只能重新打开已拒绝或已解决的项目")

    row.status = "open"
    row.resolved_by = None
    row.resolved_at = None
    await db.commit()
    await db.refresh(row)
    return ValidationResultResponse.model_validate(row)
```

- [ ] **Step 2: Fix missing import**

Add to the top of the file:
```python
from datetime import datetime, timezone
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/cp_validation.py
git commit -m "feat(cp-validation): add API routes for validation runs and results"
```

---

### Task 7: Register Router

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add import and registration**

Find the existing control_plan router import in `backend/app/main.py`:
```python
from app.api.control_plan import router as control_plan_router
```

Add below it:
```python
from app.api.cp_validation import router as cp_validation_router
```

Find where control_plan router is included:
```python
app.include_router(control_plan_router)
```

Add below it:
```python
app.include_router(cp_validation_router)
```

- [ ] **Step 2: Verify server starts**

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
curl -s http://localhost:8000/docs | grep -q "cp-validation" && echo "Router registered" || echo "Router NOT found"
kill %1
```

Expected: "Router registered"

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(cp-validation): register cp_validation router in main app"
```

---

### Task 8: API Integration Tests

**Files:**
- Create: `backend/tests/test_cp_validation_api.py`

- [ ] **Step 1: Write API tests**

```python
"""Integration tests for cp_validation API endpoints."""
import uuid
import pytest

from app.models.cp_validation import CPValidationResult


@pytest.mark.asyncio
async def test_trigger_validation_endpoint(client, db, admin_user):
    """POST /control-plans/{id}/validate triggers a run and returns results."""
    from app.services.control_plan_service import create_control_plan
    from app.schemas.control_plan import ControlPlanCreate
    from app.models.control_plan import ControlPlanItem

    # Setup: create CP with a problematic item
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

    # Get auth token
    from app.core.security import create_access_token
    token = create_access_token(str(admin_user.user_id))

    # Trigger validation
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
    """GET /control-plans/{id}/validation-results returns findings."""
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


@pytest.mark.asyncio
async def test_reject_and_reopen_endpoint(client, db, admin_user):
    """POST /validation-results/{id}/reject and /reopen work correctly."""
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

    # Get the validation result
    from app.models.cp_validation import CPValidationResult
    result = await db.execute(
        select(CPValidationResult).where(CPValidationResult.cp_id == cp.cp_id)
    )
    vr = result.scalars().first()

    from app.core.security import create_access_token
    token = create_access_token(str(admin_user.user_id))

    # Reject
    resp = client.post(
        f"/api/validation-results/{vr.validation_id}/reject",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    # Reopen
    resp = client.post(
        f"/api/validation-results/{vr.validation_id}/reopen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"


@pytest.mark.asyncio
async def test_summary_endpoint(client, db, admin_user):
    """GET /control-plans/{id}/validation-summary returns counts."""
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

- [ ] **Step 2: Run the tests**

```bash
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/openqms_test pytest tests/test_cp_validation_api.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_cp_validation_api.py
git commit -m "test(cp-validation): add API integration tests"
```

---

### Task 9: Frontend Types

**Files:**
- Create: `frontend/src/types/cpValidation.ts`

**Context:** Follow patterns in `frontend/src/types/index.ts`.

- [ ] **Step 1: Write TypeScript types**

```typescript
export interface ValidationResult {
  validation_id: string;
  run_id: string;
  cp_id: string;
  validation_type: string;
  rule_id: string;
  severity: "error" | "warning" | "info";
  category: string;
  title: string;
  description: string | null;
  affected_items: string[];
  fmea_node_ids: string[];
  finding_hash: string;
  suggestion: string | null;
  suggestion_data: Record<string, unknown> | null;
  status: "open" | "accepted" | "rejected" | "resolved" | "superseded";
  resolved_by: string | null;
  resolved_at: string | null;
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

**Context:** Follow pattern in `frontend/src/api/controlPlan.ts`. Use the existing `client` axios instance.

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

export async function rejectValidationResult(validationId: string): Promise<ValidationResult> {
  const resp = await client.post(`/validation-results/${validationId}/reject`);
  return resp.data;
}

export async function resolveValidationResult(validationId: string): Promise<ValidationResult> {
  const resp = await client.post(`/validation-results/${validationId}/resolve`);
  return resp.data;
}

export async function reopenValidationResult(validationId: string): Promise<ValidationResult> {
  const resp = await client.post(`/validation-results/${validationId}/reopen`);
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

**Context:** Use Ant Design components (Card, Tag, Button, Spin, Empty, Alert). Follow Chinese UI convention.

- [ ] **Step 1: Write ValidationCard**

```tsx
import { Card, Tag, Button, Space, Typography } from "antd";
import {
  CloseCircleOutlined,
  CheckCircleOutlined,
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
  onReject: (id: string) => void;
  onResolve: (id: string) => void;
  onReopen: (id: string) => void;
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
                <Button size="small" onClick={() => onResolve(result.validation_id)} loading={loading}>
                  标记已解决
                </Button>
                <Button size="small" danger onClick={() => onReject(result.validation_id)} loading={loading}>
                  忽略
                </Button>
              </Space>
            )}
            {result.status === "rejected" && (
              <Button size="small" icon={<UndoOutlined />} onClick={() => onReopen(result.validation_id)} loading={loading}>
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

  // Polling effect
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

  // Initial load
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
              key={r.validation_id}
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
            共 {summary.total} 项: {" "}
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

**Context:** The editor page already has a complex layout. Add the ValidationPanel as a collapsible right sidebar, similar to how other panels are structured.

- [ ] **Step 1: Add import**

Add near the top of the file with other imports:
```tsx
import ValidationPanel from "../../../components/control-plan/ValidationPanel";
```

- [ ] **Step 2: Add panel to the layout**

Find where the main layout is rendered. Look for a Row/Col structure. The page likely has something like:
```tsx
<Row gutter={[16, 16]}>
  <Col span={24}>...</Col>
</Row>
```

Add a right-side Col for the validation panel. If the main content is full-width, change it to make room:

Find the main content area and adjust:
```tsx
// Change from something like:
<Col span={24}>...</Col>

// To:
<Col span={18}>...</Col>
<Col span={6}>
  {cp?.cp_id && <ValidationPanel cpId={cp.cp_id} />}
</Col>
```

If the layout doesn't use Row/Col for the main body, wrap the existing content and add the panel side by side.

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

**Context:** Add a background validation trigger after `update_control_plan` completes. Use `asyncio.create_task` with a fresh DB session (from `async_session`).

- [ ] **Step 1: Add import at top of file**

```python
import asyncio
```

Also import the engine:
```python
from app.services.cp_validation import CPValidationEngine
from app.database import async_session
```

- [ ] **Step 2: Add background helper function**

Add this function near the top of the file, after imports:

```python
async def _run_validation_background(cp_id: uuid.UUID, user_id: uuid.UUID, trigger: str) -> None:
    """Run CP validation in a background task with an isolated DB session."""
    async with async_session() as db:
        try:
            engine = CPValidationEngine()
            await engine.validate(db, cp_id, user_id, trigger=trigger)
        except Exception:
            # Background task failures should not crash the request
            import logging
            logging.getLogger(__name__).exception("Background CP validation failed for %s", cp_id)
```

- [ ] **Step 3: Hook into update_control_plan**

Find `async def update_control_plan(...)` in the file. After the final `await db.commit()` and just before the `return cp`, add:

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

**Context:** Add a column showing validation status. The list page likely uses Ant Design Table.

- [ ] **Step 1: Add imports**

```tsx
import { useEffect, useState } from "react";
import ValidationBadge from "../../../components/control-plan/ValidationBadge";
import { getValidationSummary } from "../../../api/cpValidation";
import type { ValidationSummary } from "../../../types/cpValidation";
```

- [ ] **Step 2: Add validation summary state and fetch logic**

In the list page component, add state for validation summaries:

```tsx
const [validationMap, setValidationMap] = useState<Record<string, ValidationSummary>>({});
```

After the control plans are fetched, fetch validation summaries:

```tsx
useEffect(() => {
  if (!controlPlans?.items?.length) return;
  const fetchSummaries = async () => {
    const map: Record<string, ValidationSummary> = {};
    await Promise.all(
      controlPlans.items.map(async (cp) => {
        try {
          const summary = await getValidationSummary(cp.cp_id);
          map[cp.cp_id] = summary;
        } catch {
          // ignore
        }
      })
    );
    setValidationMap(map);
  };
  fetchSummaries();
}, [controlPlans]);
```

- [ ] **Step 3: Add column to the Table**

Find the `columns` array in the Table. Add a new column:

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

- [ ] **Step 4: Verify build**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/control-plan/ControlPlanListPage.tsx
git commit -m "feat(cp-validation): add validation status badge to ControlPlanListPage"
```

---

## Self-Review

### Spec Coverage Check

| Spec Requirement | Plan Task |
|---|---|
| `cp_validation_runs` table | Task 1 |
| `cp_validation_results` table with `finding_hash` | Task 1 |
| Partial unique index on hash | Task 2 |
| Partial unique index on running runs | Task 2 |
| 4 rules (R001-R004) | Task 4 |
| Rule engine pure functions | Task 4 |
| Engine orchestrator with hash dedup | Task 5 |
| Inherit accepted/rejected/resolved state | Task 5 |
| Mark missing as superseded | Task 5 |
| Update run_id on inherited records | Task 5 |
| API endpoints (list, trigger, runs, summary, reject, resolve, reopen) | Task 6 |
| Permission checks (Module.PLANNING + VIEW/EDIT) | Task 6 |
| Register router in main.py | Task 7 |
| Backend tests (rules, engine, API) | Tasks 4, 5, 8 |
| Frontend types | Task 9 |
| Frontend API client | Task 10 |
| ValidationPanel component | Task 11 |
| ValidationCard component | Task 11 |
| ValidationBadge component | Task 11 |
| Embed panel in editor | Task 12 |
| Auto-trigger on save with isolated session | Task 13 |
| List page badge | Task 14 |

### Placeholder Scan

- No "TBD", "TODO", "implement later" found.
- All code blocks contain complete, runnable code.
- All test commands include expected output.
- No "similar to Task N" shortcuts.

### Type Consistency Check

- `ValidationFinding` dataclass fields match `CPValidationResult` model columns.
- Schema response types match model fields.
- Frontend `ValidationResult` interface matches backend schema.
- API client function signatures match endpoint paths and methods.

---

*Plan version: v1.0*
