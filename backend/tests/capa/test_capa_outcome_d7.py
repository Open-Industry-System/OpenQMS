"""D7 complete history and strict DTO contracts."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select, text, update

from app.models.capa import CapaD7NodeAction, CapaRootCauseVerification
from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.models.audit import AuditLog
from app.schemas.capa_outcome_review import CapaOutcomeReview
from app.services.capa_review_guard import OutcomeReviewConflict
from app.services.version_service import create_fmea_version
from tests.capa.test_capa_outcome_review import read

pytestmark = pytest.mark.requires_db


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('reason', 'changed reason'), ('status', 'verified'),
    ('prevention_control_name_after', 'changed control'), ('recommendation_hash', '1234567890abcdef'),
    ('acted_at', datetime(2030, 1, 1, tzinfo=UTC))])
async def test_d7_full_fields_participate_in_revision(review_case, field, value):
    async with review_case.session_factory() as db:
        action = CapaD7NodeAction(capa_id=review_case.report_id, factory_id=review_case.factory_id,
            action='skipped', failure_mode_node_id='rule:known', match_source='rule',
            reason='not applicable', acted_by=review_case.actor_id)
        db.add(action)
        await db.commit()
        identifier = action.action_id
    old = await read(review_case)
    async with review_case.session_factory() as db:
        await db.execute(update(CapaD7NodeAction).where(CapaD7NodeAction.action_id == identifier).values(**{field: value}))
        await db.commit()
    changed = await read(review_case)
    assert old.revision != changed.revision
    assert len(changed.d7_actions) == 1
    async with review_case.session_factory() as db:
        await db.execute(delete(CapaD7NodeAction).where(CapaD7NodeAction.action_id == identifier))
        await db.commit()
    assert changed.revision != (await read(review_case)).revision


@pytest.mark.asyncio
async def test_d7_secondary_document_is_not_rebound_to_primary_fmea(review_case, review_sources):
    secondary_id = uuid4()
    try:
        async with review_case.session_factory() as db:
            fmea = FMEADocument(fmea_id=secondary_id, document_no='PFMEA-SECOND-'+secondary_id.hex[:10],
                title='legitimate secondary source', factory_id=review_case.factory_id,
                product_line_code=review_case.product_line_code, created_by=review_case.actor_id,
                graph_data={'nodes': [{'id': 'mode', 'type': 'FailureMode'},
                    {'id': 'cause', 'type': 'FailureCause'}, {'id': 'control', 'type': 'PreventionControl'}],
                    'edges': [{'source': 'cause', 'target': 'mode', 'type': 'CAUSE_OF'}]})
            db.add(fmea)
            await db.commit()
            await create_fmea_version(db, fmea, 'edit', 'controlled secondary', review_case.actor_id)
            (await review_case.report(db)).fmea_ref_id = review_sources.fmea_id
            db.add(CapaD7NodeAction(capa_id=review_case.report_id, factory_id=review_case.factory_id,
                action='confirmed', fmea_id=secondary_id, failure_mode_node_id='mode',
                failure_cause_node_id='cause', prevention_control_node_id='control',
                match_source='graph', acted_by=review_case.actor_id))
            await db.commit()
        result = await read(review_case)
        assert {v.object_id for v in result.documents} == {secondary_id, review_sources.fmea_id}
        assert result.d7_actions[0].fmea_id == secondary_id
        async with review_case.session_factory() as db:
            action = await db.scalar(select(CapaD7NodeAction).where(CapaD7NodeAction.fmea_id == secondary_id))
            action.failure_cause_node_id = 'missing'
            await db.commit()
        with pytest.raises(OutcomeReviewConflict):
            await read(review_case)
    finally:
        async with review_case.session_factory() as db:
            await db.execute(delete(CapaD7NodeAction).where(CapaD7NodeAction.fmea_id == secondary_id))
            await db.execute(text('SET LOCAL session_replication_role = replica'))
            await db.execute(delete(FMEAVersion).where(FMEAVersion.fmea_id == secondary_id))
            await db.execute(delete(FMEADocument).where(FMEADocument.fmea_id == secondary_id))
            await db.execute(delete(AuditLog).where(AuditLog.operated_by == review_case.actor_id,
                AuditLog.table_name == 'fmea_versions'))
            await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [[], 'bad', {'fmea_id': 'bad', 'cause_node_id': 'cause'},
    {'fmea_id': 'bad', 'cause_node_id': 'cause', 'extra': 1}])
async def test_unknown_verification_source_shape_fails_whole_read(review_case, bad):
    async with review_case.session_factory() as db:
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
            review_case.verification_id).values(source_ref=bad))
        await db.commit()
    with pytest.raises(PermissionError):
        await read(review_case)


@pytest.mark.asyncio
async def test_strict_dto_forbids_extra_core_document_and_supplement_fields(review_case):
    result = await read(review_case)
    for part in ['top', 'core', 'supplement']:
        data = result.model_dump(mode='json')
        target = data if part == 'top' else data[part]
        target['unrequested_body'] = 'not allowed'
        with pytest.raises(ValidationError):
            CapaOutcomeReview.model_validate(data)
    from app.schemas.capa_outcome_review import OutcomeDocumentRef
    with pytest.raises(ValidationError):
        OutcomeDocumentRef(module='control_plan', object_id=uuid4(), version_id=uuid4(), sha256='a'*64)


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['cause_type', 'edge'])
async def test_d7_checks_bound_node_types_and_cause_edge(review_case, review_sources, damage):
    async with review_case.session_factory() as db:
        fmea = await db.get(FMEADocument, review_sources.fmea_id)
        fmea.graph_data = {'nodes': [{'id': 'mode', 'type': 'FailureMode'},
            {'id': 'cause', 'type': 'Function' if damage == 'cause_type' else 'FailureCause'}],
            'edges': [] if damage == 'edge' else [{'source': 'cause', 'target': 'mode', 'type': 'CAUSE_OF'}]}
        await db.commit()
        await create_fmea_version(db, fmea, 'edit', 'bound structure test', review_case.actor_id)
        db.add(CapaD7NodeAction(capa_id=review_case.report_id, factory_id=review_case.factory_id,
            action='auto_filled', fmea_id=review_sources.fmea_id, failure_mode_node_id='mode',
            failure_cause_node_id='cause', match_source='graph', acted_by=review_case.actor_id))
        await db.commit()
    with pytest.raises(OutcomeReviewConflict):
        await read(review_case)


@pytest.mark.asyncio
async def test_review_expectation_uses_real_collector_round_and_revision(review_case):
    from tests.capa.outcome_review_support import review_expectation
    result = await read(review_case)
    async with review_case.session_factory() as db:
        expected = await review_expectation(db, await review_case.report(db))
    assert expected == {'expected_outcome_revision': result.revision,
                        'expected_review_round_id': str(result.review_round_id)}
