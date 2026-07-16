"""advance_capa D7_COMPLETED writes supplier risk input outbox (US-E2E-01.6)."""
import uuid

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.supplier import Supplier
from app.models.supplier_risk_capa_input import SupplierRiskCapaInput
from app.schemas.capa import AdvanceRequest
from app.schemas.capa_verification import D7NodeActionCreate
from app.services.capa_d7_action_service import record_d7_action
from app.services.capa_service import advance_capa
from app.state_machines.eightd_state import EightDState

pytestmark = pytest.mark.requires_db


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


async def _make_capa(db, factory_id, user_id, status="D7_PREVENTION", **extra):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-SR-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status=status,
        d5_correction="措施A",
        d6_verification="已验证",
        d7_prevention="预防措施",
        **extra,
    )
    db.add(capa)
    await db.flush()
    return capa


async def _make_fmea(db, factory_id, user_id):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no=f"PFMEA-SR-{uuid.uuid4().hex[:6]}",
        title="t",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        status="draft",
        created_by=user_id,
        graph_data={
            "nodes": [
                {"id": "fm-1", "type": "FailureMode", "name": "虚焊"},
                {"id": "c-1", "type": "FailureCause", "name": "参数偏移"},
            ],
            "edges": [{"source": "c-1", "target": "fm-1", "type": "CAUSE_OF"}],
        },
    )
    db.add(fmea)
    await db.flush()
    return fmea


async def _seed_d7_action(db, capa, fmea, user):
    """Satisfy _d7_completion_gate for linked FM+cause recommendation."""
    capa.fmea_ref_id = fmea.fmea_id
    capa.fmea_node_id = "fm-1"
    await db.flush()
    await record_d7_action(
        db,
        capa,
        D7NodeActionCreate(
            action="confirmed",
            fmea_id=fmea.fmea_id,
            failure_mode_node_id="fm-1",
            failure_cause_node_id="c-1",
            match_source="linked",
        ),
        user,
    )


@pytest.mark.asyncio
async def test_advance_to_d7_completed_writes_pending_input(db, default_factory, admin_user):
    """D7_PREVENTION→D7_COMPLETED 且有 supplier_id → 写 pending input + QUEUED 审计。"""
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, supplier_id=sup.supplier_id
    )
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _seed_d7_action(db, capa, fmea, admin_user)

    await advance_capa(
        db, capa, admin_user.user_id, AdvanceRequest(target_state=EightDState.D7_COMPLETED)
    )

    inp = (
        await db.execute(
            select(SupplierRiskCapaInput).where(SupplierRiskCapaInput.capa_id == capa.report_id)
        )
    ).scalar_one()
    assert inp.status == "pending"
    assert inp.supplier_id == sup.supplier_id
    assert inp.severity == capa.severity
    assert inp.disposition == capa.d7_prevention
    assert inp.attempt_count == 0
    assert inp.max_attempts == 5
    assert inp.repeat_confirmed is None
    assert inp.repeat_detection_status in ("matched", "not_matched", "unavailable")

    logs = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "SUPPLIER_RISK_INPUT_QUEUED",
            )
        )
    ).scalars().all()
    assert len(logs) == 1
    assert "supplier_id" in logs[0].changed_fields
    assert "disposition" in logs[0].changed_fields
    assert logs[0].changed_fields["disposition"] == "预防措施"
    assert logs[0].changed_fields["capa_id"] == str(capa.report_id)
    assert logs[0].changed_fields["supplier_id"] == str(sup.supplier_id)


@pytest.mark.asyncio
async def test_advance_skips_when_no_supplier(db, default_factory, admin_user):
    """capa.supplier_id 为空 → 不写 input。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, supplier_id=None)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _seed_d7_action(db, capa, fmea, admin_user)

    await advance_capa(
        db, capa, admin_user.user_id, AdvanceRequest(target_state=EightDState.D7_COMPLETED)
    )

    cnt = (
        await db.execute(
            select(SupplierRiskCapaInput).where(SupplierRiskCapaInput.capa_id == capa.report_id)
        )
    ).scalars().all()
    assert len(cnt) == 0


@pytest.mark.asyncio
async def test_repeat_detection_matched_with_history(db, default_factory, admin_user):
    """同 supplier + 同 fmea_node_id 的归档 8D 存在 → matched。"""
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    archived = await _make_capa(
        db,
        default_factory.id,
        admin_user.user_id,
        status="ARCHIVED",
        supplier_id=sup.supplier_id,
        fmea_node_id="fm-1",
    )
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, supplier_id=sup.supplier_id
    )
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _seed_d7_action(db, capa, fmea, admin_user)

    await advance_capa(
        db, capa, admin_user.user_id, AdvanceRequest(target_state=EightDState.D7_COMPLETED)
    )

    inp = (
        await db.execute(
            select(SupplierRiskCapaInput).where(SupplierRiskCapaInput.capa_id == capa.report_id)
        )
    ).scalar_one()
    assert inp.repeat_suggested is True
    assert inp.repeat_detection_status == "matched"
    assert archived.document_no in inp.matched_capa_nos


@pytest.mark.asyncio
async def test_repeat_detection_unavailable_without_fmea(db, default_factory, admin_user):
    """capa 无 fmea_node_id → repeat_detection_status='unavailable'。"""
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    # No fmea link/node → _d7_completion_gate recs empty → trivial pass
    capa = await _make_capa(
        db,
        default_factory.id,
        admin_user.user_id,
        supplier_id=sup.supplier_id,
        fmea_node_id=None,
        fmea_ref_id=None,
    )

    await advance_capa(
        db, capa, admin_user.user_id, AdvanceRequest(target_state=EightDState.D7_COMPLETED)
    )

    inp = (
        await db.execute(
            select(SupplierRiskCapaInput).where(SupplierRiskCapaInput.capa_id == capa.report_id)
        )
    ).scalar_one()
    assert inp.repeat_detection_status == "unavailable"
    assert inp.repeat_suggested is None
    assert inp.matched_capa_nos == []


@pytest.mark.asyncio
async def test_advance_other_transitions_no_input(db, default_factory, admin_user):
    """非 D7_COMPLETED 的推进不写 input。"""
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(
        db,
        default_factory.id,
        admin_user.user_id,
        status="D1_TEAM",
        supplier_id=sup.supplier_id,
        fmea_node_id="fm-1",
    )

    await advance_capa(db, capa, admin_user.user_id)  # linear next D2
    await db.refresh(capa)
    assert capa.status == EightDState.D2_DESCRIPTION.value

    cnt = (
        await db.execute(
            select(SupplierRiskCapaInput).where(SupplierRiskCapaInput.capa_id == capa.report_id)
        )
    ).scalars().all()
    assert len(cnt) == 0


@pytest.mark.asyncio
async def test_d7_completed_reentry_is_idempotent(db, default_factory, admin_user):
    """D8 reject 后再次 D7_COMPLETED：不二次 insert，不二次 QUEUED 审计。"""
    sup = await _make_supplier(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id, supplier_id=sup.supplier_id
    )
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _seed_d7_action(db, capa, fmea, admin_user)

    await advance_capa(
        db, capa, admin_user.user_id, AdvanceRequest(target_state=EightDState.D7_COMPLETED)
    )
    await db.refresh(capa)
    assert capa.status == EightDState.D7_COMPLETED.value

    first_inputs = (
        await db.execute(
            select(SupplierRiskCapaInput).where(SupplierRiskCapaInput.capa_id == capa.report_id)
        )
    ).scalars().all()
    assert len(first_inputs) == 1
    first_input_id = first_inputs[0].input_id

    # Simulate D8 reject path re-entry without full D8 setup.
    capa.status = EightDState.D7_PREVENTION.value
    await db.flush()

    await advance_capa(
        db, capa, admin_user.user_id, AdvanceRequest(target_state=EightDState.D7_COMPLETED)
    )
    await db.refresh(capa)
    assert capa.status == EightDState.D7_COMPLETED.value

    inputs = (
        await db.execute(
            select(SupplierRiskCapaInput).where(SupplierRiskCapaInput.capa_id == capa.report_id)
        )
    ).scalars().all()
    assert len(inputs) == 1
    assert inputs[0].input_id == first_input_id

    queued_logs = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "SUPPLIER_RISK_INPUT_QUEUED",
            )
        )
    ).scalars().all()
    assert len(queued_logs) == 1
