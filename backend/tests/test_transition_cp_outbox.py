# backend/tests/test_transition_cp_outbox.py
import uuid
import pytest
from sqlalchemy import select
from app.models.control_plan import ControlPlan
from app.models.cp_sync_outbox import CPSyncOutbox
from app.models.fmea import FMEADocument
from app.services import fmea_service


async def _mk(db, factory_id):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-TR-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=factory_id, status="draft",
        graph_data={"nodes": [], "edges": [], "wizardScope": {"wizard_completed": True}},
        version=1,
    )
    cp = ControlPlan(
        cp_id=uuid.uuid4(), document_no=f"CP-{uuid.uuid4().hex[:8]}",
        title="cp", fmea_ref_id=fmea.fmea_id,
        product_line_code="DC-DC-100", factory_id=factory_id, sync_pending=False,
    )
    db.add(fmea)
    await db.flush()
    db.add(cp)
    await db.commit()
    return fmea, cp


@pytest.mark.asyncio
async def test_approve_enqueues_cp_outbox_and_does_not_set_pending_sync(db, default_factory, admin_user):
    fmea, cp = await _mk(db, default_factory.id)
    # drive draft -> in_review -> approved
    await fmea_service.transition_fmea(db, fmea, "in_review", admin_user.user_id)
    await fmea_service.transition_fmea(db, fmea, "approved", admin_user.user_id)
    rows = (await db.execute(select(CPSyncOutbox).where(
        CPSyncOutbox.fmea_id == fmea.fmea_id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == "cp.sync_pending_set"
    assert rows[0].fmea_version_id is not None
    await db.refresh(cp)
    assert cp.sync_pending is False  # worker has not run


@pytest.mark.asyncio
async def test_submit_does_not_enqueue_cp_outbox(db, default_factory, admin_user):
    fmea, _ = await _mk(db, default_factory.id)
    await fmea_service.transition_fmea(db, fmea, "in_review", admin_user.user_id)
    rows = (await db.execute(select(CPSyncOutbox))).scalars().all()
    assert rows == []
