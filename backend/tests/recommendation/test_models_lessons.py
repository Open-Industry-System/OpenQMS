import uuid

import pytest
from sqlalchemy import select

from app.models.capa import CAPAEightD, CapaD7NodeAction
from app.models.capa_lesson import CapaLessonLearned
from app.models.fmea import FMEADocument

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
async def test_persist_lesson(db, default_factory, admin_user):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no="8D-L-001",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        created_by=admin_user.user_id,
    )
    db.add(capa)
    await db.flush()
    lesson = CapaLessonLearned(
        lesson_id=uuid.uuid5(
            uuid.NAMESPACE_URL, f"capa_lesson:{capa.report_id}:d7:螺栓尺寸超差"
        ),
        capa_id=capa.report_id,
        factory_id=default_factory.id,
        product_line_code="DC-DC-100",
        lesson_text="螺栓尺寸超差",
        lesson_text_normalized="螺栓尺寸超差",
        category="prevention",
        source_d_step="d7",
    )
    db.add(lesson)
    # CapaD7NodeAction.recommendation_hash 列存在
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(),
        document_no="PFMEA-L-001",
        title="t",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        factory_id=default_factory.id,
        status="draft",
        created_by=admin_user.user_id,
        graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea)
    await db.flush()
    act = CapaD7NodeAction(
        action_id=uuid.uuid4(),
        capa_id=capa.report_id,
        factory_id=default_factory.id,
        action="confirmed",
        fmea_id=fmea.fmea_id,
        failure_mode_node_id="fm-1",
        match_source="linked",
        acted_by=admin_user.user_id,
        recommendation_hash="abc123def456abcd",
    )
    db.add(act)
    await db.flush()
    assert (
        await db.scalar(
            select(CapaLessonLearned).where(
                CapaLessonLearned.lesson_id == lesson.lesson_id
            )
        )
    ).category == "prevention"
    assert (
        await db.scalar(
            select(CapaD7NodeAction).where(CapaD7NodeAction.action_id == act.action_id)
        )
    ).recommendation_hash == "abc123def456abcd"
