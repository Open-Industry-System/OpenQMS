"""Bound controlled sources, immutable history, and receipt compatibility."""
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update

from app.models.audit import AuditLog
from app.models.capa import CapaRootCauseVerification
from app.models.capa_doc_gate import CapaDocgDecision
from tests.capa.test_capa_outcome_review import read

pytestmark = pytest.mark.requires_db


async def bind_sources(case, sources, *, modules=('fmea', 'planning'), explicit=False):
    from app.models.fmea_version import FMEAVersion
    from app.models.control_plan_version import ControlPlanVersion
    refs = []
    async with case.session_factory() as db:
        for module in modules:
            model = FMEAVersion if module == 'fmea' else ControlPlanVersion
            identity = model.fmea_id if module == 'fmea' else model.cp_id
            object_id = sources.fmea_id if module == 'fmea' else sources.cp_id
            version = await db.scalar(select(model).where(identity == object_id))
            refs.append({'doc_type': 'control_plan' if module == 'planning' else module,
                'doc_id': str(object_id), 'version_after_id': str(version.version_id), 'sha256': version.sha256_hash})
        decision = await db.scalar(select(CapaDocgDecision).where(
            CapaDocgDecision.analysis_id == case.owned_ids['analysis_id']))
        decision.version_snapshot = refs
        if explicit:
            capa = await case.report(db)
            capa.fmea_ref_id = sources.fmea_id
            verification = await db.get(CapaRootCauseVerification, case.verification_id)
            verification.source_ref = {'fmea_id': str(sources.fmea_id), 'cause_node_id': 'cause'}
        await db.commit()
    return refs


async def approved_receipt(case):
    """Test-only exact Task 4 consumer fixture; no production decision writer."""
    result = await read(case)
    async with case.session_factory() as db:
        doc_decision_id = await db.scalar(select(CapaDocgDecision.decision_id).where(
            CapaDocgDecision.analysis_id == case.owned_ids['analysis_id']).order_by(CapaDocgDecision.revision.desc()).limit(1))
        receipt = {'contract': result.contract, 'round_id': str(result.review_round_id),
                   'revision': result.revision, 'doc_decision_id': str(doc_decision_id),
                   'source_versions': [v.model_dump(mode='json') for v in result.documents]}
        db.add(AuditLog(table_name='capa_eightd', record_id=case.report_id,
            action='D8_APPROVED', operated_by=case.actor_id, factory_id=case.factory_id,
            changed_fields={'old_status': 'D8_APPROVAL_PENDING', 'new_status': 'D8_CLOSURE', 'outcome_review': receipt}))
        capa = await case.report(db)
        capa.status = 'D8_CLOSURE'
        await db.commit()
    return result, receipt


@pytest.mark.asyncio
async def test_bound_gate_versions_and_every_explicit_source_are_returned(review_case, review_sources):
    await bind_sources(review_case, review_sources, explicit=True)
    result = await read(review_case)
    assert {v.module for v in result.documents} == {'fmea', 'planning'}
    assert len(result.documents) == 2
    assert result.verifications[0].source_ref['cause_node_id'] == 'cause'


@pytest.mark.asyncio
@pytest.mark.parametrize('module', ['fmea', 'planning'])
async def test_source_authority_is_separate_from_capa_access(review_case, review_sources, module):
    from app.models.role import RolePermission
    await bind_sources(review_case, review_sources)
    async with review_case.session_factory() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == review_case.owned_ids['role_id'],
            RolePermission.module == module).values(permission_level=0))
        await db.commit()
    with pytest.raises(PermissionError, match='CAPA_OUTCOME_REVIEW_ACCESS_DENIED'):
        await read(review_case)


@pytest.mark.asyncio
async def test_source_snapshot_order_does_not_rebind(review_case, review_sources):
    refs = await bind_sources(review_case, review_sources)
    old = await read(review_case)
    async with review_case.session_factory() as db:
        await db.execute(update(CapaDocgDecision).where(
            CapaDocgDecision.analysis_id == review_case.owned_ids['analysis_id']).values(version_snapshot=list(reversed(refs))))
        await db.commit()
    assert old.revision == (await read(review_case)).revision


@pytest.mark.asyncio
async def test_approval_archive_supplement_and_source_evolution_preserve_binding(review_case, review_sources):
    from app.models.fmea import FMEADocument
    from app.models.control_plan import ControlPlan
    from app.services.version_service import create_cp_version, create_fmea_version
    await bind_sources(review_case, review_sources, explicit=True)
    pending, receipt = await approved_receipt(review_case)
    closed = await read(review_case)
    assert closed.binding_status == 'verified'
    assert closed.revision == pending.revision
    assert closed.review_round_id == pending.review_round_id
    assert closed.decision.action == 'approved'
    async with review_case.session_factory() as db:
        fmea = await db.get(FMEADocument, review_sources.fmea_id)
        fmea.graph_data = {'nodes': [], 'edges': []}
        await db.commit()
        await create_fmea_version(db, fmea, 'edit', 'legitimate new version', review_case.actor_id)
        cp = await db.get(ControlPlan, review_sources.cp_id)
        cp.title = 'legitimate next CP revision'
        await db.commit()
        await create_cp_version(db, cp, 'edit', 'legitimate new CP version', review_case.actor_id)
        capa = await review_case.report(db)
        capa.d8_closure = '结案后补写，不是审核依据'
        db.add(AuditLog(table_name='capa_eightd', record_id=review_case.report_id,
            action='UPDATE', changed_fields={'d8_closure': capa.d8_closure},
            operated_by=review_case.actor_id, factory_id=review_case.factory_id))
        await db.commit()
    supplemented = await read(review_case)
    assert supplemented.binding_status == 'verified'
    assert supplemented.revision == pending.revision
    assert [v.model_dump(mode='json') for v in supplemented.documents] == receipt['source_versions']
    assert supplemented.supplement.updated_by == review_case.actor_id
    assert supplemented.supplement.updated_at is not None
    assert supplemented.supplement.text == '结案后补写，不是审核依据'
    await review_case.set_status('ARCHIVED')
    archived = await read(review_case)
    assert archived.binding_status == 'verified'
    assert archived.revision == pending.revision


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['unknown', 'missing', 'hash', 'wrong_object', 'null_version'])
async def test_bad_gate_binding_fails_whole_read(review_case, review_sources, damage):
    refs = await bind_sources(review_case, review_sources)
    if damage == 'unknown': refs[0]['doc_type'] = 'sop'
    if damage == 'missing': refs[0]['version_after_id'] = str(uuid4())
    if damage == 'hash': refs[0]['sha256'] = '0' * 64
    if damage == 'wrong_object': refs[0]['doc_id'] = str(review_sources.cp_id)
    if damage == 'null_version': refs[0]['version_after_id'] = None
    async with review_case.session_factory() as db:
        await db.execute(update(CapaDocgDecision).where(CapaDocgDecision.analysis_id ==
            review_case.owned_ids['analysis_id']).values(version_snapshot=refs))
        await db.commit()
    from app.services.capa_review_guard import OutcomeReviewConflict
    with pytest.raises((PermissionError, OutcomeReviewConflict)):
        await read(review_case)


@pytest.mark.asyncio
async def test_explicit_pending_fmea_uses_existing_version_and_detects_new_version(review_case, review_sources):
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        capa.fmea_ref_id = review_sources.fmea_id
        await db.commit()
    old = await read(review_case)
    assert len(old.documents) == 1
    assert old.documents[0].object_id == review_sources.fmea_id
    from app.models.fmea import FMEADocument
    from app.services.version_service import create_fmea_version
    async with review_case.session_factory() as db:
        fmea = await db.get(FMEADocument, review_sources.fmea_id)
        await create_fmea_version(db, fmea, 'edit', 'next', review_case.actor_id)
    new = await read(review_case)
    assert old.revision != new.revision
    assert old.documents[0].version_id != new.documents[0].version_id


@pytest.mark.asyncio
@pytest.mark.parametrize('review_sources', [False], indirect=True)
async def test_missing_explicit_version_conflicts_without_writes(review_case, review_sources):
    from app.services.capa_review_guard import OutcomeReviewConflict
    async with review_case.session_factory() as db:
        (await review_case.report(db)).fmea_ref_id = review_sources.fmea_id
        await db.commit()
    before = await review_case.snapshot()
    with pytest.raises(OutcomeReviewConflict):
        await read(review_case)
    assert before == await review_case.snapshot()


@pytest.mark.asyncio
async def test_legacy_pending_round_is_exact_server_uuid5_without_get_writes(review_case):
    from uuid import NAMESPACE_URL, uuid5
    async with review_case.session_factory() as db:
        await db.execute(delete(AuditLog).where(AuditLog.record_id == review_case.report_id))
        capa = await review_case.report(db)
        expected = uuid5(NAMESPACE_URL, f'capa.outcome-review.legacy:public:{capa.report_id}')
        await db.commit()
    before = await review_case.snapshot()
    result = await read(review_case)
    assert result.review_round_id == expected
    assert result.binding_status == 'pending'
    assert before == await review_case.snapshot()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['D8_CLOSURE', 'ARCHIVED'])
async def test_legacy_closed_has_no_fabricated_receipt_or_round(review_case, status):
    await review_case.set_status(status)
    before = await review_case.snapshot()
    result = await read(review_case)
    assert result.binding_status == 'legacy_unversioned'
    assert result.review_round_id is None
    assert result.decision is None
    assert before == await review_case.snapshot()


@pytest.mark.asyncio
async def test_key_rotation_never_resigns_history(review_case, monkeypatch):
    from app.config import settings
    old, receipt = await approved_receipt(review_case)
    monkeypatch.setattr(settings, 'SECRET_KEY', 'rotated-test-only-secret')
    result = await read(review_case)
    assert result.binding_status == 'unverifiable'
    assert result.revision == old.revision == receipt['revision']
    assert result.status == 'D8_CLOSURE'


@pytest.mark.asyncio
async def test_valid_source_ref_change_binds_result_and_existing_version(review_case, review_sources):
    async with review_case.session_factory() as db:
        (await review_case.report(db)).fmea_ref_id = review_sources.fmea_id
        await db.commit()
    old = await read(review_case)
    async with review_case.session_factory() as db:
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id ==
            review_case.verification_id).values(source_ref={'fmea_id': str(review_sources.fmea_id), 'cause_node_id': 'cause'}))
        await db.commit()
    new = await read(review_case)
    assert new.revision != old.revision
    assert new.documents == old.documents


@pytest.mark.asyncio
@pytest.mark.parametrize('module', [[], {}, 1, None])
async def test_malformed_source_module_denies_without_internal_type_error(review_case, module):
    async with review_case.session_factory() as db:
        await db.execute(update(CapaDocgDecision).where(CapaDocgDecision.analysis_id == review_case.owned_ids['analysis_id']).values(
            version_snapshot=[{'doc_type': module, 'doc_id': str(uuid4()), 'version_after_id': str(uuid4()), 'sha256': 'a'*64}]))
        await db.commit()
    with pytest.raises(PermissionError, match='CAPA_OUTCOME_REVIEW_ACCESS_DENIED'):
        await read(review_case)


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['contract', 'round', 'revision', 'revision_unicode', 'flat'])
async def test_exact_nested_receipt_verification_states(review_case, damage):
    old, receipt = await approved_receipt(review_case)
    if damage == 'contract': receipt['contract'] = 'wrong'
    if damage == 'round': receipt.pop('round_id')
    if damage == 'revision': receipt['revision'] = '0' * 64
    if damage == 'revision_unicode': receipt['revision'] = '无法验证'
    async with review_case.session_factory() as db:
        await db.execute(update(AuditLog).where(AuditLog.record_id == review_case.report_id,
            AuditLog.action == 'D8_APPROVED').values(changed_fields=receipt if damage == 'flat' else {'outcome_review': receipt}))
        await db.commit()
    before = await review_case.snapshot()
    result = await read(review_case)
    assert result.binding_status == ('legacy_unversioned' if damage == 'flat' else 'unverifiable')
    assert result.decision.action == 'approved'
    assert result.status == 'D8_CLOSURE'
    assert before == await review_case.snapshot()


@pytest.mark.asyncio
async def test_latest_production_transition_is_round_and_old_rejection_is_not_current(review_case):
    from datetime import UTC, datetime, timedelta
    old = await read(review_case)
    round_id = uuid4()
    async with review_case.session_factory() as db:
        doc_decision_id = await db.scalar(select(CapaDocgDecision.decision_id).where(
            CapaDocgDecision.analysis_id == review_case.owned_ids['analysis_id']))
        db.add(AuditLog(table_name='capa_eightd', record_id=review_case.report_id,
            factory_id=review_case.factory_id, action='D8_REJECTED', operated_by=review_case.actor_id,
            operated_at=datetime.now(UTC), changed_fields={'outcome_review': {
                'contract': old.contract, 'round_id': str(old.review_round_id), 'revision': old.revision,
                'doc_decision_id': str(doc_decision_id), 'source_versions': []}}))
        db.add(AuditLog(log_id=round_id, table_name='capa_eightd', record_id=review_case.report_id,
            factory_id=review_case.factory_id, action='TRANSITION', operated_by=review_case.actor_id,
            operated_at=datetime.now(UTC)+timedelta(seconds=1),
            changed_fields={'old_status': 'D8_GATE_PENDING', 'new_status': 'D8_APPROVAL_PENDING'}))
        await db.commit()
    new = await read(review_case)
    assert new.review_round_id == round_id
    assert new.revision != old.revision
    assert new.decision is None


@pytest.mark.asyncio
async def test_pending_explicit_source_new_version_after_snapshot_conflicts(review_case, review_sources, monkeypatch):
    from app.models.fmea import FMEADocument
    from app.services import capa_outcome_review as service
    from app.services.version_service import create_fmea_version
    from app.services.capa_review_guard import OutcomeReviewConflict
    async with review_case.session_factory() as db:
        (await review_case.report(db)).fmea_ref_id = review_sources.fmea_id
        await db.commit()
    original = service._read_snapshot
    async def changed(*args, **kwargs):
        result = await original(*args, **kwargs)
        async with review_case.session_factory() as db:
            fmea = await db.get(FMEADocument, review_sources.fmea_id)
            await create_fmea_version(db, fmea, 'edit', 'concurrent new source version', review_case.actor_id)
        return result
    monkeypatch.setattr(service, '_read_snapshot', changed)
    with pytest.raises(OutcomeReviewConflict):
        await read(review_case)


@pytest.mark.asyncio
async def test_missing_closed_binding_never_uses_latest_version(review_case, review_sources):
    from app.services.capa_review_guard import OutcomeReviewConflict
    async with review_case.session_factory() as db:
        (await review_case.report(db)).fmea_ref_id = review_sources.fmea_id
        await db.commit()
    await review_case.set_status('D8_CLOSURE')
    with pytest.raises(OutcomeReviewConflict):
        await read(review_case)
