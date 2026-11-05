"""Expose the already-bound document gate without changing its digest."""
import pytest
from sqlalchemy import update

from app.models.capa_doc_gate import CapaDocgDecision
from tests.capa.test_capa_outcome_review import read

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
@pytest.mark.parametrize('waiver', [False, True])
async def test_outcome_includes_complete_bound_gate_and_responsibility(review_case, waiver):
    from app.services.capa_outcome_review import collect_outcome_material, outcome_revision
    if waiver:
        async with review_case.session_factory() as db:
            await db.execute(update(CapaDocgDecision).where(
                CapaDocgDecision.analysis_id == review_case.owned_ids['analysis_id']).values(
                    no_affected_confirmed=False, waiver_reason='历史条目已移除 <script>unsafe</script>',
                    waiver_items=[{'doc_type': 'control_plan', 'doc_id': str(review_case.report_id),
                                   'target_key': 'removed-item', 'field': 'control_method'}]))
            await db.commit()
    before = await review_case.snapshot()
    result = await read(review_case)
    async with review_case.session_factory() as db:
        material = await collect_outcome_material(db, await review_case.report(db))
    payload = result.model_dump(mode='json')
    expected = dict(material['doc_gate'])
    expected['decided_at'] = expected['decided_at'].replace('+00:00', 'Z')
    assert payload.get('doc_gate') == expected
    assert payload['doc_gate']['decision'] == 'passed'
    assert payload['doc_gate']['decided_by']
    assert payload['doc_gate']['decided_at']
    assert result.revision == outcome_revision(material)
    if waiver:
        assert payload['doc_gate']['waiver_items'][0]['target_key'] == 'removed-item'
        assert '历史条目' not in repr(result)
    assert before == await review_case.snapshot()


@pytest.mark.asyncio
async def test_legacy_without_gate_exposes_null_not_a_synthetic_pass(review_case):
    from sqlalchemy import delete
    await review_case.set_status('D8_CLOSURE')
    async with review_case.session_factory() as db:
        await db.execute(delete(CapaDocgDecision).where(
            CapaDocgDecision.analysis_id == review_case.owned_ids['analysis_id']))
        await db.commit()
    result = await read(review_case)
    assert 'doc_gate' in result.model_dump()
    assert result.doc_gate is None
    assert result.binding_status == 'legacy_unversioned'


@pytest.mark.asyncio
async def test_gate_counts_toward_response_budget(review_case, monkeypatch):
    import app.services.capa_outcome_review as service
    async with review_case.session_factory() as db:
        material = await service.collect_outcome_material(db, await review_case.report(db))
        existing = await service._dto(db, await review_case.report(db), material)
        old_shape = existing.model_dump(mode='json')
        old_shape.pop('doc_gate', None)
        monkeypatch.setattr(service, 'MAX_OUTCOME_REVIEW_BYTES', len(service._encoded(old_shape)) + 2)
        with pytest.raises(service.OutcomeReviewLimit):
            await service._dto(db, await review_case.report(db), material)
        await db.rollback()


@pytest.mark.asyncio
async def test_gate_does_not_bypass_current_authority(review_case):
    await review_case.set_capa_level(0)
    with pytest.raises(PermissionError):
        await read(review_case)
