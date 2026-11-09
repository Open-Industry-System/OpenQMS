"""Production D8 decisions, committed HTTP and direct-service contracts."""
import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.schemas.capa import AdvanceRequest
from app.services.capa_service import advance_capa, update_capa
from app.services.capa_review_guard import OutcomeReviewRequired
from tests.capa.test_capa_outcome_review import read

pytestmark = pytest.mark.requires_db


async def expectation(case):
    result = await read(case)
    return dict(expected_outcome_revision=result.revision,
                expected_review_round_id=str(result.review_round_id))


@pytest.fixture
def decision_provider(monkeypatch):
    """Only external provider responses are replaced; all closure code is real."""
    from app.services.agent import provider_adapter
    from app.services.agent.provider_adapter import ProviderClient
    async def client(db):
        return ProviderClient(provider='openai', client=object(), model='task4-unit')
    async def complete(pc, prompt, schema):
        assert 'lesson_summary' in schema['properties']
        return {'lesson_summary': '已实施措施及验证结果', 'tags': ['措施', '验证', '预防']}
    monkeypatch.setattr(provider_adapter, 'build_client', client)
    monkeypatch.setattr(provider_adapter, 'complete_json', complete)


@pytest.mark.asyncio
@pytest.mark.parametrize('target,reason', [('D8_CLOSURE', None), ('D7_PREVENTION', '证据不足')])
async def test_without_seen_revision_is_rejected(review_http_client, review_case, target, reason):
    before = await review_case.snapshot()
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': target, 'reject_reason': reason})
    assert response.status_code == 409
    assert response.json()['detail'] == 'CAPA_OUTCOME_REVIEW_REQUIRED'
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['d6_verification', 'verification'])
async def test_stale_material_rejected(review_http_client, review_case, field):
    seen = await expectation(review_case)
    async with review_case.session_factory() as db:
        if field == 'verification':
            row = await db.get(CapaRootCauseVerification, review_case.verification_id)
            row.result = '补充验证结果'
        else:
            await update_capa(db, await review_case.report(db), {field: '补充复测'}, review_case.actor_id)
        await db.commit()
    before = await review_case.snapshot()
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D8_CLOSURE', **seen})
    assert response.status_code == 409
    assert response.json()['detail'] == 'CAPA_OUTCOME_REVIEW_CHANGED'
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
async def test_direct_service_without_expectation_is_rejected(review_case):
    async with review_case.session_factory() as db:
        with pytest.raises(OutcomeReviewRequired):
            await advance_capa(db, await review_case.report(db), review_case.actor_id,
                AdvanceRequest(target_state='D8_CLOSURE'))


@pytest.mark.asyncio
async def test_edit_cannot_approve_with_real_token(review_http_client, review_case):
    seen = await expectation(review_case)
    await review_case.set_capa_level(3)
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D8_CLOSURE', **seen})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_empty_rejection_reason_still_rejected(review_http_client, review_case):
    seen = await expectation(review_case)
    before = await review_case.snapshot()
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D7_PREVENTION', 'reject_reason': '  ', **seen})
    assert response.status_code == 400
    assert response.json()['detail'] == '驳回需填写理由'
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
async def test_actual_approval_receipt_reader_and_archive(review_http_client, review_case, decision_provider):
    seen = await expectation(review_case)
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D8_CLOSURE', **seen})
    assert response.status_code == 200, response.text
    async with review_case.session_factory() as db:
        audit = (await db.scalars(select(AuditLog).where(AuditLog.record_id == review_case.report_id,
            AuditLog.action == 'D8_APPROVED'))).one()
        receipt = audit.changed_fields['outcome_review']
        assert set(receipt) == {'contract', 'round_id', 'revision', 'doc_decision_id', 'source_versions'}
        assert receipt['revision'] == seen['expected_outcome_revision']
        assert receipt['round_id'] == seen['expected_review_round_id']
    result = await read(review_case)
    assert result.binding_status == 'verified'
    assert result.decision.action == 'approved'
    assert str(result.decision.actor_id) == str(review_case.actor_id)
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance', json={})
    assert response.status_code == 200
    assert (await read(review_case)).binding_status == 'verified'


@pytest.mark.asyncio
async def test_rejection_receipt_and_resubmitted_round(review_http_client, review_case):
    seen = await expectation(review_case)
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D7_PREVENTION', 'reject_reason': '验证不足', **seen})
    assert response.status_code == 200, response.text
    async with review_case.session_factory() as db:
        audit = (await db.scalars(select(AuditLog).where(AuditLog.record_id == review_case.report_id,
            AuditLog.action == 'D8_REJECTED'))).one()
        assert set(audit.changed_fields['outcome_review']) == {'contract', 'round_id', 'revision', 'doc_decision_id', 'source_versions'}
        assert audit.changed_fields['reject_reason'] == '验证不足'
        capa = await review_case.report(db)
        capa.status = 'D8_GATE_PENDING'
        await db.commit()
        await advance_capa(db, capa, review_case.actor_id, AdvanceRequest(target_state='D8_APPROVAL_PENDING'))
    new = await read(review_case)
    assert str(new.review_round_id) != seen['expected_review_round_id']
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D7_PREVENTION', 'reject_reason': '旧轮次', **seen})
    assert response.status_code == 409


async def bind_decision_sources(case, sources):
    """A gate CP plus explicit FMEA outside its snapshot, with real C9 inputs."""
    from tests.capa.test_capa_outcome_sources import bind_sources
    from app.models.capa_doc_gate import CapaDocgAnalysis
    from app.services.capa_doc_gate_service import _build_allowlist, _compute_input_hash
    await bind_sources(case, sources, modules=('planning',), explicit=True)
    async with case.session_factory() as db:
        capa = await case.report(db)
        analysis = await db.get(CapaDocgAnalysis, case.owned_ids['analysis_id'])
        analysis.analysis_input_hash = _compute_input_hash(capa, await _build_allowlist(db, capa))
        await db.commit()


@pytest.mark.asyncio
async def test_actual_source_receipt_consumed_by_reader_and_reference_collector(
    review_case, review_sources, decision_provider,
):
    from app.services.capa_review_source_guard import _source_capa_ids
    from app.services.capa_outcome_review import collect_outcome_material
    await bind_decision_sources(review_case, review_sources)
    seen = await expectation(review_case)
    async with review_case.session_factory() as db:
        await advance_capa(db, await review_case.report(db), review_case.actor_id,
            AdvanceRequest(target_state='D8_CLOSURE', **seen))
        audit = (await db.scalars(select(AuditLog).where(AuditLog.record_id == review_case.report_id,
            AuditLog.action == 'D8_APPROVED'))).one()
        receipt = audit.changed_fields['outcome_review']
        material = await collect_outcome_material(db, await review_case.report(db))
        assert material['source_versions'] == receipt['source_versions']
        assert {v['module'] for v in receipt['source_versions']} == {'fmea', 'planning'}
        assert await _source_capa_ids(db, 'planning', review_sources.cp_id) == {review_case.report_id}
        # Isolate receipt-only lookup inside a rolled-back test transaction; do
        # not manufacture a receipt or persist changes to reviewed material.
        capa = await review_case.report(db)
        capa.fmea_ref_id = None
        verification = await db.get(CapaRootCauseVerification, review_case.verification_id)
        verification.source_ref = None
        await db.flush()
        assert await _source_capa_ids(db, 'fmea', review_sources.fmea_id) == {review_case.report_id}
        await db.rollback()
    result = await read(review_case)
    assert result.binding_status == 'verified'
    assert result.revision == seen['expected_outcome_revision']
    assert len(result.documents) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('module', ['capa', 'fmea', 'planning'])
async def test_direct_service_requires_current_authority_with_real_token(review_case, review_sources, module):
    from sqlalchemy import update
    from app.models.role import RolePermission
    await bind_decision_sources(review_case, review_sources)
    seen = await expectation(review_case)
    async with review_case.session_factory() as cached:
        capa = await review_case.report(cached)
        async with review_case.session_factory() as db:
            await db.execute(update(RolePermission).where(RolePermission.role_id == review_case.owned_ids['role_id'],
                RolePermission.module == module).values(permission_level=0 if module != 'capa' else 3))
            await db.commit()
        before = await review_case.snapshot()
        with pytest.raises(PermissionError):
            await advance_capa(cached, capa, review_case.actor_id, AdvanceRequest(target_state='D8_CLOSURE', **seen))
        await cached.rollback()
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize('missing', ['expected_outcome_revision', 'expected_review_round_id'])
async def test_partial_expectation_rejected(review_http_client, review_case, missing):
    seen = await expectation(review_case)
    seen.pop(missing)
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D7_PREVENTION', 'reject_reason': '需补证据', **seen})
    assert response.status_code == 409
    assert response.json()['detail'] == 'CAPA_OUTCOME_REVIEW_REQUIRED'


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['d4_root_cause', 'd5_correction', 'd6_verification', 'passed'])
async def test_current_outcome_prerequisites_not_nonempty_text_inference(review_http_client, review_case, field):
    async with review_case.session_factory() as db:
        if field == 'passed':
            verification = await db.get(CapaRootCauseVerification, review_case.verification_id)
            verification.conclusion, verification.is_verified = 'failed', False
        else:
            (await review_case.report(db)).__setattr__(field, '  ')
        # Keep the gate C9 accurate, so this exercises outcome prerequisites.
        from app.models.capa_doc_gate import CapaDocgAnalysis
        from app.services.capa_doc_gate_service import _compute_input_hash
        await db.flush()
        (await db.get(CapaDocgAnalysis, review_case.owned_ids['analysis_id'])).analysis_input_hash = _compute_input_hash(await review_case.report(db), [])
        await db.commit()
    seen = await expectation(review_case)
    before = await review_case.snapshot()
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D8_CLOSURE', **seen})
    assert response.status_code == 400
    assert 'D8 审批需' in response.json()['detail']
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
async def test_current_cp_version_gate_rechecked_at_approval(review_http_client, review_case, review_sources):
    from app.models.control_plan import ControlPlan
    from app.services.version_service import create_cp_version
    await bind_decision_sources(review_case, review_sources)
    seen = await expectation(review_case)
    async with review_case.session_factory() as db:
        cp = await db.get(ControlPlan, review_sources.cp_id)
        await create_cp_version(db, cp, 'edit', 'new version after reading', review_case.actor_id)
    # CP is bound to its gate version: the token remains unchanged but C8 must fail.
    assert await expectation(review_case) == seen
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D8_CLOSURE', **seen})
    assert response.status_code == 400
    assert response.json()['detail'] == '文档已变更，请重新审核'


@pytest.mark.asyncio
async def test_final_gate_after_real_mes_outbox_rolls_back_and_retry_is_single_decision(
    review_case, decision_provider, monkeypatch,
):
    import asyncio
    from uuid import uuid4
    from sqlalchemy import delete, update
    from app.models.mes import MESConnection, MESPushOutbox
    from app.models.role import RolePermission
    from app.models.knowledge_entry import KnowledgeEntry
    from app.services.mes_service import MESPushService
    from tests.capa.test_capa_review_concurrency import no_closure_effects
    case = review_case
    connection_id = uuid4()
    async with case.session_factory() as db:
        db.add(MESConnection(connection_id=connection_id, name='task4 owned mock MES', connector_type='mock',
            config={}, is_active=True, product_line_code=case.product_line_code, factory_id=case.factory_id,
            created_by=case.actor_id))
        await db.commit()
    staged, resume = asyncio.Event(), asyncio.Event()
    push = MESPushService.push_event
    async def pause_after_actual_insert(*args, **kwargs):
        row = await push(*args, **kwargs)
        staged.set()
        await resume.wait()
        return row
    monkeypatch.setattr(MESPushService, 'push_event', pause_after_actual_insert)
    seen = await expectation(case)
    async def approve():
        async with case.session_factory() as db:
            return await advance_capa(db, await case.report(db), case.actor_id,
                AdvanceRequest(target_state='D8_CLOSURE', **seen))
    task = asyncio.create_task(approve())
    try:
        await asyncio.wait_for(staged.wait(), 5)
        await case.set_capa_level(3)
        resume.set()
        with pytest.raises(PermissionError):
            await asyncio.wait_for(task, 5)
        await no_closure_effects(case)
        await case.set_capa_level(4)
        assert await expectation(case) == seen
        monkeypatch.setattr(MESPushService, 'push_event', push)
        await approve()
        async with case.session_factory() as db:
            assert len((await db.scalars(select(AuditLog).where(AuditLog.record_id == case.report_id,
                AuditLog.action == 'D8_APPROVED'))).all()) == 1
            assert len((await db.scalars(select(KnowledgeEntry).where(KnowledgeEntry.source_id == case.report_id))).all()) == 1
            events = (await db.scalars(select(MESPushOutbox).where(MESPushOutbox.connection_id == connection_id))).all()
            assert len(events) == 1
            assert events[0].payload['new_status'] == 'D8_CLOSURE'
    finally:
        resume.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with case.session_factory() as db:
            await db.execute(delete(MESPushOutbox).where(MESPushOutbox.connection_id == connection_id))
            await db.execute(delete(MESConnection).where(MESConnection.connection_id == connection_id))
            await db.commit()


from tests.e2e.agent_local_trial_harness import owned_local_trial


@pytest.mark.asyncio
@pytest.mark.parametrize('target', ['D8_CLOSURE', 'D7_PREVENTION'])
async def test_real_employee_http_rr_decision_binding(owned_local_trial, decision_provider, target):
    """Real JWT, tenant middleware, scope dependencies and RR/RO GET; unit provider only."""
    from app.models.capa_doc_gate import CapaDocgAnalysis
    from app.services.capa_doc_gate_service import _build_allowlist, _compute_input_hash
    from tests.capa.test_capa_outcome_namespace import bootstrap
    owned = owned_local_trial
    async with owned.session() as db:
        report_id = await bootstrap(db, owned.admin_user_id)
        capa = await db.get(CAPAEightD, report_id)
        capa.d5_correction, capa.d6_verification, capa.d7_prevention = '已实施', '实施后验证结果', '预防'
        db.add(CapaRootCauseVerification(capa_id=report_id, factory_id=capa.factory_id,
            root_cause_text=capa.d4_root_cause, result='验证通过', method='observation',
            is_verified=True, conclusion='passed', evidence_attachments=[], verified_by=owned.admin_user_id))
        await db.flush()
        analysis = await db.scalar(select(CapaDocgAnalysis).where(CapaDocgAnalysis.capa_id == report_id))
        analysis.analysis_input_hash = _compute_input_hash(capa, await _build_allowlist(db, capa))
        await db.commit()
    path = f'/api/capa/{report_id}/advance'
    response = await owned.admin.post(path, json={'target_state': target, 'reject_reason': '需补验证'})
    assert response.status_code == 409, response.text
    assert response.json()['detail'] == 'CAPA_OUTCOME_REVIEW_REQUIRED'
    response = await owned.admin.get(f'/api/capa/{report_id}/outcome-review')
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    review = response.json()
    response = await owned.admin.post(path, json={'target_state': target, 'reject_reason': '需补验证',
        'expected_outcome_revision': review['revision'], 'expected_review_round_id': review['review_round_id']})
    assert response.status_code == 200, response.text
    assert response.json()['capa']['status'] == target
    async with owned.session() as db:
        audit = (await db.scalars(select(AuditLog).where(AuditLog.record_id == report_id,
            AuditLog.action == ('D8_APPROVED' if target == 'D8_CLOSURE' else 'D8_REJECTED')))).one()
        assert audit.changed_fields['outcome_review']['revision'] == review['revision']
        assert audit.changed_fields['outcome_review']['round_id'] == review['review_round_id']
    response = await owned.admin.get(f'/api/capa/{report_id}/outcome-review')
    if target == 'D8_CLOSURE':
        assert response.status_code == 200, response.text
        assert response.json()['binding_status'] == 'verified'
    else:
        assert response.status_code == 404
        assert response.json()['detail'] == 'CAPA_OUTCOME_REVIEW_UNAVAILABLE'


@pytest.mark.asyncio
async def test_e2e_pending_fixture_backfill_does_not_preproduce_receipt_or_commit(review_case, review_sources):
    from app.seed_e2e import _seed_pending_outcome_prerequisites
    from app.models.capa import CapaRootCauseVerification
    from app.services.capa_outcome_review import collect_outcome_material
    from app.services.capa_service import _d8_doc_gate_gate
    from sqlalchemy import delete
    # Use only this owned case; never invoke main() or touch fixed/shared seeds.
    async with review_case.session_factory() as db:
        capa = await review_case.report(db)
        capa.fmea_ref_id = review_sources.fmea_id
        await db.execute(delete(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id == capa.report_id))
        await db.commit()
        await _seed_pending_outcome_prerequisites(db, capa, review_case.actor_id)
        await _d8_doc_gate_gate(db, capa)
        material = await collect_outcome_material(db, capa)
        assert len(material['verifications']) == 1
        assert material['source_versions'][0]['object_id'] == str(review_sources.fmea_id)
        assert await db.scalar(select(AuditLog.log_id).where(AuditLog.record_id == capa.report_id,
            AuditLog.action.in_(['D8_APPROVED', 'D8_REJECTED']))) is None
        await db.rollback()
    async with review_case.session_factory() as db:
        assert await db.scalar(select(CapaRootCauseVerification.verification_id).where(
            CapaRootCauseVerification.capa_id == review_case.report_id)) is None


@pytest.mark.asyncio
async def test_fresh_token_does_not_replace_approval_c9_gate(review_http_client, review_case):
    async with review_case.session_factory() as db:
        await update_capa(db, await review_case.report(db), {'d5_correction': '新措施'}, review_case.actor_id)
    seen = await expectation(review_case)
    before = await review_case.snapshot()
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D8_CLOSURE', **seen})
    assert response.status_code == 400
    assert response.json()['detail'] == '分析输入已变更，请重新生成影响分析'
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
async def test_real_database_commit_failure_rolls_back_and_retry_emits_once(review_case, decision_provider):
    from sqlalchemy import event, text
    from sqlalchemy.exc import DBAPIError
    case = review_case
    seen = await expectation(case)
    attempted = []
    async with case.session_factory() as db:
        def fail_database_at_commit(session):
            if session.in_nested_transaction():
                return
            connection = session.connection()
            # The actual decision and knowledge rows exist in this transaction,
            # but must not survive a real database error at the commit boundary.
            assert connection.scalar(text("SELECT count(*) FROM audit_logs WHERE record_id=:id AND action='D8_APPROVED'"),
                {'id': case.report_id}) == 1
            attempted.append(True)
            connection.execute(text('SELECT 1/0'))
        event.listen(db.sync_session, 'before_commit', fail_database_at_commit)
        try:
            with pytest.raises(DBAPIError):
                await advance_capa(db, await case.report(db), case.actor_id,
                    AdvanceRequest(target_state='D8_CLOSURE', **seen))
        finally:
            event.remove(db.sync_session, 'before_commit', fail_database_at_commit)
        assert attempted == [True]
        from tests.capa.test_capa_review_concurrency import no_closure_effects
        await no_closure_effects(case)
        await advance_capa(db, await case.report(db), case.actor_id,
            AdvanceRequest(target_state='D8_CLOSURE', **seen))
    async with case.session_factory() as db:
        assert len((await db.scalars(select(AuditLog).where(AuditLog.record_id == case.report_id,
            AuditLog.action == 'D8_APPROVED'))).all()) == 1


@pytest.mark.asyncio
async def test_three_argument_early_edit_progression_stays_compatible(review_case):
    await review_case.set_status('D5_CORRECTION')
    await review_case.set_capa_level(3)
    async with review_case.session_factory() as db:
        capa = await advance_capa(db, await review_case.report(db), review_case.actor_id)
        assert capa.status == 'D6_VERIFICATION'


@pytest.mark.asyncio
async def test_none_request_cannot_approve_pending_by_direct_service(review_case):
    before = await review_case.snapshot()
    async with review_case.session_factory() as db:
        with pytest.raises(ValueError, match='需显式传 target_state'):
            await advance_capa(db, await review_case.report(db), review_case.actor_id)
    assert await review_case.snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('expected_outcome_revision', 'A' * 64),
    ('expected_outcome_revision', 'a' * 63), ('expected_review_round_id', 'invalid-uuid')])
async def test_decision_dto_rejects_malformed_expectation(review_http_client, review_case, field, value):
    seen = await expectation(review_case)
    seen[field] = value
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D8_CLOSURE', **seen})
    assert response.status_code == 422
    assert (await review_case.snapshot())['capa']['status'] == 'D8_APPROVAL_PENDING'


@pytest.mark.asyncio
async def test_client_receipt_is_not_a_version_expectation(review_http_client, review_case):
    seen = await expectation(review_case)
    response = await review_http_client.post(f'/api/capa/{review_case.report_id}/advance',
        json={'target_state': 'D8_CLOSURE', 'outcome_review': {'contract': 'capa.outcome-review.v1',
            'round_id': seen['expected_review_round_id'], 'revision': seen['expected_outcome_revision'],
            'doc_decision_id': str(review_case.owned_ids['analysis_id']), 'source_versions': []}})
    assert response.status_code == 409
    assert response.json()['detail'] == 'CAPA_OUTCOME_REVIEW_REQUIRED'
