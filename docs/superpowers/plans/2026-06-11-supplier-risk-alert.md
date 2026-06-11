# 供应商风险智能预警 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rule-driven risk scoring engine that continuously evaluates supplier risk, generates alerts, and provides a closed-loop disposition workflow (acknowledge/ignore/create SCAR/CAPA).

**Architecture:** Pure-function rule engine (10 rules, 3 categories) + weighted scoring with critical-bypass + alert lifecycle state machine. Follows existing `cp_validation/rule_engine` and `lessons_learned` patterns. Backend service layer coordinates rule evaluation, alert generation, and notification dispatch. Frontend provides risk dashboard and alert disposition.

**Tech Stack:** Python/FastAPI (async), SQLAlchemy 2.0 (async), PostgreSQL partial unique indexes, Pydantic v2, React/TypeScript/Ant Design, @ant-design/charts for scatter plots

---

## File Structure

### Backend (new files)
```
backend/app/
├── alembic/versions/033_add_supplier_risk_tables.py   # 3 tables + partial unique indexes + permission seed
├── models/supplier_risk.py                            # 3 ORM models
├── schemas/supplier_risk.py                           # Pydantic request/response schemas
├── services/supplier_risk/
│   ├── __init__.py                                    # Public API exports
│   ├── rule_engine.py                                 # 10 pure-function rules + SupplierRiskInput/RuleResult dataclasses
│   ├── scorer.py                                      # Weighted scoring + critical bypass
│   ├── service.py                                     # Main service: evaluate, handle_alert, create_scar/capa_from_alert
│   ├── notifier.py                                    # Email + Webhook notification dispatch
│   └── config.py                                      # Rule config CRUD with 4-layer priority resolution
└── api/supplier_risk.py                               # 14 API endpoints
```

### Backend (modified files)
```
backend/app/main.py                                    # Register router + start daily evaluation loop
backend/app/core/permissions.py                        # Add SUPPLIER_RISK to Module enum
backend/app/services/capa_service.py                   # Add _create_capa_without_commit + CAPA-close-triggers-alert-close
backend/app/services/scar_service.py                   # Add SCAR-close-triggers-alert-close
backend/app/services/iqc_inspection_service.py         # Add incremental evaluation hook on judgment
```

### Frontend (new files)
```
frontend/src/
├── api/supplierRisk.ts                                # API client functions
├── types/index.ts                                     # Extended with risk types
├── pages/supplierRisk/
│   ├── SupplierRiskPage.tsx                           # Risk dashboard + alert list
│   └── RiskConfigPage.tsx                             # Rule config + notification channels
│   └── components/
│       ├── RiskMatrixChart.tsx                        # Scatter plot
│       ├── AlertTable.tsx                             # Alert list with filters
│       ├── HandleAlertDrawer.tsx                      # Disposition drawer
│       ├── RuleConfigTable.tsx                        # Rule config editor
│       └── ChannelConfigTable.tsx                     # Notification channel CRUD
```

### Frontend (modified files)
```
frontend/src/App.tsx                                   # Add routes
frontend/src/components/layout/AppLayout.tsx           # Add sidebar menu item
```

### Tests (new files)
```
backend/tests/test_supplier_risk_rule_engine.py         # 20 rule tests + 4 scoring tests
backend/tests/test_supplier_risk_service.py             # 6 disposition + config tests
backend/tests/test_supplier_risk_integration.py         # 11 integration/boundary tests
```

---

### Task 1: Database Migration

**Files:**
- Create: `backend/alembic/versions/033_add_supplier_risk_tables.py`
- Modify: `backend/app/core/permissions.py` (add `SUPPLIER_RISK` to Module enum)

- [ ] **Step 1: Create migration file with 3 tables, partial unique indexes, and permission seed**

```python
"""add supplier risk tables

Revision ID: 033_add_supplier_risk_tables
Revises: bfd90bb593fc
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "033_add_supplier_risk_tables"
down_revision: Union[str, None] = "bfd90bb593fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RISK_PERMS = {
    "admin": 5,
    "manager": 4,
    "field_qe": 3,
    "viewer": 1,
    "customer_qe": 1,
    "supplier_qe": 3,
    "planning_qe": 1,
}

DEFAULT_CONFIGS = [
    {"rule_id": "R01", "enabled": True, "category": "quality", "weight": 15.0,
     "thresholds": {"ppm_limit": 1000, "window_days": 90}},
    {"rule_id": "R02", "enabled": True, "category": "quality", "weight": 12.0,
     "thresholds": {"acceptance_rate_min": 0.9, "decline_ratio": 0.1, "window_days": 90, "compare_window_days": 180}},
    {"rule_id": "R03", "enabled": True, "category": "quality", "weight": 18.0,
     "thresholds": {"consecutive_batches": 3, "batch_limit": 10}},
    {"rule_id": "R04", "enabled": True, "category": "quality", "weight": 10.0,
     "thresholds": {"open_days_limit": 30}},
    {"rule_id": "R05", "enabled": True, "category": "quality", "weight": 12.0,
     "thresholds": {"scar_count_limit": 3, "window_days": 90}},
    {"rule_id": "R06", "enabled": True, "category": "delivery", "weight": 12.0,
     "thresholds": {"delivery_score_min": 70, "decline_ratio": 0.15}},
    {"rule_id": "R07", "enabled": True, "category": "delivery", "weight": 10.0,
     "thresholds": {"from_grades": ["A", "B"], "to_grades": ["C", "D"]}},
    {"rule_id": "R08", "enabled": True, "category": "compliance", "weight": 8.0,
     "thresholds": {"warning_days": [90, 60, 30]}},
    {"rule_id": "R09", "enabled": True, "category": "compliance", "weight": 8.0,
     "thresholds": {"score_decline_limit": 15}},
    {"rule_id": "R10", "enabled": True, "category": "compliance", "weight": 15.0,
     "thresholds": {"keywords": ["安全", "安全特性", "safety"]}},
]


def upgrade() -> None:
    # ---- 1. supplier_risk_alerts ------------------------------------------------
    op.create_table(
        "supplier_risk_alerts",
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("risk_score", sa.Float, nullable=False),
        sa.Column("quality_score", sa.Float, nullable=False),
        sa.Column("delivery_score", sa.Float, nullable=False),
        sa.Column("compliance_score", sa.Float, nullable=False),
        sa.Column("rule_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("alert_type", sa.String(20), nullable=False, server_default="initial"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("handled_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handle_note", sa.Text, nullable=True),
        sa.Column("linked_scar_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("supplier_scars.scar_id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_capa_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("capa_eightd.report_id", ondelete="SET NULL"), nullable=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Partial unique indexes for alerts (PG14+ compatible, handles NULL product_line_code)
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_alert_unique_pl
        ON supplier_risk_alerts (supplier_id, product_line_code, snapshot_date)
        WHERE product_line_code IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_alert_unique_global
        ON supplier_risk_alerts (supplier_id, snapshot_date)
        WHERE product_line_code IS NULL;
    """)

    # ---- 2. supplier_risk_configs -----------------------------------------------
    op.create_table(
        "supplier_risk_configs",
        sa.Column("config_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("rule_id", sa.String(10), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("product_line_code", sa.String(20), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # 4 partial unique indexes for configs
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_config_global
        ON supplier_risk_configs (rule_id)
        WHERE supplier_id IS NULL AND product_line_code IS NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_config_product_line
        ON supplier_risk_configs (rule_id, product_line_code)
        WHERE supplier_id IS NULL AND product_line_code IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_config_supplier_pl
        ON supplier_risk_configs (rule_id, supplier_id, product_line_code)
        WHERE supplier_id IS NOT NULL AND product_line_code IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_risk_config_supplier_global
        ON supplier_risk_configs (rule_id, supplier_id)
        WHERE supplier_id IS NOT NULL AND product_line_code IS NULL;
    """)

    # ---- 3. supplier_risk_notification_channels ---------------------------------
    op.create_table(
        "supplier_risk_notification_channels",
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("min_risk_level", sa.String(10), nullable=False, server_default="high"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=True),
        sa.Column("product_line_code", sa.String(20), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ---- 4. Permission seed -----------------------------------------------------
    op.execute("""
        INSERT INTO role_permissions (role_id, module, permission_level)
        SELECT rd.id, 'supplier_risk', %s
        FROM role_definitions rd
        WHERE rd.role_key = %s
        ON CONFLICT DO NOTHING;
    """ % (RISK_PERMS.get("admin", 5), "'admin'"))
    # Repeat for each role...
    for role_key, level in RISK_PERMS.items():
        op.execute(f"""
            INSERT INTO role_permissions (role_id, module, permission_level)
            SELECT rd.id, 'supplier_risk', {level}
            FROM role_definitions rd
            WHERE rd.role_key = '{role_key}'
            ON CONFLICT DO NOTHING;
        """)

    # ---- 5. Default rule configs ------------------------------------------------
    for cfg in DEFAULT_CONFIGS:
        op.execute(f"""
            INSERT INTO supplier_risk_configs (rule_id, enabled, category, weight, thresholds, updated_by)
            SELECT '{cfg['rule_id']}', {cfg['enabled']}, '{cfg['category']}', {cfg['weight']},
                   '{__import__('json').dumps(cfg['thresholds'])}'::jsonb,
                   (SELECT user_id FROM users WHERE username = 'admin' LIMIT 1)
            WHERE NOT EXISTS (
                SELECT 1 FROM supplier_risk_configs
                WHERE rule_id = '{cfg['rule_id']}' AND supplier_id IS NULL AND product_line_code IS NULL
            );
        """)


def downgrade() -> None:
    op.drop_table("supplier_risk_notification_channels")
    op.drop_table("supplier_risk_configs")
    op.drop_table("supplier_risk_alerts")
    op.execute("DELETE FROM role_permissions WHERE module = 'supplier_risk'")
```

- [ ] **Step 2: Add SUPPLIER_RISK to Module enum**

In `backend/app/core/permissions.py`, add after the `ERP` line:

```python
    SUPPLIER_RISK = "supplier_risk"
```

- [ ] **Step 3: Run migration and verify**

Run: `cd backend && alembic upgrade head`
Expected: No errors. 3 tables created.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): add migration, models, permission seed"
```

---

### Task 2: ORM Models and Pydantic Schemas

**Files:**
- Create: `backend/app/models/supplier_risk.py`
- Create: `backend/app/schemas/supplier_risk.py`

- [ ] **Step 1: Create ORM models**

```python
# backend/app/models/supplier_risk.py
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Float, Date, DateTime, Text, Boolean, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SupplierRiskAlert(Base):
    __tablename__ = "supplier_risk_alerts"

    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    delivery_score: Mapped[float] = mapped_column(Float, nullable=False)
    compliance_score: Mapped[float] = mapped_column(Float, nullable=False)
    rule_results: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    alert_type: Mapped[str] = mapped_column(String(20), nullable=False, default="initial")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    handled_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    handled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    handle_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    linked_scar_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier_scars.scar_id", ondelete="SET NULL"), nullable=True)
    linked_capa_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id", ondelete="SET NULL"), nullable=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SupplierRiskConfig(Base):
    __tablename__ = "supplier_risk_configs"

    config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[str] = mapped_column(String(10), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    updated_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SupplierRiskNotificationChannel(Base):
    __tablename__ = "supplier_risk_notification_channels"

    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    min_risk_level: Mapped[str] = mapped_column(String(10), nullable=False, default="high")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=True)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 2: Create Pydantic schemas**

```python
# backend/app/schemas/supplier_risk.py
import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


# ─── Alerts ────────────────────────────────────────────────────────────────────

class AlertListParams(BaseModel):
    page: int = 1
    page_size: int = 20
    risk_level: Optional[str] = None
    status: Optional[str] = None
    supplier_id: Optional[uuid.UUID] = None
    product_line_code: Optional[str] = None


class AlertResponse(BaseModel):
    alert_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str = ""
    supplier_no: str = ""
    risk_level: str
    risk_score: float
    quality_score: float
    delivery_score: float
    compliance_score: float
    rule_results: dict
    alert_type: str
    status: str
    handled_by: Optional[uuid.UUID]
    handled_at: Optional[datetime]
    handle_note: Optional[str]
    linked_scar_id: Optional[uuid.UUID]
    linked_capa_id: Optional[uuid.UUID]
    snapshot_date: date
    product_line_code: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    total: int
    page: int
    page_size: int


class HandleAlertRequest(BaseModel):
    action: str  # acknowledge | ignore | close
    note: Optional[str] = None


# ─── Dashboard ─────────────────────────────────────────────────────────────────

class RiskDashboardResponse(BaseModel):
    high_risk_count: int
    critical_risk_count: int
    open_alert_count: int
    avg_risk_score: float
    risk_distribution: dict  # {"low": N, "medium": N, "high": N, "critical": N}
    supplier_risk_points: list[dict]  # For scatter plot


# ─── Configs ───────────────────────────────────────────────────────────────────

class RuleConfigResponse(BaseModel):
    config_id: uuid.UUID
    rule_id: str
    enabled: bool
    thresholds: dict
    weight: float
    supplier_id: Optional[uuid.UUID]
    category: str
    product_line_code: Optional[str]
    updated_by: uuid.UUID
    updated_at: datetime

    class Config:
        from_attributes = True


class RuleConfigUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    thresholds: Optional[dict] = None
    weight: Optional[float] = None


# ─── Notification Channels ─────────────────────────────────────────────────────

class ChannelCreateRequest(BaseModel):
    channel_type: str  # email | webhook
    config: dict
    min_risk_level: str = "high"
    enabled: bool = True
    supplier_id: Optional[uuid.UUID] = None
    product_line_code: Optional[str] = None


class ChannelUpdateRequest(BaseModel):
    config: Optional[dict] = None
    min_risk_level: Optional[str] = None
    enabled: Optional[bool] = None


class ChannelResponse(BaseModel):
    channel_id: uuid.UUID
    channel_type: str
    config: dict
    min_risk_level: str
    enabled: bool
    supplier_id: Optional[uuid.UUID]
    product_line_code: Optional[str]
    created_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Evaluation ────────────────────────────────────────────────────────────────

class EvaluationResponse(BaseModel):
    supplier_id: uuid.UUID
    risk_level: str
    risk_score: float
    quality_score: float
    delivery_score: float
    compliance_score: float
    rule_results: list[dict]
    alert_id: Optional[uuid.UUID] = None
```

- [ ] **Step 3: Verify imports compile**

Run: `cd backend && python -c "from app.models.supplier_risk import SupplierRiskAlert, SupplierRiskConfig, SupplierRiskNotificationChannel; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): add ORM models and Pydantic schemas"
```

---

### Task 3: Rule Engine (Pure Functions)

**Files:**
- Create: `backend/app/services/supplier_risk/__init__.py`
- Create: `backend/app/services/supplier_risk/rule_engine.py`
- Create: `backend/tests/test_supplier_risk_rule_engine.py`

- [ ] **Step 1: Write failing tests for all 10 rules**

Create `backend/tests/test_supplier_risk_rule_engine.py` with test helpers and 20 test cases (2 per rule: triggered + not triggered). Use factory fixtures that construct `SupplierRiskInput` dataclasses with minimal data.

Key test patterns:
- R01: PPM > 1000 triggers, PPM < 1000 does not
- R02: acceptance rate < 0.9 triggers, rate decline > 10% triggers, normal does not
- R03: 3 consecutive rejected inspections triggers, 2 does not
- R04: SCAR with issued_date 31 days ago + still open triggers, 29 days does not
- R05: 4 SCARs in 90 days triggers, 2 does not
- R06: delivery_score < 70 triggers, decline > 15% triggers, normal does not
- R07: grade goes from A→D triggers, A→B does not
- R08: cert expires in 20 days (score=100) triggers, 100 days does not
- R09: total_score drops 20 points triggers, 5 points does not
- R10: defect_description contains "安全" triggers, "外观不良" does not

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_supplier_risk_rule_engine.py -v`
Expected: All FAIL (module not found)

- [ ] **Step 3: Implement rule_engine.py**

Create `backend/app/services/supplier_risk/__init__.py` (empty).

Create `backend/app/services/supplier_risk/rule_engine.py` containing:

1. `SupplierRiskInput` dataclass
2. `RuleResult` dataclass (with `critical: bool = False`)
3. 10 rule functions: `rule_r01_ppm` through `rule_r10_safety_defect`
4. `RULE_REGISTRY` list mapping rule_id → (function, category, default_weight, default_critical)
5. `run_all_rules(input_data, configs)` that iterates enabled rules, catches exceptions, returns `(list[RuleResult], list[str] failed_rule_ids)`

Each rule function signature: `(data: SupplierRiskInput, thresholds: dict) -> RuleResult`

Critical rules: only R10 has `critical=True`.

R08 scoring: 60-90 days → 30, 30-60 days → 60, <30 days → 100. Take max across all certs.

R04 basis: `date.today() - scar.issued_date > open_days_limit` where scar.status != "closed".

R03 filter: only inspections where `status` in ("judged", "closed") and `inspection_result` == "rejected".

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_supplier_risk_rule_engine.py -v`
Expected: All 20 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): rule engine with 10 pure-function rules and 20 tests"
```

---

### Task 4: Scorer

**Files:**
- Create: `backend/app/services/supplier_risk/scorer.py`
- Modify: `backend/tests/test_supplier_risk_rule_engine.py` (add scorer tests)

- [ ] **Step 1: Write failing scorer tests (4 tests)**

Add to existing test file:
- All rules not triggered → score=0, level="low"
- Only quality rules triggered → moderate score, level="medium"
- Multiple categories triggered → higher score, level="high"
- All rules triggered + R10 critical bypass → score≥61 even if math says lower

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_supplier_risk_rule_engine.py -v -k scorer`
Expected: FAIL

- [ ] **Step 3: Implement scorer.py**

```python
# backend/app/services/supplier_risk/scorer.py
from dataclasses import dataclass

CATEGORY_WEIGHTS = {"quality": 0.50, "delivery": 0.30, "compliance": 0.20}
RISK_THRESHOLDS = [(30, "low"), (60, "medium"), (80, "high"), (101, "critical")]


@dataclass
class RiskScore:
    risk_score: float
    risk_level: str
    quality_score: float
    delivery_score: float
    compliance_score: float


def calculate_risk_score(results: list, configs: list) -> RiskScore:
    """Calculate weighted risk score from rule results.
    
    Denominator uses ALL active rule weights (not just triggered) to reflect risk accumulation.
    Critical bypass: if any critical rule triggered, risk_score = max(calculated, 61).
    """
    from .rule_engine import RuleResult

    category_scores = {}
    for cat, cat_weight in CATEGORY_WEIGHTS.items():
        active_weights = sum(c.weight for c in configs if c.category == cat and c.enabled)
        if active_weights == 0:
            category_scores[cat] = 0.0
            continue
        triggered = sum(r.score * _get_weight(configs, r.rule_id) for r in results if r.category == cat and r.triggered)
        category_scores[cat] = triggered / active_weights

    overall = sum(category_scores[cat] * w for cat, w in CATEGORY_WEIGHTS.items())

    # Critical bypass
    if any(r.triggered and r.critical for r in results):
        overall = max(overall, 61.0)

    level = "low"
    for threshold, label in RISK_THRESHOLDS:
        if overall < threshold:
            break
        level = label

    return RiskScore(
        risk_score=round(overall, 2),
        risk_level=level,
        quality_score=round(category_scores["quality"], 2),
        delivery_score=round(category_scores["delivery"], 2),
        compliance_score=round(category_scores["compliance"], 2),
    )


def _get_weight(configs, rule_id: str) -> float:
    for c in configs:
        if c.rule_id == rule_id:
            return c.weight
    return 1.0
```

Note: `_get_weight` is a helper that finds the weight for a rule_id from the config list. In practice the service layer will pass structured config objects.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_supplier_risk_rule_engine.py -v`
Expected: All 24 PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): risk scorer with critical bypass and 4 tests"
```

---

### Task 5: Config Service

**Files:**
- Create: `backend/app/services/supplier_risk/config.py`

- [ ] **Step 1: Implement config service with 4-layer priority resolution**

```python
# backend/app/services/supplier_risk/config.py
"""Rule configuration CRUD with 4-layer priority resolution.

Priority (highest first):
1. supplier_id + product_line_code (both NOT NULL)
2. supplier_id only (product_line_code IS NULL)
3. product_line_code only (supplier_id IS NULL)
4. Global default (both NULL)
"""
import uuid
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplier_risk import SupplierRiskConfig


async def get_effective_configs(
    db: AsyncSession,
    product_line_code: str | None = None,
    supplier_id: uuid.UUID | None = None,
) -> list[SupplierRiskConfig]:
    """Get effective configs for a supplier+product_line, resolving priority layers."""
    results = []
    for rule_id in [f"R{i:02d}" for i in range(1, 11)]:
        config = await _resolve_config(db, rule_id, product_line_code, supplier_id)
        if config:
            results.append(config)
    return results


async def _resolve_config(
    db: AsyncSession,
    rule_id: str,
    product_line_code: str | None,
    supplier_id: uuid.UUID | None,
) -> SupplierRiskConfig | None:
    """Resolve a single rule's config through the priority chain."""
    # Layer 1: supplier + product_line
    if supplier_id and product_line_code:
        result = await db.execute(
            select(SupplierRiskConfig).where(and_(
                SupplierRiskConfig.rule_id == rule_id,
                SupplierRiskConfig.supplier_id == supplier_id,
                SupplierRiskConfig.product_line_code == product_line_code,
            ))
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            return cfg

    # Layer 2: supplier global override
    if supplier_id:
        result = await db.execute(
            select(SupplierRiskConfig).where(and_(
                SupplierRiskConfig.rule_id == rule_id,
                SupplierRiskConfig.supplier_id == supplier_id,
                SupplierRiskConfig.product_line_code.is_(None),
            ))
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            return cfg

    # Layer 3: product_line default
    if product_line_code:
        result = await db.execute(
            select(SupplierRiskConfig).where(and_(
                SupplierRiskConfig.rule_id == rule_id,
                SupplierRiskConfig.supplier_id.is_(None),
                SupplierRiskConfig.product_line_code == product_line_code,
            ))
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            return cfg

    # Layer 4: global default
    result = await db.execute(
        select(SupplierRiskConfig).where(and_(
            SupplierRiskConfig.rule_id == rule_id,
            SupplierRiskConfig.supplier_id.is_(None),
            SupplierRiskConfig.product_line_code.is_(None),
        ))
    )
    return result.scalar_one_or_none()


async def list_configs(
    db: AsyncSession,
    product_line_code: str | None = None,
    supplier_id: uuid.UUID | None = None,
) -> list[SupplierRiskConfig]:
    """List all configs (raw, for admin UI)."""
    query = select(SupplierRiskConfig)
    if product_line_code:
        query = query.where(SupplierRiskConfig.product_line_code == product_line_code)
    if supplier_id:
        query = query.where(SupplierRiskConfig.supplier_id == supplier_id)
    query = query.order_by(SupplierRiskConfig.rule_id)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_config(
    db: AsyncSession,
    config_id: uuid.UUID,
    updates: dict,
    user_id: uuid.UUID,
) -> SupplierRiskConfig:
    """Update a rule config."""
    config = await db.get(SupplierRiskConfig, config_id)
    if not config:
        raise ValueError("配置不存在")
    for key, value in updates.items():
        if value is not None and hasattr(config, key):
            setattr(config, key, value)
    config.updated_by = user_id
    await db.commit()
    await db.refresh(config)
    return config
```

- [ ] **Step 2: Verify imports compile**

Run: `cd backend && python -c "from app.services.supplier_risk.config import get_effective_configs; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): config service with 4-layer priority resolution"
```

---

### Task 6: Main Service + CAPA No-Commit Helper

**Files:**
- Create: `backend/app/services/supplier_risk/service.py`
- Create: `backend/app/services/supplier_risk/notifier.py`
- Modify: `backend/app/services/capa_service.py` (add `_create_capa_without_commit`)
- Modify: `backend/app/services/scar_service.py` (add alert-close on SCAR close)
- Modify: `backend/app/services/iqc_inspection_service.py` (add incremental evaluation hook)

- [ ] **Step 1: Add `_create_capa_without_commit` to capa_service.py**

At the end of `backend/app/services/capa_service.py`, add a function that mirrors `create_capa` but uses `db.flush()` instead of `db.commit()`, and defers `enqueue_embedding` to the caller:

```python
async def _create_capa_without_commit(
    db: AsyncSession,
    title: str,
    document_no: str,
    severity: str,
    due_date,
    user_id: uuid.UUID,
    product_line_code: str = "DC-DC-100",
) -> CAPAEightD:
    """Create CAPA without committing — caller must commit and enqueue embedding."""
    await validate_product_line(db, product_line_code)
    existing_result = await db.execute(
        select(CAPAEightD).where(CAPAEightD.document_no == document_no)
    )
    if existing_result.scalar_one_or_none():
        raise ValueError(f"CAPA report number '{document_no}' already exists.")

    report_id = uuid.uuid4()
    capa = CAPAEightD(
        report_id=report_id,
        title=title,
        document_no=document_no,
        severity=severity,
        due_date=due_date,
        product_line_code=product_line_code,
        created_by=user_id,
    )
    db.add(capa)

    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=report_id,
        action="CREATE",
        changed_fields={
            "title": title, "document_no": document_no,
            "severity": severity, "due_date": str(due_date) if due_date else None,
            "product_line_code": product_line_code, "status": capa.status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.flush()
    await db.refresh(capa)
    return capa
```

- [ ] **Step 2: Implement main service**

Create `backend/app/services/supplier_risk/service.py` with:

1. `evaluate_supplier_risk(db, supplier_id, product_line_code)` — gather data, run rules, score, upsert alert
2. `evaluate_all_suppliers(db, product_line_code)` — batch aggregate query, iterate suppliers
3. `handle_alert(db, alert_id, action, note, user_id)` — state transitions (open→acknowledged/ignored, acknowledged→action_taken/closed)
4. `create_scar_from_alert(db, alert_id, user_id)` — call `_create_scar_without_commit`, link, commit
5. `create_capa_from_alert(db, alert_id, user_id)` — call `_create_capa_without_commit`, link, commit
6. `get_risk_dashboard(db, product_line_code)` — aggregate queries for dashboard

Data gathering for `evaluate_supplier_risk`:
- `IqcInspection` filtered by `supplier_id` + `product_line_code` (if not NULL)
- `SupplierSCAR` filtered by `supplier_id` + `product_line_code`
- `SupplierEvaluation` filtered by `supplier_id` (global)
- `SupplierCertification` filtered by `supplier_id` (global)

Alert upsert logic:
- Try to find existing alert for `(supplier_id, product_line_code, snapshot_date=today)`
- If exists and new risk_level > existing: update scores, set `alert_type="escalated"`
- If exists and new risk_level <= existing: skip (no downgrade auto-close)
- If not exists and risk_level != "low": insert new alert

- [ ] **Step 3: Implement notifier.py**

Create `backend/app/services/supplier_risk/notifier.py` with `send_notifications(db, alert, product_line_code)` that:

1. Queries enabled notification channels matching the alert's risk_level threshold
2. For email channels: sends via aiosmtplib (SMTP config from env vars, non-blocking, failures logged only)
3. For webhook channels: decrypts `config.secret_encrypted` via Fernet (`RISK_ENCRYPTION_KEY`), computes HMAC-SHA256 signature, POSTs JSON payload with 5s timeout, 1 retry. Validates URL is not private (SSRF check).
4. All notification errors are caught and logged, never blocking the alert creation flow

- [ ] **Step 4: Add SCAR close → alert close trigger**

In `backend/app/services/scar_service.py`, in the SCAR status transition where status becomes "closed", add:

```python
# Close linked risk alerts
from app.models.supplier_risk import SupplierRiskAlert
from sqlalchemy import select, and_

linked_alerts = await db.execute(
    select(SupplierRiskAlert).where(and_(
        SupplierRiskAlert.linked_scar_id == scar.scar_id,
        SupplierRiskAlert.status != "closed",
    ))
)
for alert in linked_alerts.scalars().all():
    alert.status = "closed"
    alert.handled_by = scar.issued_by
    alert.handled_at = datetime.now(timezone.utc)
```

- [ ] **Step 5: Add incremental evaluation hook on IQC judgment**

In `backend/app/services/iqc_inspection_service.py`, after judgment completes (where `inspection_result` is set), add:

```python
# Trigger incremental risk evaluation
import asyncio
from app.database import async_session

async def _trigger_risk_eval(supplier_id, product_line_code):
    async with async_session() as db:
        from app.services.supplier_risk.service import evaluate_supplier_risk
        await evaluate_supplier_risk(db, supplier_id, product_line_code)

asyncio.create_task(_trigger_risk_eval(inspection.supplier_id, inspection.product_line_code))
```

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): main service, notifier, CAPA no-commit helper, SCAR/IQC hooks"
```

---

### Task 7: API Routes

**Files:**
- Create: `backend/app/api/supplier_risk.py`
- Modify: `backend/app/main.py` (register router + start daily loop)

- [ ] **Step 1: Create API routes file**

Create `backend/app/api/supplier_risk.py` with 14 endpoints following existing route patterns (thin API layer: parse request, call service, return response). Use `require_permission(Module.SUPPLIER_RISK, ...)` for authorization.

Key endpoints:
- `GET /supplier-risk/alerts` — paginated list with filters
- `GET /supplier-risk/alerts/{alert_id}` — detail
- `POST /supplier-risk/alerts/{alert_id}/handle` — acknowledge/ignore/close
- `POST /supplier-risk/alerts/{alert_id}/scar` — create SCAR from alert
- `POST /supplier-risk/alerts/{alert_id}/capa` — create CAPA from alert
- `POST /supplier-risk/evaluate/{supplier_id}` — manual single evaluation
- `POST /supplier-risk/evaluate` — manual full evaluation
- `GET /supplier-risk/dashboard` — dashboard data
- `GET /supplier-risk/configs` — config list
- `PUT /supplier-risk/configs/{config_id}` — update config
- `GET /supplier-risk/channels` — channel list
- `POST /supplier-risk/channels` — create channel
- `PUT /supplier-risk/channels/{channel_id}` — update channel
- `DELETE /supplier-risk/channels/{channel_id}` — delete channel

- [ ] **Step 2: Register router and start daily loop in main.py**

In `backend/app/main.py`:

1. Add import: `from app.api.supplier_risk import router as supplier_risk_router`
2. Add `app.include_router(supplier_risk_router)` after erp_router
3. Add daily evaluation loop in lifespan (after existing MES/PLM/ERP loops):

```python
# Start supplier risk daily evaluation loop
from app.services.supplier_risk.service import evaluate_all_suppliers

async def _risk_eval_loop():
    while True:
        await asyncio.sleep(86400)
        try:
            async with async_session() as db:
                await evaluate_all_suppliers(db, product_line_code=None)
        except Exception as e:
            logger.error("[risk_eval] error: %s", e)

risk_eval_task = asyncio.create_task(_risk_eval_loop())
```

4. Add `risk_eval_task.cancel()` in the shutdown section.

- [ ] **Step 3: Verify app starts**

Run: `cd backend && timeout 5 python -c "from app.main import app; print('OK')" 2>/dev/null || echo "Timeout expected — app started"`
Expected: No import errors

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): API routes, router registration, daily eval loop"
```

---

### Task 8: Backend Tests — Service and Integration

**Files:**
- Create: `backend/tests/test_supplier_risk_service.py`
- Create: `backend/tests/test_supplier_risk_integration.py`

- [ ] **Step 1: Write service tests (6 tests)**

`test_supplier_risk_service.py`:
- Test acknowledge alert (open → acknowledged)
- Test ignore alert (open → ignored, requires note)
- Test close alert (acknowledged → closed, manager only)
- Test create SCAR from alert (calls `_create_scar_without_commit`, links, commits atomically)
- Test create CAPA from alert (calls `_create_capa_without_commit`, links, commits atomically)
- Test config priority resolution (supplier+PL > supplier global > PL default > global)

Use pytest with async fixtures, in-memory test DB or mock session.

- [ ] **Step 2: Write integration tests (11 tests)**

`test_supplier_risk_integration.py`:
- Migration constraint: partial unique indexes block duplicate configs
- Permission: viewer gets 403 on EDIT/APPROVE endpoints
- Product line isolation: alerts/configs for PL-A don't leak to PL-B
- Dedup concurrency: same day same supplier same PL → only one alert
- Escalation: risk upgrade changes alert_type to "escalated"
- Notification failure: email send fails → alert still created
- SCAR no-commit helper: `_create_scar_without_commit` flushes but doesn't commit
- CAPA no-commit helper: `_create_capa_without_commit` flushes but doesn't commit
- Transaction rollback: SCAR creation fails → alert unchanged
- CAPA close linkage: CAPA status → D8_CLOSURE → linked alert auto-closed
- Webhook SSRF: private IP URL rejected

- [ ] **Step 3: Run all tests**

Run: `cd backend && python -m pytest tests/test_supplier_risk_* -v`
Expected: All 39 tests PASS

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "test(supplier-risk): 6 service tests + 11 integration tests"
```

---

### Task 9: Frontend — Types, API Client, and Routes

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/supplierRisk.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Add TypeScript types**

Append to `frontend/src/types/index.ts`:

```typescript
// Supplier Risk Alert
export interface SupplierRiskAlert {
  alert_id: string;
  supplier_id: string;
  supplier_name: string;
  supplier_no: string;
  risk_level: "low" | "medium" | "high" | "critical";
  risk_score: number;
  quality_score: number;
  delivery_score: number;
  compliance_score: number;
  rule_results: Record<string, RuleResultDetail>;
  alert_type: "initial" | "escalated" | "routine";
  status: "open" | "acknowledged" | "action_taken" | "ignored" | "closed";
  handled_by: string | null;
  handled_at: string | null;
  handle_note: string | null;
  linked_scar_id: string | null;
  linked_capa_id: string | null;
  snapshot_date: string;
  product_line_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface RuleResultDetail {
  rule_id: string;
  triggered: boolean;
  score: number;
  detail: string;
  category: string;
  critical: boolean;
}

export interface RiskDashboard {
  high_risk_count: number;
  critical_risk_count: number;
  open_alert_count: number;
  avg_risk_score: number;
  risk_distribution: Record<string, number>;
  supplier_risk_points: Array<{
    supplier_id: string;
    supplier_name: string;
    quality_score: number;
    delivery_score: number;
    compliance_score: number;
    risk_level: string;
    risk_score: number;
  }>;
}

export interface SupplierRiskConfig {
  config_id: string;
  rule_id: string;
  enabled: boolean;
  thresholds: Record<string, unknown>;
  weight: number;
  supplier_id: string | null;
  category: string;
  product_line_code: string | null;
  updated_by: string;
  updated_at: string;
}

export interface NotificationChannel {
  channel_id: string;
  channel_type: "email" | "webhook";
  config: Record<string, unknown>;
  min_risk_level: string;
  enabled: boolean;
  supplier_id: string | null;
  product_line_code: string | null;
  created_by: string;
  created_at: string;
}
```

- [ ] **Step 2: Create API client**

Create `frontend/src/api/supplierRisk.ts` following existing pattern (e.g., `supplier.ts`):

```typescript
import client from "./client";

export const riskAlertApi = {
  list: (params: Record<string, unknown>) => client.get("/supplier-risk/alerts", { params }),
  get: (id: string) => client.get(`/supplier-risk/alerts/${id}`),
  handle: (id: string, data: { action: string; note?: string }) => client.post(`/supplier-risk/alerts/${id}/handle`, data),
  createScar: (id: string) => client.post(`/supplier-risk/alerts/${id}/scar`),
  createCapa: (id: string) => client.post(`/supplier-risk/alerts/${id}/capa`),
  evaluateSupplier: (supplierId: string) => client.post(`/supplier-risk/evaluate/${supplierId}`),
  evaluateAll: () => client.post("/supplier-risk/evaluate"),
  dashboard: (params?: Record<string, unknown>) => client.get("/supplier-risk/dashboard", { params }),
  listConfigs: () => client.get("/supplier-risk/configs"),
  updateConfig: (id: string, data: Record<string, unknown>) => client.put(`/supplier-risk/configs/${id}`, data),
  listChannels: () => client.get("/supplier-risk/channels"),
  createChannel: (data: Record<string, unknown>) => client.post("/supplier-risk/channels", data),
  updateChannel: (id: string, data: Record<string, unknown>) => client.put(`/supplier-risk/channels/${id}`, data),
  deleteChannel: (id: string) => client.delete(`/supplier-risk/channels/${id}`),
};
```

- [ ] **Step 3: Add routes to App.tsx**

Add route entries for `/supplier-risk` and `/supplier-risk/config` using `requiredModule="supplier_risk"`.

- [ ] **Step 4: Add sidebar menu item to AppLayout.tsx**

In the `grp:supplier` menu group, add after "供货质量看板":

```tsx
{ key: "/supplier-risk", icon: <WarningOutlined />, label: "供应商风险预警" },
```

- [ ] **Step 5: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: No TypeScript errors

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): frontend types, API client, routes, sidebar"
```

---

### Task 10: Frontend — Risk Dashboard Page

**Files:**
- Create: `frontend/src/pages/supplierRisk/SupplierRiskPage.tsx`
- Create: `frontend/src/pages/supplierRisk/components/RiskMatrixChart.tsx`
- Create: `frontend/src/pages/supplierRisk/components/AlertTable.tsx`
- Create: `frontend/src/pages/supplierRisk/components/HandleAlertDrawer.tsx`

- [ ] **Step 1: Create RiskMatrixChart component**

Scatter plot using `@ant-design/charts` (already a project dependency): X=quality_score, Y=delivery_score, bubble size=compliance_score, color=risk_level. Four color zones: green/yellow/orange/red.

- [ ] **Step 2: Create AlertTable component**

Ant Design Table with columns: supplier_no, supplier_name, risk_level (colored tag), risk_score, alert_type, status, snapshot_date, actions. Filters: risk_level, status. Sort by risk_score desc.

- [ ] **Step 3: Create HandleAlertDrawer component**

Ant Drawer with:
- Action buttons: 确认 (acknowledge), 忽略 (ignore, requires note input), 关闭 (close)
- "创建 SCAR" button → calls createScar API
- "创建 CAPA" button → calls createCapa API
- Note textarea for handle_note

- [ ] **Step 4: Create SupplierRiskPage**

Layout:
- Top row: 4 KPI cards (高风险, 极高风险, 开放预警, 平均风险分)
- Middle: RiskMatrixChart
- Bottom: AlertTable with HandleAlertDrawer on row click

- [ ] **Step 5: Verify page renders**

Run: `cd frontend && npm run build`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): risk dashboard page with matrix chart, alert table, handle drawer"
```

---

### Task 11: Frontend — Config Page

**Files:**
- Create: `frontend/src/pages/supplierRisk/RiskConfigPage.tsx`
- Create: `frontend/src/pages/supplierRisk/components/RuleConfigTable.tsx`
- Create: `frontend/src/pages/supplierRisk/components/ChannelConfigTable.tsx`

- [ ] **Step 1: Create RuleConfigTable component**

Ant Table with columns: rule_id, category (tag), enabled (switch), thresholds (JSON editor modal), weight (input number). Each row editable inline. Save button per row.

- [ ] **Step 2: Create ChannelConfigTable component**

Ant Table with columns: channel_type, config summary, min_risk_level, enabled. Add button opens modal for creating email or webhook channel. Edit/delete actions.

For webhook: URL input + secret input (masked on display). SSRF validation message.

- [ ] **Step 3: Create RiskConfigPage**

Two tabs: "规则配置" (RuleConfigTable) and "通知渠道" (ChannelConfigTable). Product line selector at top.

- [ ] **Step 4: Verify page renders**

Run: `cd frontend && npm run build`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): config page with rule config and notification channel tables"
```

---

### Task 12: End-to-End Verification

**Files:** None (verification only)

- [ ] **Step 1: Start backend and verify API**

Run: `cd backend && uvicorn app.main:app --reload`
Then verify endpoints respond:
- `GET /api/supplier-risk/dashboard` → 200
- `GET /supplier-risk/alerts` → 200 with empty list
- `GET /supplier-risk/configs` → 200 with 10 default configs
- `POST /supplier-risk/evaluate` → 200 (triggers full evaluation)

- [ ] **Step 2: Start frontend and verify pages**

Run: `cd frontend && npm run dev`
Navigate to:
- `/supplier-risk` → Risk dashboard renders with KPI cards, empty chart, empty table
- `/supplier-risk/config` → Config page renders with 10 rules, empty channels

- [ ] **Step 3: Run full test suite**

Run: `cd backend && python -m pytest tests/test_supplier_risk_* -v`
Expected: All 39 tests PASS

- [ ] **Step 4: Commit final state**

```bash
git add -A && git commit -m "feat(supplier-risk): supplier risk intelligent alert module complete"
```
