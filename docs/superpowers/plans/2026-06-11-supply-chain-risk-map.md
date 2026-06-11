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
└── test_supply_chain_risk_map.py       # CREATE: 27 tests

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
from sqlalchemy.dialects.postgresql import UUID

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
        sa.Column("dimensions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 3. Unique constraint — NULLS NOT DISTINCT (PostgreSQL 15+)
    # NOTE: This migration is PostgreSQL-only. The sa.JSON column type and
    # NULLS NOT DISTINCT constraint both require PG. SQLite tests must use
    # separate model definitions with sa.JSON and standard unique constraint,
    # and must test NULL dedup at the application layer since SQLite unique
    # constraints don't enforce uniqueness on NULL columns.
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

from sqlalchemy import String, Float, Integer, DateTime, Date, ForeignKey, func, text, JSON
from sqlalchemy.dialects.postgresql import UUID
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
    dimensions: Mapped[dict] = mapped_column(JSON, nullable=False, server_default="{}")
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


@pytest.mark.asyncio
async def test_calculate_all_supplier_scores_returns_scores_without_side_effects(db):
    """calculate_all_supplier_scores should return scores for all suppliers
    including low-risk ones, without creating alerts or committing."""
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierRiskConfig, SupplierRiskAlert

    # Create an approved supplier
    user_id = uuid4()
    supplier = Supplier(
        supplier_id=uuid4(),
        supplier_no="TEST-SCRM-001",
        name="Test Supplier SCRM",
        short_name="Test SCRM",
        status="approved",
        created_by=user_id,
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
            updated_by=user_id,
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


@pytest.mark.asyncio
async def test_erp_on_time_rate_with_filter(db):
    """ERP on-time rate uses FILTER (WHERE actual_delivery_date <= delivery_date)."""
    from app.models.supplier import Supplier
    from app.models.erp import ERPPurchaseOrder, ERPConnection

    # Seed: approved supplier, ERP connection, POs with actual_delivery_date
    conn_id = uuid4()
    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-ONT-01", name="OntimeTest",
                         short_name="OT", status="approved", created_by=uuid4())
    db.add(supplier)
    erp_conn = ERPConnection(connection_id=conn_id, name="test_conn", connector_type="mock",
                               is_active=True, created_by=uuid4())
    db.add(erp_conn)
    # 3 POs: 2 on-time (actual <= delivery), 1 late
    for i, (ad, dd) in enumerate([
        (date(2026, 6, 1), date(2026, 6, 5)),  # on-time
        (date(2026, 6, 3), date(2026, 6, 5)),  # on-time
        (date(2026, 6, 10), date(2026, 6, 5)),  # late
    ]):
        db.add(ERPPurchaseOrder(
            po_id=uuid4(), connection_id=conn_id, external_id=f"PO-{i}",
            po_number=f"PO-2026-{i:03d}", line_number="1",
            supplier_code="SUP-01", delivery_date=dd,
            actual_delivery_date=ad, quantity=100, unit_price=10,
            status="completed", product_line_code=None,
        ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    assert metrics["erp_on_time_rate"] == pytest.approx(66.67, rel=0.01)
    assert metrics["erp_on_time_rate_source"] == "erp_po"


@pytest.mark.asyncio
async def test_erp_fallback_to_evaluation(db):
    """When no PO data, fall back to supplier_evaluations.delivery_score."""
    from app.models.supplier import Supplier
    from app.models.supplier import SupplierEvaluation

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-FB-01", name="FallbackTest",
                         short_name="FB", status="approved", created_by=uuid4())
    db.add(supplier)
    db.add(SupplierEvaluation(
        eval_id=uuid4(), supplier_id=supplier.supplier_id,
        eval_period="2026-06", eval_type="monthly",
        quality_score=80, delivery_score=75, service_score=70,
        capa_count=0, finding_count=0, premium_freight_count=0,
        customer_disruption_count=0, capa_penalty=0, finding_penalty=0,
        premium_freight_penalty=0, customer_disruption_penalty=0,
        total_score=75, grade="B", notes="fallback test",
        evaluated_by=uuid4(),
    ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    assert metrics["erp_on_time_rate"] == 75.0
    assert metrics["erp_on_time_rate_source"] == "supplier_evaluation_fallback"


@pytest.mark.asyncio
async def test_purchase_amount_pct_window_function(db):
    """Purchase amount % uses SUM(SUM(...)) OVER () window function."""
    from app.models.supplier import Supplier
    from app.models.erp import ERPPurchaseOrder, ERPConnection

    conn_id = uuid4()
    s1 = Supplier(supplier_id=uuid4(), supplier_no="T-PCT-01", name="PctTest1",
                    short_name="P1", status="approved", created_by=uuid4())
    s2 = Supplier(supplier_id=uuid4(), supplier_no="T-PCT-02", name="PctTest2",
                    short_name="P2", status="approved", created_by=uuid4())
    db.add_all([s1, s2])
    erp_conn = ERPConnection(connection_id=conn_id, name="test_conn", connector_type="mock",
                               is_active=True, created_by=uuid4())
    db.add(erp_conn)
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
async def test_ppm_calculation_with_period_filter(db):
    """PPM aggregates only inspections in the snapshot period."""
    from app.models.supplier import Supplier
    from app.models.iqc_inspection import IqcInspection
    from app.models.product_line import ProductLine

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-PPM-01", name="PPMTest",
                         short_name="PT", status="approved", created_by=uuid4())
    db.add(supplier)
    # Create inspections in June (should be counted) and May (should not)
    for month, result in [(6, "rejected"), (6, "rejected"), (6, "accepted"), (5, "rejected")]:
        db.add(IqcInspection(
            inspection_id=uuid4(), supplier_id=supplier.supplier_id,
            inspection_date=date(2026, month, 15),
            inspection_result=result, status="judged",
            product_line_code=None,
        ))
    await db.commit()

    result = await aggregate_supply_chain_metrics(db, [supplier.supplier_id], None, "2026-06")
    metrics = result[supplier.supplier_id]
    # 2 rejected out of 3 in June = 666667 PPM (2/3 * 1M), but only June counts
    assert metrics["ppm_value"] is not None
    assert metrics["ppm_source"] == "iqc_inspection"


@pytest.mark.asyncio
async def test_open_scar_count_time_point_logic(db):
    """SCAR count uses time-point: created_at <= period_end AND (closed_date IS NULL OR closed_date > period_end)."""
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierSCAR

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-SCAR-01", name="SCARTest",
                         short_name="ST", status="approved", created_by=uuid4())
    db.add(supplier)
    period_end = date(2026, 6, 30)
    # SCAR opened before period end, still open — counted
    db.add(SupplierSCAR(
        scar_id=uuid4(), scar_no="SCAR-2026-001", supplier_id=supplier.supplier_id,
        source_type="internal", description="open scar",
        status="open", issued_date=date(2026, 6, 10),
    ))
    # SCAR opened before period end, closed after period end — counted (was open at period end)
    db.add(SupplierSCAR(
        scar_id=uuid4(), scar_no="SCAR-2026-002", supplier_id=supplier.supplier_id,
        source_type="internal", description="closed after period",
        status="closed", issued_date=date(2026, 6, 5), closed_date=date(2026, 7, 15),
    ))
    # SCAR opened after period end — NOT counted
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

Expected: All 10 tests PASS

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


@pytest.fixture
async def seed_supplier(db):
    """Create an approved supplier with global default configs."""
    from app.models.supplier_risk import SupplierRiskConfig
    from app.services.supplier_risk.config import DEFAULT_CONFIGS
    user_id = uuid4()
    supplier = Supplier(
        supplier_id=uuid4(), supplier_no="T-SNAP-01", name="SnapshotTest",
        short_name="ST", status="approved", created_by=user_id,
    )
    db.add(supplier)
    for cfg in DEFAULT_CONFIGS:
        db.add(SupplierRiskConfig(
            config_id=uuid4(), rule_id=cfg["rule_id"], enabled=True,
            thresholds=cfg["thresholds"], weight=cfg["weight"],
            supplier_id=None, category=cfg["category"], product_line_code=None,
            updated_by=user_id,
        ))
    await db.commit()
    return supplier


@pytest.mark.asyncio
async def test_generate_snapshot_upsert(db, seed_supplier):
    """Generating snapshot twice for the same month overwrites (UPSERT)."""
    from app.services.supply_chain_risk_map.service import generate_snapshot
    count1 = await generate_snapshot(db, None, "2026-06")
    assert count1 >= 1
    count2 = await generate_snapshot(db, None, "2026-06")
    # Second call should UPSERT, not add new rows
    total = (await db.execute(
        select(func.count()).select_from(SupplyChainRiskSnapshot)
        .where(SupplyChainRiskSnapshot.snapshot_period == "2026-06")
    )).scalar()
    assert total == count1  # No duplicate rows


@pytest.mark.asyncio
async def test_product_line_isolation(db, seed_supplier):
    """Different product_line_code creates independent snapshots."""
    from app.services.supply_chain_risk_map.service import generate_snapshot
    await generate_snapshot(db, None, "2026-06")
    await generate_snapshot(db, "DC-DC-100", "2026-06")
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
    await generate_snapshot(db, None, "2026-06")
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

Create `backend/app/services/supply_chain_risk_map/service.py` with:
- `generate_snapshot(db, product_line_code, period) -> int` — calls `calculate_all_supplier_scores` + `aggregate_supply_chain_metrics`, normalizes, UPSERTs into `supply_chain_risk_snapshots`. Only allows `current_period()`.
- `get_heatmap_data(db, product_line_code, period) -> HeatmapResponse` — queries snapshot + previous month for diff
- `get_timeline(db, product_line_code) -> TimelineResponse`
- `get_supplier_detail(db, supplier_id, product_line_code, period) -> SupplierDetailResponse`
- `get_comparison(db, supplier_ids, period) -> ComparisonResponse`
- `export_heatmap(db, product_line_code, period, format) -> StreamingResponse` — CSV or Excel (openpyxl) with conditional formatting

- [ ] **Step 4: Implement `scheduler.py`**

Create `backend/app/services/supply_chain_risk_map/scheduler.py` with:
- `_acquire_snapshot_lock(db)` / `_release_snapshot_lock(db)` — `pg_try_advisory_lock(20260611)` / `pg_advisory_unlock(20260611)`
- `snapshot_loop()` — async while-true with advisory lock + `async with async_session()` (session released before sleep)

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_supply_chain_risk_service.py -v
```

Expected: All 10 tests PASS

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

Create `backend/app/schemas/supply_chain_risk_map.py` with:
- `HeatmapCell`: key, value, risk_index, level, diff, source
- `HeatmapColumn`: key, label, type, polarity
- `HeatmapRow`: supplier_id, supplier_name, cells
- `HeatmapResponse`: period, prev_period, product_line_code, columns, rows
- `TimelineResponse`: periods, current_period, supplier_count
- `SupplierDetailResponse`: supplier info + dimensions + 6-month trend
- `ComparisonResponse`: list of suppliers with dimensions side-by-side
- `SnapshotGenerateResponse`: snapshot_count, period

- [ ] **Step 2: Create API routes**

Create `backend/app/api/supply_chain_risk_map.py` with routes per spec Section 5:
- `GET /supply-chain-risk-map/heatmap` (VIEW)
- `GET /supply-chain-risk-map/timeline` (VIEW)
- `GET /supply-chain-risk-map/suppliers/{id}` (VIEW)
- `POST /supply-chain-risk-map/suppliers/compare` (VIEW)
- `POST /supply-chain-risk-map/snapshots/generate` (EDIT)
- `GET /supply-chain-risk-map/export` (VIEW)

All routes use `require_permission(Module.SUPPLY_CHAIN_RISK_MAP, ...)` and `enforce_product_line_access`.

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
from app.core.security import get_password_hash, create_access_token


@pytest.fixture
async def admin_user(db):
    """Create a real admin user in DB and return the user object."""
    user = User(
        user_id=uuid4(), username="test_admin_riskmap",
        email="admin_riskmap@test.com",
        hashed_password=get_password_hash("Admin@2026"),
        role="admin", is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def viewer_user(db):
    """Create a real viewer user in DB."""
    user = User(
        user_id=uuid4(), username="test_viewer_riskmap",
        email="viewer_riskmap@test.com",
        hashed_password=get_password_hash("Viewer@2026"),
        role="viewer", is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def admin_client(client: AsyncClient, admin_user):
    """Client with real admin user token."""
    token = create_access_token({"sub": str(admin_user.user_id)})
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
async def viewer_client(client: AsyncClient, viewer_user):
    """Client with real viewer user token."""
    token = create_access_token({"sub": str(viewer_user.user_id)})
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.mark.asyncio
async def test_csv_export_contains_source_column(admin_client, db):
    """CSV export includes a 'source' column for each dimension."""
    from app.services.supply_chain_risk_map.service import generate_snapshot
    from app.database import async_session
    async with async_session() as session:
        await generate_snapshot(session, None, "2026-06")
    response = await admin_client.get(
        "/api/supply-chain-risk-map/export",
        params={"period": "2026-06", "format": "csv"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    lines = response.text.split("\n")
    assert any("source" in line.lower() for line in lines[:2])


@pytest.mark.asyncio
async def test_viewer_cannot_generate_snapshot(viewer_client):
    """Viewer role gets 403 on snapshot generate endpoint."""
    response = await viewer_client.post("/api/supply-chain-risk-map/snapshots/generate")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_field_qe_has_edit_permission(db, client):
    """field_qe role can generate snapshots (EDIT level)."""
    user = User(
        user_id=uuid4(), username="test_fqe_riskmap",
        email="fqe_riskmap@test.com",
        hashed_password=get_password_hash("Fqe@2026"),
        role="field_qe", is_active=True,
    )
    db.add(user)
    await db.commit()
    token = create_access_token({"sub": str(user.user_id)})
    response = await client.post(
        "/api/supply-chain-risk-map/snapshots/generate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 403  # Not forbidden


@pytest.mark.asyncio
async def test_nulls_not_distinct_prevents_duplicate_snapshot(db):
    """UNIQUE NULLS NOT DISTINCT constraint prevents duplicate snapshots (PG-only)."""
    from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
    from app.models.supplier import Supplier
    from sqlalchemy.exc import IntegrityError

    supplier = Supplier(supplier_id=uuid4(), supplier_no="T-DUP-01", name="DupeTest",
                         short_name="DT", status="approved", created_by=uuid4())
    db.add(supplier)
    await db.commit()

    s1 = SupplyChainRiskSnapshot(
        snapshot_id=uuid4(), supplier_id=supplier.supplier_id,
        product_line_code=None, snapshot_period="2026-06",
        risk_score=10, risk_level="low",
        quality_score=5, delivery_score=3, compliance_score=2,
    )
    db.add(s1)
    await db.commit()

    s2 = SupplyChainRiskSnapshot(
        snapshot_id=uuid4(), supplier_id=supplier.supplier_id,
        product_line_code=None, snapshot_period="2026-06",
        risk_score=15, risk_level="low",
        quality_score=8, delivery_score=4, compliance_score=3,
    )
    db.add(s2)
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.asyncio
async def test_calculate_all_supplier_scores_called_by_snapshot(db):
    """generate_snapshot calls calculate_all_supplier_scores, not evaluate_all_suppliers."""
    from unittest.mock import patch, AsyncMock
    from app.services.supply_chain_risk_map.service import generate_snapshot

    mock_scores = AsyncMock(return_value=[{
        "supplier_id": uuid4(), "supplier_name": "Mock",
        "risk_level": "low", "risk_score": 10,
        "quality_score": 5, "delivery_score": 3, "compliance_score": 2,
        "rule_results": [],
    }])
    with patch("app.services.supply_chain_risk_map.service.calculate_all_supplier_scores", mock_scores):
        with patch("app.services.supply_chain_risk_map.service.aggregate_supply_chain_metrics", new_callable=AsyncMock) as mock_agg:
            mock_agg.return_value = {}
            await generate_snapshot(db, None, "2026-06")
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

Expected: All 8 tests PASS

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

Product line select (from zustand store), period selector, "Refresh Snapshot" button (calls `riskMapApi.generateSnapshot`), export dropdown (CSV/Excel).

- [ ] **Step 2: Create `TimelineSlider.tsx`**

Ant Design `Slider` with month marks, play/pause/speed buttons (0.5x/1x/2x), `setInterval`-based animation, calls `riskMapApi.heatmap` on period change.

- [ ] **Step 3: Create `RiskHeatmap.tsx`**

ECharts heatmap with:
- Y axis = supplier names, X axis = dimension columns from `HeatmapColumn[]`
- Color mapping uses `risk_index` (not raw value)
- `higher_is_risk` / `lower_is_risk` → green-yellow-orange-red visualMap
- `neutral_exposure` → separate blue scale
- `dataZoom` vertical slider (start: 0, end: 30)
- Tooltip shows raw value, level, diff, source
- Click cell → emit callback to parent
- Click row label → emit callback to parent
- Checkbox per row for multi-select comparison

- [ ] **Step 4: Create `SupplyChainRiskMapPage.tsx`**

Left-right layout (70/30):
- Left: `<HeatmapToolbar>` + `<TimelineSlider>` + `<RiskHeatmap>`
- Right: `<DetailPanel>` (placeholder, will be implemented in Task 9)
- State: selected period, product line, heatmap data, selected supplier IDs

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

Small tag component: `erp_po` → blue "ERP", `supplier_evaluation_fallback` → orange "评价", `missing` → gray "N/A"

- [ ] **Step 2: Create `DiffIndicator.tsx`**

Arrow component: diff > 10% → red ↑, diff < -10% → green ↓, else no indicator.

- [ ] **Step 3: Create `SupplierDetail.tsx`**

Shows single supplier detail: name, risk level badge, dimension breakdown table (raw value + risk_index + source + diff), 6-month trend mini chart (ECharts line).

- [ ] **Step 4: Create `ComparisonRadar.tsx`**

ECharts radar chart overlaying multiple suppliers. Dimensions: quality/delivery/compliance/on-time-rate/PPM.

- [ ] **Step 5: Create `SupplierComparison.tsx`**

Side-by-side comparison: `<ComparisonRadar>` on top, dimension table below (with `DataSourceBadge`), export button.

- [ ] **Step 6: Create `DetailPanel.tsx`**

Container that switches between `<SupplierDetail>` (single supplier) and `<SupplierComparison>` (multi-select), based on number of selected suppliers.

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

In `frontend/src/App.tsx`, add the route after the existing `/supplier-risk` route block (around line 137). Also add the import at the top:

```tsx
import SupplyChainRiskMapPage from "./pages/supplyChainRiskMap/SupplyChainRiskMapPage";
```

```tsx
<Route
  path="/supply-chain-risk-map"
  element={
    <ProtectedRoute requiredModule="supply_chain_risk_map">
      <AppLayout />
    </ProtectedRoute>
  }
>
  <Route index element={<SupplyChainRiskMapPage />} />
</Route>
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

In `backend/app/seed.py`, add a function that creates sample `SupplyChainRiskSnapshot` records for 2-3 suppliers across 3 months (2026-01 through 2026-03) with realistic dimension values. Call it from the main seed function.

- [ ] **Step 2: Write end-to-end test**

Create `backend/tests/test_supply_chain_risk_e2e.py` that:
1. Seeds test data
2. Calls `GET /supply-chain-risk-map/heatmap?period=2026-03` → verifies response structure
3. Calls `GET /supply-chain-risk-map/timeline` → verifies periods returned
4. Calls `POST /supply-chain-risk-map/snapshots/generate` → verifies snapshot created
5. Calls `GET /supply-chain-risk-map/export?format=csv` → verifies CSV download

- [ ] **Step 3: Run all tests**

```bash
cd backend && python -m pytest tests/test_supply_chain_risk_e2e.py tests/test_supply_chain_risk_service.py tests/test_supply_chain_risk_aggregator.py tests/test_supply_chain_risk_integration.py -v
```

Expected: All tests PASS

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
| §8 Tests (27 total) | Tasks 2-6 + 11 |
| §9 Integration (calculate_all_supplier_scores, enforce_product_line, ERP) | Tasks 2, 5, 6 |
| §10 Security (advisory lock, historical snapshot read-only, product_line) | Tasks 4, 5 |

### Placeholder Scan

Backend test code (Tasks 2-4, 6) has complete Python code with imports, fixtures, and assertions — no `pass` stubs. Integration tests use real DB users with `create_access_token`. The advisory lock test uses two independent sessions.

Frontend component steps (Tasks 8-10) describe behavior and component structure but do not include full JSX code — the executor must implement React components following the project's Ant Design + ECharts patterns. This is standard for UI plans where the backend contract is fully specified.

### Type Consistency Check

- `calculate_all_supplier_scores` returns `list[dict]` with keys matching `aggregator.py` input — ✓
- `SupplyChainRiskSnapshot` model fields match migration columns — ✓
- `HeatmapCell`/`HeatmapResponse` types match API response format — ✓
- `riskMapApi` method signatures match API endpoints — ✓
- Module enum `SUPPLY_CHAIN_RISK_MAP` used consistently — ✓

Plan complete and saved to `docs/superpowers/plans/2026-06-11-supply-chain-risk-map.md`.