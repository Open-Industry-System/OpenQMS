"""Immutable checkpoints and bounded history on actual committed tenant rows."""
import asyncio
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.util import await_only

from app.models.agent_plugin import AgentPluginInstallation, AgentPluginGrant
from app.models.agent_readonly_control import AgentReadonlyCheckpoint, AgentCheckpointReceipt, AgentTaskUpdate, AgentTaskControl
from app.models.agent_runtime_event import AgentProjectionReceipt
from app.models.agent_task import AgentRun, AgentTask, AgentTaskMessage, AgentTaskGrant
from app.models.audit import AuditLog
from app.models.capa import CapaRootCauseVerification
from app.models.role import RolePermission, RoleDefinition
from app.services.agent_runtime import runtime_access, runtime_messages, run_dispatch, task_controls, readonly_delivery
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned
from tests.services.agent_runtime.test_runtime_messages import delivery, append, claim, ack, snapshot
from tests.services.agent_runtime.test_readonly_delivery import context_delivery, context
from tests.services.agent_runtime.test_task_controls import scope, control, wait_lock


def service():
    try:
        from app.services.agent_runtime import checkpoint_service
    except ImportError:
        pytest.fail('checkpoint service is not implemented')
    return checkpoint_service


async def save(owned, receipts, key='checkpoint'):
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        return await service().save_checkpoint(db, identity, dict(idempotency_key=key, receipt_ids=receipts))


async def view(owned, checkpoint_id):
    async with owned.factory(binding=owned.binding) as db:
        return await service().get_checkpoint_for_view(db, await scope(db, owned), owned.task_id, UUID(str(checkpoint_id)))


async def history(owned, after=0, limit=20):
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        return await runtime_messages.get_message_history(db, identity, after, limit)


async def restart(owned, checkpoint_id, key='restart', epoch=2):
    from app.schemas.agent_control import TaskControl
    async with owned.factory(binding=owned.binding) as db:
        return await task_controls.control_task(db, await scope(db, owned), owned.task_id,
            TaskControl(action='restart', run_id=owned.run_id, expected_epoch=epoch,
                checkpoint_id=checkpoint_id, idempotency_key=key))


async def counts(owned):
    async with owned.factory(binding=owned.binding) as db:
        return tuple([await db.scalar(select(func.count()).select_from(model)) for model in
            (AgentReadonlyCheckpoint, AgentCheckpointReceipt, AgentTaskControl, AgentRun)])


def test_strict_checkpoint_history_restart_contracts():
    from app.schemas import agent_runtime as schema
    assert hasattr(schema, 'ReadonlyCheckpointCreate'), 'checkpoint DTO is missing'
    valid = dict(idempotency_key='key', receipt_ids=[uuid4()])
    assert schema.ReadonlyCheckpointCreate(**valid)
    for fields in ({'receipt_ids': []}, {'receipt_ids': [uuid4() for _ in range(21)]},
                   {'idempotency_key': ''}, {'idempotency_key': 7}, {'idempotency_key': 'x'*101}):
        with pytest.raises(ValidationError):
            schema.ReadonlyCheckpointCreate(**{**valid, **fields})
    for name in ('watermark', 'accepted_message_seq', 'digest', 'tenant_generation', 'lease_epoch', 'memory', 'target_capa_id'):
        with pytest.raises(ValidationError):
            schema.ReadonlyCheckpointCreate(**valid, **{name: 'spoof'})
    for fields in ({'after_sequence': True}, {'after_sequence': '1'}, {'after_sequence': -1}, {'limit': 21}, {'limit': '1'}):
        with pytest.raises(ValidationError):
            schema.MessageHistoryQuery(**fields)
    from app.schemas.agent_control import TaskControl
    base = dict(run_id=uuid4(), expected_epoch=1, idempotency_key='key', checkpoint_id=uuid4())
    assert TaskControl(action='restart', **base)
    for action in ('pause', 'resume', 'cancel'):
        with pytest.raises(ValidationError):
            TaskControl(action=action, **base)


@pytest.mark.asyncio
async def test_checkpoint_actual_position_plural_different_versions_and_atomic_retry(context_delivery):
    owned = context_delivery
    first = await context(owned)
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.verification_id == UUID(int=2)).values(conclusion='failed'))
        await db.commit()
    second = await context(owned)
    assert first['projection_digest'] != second['projection_digest']
    receipts = [first['receipt_id'], second['receipt_id']]
    await append(owned, 'queued future input')
    cp = await save(owned, receipts)
    assert cp['accepted_message_seq'] == 0 and cp['update_sequence'] > 0
    assert cp == await save(owned, receipts[::-1]+receipts[:1])
    assert (await counts(owned))[:2] == (1, 2)
    assert (await view(owned, cp['checkpoint_id']))['is_latest']
    async with owned.factory(binding=owned.binding) as db:
        pointer = await db.scalar(select(AgentTaskUpdate).where(AgentTaskUpdate.kind == 'checkpoint'))
        assert pointer.object_id == UUID(cp['checkpoint_id']) and pointer.sequence == cp['update_sequence']
        audits = list((await db.scalars(select(AuditLog).where(AuditLog.action == 'SAVE_AGENT_READONLY_CHECKPOINT'))).all())
        assert len(audits) == 1 and 'queued future input' not in str(audits[0].changed_fields)
    with pytest.raises(ValueError):
        await save(owned, receipts[:1])
    batch = await claim(owned)
    await ack(owned, batch.batch_id, 1)
    with pytest.raises(ValueError):
        await save(owned, receipts)
    assert (await counts(owned))[:2] == (1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['claimed', 'gap', 'accepted_above', 'watermark'])
async def test_checkpoint_rejects_unconfirmed_claim_and_corrupt_prefix(context_delivery, change):
    owned = context_delivery
    receipts = [(await context(owned))['receipt_id']]
    await append(owned, 'first'); await append(owned, 'second')
    batch = await claim(owned)
    if change != 'claimed':
        await ack(owned, batch.batch_id, 2)
        async with owned.factory(binding=owned.binding) as db:
            if change == 'gap':
                await db.execute(delete(AgentTaskMessage).where(AgentTaskMessage.sequence == 1))
            else:
                await db.execute(update(AgentRun).where(AgentRun.run_id == owned.run_id).values(accepted_message_seq=1 if change == 'accepted_above' else 3))
            await db.commit()
    before = await snapshot(owned)
    with pytest.raises(ValueError):
        await save(owned, receipts)
    assert (await counts(owned))[:2] == (0, 0) and await snapshot(owned) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['foreign_run', 'epoch', 'generation', 'digest', 'projection', 'source'])
async def test_checkpoint_requires_actual_current_receipt_coordinates(context_delivery, change):
    owned = context_delivery
    receipt_id = UUID((await context(owned))['receipt_id'])
    async with owned.factory(binding=owned.binding) as db:
        row = await db.get(AgentProjectionReceipt, receipt_id)
        if change == 'foreign_run':
            other = AgentRun(task_id=owned.task_id, installation_id=owned.plugin_id, plugin_version='1.0.0', status='completed')
            db.add(other); await db.flush(); row.run_id = other.run_id
        else:
            fields = {'epoch': ('lease_epoch', 0), 'generation': ('tenant_generation', owned.binding.generation+1),
                'digest': ('projection_digest', 'a'*63), 'projection': ('projection_id', 'unknown'), 'source': ('source_capa_id', uuid4())}
            if change == 'source':
                from app.models.capa import CAPAEightD
                other = CAPAEightD(document_no='8D-OTHER', title='other', factory_id=owned.factory_id, product_line_code='DC-DC-100')
                db.add(other); await db.flush(); row.source_capa_id = other.report_id
            else:
                name, value = fields[change]; setattr(row, name, value)
        await db.commit()
    with pytest.raises(PermissionError):
        await save(owned, [receipt_id])
    assert (await counts(owned))[:2] == (0, 0)


@pytest.mark.asyncio
async def test_same_run_resume_history_prefix_only_and_no_mutation(context_delivery):
    owned = context_delivery
    receipts = [(await context(owned))['receipt_id']]
    for value in ('accepted original', 'pending original'):
        await append(owned, value)
    batch = await claim(owned); await ack(owned, batch.batch_id, 1)
    await control(owned, 'pause')
    from app.services.agent_runtime import message_queue
    async with owned.factory(binding=owned.binding) as db:
        await message_queue.append_task_message(db, await db.get(AgentTask, owned.task_id), await scope(db, owned), 'while paused', 'paused-input')
    await control(owned, 'resume', epoch=2)
    async with owned.factory(binding=owned.binding) as db:
        newer = await run_dispatch.claim_run(db, owned.binding, owned.plugin_id, owned.secret, 'resumed')
    owned.token = newer.token
    before = await snapshot(owned)
    page = await history(owned, limit=1)
    assert [m.content for m in page.messages] == ['accepted original']
    assert page.next_sequence == 1 and page.complete
    assert not (await history(owned, 1)).messages and (await history(owned, 50)).complete
    assert await snapshot(owned) == before
    assert [m.sequence for m in (await claim(owned)).messages] == [2, 3]
    with pytest.raises(ValueError):
        await ack(owned, batch.batch_id, 2)
    with pytest.raises(PermissionError):
        await save(owned, receipts)


@pytest.mark.asyncio
async def test_latest_safe_restart_inherits_prefix_fences_old_receipts_and_exact_retry(context_delivery):
    owned = context_delivery
    receipt = (await context(owned))['receipt_id']
    await append(owned, 'accepted original')
    batch = await claim(owned); await ack(owned, batch.batch_id, 1)
    old_cp = await save(owned, [receipt], 'old')
    cp = await save(owned, [receipt], 'latest')
    await append(owned, 'queued future')
    await control(owned, 'pause')
    assert not (await view(owned, old_cp['checkpoint_id']))['is_latest']
    with pytest.raises(ValueError):
        await restart(owned, old_cp['checkpoint_id'])
    before = await snapshot(owned)
    restarted = await restart(owned, cp['checkpoint_id'])
    assert restarted.run_id != owned.run_id and restarted.run_status == 'pending' and restarted.lease_epoch == 0
    again = await restart(owned, cp['checkpoint_id'])
    assert again.control_id == restarted.control_id and again.run_id == restarted.run_id
    assert (await snapshot(owned))[1:] == before[1:]
    async with owned.factory(binding=owned.binding) as db:
        old = await db.get(AgentRun, owned.run_id); new = await db.get(AgentRun, restarted.run_id)
        assert old.status == 'stopped' and old.lease_epoch == 3 and old.claim_key is None
        assert new.accepted_message_seq == 1 and new.resume_checkpoint_id == UUID(cp['checkpoint_id'])
        newer = await run_dispatch.claim_run(db, owned.binding, owned.plugin_id, owned.secret, 'restarted')
    assert newer.accepted_message_seq == 1 and newer.has_resume_checkpoint
    owned.token = newer.token
    assert [m.content for m in (await history(owned)).messages] == ['accepted original']
    assert [m.sequence for m in (await claim(owned)).messages] == [2]
    with pytest.raises(PermissionError):
        await save(owned, [receipt], 'new-run')
    with pytest.raises(PermissionError):
        async with owned.factory(binding=owned.binding) as db:
            identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
            await readonly_delivery.save_result(db, identity, dict(idempotency_key='old-source', receipt_ids=[receipt], payload={}))
    assert (await view(owned, cp['checkpoint_id']))['checkpoint_id'] == cp['checkpoint_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['plugin', 'version', 'plugin_grant', 'task_grant', 'permission', 'trust', 'prefix'])
async def test_restart_current_authority_and_prefix_before_any_mutation(context_delivery, monkeypatch, change):
    owned = context_delivery
    cp = await save(owned, [(await context(owned))['receipt_id']])
    await control(owned, 'pause')
    if change == 'trust':
        monkeypatch.setattr(runtime_access, 'TRUSTED_DELIVERY_DEPLOYMENTS', frozenset())
    else:
        changes = {'plugin': update(AgentPluginInstallation).values(enabled=False),
            'version': update(AgentPluginInstallation).values(plugin_version='changed'),
            'plugin_grant': delete(AgentPluginGrant), 'task_grant': delete(AgentTaskGrant),
            'permission': update(RolePermission).where(RolePermission.module=='capa').values(permission_level=0),
            'prefix': update(AgentRun).values(accepted_message_seq=1)}
        async with owned.factory(binding=owned.binding) as db:
            await db.execute(changes[change]); await db.commit()
    before = await counts(owned), await snapshot(owned)
    with pytest.raises((PermissionError, ValueError)):
        await restart(owned, cp['checkpoint_id'])
    assert (await counts(owned), await snapshot(owned)) == before


@pytest.mark.asyncio
async def test_historical_checkpoint_keeps_saved_generation_without_live_plugin(context_delivery, monkeypatch):
    owned = context_delivery
    cp = await save(owned, [(await context(owned))['receipt_id']])
    await control(owned, 'pause')
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentPluginInstallation).values(enabled=False)); await db.commit()
    async with owned.engine.begin() as conn:
        await conn.execute(text('UPDATE public.tenants SET generation=generation+1 WHERE id=:id'), {'id': owned.binding.tenant_id})
    owned.binding = replace(owned.binding, generation=owned.binding.generation+1)
    monkeypatch.setattr(runtime_access, 'TRUSTED_DELIVERY_DEPLOYMENTS', frozenset())
    assert (await view(owned, cp['checkpoint_id']))['tenant_generation'] == cp['tenant_generation']
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentProjectionReceipt).values(projection_digest='bad')); await db.commit()
    with pytest.raises(PermissionError):
        await view(owned, cp['checkpoint_id'])


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['save', 'history', 'view'])
async def test_final_authority_after_materialization_revocation_returns_nothing(context_delivery, operation):
    owned = context_delivery
    receipt = (await context(owned))['receipt_id']
    cp = await save(owned, [receipt]) if operation == 'view' else None
    if operation == 'history':
        await append(owned, 'restricted original'); batch = await claim(owned); await ack(owned, batch.batch_id, 1)
    reached, release = asyncio.Event(), asyncio.Event()
    async def pause():
        reached.set(); await release.wait()
    def intercept(conn, cursor, statement, parameters, ctx, many):
        needle = 'agent_task_messages.content' if operation == 'history' else 'FROM agent_projection_receipts'
        if needle in statement:
            await_only(pause())
    event.listen(owned.engine.sync_engine, 'after_cursor_execute', intercept)
    coroutine = save(owned, [receipt]) if operation == 'save' else history(owned) if operation == 'history' else view(owned, cp['checkpoint_id'])
    future = asyncio.create_task(coroutine)
    try:
        await asyncio.wait_for(reached.wait(), 10)
        async with owned.factory(binding=owned.binding) as db:
            await db.execute(update(RolePermission).where(RolePermission.module=='capa').values(permission_level=0)); await db.commit()
        release.set()
        with pytest.raises(PermissionError):
            await asyncio.wait_for(future, 10)
    finally:
        release.set(); await asyncio.gather(future, return_exceptions=True)
        event.remove(owned.engine.sync_engine, 'after_cursor_execute', intercept)
    assert (await counts(owned))[0] == (1 if operation == 'view' else 0)


@pytest.mark.asyncio
async def test_checkpoint_audit_failure_and_unknown_integrity_are_atomic(context_delivery):
    owned = context_delivery
    receipt = (await context(owned))['receipt_id']
    def fail(conn, cursor, statement, params, ctx, many):
        if statement.startswith('INSERT INTO audit_logs'):
            raise RuntimeError('fixture audit failure')
    event.listen(owned.engine.sync_engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='fixture audit failure'):
            await save(owned, [receipt])
    finally:
        event.remove(owned.engine.sync_engine, 'before_cursor_execute', fail)
    assert (await counts(owned))[:2] == (0, 0)
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        db.add(AgentCheckpointReceipt(checkpoint_id=uuid4(), receipt_id=uuid4()))
        with pytest.raises(IntegrityError):
            await service().save_checkpoint(db, identity, dict(idempotency_key='bad', receipt_ids=[receipt]))
    assert (await counts(owned))[:2] == (0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('same_key', [True, False])
async def test_actual_competing_restarts_create_only_one_new_run(context_delivery, same_key):
    owned = context_delivery
    cp = await save(owned, [(await context(owned))['receipt_id']]); await control(owned, 'pause')
    async with owned.factory(binding=owned.binding) as holder:
        await holder.scalar(select(AgentPluginInstallation).where(AgentPluginInstallation.installation_id==owned.plugin_id).with_for_update())
        first = asyncio.create_task(restart(owned, cp['checkpoint_id']))
        second = asyncio.create_task(restart(owned, cp['checkpoint_id'], 'restart' if same_key else 'competing'))
        try:
            await wait_lock(owned, 'agent_plugin_installations'); await holder.commit()
            results = await asyncio.wait_for(asyncio.gather(first, second, return_exceptions=True), 15)
        finally:
            for future in (first, second):
                if not future.done(): future.cancel()
            await asyncio.gather(first, second, return_exceptions=True)
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) == (2 if same_key else 1), results
    if same_key: assert successes[0].control_id == successes[1].control_id
    else: assert any(isinstance(r, ValueError) for r in results)
    assert (await counts(owned))[3] == 2


@pytest.mark.asyncio
async def test_history_bounded_pages_entire_prefix_proof_and_no_second_ack(context_delivery):
    owned = context_delivery
    for i in range(23):
        await append(owned, 'original '+str(i))
    batch = await claim(owned); await ack(owned, batch.batch_id, 20)
    batch2 = await claim(owned); await ack(owned, batch2.batch_id, 22)
    before = await snapshot(owned)
    first = await history(owned)
    assert len(first.messages) == 20 and first.next_sequence == 20 and not first.complete
    second = await history(owned, first.next_sequence)
    assert [m.sequence for m in second.messages] == [21, 22] and second.complete and second.next_sequence == 22
    assert await snapshot(owned) == before
    async with owned.factory(binding=owned.binding) as db:
        # Corruption on an earlier, unrequested page must deny this later page.
        await db.execute(delete(AgentTaskMessage).where(AgentTaskMessage.sequence==1)); await db.commit()
    with pytest.raises(ValueError):
        await history(owned, 20)


@pytest.mark.asyncio
async def test_restart_fault_after_replacement_insert_rolls_back_every_object(context_delivery):
    from tests.services.agent_runtime.test_task_controls import state
    owned = context_delivery
    cp = await save(owned, [(await context(owned))['receipt_id']]); await control(owned, 'pause')
    before = await counts(owned), await state(owned)
    inserts = []
    def fail(conn, cursor, statement, params, ctx, many):
        if statement.startswith('INSERT'):
            inserts.append(statement)
        if statement.startswith('INSERT INTO audit_logs'):
            raise RuntimeError('fixture restart audit failure')
    event.listen(owned.engine.sync_engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='fixture restart audit failure'):
            await restart(owned, cp['checkpoint_id'])
    finally:
        event.remove(owned.engine.sync_engine, 'before_cursor_execute', fail)
    assert any(sql.startswith('INSERT INTO agent_runs') for sql in inserts)
    assert (await counts(owned), await state(owned)) == before


@pytest.mark.asyncio
async def test_restart_retained_namespace_generation_is_historical_reference_only(context_delivery):
    owned = context_delivery
    receipt = (await context(owned))['receipt_id']
    cp = await save(owned, [receipt]); await control(owned, 'pause')
    async with owned.engine.begin() as conn:
        await conn.execute(text('UPDATE public.tenants SET generation=generation+1 WHERE id=:id'), {'id': owned.binding.tenant_id})
    owned.binding = replace(owned.binding, generation=owned.binding.generation+1)
    result = await restart(owned, cp['checkpoint_id'])
    assert result.run_id != owned.run_id
    async with owned.factory(binding=owned.binding) as db:
        claimed = await run_dispatch.claim_run(db, owned.binding, owned.plugin_id, owned.secret, 'new-generation')
    owned.token = claimed.token
    with pytest.raises(PermissionError):
        await save(owned, [receipt], 'old-generation')
    assert (await view(owned, cp['checkpoint_id']))['tenant_generation'] == cp['tenant_generation']


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['save', 'history', 'view'])
async def test_plain_session_tenant_info_spoof_cannot_admit_checkpoint_or_history(context_delivery, operation):
    from sqlalchemy.ext.asyncio import AsyncSession
    owned = context_delivery
    receipt = (await context(owned))['receipt_id']
    cp = await save(owned, [receipt])
    async with owned.factory(binding=owned.binding) as actual:
        identity = await runtime_access.verify_runtime_identity(actual, owned.token, owned.binding)
        user_scope = await scope(actual, owned)
    async with AsyncSession(owned.engine, info={'tenant_binding': owned.binding}, expire_on_commit=False) as db:
        with pytest.raises(PermissionError):
            if operation == 'save':
                await service().save_checkpoint(db, identity, dict(idempotency_key='spoof', receipt_ids=[receipt]))
            elif operation == 'history':
                await runtime_messages.get_message_history(db, identity)
            else:
                await service().get_checkpoint_for_view(db, user_scope, owned.task_id, UUID(cp['checkpoint_id']))


@pytest.mark.asyncio
async def test_restart_uses_monotonic_pointer_when_checkpoint_times_tie(context_delivery):
    owned = context_delivery
    receipt = (await context(owned))['receipt_id']
    first = await save(owned, [receipt], 'first'); second = await save(owned, [receipt], 'second')
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentReadonlyCheckpoint).values(created_at=func.now())); await db.commit()
    await control(owned, 'pause')
    with pytest.raises(ValueError):
        await restart(owned, first['checkpoint_id'])
    assert (await restart(owned, second['checkpoint_id'])).run_id != owned.run_id


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['source', 'role', 'canonical'])
async def test_restart_withdrawn_source_or_policy_is_atomic(context_delivery, monkeypatch, change):
    from app.services.agent.permissions import catalog
    from app.services.agent.permissions.types import ApprovalFloor
    from types import MappingProxyType
    owned = context_delivery
    cp = await save(owned, [(await context(owned))['receipt_id']]); await control(owned, 'pause')
    if change == 'canonical':
        monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', MappingProxyType({k: replace(v, approval_floor=ApprovalFloor.DENY) for k,v in catalog.CAPA_CAPABILITIES.items()}))
    else:
        query = update(AgentProjectionReceipt).values(projection_id='withdrawn') if change=='source' else update(RoleDefinition).where(RoleDefinition.id==owned.role_id).values(is_active=False)
        async with owned.factory(binding=owned.binding) as db:
            await db.execute(query); await db.commit()
    before = await counts(owned), await snapshot(owned)
    with pytest.raises(PermissionError):
        await restart(owned, cp['checkpoint_id'])
    assert (await counts(owned), await snapshot(owned)) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['history', 'view'])
async def test_source_product_line_withdrawal_during_read_returns_no_material(context_delivery, operation):
    from app.models.capa import CAPAEightD
    from app.models.factory import UserFactory
    from app.models.role import UserProductLine
    from app.models.product_line import ProductLine
    owned = context_delivery
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(delete(RolePermission).where(RolePermission.role_id==owned.role_id, RolePermission.module=='group'))
        await db.execute(update(RoleDefinition).where(RoleDefinition.id==owned.role_id).values(bypass_row_level_security=False))
        await db.execute(delete(UserFactory).where(UserFactory.user_id==owned.user_id))
        db.add(UserFactory(user_id=owned.user_id, factory_id=owned.factory_id))
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id==owned.user_id))
        db.add(UserProductLine(user_id=owned.user_id, product_line_code='DC-DC-100'))
        db.add(ProductLine(code='NEW-CP-LINE', name='withdrawn line', factory_id=owned.factory_id))
        await db.commit()
    cp = await save(owned, [(await context(owned))['receipt_id']])
    await append(owned, 'original protected input'); batch = await claim(owned); await ack(owned, batch.batch_id, 1)
    reached, release = asyncio.Event(), asyncio.Event()
    async def pause():
        reached.set(); await release.wait()
    def intercept(conn, cursor, statement, params, ctx, many):
        needle = 'agent_task_messages.content' if operation=='history' else 'FROM agent_projection_receipts'
        if needle in statement:
            await_only(pause())
    event.listen(owned.engine.sync_engine, 'after_cursor_execute', intercept)
    future = asyncio.create_task(history(owned) if operation=='history' else view(owned, cp['checkpoint_id']))
    try:
        await asyncio.wait_for(reached.wait(), 10)
        async with owned.factory(binding=owned.binding) as db:
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==owned.report_id).values(product_line_code='NEW-CP-LINE')); await db.commit()
        release.set()
        with pytest.raises(PermissionError):
            await asyncio.wait_for(future, 10)
    finally:
        release.set(); await asyncio.gather(future, return_exceptions=True)
        event.remove(owned.engine.sync_engine, 'after_cursor_execute', intercept)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['links', 'epoch', 'generation', 'run_association'])
async def test_historical_checkpoint_corrupt_saved_sources_or_run_association_denied(context_delivery, change):
    owned = context_delivery
    cp = await save(owned, [(await context(owned))['receipt_id']])
    async with owned.factory(binding=owned.binding) as db:
        if change == 'links':
            await db.execute(delete(AgentCheckpointReceipt))
        elif change == 'run_association':
            old = await db.get(AgentTask, owned.task_id)
            other = AgentTask(initiator_id=old.initiator_id, executor_user_id=old.executor_user_id,
                preferred_installation_id=old.preferred_installation_id, target_capa_id=old.target_capa_id,
                factory_id=old.factory_id, status='ready', request_key=uuid4().hex)
            db.add(other); await db.flush()
            await db.execute(update(AgentRun).where(AgentRun.run_id==owned.run_id).values(task_id=other.task_id))
        else:
            await db.execute(update(AgentProjectionReceipt).values(**{'lease_epoch' if change=='epoch' else 'tenant_generation': 999}))
        await db.commit()
    with pytest.raises(PermissionError):
        await view(owned, cp['checkpoint_id'])
