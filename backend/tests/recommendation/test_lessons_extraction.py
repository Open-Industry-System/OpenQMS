"""D7 lessons 抽取测试（Task 13）。

advance_capa D7_PREVENTION → D8_CLOSURE 在闸口（Task 12）通过后、状态 mutation 前
于 savepoint 内抽 d7_prevention lessons，fail-closed：抽取失败 → savepoint rollback
+ 状态未 mutate + 无 TRANSITION audit + 无 lesson 行。
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_lesson import CapaLessonLearned
from app.services.capa_service import advance_capa

pytestmark = pytest.mark.requires_db


async def _make_capa(db, factory_id, user_id, *, d7_prevention="", status="D7_PREVENTION"):
    capa = CAPAEightD(
        report_id=uuid.uuid4(),
        document_no=f"8D-LESSON-{uuid.uuid4().hex[:6]}",
        title="t",
        product_line_code="DC-DC-100",
        factory_id=factory_id,
        created_by=user_id,
        status=status,
        d5_correction="措施A",
        d7_prevention=d7_prevention,
    )
    db.add(capa)
    await db.flush()
    return capa


@pytest.mark.asyncio
async def test_d7_lessons_extracted_on_advance(db, default_factory, admin_user):
    # 无 FMEA → 闸口平凡通过 → 抽 d7_prevention lessons
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        d7_prevention="更新防呆工装避免误装。\n增加检测工序识别偏移。完善流程制度。",
    )
    advanced = await advance_capa(db, capa, admin_user.user_id)
    assert advanced.status == "D8_CLOSURE"

    lessons = (
        await db.execute(
            select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id)
        )
    ).scalars().all()
    assert lessons and all(l.source_d_step == "d7" for l in lessons)
    # 三句非空 → 至少 3 条 lesson
    assert len(lessons) >= 3
    # category 启发式覆盖
    cats = {l.category for l in lessons}
    assert "prevention" in cats  # "防呆"
    assert "detection" in cats  # "检测"
    assert "systemic" in cats  # "流程制度"


@pytest.mark.asyncio
async def test_d7_extraction_failure_blocks_transition(db, default_factory, admin_user, monkeypatch):
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        d7_prevention="预防性措施一。\n预防性措施二。",
    )

    from app.services import capa_lessons_service as svc

    async def _boom(*a, **kw):
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(svc, "enqueue_embedding", _boom)

    with pytest.raises(ValueError, match="D7 lessons 抽取失败"):
        await advance_capa(db, capa, admin_user.user_id)

    # R4：重查 DB（非仅内存对象）确认状态未推进 + 无 TRANSITION audit + 无 lesson 行
    await db.refresh(capa)
    assert capa.status == "D7_PREVENTION"
    audits = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.record_id == capa.report_id,
                AuditLog.action == "TRANSITION",
            )
        )
    ).scalars().all()
    assert len(audits) == 0
    lessons = (
        await db.execute(
            select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id)
        )
    ).scalars().all()
    assert len(lessons) == 0


@pytest.mark.asyncio
async def test_d7_no_d8_closure_extracted(db, default_factory, admin_user):
    # D7→D8 时 d8_closure 为空 → 不产 source_d_step='d8' 行
    capa = await _make_capa(
        db, default_factory.id, admin_user.user_id,
        d7_prevention="预防措施。\n检测措施。",
    )
    capa.d8_closure = None
    await db.flush()

    advanced = await advance_capa(db, capa, admin_user.user_id)
    assert advanced.status == "D8_CLOSURE"

    lessons = (
        await db.execute(
            select(CapaLessonLearned).where(CapaLessonLearned.capa_id == capa.report_id)
        )
    ).scalars().all()
    assert lessons  # d7 lessons 有
    assert not any(l.source_d_step == "d8" for l in lessons)