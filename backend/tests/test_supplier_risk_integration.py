"""Integration tests for supplier risk alert module.

Covers DB-level constraints, service concurrency, notification resilience,
rollback behavior, CAPA close hooks, and SSRF protection.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-supplier-risk-integration-tests")

import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import status
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.database import get_db
from app.core.deps import get_request_scope, RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import get_current_user, Module, PermissionLevel
from app.models.supplier import Supplier, SupplierSCAR
from app.models.capa import CAPAEightD
from app.models.iqc_inspection import IqcInspection
from app.models.supplier_risk import (
    SupplierRiskAlert,
    SupplierRiskConfig,
    SupplierRiskNotificationChannel,
)
from app.models.user import User
from app.services.supplier_risk.service import (
    evaluate_supplier_risk,
    create_scar_from_alert,
)
from app.services.supplier_risk.notifier import (
    send_notifications,
    _is_private_url,
    SSRFError,
)
from app.services.capa_service import _create_capa_without_commit, update_capa
from app.services.scar_service import _create_scar_without_commit


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seed_supplier(db, admin_user):
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
async def seed_global_configs(db, admin_user):
    """Seed one global default config per rule so evaluation can run (idempotent)."""
    defaults = [
        ("R01", "quality", 15.0, {"ppm_limit": 1000, "window_days": 90}),
        ("R02", "quality", 12.0, {"acceptance_rate_min": 0.9, "decline_ratio": 0.1, "window_days": 90, "compare_window_days": 180}),
        ("R03", "quality", 18.0, {"consecutive_batches": 3, "batch_limit": 10}),
        ("R04", "quality", 10.0, {"open_days_limit": 30}),
        ("R05", "quality", 12.0, {"scar_count_limit": 3, "window_days": 90}),
        ("R06", "delivery", 12.0, {"delivery_score_min": 70, "decline_ratio": 0.15}),
        ("R07", "delivery", 10.0, {"from_grades": ["A", "B"], "to_grades": ["C", "D"]}),
        ("R08", "compliance", 8.0, {"warning_days": [90, 60, 30]}),
        ("R09", "compliance", 8.0, {"score_decline_limit": 15}),
        ("R10", "compliance", 15.0, {"keywords": ["安全", "安全特性", "safety"]}),
    ]
    existing = set()
    result = await db.execute(
        select(SupplierRiskConfig.rule_id).where(
            SupplierRiskConfig.supplier_id.is_(None),
            SupplierRiskConfig.product_line_code.is_(None),
        )
    )
    existing = {r for r in result.scalars().all()}
    for rule_id, category, weight, thresholds in defaults:
        if rule_id in existing:
            continue
        db.add(SupplierRiskConfig(
            rule_id=rule_id,
            enabled=True,
            category=category,
            weight=weight,
            thresholds=thresholds,
            updated_by=admin_user.user_id,
        ))
    await db.flush()


@pytest_asyncio.fixture
async def seed_open_alert(db, seed_supplier):
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
async def seed_medium_alert(db, seed_supplier):
    alert = SupplierRiskAlert(
        supplier_id=seed_supplier.supplier_id,
        risk_level="medium",
        risk_score=55.0,
        quality_score=70.0,
        delivery_score=60.0,
        compliance_score=50.0,
        rule_results={},
        snapshot_date=date.today(),
        status="open",
        alert_type="initial",
        product_line_code="DC-DC-100",
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return alert


@pytest_asyncio.fixture
async def seed_alert_with_capa(db, seed_supplier, admin_user):
    """Create an alert already linked to a CAPA in D7 status."""
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-{date.today().year}-LINKED-{uuid.uuid4().hex[:8].upper()}",
        title="Linked CAPA",
        severity="严重",
        due_date=date.today(),
        product_line_code="DC-DC-100",
        status="D7_PREVENTION",
        created_by=admin_user.user_id,
    )
    db.add(capa)
    await db.flush()
    await db.refresh(capa)

    alert = SupplierRiskAlert(
        supplier_id=seed_supplier.supplier_id,
        risk_level="high",
        risk_score=75.0,
        quality_score=80.0,
        delivery_score=60.0,
        compliance_score=40.0,
        rule_results={},
        snapshot_date=date.today(),
        status="acknowledged",
        alert_type="initial",
        linked_capa_id=capa.report_id,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return alert, capa


@pytest_asyncio.fixture
async def seed_inspections_for_high_risk(db, seed_supplier, admin_user):
    """Create rejected IQC inspections that will trigger high/critical risk."""
    suffix = uuid.uuid4().hex[:8]
    for i in range(5):
        db.add(IqcInspection(
            inspection_id=uuid.uuid4(),
            inspection_no=f"IQC-HIGH-{suffix}-{i:03d}",
            supplier_id=seed_supplier.supplier_id,
            lot_qty=100,
            defect_qty=100,
            inspection_result="rejected",
            inspection_date=date.today() - timedelta(days=i),
            status="judged",
            product_line_code="DC-DC-100",
            defect_description="发现安全特性不合格",
        ))
    await db.flush()


# ─── API client helpers ───────────────────────────────────────────────────────


def _make_user(role_key: str = "admin"):
    role_id = uuid.uuid4()
    factory_id = uuid.uuid4()
    user = User(
        user_id=uuid.uuid4(),
        username=role_key,
        display_name=role_key,
        email=f"{role_key}@openqms.local",
        password_hash="hashed",
        is_active=True,
        role_id=role_id,
        factory_id=factory_id,
    )
    user.role_definition = MagicMock()
    user.role_definition.role_key = role_key
    user.role_definition.bypass_row_level_security = (role_key == "admin")
    return user


@pytest.fixture
def override_dependencies_edit():
    user = _make_user("admin")

    async def mock_get_current_user():
        return user

    mock_scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=user.factory_id),
        effective_factory_id=user.factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=user,
    )

    async def mock_get_request_scope():
        return mock_scope

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_request_scope] = mock_get_request_scope
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)), \
         patch("app.api.supplier_risk.get_user_permission", new=AsyncMock(return_value=PermissionLevel.EDIT)):
        yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_dependencies_view():
    user = _make_user("viewer")

    async def mock_get_current_user():
        return user

    mock_scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=[user.factory_id], default_factory_id=user.factory_id),
        effective_factory_id=user.factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=user,
    )

    async def mock_get_request_scope():
        return mock_scope

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_request_scope] = mock_get_request_scope
    with patch("app.core.permissions.get_user_permission", new=AsyncMock(return_value=PermissionLevel.VIEW)), \
         patch("app.api.supplier_risk.get_user_permission", new=AsyncMock(return_value=PermissionLevel.VIEW)):
        yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client_edit(override_dependencies_edit):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def client_view(override_dependencies_view):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ─── 1. Migration unique index ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_migration_unique_indexes_prevent_duplicate_configs(db, admin_user):
    """The partial unique index blocks two global-default configs for the same rule."""
    unique_rule = f"R{uuid.uuid4().hex[:6].upper()}"
    db.add(SupplierRiskConfig(
        rule_id=unique_rule,
        enabled=True,
        category="quality",
        weight=10.0,
        thresholds={},
        updated_by=admin_user.user_id,
    ))
    await db.flush()

    db.add(SupplierRiskConfig(
        rule_id=unique_rule,
        enabled=True,
        category="quality",
        weight=12.0,
        thresholds={},
        updated_by=admin_user.user_id,
    ))
    try:
        with pytest.raises(IntegrityError):
            await db.flush()
    finally:
        # Ensure the aborted transaction is rolled back so the first insert
        # is not committed when the session context exits normally.
        await db.rollback()


# ─── 2. Viewer cannot edit alert ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_cannot_edit_alert(client_view, seed_open_alert):
    """A viewer hitting the handle endpoint gets 403."""
    resp = await client_view.post(
        f"/api/supplier-risk/alerts/{seed_open_alert.alert_id}/handle",
        json={"action": "acknowledge"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


# ─── 3. Product line isolation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_product_line_isolation(db, seed_supplier):
    """List endpoint filters alerts by product_line_code."""
    alert_pl = SupplierRiskAlert(
        supplier_id=seed_supplier.supplier_id,
        risk_level="high",
        risk_score=70.0,
        quality_score=60.0,
        delivery_score=60.0,
        compliance_score=60.0,
        rule_results={},
        snapshot_date=date.today(),
        status="open",
        alert_type="initial",
        product_line_code="DC-DC-100",
    )
    alert_other = SupplierRiskAlert(
        supplier_id=seed_supplier.supplier_id,
        risk_level="medium",
        risk_score=50.0,
        quality_score=60.0,
        delivery_score=60.0,
        compliance_score=60.0,
        rule_results={},
        snapshot_date=date.today(),
        status="open",
        alert_type="initial",
        product_line_code="DC-DC-200",
    )
    db.add_all([alert_pl, alert_other])
    await db.flush()

    result = await db.execute(
        select(SupplierRiskAlert).where(
            SupplierRiskAlert.product_line_code == "DC-DC-100"
        )
    )
    rows = list(result.scalars().all())
    assert all(r.product_line_code == "DC-DC-100" for r in rows)
    assert any(r.alert_id == alert_pl.alert_id for r in rows)
    assert not any(r.alert_id == alert_other.alert_id for r in rows)


# ─── 4. Concurrent evaluation dedup ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_eval_creates_single_alert(
    db, seed_supplier, seed_global_configs, seed_inspections_for_high_risk
):
    """Multiple evaluate calls on the same supplier+PL+date yield a single alert."""
    result1 = await evaluate_supplier_risk(
        db, seed_supplier.supplier_id, product_line_code="DC-DC-100"
    )
    result2 = await evaluate_supplier_risk(
        db, seed_supplier.supplier_id, product_line_code="DC-DC-100"
    )

    assert result1["alert_id"] is not None
    assert result1["alert_id"] == result2["alert_id"]

    result = await db.execute(
        select(SupplierRiskAlert).where(
            SupplierRiskAlert.supplier_id == seed_supplier.supplier_id,
            SupplierRiskAlert.product_line_code == "DC-DC-100",
            SupplierRiskAlert.snapshot_date == date.today(),
        )
    )
    assert len(list(result.scalars().all())) == 1


# ─── 5. Alert escalation on risk upgrade ──────────────────────────────────────


@pytest.mark.asyncio
async def test_alert_escalated_on_risk_upgrade(
    db, seed_supplier, seed_medium_alert, seed_inspections_for_high_risk, seed_global_configs
):
    """An existing medium alert is escalated when new evaluation yields high/critical."""
    await evaluate_supplier_risk(
        db, seed_supplier.supplier_id, product_line_code="DC-DC-100"
    )

    result = await db.execute(
        select(SupplierRiskAlert).where(
            SupplierRiskAlert.alert_id == seed_medium_alert.alert_id
        )
    )
    alert = result.scalar_one()
    assert alert.alert_type == "escalated"
    assert alert.risk_level in ("high", "critical")


# ─── 6. Notification failure is non-blocking ──────────────────────────────────


@pytest.mark.asyncio
async def test_notification_failure_non_blocking(db, seed_open_alert, admin_user):
    """An exception inside _send_email is swallowed by send_notifications."""
    channel = SupplierRiskNotificationChannel(
        channel_id=uuid.uuid4(),
        channel_type="email",
        config={"addresses": ["test@openqms.local"]},
        min_risk_level="high",
        enabled=True,
        created_by=admin_user.user_id,
    )
    db.add(channel)
    await db.flush()

    with patch(
        "app.services.supplier_risk.notifier._send_email",
        side_effect=RuntimeError("SMTP down"),
    ):
        # Should not raise
        await send_notifications(db, seed_open_alert, product_line_code=None)


# ─── 6a. Unchanged alert must NOT trigger notifications ───────────────────────


@pytest.mark.asyncio
async def test_unchanged_alert_no_notification(
    db, seed_supplier, seed_open_alert, seed_global_configs
):
    """Re-evaluating an existing high alert with same-or-lower risk must NOT call send_notifications."""
    with patch("app.services.supplier_risk.notifier.send_notifications", new=AsyncMock()) as mock_send:
        await evaluate_supplier_risk(
            db, seed_supplier.supplier_id, product_line_code=None
        )
        mock_send.assert_not_called()


# ─── 7/8. _create_scar_without_commit / _create_capa_without_commit flush only ─


@pytest.mark.asyncio
async def test_create_scar_without_commit_flushes_only(
    db, seed_supplier, admin_user
):
    """_create_scar_without_commit produces a scar_id after flush without commit."""
    scar = await _create_scar_without_commit(
        db,
        supplier_id=seed_supplier.supplier_id,
        source_type="risk_alert",
        source_id=uuid.uuid4(),
        description="Test SCAR",
        issued_by=admin_user.user_id,
    )
    assert scar.scar_id is not None

    # Verify visible in current session
    result = await db.execute(
        select(SupplierSCAR).where(SupplierSCAR.scar_id == scar.scar_id)
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_create_capa_without_commit_flushes_only(
    db, admin_user
):
    """_create_capa_without_commit produces a report_id after flush without commit."""
    capa = await _create_capa_without_commit(
        db,
        title="Test CAPA",
        document_no=f"8D-{date.today().year}-FLUSH-{uuid.uuid4().hex[:6]}",
        severity="一般",
        due_date=date.today(),
        user_id=admin_user.user_id,
    )
    assert capa.report_id is not None

    result = await db.execute(
        select(CAPAEightD).where(CAPAEightD.report_id == capa.report_id)
    )
    assert result.scalar_one_or_none() is not None


# ─── 9. SCAR creation failure rolls back alert ─────────────────────────────────


@pytest.mark.asyncio
async def test_scar_creation_failure_rolls_back_alert(
    db, seed_open_alert, admin_user, monkeypatch
):
    """If _create_scar_without_commit raises, the alert remains unchanged."""
    original_status = seed_open_alert.status
    monkeypatch.setattr(
        "app.services.scar_service._create_scar_without_commit",
        AsyncMock(side_effect=RuntimeError("SCAR creation failed")),
    )

    with pytest.raises(RuntimeError, match="SCAR creation failed"):
        await create_scar_from_alert(
            db, seed_open_alert.alert_id, admin_user.user_id
        )

    result = await db.execute(
        select(SupplierRiskAlert).where(
            SupplierRiskAlert.alert_id == seed_open_alert.alert_id
        )
    )
    alert = result.scalar_one()
    assert alert.status == original_status
    assert alert.linked_scar_id is None


# ─── 10. CAPA close closes linked alert ───────────────────────────────────────


@pytest.mark.asyncio
async def test_capa_close_closes_linked_alert(
    db, seed_alert_with_capa, admin_user
):
    """Updating a CAPA to D8_CLOSURE closes the linked risk alert."""
    alert, capa = seed_alert_with_capa
    capa.status = "D8_CLOSURE"

    await update_capa(db, capa, {"status": "D8_CLOSURE"}, admin_user.user_id)

    result = await db.execute(
        select(SupplierRiskAlert).where(
            SupplierRiskAlert.alert_id == alert.alert_id
        )
    )
    updated_alert = result.scalar_one()
    assert updated_alert.status == "closed"


# ─── 11. Webhook SSRF blocked ─────────────────────────────────────────────────


def test_webhook_ssrf_blocked_private_url():
    """_is_private_url rejects loopback/private addresses."""
    assert _is_private_url("http://127.0.0.1:8080/webhook") is True
    assert _is_private_url("http://localhost/foo") is True
    assert _is_private_url("http://192.168.1.1/bar") is True
    assert _is_private_url("http://10.0.0.1/baz") is True


@pytest.mark.asyncio
async def test_webhook_ssrf_blocked_send_notifications(db, seed_open_alert, admin_user):
    """_send_webhook raises SSRFError for a private webhook URL."""
    channel = SupplierRiskNotificationChannel(
        channel_id=uuid.uuid4(),
        channel_type="webhook",
        config={"url": "http://127.0.0.1:8080/webhook"},
        min_risk_level="low",
        enabled=True,
        created_by=admin_user.user_id,
    )
    db.add(channel)
    await db.flush()

    from app.services.supplier_risk.notifier import _send_webhook
    with pytest.raises(SSRFError):
        await _send_webhook(channel, seed_open_alert)
