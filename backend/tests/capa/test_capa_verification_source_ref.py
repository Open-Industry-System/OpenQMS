import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.fmea import FMEADocument
from app.schemas.capa_verification import VerificationCreate, VerificationUpdate
from app.services.capa_verification_service import (
    create_verification, update_verification, _normalize_and_validate_source_ref,
)

pytestmark = pytest.mark.requires_db


async def _make_capa_linked(db, factory_id, user_id, fmea_id, pl_code="DC-DC-100"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-SR-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code=pl_code, factory_id=factory_id,
        created_by=user_id, status="D4_ROOT_CAUSE",
        fmea_ref_id=fmea_id, fmea_node_id="fm-1",
    )
    db.add(capa); await db.flush()
    return capa


async def _make_fmea_with_cause(db, factory_id, user_id, cause_id="cause-1", pl_code="DC-DC-100"):
    graph = {"nodes": [
        {"id": "fm-1", "type": "FailureMode", "name": "虚焊"},
        {"id": cause_id, "type": "FailureCause", "name": "参数偏移"},
    ], "edges": [{"source": cause_id, "target": "fm-1", "type": "CAUSE_OF"}]}
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-SR-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code=pl_code, factory_id=factory_id,
        status="draft", created_by=user_id, graph_data=graph,
    )
    db.add(fmea); await db.flush()
    return fmea


@pytest.mark.asyncio
async def test_normalize_valid_cause(db, default_factory, admin_user):
    fmea = await _make_fmea_with_cause(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa_linked(db, default_factory.id, admin_user.user_id, fmea.fmea_id)
    out = await _normalize_and_validate_source_ref(db, capa, {"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-1"})
    assert out == {"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-1"}


@pytest.mark.asyncio
async def test_normalize_rejects_extra_keys(db, default_factory, admin_user):
    fmea = await _make_fmea_with_cause(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa_linked(db, default_factory.id, admin_user.user_id, fmea.fmea_id)
    with pytest.raises(ValueError):
        await _normalize_and_validate_source_ref(db, capa, {"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-1", "x": 1})


@pytest.mark.asyncio
async def test_normalize_rejects_no_linked_fmea(db, default_factory, admin_user):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-SR-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=default_factory.id,
        created_by=admin_user.user_id, status="D4_ROOT_CAUSE",
    )
    db.add(capa); await db.flush()
    with pytest.raises(ValueError):
        await _normalize_and_validate_source_ref(db, capa, {"fmea_id": str(uuid.uuid4()), "cause_node_id": "cause-1"})


@pytest.mark.asyncio
async def test_normalize_rejects_wrong_fmea_id(db, default_factory, admin_user):
    fmea = await _make_fmea_with_cause(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa_linked(db, default_factory.id, admin_user.user_id, fmea.fmea_id)
    with pytest.raises(ValueError):
        await _normalize_and_validate_source_ref(db, capa, {"fmea_id": str(uuid.uuid4()), "cause_node_id": "cause-1"})


@pytest.mark.asyncio
async def test_normalize_rejects_non_failure_cause_node(db, default_factory, admin_user):
    fmea = await _make_fmea_with_cause(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa_linked(db, default_factory.id, admin_user.user_id, fmea.fmea_id)
    with pytest.raises(ValueError):
        await _normalize_and_validate_source_ref(db, capa, {"fmea_id": str(fmea.fmea_id), "cause_node_id": "fm-1"})


@pytest.mark.asyncio
async def test_normalize_rejects_unknown_node(db, default_factory, admin_user):
    fmea = await _make_fmea_with_cause(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa_linked(db, default_factory.id, admin_user.user_id, fmea.fmea_id)
    with pytest.raises(ValueError):
        await _normalize_and_validate_source_ref(db, capa, {"fmea_id": str(fmea.fmea_id), "cause_node_id": "nope"})


@pytest.mark.asyncio
async def test_create_pending_with_cause_writes_updated_and_linkage(db, default_factory, admin_user):
    fmea = await _make_fmea_with_cause(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa_linked(db, default_factory.id, admin_user.user_id, fmea.fmea_id)
    rec = await create_verification(db, capa, VerificationCreate(
        root_cause_text="根因", conclusion="pending",
        source_ref={"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-1"},
    ), admin_user)
    assert rec.source_ref == {"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-1"}
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    actions = {a.action for a in audits}
    assert "D4_VERIFICATION_UPDATED" in actions
    assert "FMEA_LINKAGE_CREATED" in actions


@pytest.mark.asyncio
async def test_create_passed_with_cause_carries_source_ref(db, default_factory, admin_user):
    fmea = await _make_fmea_with_cause(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa_linked(db, default_factory.id, admin_user.user_id, fmea.fmea_id)
    rec = await create_verification(db, capa, VerificationCreate(
        root_cause_text="根因", conclusion="passed", method="measurement", result="ok",
        source_ref={"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-1"},
    ), admin_user)
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    passed = next(a for a in audits if a.action == "D4_VERIFICATION_PASSED")
    assert passed.changed_fields.get("source_ref") == rec.source_ref
    assert any(a.action == "FMEA_LINKAGE_CREATED" for a in audits)


@pytest.mark.asyncio
async def test_update_clear_cause_writes_updated_no_linkage(db, default_factory, admin_user):
    fmea = await _make_fmea_with_cause(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa_linked(db, default_factory.id, admin_user.user_id, fmea.fmea_id)
    rec = await create_verification(db, capa, VerificationCreate(
        root_cause_text="根因", conclusion="pending",
        source_ref={"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-1"},
    ), admin_user)
    vid = rec.verification_id  # capture before any session mutation
    await update_verification(db, capa, vid, VerificationUpdate(source_ref=None), admin_user)
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    updated = [a for a in audits if a.action == "D4_VERIFICATION_UPDATED"]
    assert len(updated) >= 2  # one for create, one for clear
    assert not any(a.action == "FMEA_LINKAGE_CREATED" and a.changed_fields.get("source") == "d4_cause"
                   for a in audits if a == updated[-1])


@pytest.mark.asyncio
async def test_update_same_cause_is_idempotent(db, default_factory, admin_user):
    fmea = await _make_fmea_with_cause(db, default_factory.id, admin_user.user_id)
    capa = await _make_capa_linked(db, default_factory.id, admin_user.user_id, fmea.fmea_id)
    rec = await create_verification(db, capa, VerificationCreate(
        root_cause_text="根因", conclusion="pending",
        source_ref={"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-1"},
    ), admin_user)
    before = len((await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all())
    await update_verification(db, capa, rec.verification_id,
                              VerificationUpdate(source_ref={"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-1"}),
                              admin_user)
    after = len((await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all())
    assert before == after


@pytest.mark.asyncio
async def test_update_change_cause_writes_linkage(db, default_factory, admin_user):
    fmea = await _make_fmea_with_cause(db, default_factory.id, admin_user.user_id, cause_id="cause-2")
    capa = await _make_capa_linked(db, default_factory.id, admin_user.user_id, fmea.fmea_id)
    rec = await create_verification(db, capa, VerificationCreate(
        root_cause_text="根因", conclusion="passed", method="measurement", result="ok",
        source_ref={"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-2"},
    ), admin_user)
    # graph has only cause-2; add cause-3 via a second FMEA? No—same FMEA, add node directly:
    fmea.graph_data["nodes"].append({"id": "cause-3", "type": "FailureCause", "name": "x"})
    fmea.graph_data["edges"].append({"source": "cause-3", "target": "fm-1", "type": "CAUSE_OF"})
    await db.flush()
    await update_verification(db, capa, rec.verification_id,
                              VerificationUpdate(source_ref={"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-3"}),
                              admin_user)
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    linkages = [a for a in audits if a.action == "FMEA_LINKAGE_CREATED" and a.changed_fields.get("source") == "d4_cause"]
    assert len(linkages) == 2  # create + change


@pytest.mark.asyncio
async def test_normalize_rejects_cross_factory_fmea(db, default_factory, admin_user):
    # capa in default_factory; fmea in a different factory — same PL but different factory
    from app.models.factory import Factory
    other = Factory(name="other", code="OTHER")
    db.add(other); await db.flush()
    fmea = await _make_fmea_with_cause(db, other.id, admin_user.user_id)
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-SR-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code="DC-DC-100", factory_id=default_factory.id,
        created_by=admin_user.user_id, status="D4_ROOT_CAUSE",
        fmea_ref_id=fmea.fmea_id, fmea_node_id="fm-1",
    )
    db.add(capa); await db.flush()
    with pytest.raises(PermissionError):
        await _normalize_and_validate_source_ref(db, capa, {"fmea_id": str(fmea.fmea_id), "cause_node_id": "cause-1"})
