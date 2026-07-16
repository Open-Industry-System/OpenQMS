"""Tests for supplier risk input outbox worker (claim / process / recover)."""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-risk-input-worker")

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.supplier import Supplier
from app.models.supplier_risk import SupplierRiskConfig
from app.models.supplier_risk_capa_input import SupplierRiskCapaInput
from app.services.supplier_risk.risk_input_worker import (
    claim_batch,
    process_one,
    recover_stale_inputs,
)


async def _make_supplier(db, factory_id, user_id) -> Supplier:
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"SUP-{uuid.uuid4().hex[:8]}",
        name="Risk Input Worker Supplier",
        short_name="RIW",
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
        document_no=f"8D-RIW-{uuid.uuid4().hex[:8].upper()}",
        title="Risk Input Worker CAPA",
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
):
    q = select(SupplierRiskConfig).where(
        SupplierRiskConfig.rule_id == rule_id,
        SupplierRiskConfig.supplier_id.is_(None),
        SupplierRiskConfig.product_line_code.is_(None),
    )
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
        product_line_code=None,
        supplier_id=None,
        updated_by=user_id,
    )
    db.add(cfg)
    await db.flush()
    return cfg


async def _make_input(
    db,
    *,
    factory_id,
    user_id,
    supplier_id,
    status: str = "pending",
    locked_at: datetime | None = None,
    attempt_count: int = 0,
    max_attempts: int = 5,
    claim_token=None,
    next_retry_at=None,
) -> SupplierRiskCapaInput:
    capa = await _make_capa(db, factory_id, user_id, supplier_id=supplier_id)
    inp = SupplierRiskCapaInput(
        input_id=uuid.uuid4(),
        capa_id=capa.report_id,
        supplier_id=supplier_id,
        factory_id=factory_id,
        product_line_code="DC-DC-100",
        created_by=user_id,
        severity="严重",
        disposition="退货",
        repeat_suggested=True,
        repeat_confirmed=True,
        repeat_detection_status="matched",
        matched_capa_nos=["8D-2025-001"],
        status=status,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        locked_at=locked_at,
        claim_token=claim_token,
        next_retry_at=next_retry_at,
    )
    db.add(inp)
    await db.flush()
    await db.refresh(inp)
    return inp


@pytest_asyncio.fixture
async def seed_supplier(db, admin_user, default_factory):
    return await _make_supplier(db, default_factory.id, admin_user.user_id)


@pytest_asyncio.fixture
async def pending_input_factory(db, admin_user, default_factory, seed_supplier):
    async def _factory(**kwargs):
        return await _make_input(
            db,
            factory_id=default_factory.id,
            user_id=admin_user.user_id,
            supplier_id=seed_supplier.supplier_id,
            **kwargs,
        )

    return _factory


@pytest_asyncio.fixture
async def input_factory(db, admin_user, default_factory, seed_supplier):
    async def _factory(**kwargs):
        return await _make_input(
            db,
            factory_id=default_factory.id,
            user_id=admin_user.user_id,
            supplier_id=seed_supplier.supplier_id,
            **kwargs,
        )

    return _factory


@pytest_asyncio.fixture
async def pending_input_with_r11(db, admin_user, default_factory, seed_supplier):
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
    inp = await _make_input(
        db,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        supplier_id=seed_supplier.supplier_id,
        status="pending",
    )
    return inp, seed_supplier


@pytest_asyncio.fixture
async def pending_input_without_r11(db, admin_user, default_factory, seed_supplier):
    await _ensure_rule_config(
        db,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        rule_id="R01",
        thresholds={"ppm_limit": 1000, "window_days": 90},
        weight=15.0,
    )
    # Remove global R11 if present so trigger_input evaluation raises.
    q = select(SupplierRiskConfig).where(
        SupplierRiskConfig.rule_id == "R11",
        SupplierRiskConfig.supplier_id.is_(None),
        SupplierRiskConfig.product_line_code.is_(None),
    )
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.flush()
    inp = await _make_input(
        db,
        factory_id=default_factory.id,
        user_id=admin_user.user_id,
        supplier_id=seed_supplier.supplier_id,
        status="pending",
        max_attempts=3,
    )
    return inp, seed_supplier


async def _reload_input(db, input_id) -> SupplierRiskCapaInput:
    """Bypass identity-map staleness after flush-only commit + raw SQL updates."""
    return (
        await db.execute(
            select(SupplierRiskCapaInput)
            .where(SupplierRiskCapaInput.input_id == input_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_claim_batch_locks_pending(db, pending_input_factory):
    inp = await pending_input_factory()
    claimed = await claim_batch(db, 10)
    await db.commit()
    assert len(claimed) == 1
    assert claimed[0]["input_id"] == str(inp.input_id)
    assert claimed[0]["status"] == "processing"
    assert claimed[0]["claim_token"] is not None

    fresh = await _reload_input(db, inp.input_id)
    assert fresh.status == "processing"
    assert fresh.attempt_count == 1
    assert fresh.claim_token is not None
    assert fresh.locked_at is not None


@pytest.mark.asyncio
async def test_process_one_uses_claim_token_and_processes(db, pending_input_with_r11):
    """process_one 重锁 + claim_token 校验 + 成功 processed + 写 SENT。"""
    inp, _supplier = pending_input_with_r11
    claimed = await claim_batch(db, 10)
    await db.commit()
    assert len(claimed) == 1
    await process_one(db, claimed[0])
    await db.commit()

    fresh = await _reload_input(db, inp.input_id)
    assert fresh.status == "processed"
    assert fresh.claim_token is None
    assert fresh.evaluated_risk_level is not None
    assert fresh.evaluated_at is not None

    sent = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == inp.capa_id,
                AuditLog.action == "SUPPLIER_RISK_INPUT_SENT",
            )
        )
    ).scalars().all()
    assert len(sent) == 1
    cf = sent[0].changed_fields
    assert cf["risk_level"] == fresh.evaluated_risk_level
    assert "disposition" in cf
    assert cf["input_id"] == str(inp.input_id)
    assert cf["supplier_id"] == str(inp.supplier_id)


@pytest.mark.asyncio
async def test_process_one_aborts_when_claim_token_mismatch(db, pending_input_factory):
    """token 不匹配 → 放弃不处理。"""
    inp = await pending_input_factory()
    claimed = await claim_batch(db, 10)
    await db.commit()
    fake = dict(claimed[0])
    fake["claim_token"] = str(uuid.uuid4())
    await process_one(db, fake)
    await db.commit()

    fresh = await _reload_input(db, inp.input_id)
    assert fresh.status == "processing"


@pytest.mark.asyncio
async def test_process_one_failure_retries_then_error(db, pending_input_without_r11):
    """缺 R11 → raise → attempt 累加 + pending+next_retry；超 max → error。"""
    inp, _supplier = pending_input_without_r11
    claimed = await claim_batch(db, 10)
    await db.commit()
    for _ in range(inp.max_attempts + 1):
        await process_one(db, claimed[0])
        await db.commit()
        # Force next_retry ready so claim_batch can pick it up again
        await db.execute(
            text(
                "UPDATE supplier_risk_capa_inputs "
                "SET next_retry_at = NULL "
                "WHERE input_id = :id AND status = 'pending'"
            ),
            {"id": inp.input_id},
        )
        await db.commit()
        reclaimed = await claim_batch(db, 10)
        await db.commit()
        if not reclaimed:
            break
        claimed[0] = reclaimed[0]

    fresh = await _reload_input(db, inp.input_id)
    assert fresh.status == "error"
    assert fresh.last_error is not None
    sent = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == inp.capa_id,
                AuditLog.action == "SUPPLIER_RISK_INPUT_SENT",
            )
        )
    ).scalars().all()
    assert len(sent) == 0


@pytest.mark.asyncio
async def test_recover_stale_resets_old_processing(db, input_factory):
    """processing 超 10min → reset pending；达 max_attempts 的不重置为 pending，标 error。"""
    stale = await input_factory(
        status="processing",
        locked_at=datetime.now(timezone.utc) - timedelta(minutes=11),
        attempt_count=2,
        max_attempts=5,
        claim_token=uuid.uuid4(),
    )
    terminal = await input_factory(
        status="processing",
        locked_at=datetime.now(timezone.utc) - timedelta(minutes=11),
        attempt_count=6,
        max_attempts=5,
        claim_token=uuid.uuid4(),
    )
    stale_id = stale.input_id
    terminal_id = terminal.input_id
    await recover_stale_inputs(db)
    await db.commit()

    s = await _reload_input(db, stale_id)
    t = await _reload_input(db, terminal_id)
    assert s.status == "pending"
    assert s.locked_at is None
    assert s.claim_token is None
    assert t.status == "error"
    assert t.locked_at is None
    assert t.claim_token is None
