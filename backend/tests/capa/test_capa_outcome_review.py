"""Committed, complete outcome material and current-authority read contract."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, update

from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.capa_doc_gate import CapaDocgDecision

pytestmark = pytest.mark.requires_db


async def read(case):
    from app.services.capa_outcome_review import read_outcome_review
    async with case.session_factory() as db:
        return await read_outcome_review(db, await case.scope(db), case.report_id)


@pytest.mark.asyncio
async def test_all_verification_rows_participate_in_revision(review_case):
    old = await read(review_case)
    async with review_case.session_factory() as db:
        await db.execute(update(CapaRootCauseVerification).where(
            CapaRootCauseVerification.verification_id == review_case.verification_id
        ).values(result='复测结果已补充'))
        await db.commit()
    new = await read(review_case)
    assert old.revision != new.revision
    assert new.verifications[0].result == '复测结果已补充'


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['d4_root_cause', 'd5_correction', 'd6_verification',
                                    'd7_prevention', 'severity', 'd4_retry_count'])
async def test_core_whitelist_changes_revision(review_case, field):
    old = await read(review_case)
    async with review_case.session_factory() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id)
                         .values(**{field: 2 if field == 'd4_retry_count' else 'changed'}))
        await db.commit()
    assert old.revision != (await read(review_case)).revision


@pytest.mark.asyncio
async def test_get_is_pure_strict_complete_and_does_not_repr_bodies(review_case):
    from app.services.capa_outcome_review import collect_outcome_material
    before = await review_case.snapshot()
    result = await read(review_case)
    assert result.contract == 'capa.outcome-review.v1'
    assert result.binding_status == 'pending'
    assert result.review_round_id is not None
    assert result.decision is None
    assert result.core.d4_root_cause == '扭矩不足'
    assert result.supplement.review_scope == 'unreviewed_supplement'
    assert '扭矩不足' not in repr(result)
    async with review_case.session_factory() as db:
        material = await collect_outcome_material(db, await review_case.report(db))
        assert set(material) == {'contract', 'tenant_identity', 'report_id', 'factory_id',
            'product_line_code', 'round_id', 'core', 'verifications', 'd7_actions', 'doc_gate', 'source_versions'}
        assert '扭矩不足' not in repr(material)
    assert before == await review_case.snapshot()


@pytest.mark.asyncio
async def test_complete_collection_over_200_includes_tail_insert_delete_and_evidence(review_case):
    async with review_case.session_factory() as db:
        db.add_all([CapaRootCauseVerification(capa_id=review_case.report_id,
            factory_id=review_case.factory_id, root_cause_text=f'cause-{i}',
            verification_id=uuid4(), conclusion='pending', evidence_attachments=[]) for i in range(205)])
        await db.commit()
    old = await read(review_case)
    assert len(old.verifications) == 206
    ids = [str(v.verification_id) for v in old.verifications]
    assert ids == sorted(ids)
    tail = old.verifications[-1].verification_id
    async with review_case.session_factory() as db:
        await db.execute(update(CapaRootCauseVerification).where(
            CapaRootCauseVerification.verification_id == tail).values(evidence_attachments=[{'name': 'tail evidence'}]))
        await db.commit()
    changed = await read(review_case)
    assert changed.revision != old.revision
    async with review_case.session_factory() as db:
        await db.execute(delete(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id == tail))
        await db.commit()
    removed = await read(review_case)
    assert len(removed.verifications) == 205
    assert removed.revision != changed.revision


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('result', 'new'), ('method', 'measurement'),
    ('evidence_attachments', [{'file': 'proof'}]), ('updated_at', datetime(2030, 1, 1, tzinfo=UTC))])
async def test_child_actual_fields_and_version_are_bound(review_case, field, value):
    old = await read(review_case)
    async with review_case.session_factory() as db:
        await db.execute(update(CapaRootCauseVerification).where(
            CapaRootCauseVerification.verification_id == review_case.verification_id).values(**{field: value}))
        await db.commit()
    assert old.revision != (await read(review_case)).revision


@pytest.mark.asyncio
async def test_canonical_order_and_key_order_are_deterministic(review_case):
    from app.services.capa_outcome_review import collect_outcome_material, outcome_revision
    async with review_case.session_factory() as db:
        material = await collect_outcome_material(db, await review_case.report(db))
    reordered = dict(reversed(list(material.items())))
    assert outcome_revision(material) == outcome_revision(reordered)
    assert len(outcome_revision(material)) == 64


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('d8_closure', '补充'), ('updated_at', datetime(2030, 1, 1, tzinfo=UTC)), ('title', 'maintenance')])
async def test_non_core_maintenance_does_not_rebind(review_case, field, value):
    old = await read(review_case)
    async with review_case.session_factory() as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == review_case.report_id).values(**{field: value}))
        await db.commit()
    assert old.revision == (await read(review_case)).revision


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['D1_TEAM', 'D4_ANALYSIS', 'D7_PREVENTION', 'D8_GATE_PENDING'])
async def test_early_stages_have_no_outcome_package(review_case, status):
    await review_case.set_status(status)
    with pytest.raises(LookupError, match='CAPA_OUTCOME_REVIEW_UNAVAILABLE'):
        await read(review_case)


@pytest.mark.asyncio
async def test_live_capa_revocation_denies_even_with_stale_scope(review_case):
    await review_case.set_capa_level(0)
    with pytest.raises(PermissionError):
        await read(review_case)


@pytest.mark.asyncio
async def test_evidence_collection_order_is_not_a_business_change(review_case):
    values = [{'attachment_id': 'b', 'name': 'B'}, {'attachment_id': 'a', 'name': 'A'}]
    async with review_case.session_factory() as db:
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
            review_case.verification_id).values(evidence_attachments=values))
        await db.commit()
    old = await read(review_case)
    async with review_case.session_factory() as db:
        from sqlalchemy import select
        timestamp = await db.scalar(select(CapaRootCauseVerification.updated_at).where(
            CapaRootCauseVerification.verification_id == review_case.verification_id))
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
            review_case.verification_id).values(evidence_attachments=list(reversed(values)), updated_at=timestamp))
        # Pin the child version to isolate ordering from an actual version bump.
        await db.commit()
    assert (await read(review_case)).revision == old.revision


@pytest.mark.asyncio
async def test_gate_decision_revision_changes_digest(review_case):
    old = await read(review_case)
    async with review_case.session_factory() as db:
        await db.execute(update(CapaDocgDecision).where(
            CapaDocgDecision.analysis_id == review_case.owned_ids['analysis_id']).values(revision=1))
        await db.commit()
    assert old.revision != (await read(review_case)).revision
