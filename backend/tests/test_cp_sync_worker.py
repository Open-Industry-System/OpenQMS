import uuid

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.control_plan import ControlPlan
from app.models.cp_sync_outbox import CPSyncOutbox
from app.models.fmea import FMEADocument
from app.services.control_plan_service import apply_cp_sync_pending
from app.services.cp_sync_worker import process_cp_sync_outbox_batch


async def _mk_fmea_with_cps(db, factory_id, n=2):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-CPS-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=factory_id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.flush()
    cps = []
    for i in range(n):
        cp = ControlPlan(
            cp_id=uuid.uuid4(), document_no=f"CP-{uuid.uuid4().hex[:8]}",
            title=f"cp{i}", fmea_ref_id=fmea.fmea_id,
            product_line_code="DC-DC-100", factory_id=factory_id, sync_pending=False,
        )
        db.add(cp)
        cps.append(cp)
    await db.commit()
    return fmea, cps


@pytest.mark.asyncio
async def test_applier_flips_only_pending_and_audits_each(db, default_factory, admin_user):
    fmea, cps = await _mk_fmea_with_cps(db, default_factory.id, 2)
    version_id = uuid.uuid4()
    outbox = CPSyncOutbox(fmea_id=fmea.fmea_id, fmea_version_id=version_id, payload={})
    n = await apply_cp_sync_pending(db, outbox, admin_user.user_id)
    await db.commit()
    assert n == 2
    audits = (await db.execute(select(AuditLog).where(
        AuditLog.table_name == "control_plans", AuditLog.action == "UPDATE"))).scalars().all()
    assert len(audits) == 2  # 2 + N rule: one per flipped CP
    for a in audits:
        assert a.changed_fields["sync_pending"] == "false->true"
        assert "source_fmea_version_id" not in a.changed_fields
        assert a.changed_fields["trigger_fmea_version_id"] == str(version_id)


@pytest.mark.asyncio
async def test_worker_idempotent_no_duplicate_audit(db, default_factory, admin_user):
    fmea, cps = await _mk_fmea_with_cps(db, default_factory.id, 2)
    db.add(CPSyncOutbox(fmea_id=fmea.fmea_id, fmea_version_id=uuid.uuid4(),
                        payload={"user_id": str(admin_user.user_id)}))
    await db.commit()
    await process_cp_sync_outbox_batch(db)
    await process_cp_sync_outbox_batch(db)  # second run: row already completed
    audits = (await db.execute(select(AuditLog).where(
        AuditLog.table_name == "control_plans", AuditLog.action == "UPDATE"))).scalars().all()
    assert len(audits) == 2  # still exactly one per CP
