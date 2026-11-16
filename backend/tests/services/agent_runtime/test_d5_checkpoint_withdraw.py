"""Task ordered R5 checkpoints and employee partial withdrawal with real DB."""
from types import SimpleNamespace
from uuid import UUID, uuid4
import pytest
from sqlalchemy import delete, func, select, update
from app.models.agent_d5_command import AgentD5CheckpointPosition, AgentD5Command
from app.models.agent_task import AgentTask, AgentRun
from app.models.capa import CAPAEightD
from app.models.capa_d5_proposal import CapaD5Proposal, CapaD5Measure, CapaD5StaffReceipt
from app.models.role import RolePermission
from tests.services.agent_runtime.test_d5_commands import command_case, d4_text_local_trial, owned_local_trial

pytestmark = [pytest.mark.requires_db, pytest.mark.asyncio]

async def checkpoint(c):
    from app.services.agent_runtime.checkpoint_service import save_d5_checkpoint
    async with c.session() as db:
        try:
            return await save_d5_checkpoint(db, await c.identity(db))
        except Exception:
            await db.rollback()
            raise

async def test_checkpoint_captures_task_sequence_not_run_and_is_idempotent(command_case):
    c = command_case
    before = await c.save()
    cp = await checkpoint(c)
    assert cp == await checkpoint(c)
    assert cp['command_watermark'] == 1
    after = await c.save('after')
    from app.services.agent_runtime.task_controls import d5_checkpoint_candidates
    async with c.session() as db:
        scope = SimpleNamespace(user=SimpleNamespace(user_id=c.user_id))
        rows = await d5_checkpoint_candidates(db, scope, c.task_id, UUID(cp['checkpoint_id']))
        assert [str(row['proposal_id']) for row in rows] == [str(after['proposal_id'])]
        assert str(before['proposal_id']) not in str(rows)
        position = await db.get(AgentD5CheckpointPosition, UUID(cp['checkpoint_id']))
        assert position.watermark == 1

async def test_partial_withdraw_commits_each_item_and_retries_outcomes(command_case):
    from app.services.agent_runtime.task_controls import withdraw_d5_after_checkpoint
    c = command_case
    cp = await checkpoint(c)
    items = [await c.save(str(i)) for i in range(3)]
    scope = SimpleNamespace(user=SimpleNamespace(user_id=c.user_id))
    async with c.session() as db:
        from app.services.capa_d5_proposals import staff_action
        from app.services.capa_service import advance_capa
        report = await db.get(CAPAEightD, c.report_id)
        await advance_capa(db, report, c.user_id)
        await staff_action(db, scope, c.report_id, items[1]['proposal_id'],
            operation='adopt', operation_key='colleague', value='confirmed')
        # A third persisted proposal carries an additional original source.
        # Employee handling uses current employee ACL, not old task source grants.
        from app.models.capa_d5_proposal import CapaD5ProposalSource
        from app.models.product_line import ProductLine
        from app.models.fmea import FMEADocument
        from app.models.role import UserProductLine
        from app.services.fmea_agent_sources import visible_fmea_source, failure_cause_version
        from app.services.capa_d5_measures import _visible_metadata
        line = ProductLine(code='extra-'+uuid4().hex[:10], name='extra', factory_id=c.factory_id)
        db.add(line)
        await db.flush()
        doc = FMEADocument(document_no=uuid4().hex, title='extra source', factory_id=c.factory_id,
            product_line_code=line.code, graph_data={'nodes':[{'id':'cause', 'type':'FailureCause'}]})
        db.add(doc)
        db.add(UserProductLine(user_id=c.user_id, product_line_code=line.code))
        await db.commit()
        version = await failure_cause_version(db, await visible_fmea_source(db, scope, doc.fmea_id), 'cause')
        db.add(CapaD5ProposalSource(proposal_id=items[2]['proposal_id'], projection_id='fmea.failure_cause.reference.v1',
            factory_id=c.factory_id, product_line_code=line.code, fmea_id=doc.fmea_id, node_id='cause', node_hmac=version))
        await db.commit()
        assert len((await _visible_metadata(db, scope, c.report_id))[1]) == 3
        # A separate committed session revokes only this secondary source line.
        async with c.session() as writer:
            await writer.execute(delete(UserProductLine).where(UserProductLine.user_id == c.user_id,
                UserProductLine.product_line_code == line.code))
            await writer.commit()
        args = dict(proposal_ids=[item['proposal_id'] for item in items], operation_key='batch', reason='retract')
        result = await withdraw_d5_after_checkpoint(db, scope, c.task_id, UUID(cp['checkpoint_id']), **args)
        assert [row['outcome'] for row in result] == ['withdrawn', 'adopted', 'unavailable']
        assert result == await withdraw_d5_after_checkpoint(db, scope, c.task_id, UUID(cp['checkpoint_id']), **args)
        assert await db.scalar(select(func.count()).select_from(CapaD5StaffReceipt)) == 2

async def test_old_checkpoint_and_other_task_never_authorize_withdraw(command_case):
    from app.services.agent_runtime.task_controls import withdraw_d5_after_checkpoint
    c = command_case
    earlier = await c.save('earlier')
    cp = await checkpoint(c)
    later = await c.save('later')
    scope = SimpleNamespace(user=SimpleNamespace(user_id=c.user_id))
    async with c.session() as db:
        rows = await withdraw_d5_after_checkpoint(db, scope, c.task_id, UUID(cp['checkpoint_id']),
            proposal_ids=[earlier['proposal_id'], later['proposal_id']], operation_key='batch', reason='reason')
        assert [r['outcome'] for r in rows] == ['unavailable','withdrawn']
        rows = await withdraw_d5_after_checkpoint(db, scope, uuid4(), UUID(cp['checkpoint_id']),
            proposal_ids=[later['proposal_id']], operation_key='wrong', reason='reason')
        assert rows[0]['outcome'] == 'unavailable'

async def test_closed_r4b_checkpoint_branch_never_captures_d5_position(command_case, monkeypatch):
    from app.services.agent_runtime import d5_commands
    from app.services.agent_runtime.checkpoint_service import save_d5_checkpoint
    c = command_case
    async with c.session() as db:
        with pytest.raises(PermissionError):
            c.production_admission(await c.identity(db))
        # Restore production gate to exercise the actual HTTP branch as R4b.
        monkeypatch.setattr(d5_commands, 'require_r5_admission', c.production_admission)
        response = await c.client.post('/api/agent/runtime/capa/d5/checkpoints',
            headers={'Authorization':'Bearer ' + c.token}, json={})
        assert response.status_code == 403, response.text
        assert await db.scalar(select(func.count()).select_from(AgentD5CheckpointPosition)) == 0

async def test_batch_changed_reason_conflicts_without_new_effect(command_case):
    from app.services.agent_runtime.task_controls import withdraw_d5_after_checkpoint
    c = command_case
    cp = await checkpoint(c)
    item = await c.save()
    scope = SimpleNamespace(user=SimpleNamespace(user_id=c.user_id))
    async with c.session() as db:
        args = dict(proposal_ids=[item['proposal_id']], operation_key='batch')
        assert (await withdraw_d5_after_checkpoint(db, scope, c.task_id, UUID(cp['checkpoint_id']), reason='one', **args))[0]['outcome'] == 'withdrawn'
        assert (await withdraw_d5_after_checkpoint(db, scope, c.task_id, UUID(cp['checkpoint_id']), reason='two', **args))[0]['outcome'] == 'conflict'

async def test_http_checkpoint_and_partial_withdraw_contract(command_case):
    c = command_case
    runtime_headers = {'Authorization': 'Bearer ' + c.token}
    cp = await c.client.post('/api/agent/runtime/capa/d5/checkpoints', headers=runtime_headers, json={})
    assert cp.status_code == 200, cp.text
    item = await c.save()
    base = f'/api/agent/tasks/{c.task_id}/d5-checkpoints/{cp.json()["checkpoint_id"]}/proposals'
    listed = await c.client.get(base)
    assert listed.status_code == 200, listed.text
    assert listed.headers['cache-control'] == 'no-store'
    assert [r['proposal_id'] for r in listed.json()] == [str(item['proposal_id'])]
    result = await c.client.post(base+'/withdraw', json=dict(operation_key='http-batch', reason='reason', proposal_ids=[str(item['proposal_id'])]))
    assert result.status_code == 200, result.text
    assert result.json()[0]['outcome'] == 'withdrawn'

async def test_pause_restart_preserves_original_boundary_and_task_order(command_case):
    """Actual existing lifecycle; R5 model admission/binding remains a T6 dependency."""
    c = command_case
    first = await c.save()
    cp = await checkpoint(c)
    second = await c.save('second')
    pause = await c.client.post(f'/api/agent/tasks/{c.task_id}/control', json=dict(action='pause',
        run_id=str(c.run_id), expected_epoch=c.lease_epoch, idempotency_key='pause'))
    assert pause.status_code == 200, pause.text
    # Existing D4 paused-restart epoch remains separate from active R5 boundary.
    paused_cp = await c.client.post(f'/api/agent/tasks/{c.task_id}/d4-recovery-checkpoints',
        json=dict(run_id=str(c.run_id), expected_epoch=pause.json()['lease_epoch']))
    assert paused_cp.status_code == 200, paused_cp.text
    restart = await c.client.post(f'/api/agent/tasks/{c.task_id}/control', json=dict(action='restart',
        run_id=str(c.run_id), expected_epoch=pause.json()['lease_epoch'],
        checkpoint_id=paused_cp.json()['checkpoint_id'], idempotency_key='restart'))
    assert restart.status_code == 200, restart.text
    from app.services.agent_runtime.task_controls import d5_checkpoint_candidates
    async with c.session() as db:
        row = await db.get(AgentD5CheckpointPosition, UUID(cp['checkpoint_id']))
        assert row.watermark == 1
        assert list(await db.scalars(select(AgentD5Command.sequence).where(AgentD5Command.task_id == c.task_id).order_by(AgentD5Command.sequence))) == [1,2]
        rows = await d5_checkpoint_candidates(db, SimpleNamespace(user=SimpleNamespace(user_id=c.user_id)), c.task_id, UUID(cp['checkpoint_id']))
        assert [r['proposal_id'] for r in rows] == [second['proposal_id']]
        assert (await db.get(CapaD5Proposal, first['proposal_id'])).state == 'pending'

async def test_replace_and_adopt_actual_sessions_have_one_winner(command_case):
    import asyncio, json
    from app.models.agent_task import AgentTaskMessage
    from app.services.capa_d5_proposals import staff_action
    c = command_case
    first = await c.save()
    async with c.session() as db:
        message = AgentTaskMessage(task_id=c.task_id, sequence=2, author_id=c.user_id,
            idempotency_key='correction', state='accepted', delivery_batch_id=c.message_batch,
            delivery_epoch=c.lease_epoch, content=json.dumps(dict(intent='replace_d5', predecessor_id=str(first['proposal_id']))))
        db.add(message)
        await db.execute(update(AgentRun).where(AgentRun.run_id == c.run_id).values(accepted_message_seq=2))
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report_id).values(status='D5_CORRECTION'))
        await db.commit()
        message_id = message.message_id
    async def adopt():
        async with c.session() as db:
            try:
                return await staff_action(db, SimpleNamespace(user=SimpleNamespace(user_id=c.user_id)),
                    c.report_id, first['proposal_id'], operation='adopt', operation_key='adopt-race', value='final')
            except Exception:
                await db.rollback()
                raise
    results = await asyncio.gather(adopt(), c.save('replacement', operation='replace',
        predecessor_id=first['proposal_id'], correction_message_id=message_id), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1, results
    assert sum(isinstance(result, ValueError) for result in results) == 1, results
    async with c.session() as db:
        old = await db.get(CapaD5Proposal, first['proposal_id'])
        assert old.state in {'adopted','superseded'}
        assert await db.scalar(select(func.count()).select_from(CapaD5Measure)) == (old.state == 'adopted')

async def test_batch_interruption_preserves_prior_commit_and_individual_retry_key(command_case, monkeypatch):
    from app.services.agent_runtime.task_controls import withdraw_d5_after_checkpoint
    from app.services import capa_d5_proposals as proposals
    c = command_case
    cp = await checkpoint(c)
    items = [await c.save(str(i)) for i in range(2)]
    scope = SimpleNamespace(user=SimpleNamespace(user_id=c.user_id))
    actual = proposals.staff_action
    calls = 0
    async def interrupted(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2: raise RuntimeError('worker interrupted')
        return await actual(*args, **kwargs)
    monkeypatch.setattr(proposals, 'staff_action', interrupted)
    async with c.session() as db:
        args = dict(proposal_ids=[item['proposal_id'] for item in items], operation_key='recover', reason='reason')
        with pytest.raises(RuntimeError):
            await withdraw_d5_after_checkpoint(db, scope, c.task_id, UUID(cp['checkpoint_id']), **args)
        assert (await db.get(CapaD5Proposal, items[0]['proposal_id'])).state == 'withdrawn'
        assert (await db.get(CapaD5Proposal, items[1]['proposal_id'])).state == 'pending'
        monkeypatch.setattr(proposals, 'staff_action', actual)
        rows = await withdraw_d5_after_checkpoint(db, scope, c.task_id, UUID(cp['checkpoint_id']), **args)
        assert [r['outcome'] for r in rows] == ['withdrawn','withdrawn']
        assert await db.scalar(select(func.count()).select_from(CapaD5StaffReceipt)) == 2

async def test_real_request_scope_survives_rollback_between_batch_items(command_case):
    from app.core.deps import RequestScope
    from app.models.user import User
    from app.services.capa_current_access import current_capa_access
    from app.services.agent_runtime.task_controls import withdraw_d5_after_checkpoint
    c = command_case
    before = await c.save('before')
    cp = await checkpoint(c)
    after = await c.save('after')
    async with c.session() as db:
        user = await db.get(User, c.user_id)
        _, factories, lines = await current_capa_access(db, SimpleNamespace(user=user))
        scope = RequestScope(factory_scope=factories, effective_factory_id=c.factory_id,
            pl_scope=lines, user=user)
        rows = await withdraw_d5_after_checkpoint(db, scope, c.task_id, UUID(cp['checkpoint_id']),
            proposal_ids=[before['proposal_id'], after['proposal_id']], operation_key='real-request', reason='reason')
        assert [row['outcome'] for row in rows] == ['unavailable','withdrawn']
        assert await db.scalar(select(func.count()).select_from(CapaD5StaffReceipt)) == 1
