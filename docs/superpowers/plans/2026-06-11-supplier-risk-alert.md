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
├── alembic/versions/034_add_supplier_risk_tables.py   # 3 tables + partial unique indexes + permission seed
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

Revision ID: 034_add_supplier_risk_tables
Revises: 033_add_iqc_aql_optimization
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "034_add_supplier_risk_tables"
down_revision: Union[str, None] = "033_add_iqc_aql_optimization"
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
    # Single loop for all roles (no redundant separate admin insert)
    # Role keys match project's actual role_definitions: admin, manager, field_qe, supplier_qe, etc.
    for role_key, level in RISK_PERMS.items():
        op.execute(f"""
            INSERT INTO role_permissions (role_id, module, permission_level)
            SELECT rd.id, 'supplier_risk', {level}
            FROM role_definitions rd
            WHERE rd.role_key = '{role_key}'
            ON CONFLICT DO NOTHING;
        """)

    # ---- 5. Default rule configs are NOT seeded in migration ----
    # Default configs require a valid updated_by user_id. The users table may be
    # empty during fresh migration (admin user is created at app startup, not migration).
    # Therefore, default configs are seeded by the application seed command
    # (python -m app.seed) which runs after users exist. See Task 1 Step 3.


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

- [ ] **Step 4: Add default config seed to application seed**

In `backend/app/seed.py`, add a function that seeds default rule configs (using the `DEFAULT_CONFIGS` list). This runs after admin user exists, so `updated_by` is always valid. Call it from the main seed entry point.

```python
async def seed_supplier_risk_configs(db: AsyncSession):
    """Seed default supplier risk rule configs if not present."""
    from app.models.supplier_risk import SupplierRiskConfig
    from app.models.user import User
    from sqlalchemy import select

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one_or_none()
    if not admin:
        return

    DEFAULT_CONFIGS = [
        {"rule_id": "R01", "enabled": True, "category": "quality", "weight": 15.0,
         "thresholds": {"ppm_limit": 1000, "window_days": 90}},
        # ... (same list as in migration file)
        {"rule_id": "R10", "enabled": True, "category": "compliance", "weight": 15.0,
         "thresholds": {"keywords": ["安全", "安全特性", "safety"]}},
    ]

    for cfg in DEFAULT_CONFIGS:
        existing = (await db.execute(
            select(SupplierRiskConfig).where(
                SupplierRiskConfig.rule_id == cfg["rule_id"],
                SupplierRiskConfig.supplier_id.is_(None),
                SupplierRiskConfig.product_line_code.is_(None),
            )
        )).scalar_one_or_none()
        if not existing:
            db.add(SupplierRiskConfig(
                rule_id=cfg["rule_id"],
                enabled=cfg["enabled"],
                category=cfg["category"],
                weight=cfg["weight"],
                thresholds=cfg["thresholds"],
                updated_by=admin.user_id,
            ))
    await db.commit()
```

- [ ] **Step 5: Commit**

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

from pydantic import BaseModel, ConfigDict


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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

### Task 6: Main Service — Evaluate (TDD)

**Files:**
- Create: `backend/app/services/supplier_risk/service.py` (initial: `evaluate_supplier_risk` only)

- [ ] **Step 1: Write failing test for evaluate_supplier_risk**

```python
# tests/test_supplier_risk_service.py
import pytest
from datetime import date
from app.services.supplier_risk.service import evaluate_supplier_risk

@pytest.mark.asyncio
async def test_evaluate_high_ppm_supplier(db_session, seed_supplier):
    """Supplier with PPM > 1000 should produce high-risk alert."""
    # seed_supplier creates a supplier + IQC inspections with high defect rate
    result = await evaluate_supplier_risk(db_session, seed_supplier.supplier_id, product_line_code=None)
    assert result.risk_level in ("high", "critical")
    assert result.risk_score > 60
    # Verify alert was created in DB
    from app.models.supplier_risk import SupplierRiskAlert
    from sqlalchemy import select
    alert = (await db_session.execute(
        select(SupplierRiskAlert).where(SupplierRiskAlert.supplier_id == seed_supplier.supplier_id)
    )).scalar_one_or_none()
    assert alert is not None
    assert alert.risk_level in ("high", "critical")
```

Run: `cd backend && python -m pytest tests/test_supplier_risk_service.py::test_evaluate_high_ppm_supplier -v`
Expected: FAIL (ImportError: cannot import name 'evaluate_supplier_risk')

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement evaluate_supplier_risk**

Gather data (IQC filtered by supplier_id + product_line_code; SCAR filtered by supplier_id + product_line_code; Evaluation/Certification filtered by supplier_id only), run rules, score, upsert alert.

Alert upsert logic:
- Find existing alert for `(supplier_id, product_line_code, snapshot_date=today)`
- If exists and new risk_level > existing: update scores, set `alert_type="escalated"`
- If exists and new risk_level <= existing: skip
- If not exists and risk_level != "low": insert new alert

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Write failing test for evaluate_all_suppliers (batch, no N+1)**

```python
@pytest.mark.asyncio
async def test_evaluate_all_suppliers_batch(db_session, seed_three_suppliers):
    """evaluate_all should use batch query, not per-supplier N+1."""
    results = await evaluate_all_suppliers(db_session, product_line_code=None)
    assert len(results) == 3
    # All results have valid risk_level
    for r in results:
        assert r.risk_level in ("low", "medium", "high", "critical")
```

Run: `cd backend && python -m pytest tests/test_supplier_risk_service.py::test_evaluate_all_suppliers_batch -v`
Expected: FAIL

- [ ] **Step 6: Implement evaluate_all_suppliers with batch aggregate query**

One SQL query per data type (IQC, SCAR, Evaluation, Certification) grouped by supplier_id, then iterate.

- [ ] **Step 7: Run test to verify it passes**

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): evaluate_supplier_risk and evaluate_all_suppliers with batch query"
```

---

### Task 7: Main Service — Handle Alert (TDD)

**Files:**
- Modify: `backend/app/services/supplier_risk/service.py` (add `handle_alert`)

- [ ] **Step 1: Write failing test for handle_alert**

```python
@pytest.mark.asyncio
async def test_handle_alert_acknowledge(db_session, seed_open_alert):
    """Acknowledging an open alert should change status to acknowledged."""
    from app.services.supplier_risk.service import handle_alert
    alert = await handle_alert(db_session, seed_open_alert.alert_id, "acknowledge", None, seed_open_alert.supplier_id)
    assert alert.status == "acknowledged"

@pytest.mark.asyncio
async def test_handle_alert_ignore_requires_note(db_session, seed_open_alert):
    """Ignoring without a note should raise ValueError."""
    from app.services.supplier_risk.service import handle_alert
    with pytest.raises(ValueError, match="理由"):
        await handle_alert(db_session, seed_open_alert.alert_id, "ignore", None, seed_open_alert.supplier_id)
```

Run: `cd backend && python -m pytest tests/test_supplier_risk_service.py::test_handle_alert_acknowledge tests/test_supplier_risk_service.py::test_handle_alert_ignore_requires_note -v`
Expected: FAIL

- [ ] **Step 2: Implement handle_alert**

State transitions: open→acknowledged, open→ignored (requires note), acknowledged→closed (manager only).

- [ ] **Step 3: Run tests to verify they pass**

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): handle_alert with state machine"
```

---

### Task 8: Main Service — Create SCAR/CAPA from Alert (TDD)

**Files:**
- Modify: `backend/app/services/supplier_risk/service.py` (add `create_scar_from_alert`, `create_capa_from_alert`)
- Modify: `backend/app/services/capa_service.py` (add `_create_capa_without_commit`)

- [ ] **Step 1: Write failing test for create_scar_from_alert**

```python
@pytest.mark.asyncio
async def test_create_scar_from_alert_atomic(db_session, seed_open_alert, seed_user):
    """Creating SCAR from alert should link them and set status=action_taken."""
    from app.services.supplier_risk.service import create_scar_from_alert
    scar = await create_scar_from_alert(db_session, seed_open_alert.alert_id, seed_user.user_id)
    assert scar is not None
    assert scar.supplier_id == seed_open_alert.supplier_id
    # Alert should be updated
    await db_session.refresh(seed_open_alert)
    assert seed_open_alert.status == "action_taken"
    assert seed_open_alert.linked_scar_id == scar.scar_id
```

Run: `cd backend && python -m pytest tests/test_supplier_risk_service.py::test_create_scar_from_alert_atomic -v`
Expected: FAIL

- [ ] **Step 2: Add `_create_capa_without_commit` to capa_service.py**

Mirror of existing `create_capa` but uses `db.flush()` instead of `db.commit()`, defers `enqueue_embedding` to caller.

- [ ] **Step 3: Implement create_scar_from_alert and create_capa_from_alert**

Both use the same pattern: `begin → _create_without_commit → update alert → commit → enqueue_embedding`.

- [ ] **Step 4: Write failing test for transaction rollback**

```python
@pytest.mark.asyncio
async def test_create_scar_rollback_on_failure(db_session, seed_open_alert, seed_user, monkeypatch):
    """If SCAR creation fails, alert status should remain unchanged."""
    from app.services.supplier_risk import service as risk_service
    from app.services import scar_service
    original = scar_service._create_scar_without_commit
    async def failing_create(*args, **kwargs):
        raise ValueError("模拟SCAR创建失败")
    monkeypatch.setattr(scar_service, "_create_scar_without_commit", failing_create)
    with pytest.raises(ValueError, match="模拟"):
        await risk_service.create_scar_from_alert(db_session, seed_open_alert.alert_id, seed_user.user_id)
    # Alert unchanged
    await db_session.refresh(seed_open_alert)
    assert seed_open_alert.status == "open"
    assert seed_open_alert.linked_scar_id is None
```

Run: `cd backend && python -m pytest tests/test_supplier_risk_service.py::test_create_scar_rollback_on_failure -v`
Expected: FAIL

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): create_scar/capa_from_alert with atomic transaction"
```

---

### Task 9: Notifier Service

**Files:**
- Create: `backend/app/services/supplier_risk/notifier.py`

- [ ] **Step 1: Write failing test for send_notifications**

```python
@pytest.mark.asyncio
async def test_notification_email_sent(db_session, seed_high_alert, seed_email_channel, mock_smtp):
    """Email channel should trigger send via aiosmtplib."""
    from app.services.supplier_risk.notifier import send_notifications
    await send_notifications(db_session, seed_high_alert, product_line_code=None)
    assert mock_smtp.call_count == 1

@pytest.mark.asyncio
async def test_notification_webhook_ssrf_blocked(db_session, seed_high_alert, seed_webhook_channel_private_ip):
    """Webhook to private IP should be rejected."""
    from app.services.supplier_risk.notifier import send_notifications, SSRFError
    with pytest.raises(SSRFError):
        await send_notifications(db_session, seed_high_alert, product_line_code=None)

@pytest.mark.asyncio
async def test_notification_failure_non_blocking(db_session, seed_high_alert, seed_broken_channel):
    """Notification failure should not prevent alert creation."""
    from app.services.supplier_risk.notifier import send_notifications
    # Should not raise — errors are caught and logged
    await send_notifications(db_session, seed_high_alert, product_line_code=None)
```

Run: `cd backend && python -m pytest tests/test_supplier_risk_service.py::test_notification_email_sent -v`
Expected: FAIL

- [ ] **Step 2: Implement notifier.py**

1. Query enabled channels matching alert's risk_level
2. Email: aiosmtplib async send, SMTP from env vars, failures logged only
3. Webhook: decrypt `config.secret_encrypted` via Fernet (`RISK_ENCRYPTION_KEY`), HMAC-SHA256 signature, POST JSON with 5s timeout + 1 retry. SSRF: reject private IPs.
4. All errors caught and logged, never blocking

- [ ] **Step 3: Run tests to verify they pass**

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): notifier with email, webhook, SSRF protection"
```

---

### Task 10: SCAR/CAPA Close → Alert Close Hooks

**Files:**
- Modify: `backend/app/services/scar_service.py` (add alert-close on SCAR close)
- Modify: `backend/app/services/capa_service.py` (add alert-close on CAPA D8_CLOSURE)
- Modify: `backend/app/services/iqc_inspection_service.py` (add incremental evaluation hook)

- [ ] **Step 1: Write failing test for CAPA close → alert close**

```python
@pytest.mark.asyncio
async def test_capa_close_closes_linked_alert(db_session, seed_open_alert_with_capa, seed_manager):
    """When CAPA transitions to D8_CLOSURE, linked alert should auto-close."""
    from app.services.capa_service import update_capa
    capa = seed_open_alert_with_capa.linked_capa
    await update_capa(db_session, capa.report_id, {"status": "D8_CLOSURE"}, seed_manager.user_id)
    await db_session.refresh(seed_open_alert_with_capa)
    assert seed_open_alert_with_capa.status == "closed"
```

Run: `cd backend && python -m pytest tests/test_supplier_risk_service.py::test_capa_close_closes_linked_alert -v`
Expected: FAIL

- [ ] **Step 2: Add hook in capa_service.update_capa**

After status changes to D8_CLOSURE, query `supplier_risk_alerts` where `linked_capa_id = capa.report_id` and `status != 'closed'`, set to "closed".

- [ ] **Step 3: Add hook in scar_service SCAR close transition**

Same pattern: after status becomes "closed", close linked alerts.

- [ ] **Step 4: Add incremental evaluation hook on IQC judgment**

In `iqc_inspection_service.py`, after judgment completes, fire `asyncio.create_task(_trigger_risk_eval(...))` with independent Session.

- [ ] **Step 5: Run tests to verify they pass**

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): CAPA/SCAR close hooks and IQC incremental evaluation"
```

---

### Task 11: API Routes (TDD)

**Files:**
- Create: `backend/app/api/supplier_risk.py`
- Modify: `backend/app/main.py` (register router + start daily loop)

- [ ] **Step 1: Write failing test for GET /api/supplier-risk/alerts**

```python
@pytest.mark.asyncio
async def test_alerts_list_authenticated(client, auth_headers):
    """GET /api/supplier-risk/alerts should return paginated list."""
    resp = await client.get("/api/supplier-risk/alerts", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
```

Run: `cd backend && python -m pytest tests/test_supplier_risk_service.py::test_alerts_list_authenticated -v`
Expected: FAIL (404 — route not registered)

- [ ] **Step 2: Create API routes file with 14 endpoints**

Router prefix: `APIRouter(prefix="/api/supplier-risk", tags=["supplier-risk"])`. All endpoints use `require_permission(Module.SUPPLIER_RISK, ...)`.

| Endpoint | Method | Permission |
|----------|--------|------------|
| `/alerts` | GET | VIEW |
| `/alerts/{alert_id}` | GET | VIEW |
| `/alerts/{alert_id}/handle` | POST | EDIT |
| `/alerts/{alert_id}/scar` | POST | EDIT |
| `/alerts/{alert_id}/capa` | POST | EDIT |
| `/evaluate/{supplier_id}` | POST | EDIT |
| `/evaluate` | POST | APPROVE |
| `/dashboard` | GET | VIEW |
| `/configs` | GET | VIEW |
| `/configs/{config_id}` | PUT | APPROVE |
| `/channels` | GET | VIEW |
| `/channels` | POST | APPROVE |
| `/channels/{channel_id}` | PUT | APPROVE |
| `/channels/{channel_id}` | DELETE | APPROVE |

- [ ] **Step 3: Register router and start daily loop in main.py**

Add `from app.api.supplier_risk import router as supplier_risk_router` and `app.include_router(supplier_risk_router)`.

Daily evaluation loop with initial execution on startup:

```python
async def _risk_eval_loop():
    # Initial evaluation 10 seconds after startup (avoids startup peak)
    await asyncio.sleep(10)
    try:
        async with async_session() as db:
            await evaluate_all_suppliers(db, product_line_code=None)
    except Exception as e:
        logger.error("[risk_eval_init] error: %s", e)

    # Then every 24 hours
    while True:
        await asyncio.sleep(86400)
        try:
            async with async_session() as db:
                await evaluate_all_suppliers(db, product_line_code=None)
        except Exception as e:
            logger.error("[risk_eval] error: %s", e)

risk_eval_task = asyncio.create_task(_risk_eval_loop())
```

Add `risk_eval_task.cancel()` in shutdown section.

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): API routes with /api/supplier-risk prefix, daily eval loop"
```

---

### Task 12: Backend Tests — Service and Integration

**Files:**
- Create: `backend/tests/test_supplier_risk_service.py`
- Create: `backend/tests/test_supplier_risk_integration.py`

**Test DB requirement**: All tests use the project's PostgreSQL test database (same as existing pytest fixtures). In-memory/mock sessions are NOT sufficient for verifying partial unique indexes, concurrent dedup, or transaction rollback. The `db_session` fixture should use `async_session()` with a test database, wrapping each test in a transaction that rolls back on teardown.

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

### Task 13: Frontend — Types, API Client, Routes, and Sidebar

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/supplierRisk.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Ensure @ant-design/charts is installed**

Run: `cd frontend && grep -q '"@ant-design/charts"' package.json || npm install @ant-design/charts`

- [ ] **Step 2: Add TypeScript types**

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

### Task 14: Frontend — Risk Dashboard Page

**Files:**
- Create: `frontend/src/pages/supplierRisk/SupplierRiskPage.tsx`
- Create: `frontend/src/pages/supplierRisk/components/RiskMatrixChart.tsx`
- Create: `frontend/src/pages/supplierRisk/components/AlertTable.tsx`
- Create: `frontend/src/pages/supplierRisk/components/HandleAlertDrawer.tsx`

- [ ] **Step 1: Create RiskMatrixChart component**

```tsx
// frontend/src/pages/supplierRisk/components/RiskMatrixChart.tsx
import React from "react";
import { Scatter } from "@ant-design/charts";
import type { RiskDashboard } from "../../../types";

interface Props { data: RiskDashboard["supplier_risk_points"]; }

const RiskMatrixChart: React.FC<Props> = ({ data }) => {
  const config = {
    data,
    xField: "quality_score",
    yField: "delivery_score",
    sizeField: "compliance_score",
    colorField: "risk_level",
    color: { low: "#52c41a", medium: "#faad14", high: "#fa8c16", critical: "#f5222d" },
    xAxis: { title: { text: "质量风险" }, min: 0, max: 100 },
    yAxis: { title: { text: "交付风险" }, min: 0, max: 100 },
    tooltip: { fields: ["supplier_name", "risk_score", "risk_level"] },
  };
  return <Scatter {...config} />;
};
export default RiskMatrixChart;
```

- [ ] **Step 2: Create AlertTable component**

```tsx
// frontend/src/pages/supplierRisk/components/AlertTable.tsx
import React, { useState, useEffect } from "react";
import { Table, Tag, Button, Space } from "antd";
import type { SupplierRiskAlert } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";
import HandleAlertDrawer from "./HandleAlertDrawer";

const RISK_COLORS: Record<string, string> = { low: "green", medium: "gold", high: "orange", critical: "red" };
const STATUS_LABELS: Record<string, string> = { open: "开放", acknowledged: "已确认", action_taken: "已处置", ignored: "已忽略", closed: "已关闭" };

interface Props {
  productLineCode?: string;
  onRefresh?: () => void;
}

const AlertTable: React.FC<Props> = ({ productLineCode, onRefresh }) => {
  const [data, setData] = useState<SupplierRiskAlert[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<SupplierRiskAlert | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await riskAlertApi.list({ page, page_size: 20, product_line_code: productLineCode });
      setData(res.data.items); setTotal(res.data.total);
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(); }, [page, productLineCode]);

  const columns = [
    { title: "供应商编号", dataIndex: "supplier_no", sorter: true },
    { title: "供应商名称", dataIndex: "supplier_name" },
    { title: "风险等级", dataIndex: "risk_level", render: (v: string) => <Tag color={RISK_COLORS[v]}>{v}</Tag> },
    { title: "风险分", dataIndex: "risk_score", sorter: true },
    { title: "状态", dataIndex: "status", render: (v: string) => STATUS_LABELS[v] || v },
    { title: "快照日期", dataIndex: "snapshot_date" },
    { title: "操作", render: (_: unknown, record: SupplierRiskAlert) => (
      <Button size="small" onClick={() => { setSelectedAlert(record); setDrawerOpen(true); }}>处置</Button>
    )},
  ];

  return (
    <>
      <Table rowKey="alert_id" columns={columns} dataSource={data} loading={loading}
             pagination={{ current: page, total, pageSize: 20, onChange: setPage }} />
      <HandleAlertDrawer alert={selectedAlert} open={drawerOpen}
        onClose={() => { setDrawerOpen(false); fetchData(); onRefresh?.(); }} />
    </>
  );
};
export default AlertTable;
```

- [ ] **Step 3: Create HandleAlertDrawer component**

```tsx
// frontend/src/pages/supplierRisk/components/HandleAlertDrawer.tsx
import React, { useState } from "react";
import { Drawer, Button, Space, Input, message } from "antd";
import type { SupplierRiskAlert } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";

interface Props { alert: SupplierRiskAlert | null; open: boolean; onClose: () => void; }

const HandleAlertDrawer: React.FC<Props> = ({ alert, open, onClose }) => {
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);

  if (!alert) return null;

  const handle = async (action: string) => {
    if (action === "ignore" && !note.trim()) { message.warning("忽略预警需填写理由"); return; }
    setLoading(true);
    try {
      await riskAlertApi.handle(alert.alert_id, { action, note: note || undefined });
      message.success("操作成功"); onClose();
    } catch { message.error("操作失败"); } finally { setLoading(false); }
  };

  const createScar = async () => {
    setLoading(true);
    try { await riskAlertApi.createScar(alert.alert_id); message.success("SCAR 已创建"); onClose(); }
    catch { message.error("创建失败"); } finally { setLoading(false); }
  };

  const createCapa = async () => {
    setLoading(true);
    try { await riskAlertApi.createCapa(alert.alert_id); message.success("CAPA 已创建"); onClose(); }
    catch { message.error("创建失败"); } finally { setLoading(false); }
  };

  return (
    <Drawer title={`预警处置 — ${alert.supplier_name}`} open={open} onClose={onClose} width={400}>
      <Space direction="vertical" style={{ width: "100%" }}>
        <p>风险等级: <b>{alert.risk_level}</b> | 风险分: <b>{alert.risk_score}</b></p>
        <Input.TextArea placeholder="处置备注（忽略时必填）" value={note} onChange={e => setNote(e.target.value)} rows={3} />
        <Space>
          <Button onClick={() => handle("acknowledge")} loading={loading}>确认</Button>
          <Button onClick={() => handle("ignore")} loading={loading}>忽略</Button>
          <Button onClick={() => handle("close")} loading={loading}>关闭</Button>
        </Space>
        <Space>
          <Button type="primary" onClick={createScar} loading={loading}>创建 SCAR</Button>
          <Button type="primary" onClick={createCapa} loading={loading}>创建 CAPA</Button>
        </Space>
      </Space>
    </Drawer>
  );
};
export default HandleAlertDrawer;
```

- [ ] **Step 4: Create SupplierRiskPage**

```tsx
// frontend/src/pages/supplierRisk/SupplierRiskPage.tsx
import React, { useState, useEffect } from "react";
import { Row, Col, Card, Statistic } from "antd";
import { WarningOutlined, AlertOutlined } from "@ant-design/icons";
import RiskMatrixChart from "./components/RiskMatrixChart";
import AlertTable from "./components/AlertTable";
import { riskAlertApi } from "../../api/supplierRisk";
import type { RiskDashboard } from "../../types";

const SupplierRiskPage: React.FC = () => {
  const [dashboard, setDashboard] = useState<RiskDashboard | null>(null);

  useEffect(() => {
    riskAlertApi.dashboard().then(res => setDashboard(res.data));
  }, []);

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}><Card><Statistic title="高风险供应商" value={dashboard?.high_risk_count ?? 0} prefix={<WarningOutlined />} valueStyle={{ color: "#fa8c16" }} /></Card></Col>
        <Col span={6}><Card><Statistic title="极高风险" value={dashboard?.critical_risk_count ?? 0} prefix={<AlertOutlined />} valueStyle={{ color: "#f5222d" }} /></Card></Col>
        <Col span={6}><Card><Statistic title="开放预警" value={dashboard?.open_alert_count ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="平均风险分" value={dashboard?.avg_risk_score ?? 0} precision={1} /></Card></Col>
      </Row>
      <Card title="风险矩阵" style={{ marginBottom: 24 }}>
        {dashboard && <RiskMatrixChart data={dashboard.supplier_risk_points} />}
      </Card>
      <Card title="预警列表">
        <AlertTable onRefresh={() => riskAlertApi.dashboard().then(res => setDashboard(res.data))} />
      </Card>
    </div>
  );
};
export default SupplierRiskPage;
```

- [ ] **Step 5: Verify page renders**

Run: `cd frontend && npm run build`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): risk dashboard page with matrix chart, alert table, handle drawer"
```

---

### Task 15: Frontend — Config Page

**Files:**
- Create: `frontend/src/pages/supplierRisk/RiskConfigPage.tsx`
- Create: `frontend/src/pages/supplierRisk/components/RuleConfigTable.tsx`
- Create: `frontend/src/pages/supplierRisk/components/ChannelConfigTable.tsx`

- [ ] **Step 1: Create RuleConfigTable component**

```tsx
// frontend/src/pages/supplierRisk/components/RuleConfigTable.tsx
import React, { useState, useEffect } from "react";
import { Table, Switch, InputNumber, Button, message, Modal, Form, Input } from "antd";
import type { SupplierRiskConfig } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";

const RuleConfigTable: React.FC = () => {
  const [data, setData] = useState<SupplierRiskConfig[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try { const res = await riskAlertApi.listConfigs(); setData(res.data); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchData(); }, []);

  const toggleEnabled = async (record: SupplierRiskConfig, enabled: boolean) => {
    await riskAlertApi.updateConfig(record.config_id, { enabled });
    message.success("已更新"); fetchData();
  };

  const updateWeight = async (record: SupplierRiskConfig, weight: number) => {
    await riskAlertApi.updateConfig(record.config_id, { weight });
    message.success("权重已更新");
  };

  const columns = [
    { title: "规则", dataIndex: "rule_id" },
    { title: "类别", dataIndex: "category", render: (v: string) => ({ quality: "质量", delivery: "交付", compliance: "合规" }[v] || v) },
    { title: "启用", dataIndex: "enabled", render: (v: boolean, record: SupplierRiskConfig) => <Switch checked={v} onChange={val => toggleEnabled(record, val)} /> },
    { title: "权重", dataIndex: "weight", render: (v: number, record: SupplierRiskConfig) => <InputNumber min={0} max={100} value={v} onBlur={() => updateWeight(record, v)} size="small" /> },
    { title: "阈值", dataIndex: "thresholds", render: (v: Record<string, unknown>) => <span>{JSON.stringify(v)}</span> },
  ];

  return <Table rowKey="config_id" columns={columns} dataSource={data} loading={loading} pagination={false} />;
};
export default RuleConfigTable;
```

- [ ] **Step 2: Create ChannelConfigTable component**

```tsx
// frontend/src/pages/supplierRisk/components/ChannelConfigTable.tsx
import React, { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Select, Switch, message, Popconfirm } from "antd";
import type { NotificationChannel } from "../../../types";
import { riskAlertApi } from "../../../api/supplierRisk";

const ChannelConfigTable: React.FC = () => {
  const [data, setData] = useState<NotificationChannel[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try { const res = await riskAlertApi.listChannels(); setData(res.data); }
    finally { setLoading(false); }
  };
  useEffect(() => { fetchData(); }, []);

  const createChannel = async (values: Record<string, unknown>) => {
    try { await riskAlertApi.createChannel(values); message.success("已创建"); setModalOpen(false); fetchData(); }
    catch { message.error("创建失败"); }
  };

  const deleteChannel = async (id: string) => {
    try { await riskAlertApi.deleteChannel(id); message.success("已删除"); fetchData(); }
    catch { message.error("删除失败"); }
  };

  const columns = [
    { title: "类型", dataIndex: "channel_type", render: (v: string) => v === "email" ? "邮件" : "Webhook" },
    { title: "最低风险等级", dataIndex: "min_risk_level" },
    { title: "启用", dataIndex: "enabled", render: (v: boolean) => <Switch checked={v} disabled /> },
    { title: "操作", render: (_: unknown, record: NotificationChannel) => (
      <Popconfirm title="确定删除?" onConfirm={() => deleteChannel(record.channel_id)}><Button size="small" danger>删除</Button></Popconfirm>
    )},
  ];

  return (
    <>
      <Button type="primary" onClick={() => setModalOpen(true)} style={{ marginBottom: 16 }}>添加渠道</Button>
      <Table rowKey="channel_id" columns={columns} dataSource={data} loading={loading} />
      <Modal title="添加通知渠道" open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => form.submit()}>
        <Form form={form} onFinish={createChannel} layout="vertical">
          <Form.Item name="channel_type" label="类型" rules={[{ required: true }]}>
            <Select options={[{ value: "email", label: "邮件" }, { value: "webhook", label: "Webhook" }]} />
          </Form.Item>
          <Form.Item name="min_risk_level" label="最低风险等级" initialValue="high">
            <Select options={[{ value: "high", label: "高" }, { value: "critical", label: "极高" }]} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.channel_type !== cur.channel_type}>
            {({ getFieldValue }) => getFieldValue("channel_type") === "email" ? (
              <Form.Item name={["config", "addresses"]} label="邮件地址（逗号分隔）" rules={[{ required: true }]}>
                <Input placeholder="a@b.com,c@d.com" />
              </Form.Item>
            ) : (
              <>
                <Form.Item name={["config", "url"]} label="Webhook URL" rules={[{ required: true }]}>
                  <Input placeholder="https://hooks.example.com/..." />
                </Form.Item>
                <Form.Item name={["config", "secret"]} label="签名密钥" rules={[{ required: true }]}>
                  <Input.Password />
                </Form.Item>
              </>
            )}
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};
export default ChannelConfigTable;
```

- [ ] **Step 3: Create RiskConfigPage**

```tsx
// frontend/src/pages/supplierRisk/RiskConfigPage.tsx
import React from "react";
import { Tabs, Card } from "antd";
import RuleConfigTable from "./components/RuleConfigTable";
import ChannelConfigTable from "./components/ChannelConfigTable";

const RiskConfigPage: React.FC = () => (
  <Card style={{ margin: 24 }}>
    <Tabs items={[
      { key: "rules", label: "规则配置", children: <RuleConfigTable /> },
      { key: "channels", label: "通知渠道", children: <ChannelConfigTable /> },
    ]} />
  </Card>
);
export default RiskConfigPage;
```

- [ ] **Step 4: Verify page renders**

Run: `cd frontend && npm run build`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(supplier-risk): config page with rule config and notification channel tables"
```

---

### Task 16: End-to-End Verification

**Files:** None (verification only)

- [ ] **Step 1: Start backend and verify API**

Run: `cd backend && uvicorn app.main:app --reload`
Then verify endpoints respond (all under `/api/supplier-risk/`):
- `GET /api/supplier-risk/dashboard` → 200
- `GET /api/supplier-risk/alerts` → 200 with empty list
- `GET /api/supplier-risk/configs` → 200 with 10 default configs
- `POST /api/supplier-risk/evaluate` → 200 (triggers full evaluation)

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
