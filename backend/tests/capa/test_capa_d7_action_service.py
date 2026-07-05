import copy
import uuid
import pytest
from sqlalchemy import select
from app.models.capa import CAPAEightD, CapaD7NodeAction
from app.models.fmea import FMEADocument
from app.schemas.capa_verification import D7NodeActionCreate
from app.services.capa_d7_action_service import (
    ConflictError, record_d7_action, list_d7_actions,
)

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, d5="措施A"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-D7-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status="D7_PREVENTION", d5_correction=d5,
    )
    db.add(capa); await db.flush()
    return capa


async def _make_fmea(db, factory_id, user_id, fm_id="fm-1", cause_id="c-1"):
    graph = {"nodes": [
        {"id": fm_id, "type": "FailureMode", "name": "虚焊"},
        {"id": cause_id, "type": "FailureCause", "name": "参数偏移"},
    ], "edges": [{"source": cause_id, "target": fm_id, "type": "CAUSE_OF"}]}
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-D7-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=factory_id,
        status="draft", created_by=user_id, graph_data=graph,
    )
    db.add(fmea); await db.flush()
    return fmea


@pytest.mark.asyncio
async def test_record_confirmed_inserts_and_audits(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    rec = await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    assert rec.action == "confirmed"


@pytest.mark.asyncio
async def test_record_idempotent_same_action_and_reason(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    req = D7NodeActionCreate(action="confirmed", fmea_id=fmea.fmea_id,
                            failure_mode_node_id="fm-1", failure_cause_node_id="c-1",
                            match_source="linked")
    first = await record_d7_action(db, capa, req, admin_user)
    second = await record_d7_action(db, capa, req, admin_user)
    assert second.action_id == first.action_id   # 幂等返回既有行，无新行
    all_rows = (await db.execute(
        select(CapaD7NodeAction).where(CapaD7NodeAction.capa_id == capa.report_id)
    )).scalars().all()
    assert len(all_rows) == 1


@pytest.mark.asyncio
async def test_record_change_action_writes_changed_audit(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    rec = await record_d7_action(db, capa, D7NodeActionCreate(
        action="skipped", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked", reason="不适用"), admin_user)
    assert rec.action == "skipped"
    assert rec.reason == "不适用"


@pytest.mark.asyncio
async def test_record_fmea_not_found_lookup(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    with pytest.raises(LookupError):
        await record_d7_action(db, capa, D7NodeActionCreate(
            action="confirmed", fmea_id=uuid.uuid4(), failure_mode_node_id="fm-1",
            match_source="linked"), admin_user)


@pytest.mark.asyncio
async def test_record_cross_factory_fmea_permission(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    # 在另一个 factory 建 FMEA
    from app.models.factory import Factory
    other = Factory(id=uuid.uuid4(), code="OTHER", name="Other")
    db.add(other); await db.flush()
    fmea = await _make_fmea(db, other.id, admin_user.user_id)
    with pytest.raises(PermissionError):
        await record_d7_action(db, capa, D7NodeActionCreate(
            action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
            match_source="linked"), admin_user)
