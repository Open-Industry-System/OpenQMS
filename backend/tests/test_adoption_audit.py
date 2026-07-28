import uuid

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.schemas.fmea import RecommendationAdoption
from app.services.adoption_audit import write_adoption_audits


def _a(rid, fid="fm1"):
    return RecommendationAdoption(
        field_id=fid, recommendation_id=rid, source="graph",
        stage_index=0, adopted_text="焊接电流不足",
    )


async def _mk(db, factory_id):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-ADO-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=factory_id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()
    return fmea


@pytest.mark.asyncio
async def test_writes_one_audit_per_adoption(db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id)
    n = await write_adoption_audits(db, fmea.fmea_id, [_a("r1"), _a("r2")], admin_user.user_id)
    await db.commit()
    assert n == 2
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert len(rows) == 2
    assert rows[0].changed_fields["recommendation_id"] in ("r1", "r2")


@pytest.mark.asyncio
async def test_idempotent_by_recommendation_id(db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id)
    await write_adoption_audits(db, fmea.fmea_id, [_a("r1")], admin_user.user_id)
    await db.commit()
    n2 = await write_adoption_audits(db, fmea.fmea_id, [_a("r1")], admin_user.user_id)
    await db.commit()
    assert n2 == 0
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_same_recommendation_id_audits_per_fmea(db, default_factory, admin_user):
    fmea1 = await _mk(db, default_factory.id)
    fmea2 = await _mk(db, default_factory.id)
    n1 = await write_adoption_audits(db, fmea1.fmea_id, [_a("r1")], admin_user.user_id)
    await db.commit()
    n2 = await write_adoption_audits(db, fmea2.fmea_id, [_a("r1")], admin_user.user_id)
    await db.commit()
    assert n1 == 1
    assert n2 == 1
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert len(rows) == 2
