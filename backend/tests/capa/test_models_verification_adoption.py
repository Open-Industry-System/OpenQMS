import uuid
import pytest
from sqlalchemy import select
from app.models.capa import (
    CAPAEightD, CapaRootCauseVerification, CapaAIAdoption, CapaD7NodeAction,
)
from app.models.fmea import FMEADocument

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_can_persist_three_new_tables(db, default_factory, admin_user):
    capa = CAPAEightD(
        report_id=uuid.uuid4(), document_no="8D-MODEL-001", title="t",
        product_line_code="DC-DC-100", factory_id=default_factory.id,
        created_by=admin_user.user_id,
    )
    db.add(capa); await db.flush()

    # CapaD7NodeAction.fmea_id 是 FK→fmea_documents.fmea_id，必须先建真实 FMEA 行
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-MODEL-001", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", created_by=admin_user.user_id,
        graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea); await db.flush()

    rcv = CapaRootCauseVerification(
        verification_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=default_factory.id,
        root_cause_text="螺栓尺寸超差", method="千分尺复测", result="4/5 超差",
        is_verified=True, verified_by=admin_user.user_id,
    )
    db.add(rcv)

    adopt = CapaAIAdoption(
        adoption_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=default_factory.id,
        d_step="d4", adopted_text="螺栓尺寸超差", source="fmea_graph",
        stage_index=None, adopted_by=admin_user.user_id,
    )
    db.add(adopt)

    d7 = CapaD7NodeAction(
        action_id=uuid.uuid4(), capa_id=capa.report_id, factory_id=default_factory.id,
        action="confirmed", fmea_id=fmea.fmea_id, failure_mode_node_id="fm-1",
        failure_cause_node_id=None, match_source="linked", acted_by=admin_user.user_id,
    )
    db.add(d7); await db.flush()

    assert (await db.scalar(select(CapaRootCauseVerification).where(
        CapaRootCauseVerification.verification_id == rcv.verification_id))).is_verified is True
    assert (await db.scalar(select(CapaAIAdoption).where(
        CapaAIAdoption.adoption_id == adopt.adoption_id))).source == "fmea_graph"
    assert (await db.scalar(select(CapaD7NodeAction).where(
        CapaD7NodeAction.action_id == d7.action_id))).action == "confirmed"
