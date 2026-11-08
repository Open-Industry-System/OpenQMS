"""Committed task activity is serialized by the caller's task row lock."""
import asyncio
import importlib.util
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.models.agent_readonly_control import AgentTaskUpdate
from app.models.agent_runtime_event import AgentRunEvent, AgentResult, AgentEventReceipt, AgentResultReceipt
from app.models.audit import AuditLog
from app.models.agent_task import AgentRun, AgentTask, AgentTaskMessage
from app.models.agent_plugin import AgentPluginInstallation
from app.models.user import User
from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.services.agent_runtime import run_dispatch, task_service, runtime_access, runtime_messages, readonly_delivery, message_queue
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned
from tests.services.agent_runtime.test_runtime_messages import delivery, append, claim, ack
from tests.services.agent_runtime.test_readonly_delivery import context_delivery, context
from tests.services.agent_runtime.test_readonly_outputs import event_body, result_body, write


def updates_service():
    name = 'app.services.agent_runtime.task_updates'
    assert importlib.util.find_spec(name) is not None, 'atomic task update helper is missing'
    return __import__(name, fromlist=['append_update'])


async def updates(owned, task_id=None):
    async with owned.factory(binding=owned.binding) as db:
        rows = (await db.scalars(select(AgentTaskUpdate).where(
            AgentTaskUpdate.task_id == (task_id or owned.task_id))
            .order_by(AgentTaskUpdate.sequence))).all()
        return [(r.sequence, r.kind, r.object_id) for r in rows]


async def append_event(db, owned, key):
    await db.scalar(select(AgentTask).where(AgentTask.task_id == owned.task_id).with_for_update())
    row = AgentRunEvent(task_id=owned.task_id, run_id=owned.run_id,
        idempotency_key=key, event_type='progress', payload={})
    db.add(row)
    await db.flush()
    pointer = await updates_service().append_update(db, task_id=owned.task_id,
        kind='event', object_id=row.event_id)
    return row.event_id, pointer.sequence


@pytest.mark.asyncio
@pytest.mark.parametrize('rollback', [False, True])
async def test_same_task_writer_waits_for_commit_and_rollback_hides_both_rows(committed_runtime, rollback):
    owned = committed_runtime
    started = asyncio.Event()
    async with owned.factory(binding=owned.binding) as first:
        first_id, seq = await append_event(first, owned, 'first')
        assert seq == 1
        async def second_writer():
            async with owned.factory(binding=owned.binding) as second:
                started.set()
                result = await append_event(second, owned, 'second')
                await second.commit()
                return result
        future = asyncio.create_task(second_writer())
        try:
            await started.wait()
            waiting = 0
            for _ in range(100):
                async with owned.engine.connect() as observer:
                    waiting = await observer.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%agent_tasks%FOR UPDATE%'"))
                if waiting:
                    break
                await asyncio.sleep(.01)
            assert waiting and not future.done(), 'second allocator must wait for the task lock'
            assert await updates(owned) == []
            async with owned.factory(binding=owned.binding) as observer:
                assert await observer.get(AgentRunEvent, first_id) is None
            await (first.rollback() if rollback else first.commit())
            second_id, second_seq = await asyncio.wait_for(future, 10)
        finally:
            if not future.done():
                future.cancel()
                await asyncio.gather(future, return_exceptions=True)
    assert second_seq == (1 if rollback else 2)
    assert await updates(owned) == ([(1, 'event', second_id)] if rollback else
        [(1, 'event', first_id), (2, 'event', second_id)])
    async with owned.factory(binding=owned.binding) as observer:
        assert (await observer.get(AgentRunEvent, first_id) is None) == rollback


@pytest.mark.asyncio
async def test_distinct_task_sequence_is_independent_of_uncommitted_other_task(committed_runtime):
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as db:
        original = await db.get(AgentTask, owned.task_id)
        other = AgentTask(initiator_id=owned.user_id, executor_user_id=owned.user_id,
            preferred_installation_id=owned.plugin_id, target_capa_id=original.target_capa_id,
            factory_id=original.factory_id, request_key=uuid.uuid4().hex, status='ready')
        db.add(other)
        await db.commit()
        other_id = other.task_id
    async with owned.factory(binding=owned.binding) as first:
        await append_event(first, owned, 'held')
        async def independent():
            async with owned.factory(binding=owned.binding) as db:
                await db.scalar(select(AgentTask).where(AgentTask.task_id == other_id).with_for_update())
                pointer = await updates_service().append_update(db, task_id=other_id,
                    kind='claim', object_id=owned.run_id)
                await db.commit()
                return pointer.sequence
        assert await asyncio.wait_for(independent(), 5) == 1
        assert await updates(owned) == []
        await first.rollback()
    assert len(await updates(owned, other_id)) == 1


@pytest.mark.asyncio
async def test_effective_message_claim_ack_and_run_retry_have_one_pointer(delivery):
    owned = delivery
    assert await updates(owned) == [(1, 'claim', owned.run_id)]
    async with owned.factory(binding=owned.binding) as db:
        await run_dispatch.claim_run(db, owned.binding, owned.plugin_id, owned.secret, 'messages')
    first = await append(owned, 'instruction', 'message-key')
    retry = await append(owned, 'instruction', 'message-key')
    assert first.message_id == retry.message_id
    assert await updates(owned) == [(1, 'claim', owned.run_id), (2, 'message', first.message_id)]
    second = await append(owned, 'next instruction', 'second-key')
    batch = await claim(owned)
    async with owned.factory(binding=owned.binding) as db:
        assert (await db.get(AgentTaskMessage, first.message_id)).state == 'claimed'
    before = await updates(owned)
    assert (await claim(owned, 1)).model_dump() == batch.model_dump()
    assert await updates(owned) == before
    await ack(owned, batch.batch_id, 1)
    before = await updates(owned)
    assert before == [(1, 'claim', owned.run_id), (2, 'message', first.message_id),
        (3, 'message', second.message_id), (4, 'ack', batch.batch_id)]
    await ack(owned, batch.batch_id, 1)
    assert await updates(owned) == before
    await ack(owned, batch.batch_id, 2)
    assert await updates(owned) == before + [(5, 'ack', batch.batch_id)]
    await ack(owned, batch.batch_id, 1)
    await ack(owned, batch.batch_id, 2)
    assert await updates(owned) == before + [(5, 'ack', batch.batch_id)]


@pytest.mark.asyncio
async def test_event_and_result_retries_keep_exact_committed_pointer_order(context_delivery):
    owned = context_delivery
    receipt = (await context(owned))['receipt_id']
    first = await write(owned, event_body([receipt]), True)
    result = await write(owned, result_body([receipt]))
    expected = [(1, 'claim', owned.run_id), (2, 'event', uuid.UUID(first['event_id'])),
        (3, 'result', uuid.UUID(result['result_id']))]
    assert await updates(owned) == expected
    assert await write(owned, event_body([receipt]), True) == first
    assert await write(owned, result_body([receipt])) == result
    assert await updates(owned) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('blocked', [False, True])
async def test_initial_message_optional_run_and_creation_race_are_atomic(ready_owned, monkeypatch, blocked):
    owned = ready_owned
    async with owned.factory(binding=owned.binding) as db:
        original = await db.get(AgentTask, owned.task_id)
        target = original.target_capa_id
        if blocked:
            plugin = await db.get(AgentPluginInstallation, owned.plugin_id)
            plugin.manifest = dict(protocol_versions=['1'], required_capabilities=['unknown.context'])
            await db.commit()
    both_absent = asyncio.Event()
    absent = 0
    original_existing = task_service._existing
    async def simultaneous(*args):
        nonlocal absent
        found = await original_existing(*args)
        if found is None:
            absent += 1
            if absent == 2:
                both_absent.set()
            await both_absent.wait()
        return found
    monkeypatch.setattr(task_service, '_existing', simultaneous)
    key = uuid.uuid4().hex
    async def create():
        async with owned.factory(binding=owned.binding) as db:
            user = await db.get(User, owned.user_id)
            scope = RequestScope(FactoryScope([], None), None, ProductLineScope('NONE', None), user)
            task = await task_service.create_task(db, scope, target, owned.plugin_id, key, 'initial instruction')
            return task.task_id
    identifiers = await asyncio.wait_for(asyncio.gather(create(), create()), 20)
    assert identifiers[0] == identifiers[1] == await create()
    async with owned.factory(binding=owned.binding) as db:
        message = await db.scalar(select(AgentTaskMessage).where(AgentTaskMessage.task_id == identifiers[0]))
        run = await db.scalar(select(AgentRun).where(AgentRun.task_id == identifiers[0]))
        expected = [(1, 'message', message.message_id)]
        if blocked:
            assert run is None
        else:
            assert run.status == 'pending'
            expected.append((2, 'run_created', run.run_id))
        assert await updates(owned, identifiers[0]) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['message', 'ack', 'event', 'result', 'claim', 'initial_message', 'initial_run'])
async def test_failure_after_update_flush_rolls_back_object_audit_and_pointer(context_delivery, monkeypatch, operation):
    owned = context_delivery
    receipt = (await context(owned))['receipt_id']
    batch = None
    if operation == 'ack':
        await append(owned, 'instruction')
        batch = await claim(owned)
    if operation == 'claim':
        async with owned.factory(binding=owned.binding) as db:
            run = await db.get(AgentRun, owned.run_id)
            run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()
    models = (AgentTask, AgentRun, AgentTaskMessage, AgentRunEvent, AgentResult,
        AgentEventReceipt, AgentResultReceipt, AuditLog, AgentTaskUpdate)
    async def snapshot():
        async with owned.factory(binding=owned.binding) as db:
            counts = [await db.scalar(select(func.count()).select_from(model)) for model in models]
            run = await db.get(AgentRun, owned.run_id)
            messages = (await db.scalars(select(AgentTaskMessage).order_by(AgentTaskMessage.sequence))).all()
            return counts, (run.status, run.lease_epoch, run.claim_key, run.accepted_message_seq), [
                (r.message_id, r.state, r.delivery_batch_id, r.delivery_epoch) for r in messages]
    before = await snapshot()
    helper = updates_service()
    original_append = helper.append_update
    failure_kind = {'initial_message': 'message', 'initial_run': 'run_created'}.get(operation, operation)
    async def fail_after_flush(db, **fields):
        pointer = await original_append(db, **fields)
        if fields['kind'] == failure_kind:
            raise RuntimeError('injected transaction abort')
        return pointer
    monkeypatch.setattr(helper, 'append_update', fail_after_flush)
    async with owned.factory(binding=owned.binding) as db:
        with pytest.raises(RuntimeError, match='injected transaction abort'):
            if operation == 'claim':
                await run_dispatch.claim_run(db, owned.binding, owned.plugin_id, owned.secret, 'reclaim')
            else:
                identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
                if operation == 'message':
                    await message_queue.append_task_message(db, identity.task, identity.scope, 'new', 'abort')
                elif operation == 'ack':
                    await runtime_messages.ack_messages(db, identity, batch.batch_id, 1)
                elif operation in {'event', 'result'}:
                    await (readonly_delivery.record_event(db, identity, event_body([receipt])) if operation == 'event'
                        else readonly_delivery.save_result(db, identity, result_body([receipt])))
                else:
                    await task_service.create_task(db, identity.scope, identity.task.target_capa_id,
                        owned.plugin_id, 'abort-create', 'initial')
        await db.rollback()
    assert await snapshot() == before
