import uuid
import pytest
from sqlalchemy import select

from app.models.capa import CAPAEightD, CapaAIAdoption
from app.schemas.capa_verification import AdoptRequest
from app.services.capa_verification_service import adopt_recommendation

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, doc_no="8D-STAGE-001", d4=None):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no=doc_no, title="t",
        product_line_code="DC-DC-100", factory_id=factory_id,
        created_by=user_id, d4_root_cause=d4, status="D4_ROOT_CAUSE",
    )
    db.add(capa)
    await db.flush()
    return capa


@pytest.mark.asyncio
async def test_adopt_recommendation_persists_stage_index(db, default_factory, admin_user):
    capa = await _make_capa(db, default_factory.id, admin_user.user_id, d4=None)
    req = AdoptRequest(
        d_step="d4", adopted_text="根因-阶段2", source="fmea_graph",
        stage_index=2, item_ref={"failure_cause_node_id": "c1"},
    )
    adoption, new_value = await adopt_recommendation(db, capa, req, admin_user)
    assert new_value == "根因-阶段2"
    rows = (await db.execute(
        select(CapaAIAdoption).where(CapaAIAdoption.capa_id == capa.report_id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].stage_index == 2
    assert adoption.stage_index == 2
