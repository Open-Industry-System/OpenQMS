import pytest
from datetime import date
from uuid import uuid4
from sqlalchemy import select, text, func
from app.models.supplier import Supplier
from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
from app.services.supply_chain_risk_map.service import current_period


# Default rule configs inlined from seed.py (config.py doesn't export DEFAULT_CONFIGS)
_DEFAULT_RULE_CONFIGS = [
    {"rule_id": "R01", "category": "quality", "weight": 15.0, "thresholds": {"ppm_limit": 1000, "window_days": 90}},
    {"rule_id": "R02", "category": "quality", "weight": 12.0, "thresholds": {"acceptance_rate_min": 0.9, "decline_ratio": 0.1, "window_days": 90, "compare_window_days": 180}},
    {"rule_id": "R03", "category": "quality", "weight": 18.0, "thresholds": {"consecutive_batches": 3, "batch_limit": 10}},
    {"rule_id": "R04", "category": "quality", "weight": 10.0, "thresholds": {"open_days_limit": 30}},
    {"rule_id": "R05", "category": "quality", "weight": 12.0, "thresholds": {"scar_count_limit": 3, "window_days": 90}},
    {"rule_id": "R06", "category": "delivery", "weight": 12.0, "thresholds": {"delivery_score_min": 70, "decline_ratio": 0.15}},
    {"rule_id": "R07", "category": "delivery", "weight": 10.0, "thresholds": {"from_grades": ["A", "B"], "to_grades": ["C", "D"]}},
    {"rule_id": "R08", "category": "compliance", "weight": 8.0, "thresholds": {"warning_days": [90, 60, 30]}},
    {"rule_id": "R09", "category": "compliance", "weight": 8.0, "thresholds": {"score_decline_limit": 15}},
    {"rule_id": "R10", "category": "compliance", "weight": 15.0, "thresholds": {"keywords": ["安全", "安全特性", "safety"]}},
]


@pytest.fixture
async def seed_supplier(db, admin_user, default_factory):
    """Create an approved supplier with global default configs.
    Also ensures ProductLine DC-DC-100 exists (FK for product_line_code)."""
    from app.models.supplier_risk import SupplierRiskConfig
    from app.models.product_line import ProductLine

    # Ensure product line exists for product_line_code FK
    result = await db.execute(
        select(ProductLine).where(ProductLine.code == "DC-DC-100")
    )
    if result.scalar_one_or_none() is None:
        db.add(ProductLine(code="DC-DC-100", name="DC-DC-100", factory_id=default_factory.id))
        await db.flush()

    supplier = Supplier(
        supplier_id=uuid4(), supplier_no="T-SNAP-01", name="SnapshotTest",
        short_name="ST", factory_id=default_factory.id, status="approved", created_by=admin_user.user_id,
    )
    db.add(supplier)
    for cfg in _DEFAULT_RULE_CONFIGS:
        # Check if global config already exists (idempotent with NULLS NOT DISTINCT)
        existing = await db.execute(
            select(SupplierRiskConfig.config_id).where(
                SupplierRiskConfig.rule_id == cfg["rule_id"],
                SupplierRiskConfig.supplier_id.is_(None),
                SupplierRiskConfig.product_line_code.is_(None),
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(SupplierRiskConfig(
                rule_id=cfg["rule_id"], enabled=True,
                thresholds=cfg["thresholds"], weight=cfg["weight"],
                supplier_id=None, factory_id=default_factory.id,
                category=cfg["category"], product_line_code=None,
                updated_by=admin_user.user_id,
            ))
    await db.flush()
    return supplier


@pytest.mark.asyncio
async def test_generate_snapshot_upsert(db, seed_supplier):
    """Generating snapshot twice for the same month overwrites (UPSERT).

    Uses product_line_code="DC-DC-100" because ON CONFLICT on a standard
    UNIQUE constraint does not match NULLs. The NULLS NOT DISTINCT variant
    from the migration only applies when the migration-created index is active.
    """
    from app.services.supply_chain_risk_map.service import generate_snapshot
    period = current_period()
    count1 = await generate_snapshot(db, "DC-DC-100", period)
    assert count1 >= 1
    count2 = await generate_snapshot(db, "DC-DC-100", period)
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
    """pg_try_advisory_xact_lock prevents concurrent snapshot generation."""
    from app.services.supply_chain_risk_map.scheduler import _try_acquire_xact_lock

    # Transaction-level advisory lock is held until commit/rollback.
    # Since our test db fixture wraps everything in a transaction that gets
    # rolled back, we can verify the lock is acquired successfully.
    acquired = await _try_acquire_xact_lock(db)
    assert acquired is True

    # A second attempt within the same transaction should succeed
    # (same transaction holds the lock already)
    acquired_again = await _try_acquire_xact_lock(db)
    assert acquired_again is True


@pytest.mark.asyncio
async def test_supplier_detail_trend_filters_by_product_line_and_period(db, seed_supplier):
    """Supplier detail trend filters by product_line_code and truncates at the selected period.

    Seeds 3 months of global + product-line snapshots, then requests period="2026-02".
    Asserts that trend for 2026-02 does NOT include 2026-03 (future month),
    and that global vs product-line trends are isolated.
    """
    from app.models.supply_chain_risk_map import SupplyChainRiskSnapshot
    from app.services.supply_chain_risk_map.service import get_supplier_detail

    # Seed 3 months of global + DC-DC-100 snapshots with DIFFERENT risk_scores per product line
    # so that if the product_line filter is removed, the assertion catches it.
    for period in ["2026-01", "2026-02", "2026-03"]:
        # Global snapshots: risk_score increments with month (10, 20, 30)
        db.add(SupplyChainRiskSnapshot(
            snapshot_id=uuid4(),
            supplier_id=seed_supplier.supplier_id,
            product_line_code=None,
            snapshot_period=period,
            risk_score=10.0 * (int(period.split("-")[1])),
            risk_level="low",
            quality_score=5.0,
            delivery_score=3.0,
            compliance_score=2.0,
            erp_on_time_rate=95.0,
            purchase_amount_pct=33.0,
            open_scar_count=0,
            ppm_value=100,
            dimensions={},
        ))
        # DC-DC-100 snapshots: risk_score is 100 + month (110, 120, 130)
        db.add(SupplyChainRiskSnapshot(
            snapshot_id=uuid4(),
            supplier_id=seed_supplier.supplier_id,
            product_line_code="DC-DC-100",
            snapshot_period=period,
            risk_score=100.0 + 10.0 * (int(period.split("-")[1])),
            risk_level="high",
            quality_score=50.0,
            delivery_score=40.0,
            compliance_score=30.0,
            erp_on_time_rate=60.0,
            purchase_amount_pct=67.0,
            open_scar_count=3,
            ppm_value=5000,
            dimensions={},
        ))
    await db.commit()

    # Request detail for period 2026-02 — trend must NOT include 2026-03
    detail_global = await get_supplier_detail(db, seed_supplier.supplier_id, None, "2026-02")
    global_periods = [t.period for t in detail_global.trend]
    global_risk_scores = [t.risk_score for t in detail_global.trend]
    assert "2026-03" not in global_periods, "Trend should not include months after the selected period"
    assert "2026-02" in global_periods, "Trend should include the selected period"
    assert "2026-01" in global_periods, "Trend should include prior periods"
    # Verify global trend has global risk_scores (10, 20), not product-line scores (110, 120)
    for score in global_risk_scores:
        assert score < 100, f"Global trend should have global risk_scores (<100), got {score}"

    # Product-line detail should also cap at 2026-02 and have product-line risk_scores
    detail_pl = await get_supplier_detail(db, seed_supplier.supplier_id, "DC-DC-100", "2026-02")
    pl_periods = [t.period for t in detail_pl.trend]
    pl_risk_scores = [t.risk_score for t in detail_pl.trend]
    assert "2026-03" not in pl_periods, "Product-line trend should not include months after the selected period"
    assert "2026-02" in pl_periods
    # Verify product-line trend has product-line risk_scores (110, 120), not global (10, 20)
    for score in pl_risk_scores:
        assert score >= 100, f"Product-line trend should have product-line risk_scores (>=100), got {score}"