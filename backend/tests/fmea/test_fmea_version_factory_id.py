import uuid
import pytest
from sqlalchemy import select

from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.services.version_service import create_fmea_version

pytestmark = pytest.mark.requires_db


async def _make_fmea(db, factory_id, user_id, graph=None):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-VER-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=factory_id,
        status="draft", created_by=user_id, graph_data=graph or {"nodes": [], "edges": []},
    )
    db.add(fmea); await db.flush()
    return fmea


@pytest.mark.asyncio
async def test_fmea_version_carries_factory_id(db, default_factory, admin_user):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id,
                            graph={"nodes": [], "edges": []})
    version = await create_fmea_version(db, fmea, "submit", "提交评审", admin_user.user_id)
    assert version.factory_id == default_factory.id

    # round-trip from DB to prove the column is populated, not just the ORM object
    row = (await db.execute(
        select(FMEAVersion).where(FMEAVersion.version_id == version.version_id)
    )).scalar_one()
    assert row.factory_id == default_factory.id
