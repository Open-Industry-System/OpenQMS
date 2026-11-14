"""Employee D5 actions are independent of run authority and preserve source ACL."""
import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, update
from app.models.agent_task import AgentTask
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.capa_d5_proposal import CapaD5Measure, CapaD5Proposal, CapaD5StaffReceipt, CapaD5Withdrawal
from app.models.role import RolePermission, UserProductLine
from tests.capa.test_d5_measure_visibility import d5_case, committed_runtime

pytestmark = pytest.mark.requires_db

@pytest_asyncio.fixture
async def staff_case(d5_case):
    c = d5_case
    await c.db.execute(delete(CapaD5Measure))
    await c.db.execute(update(CapaD5Proposal).values(state='pending'))
    await c.db.execute(update(RolePermission).where(RolePermission.module == 'capa').values(permission_level=3))
    await c.db.execute(update(AgentTask).where(AgentTask.task_id == c.task_id).values(status='completed'))
    await c.db.commit()
    c.scope = c.actors[2]
    return c

async def act(c, proposal=None, *, operation='adopt', key='staff-one', value='employee final', scope=None):
    from app.services.capa_d5_proposals import staff_action
    async with c.factory(binding=c.binding) as db:
        try:
            return await staff_action(db, scope or c.scope, c.report.report_id, proposal or c.proposals[0],
                operation=operation, operation_key=key, value=value)
        except Exception:
            await db.rollback()
            raise

@pytest.mark.asyncio
async def test_colleague_adopts_after_task_finished_and_replays_exactly(staff_case):
    c = staff_case
    first = await act(c)
    assert first == await act(c)
    assert first['state'] == 'adopted'
    async with c.factory(binding=c.binding) as db:
        measure = await db.get(CapaD5Measure, first['measure_id'])
        assert measure.final_text == 'employee final'
        assert measure.adopted_by == c.scope.user.user_id
        assert (await db.get(CapaD5Proposal, c.proposals[0])).original_text == 'secret original 1'
        assert await db.scalar(select(func.count()).select_from(CapaD5StaffReceipt)) == 1
        audit = await db.scalar(select(AuditLog).where(AuditLog.action == 'D5_PROPOSAL_ADOPT'))
        assert 'employee final' not in str(audit.changed_fields)
    with pytest.raises(ValueError, match='conflict'):
        await act(c, value='changed')

@pytest.mark.asyncio
async def test_withdraw_reason_is_controlled_and_adopted_cannot_be_changed(staff_case):
    c = staff_case
    result = await act(c, operation='withdraw', value='business reason')
    assert result == await act(c, operation='withdraw', value='business reason')
    async with c.factory(binding=c.binding) as db:
        withdrawal = await db.scalar(select(CapaD5Withdrawal))
        assert withdrawal.reason == 'business reason'
    with pytest.raises(ValueError):
        await act(c, key='other')
    await act(c, c.proposals[1], key='second')
    with pytest.raises(ValueError):
        await act(c, c.proposals[1], key='third', operation='withdraw', value='reason')

@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['adopt', 'withdraw'])
async def test_complete_employee_source_permissions_required(staff_case, operation):
    c = staff_case
    with pytest.raises(LookupError):
        await act(c, c.proposals[1], scope=c.actors[1], operation=operation)
    async with c.factory(binding=c.binding) as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5StaffReceipt)) == 0

@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['proof', 'root-aba', 'node', 'stage', 'superseded', 'edit'])
async def test_adopt_requires_current_basis_stage_pending_and_edit(staff_case, change):
    c = staff_case
    if change == 'proof': c.proof.status = 'superseded'
    elif change == 'root-aba':
        from app.services.capa_d4_provenance import record_root_revision
        c.report.d4_root_cause = 'B'
        await record_root_revision(c.db, report_id=c.report.report_id, actor_id=c.user_id, write_path='fixture')
        c.report.d4_root_cause = 'root'
        await record_root_revision(c.db, report_id=c.report.report_id, actor_id=c.user_id, write_path='fixture')
    elif change == 'node': c.docs[0].graph_data = {'nodes': []}
    elif change == 'stage': c.report.status = 'D4_ROOT_CAUSE'
    elif change == 'superseded':
        await c.db.execute(update(CapaD5Proposal).values(state='superseded'))
    else:
        await c.db.execute(update(RolePermission).where(RolePermission.role_id == c.scope.role_id,
            RolePermission.module == 'capa').values(permission_level=1))
    await c.db.commit()
    with pytest.raises((PermissionError, ValueError, LookupError)):
        await act(c)

@pytest.mark.asyncio
async def test_adopt_withdraw_race_has_one_effect(staff_case):
    c = staff_case
    result = await asyncio.gather(act(c), act(c, operation='withdraw', key='withdraw', value='reason'), return_exceptions=True)
    assert sum(isinstance(x, dict) for x in result) == 1
    assert sum(isinstance(x, ValueError) for x in result) == 1
    async with c.factory(binding=c.binding) as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5StaffReceipt)) == 1

@pytest.mark.asyncio
async def test_replay_still_requires_current_source_permission(staff_case):
    c = staff_case
    await act(c, c.proposals[1])
    await c.db.execute(delete(UserProductLine).where(UserProductLine.user_id == c.scope.user.user_id,
        UserProductLine.product_line_code == c.line_b.code))
    await c.db.commit()
    with pytest.raises(LookupError): await act(c, c.proposals[1])

@pytest.mark.asyncio
async def test_http_staff_contract_conflicts_and_invisible_uniform(staff_case):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.api.capa import router
    from app.core.deps import get_request_scope
    from app.database import get_db
    c = staff_case
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_request_scope] = lambda: c.scope
    app.dependency_overrides[get_db] = lambda: c.db
    report_id = c.report.report_id
    path = f'/api/capa/{report_id}/d5-proposals/{c.proposals[0]}/adopt'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        result = await client.post(path, json={'operation_key':'http', 'final_text':'confirmed'})
        assert result.status_code == 200, result.text
        assert result.headers['cache-control'] == 'no-store'
        conflict = await client.post(path, json={'operation_key':'http', 'final_text':'different'})
        assert conflict.status_code == 409
        for extra in ({'report_id':str(report_id)}, {'sources':[]}, {'reason':'no'}):
            invalid = await client.post(path, json={'operation_key':'new', 'final_text':'confirmed', **extra})
            assert invalid.status_code == 422
        app.dependency_overrides[get_request_scope] = lambda: c.actors[0]
        hidden = await client.post(path, json={'operation_key':'hidden', 'final_text':'confirmed'})
        missing = await client.post(path.replace(str(c.proposals[0]),str(uuid4())),
            json={'operation_key':'hidden', 'final_text':'confirmed'})
        assert hidden.status_code == missing.status_code == 404
        assert hidden.content == missing.content

@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['adopt', 'withdraw'])
async def test_terminal_protection_is_shared_and_atomic(staff_case, operation):
    from app.services.capa_review_guard import ReviewedContentLocked
    c = staff_case
    c.report.status = 'D8_CLOSURE'
    await c.db.commit()
    with pytest.raises(ReviewedContentLocked): await act(c, operation=operation)
    async with c.factory(binding=c.binding) as db:
        assert await db.scalar(select(func.count()).select_from(CapaD5StaffReceipt)) == 0

@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['source', 'proof', 'stage'])
async def test_adopt_checks_after_real_report_lock_wait(staff_case, change):
    c = staff_case
    async with c.factory(binding=c.binding) as blocker:
        await blocker.scalar(select(CAPAEightD.report_id).where(CAPAEightD.report_id == c.report.report_id).with_for_update())
        started = asyncio.Event()
        async def contender():
            from app.services.capa_d5_proposals import staff_action
            async with c.factory(binding=c.binding) as db:
                execute = db.scalar
                async def observed(statement, *args, **kwargs):
                    if 'FOR UPDATE' in str(statement) and 'capa_eightd' in str(statement): started.set()
                    return await execute(statement, *args, **kwargs)
                db.scalar = observed
                try:
                    return await staff_action(db, c.scope, c.report.report_id, c.proposals[1],
                        operation='adopt', operation_key='waiting', value='final')
                except Exception:
                    await db.rollback()
                    raise
        pending = asyncio.create_task(contender())
        await asyncio.wait_for(started.wait(), 5)
        if change == 'source':
            await blocker.execute(delete(UserProductLine).where(UserProductLine.user_id == c.scope.user.user_id,
                UserProductLine.product_line_code == c.line_b.code))
        elif change == 'proof':
            from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
            await blocker.execute(update(CapaD4RootCauseSourceProof).where(CapaD4RootCauseSourceProof.proof_id == c.proof.proof_id).values(status='superseded'))
        else:
            await blocker.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report.report_id).values(status='D4_ROOT_CAUSE'))
        await blocker.commit()
        with pytest.raises(LookupError if change == 'source' else ValueError):
            await asyncio.wait_for(pending, 10)

@pytest.mark.asyncio
async def test_audit_failure_rolls_back_all_staff_effects(staff_case, monkeypatch):
    from app.services.capa_d5_proposals import staff_action
    c = staff_case
    async with c.factory(binding=c.binding) as db:
        async def failing_commit():
            await db.flush()
            raise RuntimeError('synthetic before commit')
        monkeypatch.setattr(db, 'commit', failing_commit)
        with pytest.raises(RuntimeError):
            await staff_action(db, c.scope, c.report.report_id, c.proposals[0], operation='adopt',
                operation_key='rollback', value='final')
        await db.rollback()
    assert (await act(c, key='rollback', value='final'))['state'] == 'adopted'

@pytest.mark.asyncio
async def test_actor_scoped_keys_and_final_text_keep_full_source_restrictions(staff_case):
    from app.services.capa_d5_measures import read_d5_measures
    c = staff_case
    await act(c, c.proposals[0], scope=c.actors[1], key='same')
    await act(c, c.proposals[1], key='same')
    assert (await read_d5_measures(c.db, c.actors[1], c.report.report_id)).total == 1
    assert (await read_d5_measures(c.db, c.scope, c.report.report_id)).total == 2

@pytest.mark.asyncio
async def test_unauthorized_staff_never_reads_any_body(staff_case):
    from app.services.capa_d5_proposals import staff_action
    from tests.capa.test_d4_source_access import SQLSpy
    c = staff_case
    with SQLSpy(await c.db.connection()) as spy:
        with pytest.raises(LookupError):
            await staff_action(c.db, c.actors[1], c.report.report_id, c.proposals[1],
                operation='adopt', operation_key='denied', value='final')
    assert not any('original_text' in statement or 'final_text' in statement or 'capa_eightd.d4_root_cause' in statement or 'graph_data' in statement for statement in spy.statements)
