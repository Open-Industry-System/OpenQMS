import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.factory import Factory
from app.services.capa_service import link_fmea

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, pl="DC-DC-100"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=f"8D-LF-{uuid.uuid4().hex[:6]}",
        title="t", product_line_code=pl, factory_id=factory_id, created_by=user_id, status="D4_ROOT_CAUSE",
    )
    db.add(capa); await db.flush()
    return capa


async def _make_fmea(db, factory_id, user_id, pl="DC-DC-100"):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-LF-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code=pl, factory_id=factory_id, status="draft",
        created_by=user_id, graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea); await db.flush()
    return fmea


@pytest.mark.asyncio
async def test_link_writes_linkage_on_change(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await link_fmea(db, capa, fmea.fmea_id, admin_user.user_id)
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    assert any(a.action == "LINK_FMEA" for a in audits)
    linkages = [a for a in audits if a.action == "FMEA_LINKAGE_CREATED"]
    assert len(linkages) == 1
    assert linkages[0].changed_fields["source"] == "header"
    assert linkages[0].changed_fields["node_id"] is None


@pytest.mark.asyncio
async def test_link_idempotent_no_new_linkage(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await link_fmea(db, capa, fmea.fmea_id, admin_user.user_id, "fm-1")
    # Avoid db.rollback() — test session patches commit→flush inside outer tx;
    # rollback would undo fixture data. Re-read capa and call again for idempotency.
    await db.refresh(capa)
    await link_fmea(db, capa, fmea.fmea_id, admin_user.user_id, "fm-1")
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    assert len([a for a in audits if a.action == "FMEA_LINKAGE_CREATED"]) == 1


@pytest.mark.asyncio
async def test_link_node_change_writes_new_linkage(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id)
    await link_fmea(db, capa, fmea.fmea_id, admin_user.user_id, "fm-1")
    # Avoid db.rollback() — same reason as idempotent test.
    await db.refresh(capa)
    await link_fmea(db, capa, fmea.fmea_id, admin_user.user_id, "fm-2")
    audits = (await db.execute(select(AuditLog).where(AuditLog.record_id == capa.report_id))).scalars().all()
    assert len([a for a in audits if a.action == "FMEA_LINKAGE_CREATED"]) == 2


@pytest.mark.asyncio
async def test_link_rejects_cross_factory(db, default_factory, admin_user):
    other = Factory(name="other", code="OTHER")
    db.add(other); await db.flush()
    capa = await _make_capa(db, default_factory.id, admin_user.user_id)
    fmea = await _make_fmea(db, other.id, admin_user.user_id)
    with pytest.raises(PermissionError):
        await link_fmea(db, capa, fmea.fmea_id, admin_user.user_id)


@pytest.mark.asyncio
async def test_link_rejects_cross_product_line(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, pl="PL-A")
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, pl="PL-B")
    with pytest.raises(PermissionError):
        await link_fmea(db, capa, fmea.fmea_id, admin_user.user_id)
