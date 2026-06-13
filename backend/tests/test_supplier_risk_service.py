"""Service-level tests for supplier risk alert module."""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-supplier-risk-service-tests")

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select, func

from app.models.supplier import Supplier
from app.models.supplier_risk import SupplierRiskAlert, SupplierRiskConfig
from app.services.supplier_risk.service import (
    handle_alert,
    create_scar_from_alert,
    create_capa_from_alert,
    calculate_all_supplier_scores,
)
from app.services.supplier_risk.config import get_effective_configs


@pytest_asyncio.fixture
async def seed_supplier(db, admin_user, default_factory):
    """Create a test supplier."""
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"SUP-{uuid.uuid4().hex[:8]}",
        name="Test Supplier",
        short_name="Test",
        factory_id=default_factory.id,
        status="approved",
        created_by=admin_user.user_id,
    )
    db.add(supplier)
    await db.flush()
    await db.refresh(supplier)
    return supplier


@pytest_asyncio.fixture
async def seed_open_alert(db, seed_supplier):
    """Create an open risk alert for the test supplier."""
    alert = SupplierRiskAlert(
        supplier_id=seed_supplier.supplier_id,
        factory_id=seed_supplier.factory_id,
        risk_level="high",
        risk_score=75.0,
        quality_score=80.0,
        delivery_score=60.0,
        compliance_score=40.0,
        rule_results={},
        snapshot_date=date.today(),
        status="open",
        alert_type="initial",
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return alert


@pytest_asyncio.fixture
async def seed_acknowledged_alert(db, seed_supplier):
    """Create an acknowledged risk alert for the test supplier."""
    alert = SupplierRiskAlert(
        supplier_id=seed_supplier.supplier_id,
        factory_id=seed_supplier.factory_id,
        risk_level="medium",
        risk_score=55.0,
        quality_score=70.0,
        delivery_score=60.0,
        compliance_score=50.0,
        rule_results={},
        snapshot_date=date.today(),
        status="acknowledged",
        alert_type="initial",
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return alert


@pytest_asyncio.fixture
async def seed_config_priority(db, admin_user, seed_supplier):
    """Create 4 configs with increasing specificity for priority testing."""
    fid = seed_supplier.factory_id
    configs = [
        # Layer 4: global default
        SupplierRiskConfig(
            rule_id="R01",
            enabled=True,
            category="quality",
            weight=10.0,
            thresholds={"ppm_limit": 1000, "window_days": 90},
            factory_id=fid,
            updated_by=admin_user.user_id,
        ),
        # Layer 3: product line default
        SupplierRiskConfig(
            rule_id="R01",
            enabled=True,
            category="quality",
            weight=12.0,
            thresholds={"ppm_limit": 800, "window_days": 90},
            factory_id=fid,
            product_line_code="DC-DC-100",
            updated_by=admin_user.user_id,
        ),
        # Layer 2: supplier global
        SupplierRiskConfig(
            rule_id="R01",
            enabled=True,
            category="quality",
            weight=14.0,
            thresholds={"ppm_limit": 600, "window_days": 90},
            factory_id=fid,
            supplier_id=seed_supplier.supplier_id,
            updated_by=admin_user.user_id,
        ),
        # Layer 1: supplier + product line
        SupplierRiskConfig(
            rule_id="R01",
            enabled=True,
            category="quality",
            weight=16.0,
            thresholds={"ppm_limit": 400, "window_days": 90},
            factory_id=fid,
            supplier_id=seed_supplier.supplier_id,
            product_line_code="DC-DC-100",
            updated_by=admin_user.user_id,
        ),
    ]
    for cfg in configs:
        # Check if this exact config already exists (by rule_id + supplier_id + product_line_code)
        q = select(func.count()).select_from(SupplierRiskConfig).where(
            SupplierRiskConfig.rule_id == cfg.rule_id,
        )
        if cfg.supplier_id is None:
            q = q.where(SupplierRiskConfig.supplier_id.is_(None))
        else:
            q = q.where(SupplierRiskConfig.supplier_id == cfg.supplier_id)
        if cfg.product_line_code is None:
            q = q.where(SupplierRiskConfig.product_line_code.is_(None))
        else:
            q = q.where(SupplierRiskConfig.product_line_code == cfg.product_line_code)
        exists = (await db.execute(q)).scalar()
        if exists == 0:
            db.add(cfg)
    await db.flush()
    return configs


# ─── handle_alert tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_alert_acknowledge(db, seed_open_alert, admin_user):
    """Acknowledge action transitions open -> acknowledged."""
    alert = await handle_alert(
        db, seed_open_alert.alert_id, "acknowledge", None, admin_user.user_id
    )
    assert alert.status == "acknowledged"
    assert alert.handled_by == admin_user.user_id


@pytest.mark.asyncio
async def test_handle_alert_ignore_requires_note(db, seed_open_alert, admin_user):
    """Ignore action requires a non-empty note."""
    with pytest.raises(ValueError, match="理由"):
        await handle_alert(
            db, seed_open_alert.alert_id, "ignore", None, admin_user.user_id
        )

    with pytest.raises(ValueError, match="理由"):
        await handle_alert(
            db, seed_open_alert.alert_id, "ignore", "   ", admin_user.user_id
        )


@pytest.mark.asyncio
async def test_close_alert_after_acknowledged(db, seed_acknowledged_alert, admin_user):
    """Close action transitions acknowledged -> closed."""
    alert = await handle_alert(
        db, seed_acknowledged_alert.alert_id, "close", None, admin_user.user_id
    )
    assert alert.status == "closed"
    assert alert.handled_by == admin_user.user_id


# ─── Config priority test ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_priority_resolution(db, seed_config_priority, seed_supplier):
    """get_effective_configs returns the most specific config (supplier + PL)."""
    configs = await get_effective_configs(
        db, product_line_code="DC-DC-100", supplier_id=seed_supplier.supplier_id
    )
    r01_configs = [c for c in configs if c.rule_id == "R01"]
    assert len(r01_configs) == 1
    effective = r01_configs[0]
    assert effective.weight == 16.0
    assert effective.thresholds["ppm_limit"] == 400
    assert effective.supplier_id == seed_supplier.supplier_id
    assert effective.product_line_code == "DC-DC-100"


# ─── SCAR / CAPA creation tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_scar_from_alert_atomic(db, seed_open_alert, admin_user):
    """Creating a SCAR from an alert links it and updates status."""
    scar = await create_scar_from_alert(
        db, seed_open_alert.alert_id, admin_user.user_id
    )

    assert scar.scar_id is not None
    assert scar.supplier_id == seed_open_alert.supplier_id

    # Refresh alert to see in-session changes
    result = await db.execute(
        select(SupplierRiskAlert).where(
            SupplierRiskAlert.alert_id == seed_open_alert.alert_id
        )
    )
    alert = result.scalar_one()
    assert alert.status == "action_taken"
    assert alert.linked_scar_id == scar.scar_id


@pytest.mark.asyncio
async def test_create_capa_from_alert_atomic(db, seed_open_alert, admin_user):
    """Creating a CAPA from an alert links it and updates status."""
    capa = await create_capa_from_alert(
        db, seed_open_alert.alert_id, admin_user.user_id
    )

    assert capa.report_id is not None
    assert capa.title is not None

    result = await db.execute(
        select(SupplierRiskAlert).where(
            SupplierRiskAlert.alert_id == seed_open_alert.alert_id
        )
    )
    alert = result.scalar_one()
    assert alert.status == "action_taken"
    assert alert.linked_capa_id == capa.report_id


# ─── Pure scoring function tests ─────────────────────────────────────────────


# Default rule configs matching seed.py's DEFAULT_CONFIGS (10 rules).
# Inlined here rather than imported because supplier_risk.config does not
# export DEFAULT_CONFIGS; touching config.py is out of scope for this task.
_DEFAULT_RULE_CONFIGS = [
    {"rule_id": "R01", "category": "quality", "weight": 15.0,
     "thresholds": {"ppm_limit": 1000, "window_days": 90}},
    {"rule_id": "R02", "category": "quality", "weight": 12.0,
     "thresholds": {"acceptance_rate_min": 0.9, "decline_ratio": 0.1, "window_days": 90, "compare_window_days": 180}},
    {"rule_id": "R03", "category": "quality", "weight": 18.0,
     "thresholds": {"consecutive_batches": 3, "batch_limit": 10}},
    {"rule_id": "R04", "category": "quality", "weight": 10.0,
     "thresholds": {"open_days_limit": 30}},
    {"rule_id": "R05", "category": "quality", "weight": 12.0,
     "thresholds": {"scar_count_limit": 3, "window_days": 90}},
    {"rule_id": "R06", "category": "delivery", "weight": 12.0,
     "thresholds": {"delivery_score_min": 70, "decline_ratio": 0.15}},
    {"rule_id": "R07", "category": "delivery", "weight": 10.0,
     "thresholds": {"from_grades": ["A", "B"], "to_grades": ["C", "D"]}},
    {"rule_id": "R08", "category": "compliance", "weight": 8.0,
     "thresholds": {"warning_days": [90, 60, 30]}},
    {"rule_id": "R09", "category": "compliance", "weight": 8.0,
     "thresholds": {"score_decline_limit": 15}},
    {"rule_id": "R10", "category": "compliance", "weight": 15.0,
     "thresholds": {"keywords": ["安全", "安全特性", "safety"]}},
]


@pytest.mark.asyncio
async def test_calculate_all_supplier_scores_returns_scores_without_side_effects(db, admin_user):
    """calculate_all_supplier_scores should return scores for all suppliers
    including low-risk ones, without creating alerts or committing."""
    # Create an approved supplier
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no="TEST-SCRM-001",
        name="Test Supplier SCRM",
        short_name="Test SCRM",
        status="approved",
        created_by=admin_user.user_id,
        factory_id=admin_user.factory_id,
    )
    db.add(supplier)

    # Seed global default configs for all 10 rules so the supplier gets scored.
    for cfg in _DEFAULT_RULE_CONFIGS:
        exists = (await db.execute(
            select(func.count()).select_from(SupplierRiskConfig)
            .where(SupplierRiskConfig.rule_id == cfg["rule_id"],
                   SupplierRiskConfig.supplier_id.is_(None),
                   SupplierRiskConfig.product_line_code.is_(None))
        )).scalar()
        if exists == 0:
            db.add(SupplierRiskConfig(
                rule_id=cfg["rule_id"],
                enabled=True,
                thresholds=cfg["thresholds"],
                weight=cfg["weight"],
                category=cfg["category"],
                factory_id=admin_user.factory_id,
                supplier_id=None,
                product_line_code=None,
                updated_by=admin_user.user_id,
            ))
    await db.flush()

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
    # Verify output shape has expected keys
    supplier_result = next(r for r in result if r["supplier_id"] == supplier.supplier_id)
    for key in ("risk_level", "risk_score", "quality_score", "delivery_score", "compliance_score", "rule_results"):
        assert key in supplier_result, f"Missing key {key} in result"
