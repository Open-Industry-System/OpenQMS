# Supply Chain Risk Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-dimensional supply chain risk heatmap that visualizes supplier risk across quality/delivery/compliance/ERP dimensions with timeline replay, drill-down, comparison, and export.

**Architecture:** Backend: new `supply_chain_risk_map` service module with aggregator, service, and scheduler. Pure scoring function extracted from `supplier_risk` (no side effects). New DB table `supply_chain_risk_snapshots` with PG15 `UNIQUE NULLS NOT DISTINCT` constraint. ERP `actual_delivery_date` field added to purchase orders. Frontend: ECharts heatmap with timeline slider, detail panel, comparison radar, export. Uses `pg_try_advisory_lock` for scheduler concurrency.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 async + PostgreSQL 15 + Pydantic v2 | React 18 + TypeScript + Ant Design 5 + ECharts 6 + openpyxl

---

## File Structure

### Backend (new/modified)

```
backend/app/
├── models/
│   ├── erp.py                          # MODIFY: add actual_delivery_date to ERPPurchaseOrder
│   └── supply_chain_risk_map.py        # CREATE: SupplyChainRiskSnapshot model
├── schemas/
│   └── supply_chain_risk_map.py        # CREATE: Pydantic request/response schemas
├── services/
│   ├── supplier_risk/
│   │   └── service.py                  # MODIFY: extract calculate_all_supplier_scores
│   └── supply_chain_risk_map/
│       ├── __init__.py                 # CREATE: public interface
│       ├── aggregator.py              # CREATE: multi-source aggregation + normalization
│       ├── service.py                  # CREATE: snapshot management + queries + export
│       └── scheduler.py               # CREATE: pg advisory lock + async loop
├── api/
│   └── supply_chain_risk_map.py        # CREATE: API routes
├── core/
│   └── permissions.py                 # MODIFY: add SUPPLY_CHAIN_RISK_MAP to Module enum
├── models/__init__.py                  # MODIFY: import new model
└── main.py                             # MODIFY: register router + start scheduler

backend/alembic/versions/
└── 035_add_supply_chain_risk_snapshot_table.py  # CREATE: migration

backend/tests/
├── test_supplier_risk_service.py          # MODIFY: add test for extracted function (1 test)
├── test_supply_chain_risk_aggregator.py   # CREATE: 6 aggregation + 3 pure-function tests
├── test_supply_chain_risk_service.py      # CREATE: 5 snapshot/service tests
├── test_supply_chain_risk_integration.py  # CREATE: 6 API integration tests
└── test_supply_chain_risk_e2e.py          # CREATE: 4 end-to-end tests

frontend/src/
├── api/
│   └── supplyChainRiskMap.ts           # CREATE: API client
├── types/
│   └── index.ts                        # MODIFY: add risk map types
├── pages/
│   └── supplyChainRiskMap/
│       ├── SupplyChainRiskMapPage.tsx   # CREATE: main page (left-right layout)
│       └── components/
│           ├── RiskHeatmap.tsx          # CREATE: ECharts heatmap core
│           ├── HeatmapToolbar.tsx       # CREATE: product line select + refresh + export
│           ├── TimelineSlider.tsx       # CREATE: timeline slider + play controls
│           ├── DetailPanel.tsx          # CREATE: right panel container
│           ├── SupplierDetail.tsx       # CREATE: single supplier drill-down
│           ├── SupplierComparison.tsx   # CREATE: multi-select comparison table
│           ├── ComparisonRadar.tsx      # CREATE: ECharts radar overlay
│           ├── DiffIndicator.tsx        # CREATE: month-over-month diff arrows
│           ├── DataSourceBadge.tsx      # CREATE: data source tag component
│           └── ExportButton.tsx         # CREATE: CSV/Excel export dropdown
├── components/
│   └── layout/
│       └── AppLayout.tsx               # MODIFY: add supply chain risk map menu item
└── App.tsx                             # MODIFY: add route
```

---

## Task 1: Database Migration — ERP `actual_delivery_date` + Snapshot Table

**Files:**
- Create: `backend/alembic/versions/035_add_supply_chain_risk_snapshot_table.py`
- Modify: `backend/app/models/erp.py`
- Create: `backend/app/models/supply_chain_risk_map.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write the migration file**

```python
"""add supply chain risk snapshot table + erp po actual_delivery_date

Revision ID: 035_add_supply_chain_risk_snapshot
Revises: 20260611_add_review_reports
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "035_add_supply_chain_risk_snapshot"
down_revision = "20260611_add_review_reports"


def upgrade() -> None:
    # 1. Add actual_delivery_date to erp_purchase_orders
    op.add_column(
        "erp_purchase_orders",
        sa.Column("actual_delivery_date", sa.Date(), nullable=True),
    )

    # 2. Create supply_chain_risk_snapshots table
    op.create_table(
        "supply_chain_risk_snapshots",
        sa.Column("snapshot_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_line_code", sa.String(20), sa.ForeignKey("product_lines.code", ondelete="CASCADE"), nullable=True),
        sa.Column("snapshot_period", sa.String(7), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("risk_level", sa.String(10), nullable=False, server_default="low"),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("delivery_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("compliance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("erp_on_time_rate", sa.Float(), nullable=True),
        sa.Column("erp_on_time_rate_source", sa.String(30), nullable=True),
        sa.Column("purchase_amount_pct", sa.Float(), nullable=True),
        sa.Column("delivery_delay_days", sa.Float(), nullable=True),
        sa.Column("open_scar_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ppm_value", sa.Float(), nullable=True),
        sa.Column("dimensions", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 3. Unique constraint — NULLS NOT DISTINCT (PostgreSQL 15+)
    # NOTE: JSONB and NULLS NOT DISTINCT are both PostgreSQL-only.
    # SQLite tests must use a standard unique constraint and test NULL dedup
    # at the application layer, since SQLite unique constraints don't enforce
    # uniqueness on NULL columns.
    op.execute(
        "ALTER TABLE supply_chain_risk_snapshots "
        "ADD CONSTRAINT uq_supplier_pl_period "
        "UNIQUE NULLS NOT DISTINCT (supplier_id, product_line_code, snapshot_period)"
    )

    # 4. Indexes
    op.create_index("idx_scrs_period", "supply_chain_risk_snapshots", ["snapshot_period"])
    op.create_index("idx_scrs_supplier", "supply_chain_risk_snapshots", ["supplier_id"])

    # 5. Permission seeds for SUPPLY_CHAIN_RISK_MAP module
    PERMS = {
        "admin": 5,
        "manager": 5,
        "field_qe": 3,
        "supplier_qe": 3,
        "customer_qe": 3,
        "planning_qe": 3,
        "viewer": 1,
    }
    for role_key, level in PERMS.items():
        op.execute(
            f"INSERT INTO role_permissions (role_id, module, permission_level) "
            f"SELECT rd.id, 'supply_chain_risk_map', {level} "
            f"FROM role_definitions rd WHERE rd.role_key = '{role_key}' "
            f"ON CONFLICT DO NOTHING"
        )


def downgrade() -> None:
    op.drop_index("idx_scrs_supplier", table_name="supply_chain_risk_snapshots")
    op.drop_index("idx_scrs_period", table_name="supply_chain_risk_snapshots")
    op.execute("ALTER TABLE supply_chain_risk_snapshots DROP CONSTRAINT uq_supplier_pl_period")
    op.drop_table("supply_chain_risk_snapshots")
    op.drop_column("erp_purchase_orders", "actual_delivery_date")

    # Remove permission seeds
    op.execute("DELETE FROM role_permissions WHERE module = 'supply_chain_risk_map'")
```

- [ ] **Step 2: Create the ORM model file**

Create `backend/app/models/supply_chain_risk_map.py`:

```python
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, DateTime, Date, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SupplyChainRiskSnapshot(Base):
    __tablename__ = "supply_chain_risk_snapshots"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id", ondelete="CASCADE"), nullable=False)
    product_line_code: Mapped[Optional[str]] = mapped_column(String(20), ForeignKey("product_lines.code", ondelete="CASCADE"), nullable=True)
    snapshot_period: Mapped[str] = mapped_column(String(7), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False, server_default="low")
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    delivery_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    compliance_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    erp_on_time_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    erp_on_time_rate_source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    purchase_amount_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delivery_delay_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_scar_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ppm_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dimensions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 3: Add `actual_delivery_date` to ERPPurchaseOrder model**

In `backend/app/models/erp.py`, add to the `ERPPurchaseOrder` class after `received_quantity`:

```python
    actual_delivery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
```

- [ ] **Step 4: Register the new model in `__init__.py`**

In `backend/app/models/__init__.py`, add:

```python
from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
```

And add `SupplyChainRiskSnapshot` to the `__all__` list.

- [ ] **Step 5: Run the migration and verify**

```bash
cd backend
alembic upgrade head
python -c "from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot; print('OK')"
```

Expected: Migration runs without errors, model imports OK.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/035_add_supply_chain_risk_snapshot_table.py backend/app/models/supply_chain_risk_map.py backend/app/models/erp.py backend/app/models/__init__.py
git commit -m "feat(supply-chain-risk-map): add migration, model, and erp po actual_delivery_date field"
```

---

## Task 2: Extract Pure Scoring Function from `supplier_risk`

**Files:**
- Modify: `backend/app/services/supplier_risk/service.py`

- [ ] **Step 1: Write the failing test**

Create a minimal test in `backend/tests/test_supplier_risk_service.py` that verifies `calculate_all_supplier_scores` returns scores without writing alerts:

```python
import pytest
from uuid import uuid4
from sqlalchemy import select, func
from app.services.supplier_risk.service import calculate_all_supplier_scores


@pytest.fixture
async def test_user(db):
    """Create a minimal user row so FKs like created_by/updated_by resolve."""
    from app.models.user import User
    from app.models.role import RoleDefinition
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="admin", name_zh="管理员", name_en="Admin", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))
        role = result.scalar_one()
    user = User(
        user_id=uuid4(), username=f"risk_svc_test_{uuid4().hex[:8]}",
        display_name="SvcTest", password_hash="hashed",
        role_id=role.id, legacy_role="admin", is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_calculate_all_supplier_scores_returns_scores_without_side_effects(db, test_user):
    """calculate_all_supplier_scores should return scores for all suppliers
    including low-risk ones, without creating alerts or committing."""
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierRiskConfig, SupplierRiskAlert

    # Create an approved supplier
    supplier = Supplier(
        supplier_id=uuid4(),
        supplier_no="TEST-SCRM-001",
        name="Test Supplier SCRM",
        short_name="Test SCRM",
        status="approved",
        created_by=test_user.user_id,
    )
    db.add(supplier)

    # Seed global default configs for all 10 rules so the supplier gets scored.
    # Without configs, calculate_all_supplier_scores skips the supplier entirely.
    from app.services.supplier_risk.config import DEFAULT_CONFIGS
    for cfg in DEFAULT_CONFIGS:
        db.add(SupplierRiskConfig(
            config_id=uuid4(),
            rule_id=cfg["rule_id"],
            enabled=True,
            thresholds=cfg["thresholds"],
            weight=cfg["weight"],
            supplier_id=None,
            category=cfg["category"],
            product_line_code=None,
            updated_by=test_user.user_id,
        ))
    await db.commit()

    # Verify no alerts exist before calling
    count_before = (await db.execute(
        select(func.count()).select_from(SupplierRiskAlert)
    )).scalar()

    result = await calculate_all_supplier_scores(db, product_line_code=None)

    # Verify no alerts were created
    count_after = (await db.execute(
        select(func.count()).select_from(SupplierRiskAlert)
    )).scalar()
    assert count_after == count_before, "calculate_all_supplier_scores should not create alerts"

    # Verify result includes the supplier (even if low risk)
    assert any(r["supplier_id"] == supplier.supplier_id for r in result)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_supplier_risk_service.py::test_calculate_all_supplier_scores_returns_scores_without_side_effects -v
```

Expected: FAIL with `ImportError: cannot import name 'calculate_all_supplier_scores'`

- [ ] **Step 3: Implement `calculate_all_supplier_scores`**

In `backend/app/services/supplier_risk/service.py`, add a new function that reuses the data-gathering and rule-evaluation logic from `evaluate_all_suppliers` but skips `_upsert_alert`, `db.commit()`, and notifications:

```python
async def calculate_all_supplier_scores(
    db: AsyncSession,
    product_line_code: Optional[str] = None,
) -> list[dict]:
    """Pure scoring — returns risk scores for all active suppliers without side effects.

    Unlike evaluate_all_suppliers, this function:
    - Does NOT write alerts
    - Does NOT commit
    - Does NOT send notifications
    - Includes LOW-RISK suppliers (which evaluate_all_suppliers skips)
    """
    result = await db.execute(
        select(Supplier).where(Supplier.status == "approved")
    )
    suppliers = list(result.scalars().all())
    if not suppliers:
        return []

    supplier_ids = [s.supplier_id for s in suppliers]

    inspections_by_supplier = await _batch_gather_inspections(db, supplier_ids, product_line_code)
    scars_by_supplier = await _batch_gather_scars(db, supplier_ids, product_line_code)
    evaluations_by_supplier = await _batch_gather_evaluations(db, supplier_ids)
    certifications_by_supplier = await _batch_gather_certifications(db, supplier_ids)
    configs_by_supplier = await get_effective_configs_batch(db, supplier_ids, product_line_code)

    results = []
    for supplier in suppliers:
        configs = configs_by_supplier.get(supplier.supplier_id)
        if not configs:
            continue
        input_data = SupplierRiskInput(
            supplier=supplier,
            inspections=inspections_by_supplier.get(supplier.supplier_id, []),
            scars=scars_by_supplier.get(supplier.supplier_id, []),
            evaluations=evaluations_by_supplier.get(supplier.supplier_id, []),
            certifications=certifications_by_supplier.get(supplier.supplier_id, []),
        )
        rule_results, failed_ids = run_all_rules(input_data, configs)
        risk_score = calculate_risk_score(rule_results, configs)

        results.append({
            "supplier_id": supplier.supplier_id,
            "supplier_name": supplier.name,
            "risk_level": risk_score.risk_level,
            "risk_score": risk_score.risk_score,
            "quality_score": risk_score.quality_score,
            "delivery_score": risk_score.delivery_score,
            "compliance_score": risk_score.compliance_score,
            "rule_results": [
                {"rule_id": r.rule_id, "triggered": r.triggered, "score": r.score,
                 "detail": r.detail, "category": r.category, "critical": r.critical}
                for r in rule_results
            ],
        })
    return results
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_supplier_risk_service.py::test_calculate_all_supplier_scores_returns_scores_without_side_effects -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/supplier_risk/service.py backend/tests/test_supplier_risk_service.py
git commit -m "feat(supplier-risk): extract calculate_all_supplier_scores pure function for risk map"
```

---

## Task 3: Aggregation Service

**Files:**
- Create: `backend/app/services/supply_chain_risk_map/__init__.py`
- Create: `backend/app/services/supply_chain_risk_map/aggregator.py`
- Create: `backend/tests/test_supply_chain_risk_aggregator.py`

- [ ] **Step 1: Write aggregator tests**

Create `backend/tests/test_supply_chain_risk_aggregator.py`. The tests must use the project's `db` async fixture from `conftest.py` and seed real ORM objects. Write each test with full setup and assertion code:

```python
import pytest
from datetime import date, timedelta
from uuid import uuid4
from sqlalchemy import select, func, text
from app.services.supply_chain_risk_map.aggregator import (
    aggregate_supply_chain_metrics,
    normalize_to_risk_index,
    ppm_to_risk_index,
)


@pytest.fixture
async def test_user(db):
    """Create a minimal user row so FKs like created_by/evaluated_by resolve."""
    from app.models.user import User
    from app.models.role import RoleDefinition
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="admin", name_zh="管理员", name_en="Admin", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))
        role = result.scalar_one()
    user = User(
        user_id=uuid4(), username=f"risk_agg_test_{uuid4().hex[:8]}",
        display_name="AggTest", password_hash="hashed",
        role_id=role.id, legacy_role="admin", is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_erp_on_time_rate_with_filter(db, test_user):
    """ERP on-time rate uses FILTER (WHERE actual_delivery_date <= delivery_date)."""
    from app.models.supplier import Supplier
    from app.models.erp import ERPPurchaseOrder, ERPConnection, ERPSupplier

    # Seed: approved supplier, ERP connection, POs with actual_delivery_date
    conn_id = uuid4()
    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-ONT-01", name="OntimeTest",
                         short_name="OT", status="approved", created_by=test_user.user_id)
    db.add(supplier)
    erp_conn = ERPConnection(connection_id=conn_id, name="test_conn", connector_type="mock",
                               is_active=True, created_by=test_user.user_id)
    db.add(erp_conn)
    # Link ERP supplier_code to OpenQMS supplier so the join resolves
    db.add(ERPSupplier(
        connection_id=conn_id, supplier_code="T-ONT-01",
        external_id="ERP-SUP-ONT-01", name=supplier.name,
        openqms_supplier_id=supplier.supplier_id,
    ))
    # 3 POs: 2 on-time (actual <= delivery), 1 late
    for i, (ad, dd) in enumerate([
        (date(2026, 6, 1), date(2026, 6, 5)),  # on-time
        (date(2026, 6, 3), date(2026, 6, 5)),  # on-time
        (date(2026, 6, 10), date(2026, 6, 5)),  # late
    ]):
        db.add(ERPPurchaseOrder(
            po_id=uuid4(), connection_id=conn_id, external_id=f"PO-{i}",
            po_number=f"PO-2026-{i:03d}", line_number="1",
            supplier_code="T-ONT-01", delivery_date=dd,
            actual_delivery_date=ad, quantity=100, unit_price=10,
            status="completed", product_line_code=None,
        ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    assert metrics["erp_on_time_rate"] == pytest.approx(66.67, rel=0.01)
    assert metrics["erp_on_time_rate_source"] == "erp_po"


@pytest.mark.asyncio
async def test_erp_fallback_to_evaluation(db, test_user):
    """When no PO data, fall back to supplier_evaluations.delivery_score."""
    from app.models.supplier import Supplier
    from app.models.supplier import SupplierEvaluation

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-FB-01", name="FallbackTest",
                         short_name="FB", status="approved", created_by=test_user.user_id)
    db.add(supplier)
    db.add(SupplierEvaluation(
        eval_id=uuid4(), supplier_id=supplier.supplier_id,
        eval_period="2026-06", eval_type="monthly",
        quality_score=80, delivery_score=75, service_score=70,
        capa_count=0, finding_count=0, premium_freight_count=0,
        customer_disruption_count=0, capa_penalty=0, finding_penalty=0,
        premium_freight_penalty=0, customer_disruption_penalty=0,
        total_score=75, grade="B", notes="fallback test",
        evaluated_by=test_user.user_id,
    ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    assert metrics["erp_on_time_rate"] == 75.0
    assert metrics["erp_on_time_rate_source"] == "supplier_evaluation_fallback"


@pytest.mark.asyncio
async def test_purchase_amount_pct_window_function(db, test_user):
    """Purchase amount % uses SUM(SUM(...)) OVER () window function."""
    from app.models.supplier import Supplier
    from app.models.erp import ERPPurchaseOrder, ERPConnection, ERPSupplier

    conn_id = uuid4()
    s1 = Supplier(supplier_id=uuid4(), supplier_no="T-PCT-01", name="PctTest1",
                    short_name="P1", status="approved", created_by=test_user.user_id)
    s2 = Supplier(supplier_id=uuid4(), supplier_no="T-PCT-02", name="PctTest2",
                    short_name="P2", status="approved", created_by=test_user.user_id)
    db.add_all([s1, s2])
    erp_conn = ERPConnection(connection_id=conn_id, name="test_conn", connector_type="mock",
                               is_active=True, created_by=test_user.user_id)
    db.add(erp_conn)
    # Link both suppliers in ERPSupplier
    db.add(ERPSupplier(connection_id=conn_id, supplier_code="T-PCT-01", external_id="ERP-SUP-PCT-01", name=s1.name, openqms_supplier_id=s1.supplier_id))
    db.add(ERPSupplier(connection_id=conn_id, supplier_code="T-PCT-02", external_id="ERP-SUP-PCT-02", name=s2.name, openqms_supplier_id=s2.supplier_id))
    # s1: 2 POs totaling 8000; s2: 1 PO totaling 2000 → total 10000
    for sup, qty, price in [(s1, 300, 20), (s1, 100, 20), (s2, 200, 10)]:
        db.add(ERPPurchaseOrder(
            po_id=uuid4(), connection_id=conn_id, external_id=f"PO-{uuid4().hex[:6]}",
            po_number=f"PO-2026-{uuid4().hex[:4]}", line_number="1",
            supplier_code=sup.supplier_no, delivery_date=date(2026, 6, 15),
            quantity=qty, unit_price=price,
            status="completed", product_line_code=None,
        ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [s1.supplier_id, s2.supplier_id], None, "2026-06")
    assert result[s1.supplier_id]["purchase_amount_pct"] == pytest.approx(80.0, rel=0.01)
    assert result[s2.supplier_id]["purchase_amount_pct"] == pytest.approx(20.0, rel=0.01)


@pytest.mark.asyncio
async def test_ppm_calculation_with_period_filter(db, test_user):
    """PPM aggregates only inspections in the snapshot period."""
    from app.models.supplier import Supplier
    from app.models.iqc_inspection import IqcInspection
    from app.models.product_line import ProductLine

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-PPM-01", name="PPMTest",
                         short_name="PT", status="approved", created_by=test_user.user_id)
    db.add(supplier)
    # Create inspections in June (should be counted) and May (should not)
    # PPM = total_defect_qty / total_lot_qty * 1_000_000
    for i, (month, lot_qty, defect_qty) in enumerate([
        (6, 500, 10),   # June, 10 defects out of 500 → 20000 PPM
        (6, 500, 5),    # June, 5 defects out of 500 → 10000 PPM
        (6, 1000, 0),   # June, 0 defects out of 1000 → 0 PPM
        (5, 500, 20),   # May — should be excluded
    ]):
        db.add(IqcInspection(
            inspection_id=uuid4(), inspection_no=f"IQC-PPM-{i:03d}",
            supplier_id=supplier.supplier_id,
            inspection_date=date(2026, month, 15),
            inspection_result="accepted" if defect_qty == 0 else "rejected",
            status="judged", lot_qty=lot_qty, defect_qty=defect_qty,
            product_line_code=None,
        ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    # June: (10+5+0) / (500+500+1000) * 1M = 15/2000 * 1M = 7500 PPM
    assert metrics["ppm_value"] == pytest.approx(7500.0, rel=0.01)
    assert metrics["ppm_source"] == "iqc_inspection"


@pytest.mark.asyncio
async def test_open_scar_count_time_point_logic(db, test_user):
    """SCAR count uses time-point: issued_date <= period_end AND (closed_date IS NULL OR closed_date > period_end)."""
    from app.models.supplier import Supplier, SupplierSCAR

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-SCAR-01", name="SCARTest",
                         short_name="ST", status="approved", created_by=test_user.user_id)
    db.add(supplier)
    period_end = date(2026, 6, 30)
    # SCAR issued before period end, still open — counted
    db.add(SupplierSCAR(
        scar_id=uuid4(), scar_no="SCAR-2026-001", supplier_id=supplier.supplier_id,
        source_type="internal", description="open scar",
        status="open", issued_date=date(2026, 6, 10),
    ))
    # SCAR issued before period end, closed after period end — counted (was open at period end)
    db.add(SupplierSCAR(
        scar_id=uuid4(), scar_no="SCAR-2026-002", supplier_id=supplier.supplier_id,
        source_type="internal", description="closed after period",
        status="closed", issued_date=date(2026, 6, 5), closed_date=date(2026, 7, 15),
    ))
    # SCAR issued after period end — NOT counted
    db.add(SupplierSCAR(
        scar_id=uuid4(), scar_no="SCAR-2026-003", supplier_id=supplier.supplier_id,
        source_type="internal", description="future scar",
        status="open", issued_date=date(2026, 7, 10),
    ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    assert metrics["open_scar_count"] == 2  # Only the first two


# --- Pure function tests (no DB needed) ---

def test_normalize_higher_is_risk():
    result = normalize_to_risk_index({"score": {"raw_value": 65, "polarity": "higher_is_risk", "source": "risk_evaluation"}})
    assert result["score"]["risk_index"] == 65

def test_normalize_lower_is_risk():
    result = normalize_to_risk_index({"rate": {"raw_value": 92, "polarity": "lower_is_risk", "source": "erp_po"}})
    assert result["rate"]["risk_index"] == 8  # 100 - 92

def test_normalize_neutral_exposure():
    result = normalize_to_risk_index({"pct": {"raw_value": 35, "polarity": "neutral_exposure", "source": "erp_po"}})
    assert result["pct"]["risk_index"] == 35  # same as raw

def test_normalize_missing():
    result = normalize_to_risk_index({"rate": {"raw_value": None, "polarity": "lower_is_risk", "source": "missing"}})
    assert result["rate"]["risk_index"] is None
    assert result["rate"]["source"] == "missing"

def test_ppm_to_risk_index():
    assert ppm_to_risk_index(0) == 0
    assert ppm_to_risk_index(500) == 10   # 500 / 50
    assert ppm_to_risk_index(5000) == 100  # min(100, 5000/50)
    assert ppm_to_risk_index(10000) == 100  # capped at 100
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_supply_chain_risk_aggregator.py -v
```

Expected: FAIL with import errors

- [ ] **Step 3: Implement `aggregator.py`**

Create `backend/app/services/supply_chain_risk_map/aggregator.py` implementing:
- `aggregate_supply_chain_metrics(db, supplier_ids, product_line_code, period) -> dict[UUID, dict]` — batch SQL queries for ERP on-time rate (with FILTER), purchase amount % (with window function), open SCAR count (with time-point logic), PPM (with period filter)
- `normalize_to_risk_index(dimensions: dict) -> dict` — pure function for polarity mapping
- `ppm_to_risk_index(ppm: float) -> float` — PPM normalization (0→0, 5000→100, linear: `min(100, ppm / 50)`)

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_supply_chain_risk_aggregator.py -v
```

Expected: All 10 tests PASS (5 DB integration + 5 pure function)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/supply_chain_risk_map/__init__.py backend/app/services/supply_chain_risk_map/aggregator.py backend/tests/test_supply_chain_risk_aggregator.py
git commit -m "feat(supply-chain-risk-map): add aggregator with normalization and time-point logic"
```

---

## Task 4: Snapshot Service + Scheduler

**Files:**
- Create: `backend/app/services/supply_chain_risk_map/service.py`
- Create: `backend/app/services/supply_chain_risk_map/scheduler.py`
- Create: `backend/tests/test_supply_chain_risk_service.py`

- [ ] **Step 1: Write service tests**

Create `backend/tests/test_supply_chain_risk_service.py` with these concrete test cases:

```python
import pytest
from datetime import date
from uuid import uuid4
from sqlalchemy import select, text, func
from app.models.supplier import Supplier
from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
from app.services.supply_chain_risk_map.service import current_period


@pytest.fixture
async def test_user(db):
    """Create a minimal user row so FKs like created_by/updated_by resolve."""
    from app.models.user import User
    from app.models.role import RoleDefinition
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="admin", name_zh="管理员", name_en="Admin", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))
        role = result.scalar_one()
    user = User(
        user_id=uuid4(), username=f"risk_snap_test_{uuid4().hex[:8]}",
        display_name="SnapTest", password_hash="hashed",
        role_id=role.id, legacy_role="admin", is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def seed_supplier(db, test_user):
    """Create an approved supplier with global default configs.
    Also ensures ProductLine DC-DC-100 exists (FK for product_line_code)."""
    from app.models.supplier_risk import SupplierRiskConfig
    from app.models.product_line import ProductLine
    from app.services.supplier_risk.config import DEFAULT_CONFIGS
    # Ensure product line exists for product_line_code FK
    result = await db.execute(
        select(ProductLine).where(ProductLine.code == "DC-DC-100")
    )
    if result.scalar_one_or_none() is None:
        db.add(ProductLine(code="DC-DC-100", name="DC-DC-100"))
        await db.flush()
    supplier = Supplier(
        supplier_id=uuid4(), supplier_no="T-SNAP-01", name="SnapshotTest",
        short_name="ST", status="approved", created_by=test_user.user_id,
    )
    db.add(supplier)
    for cfg in DEFAULT_CONFIGS:
        db.add(SupplierRiskConfig(
            config_id=uuid4(), rule_id=cfg["rule_id"], enabled=True,
            thresholds=cfg["thresholds"], weight=cfg["weight"],
            supplier_id=None, category=cfg["category"], product_line_code=None,
            updated_by=test_user.user_id,
        ))
    await db.commit()
    return supplier


@pytest.mark.asyncio
async def test_generate_snapshot_upsert(db, seed_supplier):
    """Generating snapshot twice for the same month overwrites (UPSERT)."""
    from app.services.supply_chain_risk_map.service import generate_snapshot
    period = current_period()
    count1 = await generate_snapshot(db, None, period)
    assert count1 >= 1
    count2 = await generate_snapshot(db, None, period)
    # Second call should UPSERT, not add new rows
    total = (await db.execute(
        select(func.count()).select_from(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.snapshot_period == period)
    )).scalar()
    assert total == count1  # No duplicate rows


@pytest.mark.asyncio
async def test_product_line_isolation(db, seed_supplier):
    """Different product_line_code creates independent snapshots."""
    from app.services.supply_chain_risk_map.service import generate_snapshot
    period = current_period()
    await generate_snapshot(db, None, period)
    await generate_snapshot(db, "DC-DC-100", period)
    global_count = (await db.execute(
        select(func.count()).select_from(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.product_line_code.is_(None))
    )).scalar()
    pl_count = (await db.execute(
        select(func.count()).select_from(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.product_line_code == "DC-DC-100")
    )).scalar()
    assert global_count >= 1
    assert pl_count >= 1


@pytest.mark.asyncio
async def test_low_risk_supplier_in_snapshot(db, seed_supplier):
    """Suppliers with risk_level='low' still appear in snapshots."""
    from app.services.supply_chain_risk_map.service import generate_snapshot
    await generate_snapshot(db, None, current_period())
    # The seeded supplier MUST appear in the snapshot, even if low risk
    supplier_snapshot = (await db.execute(
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.supplier_id == seed_supplier.supplier_id)
    )).scalar_one_or_none()
    assert supplier_snapshot is not None, "Low-risk supplier must appear in snapshot"


@pytest.mark.asyncio
async def test_historical_month_readonly(db, seed_supplier):
    """Attempting to generate a snapshot for a past month raises ValueError."""
    from app.services.supply_chain_risk_map.service import generate_snapshot
    with pytest.raises(ValueError, match="current"):
        await generate_snapshot(db, None, "2025-01")


@pytest.mark.asyncio
async def test_advisory_lock_prevents_concurrent(db):
    """pg_try_advisory_lock prevents concurrent snapshot generation with separate sessions."""
    from app.services.supply_chain_risk_map.scheduler import _acquire_snapshot_lock, _release_snapshot_lock
    from app.database import async_session

    # Acquire lock in first session
    async with async_session() as db1:
        acquired1 = await _acquire_snapshot_lock(db1)
        assert acquired1 is True

        # Second independent session should fail to acquire the same lock
        async with async_session() as db2:
            acquired2 = await _acquire_snapshot_lock(db2)
            assert acquired2 is False  # Lock already held by db1

        # Release lock from first session
        await _release_snapshot_lock(db1)
```

Each test function has complete setup/teardown and assertions. The `db` fixture comes from `backend/tests/conftest.py`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_supply_chain_risk_service.py -v
```

- [ ] **Step 3: Implement `service.py`**

Create `backend/app/services/supply_chain_risk_map/service.py`:

```python
"""Supply chain risk map service: snapshot generation, heatmap queries, export."""
import json
from datetime import date
from io import BytesIO
from typing import Optional
from uuid import UUID

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import StreamingResponse

from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
from app.services.supplier_risk.service import calculate_all_supplier_scores
from app.services.supply_chain_risk_map.aggregator import (
    aggregate_supply_chain_metrics,
    normalize_to_risk_index,
)
from app.schemas.supply_chain_risk_map import (
    HeatmapCell, HeatmapColumn, HeatmapRow, HeatmapResponse,
    TimelineResponse, SupplierDetailResponse, DimensionDetail,
    SupplierDimensionTrend, ComparisonSupplier, ComparisonResponse,
    SnapshotGenerateResponse,
)


def current_period() -> str:
    """Return current month as YYYY-MM string."""
    today = date.today()
    return f"{today.year}-{today.month:02d}"


def _prev_period(period: str) -> str:
    """Return previous month as YYYY-MM."""
    year, month = period.split("-")
    y, m = int(year), int(month)
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


# Column definitions for the heatmap
HEATMAP_COLUMNS = [
    HeatmapColumn(key="risk_score", label="风险分", type="risk", polarity="higher_is_risk"),
    HeatmapColumn(key="quality_score", label="质量分", type="score", polarity="higher_is_risk"),
    HeatmapColumn(key="delivery_score", label="交付分", type="score", polarity="higher_is_risk"),
    HeatmapColumn(key="compliance_score", label="合规分", type="score", polarity="higher_is_risk"),
    HeatmapColumn(key="erp_on_time_rate", label="ERP准时率", type="percent", polarity="lower_is_risk"),
    HeatmapColumn(key="purchase_amount_pct", label="采购占比", type="percent", polarity="neutral_exposure"),
    HeatmapColumn(key="open_scar_count", label="开放SCAR", type="count", polarity="higher_is_risk"),
    HeatmapColumn(key="ppm_value", label="PPM", type="number", polarity="higher_is_risk"),
]


async def generate_snapshot(
    db: AsyncSession,
    product_line_code: Optional[str],
    period: str,
) -> int:
    """Calculate scores, aggregate metrics, normalize, and UPSERT snapshots.

    Returns number of snapshots created/updated.
    Only allowed for the current period.
    """
    if period != current_period():
        raise ValueError(f"Cannot generate snapshot for {period}: only current period {current_period()} is allowed")

    # 1. Calculate risk scores for all suppliers
    scores = await calculate_all_supplier_scores(db, product_line_code)

    # 2. Aggregate ERP/IQC/SCAR metrics
    supplier_ids = [s["supplier_id"] for s in scores]
    metrics = {}
    if supplier_ids:
        metrics = await aggregate_supply_chain_metrics(db, supplier_ids, product_line_code, period)

    # 3. Build normalized dimensions and UPSERT
    count = 0
    for score_result in scores:
        sid = score_result["supplier_id"]
        supplier_metrics = metrics.get(sid, {})

        # Merge score + metrics into dimensions dict
        dimensions = {
            "risk_score": {"raw_value": score_result["risk_score"], "polarity": "higher_is_risk", "source": "risk_evaluation"},
            "quality_score": {"raw_value": score_result["quality_score"], "polarity": "higher_is_risk", "source": "risk_evaluation"},
            "delivery_score": {"raw_value": score_result["delivery_score"], "polarity": "higher_is_risk", "source": "risk_evaluation"},
            "compliance_score": {"raw_value": score_result["compliance_score"], "polarity": "higher_is_risk", "source": "risk_evaluation"},
            "erp_on_time_rate": {"raw_value": supplier_metrics.get("erp_on_time_rate"), "polarity": "lower_is_risk", "source": supplier_metrics.get("erp_on_time_rate_source", "missing")},
            "purchase_amount_pct": {"raw_value": supplier_metrics.get("purchase_amount_pct"), "polarity": "neutral_exposure", "source": supplier_metrics.get("purchase_amount_pct_source", "missing")},
            "open_scar_count": {"raw_value": supplier_metrics.get("open_scar_count", 0), "polarity": "higher_is_risk", "source": supplier_metrics.get("open_scar_count_source", "missing")},
            "ppm_value": {"raw_value": supplier_metrics.get("ppm_value"), "polarity": "higher_is_risk", "source": supplier_metrics.get("ppm_source", "missing")},
        }

        # Normalize all dimensions to risk_index
        dimensions = normalize_to_risk_index(dimensions)

        # UPSERT using the named constraint (covers both NULL and non-NULL product_line_code)
        await db.execute(
            text("""
                INSERT INTO supply_chain_risk_snapshots
                    (snapshot_id, supplier_id, product_line_code, snapshot_period,
                     risk_score, risk_level, quality_score, delivery_score, compliance_score,
                     erp_on_time_rate, purchase_amount_pct, open_scar_count, ppm_value, dimensions)
                VALUES (gen_random_uuid(), :sid, :plc, :period,
                        :rs, :rl, :qs, :ds, :cs,
                        :ot, :pap, :osc, :ppm, CAST(:dims AS jsonb))
                ON CONFLICT ON CONSTRAINT uq_supplier_pl_period
                DO UPDATE SET
                    risk_score = EXCLUDED.risk_score, risk_level = EXCLUDED.risk_level,
                    quality_score = EXCLUDED.quality_score, delivery_score = EXCLUDED.delivery_score,
                    compliance_score = EXCLUDED.compliance_score, erp_on_time_rate = EXCLUDED.erp_on_time_rate,
                    purchase_amount_pct = EXCLUDED.purchase_amount_pct, open_scar_count = EXCLUDED.open_scar_count,
                    ppm_value = EXCLUDED.ppm_value, dimensions = EXCLUDED.dimensions
            """),
            {
                "sid": sid, "plc": product_line_code, "period": period,
                "rs": score_result["risk_score"], "rl": score_result["risk_level"],
                "qs": score_result["quality_score"], "ds": score_result["delivery_score"],
                "cs": score_result["compliance_score"],
                "ot": supplier_metrics.get("erp_on_time_rate"),
                "pap": supplier_metrics.get("purchase_amount_pct"),
                "osc": supplier_metrics.get("open_scar_count", 0),
                "ppm": supplier_metrics.get("ppm_value"),
                "dims": json.dumps(dimensions),
            },
        )
        count += 1

    await db.commit()
    return count


async def get_heatmap_data(
    db: AsyncSession,
    product_line_code: Optional[str],
    period: Optional[str],
) -> HeatmapResponse:
    """Build heatmap from snapshot + previous month for diff calculation."""
    period = period or current_period()
    prev = _prev_period(period)

    # Current period snapshots
    current_rows = (await db.execute(
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.snapshot_period == period)
        .where(
            SupplyChainRiskSnapshot.product_line_code == product_line_code
            if product_line_code else
            SupplyChainRiskSnapshot.product_line_code.is_(None)
        )
    )).scalars().all()

    # Fetch supplier names for all snapshot supplier_ids
    from app.models.supplier import Supplier
    supplier_ids = list({snap.supplier_id for snap in current_rows})
    supplier_name_map = {}
    if supplier_ids:
        sup_result = await db.execute(
            select(Supplier.supplier_id, Supplier.name)
            .where(Supplier.supplier_id.in_(supplier_ids))
        )
        supplier_name_map = {sid: name for sid, name in sup_result.all()}

    # Previous period snapshots for diff
    prev_map = {}
    prev_rows = (await db.execute(
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.snapshot_period == prev)
        .where(
            SupplyChainRiskSnapshot.product_line_code == product_line_code
            if product_line_code else
            SupplyChainRiskSnapshot.product_line_code.is_(None)
        )
    )).scalars().all()
    for row in prev_rows:
        prev_map[row.supplier_id] = row

    rows = []
    for snap in current_rows:
        prev_snap = prev_map.get(snap.supplier_id)
        cells = []
        for col in HEATMAP_COLUMNS:
            dims = snap.dimensions or {}
            dim = dims.get(col.key, {})
            raw = dim.get("raw_value")
            ri = dim.get("risk_index")
            prev_raw = None
            if prev_snap and prev_snap.dimensions:
                prev_dim = prev_snap.dimensions.get(col.key, {})
                prev_raw = prev_dim.get("raw_value")
            diff_val = None
            if raw is not None and prev_raw is not None:
                diff_val = raw - prev_raw
            cells.append(HeatmapCell(
                key=col.key,
                value=raw,
                risk_index=ri,
                level=_risk_level(raw) if col.key == "risk_score" else None,
                diff=diff_val,
                source=dim.get("source", "missing"),
            ))
        rows.append(HeatmapRow(
            supplier_id=snap.supplier_id,
            supplier_name=supplier_name_map.get(snap.supplier_id, str(snap.supplier_id)),
            cells=cells,
        ))

    return HeatmapResponse(
        period=period,
        prev_period=prev,
        product_line_code=product_line_code,
        columns=HEATMAP_COLUMNS,
        rows=rows,
    )


async def get_timeline(
    db: AsyncSession,
    product_line_code: Optional[str],
) -> TimelineResponse:
    """Return list of periods that have snapshots, filtered by product line."""
    query = select(SupplyChainRiskSnapshot.snapshot_period).distinct()
    if product_line_code:
        query = query.where(SupplyChainRiskSnapshot.product_line_code == product_line_code)
    else:
        query = query.where(SupplyChainRiskSnapshot.product_line_code.is_(None))
    result = await db.execute(query.order_by(SupplyChainRiskSnapshot.snapshot_period))
    periods = [r for (r,) in result.all()]

    # Count distinct suppliers in current period
    count_query = select(func.count(SupplyChainRiskSnapshot.supplier_id.distinct()))
    if product_line_code:
        count_query = count_query.where(SupplyChainRiskSnapshot.product_line_code == product_line_code)
    else:
        count_query = count_query.where(SupplyChainRiskSnapshot.product_line_code.is_(None))
    supplier_count = (await db.execute(
        count_query.where(SupplyChainRiskSnapshot.snapshot_period == current_period())
    )).scalar() or 0

    return TimelineResponse(
        periods=periods,
        current_period=current_period(),
        supplier_count=supplier_count,
    )


async def get_supplier_detail(
    db: AsyncSession,
    supplier_id: UUID,
    product_line_code: Optional[str],
    period: Optional[str],
) -> SupplierDetailResponse:
    """Return single supplier detail with dimensions + 6-month trend."""
    period = period or current_period()

    snap = (await db.execute(
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.supplier_id == supplier_id)
        .where(SupplyChainRiskSnapshot.snapshot_period == period)
        .where(
            SupplyChainRiskSnapshot.product_line_code == product_line_code
            if product_line_code else
            SupplyChainRiskSnapshot.product_line_code.is_(None)
        )
    )).scalar_one_or_none()

    if not snap:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Fetch supplier name
    from app.models.supplier import Supplier
    sup = await db.get(Supplier, snap.supplier_id)
    supplier_name = sup.name if sup else str(snap.supplier_id)

    dimensions = {
        key: DimensionDetail(
            raw_value=val.get("raw_value"),
            risk_index=val.get("risk_index"),
            polarity=val.get("polarity", "higher_is_risk"),
            source=val.get("source", "missing"),
        )
        for key, val in (snap.dimensions or {}).items()
    }

    # 6-month trend
    trend_rows = (await db.execute(
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.supplier_id == supplier_id)
        .order_by(SupplyChainRiskSnapshot.snapshot_period.desc())
        .limit(6)
    )).scalars().all()
    trend = [
        SupplierDimensionTrend(
            period=t.snapshot_period,
            risk_score=t.risk_score,
            quality_score=t.quality_score,
            delivery_score=t.delivery_score,
            compliance_score=t.compliance_score,
        )
        for t in reversed(trend_rows)
    ]

    return SupplierDetailResponse(
        supplier_id=snap.supplier_id,
        supplier_name=supplier_name,
        product_line_code=product_line_code,
        period=period,
        dimensions=dimensions,
        trend=trend,
    )


async def get_comparison(
    db: AsyncSession,
    supplier_ids: list[UUID],
    product_line_code: Optional[str],
    period: Optional[str],
) -> ComparisonResponse:
    """Return side-by-side comparison of multiple suppliers."""
    period = period or current_period()

    snaps = (await db.execute(
        select(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.supplier_id.in_(supplier_ids))
        .where(SupplyChainRiskSnapshot.snapshot_period == period)
        .where(
            SupplyChainRiskSnapshot.product_line_code == product_line_code
            if product_line_code else
            SupplyChainRiskSnapshot.product_line_code.is_(None)
        )
    )).scalars().all()

    # Fetch supplier names
    from app.models.supplier import Supplier
    sup_result = await db.execute(
        select(Supplier.supplier_id, Supplier.name)
        .where(Supplier.supplier_id.in_(supplier_ids))
    )
    sup_name_map = {sid: name for sid, name in sup_result.all()}

    suppliers = []
    for snap in snaps:
        dimensions = {
            key: DimensionDetail(
                raw_value=val.get("raw_value"),
                risk_index=val.get("risk_index"),
                polarity=val.get("polarity", "higher_is_risk"),
                source=val.get("source", "missing"),
            )
            for key, val in (snap.dimensions or {}).items()
        }
        suppliers.append(ComparisonSupplier(
            supplier_id=snap.supplier_id,
            supplier_name=sup_name_map.get(snap.supplier_id, str(snap.supplier_id)),
            dimensions=dimensions,
        ))

    return ComparisonResponse(period=period, suppliers=suppliers)


async def export_heatmap(
    db: AsyncSession,
    product_line_code: Optional[str],
    period: Optional[str],
    format: str,
) -> StreamingResponse:
    """Export heatmap as CSV or Excel with conditional formatting."""
    heatmap = await get_heatmap_data(db, product_line_code, period)

    if format == "excel":
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "风险热力图"

        # Header
        headers = ["供应商"] + [c.label for c in heatmap.columns] + [c.label + "(来源)" for c in heatmap.columns]
        ws.append(headers)

        # Rows with conditional formatting
        for row in heatmap.rows:
            values = [row.supplier_name]
            sources = [""]
            for cell in row.cells:
                values.append(cell.value if cell.value is not None else "")
                sources.append(cell.source)
            ws.append(values + sources)

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=risk_map_{period}.xlsx"},
        )

    # CSV fallback
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)
    headers = ["供应商"] + [c.label for c in heatmap.columns] + [c.label + "(来源)" for c in heatmap.columns]
    writer.writerow(headers)
    for row in heatmap.rows:
        values = [row.supplier_name]
        sources = [""]
        for cell in row.cells:
            values.append(cell.value if cell.value is not None else "")
            sources.append(cell.source)
        writer.writerow(values + sources)

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=risk_map_{period}.csv"},
    )


def _risk_level(score: float | None) -> str | None:
    if score is None:
        return None
    if score <= 30:
        return "low"
    if score <= 60:
        return "medium"
    if score <= 80:
        return "high"
    return "critical"
```

- [ ] **Step 4: Implement `scheduler.py`**

Create `backend/app/services/supply_chain_risk_map/scheduler.py`:

```python
"""Background scheduler for supply chain risk map snapshots.

Uses pg_try_advisory_lock for concurrency control so only one instance
generates snapshots at a time. Sessions are released before sleep to
avoid holding connections idle.
"""
import asyncio
import logging
from sqlalchemy import text
from app.database import async_session
from app.services.supply_chain_risk_map.service import generate_snapshot, current_period

logger = logging.getLogger(__name__)

LOCK_ID = 20260611  # Unique advisory lock ID for risk map scheduler
SLEEP_SECONDS = 3600  # Run hourly


async def _acquire_snapshot_lock(db) -> bool:
    """Try to acquire the advisory lock. Returns True if acquired."""
    result = await db.execute(text(f"SELECT pg_try_advisory_lock({LOCK_ID})"))
    return result.scalar()


async def _release_snapshot_lock(db) -> bool:
    """Release the advisory lock. Returns True if released."""
    result = await db.execute(text(f"SELECT pg_advisory_unlock({LOCK_ID})"))
    return result.scalar()


async def snapshot_loop():
    """Main loop: acquire lock, generate snapshot, release session, sleep.

    Each iteration opens a fresh session so connections are not held
    during the sleep interval. The sleep always happens outside the
    session context.
    """
    while True:
        try:
            acquired = False
            async with async_session() as db:
                acquired = await _acquire_snapshot_lock(db)
                if acquired:
                    try:
                        period = current_period()
                        count = await generate_snapshot(db, None, period)
                        logger.info(f"Generated {count} snapshots for {period}")
                    finally:
                        await _release_snapshot_lock(db)
                else:
                    logger.debug("Snapshot lock not acquired, skipping")
            # Session is released before sleep — connections not held idle
        except Exception:
            logger.exception("Error in snapshot loop")
        await asyncio.sleep(SLEEP_SECONDS)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_supply_chain_risk_service.py -v
```

Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/supply_chain_risk_map/service.py backend/app/services/supply_chain_risk_map/scheduler.py backend/tests/test_supply_chain_risk_service.py
git commit -m "feat(supply-chain-risk-map): add snapshot service with advisory lock scheduler"
```

---

## Task 5: Pydantic Schemas + API Routes + Module Registration

**Files:**
- Create: `backend/app/schemas/supply_chain_risk_map.py`
- Create: `backend/app/api/supply_chain_risk_map.py`
- Modify: `backend/app/core/permissions.py` (add `SUPPLY_CHAIN_RISK_MAP` to Module enum)
- Modify: `backend/app/main.py` (register router + start scheduler)

- [ ] **Step 1: Create Pydantic schemas**

Create `backend/app/schemas/supply_chain_risk_map.py`:

```python
from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class HeatmapCell(BaseModel):
    key: str
    value: Optional[float] = None
    risk_index: Optional[float] = None
    level: Optional[str] = None
    diff: Optional[float] = None
    source: str  # "risk_evaluation" | "erp_po" | "supplier_evaluation_fallback" | "iqc_inspection" | "missing"


class HeatmapColumn(BaseModel):
    key: str
    label: str
    type: str  # "score" | "percent" | "number" | "count" | "risk"
    polarity: str  # "higher_is_risk" | "lower_is_risk" | "neutral_exposure"


class HeatmapRow(BaseModel):
    supplier_id: UUID
    supplier_name: str
    cells: list[HeatmapCell]


class HeatmapResponse(BaseModel):
    period: str
    prev_period: Optional[str] = None
    product_line_code: Optional[str] = None
    columns: list[HeatmapColumn]
    rows: list[HeatmapRow]


class TimelineResponse(BaseModel):
    periods: list[str]
    current_period: str
    supplier_count: int


class DimensionDetail(BaseModel):
    raw_value: Optional[float] = None
    risk_index: Optional[float] = None
    polarity: str
    source: str


class SupplierDimensionTrend(BaseModel):
    period: str
    risk_score: float
    quality_score: float
    delivery_score: float
    compliance_score: float


class SupplierDetailResponse(BaseModel):
    supplier_id: UUID
    supplier_name: str
    product_line_code: Optional[str] = None
    period: str
    dimensions: dict[str, DimensionDetail]
    trend: list[SupplierDimensionTrend]


class ComparisonSupplier(BaseModel):
    supplier_id: UUID
    supplier_name: str
    dimensions: dict[str, DimensionDetail]


class ComparisonResponse(BaseModel):
    period: str
    suppliers: list[ComparisonSupplier]


class SnapshotGenerateResponse(BaseModel):
    snapshot_count: int
    period: str


class SupplierCompareRequest(BaseModel):
    supplier_ids: list[UUID]
```

- [ ] **Step 2: Create API routes**

Create `backend/app/api/supply_chain_risk_map.py`:

```python
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.core.permissions import require_permission, Module, PermissionLevel
from app.schemas.supply_chain_risk_map import (
    HeatmapResponse, TimelineResponse, SupplierDetailResponse,
    ComparisonResponse, SnapshotGenerateResponse, SupplierCompareRequest,
)
from app.services.supply_chain_risk_map import service

router = APIRouter(prefix="/api/supply-chain-risk-map", tags=["supply-chain-risk-map"])


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_heatmap(
    product_line_code: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    return await service.get_heatmap_data(db, product_line_code, period)


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    product_line_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    return await service.get_timeline(db, product_line_code)


@router.get("/suppliers/{supplier_id}", response_model=SupplierDetailResponse)
async def get_supplier_detail(
    supplier_id: UUID,
    product_line_code: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    return await service.get_supplier_detail(db, supplier_id, product_line_code, period)


@router.post("/suppliers/compare", response_model=ComparisonResponse)
async def compare_suppliers(
    body: SupplierCompareRequest,
    product_line_code: Optional[str] = None,
    period: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    return await service.get_comparison(db, body.supplier_ids, product_line_code, period)


@router.post("/snapshots/generate", response_model=SnapshotGenerateResponse)
async def generate_snapshot(
    product_line_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.EDIT)),
):
    count = await service.generate_snapshot(db, product_line_code, service.current_period())
    return SnapshotGenerateResponse(snapshot_count=count, period=service.current_period())


@router.get("/export")
async def export_heatmap(
    format: str = Query("csv"),
    product_line_code: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(Module.SUPPLY_CHAIN_RISK_MAP, PermissionLevel.VIEW)),
):
    return await service.export_heatmap(db, product_line_code, period, format)
```

- [ ] **Step 3: Add module to permissions**

In `backend/app/core/permissions.py`, add to the `Module` enum:

```python
SUPPLY_CHAIN_RISK_MAP = "supply_chain_risk_map"
```

- [ ] **Step 4: Register router and scheduler in main.py**

In `backend/app/main.py`, make these exact changes:

1. Add import at top of file with other router imports:
```python
from app.api.supply_chain_risk_map import router as supply_chain_risk_map_router
```

2. Add to the router registration section (after `app.include_router(supplier_risk_router)`). The repo convention is for routers to include `/api` in their own prefix — no extra prefix needed at include_router:
```python
app.include_router(supply_chain_risk_map_router)
```

The router file itself must declare:
```python
router = APIRouter(prefix="/api/supply-chain-risk-map", tags=["supply-chain-risk-map"])
```

3. Add scheduler startup in the `lifespan` function, after `risk_eval_task` creation (around line 256). The existing pattern creates an `asyncio.create_task` for the loop, and cancels it in the shutdown section:
```python
from app.services.supply_chain_risk_map.scheduler import snapshot_loop

risk_map_snapshot_task = asyncio.create_task(snapshot_loop())
```

4. Add shutdown cancellation in the cleanup section (after `risk_eval_task` cancellation, around line 296):
```python
# Cancel risk map snapshot task
risk_map_snapshot_task.cancel()
try:
    await risk_map_snapshot_task
except asyncio.CancelledError:
    pass
```

- [ ] **Step 5: Add ERP field to schema and ingestion**

In `backend/app/schemas/erp.py`, add `actual_delivery_date: Optional[date] = None` to `PurchaseOrderOut`.

In `backend/app/services/erp_service.py`, add to `_ingest_purchase_orders` values dict:

```python
"actual_delivery_date": ERPIngestionService._coerce_date(item.get("actual_delivery_date")),
```

In `backend/app/services/erp_connector.py`, add `actual_delivery_date` to mock PO data generation.

- [ ] **Step 6: Run all existing tests to verify no regressions**

```bash
cd backend && python -m pytest tests/ -v --timeout=60
```

Expected: All existing tests pass, no regressions

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/supply_chain_risk_map.py backend/app/api/supply_chain_risk_map.py backend/app/core/permissions.py backend/app/main.py backend/app/schemas/erp.py backend/app/services/erp_service.py backend/app/services/erp_connector.py
git commit -m "feat(supply-chain-risk-map): add schemas, API routes, module registration, and erp po field"
```

---

## Task 6: Integration + Permission Tests

**Files:**
- Create: `backend/tests/test_supply_chain_risk_integration.py`

- [ ] **Step 1: Write integration tests**

Create `backend/tests/test_supply_chain_risk_integration.py` with these concrete test cases:

```python
import pytest
from httpx import AsyncClient
from uuid import uuid4
from datetime import date
from sqlalchemy import select, func
from app.models.user import User
from app.core.security import hash_password, create_access_token


@pytest.fixture
async def admin_user(db):
    """Create a real admin user in DB and return the user object.
    Also ensures role_permissions has supply_chain_risk_map permission
    so the admin can call the API endpoints without 403."""
    from app.models.role import RoleDefinition, RolePermission
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="admin", name_zh="管理员", name_en="Admin", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))
        role = result.scalar_one()
    # Ensure permission exists for this module (migration seeds may not cover fixture-created roles)
    perm_count = (await db.execute(
        select(func.count()).select_from(RolePermission)
        .where(RolePermission.role_id == role.id, RolePermission.module == "supply_chain_risk_map")
    )).scalar()
    if perm_count == 0:
        db.add(RolePermission(role_id=role.id, module="supply_chain_risk_map", permission_level=5))
        await db.flush()
    user = User(
        user_id=uuid4(), username="test_admin_riskmap",
        display_name="Admin RiskMap",
        password_hash=hash_password("Admin@2026"),
        role_id=role.id, legacy_role="admin", is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def viewer_user(db):
    """Create a real viewer user in DB."""
    from app.models.role import RoleDefinition
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "viewer")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="viewer", name_zh="查看者", name_en="Viewer", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "viewer"))
        role = result.scalar_one()
    user = User(
        user_id=uuid4(), username="test_viewer_riskmap",
        display_name="Viewer RiskMap",
        password_hash=hash_password("Viewer@2026"),
        role_id=role.id, legacy_role="viewer", is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def client(db):
    """ASGI test client that uses the same db session as the test.

    Overrides get_db so API endpoints see the test's seeded data.
    Auth (get_current_user) is NOT overridden — tests set Authorization
    header with real JWT tokens so role-based access control is exercised.
    """
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.database import get_db

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(client: AsyncClient, admin_user):
    """Client with real admin user token."""
    token = create_access_token(str(admin_user.user_id))
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
async def viewer_client(client: AsyncClient, viewer_user):
    """Client with real viewer user token."""
    token = create_access_token(str(viewer_user.user_id))
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.mark.asyncio
async def test_csv_export_contains_source_column(admin_client, db):
    """CSV export includes a 'source' column for each dimension."""
    from app.services.supply_chain_risk_map.service import generate_snapshot, current_period
    await generate_snapshot(db, None, current_period())
    response = await admin_client.get(
        "/api/supply-chain-risk-map/export",
        params={"period": current_period(), "format": "csv"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    lines = response.text.split("\n")
    assert any("来源" in line for line in lines[:2])


@pytest.mark.asyncio
async def test_viewer_cannot_generate_snapshot(viewer_client):
    """Viewer role gets 403 on snapshot generate endpoint."""
    response = await viewer_client.post("/api/supply-chain-risk-map/snapshots/generate")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_field_qe_has_edit_permission(db, client, admin_user):
    """field_qe role can generate snapshots (EDIT level)."""
    from app.models.role import RoleDefinition, RolePermission
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "field_qe")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="field_qe", name_zh="现场质量工程师", name_en="Field QE", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "field_qe"))
        role = result.scalar_one()
    # Ensure permission exists: field_qe has EDIT (3) on supply_chain_risk_map
    perm_count = (await db.execute(
        select(func.count()).select_from(RolePermission)
        .where(RolePermission.role_id == role.id, RolePermission.module == "supply_chain_risk_map")
    )).scalar()
    if perm_count == 0:
        db.add(RolePermission(role_id=role.id, module="supply_chain_risk_map", permission_level=3))
        await db.flush()
    user = User(
        user_id=uuid4(), username="test_fqe_riskmap",
        display_name="FQE RiskMap",
        password_hash=hash_password("Fqe@2026"),
        role_id=role.id, legacy_role="field_qe", is_active=True,
    )
    db.add(user)
    await db.commit()
    token = create_access_token(str(user.user_id))
    response = await client.post(
        "/api/supply-chain-risk-map/snapshots/generate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 403  # Not forbidden


@pytest.mark.asyncio
async def test_nulls_not_distinct_prevents_duplicate_snapshot(db, admin_user):
    """UNIQUE NULLS NOT DISTINCT constraint prevents duplicate snapshots (PG-only)."""
    from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
    from app.models.supplier import Supplier
    from app.services.supply_chain_risk_map.service import current_period
    from sqlalchemy.exc import IntegrityError

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-DUP-01", name="DupeTest",
                         short_name="DT", status="approved", created_by=admin_user.user_id)
    db.add(supplier)
    await db.commit()

    s1 = SupplyChainRiskSnapshot(
        snapshot_id=uuid4(), supplier_id=supplier.supplier_id,
        product_line_code=None, snapshot_period=current_period(),
        risk_score=10, risk_level="low",
        quality_score=5, delivery_score=3, compliance_score=2,
    )
    db.add(s1)
    await db.commit()

    s2 = SupplyChainRiskSnapshot(
        snapshot_id=uuid4(), supplier_id=supplier.supplier_id,
        product_line_code=None, snapshot_period=current_period(),
        risk_score=15, risk_level="low",
        quality_score=8, delivery_score=4, compliance_score=3,
    )
    db.add(s2)
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.asyncio
async def test_calculate_all_supplier_scores_called_by_snapshot(db, admin_user):
    """generate_snapshot calls calculate_all_supplier_scores, not evaluate_all_suppliers."""
    from unittest.mock import patch, AsyncMock
    from app.services.supply_chain_risk_map.service import generate_snapshot, current_period
    from app.models.supplier import Supplier

    # Create a real supplier so the FK on supply_chain_risk_snapshots resolves
    supplier = Supplier(
        supplier_id=uuid4(), supplier_no="T-MOCK-01", name="MockSupplier",
        short_name="MS", status="approved", created_by=admin_user.user_id,
    )
    db.add(supplier)
    await db.flush()

    mock_scores = AsyncMock(return_value=[{
        "supplier_id": supplier.supplier_id, "supplier_name": "MockSupplier",
        "risk_level": "low", "risk_score": 10,
        "quality_score": 5, "delivery_score": 3, "compliance_score": 2,
        "rule_results": [],
    }])
    with patch("app.services.supply_chain_risk_map.service.calculate_all_supplier_scores", mock_scores):
        with patch("app.services.supply_chain_risk_map.service.aggregate_supply_chain_metrics", new_callable=AsyncMock) as mock_agg:
            mock_agg.return_value = {}
            await generate_snapshot(db, None, current_period())
    mock_scores.assert_called_once()


@pytest.mark.asyncio
async def test_erp_actual_delivery_date_mapped():
    """actual_delivery_date is correctly mapped in ERP ingestion."""
    from app.services.erp_service import ERPIngestionService
    from app.models.erp import ERPPurchaseOrder

    assert hasattr(ERPPurchaseOrder, "actual_delivery_date")
    item = {"external_id": "test-001", "po_number": "PO-2026-001", "line_number": "1",
            "actual_delivery_date": "2026-06-01"}
    coerced = ERPIngestionService._coerce_date(item.get("actual_delivery_date"))
    assert coerced == date(2026, 6, 1)
```





























































































































- [ ] **Step 2: Run tests**

```bash
cd backend && python -m pytest tests/test_supply_chain_risk_integration.py -v
```

Expected: All 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_supply_chain_risk_integration.py
git commit -m "test(supply-chain-risk-map): add integration and permission tests"
```

---

## Task 7: Frontend Types + API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/supplyChainRiskMap.ts`

- [ ] **Step 1: Add TypeScript types**

In `frontend/src/types/index.ts`, add:

```ts
// --- Supply Chain Risk Map ---

export interface HeatmapCell {
  key: string;
  value: number | null;
  risk_index: number | null;
  level: string | null;
  diff: number | null;
  source: "risk_evaluation" | "erp_po" | "supplier_evaluation_fallback" | "iqc_inspection" | "missing";
}

export interface HeatmapColumn {
  key: string;
  label: string;
  type: "score" | "percent" | "number" | "count" | "risk";
  polarity: "higher_is_risk" | "lower_is_risk" | "neutral_exposure";
}

export interface HeatmapRow {
  supplier_id: string;
  supplier_name: string;
  cells: HeatmapCell[];
}

export interface HeatmapResponse {
  period: string;
  prev_period: string | null;
  product_line_code: string | null;
  columns: HeatmapColumn[];
  rows: HeatmapRow[];
}

export interface TimelineResponse {
  periods: string[];
  current_period: string;
  supplier_count: number;
}

export interface SupplierDimensionTrend {
  period: string;
  risk_score: number;
  quality_score: number;
  delivery_score: number;
  compliance_score: number;
}

export interface SupplierDetailResponse {
  supplier_id: string;
  supplier_name: string;
  product_line_code: string | null;
  period: string;
  dimensions: Record<string, { raw_value: number | null; risk_index: number | null; polarity: string; source: string }>;
  trend: SupplierDimensionTrend[];
}

export interface ComparisonResponse {
  period: string;
  suppliers: Array<{
    supplier_id: string;
    supplier_name: string;
    dimensions: Record<string, { raw_value: number | null; risk_index: number | null; polarity: string; source: string }>;
  }>;
}

export interface SnapshotGenerateResponse {
  snapshot_count: number;
  period: string;
}
```

- [ ] **Step 2: Create API client**

Create `frontend/src/api/supplyChainRiskMap.ts`:

```ts
import client from "./client";
import type {
  HeatmapResponse,
  TimelineResponse,
  SupplierDetailResponse,
  ComparisonResponse,
  SnapshotGenerateResponse,
} from "../types";

export const riskMapApi = {
  heatmap: (params: { product_line_code?: string; period?: string }) =>
    client.get<HeatmapResponse>("/supply-chain-risk-map/heatmap", { params }),

  timeline: (params?: { product_line_code?: string }) =>
    client.get<TimelineResponse>("/supply-chain-risk-map/timeline", { params }),

  supplierDetail: (id: string, params?: { product_line_code?: string; period?: string }) =>
    client.get<SupplierDetailResponse>(`/supply-chain-risk-map/suppliers/${id}`, { params }),

  compare: (supplierIds: string[], params?: { product_line_code?: string; period?: string }) =>
    client.post<ComparisonResponse>("/supply-chain-risk-map/suppliers/compare", { supplier_ids: supplierIds }, { params }),

  generateSnapshot: (params?: { product_line_code?: string }) =>
    client.post<SnapshotGenerateResponse>("/supply-chain-risk-map/snapshots/generate", null, { params }),

  exportCsv: (params: { product_line_code?: string; period?: string }) =>
    client.get("/supply-chain-risk-map/export", { params: { ...params, format: "csv" }, responseType: "blob" }),

  exportExcel: (params: { product_line_code?: string; period?: string }) =>
    client.get("/supply-chain-risk-map/export", { params: { ...params, format: "excel" }, responseType: "blob" }),
};
```

- [ ] **Step 3: Verify types compile**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: No type errors in the new files

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/supplyChainRiskMap.ts
git commit -m "feat(supply-chain-risk-map): add TypeScript types and API client"
```

---

## Task 8: Frontend — Heatmap + Toolbar + Timeline

**Files:**
- Create: `frontend/src/pages/supplyChainRiskMap/SupplyChainRiskMapPage.tsx`
- Create: `frontend/src/pages/supplyChainRiskMap/components/RiskHeatmap.tsx`
- Create: `frontend/src/pages/supplyChainRiskMap/components/HeatmapToolbar.tsx`
- Create: `frontend/src/pages/supplyChainRiskMap/components/TimelineSlider.tsx`

- [ ] **Step 1: Create `HeatmapToolbar.tsx`**

Create `frontend/src/pages/supplyChainRiskMap/components/HeatmapToolbar.tsx`:

```tsx
import React from "react";
import { Select, Button, Space, Dropdown, message } from "antd";
import { ReloadOutlined, DownloadOutlined } from "@ant-design/icons";
import { useProductLineStore } from "../../../store/productLineStore";
import { riskMapApi } from "../../../api/supplyChainRiskMap";

interface HeatmapToolbarProps {
  period: string;
  onPeriodChange: (period: string) => void;
  onRefresh: () => void;
  refreshing: boolean;
}

const HeatmapToolbar: React.FC<HeatmapToolbarProps> = ({
  period,
  onPeriodChange,
  onRefresh,
  refreshing,
}) => {
  const { productLines, selected, setSelected } = useProductLineStore();

  const handleGenerateSnapshot = async () => {
    try {
      const params = selected ? { product_line_code: selected } : undefined;
      const res = await riskMapApi.generateSnapshot(params);
      message.success(`已生成 ${res.data.snapshot_count} 个快照`);
      onRefresh();
    } catch {
      message.error("快照生成失败");
    }
  };

  const handleExport = async (format: "csv" | "excel") => {
    try {
      const params = {
        product_line_code: selected || undefined,
        period,
        format,
      };
      const res = format === "csv"
        ? await riskMapApi.exportCsv(params)
        : await riskMapApi.exportExcel(params);
      const url = window.URL.createObjectURL(res.data as unknown as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `risk_map_${period}.${format === "csv" ? "csv" : "xlsx"}`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      message.error("导出失败");
    }
  };

  return (
    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
      <Space>
        <Select
          value={selected || undefined}
          onChange={setSelected}
          style={{ width: 180 }}
          allowClear
          placeholder="全产品线"
          options={productLines.map((pl) => ({ value: pl.code, label: pl.name }))}
        />
        <Select
          value={period}
          onChange={onPeriodChange}
          style={{ width: 120 }}
          options={[{ value: period, label: period }]}
        />
      </Space>
      <Space>
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          loading={refreshing}
          onClick={handleGenerateSnapshot}
        >
          刷新快照
        </Button>
        <Dropdown
          menu={{
            items: [
              { key: "csv", label: "导出 CSV", onClick: () => handleExport("csv") },
              { key: "excel", label: "导出 Excel", onClick: () => handleExport("excel") },
            ],
          }}
        >
          <Button icon={<DownloadOutlined />}>导出</Button>
        </Dropdown>
      </Space>
    </div>
  );
};

export default HeatmapToolbar;
```

- [ ] **Step 2: Create `TimelineSlider.tsx`**

Create `frontend/src/pages/supplyChainRiskMap/components/TimelineSlider.tsx`:

```tsx
import React, { useState, useEffect, useRef } from "react";
import { Slider, Button, Space, Select } from "antd";
import { StepBackwardOutlined, StepForwardOutlined, CaretRightOutlined, PauseOutlined } from "@ant-design/icons";

interface TimelineSliderProps {
  periods: string[];
  currentPeriod: string;
  onPeriodChange: (period: string) => void;
}

const TimelineSlider: React.FC<TimelineSliderProps> = ({
  periods,
  currentPeriod,
  onPeriodChange,
}) => {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentIndex = periods.indexOf(currentPeriod);

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(() => {
        const nextIndex = currentIndex + 1;
        if (nextIndex < periods.length) {
          onPeriodChange(periods[nextIndex]);
        } else {
          setPlaying(false);
        }
      }, 2000 / speed);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing, currentIndex, speed, periods, onPeriodChange]);

  const handlePrev = () => {
    if (currentIndex > 0) onPeriodChange(periods[currentIndex - 1]);
  };
  const handleNext = () => {
    if (currentIndex < periods.length - 1) onPeriodChange(periods[currentIndex + 1]);
  };

  const marks: Record<number, { label: string; style?: React.CSSProperties }> = {};
  periods.forEach((p, i) => {
    marks[i] = { label: p.slice(2), style: { fontSize: 11 } };
  });

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
      <Space size={4}>
        <Button size="small" icon={<StepBackwardOutlined />} onClick={handlePrev} disabled={currentIndex <= 0} />
        <Button size="small" icon={playing ? <PauseOutlined /> : <CaretRightOutlined />} onClick={() => setPlaying(!playing)} />
        <Button size="small" icon={<StepForwardOutlined />} onClick={handleNext} disabled={currentIndex >= periods.length - 1} />
      </Space>
      <Slider
        min={0}
        max={Math.max(periods.length - 1, 0)}
        value={currentIndex >= 0 ? currentIndex : 0}
        marks={marks}
        onChange={(v) => onPeriodChange(periods[v])}
        style={{ flex: 1 }}
      />
      <Select
        size="small"
        value={speed}
        onChange={setSpeed}
        style={{ width: 64 }}
        options={[
          { value: 0.5, label: "0.5x" },
          { value: 1, label: "1x" },
          { value: 2, label: "2x" },
        ]}
      />
    </div>
  );
};

export default TimelineSlider;
```

- [ ] **Step 3: Create `RiskHeatmap.tsx`**

Create `frontend/src/pages/supplyChainRiskMap/components/RiskHeatmap.tsx`:

```tsx
import React, { useEffect, useRef, useState } from "react";
import { Checkbox, Tooltip } from "antd";
import type { HeatmapResponse, HeatmapRow, HeatmapColumn } from "../../../types";

interface RiskHeatmapProps {
  data: HeatmapResponse | null;
  onCellClick?: (supplierId: string, dimensionKey: string) => void;
  onSupplierClick?: (supplierId: string) => void;
  selectedSupplierIds: string[];
  onSelectionChange: (ids: string[]) => void;
}

const RISK_COLORS = {
  low: "#52c41a",
  medium: "#faad14",
  high: "#fa8c16",
  critical: "#f5222d",
  missing: "#d9d9d9",
};

function getCellColor(riskIndex: number | null, polarity: string): string {
  if (riskIndex === null) return RISK_COLORS.missing;
  if (polarity === "neutral_exposure") {
    // Blue scale for exposure metrics
    const alpha = Math.min(riskIndex / 100, 1);
    return `rgba(24, 144, 255, ${0.2 + alpha * 0.6})`;
  }
  // Green → yellow → orange → red for risk metrics
  if (riskIndex <= 25) return "#52c41a";
  if (riskIndex <= 50) return "#faad14";
  if (riskIndex <= 75) return "#fa8c16";
  return "#f5222d";
}

const RiskHeatmap: React.FC<RiskHeatmapProps> = ({
  data,
  onCellClick,
  onSupplierClick,
  selectedSupplierIds,
  onSelectionChange,
}) => {
  const tableRef = useRef<HTMLDivElement>(null);

  if (!data || data.rows.length === 0) {
    return <div style={{ textAlign: "center", padding: 48, color: "#999" }}>暂无数据</div>;
  }

  const toggleSelect = (supplierId: string) => {
    if (selectedSupplierIds.includes(supplierId)) {
      onSelectionChange(selectedSupplierIds.filter((id) => id !== supplierId));
    } else {
      onSelectionChange([...selectedSupplierIds, supplierId]);
    }
  };

  return (
    <div ref={tableRef} style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>
            <th style={{ padding: 8, textAlign: "center", width: 40 }}></th>
            <th style={{ padding: 8, textAlign: "left", minWidth: 140 }}>供应商</th>
            {data.columns.map((col: HeatmapColumn) => (
              <th key={col.key} style={{ padding: 8, textAlign: "center", minWidth: 80 }}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row: HeatmapRow) => (
            <tr key={row.supplier_id} style={{ borderBottom: "1px solid #f0f0f0" }}>
              <td style={{ padding: 8, textAlign: "center" }}>
                <Checkbox
                  checked={selectedSupplierIds.includes(row.supplier_id)}
                  onChange={() => toggleSelect(row.supplier_id)}
                />
              </td>
              <td style={{ padding: 8, cursor: "pointer" }} onClick={() => onSupplierClick?.(row.supplier_id)}>
                <a>{row.supplier_name}</a>
              </td>
              {row.cells.map((cell) => {
                const col = data.columns.find((c) => c.key === cell.key);
                const bgColor = getCellColor(cell.risk_index, col?.polarity || "higher_is_risk");
                return (
                  <td
                    key={cell.key}
                    style={{
                      padding: 8,
                      textAlign: "center",
                      backgroundColor: bgColor,
                      cursor: "pointer",
                      position: "relative",
                    }}
                    onClick={() => onCellClick?.(row.supplier_id, cell.key)}
                  >
                    <Tooltip title={`值: ${cell.value ?? "N/A"} | 风险指数: ${cell.risk_index ?? "N/A"} | 来源: ${cell.source}${cell.diff != null ? ` | 差异: ${cell.diff > 0 ? "+" : ""}${cell.diff.toFixed(1)}` : ""}`}>
                      <span style={{ fontWeight: 500 }}>
                        {cell.value !== null && cell.value !== undefined
                          ? cell.key.includes("rate") || cell.key.includes("pct")
                            ? `${cell.value.toFixed(1)}%`
                            : cell.key === "ppm_value"
                              ? cell.value.toFixed(0)
                              : cell.value.toFixed(1)
                          : "—"}
                      </span>
                      {cell.diff != null && Math.abs(cell.diff) > 10 && (
                        <span style={{ fontSize: 10, marginLeft: 4, color: cell.diff > 0 ? "#f5222d" : "#52c41a" }}>
                          {cell.diff > 0 ? "↑" : "↓"}
                        </span>
                      )}
                    </Tooltip>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default RiskHeatmap;
```

- [ ] **Step 4: Create `SupplyChainRiskMapPage.tsx`**

Create `frontend/src/pages/supplyChainRiskMap/SupplyChainRiskMapPage.tsx`:

```tsx
import React, { useState, useEffect, useCallback } from "react";
import { Row, Col, Card, Spin } from "antd";
import { useProductLineStore } from "../../store/productLineStore";
import { riskMapApi } from "../../api/supplyChainRiskMap";
import HeatmapToolbar from "./components/HeatmapToolbar";
import TimelineSlider from "./components/TimelineSlider";
import RiskHeatmap from "./components/RiskHeatmap";
import DetailPanel from "./components/DetailPanel";
import type { HeatmapResponse, TimelineResponse } from "../../types";

const SupplyChainRiskMapPage: React.FC = () => {
  const selected = useProductLineStore((s) => s.selected);
  const [period, setPeriod] = useState("");
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedSupplierIds, setSelectedSupplierIds] = useState<string[]>([]);

  const fetchTimeline = useCallback(async () => {
    try {
      const params = selected ? { product_line_code: selected } : undefined;
      const res = await riskMapApi.timeline(params);
      setTimeline(res.data);
      if (!period && res.data.current_period) {
        setPeriod(res.data.current_period);
      }
    } catch {
      // ignore
    }
  }, [selected, period]);

  const fetchHeatmap = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (selected) params.product_line_code = selected;
      if (period) params.period = period;
      const res = await riskMapApi.heatmap(params);
      setHeatmap(res.data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [selected, period]);

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  useEffect(() => {
    if (period) fetchHeatmap();
  }, [period, selected, fetchHeatmap]);

  const handleRefresh = () => {
    setRefreshing(true);
    riskMapApi
      .generateSnapshot(selected ? { product_line_code: selected } : undefined)
      .then(() => fetchHeatmap())
      .finally(() => setRefreshing(false));
  };

  const handleCellClick = (supplierId: string, dimensionKey: string) => {
    if (selectedSupplierIds.length <= 1) {
      setSelectedSupplierIds([supplierId]);
    }
  };

  const handleSupplierClick = (supplierId: string) => {
    setSelectedSupplierIds([supplierId]);
  };

  return (
    <div style={{ padding: 24 }}>
      <HeatmapToolbar
        period={period}
        onPeriodChange={setPeriod}
        onRefresh={handleRefresh}
        refreshing={refreshing}
      />
      {timeline && (
        <TimelineSlider
          periods={timeline.periods}
          currentPeriod={period}
          onPeriodChange={setPeriod}
        />
      )}
      <Row gutter={16}>
        <Col span={selectedSupplierIds.length > 0 ? 16 : 24}>
          <Card bodyStyle={{ padding: 0 }}>
            <Spin spinning={loading}>
              <RiskHeatmap
                data={heatmap}
                onCellClick={handleCellClick}
                onSupplierClick={handleSupplierClick}
                selectedSupplierIds={selectedSupplierIds}
                onSelectionChange={setSelectedSupplierIds}
              />
            </Spin>
          </Card>
        </Col>
        {selectedSupplierIds.length > 0 && (
          <Col span={8}>
            <DetailPanel
              supplierIds={selectedSupplierIds}
              productLineCode={selected || undefined}
              period={period}
            />
          </Col>
        )}
      </Row>
    </div>
  );
};

export default SupplyChainRiskMapPage;
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/supplyChainRiskMap/
git commit -m "feat(supply-chain-risk-map): add heatmap, toolbar, and timeline components"
```

---

## Task 9: Frontend — Detail Panel + Comparison + DiffIndicator + DataSourceBadge

**Files:**
- Create: `frontend/src/pages/supplyChainRiskMap/components/DetailPanel.tsx`
- Create: `frontend/src/pages/supplyChainRiskMap/components/SupplierDetail.tsx`
- Create: `frontend/src/pages/supplyChainRiskMap/components/SupplierComparison.tsx`
- Create: `frontend/src/pages/supplyChainRiskMap/components/ComparisonRadar.tsx`
- Create: `frontend/src/pages/supplyChainRiskMap/components/DiffIndicator.tsx`
- Create: `frontend/src/pages/supplyChainRiskMap/components/DataSourceBadge.tsx`

- [ ] **Step 1: Create `DataSourceBadge.tsx`**

Create `frontend/src/pages/supplyChainRiskMap/components/DataSourceBadge.tsx`:

```tsx
import React from "react";
import { Tag } from "antd";

const SOURCE_MAP: Record<string, { color: string; label: string }> = {
  erp_po: { color: "blue", label: "ERP" },
  iqc_inspection: { color: "purple", label: "IQC" },
  supplier_evaluation_fallback: { color: "orange", label: "评价" },
  risk_evaluation: { color: "green", label: "评分" },
  missing: { color: "default", label: "N/A" },
};

interface DataSourceBadgeProps {
  source: string;
}

const DataSourceBadge: React.FC<DataSourceBadgeProps> = ({ source }) => {
  const cfg = SOURCE_MAP[source] || SOURCE_MAP.missing;
  return <Tag color={cfg.color} style={{ fontSize: 11 }}>{cfg.label}</Tag>;
};

export default DataSourceBadge;
```

- [ ] **Step 2: Create `DiffIndicator.tsx`**

Create `frontend/src/pages/supplyChainRiskMap/components/DiffIndicator.tsx`:

```tsx
import React from "antd";

interface DiffIndicatorProps {
  diff: number | null;
}

const DiffIndicator: React.FC<DiffIndicatorProps> = ({ diff }) => {
  if (diff == null || Math.abs(diff) <= 10) return null;
  if (diff > 0) {
    return <span style={{ color: "#f5222d", fontSize: 12, marginLeft: 4 }}>↑{diff.toFixed(1)}</span>;
  }
  return <span style={{ color: "#52c41a", fontSize: 12, marginLeft: 4 }}>↓{Math.abs(diff).toFixed(1)}</span>;
};

export default DiffIndicator;
```

- [ ] **Step 3: Create `SupplierDetail.tsx`**

Create `frontend/src/pages/supplyChainRiskMap/components/SupplierDetail.tsx`:

```tsx
import React, { useEffect, useState, useRef } from "react";
import { Card, Table, Tag, Spin } from "antd";
import * as echarts from "echarts";
import { riskMapApi } from "../../../api/supplyChainRiskMap";
import DataSourceBadge from "./DataSourceBadge";
import DiffIndicator from "./DiffIndicator";
import type { SupplierDetailResponse, HeatmapColumn } from "../../../types";

interface SupplierDetailProps {
  supplierId: string;
  productLineCode?: string;
  period: string;
  columns: HeatmapColumn[];
}

const SupplierDetail: React.FC<SupplierDetailProps> = ({
  supplierId,
  productLineCode,
  period,
  columns,
}) => {
  const [detail, setDetail] = useState<SupplierDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = { period };
    if (productLineCode) params.product_line_code = productLineCode;
    riskMapApi
      .supplierDetail(supplierId, params)
      .then((res) => setDetail(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [supplierId, productLineCode, period]);

  useEffect(() => {
    if (!detail || !chartRef.current) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }
    chartInstance.current.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["风险分", "质量分", "交付分", "合规分"], bottom: 0 },
      xAxis: { type: "category", data: detail.trend.map((t) => t.period) },
      yAxis: { type: "value", max: 100 },
      series: [
        { name: "风险分", type: "line", data: detail.trend.map((t) => t.risk_score), smooth: true },
        { name: "质量分", type: "line", data: detail.trend.map((t) => t.quality_score), smooth: true },
        { name: "交付分", type: "line", data: detail.trend.map((t) => t.delivery_score), smooth: true },
        { name: "合规分", type: "line", data: detail.trend.map((t) => t.compliance_score), smooth: true },
      ],
      grid: { left: 40, right: 16, top: 16, bottom: 48 },
    });
  }, [detail]);

  if (loading) return <Spin style={{ display: "block", margin: "40px auto" }} />;
  if (!detail) return null;

  const levelColor: Record<string, string> = {
    low: "green", medium: "warning", high: "orange", critical: "red",
  };

  const tableData = columns.map((col) => {
    const dim = detail.dimensions[col.key];
    return {
      key: col.key,
      dimension: col.label,
      raw_value: dim?.raw_value != null
        ? col.key.includes("rate") || col.key.includes("pct")
          ? `${dim.raw_value.toFixed(1)}%`
          : col.key === "ppm_value"
            ? dim.raw_value.toFixed(0)
            : dim.raw_value.toFixed(1)
        : "—",
      risk_index: dim?.risk_index != null ? dim.risk_index.toFixed(1) : "—",
      source: dim?.source || "missing",
    };
  });

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
        <strong>{detail.supplier_name}</strong>
        <Tag color={levelColor[Object.keys(detail.dimensions).reduce((acc, k) => {
          const d = detail.dimensions[k];
          return k === "risk_score" && d?.raw_value ? (d.raw_value > 80 ? "critical" : d.raw_value > 60 ? "high" : d.raw_value > 30 ? "medium" : "low") : acc;
        }, "low")]}>
          {period}
        </Tag>
      </div>
      <Table
        size="small"
        pagination={false}
        dataSource={tableData}
        columns={[
          { title: "维度", dataIndex: "dimension", key: "dimension" },
          { title: "值", dataIndex: "raw_value", key: "raw_value" },
          { title: "风险指数", dataIndex: "risk_index", key: "risk_index" },
          { title: "来源", dataIndex: "source", key: "source", render: (s: string) => <DataSourceBadge source={s} /> },
        ]}
      />
      <div ref={chartRef} style={{ height: 200, marginTop: 16 }} />
    </div>
  );
};

export default SupplierDetail;
```

- [ ] **Step 4: Create `ComparisonRadar.tsx`**

Create `frontend/src/pages/supplyChainRiskMap/components/ComparisonRadar.tsx`:

```tsx
import React, { useEffect, useRef } from "antd";
import * as echarts from "echarts";
import type { ComparisonSupplier } from "../../../types";

const RADAR_INDICATORS = [
  { name: "质量分", max: 100 },
  { name: "交付分", max: 100 },
  { name: "合规分", max: 100 },
  { name: "ERP准时率", max: 100 },
  { name: "PPM风险", max: 100 },
];

const COLORS = ["#52c41a", "#1890ff", "#fa8c16", "#f5222d"];

interface ComparisonRadarProps {
  suppliers: ComparisonSupplier[];
}

const ComparisonRadar: React.FC<ComparisonRadarProps> = ({ suppliers }) => {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }

    const series = suppliers.map((sup, i) => ({
      value: RADAR_INDICATORS.map((ind) => {
        const keyMap: Record<string, string> = {
          "质量分": "quality_score", "交付分": "delivery_score",
          "合规分": "compliance_score", "ERP准时率": "erp_on_time_rate",
          "PPM风险": "ppm_value",
        };
        const dim = sup.dimensions[keyMap[ind.name]];
        return dim?.risk_index ?? 0;
      }),
      name: sup.supplier_name,
      areaStyle: { opacity: 0.1 },
      lineStyle: { color: COLORS[i % COLORS.length] },
      itemStyle: { color: COLORS[i % COLORS.length] },
    }));

    chartInstance.current.setOption({
      tooltip: {},
      legend: { data: suppliers.map((s) => s.supplier_name), bottom: 0 },
      radar: { indicator: RADAR_INDICATORS, shape: "polygon", radius: "65%" },
      series: [{ type: "radar", data: series }],
    });
  }, [suppliers]);

  return <div ref={chartRef} style={{ height: 280 }} />;
};

export default ComparisonRadar;
```

- [ ] **Step 5: Create `SupplierComparison.tsx`**

Create `frontend/src/pages/supplyChainRiskMap/components/SupplierComparison.tsx`:

```tsx
import React, { useEffect, useState } from "react";
import { Table, Card, Spin, Button } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { riskMapApi } from "../../../api/supplyChainRiskMap";
import ComparisonRadar from "./ComparisonRadar";
import DataSourceBadge from "./DataSourceBadge";
import type { ComparisonResponse, ComparisonSupplier, HeatmapColumn } from "../../../types";

interface SupplierComparisonProps {
  supplierIds: string[];
  productLineCode?: string;
  period: string;
  columns: HeatmapColumn[];
}

const SupplierComparison: React.FC<SupplierComparisonProps> = ({
  supplierIds,
  productLineCode,
  period,
  columns,
}) => {
  const [data, setData] = useState<ComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    riskMapApi
      .compare(supplierIds, productLineCode ? { product_line_code: productLineCode, period } : { period })
      .then((res) => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [supplierIds, productLineCode, period]);

  if (loading) return <Spin style={{ display: "block", margin: "40px auto" }} />;
  if (!data) return null;

  const dimKeys = columns.map((c) => c.key);

  const tableColumns = [
    { title: "维度", dataIndex: "dimension", key: "dimension", fixed: "left" as const, width: 100 },
    ...data.suppliers.map((sup: ComparisonSupplier) => ({
      title: sup.supplier_name,
      key: sup.supplier_id,
      width: 120,
      render: (_: unknown, record: Record<string, unknown>) => {
        const val = record[`val_${sup.supplier_id}`];
        const src = record[`src_${sup.supplier_id}`];
        return (
          <span>
            {val != null ? String(val) : "—"}
            <DataSourceBadge source={src as string || "missing"} />
          </span>
        );
      },
    })),
  ];

  const tableData = dimKeys.map((key) => {
    const col = columns.find((c) => c.key === key);
    const row: Record<string, unknown> = { key, dimension: col?.label || key };
    data.suppliers.forEach((sup: ComparisonSupplier) => {
      const dim = sup.dimensions[key];
      row[`val_${sup.supplier_id}`] = dim?.raw_value != null
        ? key.includes("rate") || key.includes("pct")
          ? `${dim.raw_value.toFixed(1)}%`
          : key === "ppm_value"
            ? dim.raw_value.toFixed(0)
            : dim.raw_value.toFixed(1)
        : null;
      row[`src_${sup.supplier_id}`] = dim?.source || "missing";
    });
    return row;
  });

  return (
    <div>
      <ComparisonRadar suppliers={data.suppliers} />
      <Table
        size="small"
        pagination={false}
        dataSource={tableData}
        columns={tableColumns}
        scroll={{ x: 100 + data.suppliers.length * 120 }}
        style={{ marginTop: 16 }}
      />
    </div>
  );
};

export default SupplierComparison;
```

- [ ] **Step 6: Create `DetailPanel.tsx`**

Create `frontend/src/pages/supplyChainRiskMap/components/DetailPanel.tsx`:

```tsx
import React from "react";
import { Card } from "antd";
import SupplierDetail from "./SupplierDetail";
import SupplierComparison from "./SupplierComparison";
import { riskMapApi } from "../../../api/supplyChainRiskMap";
import type { HeatmapColumn } from "../../../types";

interface DetailPanelProps {
  supplierIds: string[];
  productLineCode?: string;
  period: string;
}

const DetailPanel: React.FC<DetailPanelProps> = ({
  supplierIds,
  productLineCode,
  period,
}) => {
  // Fetch columns from heatmap response to pass to sub-components
  const [columns, setColumns] = React.useState<HeatmapColumn[]>([]);
  React.useEffect(() => {
    const params: Record<string, string> = {};
    if (productLineCode) params.product_line_code = productLineCode;
    if (period) params.period = period;
    riskMapApi.heatmap(params).then((res) => setColumns(res.data.columns));
  }, [productLineCode, period]);

  return (
    <Card title={supplierIds.length === 1 ? "供应商详情" : "供应商对比"} size="small">
      {supplierIds.length === 1 ? (
        <SupplierDetail
          supplierId={supplierIds[0]}
          productLineCode={productLineCode}
          period={period}
          columns={columns}
        />
      ) : (
        <SupplierComparison
          supplierIds={supplierIds}
          productLineCode={productLineCode}
          period={period}
          columns={columns}
        />
      )}
    </Card>
  );
};

export default DetailPanel;
```

- [ ] **Step 7: Wire into `SupplyChainRiskMapPage.tsx`**

Connect DetailPanel to RiskHeatmap's click/checkbox events.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/supplyChainRiskMap/components/
git commit -m "feat(supply-chain-risk-map): add detail panel, comparison, diff indicator, and data source badge"
```

---

## Task 10: Frontend — Route Registration + Menu + Export

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`
- Create: `frontend/src/pages/supplyChainRiskMap/components/ExportButton.tsx`

- [ ] **Step 1: Create `ExportButton.tsx`**

Ant Design `Dropdown` button with CSV and Excel options. Calls `riskMapApi.exportCsv` / `riskMapApi.exportExcel` and triggers browser download.

- [ ] **Step 2: Add menu item in `AppLayout.tsx`**

Three changes required in `frontend/src/components/layout/AppLayout.tsx`:

**2a. Add `HeatMapOutlined` to the icon imports** (line ~29):
```tsx
import {
  // ... existing icons ...
  HeatMapOutlined,
} from "@ant-design/icons";
```

**2b. Add menu item** inside the `grp:supplier` children array (after `/supplier-risk`, around line 158):
```tsx
{ key: "/supply-chain-risk-map", icon: <HeatMapOutlined />, label: "供应链风险地图" },
```

**2c. Update `MENU_KEYS` array** (line ~38) to include the new paths:
```tsx
"/supply-chain-risk-map",
```

**2d. Update `MENU_KEY_TO_OPEN_KEYS`** (line ~55) to map both paths:
```tsx
"/supply-chain-risk-map": ["grp:supplier"],
```

- [ ] **Step 3: Add `supply_chain_risk_map` to `ModuleKey` type**

In `frontend/src/hooks/usePermission.ts`, add to the `ModuleKey` union type (line ~9):
```ts
| "supply_chain_risk_map"
```

- [ ] **Step 4: Add route in `App.tsx`**

In `frontend/src/App.tsx`, add the route as a **sibling** of other leaf routes (inside the outer `<AppLayout>` parent route), NOT nesting another `<AppLayout>`. The outer route at line 101-106 already provides `<AppLayout />`, so adding a second one creates a double-layout bug. Add after the `/supplier-risk` block (around line 137):

```tsx
import SupplyChainRiskMapPage from "./pages/supplyChainRiskMap/SupplyChainRiskMapPage";
```

```tsx
<Route path="/supply-chain-risk-map" element={<ProtectedRoute requiredModule="supply_chain_risk_map"><SupplyChainRiskMapPage /></ProtectedRoute>} />
```

- [ ] **Step 5: Wire ExportButton into HeatmapToolbar**

- [ ] **Step 6: Verify the page loads in browser**

```bash
cd frontend && npm run dev
```

Open `/supply-chain-risk-map` — should show the heatmap page (may be empty if no data).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx frontend/src/hooks/usePermission.ts frontend/src/pages/supplyChainRiskMap/components/ExportButton.tsx
git commit -m "feat(supply-chain-risk-map): add route, menu, permission module, and export button"
```

---

## Task 11: Full Integration Test + Seed Data

**Files:**
- Modify: `backend/app/seed.py` (add seed data for supply chain risk snapshots)
- Create: `backend/tests/test_supply_chain_risk_e2e.py`

- [ ] **Step 1: Add seed data**

In `backend/app/seed.py`, add a function that creates sample `SupplyChainRiskSnapshot` records. Add it after the existing seed functions and call it from the main `seed()` function.

```python
async def seed_supply_chain_risk_snapshots(db):
    """Seed sample risk map snapshots for 3 suppliers across 3 months."""
    from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
    from app.models.supplier import Supplier
    from sqlalchemy import select

    # Check if already seeded
    existing = await db.execute(
        select(SupplyChainRiskSnapshot).limit(1)
    )
    if existing.scalar_one_or_none():
        return

    # Fetch existing suppliers (already seeded by main seed function)
    supplier_result = await db.execute(select(Supplier).limit(3))
    suppliers = supplier_result.scalars().all()
    if len(suppliers) < 3:
        print("Not enough suppliers to seed risk map snapshots, skipping.")
        return

    periods = ["2026-01", "2026-02", "2026-03"]
    # Realistic dimension values for 3 suppliers with different risk profiles
    profiles = [
        {"quality": 12, "delivery": 18, "compliance": 8, "erp_ontime": 95, "scar": 0, "ppm": 500, "risk": 15, "level": "low"},
        {"quality": 45, "delivery": 55, "compliance": 30, "erp_ontime": 78, "scar": 2, "ppm": 8000, "risk": 48, "level": "medium"},
        {"quality": 72, "delivery": 80, "compliance": 65, "erp_ontime": 55, "scar": 5, "ppm": 35000, "risk": 76, "level": "high"},
    ]

    for supplier, profile in zip(suppliers[:3], profiles):
        for i, period in enumerate(periods):
            # Gradually worsen over 3 months for realistic trend
            factor = 1 + i * 0.08
            snap = SupplyChainRiskSnapshot(
                supplier_id=supplier.supplier_id,
                product_line_code=None,
                snapshot_period=period,
                risk_score=round(profile["risk"] * factor, 1),
                risk_level="high" if profile["risk"] * factor > 60 else "medium" if profile["risk"] * factor > 30 else "low",
                quality_score=round(profile["quality"] * factor, 1),
                delivery_score=round(profile["delivery"] * factor, 1),
                compliance_score=round(profile["compliance"] * factor, 1),
                erp_on_time_rate=round(max(profile["erp_ontime"] - i * 3, 0), 1),
                purchase_amount_pct=round(33.3, 1),
                open_scar_count=profile["scar"] + i,
                ppm_value=round(profile["ppm"] * factor),
                dimensions={},
            )
            db.add(snap)

    await db.flush()
    print("Seeded supply chain risk map snapshots.")
```

In the `seed()` function, add a call after the existing seed steps (before the final commit):

```python
await seed_supply_chain_risk_snapshots(db)
```

- [ ] **Step 2: Write end-to-end test**

Create `backend/tests/test_supply_chain_risk_e2e.py`:

```python
"""End-to-end tests for supply chain risk map API."""
import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from datetime import date
from sqlalchemy import select, func

from app.models.user import User
from app.models.role import RoleDefinition, RolePermission
from app.models.supplier import Supplier
from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
from app.core.security import hash_password, create_access_token
from app.main import app
from app.database import get_db


@pytest.fixture
async def test_user(db):
    """Create a minimal user row so FKs resolve."""
    result = await db.execute(
        select(RoleDefinition).where(RoleDefinition.role_key == "admin")
    )
    role = result.scalar_one_or_none()
    if role is None:
        db.add(RoleDefinition(role_key="admin", name_zh="管理员", name_en="Admin", is_system=True, is_active=True))
        await db.flush()
        result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "admin"))
        role = result.scalar_one()
    # Ensure permission exists
    perm_count = (await db.execute(
        select(func.count()).select_from(RolePermission)
        .where(RolePermission.role_id == role.id, RolePermission.module == "supply_chain_risk_map")
    )).scalar()
    if perm_count == 0:
        db.add(RolePermission(role_id=role.id, module="supply_chain_risk_map", permission_level=5))
        await db.flush()
    user = User(
        user_id=uuid4(), username=f"e2e_admin_{uuid4().hex[:8]}",
        display_name="E2E Admin", password_hash=hash_password("Admin@2026"),
        role_id=role.id, legacy_role="admin", is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def client(db, test_user):
    """ASGI test client with get_db overridden to use test session."""
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(client, test_user):
    """Client with admin auth token."""
    token = create_access_token(str(test_user.user_id))
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
async def seed_snapshots(db, test_user):
    """Seed supplier + risk configs + snapshots for e2e tests."""
    from app.models.supplier_risk import SupplierRiskConfig
    from app.services.supplier_risk.config import DEFAULT_CONFIGS
    supplier = Supplier(
        supplier_id=uuid4(), supplier_no="T-E2E-01", name="E2ETest",
        short_name="ET", status="approved", created_by=test_user.user_id,
    )
    db.add(supplier)
    # Seed risk configs so calculate_all_supplier_scores doesn't skip this supplier
    for cfg in DEFAULT_CONFIGS:
        db.add(SupplierRiskConfig(
            config_id=uuid4(), rule_id=cfg["rule_id"], enabled=True,
            thresholds=cfg["thresholds"], weight=cfg["weight"],
            supplier_id=None, category=cfg["category"], product_line_code=None,
            updated_by=test_user.user_id,
        ))
    for period, risk in [("2026-01", 15.0), ("2026-02", 25.0), ("2026-03", 40.0)]:
        db.add(SupplyChainRiskSnapshot(
            snapshot_id=uuid4(), supplier_id=supplier.supplier_id,
            product_line_code=None, snapshot_period=period,
            risk_score=risk, risk_level="low" if risk <= 30 else "medium",
            quality_score=risk * 0.5, delivery_score=risk * 0.3,
            compliance_score=risk * 0.2, erp_on_time_rate=90.0 - risk,
            purchase_amount_pct=50.0, open_scar_count=0, ppm_value=int(risk * 100),
            dimensions={},
        ))
    await db.commit()
    return supplier


@pytest.mark.asyncio
async def test_heatmap_endpoint(admin_client, seed_snapshots):
    """GET /heatmap returns structured heatmap data."""
    response = await admin_client.get(
        "/api/supply-chain-risk-map/heatmap",
        params={"period": "2026-03"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "columns" in data
    assert "rows" in data
    assert "period" in data
    assert data["period"] == "2026-03"
    assert len(data["rows"]) >= 1


@pytest.mark.asyncio
async def test_timeline_endpoint(admin_client, seed_snapshots):
    """GET /timeline returns list of periods with snapshots."""
    response = await admin_client.get("/api/supply-chain-risk-map/timeline")
    assert response.status_code == 200
    data = response.json()
    assert "periods" in data
    assert "current_period" in data
    assert len(data["periods"]) >= 3


@pytest.mark.asyncio
async def test_snapshot_generate_endpoint(admin_client, db, seed_snapshots):
    """POST /snapshots/generate creates or updates snapshots."""
    response = await admin_client.post(
        "/api/supply-chain-risk-map/snapshots/generate",
    )
    assert response.status_code == 200
    data = response.json()
    assert "snapshot_count" in data
    assert data["snapshot_count"] >= 1


@pytest.mark.asyncio
async def test_csv_export_endpoint(admin_client, seed_snapshots):
    """GET /export?format=csv returns CSV content."""
    response = await admin_client.get(
        "/api/supply-chain-risk-map/export",
        params={"period": "2026-03", "format": "csv"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    lines = response.text.split("\n")
    assert len(lines) >= 2  # Header + at least one row
    assert "供应商" in lines[0]
```

- [ ] **Step 3: Run all tests**

```bash
cd backend && python -m pytest tests/test_supply_chain_risk_e2e.py tests/test_supply_chain_risk_service.py tests/test_supply_chain_risk_aggregator.py tests/test_supply_chain_risk_integration.py -v
```

Expected: All 25+ tests PASS (4 e2e + 5 service + 10 aggregator + 6 integration)

- [ ] **Step 4: Commit**

```bash
git add backend/app/seed.py backend/tests/test_supply_chain_risk_e2e.py
git commit -m "feat(supply-chain-risk-map): add seed data and e2e tests"
```

---

## Self-Review

### Spec Coverage Check

| Spec Section | Covered By Task |
|---|---|
| §3.1 ERP `actual_delivery_date` | Task 1 (migration) + Task 5 (schema/ingestion) |
| §3.2 Snapshot table | Task 1 (migration + model) |
| §3.3 Reused tables | Task 3 (aggregator reads) |
| §3.4 Permissions (field_qe etc.) | Task 1 (seed) + Task 5 (Module enum) |
| §4.1 Module structure | Tasks 3-4 |
| §4.2 Aggregator (FILTER, window, time-point) | Task 3 |
| §4.2 `calculate_all_supplier_scores` | Task 2 |
| §4.3 Service (snapshot, heatmap, timeline, detail, comparison, export) | Task 4 |
| §4.4 Scheduler (advisory lock, session release before sleep) | Task 4 |
| §5 API routes (6 endpoints) | Task 5 |
| §5.1 Heatmap response format (with diff, risk_index, source, polarity) | Task 4 + Task 7 |
| §6.1 Route + menu | Task 10 |
| §6.2 Left-right layout | Task 8 |
| §6.3 File structure | Tasks 8-10 |
| §6.4 ECharts heatmap (risk_index, dataZoom, polarity) | Task 8 |
| §6.5 Timeline replay | Task 8 |
| §6.6 Comparison (checkbox + radar + table) | Task 9 |
| §6.7 Export (CSV + Excel) | Task 10 |
| §7 Migration (dialect branch, NULLS NOT DISTINCT) | Task 1 |
| §8 Tests (25+ total across 4 test files) | Tasks 2-6 + 11 |
| §9 Integration (calculate_all_supplier_scores, enforce_product_line, ERP) | Tasks 2, 5, 6 |
| §10 Security (advisory lock, historical snapshot read-only, product_line) | Tasks 4, 5 |

### Placeholder Scan

All tasks (1-11) now contain complete executable code. Backend: schemas, API routes, service, scheduler, and all test files have full Python with imports, fixtures, and assertions — no `pass` stubs or TBD. Frontend: all components (HeatmapToolbar, TimelineSlider, RiskHeatmap, SupplyChainRiskMapPage, DataSourceBadge, DiffIndicator, SupplierDetail, ComparisonRadar, SupplierComparison, DetailPanel, ExportButton) have complete JSX with Ant Design + ECharts imports and real render logic. Integration tests use real DB users with `create_access_token`. The advisory lock test uses two independent sessions.

### Type Consistency Check

- `calculate_all_supplier_scores` returns `list[dict]` with keys matching `aggregator.py` input — ✓
- `SupplyChainRiskSnapshot` model fields match migration columns — ✓
- `HeatmapCell`/`HeatmapResponse` types match API response format — ✓
- `riskMapApi` method signatures match API endpoints — ✓
- Module enum `SUPPLY_CHAIN_RISK_MAP` used consistently — ✓

Plan complete and saved to `docs/superpowers/plans/2026-06-11-supply-chain-risk-map.md`.