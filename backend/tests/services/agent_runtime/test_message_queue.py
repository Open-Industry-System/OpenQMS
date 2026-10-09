"""Initiator instructions serialize on the task and recheck current target access."""
import asyncio
import time
import uuid

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import delete, event, func, select, text, update

from app.config import settings
from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_task import AgentTask, AgentTaskMessage
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.factory import UserFactory
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from app.services.agent_runtime.task_service import create_task, get_task_for_view


def queue():
    try:
        from app.services.agent_runtime import message_queue
    except ImportError:
        pytest.fail('ordered message queue is not implemented')
    return message_queue


def message_schemas():
    try:
        from app.schemas.agent_task import TaskMessageCreate, TaskMessageOut
    except ImportError:
        pytest.fail('message request/output schemas are not implemented')
    return TaskMessageCreate, TaskMessageOut


def cached_scope(user, factory_id=None):
    # These deliberately broad cached facts cannot authorize the append.
    return RequestScope(FactoryScope(None, factory_id), factory_id,
        ProductLineScope('ALL', None), user)


@pytest_asyncio.fixture
async def message_context(db, admin_user, sample_capa, enabled_plugin, monkeypatch):
    monkeypatch.setattr(settings, 'TENANT_MODE', 'single')
    scope = cached_scope(admin_user, sample_capa.factory_id)
    task = await create_task(db, scope, sample_capa.report_id,
        enabled_plugin.installation_id, uuid.uuid4().hex, '初始指令')
    return task, scope


async def counts(db, task_id):
    messages = await db.scalar(select(func.count()).select_from(AgentTaskMessage).where(
        AgentTaskMessage.task_id == task_id))
    audits = await db.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.table_name == 'agent_task_messages'))
    return messages, audits


def test_message_request_is_strict_bounded_and_output_has_only_safe_fields():
    Request, Output = message_schemas()
    fields = {'content': '补充证据', 'idempotency_key': 'key'}
    assert Request(**fields).content == fields['content']
    for forbidden in ['author_id', 'user', 'executor_user_id', 'sensitivity', 'state', 'sequence']:
        with pytest.raises(ValidationError):
            Request(**fields, **{forbidden: 'untrusted'})
    for field, value in [('content', ''), ('content', 'x'*10001), ('content', 123),
        ('idempotency_key', ''), ('idempotency_key', 'x'*101), ('idempotency_key', 123)]:
        with pytest.raises(ValidationError):
            Request(**{**fields, field: value})
    assert set(Output.model_fields) == {'message_id', 'task_id', 'sequence', 'content',
        'sensitivity', 'state', 'created_at'}
    assert all(field.is_required() for field in Output.model_fields.values())


@pytest.mark.asyncio
async def test_append_retry_and_conflict_preserve_order_and_safe_audit(db, message_context):
    task, scope = message_context
    first = await queue().append_task_message(db, task, scope, '补充证据', 'key-1')
    retry = await queue().append_task_message(db, task, scope, '补充证据', 'key-1')
    assert (first.message_id, first.sequence) == (retry.message_id, retry.sequence)
    assert first.sequence == 2  # real Task 4 creation queued sequence 1
    before = await counts(db, task.task_id)
    with pytest.raises(ValueError, match='different content'):
        await queue().append_task_message(db, task, scope, 'conflicting text', 'key-1')
    assert await counts(db, task.task_id) == before
    second = await queue().append_task_message(db, task, scope, '核对反证', 'key-2')
    assert second.sequence == 3
    assert (second.sensitivity, second.state, second.author_id) == ('restricted', 'queued', scope.user.user_id)
    assert await counts(db, task.task_id) == (3, 2)
    audit = await db.scalar(select(AuditLog).where(AuditLog.record_id == first.message_id))
    assert audit.operated_by == scope.user.user_id
    assert audit.factory_id == task.factory_id
    assert audit.changed_fields == {'task_id': str(task.task_id), 'message_id': str(first.message_id),
        'sequence': 2, 'target_capa_id': str(task.target_capa_id)}
    assert '补充证据' not in str(audit.changed_fields)
    assert 'key-1' not in str(audit.changed_fields)
    _, Output = message_schemas()
    assert Output.model_validate(first).model_dump()['content'] == '补充证据'


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['blocked_capability', 'ready', 'paused'])
async def test_local_instructions_work_in_open_states_even_with_plugin_disabled(db, message_context, status):
    task, scope = message_context
    await db.execute(update(AgentTask).where(AgentTask.task_id == task.task_id).values(status=status))
    await db.execute(update(AgentPluginInstallation).where(
        AgentPluginInstallation.installation_id == task.preferred_installation_id).values(enabled=False))
    message = await queue().append_task_message(db, task, scope, 'local instruction', 'open-key')
    assert message.sequence == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['completed', 'failed', 'cancelled'])
async def test_terminal_task_rejects_new_messages_and_retries(db, message_context, status):
    task, scope = message_context
    await queue().append_task_message(db, task, scope, 'original', 'key')
    await db.execute(update(AgentTask).where(AgentTask.task_id == task.task_id).values(status=status))
    before = await counts(db, task.task_id)
    for content, key in [('new', 'new'), ('original', 'key')]:
        with pytest.raises(ValueError, match='^task closed$'):
            await queue().append_task_message(db, task, scope, content, key)
    assert await counts(db, task.task_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('text', ''), ('text', '  '), ('text', 'x'*10001),
    ('text', 123), ('idempotency_key', ''), ('idempotency_key', 'x'*101), ('idempotency_key', 123)])
async def test_service_validates_input_without_side_effects(db, message_context, field, value):
    task, scope = message_context
    fields = dict(text='valid', idempotency_key='key')
    fields[field] = value
    before = await counts(db, task.task_id)
    with pytest.raises(ValueError):
        await queue().append_task_message(db, task, scope, **fields)
    assert await counts(db, task.task_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke', ['user', 'role', 'view', 'factory', 'line'])
async def test_current_access_revocation_blocks_new_messages_and_retries(db, message_context, revoke):
    task, scope = message_context
    if revoke in {'factory', 'line'}:
        await db.execute(update(RoleDefinition).where(RoleDefinition.id == scope.user.role_id)
            .values(bypass_row_level_security=False))
        await db.execute(update(User).where(User.user_id == scope.user.user_id).values(factory_id=None))
        await db.execute(update(RolePermission).where(RolePermission.role_id == scope.user.role_id,
            RolePermission.module == 'group').values(permission_level=0))
        capa = await db.get(CAPAEightD, task.target_capa_id)
        db.add_all([UserFactory(user_id=scope.user.user_id, factory_id=task.factory_id),
            UserProductLine(user_id=scope.user.user_id, product_line_code=capa.product_line_code)])
        await db.flush()
    await queue().append_task_message(db, task, scope, 'original', 'key')
    if revoke == 'user':
        await db.execute(update(User).where(User.user_id == scope.user.user_id).values(is_active=False))
    elif revoke == 'role':
        await db.execute(update(RoleDefinition).where(RoleDefinition.id == scope.user.role_id).values(is_active=False))
    elif revoke == 'view':
        await db.execute(update(RolePermission).where(RolePermission.role_id == scope.user.role_id,
            RolePermission.module == 'capa').values(permission_level=0))
    else:
        model = UserFactory if revoke == 'factory' else UserProductLine
        await db.execute(delete(model).where(model.user_id == scope.user.user_id))
    before = await counts(db, task.task_id)
    expected = LookupError if revoke in {'factory', 'line'} else PermissionError
    for content, key in [('new', 'new'), ('original', 'key')]:
        with pytest.raises(expected):
            await queue().append_task_message(db, task, scope, content, key)
    assert await counts(db, task.task_id) == before


@pytest.mark.asyncio
async def test_other_author_and_foreign_executor_cannot_append_or_view(db, message_context):
    task, scope = message_context
    other = User(user_id=uuid.uuid4(), username=uuid.uuid4().hex, password_hash='fixture',
        role_id=scope.user.role_id, legacy_role='admin', is_active=True, factory_id=scope.user.factory_id)
    db.add(other)
    await db.flush()
    before = await counts(db, task.task_id)
    with pytest.raises(LookupError):
        await queue().append_task_message(db, task, cached_scope(other), 'foreign', 'key')
    with pytest.raises(LookupError):
        await get_task_for_view(db, cached_scope(other), task.task_id)
    await db.execute(update(AgentTask).where(AgentTask.task_id == task.task_id)
        .values(executor_user_id=other.user_id))
    with pytest.raises(LookupError):
        await queue().append_task_message(db, task, scope, 'foreign executor', 'key')
    assert await counts(db, task.task_id) == before


@pytest.mark.asyncio
async def test_missing_task_is_hidden(db, message_context):
    task, scope = message_context
    fake = AgentTask(task_id=uuid.uuid4(), target_capa_id=task.target_capa_id,
        initiator_id=scope.user.user_id, executor_user_id=scope.user.user_id)
    with pytest.raises(LookupError):
        await queue().append_task_message(db, fake, scope, 'missing', 'key')


@pytest.mark.asyncio
async def test_namespace_is_rejected_before_any_business_query_or_autoflush(db, message_context, monkeypatch):
    task, scope = message_context
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    statements = []
    connection = await db.connection()
    event.listen(connection.sync_connection, 'before_cursor_execute',
        lambda conn, cursor, statement, parameters, context, executemany: statements.append(statement))
    # A bad pending write must not flush before the namespace rejection.
    db.add(AgentTaskMessage(task_id=task.task_id, author_id=scope.user.user_id,
        sequence=1, content='bad', sensitivity='restricted', state='queued', idempotency_key='bad'))
    with pytest.raises(PermissionError, match='Business namespace unavailable'):
        await queue().append_task_message(db, task, scope, 'missing namespace', 'key')
    assert statements == []


@pytest.mark.asyncio
async def test_cached_ready_completed_in_other_committed_session_rejects_append(committed_runtime):
    fixture = committed_runtime
    async with fixture.factory(binding=fixture.binding) as cached:
        task = await cached.get(AgentTask, fixture.task_id)
        user = await cached.get(User, fixture.user_id)
        assert task.status == 'ready'
        before = await counts(cached, task.task_id)
        async with fixture.factory(binding=fixture.binding) as writer:
            await writer.execute(update(AgentTask).where(AgentTask.task_id == task.task_id)
                .values(status='completed'))
            await writer.commit()
        assert task.status == 'ready'
        with pytest.raises(ValueError, match='^task closed$'):
            await queue().append_task_message(cached, task, cached_scope(user), 'late', 'late-key')
        await cached.rollback()
    async with fixture.factory(binding=fixture.binding) as verify:
        assert await counts(verify, fixture.task_id) == before


async def concurrent_appends(fixture, requests):
    """Observe two actual database sessions waiting for the same held task row."""
    append = queue().append_task_message
    async with fixture.factory(binding=fixture.binding) as blocker:
        await blocker.scalar(select(AgentTask).where(AgentTask.task_id == fixture.task_id).with_for_update())
        pids = []
        started = asyncio.Event()
        async def append_independently(content, key):
            async with fixture.factory(binding=fixture.binding) as db:
                task = await db.get(AgentTask, fixture.task_id)
                user = await db.get(User, fixture.user_id)
                pids.append(await db.scalar(text('SELECT pg_backend_pid()')))
                if len(pids) == len(requests):
                    started.set()
                message = await append(db, task, cached_scope(user), content, key)
                return message.message_id, message.sequence
        jobs = [asyncio.create_task(append_independently(*request)) for request in requests]
        try:
            await asyncio.wait_for(started.wait(), 10)
            deadline = time.monotonic() + 10
            async with fixture.engine.connect() as observer:
                while True:
                    waits = (await observer.execute(text('SELECT wait_event_type FROM pg_stat_activity WHERE pid = ANY(:pids)'),
                        {'pids': pids})).scalars().all()
                    if waits == ['Lock'] * len(requests):
                        break
                    if time.monotonic() > deadline:
                        pytest.fail(f'appends did not both wait on the task row: {waits}')
                    await asyncio.sleep(.02)
            await blocker.commit()
            return await asyncio.wait_for(asyncio.gather(*jobs, return_exceptions=True), 10)
        finally:
            for job in jobs:
                if not job.done():
                    job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['distinct', 'same', 'conflict'])
async def test_two_committed_sessions_serialize_and_persist_messages(committed_runtime, mode):
    fixture = committed_runtime
    requests = {'distinct': [('one', 'key-1'), ('two', 'key-2')],
        'same': [('one', 'key'), ('one', 'key')],
        'conflict': [('one', 'key'), ('two', 'key')]}[mode]
    results = await concurrent_appends(fixture, requests)
    successes = [result for result in results if not isinstance(result, BaseException)]
    failures = [result for result in results if isinstance(result, BaseException)]
    if mode == 'distinct':
        assert not failures
        assert {seq for _, seq in successes} == {1, 2}
        assert len({message_id for message_id, _ in successes}) == 2
    elif mode == 'same':
        assert not failures
        assert successes[0] == successes[1]
    else:
        assert len(successes) == len(failures) == 1
        assert isinstance(failures[0], ValueError)
        assert 'different content' in str(failures[0])
    async with fixture.factory(binding=fixture.binding) as verify:
        expected = 2 if mode == 'distinct' else 1
        assert await counts(verify, fixture.task_id) == (expected, expected)
        messages = (await verify.scalars(select(AgentTaskMessage).where(
            AgentTaskMessage.task_id == fixture.task_id).order_by(AgentTaskMessage.sequence))).all()
        assert [message.sequence for message in messages] == list(range(1, expected+1))
        assert all(message.state == 'queued' and message.sensitivity == 'restricted' for message in messages)
        user = await verify.get(User, fixture.user_id)
        task = await verify.get(AgentTask, fixture.task_id)
        message = messages[0]
        retry = await queue().append_task_message(verify, task, cached_scope(user), message.content, message.idempotency_key)
        assert retry.message_id == message.message_id
        assert await counts(verify, fixture.task_id) == (expected, expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["view", "terminal", "namespace"])
async def test_access_and_state_are_rechecked_after_waiting_for_task_lock(committed_runtime, change):
    fixture = committed_runtime
    async with fixture.factory(binding=fixture.binding) as blocker:
        await blocker.scalar(select(AgentTask).where(AgentTask.task_id == fixture.task_id).with_for_update())
        async with fixture.factory(binding=fixture.binding) as appender:
            task = await appender.get(AgentTask, fixture.task_id)
            user = await appender.get(User, fixture.user_id)
            pid = await appender.scalar(text('SELECT pg_backend_pid()'))
            before = await counts(appender, task.task_id)
            job = asyncio.create_task(queue().append_task_message(appender, task, cached_scope(user), 'after revoke', 'key'))
            try:
                deadline = time.monotonic() + 10
                async with fixture.engine.connect() as observer:
                    while await observer.scalar(text('SELECT wait_event_type FROM pg_stat_activity WHERE pid=:pid'), {'pid': pid}) != 'Lock':
                        if time.monotonic() > deadline:
                            pytest.fail('append never waited on task row')
                        await asyncio.sleep(.02)
                # Admission was valid before the wait; change it while holding the row.
                if change == "view":
                    await blocker.execute(update(RolePermission).where(RolePermission.role_id == fixture.role_id,
                        RolePermission.module == 'capa').values(permission_level=0))
                elif change == "terminal":
                    await blocker.execute(update(AgentTask).where(AgentTask.task_id == fixture.task_id)
                        .values(status="completed"))
                else:
                    await blocker.execute(text("UPDATE public.tenants SET status='suspended' WHERE id=:id"),
                        {"id": fixture.binding.tenant_id})
                await blocker.commit()
                expected = ValueError if change == "terminal" else PermissionError
                with pytest.raises(expected):
                    await asyncio.wait_for(job, 10)
                if change == "namespace":
                    await appender.rollback()
                    async with fixture.engine.begin() as restore:
                        await restore.execute(text("UPDATE public.tenants SET status='active' WHERE id=:id"),
                            {"id": fixture.binding.tenant_id})
                assert await counts(appender, fixture.task_id) == before
            finally:
                if not job.done():
                    job.cancel()
                await asyncio.gather(job, return_exceptions=True)
