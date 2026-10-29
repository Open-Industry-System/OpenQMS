"""Real PostgreSQL decision/write races; no simulated commits or authorization."""
import asyncio
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import event, select, text, update

from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.role import RolePermission
from app.schemas.capa import AdvanceRequest
from app.services.capa_service import advance_capa, update_capa
from app.services.capa_review_guard import OutcomeReviewConflict, ReviewedContentLocked, lock_capa_parent
from tests.capa.outcome_review_support import wait_for_pg_blocker
from tests.capa.test_capa_outcome_decision import decision_provider, expectation

pytestmark = pytest.mark.requires_db


@asynccontextmanager
async def lock_witness(case, waiter_pid, table='capa_eightd'):
    """Observe execute reaching the real lock request, then PostgreSQL blocking."""
    reached = asyncio.Event()
    engine = case.session_factory.kw['bind']
    def record(conn, cursor, statement, parameters, context, executemany):
        if (f'FROM {table}' in statement and 'FOR UPDATE' in statement
                and conn.info.get('task4_pid') == waiter_pid):
            reached.set()
    event.listen(engine.sync_engine, 'before_cursor_execute', record)
    try:
        yield reached
    finally:
        event.remove(engine.sync_engine, 'before_cursor_execute', record)


async def pid(db):
    value = await db.scalar(text('SELECT pg_backend_pid()'))
    (await db.connection()).sync_connection.info['task4_pid'] = value
    return value


async def no_closure_effects(case):
    from app.models.knowledge_entry import KnowledgeEntry
    from app.models.capa_lateral_diffusion import CapaLateralDiffusionCheck
    from app.models.mes import MESPushOutbox
    async with case.session_factory() as db:
        assert (await case.report(db)).status == 'D8_APPROVAL_PENDING'
        assert await db.scalar(select(AuditLog.log_id).where(AuditLog.record_id == case.report_id,
            AuditLog.action.in_(['D8_APPROVED', 'D8_REJECTED', 'KNOWLEDGE_SUNK', 'LATERAL_DIFFUSION_CHECKED']))) is None
        assert await db.scalar(select(KnowledgeEntry.entry_id).where(KnowledgeEntry.source_id == case.report_id)) is None
        assert await db.scalar(select(CapaLateralDiffusionCheck.check_id).where(
            CapaLateralDiffusionCheck.capa_id == case.report_id)) is None
        assert await db.scalar(select(MESPushOutbox.outbox_id).where(
            MESPushOutbox.payload['capa_id'].astext == str(case.report_id))) is None


@pytest.mark.asyncio
async def test_no_closure_effects_detects_rejection_audit(review_case):
    """A failed decision must not leave a successful rejection audit either."""
    async with review_case.session_factory() as db:
        db.add(AuditLog(table_name='capa_eightd', record_id=review_case.report_id,
            action='D8_REJECTED', operated_by=review_case.actor_id,
            factory_id=review_case.factory_id))
        await db.commit()
    with pytest.raises(AssertionError):
        await no_closure_effects(review_case)


@pytest.mark.asyncio
async def test_cached_material_writer_waits_for_actual_approval_then_locked(review_case, decision_provider):
    case = review_case
    seen = await expectation(case)
    async with case.session_factory() as writer, case.session_factory() as approver:
        cached = await case.report(writer)
        writer_pid, approver_pid = await pid(writer), await pid(approver)
        await lock_capa_parent(approver, case.report_id)
        async with lock_witness(case, writer_pid) as reached:
            task = asyncio.create_task(update_capa(writer, cached, {'d6_verification': '不能覆盖'}, case.actor_id))
            try:
                await asyncio.wait_for(reached.wait(), 5)
                await wait_for_pg_blocker(case, writer_pid, approver_pid)
                await advance_capa(approver, await case.report(approver), case.actor_id,
                    AdvanceRequest(target_state='D8_CLOSURE', **seen))
                with pytest.raises(ReviewedContentLocked):
                    await asyncio.wait_for(task, 5)
                await writer.rollback()
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
    async with case.session_factory() as db:
        capa = await case.report(db)
        assert capa.status == 'D8_CLOSURE'
        assert capa.d6_verification == '实施后复测合格'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['d6', 'verification'])
async def test_material_commits_first_old_token_approval_waits_and_conflicts(review_case, kind):
    from app.models.user import User
    from app.schemas.capa_verification import VerificationUpdate
    from app.services.capa_verification_service import update_verification
    case = review_case
    seen = await expectation(case)
    async with case.session_factory() as writer, case.session_factory() as approver:
        writer_pid, approver_pid = await pid(writer), await pid(approver)
        capa_w = await lock_capa_parent(writer, case.report_id)
        capa_a = await case.report(approver)
        async with lock_witness(case, approver_pid) as reached:
            task = asyncio.create_task(advance_capa(approver, capa_a, case.actor_id,
                AdvanceRequest(target_state='D8_CLOSURE', **seen)))
            try:
                await asyncio.wait_for(reached.wait(), 5)
                await wait_for_pg_blocker(case, approver_pid, writer_pid)
                if kind == 'd6':
                    await update_capa(writer, capa_w, {'d6_verification': '实际变更已提交'}, case.actor_id)
                else:
                    await update_verification(writer, capa_w, case.verification_id,
                        VerificationUpdate(result='实际验证变更已提交'), await writer.get(User, case.actor_id))
                with pytest.raises(OutcomeReviewConflict):
                    await asyncio.wait_for(task, 5)
                await approver.rollback()
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
    await no_closure_effects(case)


@pytest.mark.asyncio
@pytest.mark.parametrize('first_target,second_target', [('D8_CLOSURE', 'D7_PREVENTION'), ('D7_PREVENTION', 'D8_CLOSURE')])
async def test_approve_reject_race_emits_only_first_actual_decision(review_case, decision_provider, first_target, second_target):
    case = review_case
    seen = await expectation(case)
    async with case.session_factory() as first, case.session_factory() as second:
        first_pid, second_pid = await pid(first), await pid(second)
        await lock_capa_parent(first, case.report_id)
        cached = await case.report(second)
        async with lock_witness(case, second_pid) as reached:
            task = asyncio.create_task(advance_capa(second, cached, case.actor_id,
                AdvanceRequest(target_state=second_target, reject_reason='需要返工', **seen)))
            try:
                await asyncio.wait_for(reached.wait(), 5)
                await wait_for_pg_blocker(case, second_pid, first_pid)
                await advance_capa(first, await case.report(first), case.actor_id,
                    AdvanceRequest(target_state=first_target, reject_reason='需要返工', **seen))
                with pytest.raises(ValueError, match='Cannot transition'):
                    await asyncio.wait_for(task, 5)
                await second.rollback()
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
    async with case.session_factory() as db:
        audits = (await db.scalars(select(AuditLog).where(AuditLog.record_id == case.report_id,
            AuditLog.action.in_(['D8_APPROVED', 'D8_REJECTED'])))).all()
        assert len(audits) == 1
        assert audits[0].action == ('D8_APPROVED' if first_target == 'D8_CLOSURE' else 'D8_REJECTED')


@pytest.mark.asyncio
async def test_role_revoked_during_real_parent_lock_wait(review_case):
    case = review_case
    seen = await expectation(case)
    async with case.session_factory() as holder, case.session_factory() as approver:
        holder_pid, approver_pid = await pid(holder), await pid(approver)
        await lock_capa_parent(holder, case.report_id)
        async with lock_witness(case, approver_pid) as reached:
            task = asyncio.create_task(advance_capa(approver, await case.report(approver), case.actor_id,
                AdvanceRequest(target_state='D8_CLOSURE', **seen)))
            try:
                await asyncio.wait_for(reached.wait(), 5)
                await wait_for_pg_blocker(case, approver_pid, holder_pid)
                await case.set_capa_level(3)
                await holder.commit()
                with pytest.raises(PermissionError):
                    await asyncio.wait_for(task, 5)
                await approver.rollback()
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
    await no_closure_effects(case)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['source_version', 'planning_permission', 'scope'])
@pytest.mark.parametrize('target', ['D8_CLOSURE', 'D7_PREVENTION'])
async def test_complete_source_wait_revalidates_version_and_current_access(review_case, review_sources, change, target):
    from app.models.fmea import FMEADocument
    from app.models.role import UserProductLine
    from app.services.version_service import create_fmea_version, lock_version_parent
    from tests.capa.test_capa_outcome_decision import bind_decision_sources
    case = review_case
    await bind_decision_sources(case, review_sources)
    seen = await expectation(case)
    # CP (gate) sorts before explicit FMEA (outside the gate snapshot). Hold
    # only FMEA so the approver has already waited after locking a proper subset.
    async with case.session_factory() as holder, case.session_factory() as approver:
        holder_pid, approver_pid = await pid(holder), await pid(approver)
        await lock_version_parent(holder, 'fmea', review_sources.fmea_id)
        async with lock_witness(case, approver_pid, 'fmea_documents') as reached:
            task = asyncio.create_task(advance_capa(approver, await case.report(approver), case.actor_id,
                AdvanceRequest(target_state=target, reject_reason='需补足实施证据', **seen)))
            try:
                await asyncio.wait_for(reached.wait(), 5)
                await wait_for_pg_blocker(case, approver_pid, holder_pid)
                if change == 'source_version':
                    await create_fmea_version(holder, await holder.get(FMEADocument, review_sources.fmea_id),
                        'edit', 'committed while approval waited for source', case.actor_id)
                else:
                    async with case.session_factory() as revoke:
                        if change == 'planning_permission':
                            await revoke.execute(update(RolePermission).where(
                                RolePermission.role_id == case.owned_ids['role_id'],
                                RolePermission.module == 'planning').values(permission_level=0))
                        else:
                            from sqlalchemy import delete
                            await revoke.execute(delete(UserProductLine).where(UserProductLine.user_id == case.actor_id))
                        await revoke.commit()
                    await holder.commit()
                error = OutcomeReviewConflict if change == 'source_version' else (PermissionError, LookupError)
                with pytest.raises(error):
                    await asyncio.wait_for(task, 5)
                await approver.rollback()
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
    await no_closure_effects(case)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['capa', 'planning', 'actor', 'scope'])
async def test_provider_wait_final_authority_failure_rolls_back_every_side_effect(
    review_case, review_sources, decision_provider, monkeypatch, change,
):
    from app.models.user import User
    from app.models.role import UserProductLine
    from app.services.agent import provider_adapter
    from tests.capa.test_capa_outcome_decision import bind_decision_sources
    case = review_case
    await bind_decision_sources(case, review_sources)
    seen = await expectation(case)
    called, resume = asyncio.Event(), asyncio.Event()
    complete = provider_adapter.complete_json
    async def paused(pc, prompt, schema):
        result = await complete(pc, prompt, schema)
        called.set()
        await resume.wait()
        return result
    monkeypatch.setattr(provider_adapter, 'complete_json', paused)
    async def approve():
        async with case.session_factory() as db:
            await advance_capa(db, await case.report(db), case.actor_id,
                AdvanceRequest(target_state='D8_CLOSURE', **seen))
    task = asyncio.create_task(approve())
    try:
        await asyncio.wait_for(called.wait(), 5)
        async with case.session_factory() as revoke:
            if change == 'actor':
                await revoke.execute(update(User).where(User.user_id == case.actor_id).values(is_active=False))
            elif change == 'scope':
                from sqlalchemy import delete
                await revoke.execute(delete(UserProductLine).where(UserProductLine.user_id == case.actor_id))
            else:
                await revoke.execute(update(RolePermission).where(RolePermission.role_id == case.owned_ids['role_id'],
                    RolePermission.module == change).values(permission_level=3 if change == 'capa' else 0))
            await revoke.commit()
        resume.set()
        with pytest.raises((PermissionError, LookupError)):
            await asyncio.wait_for(task, 5)
    finally:
        resume.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    await no_closure_effects(case)


@pytest.mark.asyncio
async def test_complete_ordered_source_locks_held_through_provider_and_commit(
    review_case, review_sources, decision_provider, monkeypatch,
):
    from app.models.fmea import FMEADocument
    from app.services.agent import provider_adapter
    from app.services.version_service import create_fmea_version
    from tests.capa.test_capa_outcome_decision import bind_decision_sources
    case = review_case
    await bind_decision_sources(case, review_sources)
    seen = await expectation(case)
    called, resume = asyncio.Event(), asyncio.Event()
    complete = provider_adapter.complete_json
    pids, locks = {}, []
    async def paused(pc, prompt, schema):
        value = await complete(pc, prompt, schema)
        called.set()
        await resume.wait()
        return value
    monkeypatch.setattr(provider_adapter, 'complete_json', paused)
    engine = case.session_factory.kw['bind']
    def record(conn, cursor, statement, parameters, context, executemany):
        if conn.info.get('task4_pid') == pids.get('approver') and 'FOR UPDATE' in statement:
            if 'FROM control_plans' in statement or 'FROM fmea_documents' in statement:
                locks.append(statement)
    event.listen(engine.sync_engine, 'before_cursor_execute', record)
    async def approve():
        async with case.session_factory() as db:
            pids['approver'] = await pid(db)
            await advance_capa(db, await case.report(db), case.actor_id,
                AdvanceRequest(target_state='D8_CLOSURE', **seen))
    task = asyncio.create_task(approve())
    writer_task = None
    try:
        await asyncio.wait_for(called.wait(), 5)
        assert len(locks) == 2
        assert 'FROM control_plans' in locks[0]
        assert 'FROM fmea_documents' in locks[1]
        async with case.session_factory() as writer:
            writer_pid = await pid(writer)
            async with lock_witness(case, writer_pid, 'fmea_documents') as reached:
                writer_task = asyncio.create_task(create_fmea_version(writer,
                    await writer.get(FMEADocument, review_sources.fmea_id), 'edit', 'after decision commit', case.actor_id))
                await asyncio.wait_for(reached.wait(), 5)
                await wait_for_pg_blocker(case, writer_pid, pids['approver'])
                resume.set()
                await asyncio.wait_for(task, 5)
                await asyncio.wait_for(writer_task, 5)
    finally:
        resume.set()
        for item in [task, writer_task]:
            if item is not None and not item.done():
                item.cancel()
                await asyncio.gather(item, return_exceptions=True)
        event.remove(engine.sync_engine, 'before_cursor_execute', record)
    from tests.capa.test_capa_outcome_review import read
    result = await read(case)
    assert result.binding_status == 'verified'
    assert result.revision == seen['expected_outcome_revision']


from tests.services.agent_runtime.conftest import committed_runtime


@pytest.mark.asyncio
@pytest.mark.parametrize('revocation', ['status', 'generation'])
async def test_tenant_admission_revalidated_after_actual_provider_wait(
    committed_runtime, decision_provider, monkeypatch, revocation,
):
    from app.core.tenant_transaction import TenantUnavailable
    from app.models.capa import CapaRootCauseVerification
    from app.models.capa_doc_gate import CapaDocgAnalysis
    from app.models.knowledge_entry import KnowledgeEntry
    from app.services.agent import provider_adapter
    from app.services.capa_doc_gate_service import _compute_input_hash, _build_allowlist
    from app.services.capa_outcome_review import read_outcome_review
    from tests.capa.test_capa_outcome_namespace import bootstrap, scope
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as db:
        report_id = await bootstrap(db, owned.user_id)
        capa = await db.get(CAPAEightD, report_id)
        capa.d5_correction, capa.d6_verification, capa.d7_prevention = 'implemented', 'verified result', 'prevention'
        db.add(CapaRootCauseVerification(capa_id=report_id, factory_id=capa.factory_id,
            root_cause_text=capa.d4_root_cause, method='observation', result='passed',
            conclusion='passed', is_verified=True, evidence_attachments=[], verified_by=owned.user_id))
        await db.flush()
        analysis = await db.scalar(select(CapaDocgAnalysis).where(CapaDocgAnalysis.capa_id == report_id))
        analysis.analysis_input_hash = _compute_input_hash(capa, await _build_allowlist(db, capa))
        await db.commit()
    async with owned.factory(binding=owned.binding) as db:
        review = await read_outcome_review(db, scope(owned.user_id), report_id)
    seen = dict(expected_outcome_revision=review.revision, expected_review_round_id=review.review_round_id)
    called, resume = asyncio.Event(), asyncio.Event()
    complete = provider_adapter.complete_json
    async def paused(pc, prompt, schema):
        result = await complete(pc, prompt, schema)
        called.set()
        await resume.wait()
        return result
    monkeypatch.setattr(provider_adapter, 'complete_json', paused)
    async def approve():
        async with owned.factory(binding=owned.binding) as db:
            await advance_capa(db, await db.get(CAPAEightD, report_id), owned.user_id,
                AdvanceRequest(target_state='D8_CLOSURE', **seen))
    task = asyncio.create_task(approve())
    try:
        await asyncio.wait_for(called.wait(), 5)
        async with owned.engine.begin() as conn:
            clause = "status='suspended'" if revocation == 'status' else 'generation=generation+1'
            await conn.execute(text('UPDATE public.tenants SET ' + clause + ' WHERE id=:id'),
                {'id': owned.binding.tenant_id})
        resume.set()
        with pytest.raises((TenantUnavailable, PermissionError)):
            await asyncio.wait_for(task, 5)
    finally:
        resume.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with owned.engine.begin() as conn:
            await conn.execute(text("UPDATE public.tenants SET status='active',generation=:generation WHERE id=:id"),
                {'id': owned.binding.tenant_id, 'generation': owned.binding.generation})
    async with owned.factory(binding=owned.binding) as db:
        assert (await db.get(CAPAEightD, report_id)).status == 'D8_APPROVAL_PENDING'
        assert await db.scalar(select(AuditLog.log_id).where(AuditLog.record_id == report_id,
            AuditLog.action.in_(['D8_APPROVED', 'KNOWLEDGE_SUNK', 'LATERAL_DIFFUSION_CHECKED']))) is None
        assert await db.scalar(select(KnowledgeEntry.entry_id).where(KnowledgeEntry.source_id == report_id)) is None
