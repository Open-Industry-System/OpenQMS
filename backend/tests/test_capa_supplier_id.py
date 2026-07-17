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
    # minimal R01 so configs non-empty
    db.add(SupplierRiskConfig(
        rule_id="R01", enabled=True, category="quality", weight=1.0,
        thresholds={}, factory_id=default_factory.id, updated_by=admin_user.user_id,
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
    db.add(SupplierRiskConfig(
        rule_id="R01", enabled=True, category="quality", weight=1.0,
        thresholds={}, factory_id=default_factory.id, updated_by=admin_user.user_id,
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
    """Batch path preloaded= must skip per-supplier gather N+1."""
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
        thresholds={}, factory_id=default_factory.id, updated_by=admin_user.user_id,
    )
    db.add(cfg)
    await db.flush()

    async def boom(*_a, **_k):
        raise AssertionError("gather should not be called when preloaded")

    monkeypatch.setattr(risk_service, "_gather_inspections", boom)
    monkeypatch.setattr(risk_service, "_gather_scars", boom)
    monkeypatch.setattr(risk_service, "_gather_evaluations", boom)
    monkeypatch.setattr(risk_service, "_gather_certifications", boom)
    monkeypatch.setattr(risk_service, "_gather_capa_inputs", boom)

    alert, score, *_ = await risk_service.evaluate_supplier_risk_in_tx(
        db, sup.supplier_id, "DC-DC-100",
        preloaded={
            "supplier": sup,
            "configs": [cfg],
            "inspections": [],
            "scars": [],
            "evaluations": [],
            "certifications": [],
            "capa_incidents": [],
        },
    )
    assert score is not None


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
