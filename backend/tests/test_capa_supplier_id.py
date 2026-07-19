"""CAPA supplier_id schema + create/update lifecycle (US-E2E-01.6 §4.1 / §4.5)."""
import uuid

import pytest

from app.schemas.capa import CAPACreate, CAPAResponse, CAPAUpdate


# ── Schema tests ────────────────────────────────────────────────────

def test_capa_create_accepts_supplier_id():
    sid = uuid.uuid4()
    c = CAPACreate(title="t", document_no="8D-T-001", supplier_id=sid)
    assert c.supplier_id == sid


def test_capa_create_supplier_id_optional():
    c = CAPACreate(title="t", document_no="8D-T-002")
    assert c.supplier_id is None


def test_capa_update_accepts_supplier_id():
    sid = uuid.uuid4()
    u = CAPAUpdate(supplier_id=sid)
    assert u.supplier_id == sid


def test_capa_response_includes_supplier_id():
    sid = uuid.uuid4()
    r = CAPAResponse.model_validate({
        "report_id": uuid.uuid4(),
        "document_no": "8D-T-003",
        "title": "t",
        "product_line_code": "DC-DC-100",
        "status": "D1_TEAM",
        "severity": "general",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "supplier_id": str(sid),
    })
    assert r.supplier_id == sid


# ── Service lifecycle (DB) ──────────────────────────────────────────

from app.models.capa import CAPAEightD
from app.models.factory import Factory
from app.models.supplier import Supplier
from app.models.supplier_risk_capa_input import SupplierRiskCapaInput
from app.services.capa_service import create_capa, update_capa


async def _async_noop(*_a, **_k):
    """No-op async stub for notification dispatch in real-commit tests."""
    return None




async def _make_capa(db, factory_id, user_id, status="D4_ROOT_CAUSE", **extra):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-SID-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status=status,
        **extra,
    )
    db.add(capa)
    await db.flush()
    return capa


async def _make_supplier(db, factory_id, user_id, *, supplier_no=None):
    supplier = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=supplier_no or f"SUP-{uuid.uuid4().hex[:8]}",
        name="Test Supplier",
        short_name="Test",
        factory_id=factory_id,
        status="approved",
        created_by=user_id,
    )
    db.add(supplier)
    await db.flush()
    return supplier


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_create_capa_persists_supplier_id(db, default_factory, admin_user):
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    capa = await create_capa(
        db,
        title="t",
        document_no=f"8D-CREATE-{uuid.uuid4().hex[:6]}",
        severity="严重",
        due_date=None,
        user_id=admin_user.user_id,
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        supplier_id=sup.supplier_id,
    )
    assert capa.supplier_id == sup.supplier_id


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_create_capa_rejects_cross_factory_supplier(db, default_factory, admin_user):
    other = Factory(id=uuid.uuid4(), code=f"OF-{uuid.uuid4().hex[:6]}", name="Other")
    db.add(other)
    await db.flush()
    other_supplier = await _make_supplier(db, other.id, admin_user.user_id)
    with pytest.raises(ValueError, match="同一工厂"):
        await create_capa(
            db,
            title="t",
            document_no=f"8D-CREATE-{uuid.uuid4().hex[:6]}",
            severity="严重",
            due_date=None,
            user_id=admin_user.user_id,
            product_line_code="DC-DC-100",
            factory_id=default_factory.id,
            supplier_id=other_supplier.supplier_id,
        )


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_create_capa_rejects_missing_supplier(db, default_factory, admin_user):
    with pytest.raises(ValueError, match="供应商不存在"):
        await create_capa(
            db,
            title="t",
            document_no=f"8D-CREATE-{uuid.uuid4().hex[:6]}",
            severity="严重",
            due_date=None,
            user_id=admin_user.user_id,
            product_line_code="DC-DC-100",
            factory_id=default_factory.id,
            supplier_id=uuid.uuid4(),
        )


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_rejects_cross_factory_supplier(db, default_factory, admin_user):
    """supplier 与 capa 不同厂 → ValueError。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status="D4_ROOT_CAUSE")
    other = Factory(id=uuid.uuid4(), code=f"OF-{uuid.uuid4().hex[:6]}", name="Other")
    db.add(other)
    await db.flush()
    other_supplier = await _make_supplier(db, other.id, admin_user.user_id)

    with pytest.raises(ValueError, match="同一工厂"):
        await update_capa(
            db, capa, {"supplier_id": other_supplier.supplier_id}, admin_user.user_id
        )


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_rejects_missing_supplier(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status="D4_ROOT_CAUSE")
    with pytest.raises(ValueError, match="供应商不存在"):
        await update_capa(db, capa, {"supplier_id": uuid.uuid4()}, admin_user.user_id)


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_allows_same_factory_supplier_before_d7(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status="D4_ROOT_CAUSE")
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    await update_capa(db, capa, {"supplier_id": sup.supplier_id}, admin_user.user_id)
    await db.refresh(capa)
    assert capa.supplier_id == sup.supplier_id


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_locks_supplier_id_after_d7_completed(db, default_factory, admin_user):
    """D7_COMPLETED 后改 supplier_id → ValueError。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status="D7_COMPLETED")
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    with pytest.raises(ValueError, match="D7"):
        await update_capa(db, capa, {"supplier_id": sup.supplier_id}, admin_user.user_id)


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_allows_same_supplier_id_after_d7(db, default_factory, admin_user):
    """同值重提在锁定态允许（未实际变更）。"""
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, status="D7_COMPLETED",
        supplier_id=sup.supplier_id,
    )
    await update_capa(db, capa, {"supplier_id": sup.supplier_id}, admin_user.user_id)
    await db.refresh(capa)
    assert capa.supplier_id == sup.supplier_id


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_locks_supplier_id_when_risk_input_exists_at_d7_prevention(
    db, default_factory, admin_user
):
    """D7_PREVENTION + existing SupplierRiskCapaInput → cannot change supplier_id."""
    sup_a = await _make_supplier(db, default_factory.id, admin_user.user_id, supplier_no="SUP-A")
    sup_b = await _make_supplier(db, default_factory.id, admin_user.user_id, supplier_no="SUP-B")
    capa = await _make_capa(
        db,
        default_factory.id,
        admin_user.user_id,
        status="D7_PREVENTION",
        supplier_id=sup_a.supplier_id,
    )
    db.add(
        SupplierRiskCapaInput(
            input_id=uuid.uuid4(),
            capa_id=capa.report_id,
            supplier_id=sup_a.supplier_id,
            factory_id=default_factory.id,
            product_line_code="DC-DC-100",
            created_by=admin_user.user_id,
            severity="严重",
            disposition="退货",
            repeat_suggested=True,
            repeat_confirmed=True,
            repeat_detection_status="matched",
            matched_capa_nos=["8D-2025-001"],
            status="pending",
        )
    )
    await db.flush()

    with pytest.raises(ValueError, match="已生成供应商风险输入"):
        await update_capa(db, capa, {"supplier_id": sup_b.supplier_id}, admin_user.user_id)


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_update_capa_allows_supplier_change_at_d7_prevention_without_risk_input(
    db, default_factory, admin_user
):
    """D7_PREVENTION without risk input → same-factory supplier change allowed."""
    sup_a = await _make_supplier(db, default_factory.id, admin_user.user_id, supplier_no="SUP-A2")
    sup_b = await _make_supplier(db, default_factory.id, admin_user.user_id, supplier_no="SUP-B2")
    capa = await _make_capa(
        db,
        default_factory.id,
        admin_user.user_id,
        status="D7_PREVENTION",
        supplier_id=sup_a.supplier_id,
    )
    await update_capa(db, capa, {"supplier_id": sup_b.supplier_id}, admin_user.user_id)
    await db.refresh(capa)
    assert capa.supplier_id == sup_b.supplier_id


@pytest.mark.asyncio
async def test_evaluate_in_tx_takes_advisory_lock(db, admin_user, default_factory):
    """Shared evaluate path must take supplier-level advisory lock (worker+confirm+rollup)."""
    from app.services.supplier_risk.service import evaluate_supplier_risk_in_tx
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierRiskConfig
    from sqlalchemy import text as sa_text

    sup = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"SUP-LOCK-{uuid.uuid4().hex[:6]}",
        name="Lock Sup",
        short_name="LS",
        factory_id=default_factory.id,
        status="approved",
        created_by=admin_user.user_id,
    )
    db.add(sup)
    await db.flush()
    # Supplier-scoped R01 (avoids unique global idx_risk_config_global).
    db.add(SupplierRiskConfig(
        rule_id="R01", enabled=True, category="quality", weight=1.0,
        thresholds={}, factory_id=default_factory.id, supplier_id=sup.supplier_id,
        updated_by=admin_user.user_id,
    ))
    await db.flush()

    # Ensure no leftover locks in this session
    await evaluate_supplier_risk_in_tx(db, sup.supplier_id, "DC-DC-100")
    # If advisory lock path is broken (bad SQL), the call raises — that's the assertion.
    # Additionally verify pg_locks has an exclusive advisory lock for this backend pid after
    # a non-committing call still holds xact lock until commit/rollback of outer fixture txn.
    locks = (await db.execute(sa_text(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted"
    ))).scalar()
    assert locks is not None and locks >= 1


@pytest.mark.asyncio
async def test_evaluate_in_tx_lock_key_ignores_product_line(db, admin_user, default_factory, monkeypatch):
    """PL-scoped and rollup paths must share supplier-level lock key (not PL-scoped)."""
    from app.services.supplier_risk import service as risk_service
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierRiskConfig

    sup = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"SUP-LK-{uuid.uuid4().hex[:6]}",
        name="Lock Key Sup",
        short_name="LKS",
        factory_id=default_factory.id,
        status="approved",
        created_by=admin_user.user_id,
    )
    db.add(sup)
    await db.flush()
    db.add(SupplierRiskConfig(
        rule_id="R01", enabled=True, category="quality", weight=1.0,
        thresholds={}, factory_id=default_factory.id, supplier_id=sup.supplier_id,
        updated_by=admin_user.user_id,
    ))
    await db.flush()

    captured_keys: list[str] = []
    real_execute = db.execute

    async def capture_execute(stmt, params=None, **kwargs):
        if params and isinstance(params, dict) and "key" in params:
            captured_keys.append(params["key"])
        return await real_execute(stmt, params, **kwargs)

    monkeypatch.setattr(db, "execute", capture_execute)

    await risk_service.evaluate_supplier_risk_in_tx(db, sup.supplier_id, "DC-DC-100")
    await risk_service.evaluate_supplier_risk_in_tx(db, sup.supplier_id, None)

    assert len(captured_keys) >= 2
    expected = f"supplier-risk:{sup.supplier_id}"
    assert captured_keys[0] == expected
    assert captured_keys[1] == expected
    assert captured_keys[0] == captured_keys[1]


@pytest.mark.asyncio
async def test_evaluate_in_tx_uses_preloaded_without_re_gather(db, admin_user, default_factory, monkeypatch):
    """Batch path preloaded= must skip per-supplier gather N+1 for stable inputs.

    CAPA inputs are intentionally always re-queried under the lock.
    """
    from app.services.supplier_risk import service as risk_service
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierRiskConfig

    sup = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"SUP-PRE-{uuid.uuid4().hex[:6]}",
        name="Preload Sup",
        short_name="PS",
        factory_id=default_factory.id,
        status="approved",
        created_by=admin_user.user_id,
    )
    db.add(sup)
    cfg = SupplierRiskConfig(
        rule_id="R01", enabled=True, category="quality", weight=1.0,
        thresholds={}, factory_id=default_factory.id, supplier_id=sup.supplier_id,
        updated_by=admin_user.user_id,
    )
    db.add(cfg)
    await db.flush()

    async def boom(*_a, **_k):
        raise AssertionError("gather should not be called when preloaded")

    capa_calls = {"n": 0}
    real_gather_capa = risk_service._gather_capa_inputs

    async def track_capa(*a, **k):
        capa_calls["n"] += 1
        return await real_gather_capa(*a, **k)

    monkeypatch.setattr(risk_service, "_gather_inspections", boom)
    monkeypatch.setattr(risk_service, "_gather_scars", boom)
    monkeypatch.setattr(risk_service, "_gather_evaluations", boom)
    monkeypatch.setattr(risk_service, "_gather_certifications", boom)
    monkeypatch.setattr(risk_service, "_gather_capa_inputs", track_capa)

    alert, score, *_ = await risk_service.evaluate_supplier_risk_in_tx(
        db, sup.supplier_id, "DC-DC-100",
        preloaded={
            "supplier": sup,
            "configs": [cfg],
            "inspections": [],
            "scars": [],
            "evaluations": [],
            "certifications": [],
            # stale CAPA snapshot must be ignored
            "capa_incidents": ["stale-must-not-be-used"],
        },
    )
    assert score is not None
    assert capa_calls["n"] == 1


@pytest.mark.asyncio
async def test_evaluate_in_tx_ignores_preloaded_capa_incidents(
    db, admin_user, default_factory, monkeypatch,
):
    """Even if preloaded contains capa_incidents, under-lock re-query wins."""
    from app.services.supplier_risk import service as risk_service
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierRiskConfig

    sup = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"SUP-CAPA-{uuid.uuid4().hex[:6]}",
        name="Capa Fresh Sup",
        short_name="CFS",
        factory_id=default_factory.id,
        status="approved",
        created_by=admin_user.user_id,
    )
    db.add(sup)
    cfg = SupplierRiskConfig(
        rule_id="R01", enabled=True, category="quality", weight=1.0,
        thresholds={}, factory_id=default_factory.id, supplier_id=sup.supplier_id,
        updated_by=admin_user.user_id,
    )
    db.add(cfg)
    await db.flush()

    sentinel = object()
    called = {"n": 0}

    async def fake_gather(db_, sid, pl):
        called["n"] += 1
        assert sid == sup.supplier_id
        return [sentinel]

    monkeypatch.setattr(risk_service, "_gather_capa_inputs", fake_gather)

    # Capture incidents passed into run_all_rules
    captured = {}
    real_run = risk_service.run_all_rules

    def wrap_run(input_data, configs):
        captured["incidents"] = input_data.capa_incidents
        return real_run(input_data, configs)

    monkeypatch.setattr(risk_service, "run_all_rules", wrap_run)

    await risk_service.evaluate_supplier_risk_in_tx(
        db, sup.supplier_id, "DC-DC-100",
        preloaded={
            "supplier": sup,
            "configs": [cfg],
            "inspections": [],
            "scars": [],
            "evaluations": [],
            "certifications": [],
            "capa_incidents": ["stale"],
        },
    )
    assert called["n"] == 1
    assert captured["incidents"] == [sentinel]


@pytest.mark.asyncio
async def test_evaluate_all_continues_after_one_supplier_fails(
    db, admin_user, default_factory, monkeypatch,
):
    """One supplier failure must not cascade-skip later suppliers (savepoint isolation).

    Uses deterministic supplier_no ordering so the bad supplier is first; the
    good supplier must still complete after the bad one's evaluation exception.
    """
    from app.services.supplier_risk import service as risk_service
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierRiskConfig

    suffix = uuid.uuid4().hex[:6]
    # Lexicographic order: AAA-BAD before ZZZ-GOOD under ORDER BY supplier_no.
    bad = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"AAA-BAD-{suffix}",
        name="Bad Sup",
        short_name="BAD",
        factory_id=default_factory.id,
        status="approved",
        created_by=admin_user.user_id,
    )
    good = Supplier(
        supplier_id=uuid.uuid4(),
        supplier_no=f"ZZZ-GOOD-{suffix}",
        name="Good Sup",
        short_name="GOOD",
        factory_id=default_factory.id,
        status="approved",
        created_by=admin_user.user_id,
    )
    db.add_all([bad, good])
    # Supplier-scoped configs so residual global R01 is not required / collided.
    for sid in (bad.supplier_id, good.supplier_id):
        db.add(SupplierRiskConfig(
            rule_id="R01", enabled=True, category="quality", weight=1.0,
            thresholds={}, factory_id=default_factory.id, product_line_code=None,
            supplier_id=sid, updated_by=admin_user.user_id,
        ))
    await db.flush()

    real_eval = risk_service.evaluate_supplier_risk_in_tx
    order = []

    async def flaky(db_, supplier_id, product_line_code=None, **kwargs):
        order.append(supplier_id)
        if supplier_id == bad.supplier_id:
            raise RuntimeError("boom-for-bad-supplier")
        return await real_eval(db_, supplier_id, product_line_code, **kwargs)

    monkeypatch.setattr(risk_service, "evaluate_supplier_risk_in_tx", flaky)

    results = await risk_service.evaluate_all_suppliers(db, product_line_code=None)
    ids = {r["supplier_id"] for r in results}
    assert good.supplier_id in ids
    assert bad.supplier_id not in ids
    # Bad ran before good under deterministic ORDER BY supplier_no.
    assert bad.supplier_id in order and good.supplier_id in order
    assert order.index(bad.supplier_id) < order.index(good.supplier_id)


@pytest.mark.asyncio
async def test_evaluate_in_tx_sees_concurrent_capa_under_lock(sessionmaker, monkeypatch):
    """Worker holds supplier lock + commits CAPA; daily rollup waits, then re-queries.

    Real race modeled (e2366732 freshness contract):
    1. worker/confirm acquires supplier-level advisory lock and pauses under lock
       (after CAPA write is committed in the same xact path)
    2. daily rollup starts evaluate_supplier_risk_in_tx and blocks on the same lock
    3. worker commits + releases lock
    4. daily acquires lock, re-queries CAPA under lock, must see worker's row

    Timeouts on all waits; unfinished tasks cancelled in finally so a failed
    assertion cannot leave a hung CI session.
    """
    import asyncio
    from datetime import datetime, timezone
    from app.services.supplier_risk import service as risk_service
    from app.models.capa import CAPAEightD
    from app.models.factory import Factory
    from app.models.role import RoleDefinition
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierRiskConfig
    from app.models.supplier_risk_capa_input import SupplierRiskCapaInput
    from app.models.user import User
    from sqlalchemy import select, delete, text as sa_text

    factory_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:8]
    user_id = uuid.uuid4()
    supplier_id = uuid.uuid4()
    capa_id = uuid.uuid4()
    input_id = uuid.uuid4()
    created_role_id = None
    lock_key = f"supplier-risk:{supplier_id}"

    async with sessionmaker() as setup:
        # Unique role_key per test — no shared admin unique-key race in parallel CI.
        role = RoleDefinition(
            role_key=f"tadm_{suffix}", name_zh="admin", name_en="admin",
            is_system=False, is_editable=True, bypass_row_level_security=True,
            sort_order=99, is_active=True,
        )
        setup.add(role)
        await setup.flush()
        created_role_id = role.id
        setup.add(Factory(id=factory_id, code=f"LK{suffix[:4]}", name=f"LockFresh {suffix}"))
        await setup.flush()
        setup.add(User(
            user_id=user_id, username=f"test_lock_fresh_{suffix}",
            display_name="LF", password_hash="x", role_id=role.id,
            legacy_role="admin", is_active=True, factory_id=factory_id,
        ))
        await setup.flush()
        setup.add(Supplier(
            supplier_id=supplier_id, supplier_no=f"SUP-LF-{suffix}",
            name="Lock Fresh Sup", short_name="LF",
            factory_id=factory_id, status="approved", created_by=user_id,
        ))
        await setup.flush()  # supplier before CAPA FK
        setup.add(SupplierRiskConfig(
            rule_id="R01", enabled=True, category="quality", weight=1.0,
            thresholds={}, factory_id=factory_id, product_line_code=None,
            supplier_id=supplier_id, updated_by=user_id,
        ))
        # CAPA row required for FK from capa_input
        setup.add(CAPAEightD(
            report_id=capa_id, document_no=f"8D-LF-{suffix}",
            title="lock fresh", product_line_code="DC-DC-100",
            factory_id=factory_id, created_by=user_id,
            status="D7_COMPLETED", supplier_id=supplier_id,
        ))
        await setup.commit()

    worker_locked = asyncio.Event()
    daily_entered_lock = asyncio.Event()  # set when daily issues blocking lock SQL
    daily_under_lock_gather = asyncio.Event()
    captured = {}
    real_gather = risk_service._gather_capa_inputs
    WAIT = 5.0

    async def gated_gather(db_, sid, pl):
        # Daily path (PL set): under lock after blocking acquire; capture CAPA.
        if pl == "DC-DC-100":
            daily_under_lock_gather.set()
            rows = await real_gather(db_, sid, pl)
            captured["ids"] = [r.input_id for r in rows]
            return rows
        return await real_gather(db_, sid, pl)

    monkeypatch.setattr(risk_service, "_gather_capa_inputs", gated_gather)

    async def worker():
        """worker/confirm: take supplier lock, write CAPA, wait for daily to block, commit."""
        async with sessionmaker() as w:
            await w.execute(
                sa_text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": lock_key},
            )
            w.add(SupplierRiskCapaInput(
                input_id=input_id,
                capa_id=capa_id,
                supplier_id=supplier_id,
                factory_id=factory_id,
                product_line_code="DC-DC-100",
                created_by=user_id,
                severity="一般",
                repeat_detection_status="not_matched",
                matched_capa_nos=[],
                status="processed",
                created_at=datetime.now(timezone.utc),
            ))
            await w.flush()
            worker_locked.set()
            # Wait until daily has *issued* the blocking lock SQL...
            await asyncio.wait_for(daily_entered_lock.wait(), timeout=WAIT)
            # ...and is actually waiting in pg_locks (NOT granted). Poll, not sleep.
            async with sessionmaker() as probe:
                deadline = asyncio.get_event_loop().time() + WAIT
                while True:
                    waiting = (await probe.execute(sa_text(
                        "SELECT count(*) FROM pg_locks "
                        "WHERE locktype = 'advisory' AND NOT granted"
                    ))).scalar() or 0
                    if waiting >= 1:
                        break
                    if asyncio.get_event_loop().time() >= deadline:
                        raise AssertionError(
                            "daily never appeared as waiting on advisory lock in pg_locks"
                        )
                    await asyncio.sleep(0.02)
            await w.commit()  # releases xact advisory lock

    async def daily():
        """daily rollup: blocks on same lock until worker commits, then re-queries."""
        await asyncio.wait_for(worker_locked.wait(), timeout=WAIT)
        # Prove worker still holds the lock before we start (try_lock fails).
        async with sessionmaker() as probe:
            got = (await probe.execute(sa_text(
                "SELECT pg_try_advisory_xact_lock(hashtext(:key))"
            ), {"key": lock_key})).scalar()
            assert got is False, "expected worker to hold supplier advisory lock"
            await probe.rollback()

        async with sessionmaker() as d:
            real_execute = d.execute

            async def execute_mark_lock(stmt, params=None, **kwargs):
                # Mark that daily is about to issue the blocking lock SQL, then
                # actually block. Worker waits for the mark + pg_locks wait row.
                try:
                    text_sql = str(getattr(stmt, "text", stmt))
                except Exception:
                    text_sql = str(stmt)
                if (
                    "pg_advisory_xact_lock" in text_sql
                    and isinstance(params, dict)
                    and params.get("key") == lock_key
                ):
                    daily_entered_lock.set()
                return await real_execute(stmt, params, **kwargs)

            d.execute = execute_mark_lock
            await risk_service.evaluate_supplier_risk_in_tx(
                d, supplier_id, "DC-DC-100",
            )
            await d.commit()

    async def _cancel_wait(ts, timeout=WAIT):
        for t in ts:
            if not t.done():
                t.cancel()
        if not ts:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*ts, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            pass

    tasks = []
    try:
        tasks = [asyncio.create_task(worker(), name="worker"),
                 asyncio.create_task(daily(), name="daily")]
        done, pending = await asyncio.wait(tasks, timeout=WAIT * 2)
        if pending:
            await _cancel_wait(list(pending))
            raise AssertionError("concurrency test timed out — hung task/txn")
        for t in done:
            exc = t.exception()
            if exc is not None:
                raise exc
        assert daily_entered_lock.is_set(), "daily never entered blocking lock SQL"
        assert daily_under_lock_gather.is_set(), "daily never reached under-lock CAPA re-query"
        assert input_id in captured.get("ids", []), (
            f"daily under-lock re-query missed worker CAPA input; saw={captured}"
        )
    finally:
        # Unblock any waiter and cancel leftovers so CI cannot hang.
        worker_locked.set()
        daily_entered_lock.set()
        await _cancel_wait(tasks)
        async with sessionmaker() as cleanup:
            await cleanup.execute(
                delete(SupplierRiskCapaInput).where(SupplierRiskCapaInput.input_id == input_id)
            )
            await cleanup.execute(
                delete(SupplierRiskConfig).where(SupplierRiskConfig.factory_id == factory_id)
            )
            await cleanup.execute(sa_text(
                "DELETE FROM supplier_risk_alerts WHERE supplier_id = :sid"
            ), {"sid": supplier_id})
            await cleanup.execute(delete(CAPAEightD).where(CAPAEightD.report_id == capa_id))
            await cleanup.execute(delete(Supplier).where(Supplier.supplier_id == supplier_id))
            await cleanup.execute(delete(User).where(User.user_id == user_id))
            await cleanup.execute(delete(Factory).where(Factory.id == factory_id))
            if created_role_id is not None:
                # Only drop roles this test created (empty-DB path).
                await cleanup.execute(
                    delete(RoleDefinition).where(RoleDefinition.id == created_role_id)
                )
            await cleanup.commit()


@pytest.mark.asyncio
async def test_evaluate_all_commit_failure_does_not_cascade(sessionmaker, monkeypatch):
    """A real commit() failure on one supplier must not cascade-kill the rest.

    Regression guard: full-session rollback() after a commit failure expires
    every preloaded ORM object in the identity map (expire_on_commit=False
    does NOT protect against rollback). If the batch loop iterates ORM
    objects, the next iteration's ``supplier.supplier_id`` access triggers a
    lazy refresh on the async session -> MissingGreenlet, aborting the whole
    batch. Uses the real-commit ``sessionmaker`` fixture so commit()/rollback()
    are real (not the db fixture's flush-only stub).
    """
    from app.services.supplier_risk import service as risk_service
    from app.models.factory import Factory
    from app.models.role import RoleDefinition
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierRiskConfig
    from app.models.user import User
    from sqlalchemy import select, delete

    # Unique factory so residual shared-test data cannot collide.
    factory_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:8]
    bad_no = f"SUP-CFAIL-{suffix}"
    good_no = f"SUP-COK-{suffix}"
    user_id = uuid.uuid4()
    created_role_id = None
    bad_id = uuid.uuid4()
    good_id = uuid.uuid4()

    async with sessionmaker() as setup:
        role = RoleDefinition(
            role_key=f"tadm_{suffix}", name_zh="admin", name_en="admin",
            is_system=False, is_editable=True, bypass_row_level_security=True,
            sort_order=99, is_active=True,
        )
        setup.add(role)
        await setup.flush()
        created_role_id = role.id

        setup.add(Factory(id=factory_id, code=f"CF{suffix[:4]}", name=f"CommitFail {suffix}"))
        await setup.flush()

        user = User(
            user_id=user_id, username=f"test_commit_fail_{suffix}",
            display_name="CF", password_hash="x", role_id=role.id,
            legacy_role="admin", is_active=True, factory_id=factory_id,
        )
        setup.add(user)
        await setup.flush()  # UUID FK, not relationship — force user before suppliers

        # Deterministic supplier_no: bad sorts before good.
        setup.add(Supplier(
            supplier_id=bad_id, supplier_no=bad_no, name="Bad Sup",
            short_name="CF", factory_id=factory_id, status="approved",
            created_by=user_id,
        ))
        setup.add(Supplier(
            supplier_id=good_id, supplier_no=good_no, name="Good Sup",
            short_name="CO", factory_id=factory_id, status="approved",
            created_by=user_id,
        ))
        await setup.flush()
        # Supplier-scoped configs avoid the unique global R01 index.
        for sid in (bad_id, good_id):
            setup.add(SupplierRiskConfig(
                rule_id="R01", enabled=True, category="quality", weight=1.0,
                thresholds={}, factory_id=factory_id, product_line_code=None,
                supplier_id=sid, updated_by=user_id,
            ))
        await setup.commit()

    owned = {bad_id, good_id}

    try:
        async with sessionmaker() as db:
            # Scope evaluation to this test's suppliers only — evaluate_all_suppliers
            # otherwise walks every approved row in the shared test DB, leaving
            # residual alert updates and potentially firing real notification channels.
            current = {"sid": None}
            real_eval = risk_service.evaluate_supplier_risk_in_tx

            async def track_eval(db_, supplier_id, product_line_code=None, **kwargs):
                if supplier_id not in owned:
                    raise RuntimeError("skip-residual-supplier")
                current["sid"] = supplier_id
                return await real_eval(db_, supplier_id, product_line_code, **kwargs)

            monkeypatch.setattr(risk_service, "evaluate_supplier_risk_in_tx", track_eval)
            # Never dispatch network notifications from real-commit tests.
            monkeypatch.setattr(
                "app.services.supplier_risk.notifier.send_notifications_by_alert_id",
                _async_noop,
            )
            monkeypatch.setattr(
                "app.services.supplier_risk.notifier.send_notifications",
                _async_noop,
            )

            original_commit = db.commit

            async def flaky_commit():
                if current["sid"] == bad_id:
                    # Fail once for the bad supplier, then allow later retries
                    # (evaluate_all_suppliers continues past this supplier).
                    if not current.get("failed"):
                        current["failed"] = True
                        raise RuntimeError("simulated commit failure for bad supplier")
                return await original_commit()

            db.commit = flaky_commit
            results = await risk_service.evaluate_all_suppliers(db, product_line_code=None)

        good_ids = {r["supplier_id"] for r in results}
        assert good_id in good_ids, (
            f"good supplier dropped after bad supplier commit failure; results={results}"
        )
        assert bad_id not in good_ids
        assert current.get("failed") is True, "flaky commit never fired for bad supplier"
        # No residual suppliers should appear in results.
        assert good_ids <= owned
    finally:
        async with sessionmaker() as cleanup:
            from app.models.supplier_risk import SupplierRiskAlert
            from sqlalchemy import text as sa_text
            await cleanup.execute(
                delete(SupplierRiskAlert).where(SupplierRiskAlert.supplier_id.in_([bad_id, good_id]))
            )
            await cleanup.execute(
                delete(SupplierRiskConfig).where(SupplierRiskConfig.factory_id == factory_id)
            )
            await cleanup.execute(delete(Supplier).where(Supplier.supplier_id.in_([bad_id, good_id])))
            await cleanup.execute(delete(User).where(User.user_id == user_id))
            await cleanup.execute(delete(Factory).where(Factory.id == factory_id))
            if created_role_id is not None:
                from app.models.role import RoleDefinition
                await cleanup.execute(
                    delete(RoleDefinition).where(RoleDefinition.id == created_role_id)
                )
            await cleanup.commit()


@pytest.mark.asyncio
async def test_evaluate_all_commit_failure_survives_next_chunk(sessionmaker, monkeypatch):
    """commit() failure in chunk N must not MissingGreenlet-kill chunk N+1.

    All Supplier ORM is loaded up front; a root rollback expires every identity-map
    state. Chunk N may copy plain IDs before the failure, but entering chunk N+1
    via ``s.supplier_id`` on the original ORM list re-triggers lazy IO on the
    async session. Force chunk size=1 so three suppliers span three chunks.
    """
    from app.services.supplier_risk import service as risk_service
    from app.models.factory import Factory
    from app.models.role import RoleDefinition
    from app.models.supplier import Supplier
    from app.models.supplier_risk import SupplierRiskConfig
    from app.models.user import User
    from sqlalchemy import select, delete

    factory_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:8]
    user_id = uuid.uuid4()
    created_role_id = None
    # Lexicographic order under ORDER BY supplier_no: bad first, then good1, good2.
    bad_id = uuid.uuid4()
    good1_id = uuid.uuid4()
    good2_id = uuid.uuid4()
    bad_no = f"AAA-CFAIL-{suffix}"
    good1_no = f"BBB-COK1-{suffix}"
    good2_no = f"CCC-COK2-{suffix}"

    async with sessionmaker() as setup:
        role = RoleDefinition(
            role_key=f"tadm_{suffix}", name_zh="admin", name_en="admin",
            is_system=False, is_editable=True, bypass_row_level_security=True,
            sort_order=99, is_active=True,
        )
        setup.add(role)
        await setup.flush()
        created_role_id = role.id
        setup.add(Factory(id=factory_id, code=f"MC{suffix[:4]}", name=f"MultiChunk {suffix}"))
        await setup.flush()
        setup.add(User(
            user_id=user_id, username=f"test_multi_chunk_{suffix}",
            display_name="MC", password_hash="x", role_id=role.id,
            legacy_role="admin", is_active=True, factory_id=factory_id,
        ))
        await setup.flush()
        for sid, sno, name, sn in (
            (bad_id, bad_no, "Bad", "B"),
            (good1_id, good1_no, "Good1", "G1"),
            (good2_id, good2_no, "Good2", "G2"),
        ):
            setup.add(Supplier(
                supplier_id=sid, supplier_no=sno, name=name, short_name=sn,
                factory_id=factory_id, status="approved", created_by=user_id,
            ))
        await setup.flush()
        for sid in (bad_id, good1_id, good2_id):
            setup.add(SupplierRiskConfig(
                rule_id="R01", enabled=True, category="quality", weight=1.0,
                thresholds={}, factory_id=factory_id, product_line_code=None,
                supplier_id=sid, updated_by=user_id,
            ))
        await setup.commit()

    monkeypatch.setattr(risk_service, "EVALUATE_ALL_CHUNK_SIZE", 1)

    owned = {bad_id, good1_id, good2_id}

    try:
        async with sessionmaker() as db:
            current = {"sid": None}
            real_eval = risk_service.evaluate_supplier_risk_in_tx

            async def track_eval(db_, supplier_id, product_line_code=None, **kwargs):
                # Isolate from residual approved suppliers in the shared test DB.
                if supplier_id not in owned:
                    raise RuntimeError("skip-residual-supplier")
                current["sid"] = supplier_id
                return await real_eval(db_, supplier_id, product_line_code, **kwargs)

            monkeypatch.setattr(risk_service, "evaluate_supplier_risk_in_tx", track_eval)
            monkeypatch.setattr(
                "app.services.supplier_risk.notifier.send_notifications_by_alert_id",
                _async_noop,
            )
            monkeypatch.setattr(
                "app.services.supplier_risk.notifier.send_notifications",
                _async_noop,
            )

            original_commit = db.commit

            async def flaky_commit():
                if current["sid"] == bad_id and not current.get("failed"):
                    current["failed"] = True
                    raise RuntimeError("simulated commit failure for bad supplier")
                return await original_commit()

            db.commit = flaky_commit
            results = await risk_service.evaluate_all_suppliers(db, product_line_code=None)

        ids = {r["supplier_id"] for r in results}
        assert good1_id in ids, f"good1 (chunk 2) dropped after chunk-1 commit fail; results={results}"
        assert good2_id in ids, f"good2 (chunk 3) dropped after chunk-1 commit fail; results={results}"
        assert bad_id not in ids
        assert current.get("failed") is True
        assert ids <= owned
    finally:
        async with sessionmaker() as cleanup:
            from app.models.supplier_risk import SupplierRiskAlert
            await cleanup.execute(
                delete(SupplierRiskAlert).where(
                    SupplierRiskAlert.supplier_id.in_([bad_id, good1_id, good2_id])
                )
            )
            await cleanup.execute(
                delete(SupplierRiskConfig).where(SupplierRiskConfig.factory_id == factory_id)
            )
            await cleanup.execute(
                delete(Supplier).where(Supplier.supplier_id.in_([bad_id, good1_id, good2_id]))
            )
            await cleanup.execute(delete(User).where(User.user_id == user_id))
            await cleanup.execute(delete(Factory).where(Factory.id == factory_id))
            if created_role_id is not None:
                from app.models.role import RoleDefinition
                await cleanup.execute(
                    delete(RoleDefinition).where(RoleDefinition.id == created_role_id)
                )
            await cleanup.commit()



@pytest.mark.asyncio
async def test_update_capa_clears_supplier_when_unlocked(db, admin_user, default_factory):
    """Pre-D7, no risk input: supplier_id=null clears the association."""
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        status="D4_ROOT_CAUSE", supplier_id=sup.supplier_id,
    )
    await update_capa(db, capa, {"supplier_id": None}, admin_user.user_id)
    await db.refresh(capa)
    assert capa.supplier_id is None


@pytest.mark.asyncio
async def test_update_capa_clear_supplier_blocked_when_input_exists(
    db, admin_user, default_factory,
):
    """Cannot clear supplier once risk input exists."""
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        status="D7_PREVENTION", supplier_id=sup.supplier_id,
    )
    db.add(SupplierRiskCapaInput(
        input_id=uuid.uuid4(),
        capa_id=capa.report_id,
        supplier_id=sup.supplier_id,
        factory_id=default_factory.id,
        product_line_code="DC-DC-100",
        created_by=admin_user.user_id,
        severity="一般",
        repeat_detection_status="not_matched",
        matched_capa_nos=[],
        status="pending",
    ))
    await db.flush()
    with pytest.raises(ValueError, match="供应商风险输入"):
        await update_capa(db, capa, {"supplier_id": None}, admin_user.user_id)


@pytest.mark.asyncio
async def test_get_capa_projects_supplier_no_and_name(
    admin_client, db, admin_user, default_factory,
):
    """GET /capa/{id} projects supplier_no/name so locked UI is not a raw UUID."""
    sup = await _make_supplier(
        db, default_factory.id, admin_user.user_id, supplier_no="SUP-LABEL-01",
    )
    # _make_supplier may not set name uniquely; ensure known label
    sup.name = "Label Supplier Co"
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        status="D7_COMPLETED", supplier_id=sup.supplier_id,
    )
    await db.flush()

    resp = await admin_client.get(f"/api/capa/{capa.report_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["supplier_id"] == str(sup.supplier_id)
    assert body["supplier_no"] == "SUP-LABEL-01"
    assert body["supplier_name"] == "Label Supplier Co"


def test_capa_response_schema_includes_supplier_labels():
    sid = uuid.uuid4()
    r = CAPAResponse.model_validate({
        "report_id": uuid.uuid4(),
        "document_no": "8D-T-LABEL",
        "title": "t",
        "product_line_code": "DC-DC-100",
        "status": "D7_COMPLETED",
        "severity": "general",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "supplier_id": str(sid),
        "supplier_no": "SUP-X",
        "supplier_name": "X Co",
    })
    assert r.supplier_no == "SUP-X"
    assert r.supplier_name == "X Co"



@pytest.mark.asyncio
async def test_update_capa_product_line_frozen_when_input_exists(
    db, admin_user, default_factory,
):
    """Once risk input exists, product_line_code cannot change (align with supplier freeze)."""
    from app.models.product_line import ProductLine
    from app.models.supplier_risk_capa_input import SupplierRiskCapaInput
    from app.services.capa_service import update_capa

    # Ensure a second PL in same factory
    other_pl = (await db.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(ProductLine).where(ProductLine.code == "ALT-PL")
    )).scalar_one_or_none()
    if other_pl is None:
        db.add(ProductLine(code="ALT-PL", name="Alt", factory_id=default_factory.id, is_active=True))
        await db.flush()

    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        status="D4_ROOT_CAUSE", supplier_id=sup.supplier_id,
    )
    # force product line
    capa.product_line_code = "DC-DC-100"
    db.add(SupplierRiskCapaInput(
        input_id=uuid.uuid4(),
        capa_id=capa.report_id,
        supplier_id=sup.supplier_id,
        factory_id=default_factory.id,
        product_line_code="DC-DC-100",
        created_by=admin_user.user_id,
        severity="一般",
        repeat_detection_status="not_matched",
        matched_capa_nos=[],
        status="pending",
    ))
    await db.flush()
    with pytest.raises(ValueError, match="产品线"):
        await update_capa(db, capa, {"product_line_code": "ALT-PL"}, admin_user.user_id)
