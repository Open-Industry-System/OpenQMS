import copy
import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaD7NodeAction
from app.models.fmea import FMEADocument
from app.schemas.capa_verification import D7AutoFillRequest, D7NodeActionCreate
from app.services.capa_d7_action_service import (
    auto_fill_d7, record_d7_action, _hash_for_rec, recommendation_fingerprint,
)

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, d5="措施A", status="D7_PREVENTION"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-D7L-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, status=status, d5_correction=d5,
    )
    db.add(capa); await db.flush()
    return capa


async def _make_fmea_with_prevention(db, factory_id, user_id, pl_code="DC-DC-100"):
    graph = {"nodes": [
        {"id": "fm-1", "type": "FailureMode", "name": "虚焊"},
        {"id": "c-1", "type": "FailureCause", "name": "参数偏移"},
        {"id": "pc-1", "type": "PreventionControl", "name": "已有控制"},
    ], "edges": [
        {"source": "c-1", "target": "fm-1", "type": "CAUSE_OF"},
        {"source": "c-1", "target": "pc-1", "type": "PREVENTED_BY"},
    ]}
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-D7L-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code=pl_code, factory_id=factory_id,
        status="draft", created_by=user_id, graph_data=graph,
    )
    db.add(fmea); await db.flush()
    return fmea


@pytest.mark.asyncio
async def test_fingerprint_changes_with_prevention_name():
    base = dict(fmea_id=str(uuid.uuid4()), failure_mode_node_id="fm-1",
                failure_cause_node_id="c-1", failure_mode_name="m", failure_cause_name="c",
                match_reason="r", prevention_control_node_id="pc-1", prevention_control_name="old")
    h1 = recommendation_fingerprint(**base)
    base2 = dict(base, prevention_control_name="new")
    assert recommendation_fingerprint(**base2) != h1


@pytest.mark.asyncio
async def test_fingerprint_changes_with_prevention_node():
    base = dict(fmea_id=str(uuid.uuid4()), failure_mode_node_id="fm-1",
                failure_cause_node_id="c-1", failure_mode_name="m", failure_cause_name="c",
                match_reason="r", prevention_control_node_id="pc-1", prevention_control_name="n")
    h1 = recommendation_fingerprint(**base)
    base2 = dict(base, prevention_control_node_id="pc-2")
    assert recommendation_fingerprint(**base2) != h1


@pytest.mark.asyncio
async def test_confirmed_copies_prevention_and_writes_linkage(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea_with_prevention(db, default_factory.id, admin_user.user_id)
    capa.fmea_ref_id = fmea.fmea_id
    capa.fmea_node_id = "fm-1"
    await db.flush()
    rec = await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    assert rec.prevention_control_node_id == "pc-1"
    assert rec.prevention_control_name_before == "已有控制"
    assert rec.prevention_control_name_after == "已有控制"  # confirmed: before==after==canonical
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    linkages = [a for a in audits if a.action == "FMEA_LINKAGE_CREATED"]
    assert len(linkages) == 1
    assert linkages[0].changed_fields["source"] == "d7_prevention"
    assert linkages[0].changed_fields["node_id"] == "pc-1"


@pytest.mark.asyncio
async def test_confirmed_rule_no_linkage(db, default_factory, admin_user):
    from app.services.capa_service import get_d7_recommendations
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d5="收紧螺栓尺寸公差")
    # No linked FMEA → rule engine fallback rec (fmea_id=None); use real synthetic key.
    capa.d4_root_cause = "来料螺栓尺寸超差"
    await db.flush()
    recs = get_d7_recommendations(
        {"fmea_ref_id": None, "fmea_node_id": None, "d4_root_cause": capa.d4_root_cause,
         "d5_correction": capa.d5_correction, "product_line_code": capa.product_line_code},
        [], allowed_product_lines=[capa.product_line_code],
    )
    assert recs and recs[0]["match_source"] == "rule" and recs[0]["fmea_id"] is None
    fallback = recs[0]
    rec = await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=None,
        failure_mode_node_id=fallback["failure_mode_node_id"],
        match_source="rule"), admin_user)
    assert rec.fmea_id is None
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    assert not any(a.action == "FMEA_LINKAGE_CREATED" for a in audits)


@pytest.mark.asyncio
async def test_skipped_not_in_reverse_lookup(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea_with_prevention(db, default_factory.id, admin_user.user_id)
    capa.fmea_ref_id = fmea.fmea_id
    capa.fmea_node_id = "fm-1"
    await db.flush()
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="skipped", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    actions = (await db.execute(select(CapaD7NodeAction).where(CapaD7NodeAction.capa_id == capa.report_id))).scalars().all()
    assert all(a.action == "skipped" for a in actions)
    # reverse lookup must exclude skipped — checked via service in Task 5; here assert action stored
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    assert not any(a.action == "FMEA_LINKAGE_CREATED" for a in audits)


@pytest.mark.asyncio
async def test_confirmed_to_skipped_no_new_linkage(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea_with_prevention(db, default_factory.id, admin_user.user_id)
    capa.fmea_ref_id = fmea.fmea_id
    capa.fmea_node_id = "fm-1"
    await db.flush()
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    # Avoid db.rollback() — test session patches commit→flush inside outer tx;
    # rollback would undo fixture data. Re-record with skipped on the same row.
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="skipped", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    assert len([a for a in audits if a.action == "FMEA_LINKAGE_CREATED"]) == 1  # only the confirm


@pytest.mark.asyncio
async def test_skipped_to_confirmed_writes_linkage(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea_with_prevention(db, default_factory.id, admin_user.user_id)
    capa.fmea_ref_id = fmea.fmea_id
    capa.fmea_node_id = "fm-1"
    await db.flush()
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="skipped", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    # Avoid db.rollback() — same reason as confirmed→skipped test.
    await record_d7_action(db, capa, D7NodeActionCreate(
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    assert len([a for a in audits if a.action == "FMEA_LINKAGE_CREATED"]) == 1


@pytest.mark.asyncio
async def test_autofill_new_prevention_gate_passes(db, default_factory, admin_user):
    """auto-fill creates a NEW Prevention; action hash must equal gate's recomputed hash."""
    from app.services.capa_d7_action_service import _compute_current_d7_recs, _hash_for_rec
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    # graph WITHOUT prevention control → auto-fill creates one
    graph = {"nodes": [
        {"id": "fm-1", "type": "FailureMode", "name": "虚焊"},
        {"id": "c-1", "type": "FailureCause", "name": "参数偏移"},
    ], "edges": [{"source": "c-1", "target": "fm-1", "type": "CAUSE_OF"}]}
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-AF-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", created_by=admin_user.user_id, graph_data=graph,
    )
    db.add(fmea); await db.flush()
    capa.fmea_ref_id = fmea.fmea_id
    capa.fmea_node_id = "fm-1"
    await db.flush()
    rec, _meta = await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    await db.refresh(fmea)
    # recompute current recs (post-mutation FMEA) and find the same key
    current = await _compute_current_d7_recs(db, capa)
    match = next(r for r in current if r["failure_mode_node_id"] == "fm-1" and r["failure_cause_node_id"] == "c-1")
    assert rec.recommendation_hash == _hash_for_rec(match), "auto-fill hash must match gate recomputation"


@pytest.mark.asyncio
async def test_autofill_writes_linkage_prevention(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    graph = {"nodes": [
        {"id": "fm-1", "type": "FailureMode", "name": "虚焊"},
        {"id": "c-1", "type": "FailureCause", "name": "参数偏移"},
    ], "edges": [{"source": "c-1", "target": "fm-1", "type": "CAUSE_OF"}]}
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-AFL-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", created_by=admin_user.user_id, graph_data=graph,
    )
    db.add(fmea); await db.flush()
    capa.fmea_ref_id = fmea.fmea_id
    capa.fmea_node_id = "fm-1"
    await db.flush()
    await auto_fill_d7(db, capa, D7AutoFillRequest(
        fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id="c-1", match_source="linked"), admin_user)
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    linkages = [a for a in audits if a.action == "FMEA_LINKAGE_CREATED" and a.changed_fields.get("source") == "d7_prevention"]
    assert len(linkages) == 1
