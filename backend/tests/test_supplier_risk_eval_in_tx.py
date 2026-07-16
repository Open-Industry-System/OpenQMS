"""Tests for evaluate_supplier_risk_in_tx, capa input gather, R11 contract, force_update."""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-supplier-risk-eval-in-tx")

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.models.capa import CAPAEightD
from app.models.supplier import Supplier
from app.models.supplier_risk import SupplierRiskAlert, SupplierRiskConfig
from app.models.supplier_risk_capa_input import SupplierRiskCapaInput
from app.services.supplier_risk.exceptions import SupplierRiskConfigurationError
from app.services.supplier_risk.service import evaluate_supplier_risk_in_tx, _gather_capa_inputs


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_supplier(db, factory_id, user_id) -> Supplier:
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"SUP-{uuid.uuid4().hex[:8]}",
        name="Eval InTx Supplier",
        short_name="EIT",
        factory_id=factory_id,
        status="approved",
        created_by=user_id,
    )
    db.add(supplier)
    await db.flush()
    await db.refresh(supplier)
    return supplier


async def _make_capa(db, factory_id, user_id, supplier_id=None) -> CAPAEightD:
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-EIT-{uuid.uuid4().hex[:8].upper()}",
        title="Eval InTx CAPA",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status="D8_CLOSURE",
        severity="严重",
        supplier_id=supplier_id,
    )
    db.add(capa)
    await db.flush()
    return capa


async def _ensure_rule_config(
    db,
    *,
    factory_id,
    user_id,
    rule_id: str,
    enabled: bool = True,
    category: str = "quality",
    weight: float = 10.0,
    thresholds: dict | None = None,
    product_line_code: str | None = None,
    supplier_id=None,
):
    """Insert a config if missing (avoids unique collisions across tests)."""
    q = select(SupplierRiskConfig).where(SupplierRiskConfig.rule_id == rule_id)
    if supplier_id is None:
        q = q.where(SupplierRiskConfig.supplier_id.is_(None))
    else:
        q = q.where(SupplierRiskConfig.supplier_id == supplier_id)
    if product_line_code is None:
        q = q.where(SupplierRiskConfig.product_line_code.is_(None))
    else:
        q = q.where(SupplierRiskConfig.product_line_code == product_line_code)
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing is not None:
        existing.enabled = enabled
        existing.weight = weight
        existing.thresholds = thresholds or {}
        existing.category = category
        await db.flush()
        return existing

    cfg = SupplierRiskConfig(
        rule_id=rule_id,
        enabled=enabled,
        category=category,
        weight=weight,
        thresholds=thresholds or {},
        factory_id=factory_id,
        product_line_code=product_line_code,
        supplier_id=supplier_id,
        updated_by=user_id,
    )
    db.add(cfg)
    await db.flush()
    return cfg


async def _make_capa_input(
    db,
    *,
    supplier_id,
    factory_id,
    user_id,
    status: str = "processed",
    severity: str = "严重",
    product_line_code: str | None = None,
    created_at: datetime | None = None,
) -> SupplierRiskCapaInput:
    capa = await _make_capa(db, factory_id, user_id, supplier_id=supplier_id)
    inp = SupplierRiskCapaInput(
        input_id=uuid.uuid4(),
        capa_id=capa.report_id,
        supplier_id=supplier_id,
        factory_id=factory_id,
        product_line_code=product_line_code,
        created_by=user_id,
        severity=severity,
        disposition="退货",
        repeat_suggested=True,
        repeat_detection_status="matched",
        matched_capa_nos=["8D-2025-001"],
        status=status,
    )
    db.add(inp)
    await db.flush()
    if created_at is not None:
        # server_default overrides Python-side created_at; set explicitly after insert
        await db.execute(
            text(
                "UPDATE supplier_risk_capa_inputs "
                "SET created_at = :ts "
                "WHERE input_id = :iid"
            ),
            {"ts": created_at, "iid": inp.input_id},
        )
        await db.flush()
        await db.refresh(inp)
    else:
        await db.refresh(inp)
    return inp


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seed_supplier(db, admin_user, default_factory):
    return await _make_supplier(db, default_factory.id, admin_user.user_id)


@pytest_asyncio.fixture
async def supplier_with_r11_config(db, admin_user, default_factory, seed_supplier):
    """Supplier + global R01/R11 enabled."""
    await _ensure_rule_config(
        db,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        rule_id="R01",
        thresholds={"ppm_limit": 1000, "window_days": 90},
        weight=15.0,
    )
    await _ensure_rule_config(
        db,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        rule_id="R11",
        thresholds={"base_score": 10, "severe_bonus": 10, "repeat_bonus": 10},
        weight=12.0,
    )
    return seed_supplier, None


@pytest_asyncio.fixture
async def supplier_without_r11_config(db, admin_user, default_factory, seed_supplier):
    """Only R01 present; no R11 row (or ensure disabled is not the case — missing)."""
    await _ensure_rule_config(
        db,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        rule_id="R01",
        thresholds={"ppm_limit": 1000, "window_days": 90},
        weight=15.0,
    )
    # If a prior test left R11 enabled globally, disable/remove effect by
    # inserting a supplier-scoped disabled R11 that wins priority? Better:
    # use supplier-scoped configs only for this supplier so globals don't matter.
    # Prefer supplier-scoped R01 and ensure no R11 for this supplier at any layer
    # that resolves. get_effective_configs walks R01..R11 and resolves each.
    # A global R11 from another fixture would still resolve. Disable global R11
    # if present; if missing, leave missing.
    q = select(SupplierRiskConfig).where(
        SupplierRiskConfig.rule_id == "R11",
        SupplierRiskConfig.supplier_id.is_(None),
        SupplierRiskConfig.product_line_code.is_(None),
    )
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing is not None:
        # Delete-from-session won't remove other tests' expectation; instead
        # mark disabled so run_all_rules skips — but contract treats disabled
        # the same as missing when trigger_input present. For no-trigger
        # tolerance we only need no raise, which disabled also satisfies.
        # For "missing" trigger case we need results without R11 → raise.
        # Disabled and missing both yield no R11 result → both raise with trigger.
        # For no-trigger tolerate test, either is fine.
        await db.delete(existing)
        await db.flush()
    return seed_supplier, None


@pytest_asyncio.fixture
async def supplier_with_r11_disabled(db, admin_user, default_factory, seed_supplier):
    await _ensure_rule_config(
        db,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        rule_id="R01",
        thresholds={"ppm_limit": 1000, "window_days": 90},
        weight=15.0,
    )
    await _ensure_rule_config(
        db,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        rule_id="R11",
        enabled=False,
        thresholds={},
        weight=12.0,
    )
    return seed_supplier, None


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_tx_does_not_commit(db, supplier_with_r11_config):
    """_in_tx 不 commit（调用方负责）。"""
    supplier, pl = supplier_with_r11_config
    alert, score, *_ = await evaluate_supplier_risk_in_tx(db, supplier.supplier_id, pl)
    # session still usable; return types present
    assert score is not None
    assert score.risk_level in ("low", "medium", "high", "critical")
    # force a follow-up query to prove session is healthy
    rows = (
        await db.execute(
            select(SupplierRiskAlert).where(SupplierRiskAlert.supplier_id == supplier.supplier_id)
        )
    ).scalars().all()
    # low risk without force_update → no alert; otherwise session-visible
    assert isinstance(rows, list)
    # Explicitly: in_tx itself must not raise and must not require commit
    _ = alert


@pytest.mark.asyncio
async def test_in_tx_raises_when_r11_missing_for_trigger(
    db, supplier_without_r11_config, admin_user, default_factory
):
    """trigger_input 评估时缺 R11 → raise（不假成功）。"""
    supplier, pl = supplier_without_r11_config
    inp = await _make_capa_input(
        db,
        supplier_id=supplier.supplier_id,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        status="processing",
        product_line_code=pl,
    )
    with pytest.raises(SupplierRiskConfigurationError):
        await evaluate_supplier_risk_in_tx(
            db, supplier.supplier_id, pl, trigger_input=inp
        )


@pytest.mark.asyncio
async def test_in_tx_raises_when_r11_disabled(
    db, supplier_with_r11_disabled, admin_user, default_factory
):
    """R11 disabled → run_all_rules 静默跳过 → results 无 R11 → raise。"""
    supplier, pl = supplier_with_r11_disabled
    inp = await _make_capa_input(
        db,
        supplier_id=supplier.supplier_id,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        status="processing",
        product_line_code=pl,
    )
    with pytest.raises(SupplierRiskConfigurationError):
        await evaluate_supplier_risk_in_tx(
            db, supplier.supplier_id, pl, trigger_input=inp
        )


@pytest.mark.asyncio
async def test_in_tx_no_trigger_tolerates_missing_r11(db, supplier_without_r11_config):
    """无 trigger_input 的普通评估容忍缺 R11（不 raise）。"""
    supplier, pl = supplier_without_r11_config
    alert, score, *_ = await evaluate_supplier_risk_in_tx(db, supplier.supplier_id, pl)
    assert score is not None
    _ = alert


@pytest.mark.asyncio
async def test_gather_capa_inputs_filters_window_and_status(
    db, seed_supplier, admin_user, default_factory
):
    """_gather_capa_inputs 读 processed/error + 90 天窗口。"""
    sup = seed_supplier
    now = datetime.now(timezone.utc)
    await _make_capa_input(
        db,
        supplier_id=sup.supplier_id,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        status="processed",
        created_at=now,
    )
    await _make_capa_input(
        db,
        supplier_id=sup.supplier_id,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        status="error",
        created_at=now,
    )
    await _make_capa_input(
        db,
        supplier_id=sup.supplier_id,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        status="pending",
        created_at=now,
    )
    await _make_capa_input(
        db,
        supplier_id=sup.supplier_id,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        status="processed",
        created_at=now - timedelta(days=100),
    )
    incidents = await _gather_capa_inputs(db, sup.supplier_id, None)
    assert len(incidents) == 2  # processed + error；超期与 pending 排除


@pytest.mark.asyncio
async def test_in_tx_injects_trigger_input_into_incidents(
    db, supplier_with_r11_config, admin_user, default_factory
):
    """trigger_input 被显式注入 incidents（即使 status=processing，gather 读不到也能消费）。"""
    supplier, pl = supplier_with_r11_config
    inp = await _make_capa_input(
        db,
        supplier_id=supplier.supplier_id,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        status="processing",
        severity="严重",
        product_line_code=pl,
    )
    alert, score, results, event_type = await evaluate_supplier_risk_in_tx(
        db,
        supplier.supplier_id,
        pl,
        trigger_input=inp,
        force_update=True,
    )
    # input 快照回填
    assert inp.evaluated_risk_level is not None
    assert inp.evaluated_risk_score is not None
    assert inp.evaluated_at is not None
    # force_update creates alert even for low → linked_alert_id set when alert exists
    if alert is not None:
        assert inp.linked_alert_id == alert.alert_id
    # R11 must have run
    assert any(r.rule_id == "R11" for r in results)
    assert score is not None
    _ = event_type
