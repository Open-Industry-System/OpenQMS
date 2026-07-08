"""D7_PREVENTION → D7_COMPLETED → D8_GATE_PENDING → D8_APPROVAL_PENDING → D8_CLOSURE 端到端（US-E2E-01.3）。"""
import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaD7NodeAction
from app.models.fmea import FMEADocument
from app.schemas.capa import AdvanceRequest
from app.schemas.capa_verification import D7NodeActionCreate
from app.services.capa_d7_action_service import record_d7_action
from app.services.capa_service import advance_capa

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, status="D7_PREVENTION"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-FLOW-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status=status, d5_correction="措施A", d6_verification="已验证",
        d7_prevention="预防",
    )
    db.add(capa); await db.flush()
    return capa


async def _make_fmea(db, factory_id, user_id):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-FLOW-{uuid.uuid4().hex[:6]}",
        title="t", fmea_type="PFMEA", product_line_code="DC-DC-100",
        factory_id=factory_id, status="draft", created_by=user_id,
        graph_data={"nodes": [
            {"id": "fm-1", "type": "FailureMode", "name": "虚焊"},
            {"id": "c-1", "type": "FailureCause", "name": "参数偏移"},
        ], "edges": [{"source": "c-1", "target": "fm-1", "type": "CAUSE_OF"}]},
    )
    db.add(fmea); await db.flush()
    return fmea


async def _to_d7_completed(db, capa, fmea, user):
    capa.fmea_ref_id = fmea.fmea_id; capa.fmea_node_id = "fm-1"; await db.flush()
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id,
        failure_mode_node_id="fm-1", failure_cause_node_id="c-1", match_source="linked",
    ), user)
    await advance_capa(db, capa, user.user_id, AdvanceRequest(target_state="D7_COMPLETED"))
    await db.refresh(capa)


@pytest.mark.asyncio
async def test_linear_advance_d7_prevention_without_target_state_raises(db, default_factory, admin_user):
    """D7_PREVENTION 是分支态，target_state=None 必须 raise（强制显式）。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    capa.fmea_ref_id = fmea.fmea_id; capa.fmea_node_id = "fm-1"; await db.flush()
    with pytest.raises(ValueError, match="需显式传 target_state"):
        await advance_capa(db, capa, admin_user.user_id, AdvanceRequest())


@pytest.mark.asyncio
async def test_full_flow_d7_to_d8_closure(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _to_d7_completed(db, capa, fmea, admin_user)
    assert capa.status == "D7_COMPLETED"

    await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D8_GATE_PENDING"))
    await db.refresh(capa); assert capa.status == "D8_GATE_PENDING"

    await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D8_APPROVAL_PENDING"))
    await db.refresh(capa); assert capa.status == "D8_APPROVAL_PENDING"

    await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D8_CLOSURE"))
    await db.refresh(capa); assert capa.status == "D8_CLOSURE"

    # D8_APPROVED 审计已发
    approved = (await db.execute(select(AuditLog).where(
        AuditLog.record_id == capa.report_id, AuditLog.action == "D8_APPROVED"
    ))).scalars().all()
    assert len(approved) == 1


@pytest.mark.asyncio
async def test_reject_requires_reason(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await _to_d7_completed(db, capa, fmea, admin_user)
    await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D8_GATE_PENDING"))
    await advance_capa(db, capa, admin_user.user_id, AdvanceRequest(target_state="D8_APPROVAL_PENDING"))
    await db.refresh(capa)

    # 缺理由 → 400 ValueError
    with pytest.raises(ValueError, match="驳回需填写理由"):
        await advance_capa(db, capa, admin_user.user_id,
                           AdvanceRequest(target_state="D7_PREVENTION"))

    # 有理由 → 回退 D7_PREVENTION + D8_REJECTED 审计
    await advance_capa(db, capa, admin_user.user_id,
                       AdvanceRequest(target_state="D7_PREVENTION", reject_reason="证据不足"))
    await db.refresh(capa); assert capa.status == "D7_PREVENTION"
    rejected = (await db.execute(select(AuditLog).where(
        AuditLog.record_id == capa.report_id, AuditLog.action == "D8_REJECTED"
    ))).scalars().all()
    assert len(rejected) == 1
    assert rejected[0].changed_fields["reject_reason"] == "证据不足"


@pytest.mark.asyncio
async def test_d8_closure_to_archived_linear(db, default_factory, admin_user):
    """D8_CLOSURE→ARCHIVED 线性（target_state=None），_LINEAR_NEXT 含此边。"""
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, status="D8_CLOSURE")
    await advance_capa(db, capa, admin_user.user_id, AdvanceRequest())  # None → ARCHIVED
    await db.refresh(capa); assert capa.status == "ARCHIVED"
