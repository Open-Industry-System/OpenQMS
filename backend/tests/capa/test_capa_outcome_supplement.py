"""Closure supplements remain outside both legacy and real approval bindings."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_lesson import CapaLessonLearned
from app.services.capa_service import update_capa
from tests.capa.test_capa_outcome_decision import decision_provider, expectation, bind_decision_sources
from tests.capa.test_capa_outcome_review import read

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
@pytest.mark.parametrize('real_receipt', [False, True], ids=['legacy', 'production-receipt'])
async def test_supplement_never_rebinds_approval(
    review_case, review_http_client, review_sources, decision_provider, real_receipt,
):
    from app.services.capa_lessons_service import _extract_lessons
    async with review_case.session_factory() as db:
        await _extract_lessons(db, await review_case.report(db), 'd7')
        await db.commit()
    if real_receipt:
        await bind_decision_sources(review_case, review_sources)
        seen = await expectation(review_case)
        approved = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
            json={'target_state': 'D8_CLOSURE', **seen})
        assert approved.status_code == 200, approved.text
    else:
        await review_case.set_status('D8_CLOSURE')
    before = await read(review_case)
    assert before.binding_status == ('verified' if real_receipt else 'legacy_unversioned')
    async with review_case.session_factory() as db:
        approvals = deepcopy(list((await db.execute(select(AuditLog.log_id, AuditLog.changed_fields).where(
            AuditLog.record_id == review_case.report_id, AuditLog.action == 'D8_APPROVED'))).all()))
        d7_before = list((await db.execute(select(CapaLessonLearned.lesson_id, CapaLessonLearned.lesson_text,
            CapaLessonLearned.tags).where(CapaLessonLearned.capa_id == review_case.report_id,
                CapaLessonLearned.source_d_step == 'd7'))).all())
        await update_capa(db, await review_case.report(db), {'d8_closure': '补充说明。补充说明。'}, review_case.actor_id)
    after = await read(review_case)
    assert after.revision == before.revision
    assert after.review_round_id == before.review_round_id
    assert after.decision == before.decision
    assert after.documents == before.documents
    assert after.core == before.core
    assert after.binding_status == before.binding_status
    assert after.supplement.review_scope == 'unreviewed_supplement'
    assert after.supplement.text == '补充说明。补充说明。'
    assert after.supplement.updated_by == review_case.actor_id
    async with review_case.session_factory() as db:
        audit = (await db.execute(select(AuditLog.operated_at).where(
            AuditLog.record_id == review_case.report_id, AuditLog.action == 'UPDATE',
            AuditLog.changed_fields.has_key('d8_closure')))).scalar_one()
        assert after.supplement.updated_at == audit
        assert list((await db.execute(select(AuditLog.log_id, AuditLog.changed_fields).where(
            AuditLog.record_id == review_case.report_id, AuditLog.action == 'D8_APPROVED'))).all()) == approvals
        assert list((await db.execute(select(CapaLessonLearned.lesson_id, CapaLessonLearned.lesson_text,
            CapaLessonLearned.tags).where(CapaLessonLearned.capa_id == review_case.report_id,
                CapaLessonLearned.source_d_step == 'd7'))).all()) == d7_before
        lessons = list((await db.scalars(select(CapaLessonLearned).where(
            CapaLessonLearned.capa_id == review_case.report_id, CapaLessonLearned.source_d_step == 'd8'))).all())
        assert len(lessons) == 1
        assert lessons[0].tags == ['review_scope:unreviewed_supplement']
        assert all('approved' not in tag for row in d7_before for tag in row.tags)


@pytest.mark.asyncio
async def test_mixed_supplement_put_is_atomic_and_archive_still_frozen(review_case, review_http_client):
    await review_case.set_status('D8_CLOSURE')
    before = await review_case.snapshot()
    response = await review_http_client.put(f'/api/capa/{review_case.report_id}',
        json={'d8_closure': '不应保存', 'd5_correction': '覆盖核心'})
    assert response.status_code == 409
    assert response.json()['detail'] == 'CAPA_REVIEWED_CONTENT_LOCKED'
    assert await review_case.snapshot() == before
    await review_case.set_status('ARCHIVED')
    before = await review_case.snapshot()
    response = await review_http_client.put(f'/api/capa/{review_case.report_id}', json={'d8_closure': '不应保存'})
    assert response.status_code == 400
    assert await review_case.snapshot() == before
    async with review_case.session_factory() as db:
        assert await db.scalar(select(CapaLessonLearned.lesson_id).where(
            CapaLessonLearned.capa_id == review_case.report_id)) is None


@pytest.mark.asyncio
async def test_supplement_metadata_without_audit_does_not_guess_from_main_row(review_case):
    await review_case.set_status('D8_CLOSURE')
    async with review_case.session_factory() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id)
            .values(d8_closure='无历史修改责任', updated_at=datetime(2035, 1, 1, tzinfo=UTC)))
        await db.commit()
    result = await read(review_case)
    assert result.supplement.text == '无历史修改责任'
    assert result.supplement.updated_by is None
    assert result.supplement.updated_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize('known_actor', [True, False])
async def test_supplement_metadata_uses_only_latest_relevant_update_without_private_copies(review_case, known_actor):
    await review_case.set_status('D8_CLOSURE')
    when = datetime(2026, 10, 24, tzinfo=UTC)
    async with review_case.session_factory() as db:
        base = dict(table_name='capa_eightd', record_id=review_case.report_id, action='UPDATE',
            factory_id=review_case.factory_id, operated_by=review_case.actor_id,
            changed_fields={'d8_closure': '旧修改'}, operated_at=when - timedelta(days=1))
        db.add(AuditLog(**base))
        # Private bodies do not belong to the metadata DTO or its byte budget.
        db.add(AuditLog(**{**base, 'changed_fields': {'d8_closure': {'before': 'PRIVATE' * 1500000,
            'after': 'PRIVATE_NEW'}}, 'operated_at': when,
            'operated_by': review_case.actor_id if known_actor else None}))
        for override in [dict(action='D8_LESSONS_EXTRACTED'), dict(table_name='unrelated'),
                         dict(record_id=uuid4()), dict(factory_id=None), dict(changed_fields={'title': '维护'})]:
            db.add(AuditLog(**{**base, 'operated_at': when + timedelta(days=1), **override}))
        await db.commit()
    before = await review_case.snapshot()
    result = await read(review_case)
    assert result.supplement.updated_by == (review_case.actor_id if known_actor else None)
    assert result.supplement.updated_at == when
    assert set(result.supplement.model_dump()) == {'text', 'review_scope', 'updated_by', 'updated_at'}
    assert 'PRIVATE' not in result.model_dump_json()
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
async def test_failed_supplement_rebuild_restores_tags_outbox_and_audit(review_case, monkeypatch):
    from app.models.document_embedding import EmbeddingSyncOutbox
    from app.services import capa_lessons_service
    await review_case.set_status('D8_CLOSURE')
    async with review_case.session_factory() as db:
        await update_capa(db, await review_case.report(db), {'d8_closure': '旧补充甲。旧补充乙。'}, review_case.actor_id)
    async def derived_snapshot():
        async with review_case.session_factory() as db:
            return (
                list((await db.execute(select(CapaLessonLearned.__table__).where(
                    CapaLessonLearned.capa_id == review_case.report_id).order_by(CapaLessonLearned.lesson_id))).all()),
                list((await db.execute(select(EmbeddingSyncOutbox.__table__).where(
                    EmbeddingSyncOutbox.factory_id == review_case.factory_id).order_by(EmbeddingSyncOutbox.id))).all()),
            )
    before = await review_case.snapshot()
    derived_before = await derived_snapshot()
    async def fail_enqueue(*args, **kwargs):
        raise RuntimeError('unit outbox failure')
    monkeypatch.setattr(capa_lessons_service, 'enqueue_embedding', fail_enqueue)
    async with review_case.session_factory() as db:
        with pytest.raises(ValueError, match='D8 lessons 抽取失败'):
            await update_capa(db, await review_case.report(db), {'d8_closure': '不应保存的新补充'}, review_case.actor_id)
    assert await derived_snapshot() == derived_before
    assert await review_case.snapshot() == before
