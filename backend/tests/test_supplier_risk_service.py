"""Service-level tests for supplier risk alert module."""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-supplier-risk-service-tests")

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.supplier import Supplier
from app.models.supplier_risk import SupplierRiskAlert, SupplierRiskConfig
from app.services.supplier_risk.service import (
    handle_alert,
    create_scar_from_alert,
    create_capa_from_alert,
)
from app.services.supplier_risk.config import get_effective_configs


@pytest_asyncio.fixture
async def seed_supplier(db, admin_user):
    """Create a test supplier."""
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"SUP-{uuid.uuid4().hex[:8]}",
        name="Test Supplier",
        short_name="Test",
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
    configs = [
        # Layer 4: global default
        SupplierRiskConfig(
            rule_id="R01",
            enabled=True,
            category="quality",
            weight=10.0,
            thresholds={"ppm_limit": 1000, "window_days": 90},
            updated_by=admin_user.user_id,
        ),
        # Layer 3: product line default
        SupplierRiskConfig(
            rule_id="R01",
            enabled=True,
            category="quality",
            weight=12.0,
            thresholds={"ppm_limit": 800, "window_days": 90},
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
            supplier_id=seed_supplier.supplier_id,
            product_line_code="DC-DC-100",
            updated_by=admin_user.user_id,
        ),
    ]
    for cfg in configs:
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
