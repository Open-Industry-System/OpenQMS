"""Receipt-bound readonly output writes and current-authority historical reads."""
import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant
from app.models.agent_runtime_event import AgentProjectionReceipt, AgentRunEvent, AgentResult, AgentEventReceipt, AgentResultReceipt
from app.models.audit import AuditLog
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.factory import UserFactory
from app.models.user import User
from app.services.agent_runtime import readonly_delivery, runtime_access
from tests.services.agent_runtime.test_readonly_delivery import context_delivery, context
from tests.services.agent_runtime.test_runtime_messages import delivery
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned


def schemas():
    import app.schemas.agent_runtime as mod
    assert hasattr(mod, 'RuntimeResultCreate'), 'bounded readonly output schemas missing'
    return mod


def result_body(receipts, key='result'):
    return dict(idempotency_key=key, receipt_ids=receipts, payload={
        'explanations': ['RESTRICTED EXPLANATION'], 'support': ['RESTRICTED SUPPORT'],
        'opposition': [], 'missing_information': ['RESTRICTED MISSING'],
        'conditional_recommendations': ['RESTRICTED RECOMMENDATION']})


def event_body(receipts, key='event', kind='query_completed'):
    return dict(idempotency_key=key, event_type=kind,
        payload={'stage': 'D4', 'message': 'RESTRICTED PROGRESS', 'completed': 1, 'total': 2}, receipt_ids=receipts)


async def write(owned, body, event=False):
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        operation = getattr(readonly_delivery, 'record_event' if event else 'save_result', None)
        assert operation is not None, 'receipt-bound readonly writes missing'
        return await operation(db, identity, body)


async def read(owned, result_id, task_id=None):
    async with owned.factory(binding=owned.binding) as db:
        from app.core.deps import RequestScope
        from app.core.factory_scope import FactoryScope, ProductLineScope
        user = await db.get(User, owned.user_id)
        scope = RequestScope(FactoryScope([], None), None, ProductLineScope('NONE', []), user)
        operation = getattr(readonly_delivery, 'get_result_for_view', None)
        assert operation is not None, 'controlled historical result read missing'
        return await operation(db, scope, task_id or owned.task_id, uuid.UUID(str(result_id)))


async def counts(owned):
    async with owned.factory(binding=owned.binding) as db:
        return tuple([await db.scalar(select(func.count()).select_from(model))
            for model in (AgentRunEvent, AgentResult, AgentEventReceipt, AgentResultReceipt)])


def test_output_dtos_bound_typed_content_and_forbid_asserted_identity():
    mod = schemas()
    for cls, body in ((mod.RuntimeResultCreate, result_body([uuid.uuid4()])),
                      (mod.RuntimeEventCreate, event_body([uuid.uuid4()]))):
        assert cls.model_validate(body)
        for field in ('actor_id', 'data_class', 'projection_id', 'projection_digest', 'source_capa_id', 'run_id'):
            with pytest.raises(ValidationError):
                cls.model_validate({**body, field: 'spoof'})
        for changes in ({'idempotency_key': ''}, {'idempotency_key': 'x'*101},
                        {'receipt_ids': [uuid.uuid4() for _ in range(21)]}, {'receipt_ids': ['bad']}):
            with pytest.raises(ValidationError):
                cls.model_validate({**body, **changes})
        with pytest.raises(ValidationError):
            cls.model_validate({**body, 'payload': {**body['payload'], 'unbounded': 'bad'}})
    for payload in ({'explanations': ['x'*2001]}, {'support': ['x']*21}, {'support': [123]}, {'explanations': 'bad'}):
        with pytest.raises(ValidationError):
            mod.RuntimeResultCreate.model_validate({**result_body([uuid.uuid4()]), 'payload': payload})
    with pytest.raises(ValidationError):
        mod.RuntimeResultCreate.model_validate(result_body([]))
    with pytest.raises(ValidationError):
        mod.RuntimeEventCreate.model_validate(event_body([]))
    assert mod.RuntimeEventCreate.model_validate(event_body([], kind='progress'))
    for payload in ({'message': 'x'*1001}, {'completed': True}, {'completed': -1}, {'stage': 7}):
        with pytest.raises(ValidationError):
            mod.RuntimeEventCreate.model_validate({**event_body([], kind='progress'), 'payload': payload})


@pytest.mark.asyncio
async def test_plural_sources_idempotency_durable_rows_safe_audit(context_delivery):
    owned = context_delivery
    receipts = [(await context(owned))['receipt_id'], (await context(owned, view='verifications'))['receipt_id']]
    for is_event, body, idfield in ((False, result_body(receipts), 'result_id'), (True, event_body(receipts), 'event_id')):
        first = await write(owned, body, is_event)
        duplicate = await write(owned, {**body, 'receipt_ids': receipts[::-1]+receipts[:1]}, is_event)
        assert first == duplicate
        assert len(first['sources']) == 2
        assert all(s['data_class'] == 'internal' for s in first['sources'])
        if not is_event:
            assert first['data_class'] == 'restricted'
            assert (await read(owned, first[idfield])) == first
        with pytest.raises(ValueError):
            await write(owned, {**body, 'receipt_ids': receipts[:1]}, is_event)
        changed = {**body['payload'], 'message': 'DIFFERENT'} if is_event else {**body['payload'], 'support': ['DIFFERENT']}
        with pytest.raises(ValueError):
            await write(owned, {**body, 'payload': changed}, is_event)
    assert await counts(owned) == (1, 1, 2, 2)
    async with owned.factory(binding=owned.binding) as db:
        audits = list((await db.scalars(select(AuditLog).where(AuditLog.action.in_(['RECORD_AGENT_RUN_EVENT', 'SAVE_AGENT_RESULT'])))).all())
        assert len(audits) == 2
        assert 'RESTRICTED' not in json.dumps([a.changed_fields for a in audits])
        assert all(a.old_values is None and a.new_values is None for a in audits)
        assert all(a.correlation_id == owned.run_id and a.operated_by == owned.user_id for a in audits)


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['unknown', 'crossrun', 'task', 'epoch', 'generation', 'source', 'projection', 'digest', 'class'])
async def test_unknown_stale_or_unrecognized_source_denies_without_writes(context_delivery, mutation):
    owned = context_delivery
    receipt_id = uuid.UUID((await context(owned))['receipt_id'])
    async with owned.factory(binding=owned.binding) as db:
        row = await db.get(AgentProjectionReceipt, receipt_id)
        if mutation == 'unknown':
            receipt_id = uuid.uuid4()
        elif mutation == 'crossrun':
            run = await db.get(AgentRun, owned.run_id)
            other = AgentRun(task_id=run.task_id, installation_id=run.installation_id, plugin_version=run.plugin_version,
                status='completed', lease_epoch=1)
            db.add(other)
            await db.flush()
            row.run_id = other.run_id
        elif mutation == 'task':
            task = await db.get(AgentTask, owned.task_id)
            other = AgentTask(initiator_id=task.initiator_id, executor_user_id=task.executor_user_id,
                preferred_installation_id=task.preferred_installation_id, target_capa_id=task.target_capa_id,
                factory_id=task.factory_id, request_key=uuid.uuid4().hex, status='ready')
            db.add(other)
            await db.flush()
            row.task_id = other.task_id
        elif mutation == 'class':
            # Deliberate fixture-only corruption demonstrates fail closed even
            # when legacy/persisted metadata escapes the schema check.
            from sqlalchemy import text
            await db.execute(text('ALTER TABLE agent_projection_receipts DROP CONSTRAINT ck_agent_receipt_data_class'))
            row.data_class = 'public'
        else:
            values = {'epoch': ('lease_epoch', 0), 'generation': ('tenant_generation', owned.binding.generation+1),
                'source': ('source_capa_id', None), 'projection': ('projection_id', 'unknown.v1'),
                'digest': ('projection_digest', 'a'*63)}
            name, value = values[mutation]
            if mutation == 'source':
                from app.models.capa import CAPAEightD
                other = CAPAEightD(document_no='8D-OTHER', title='OTHER', factory_id=owned.factory_id, product_line_code='DC-DC-100')
                db.add(other)
                await db.flush()
                value = other.report_id
            setattr(row, name, value)
        await db.commit()
    for is_event in (False, True):
        body = event_body([receipt_id]) if is_event else result_body([receipt_id])
        with pytest.raises(PermissionError):
            await write(owned, body, is_event)
    assert await counts(owned) == (0, 0, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['plugin', 'plugin_grant', 'task_grant', 'role', 'permission', 'trust', 'canonical'])
async def test_revocation_precedes_idempotent_return(context_delivery, monkeypatch, change):
    owned = context_delivery
    receipts = [(await context(owned))['receipt_id']]
    await write(owned, result_body(receipts))
    await write(owned, event_body(receipts), True)
    async with owned.factory(binding=owned.binding) as db:
        if change == 'trust':
            monkeypatch.setattr(runtime_access, 'TRUSTED_DELIVERY_DEPLOYMENTS', frozenset())
        elif change == 'canonical':
            from app.services.agent.permissions import catalog
            from app.services.agent.permissions.types import ApprovalFloor
            from dataclasses import replace
            from types import MappingProxyType
            monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', MappingProxyType({k: replace(v, approval_floor=ApprovalFloor.DENY) for k,v in catalog.CAPA_CAPABILITIES.items()}))
        else:
            changes = {'plugin': update(AgentPluginInstallation).values(enabled=False),
                'plugin_grant': update(AgentPluginGrant).values(enabled=False), 'task_grant': delete(AgentTaskGrant),
                'role': update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(is_active=False),
                'permission': update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == 'capa').values(permission_level=0)}
            await db.execute(changes[change])
            await db.commit()
    for is_event in (False, True):
        with pytest.raises(PermissionError):
            await write(owned, event_body(receipts) if is_event else result_body(receipts), is_event)
    assert await counts(owned) == (1, 1, 1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('event', [False, True])
async def test_real_concurrent_equal_writes_and_conflicting_key(context_delivery, event):
    owned = context_delivery
    receipts = [(await context(owned))['receipt_id']]
    body = event_body(receipts) if event else result_body(receipts)
    results = await asyncio.wait_for(asyncio.gather(write(owned, body, event), write(owned, body, event)), 15)
    assert results[0] == results[1]
    different = {**body, 'payload': {'message': 'changed'} if event else {'support': ['changed']}}
    result = await asyncio.gather(write(owned, body, event), write(owned, different, event), return_exceptions=True)
    assert isinstance(result[1], ValueError)
    assert (await counts(owned))[:2] == ((1,0) if event else (0,1))
    async with owned.factory(binding=owned.binding) as db:
        action = 'RECORD_AGENT_RUN_EVENT' if event else 'SAVE_AGENT_RESULT'
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action)) == 1


@pytest.mark.asyncio
async def test_history_survives_completed_run_disabled_plugin_but_checks_current_sources(context_delivery):
    owned = context_delivery
    receipts = [(await context(owned))['receipt_id'], (await context(owned))['receipt_id']]
    result = await write(owned, result_body(receipts))
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentRun).values(status='completed', lease_expires_at=datetime.now(UTC)-timedelta(days=1)))
        await db.execute(update(AgentPluginInstallation).values(enabled=False))
        await db.execute(delete(AgentTaskGrant))
        await db.commit()
    assert await read(owned, result['result_id']) == result
    with pytest.raises(LookupError):
        await read(owned, result['result_id'], uuid.uuid4())
    async with owned.factory(binding=owned.binding) as db:
        # Every plural source is checked, not just the first receipt.
        await db.execute(update(AgentProjectionReceipt).where(AgentProjectionReceipt.receipt_id == uuid.UUID(receipts[1])).values(projection_id='unknown'))
        await db.commit()
    with pytest.raises(PermissionError):
        await read(owned, result['result_id'])


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['role', 'permission', 'factory', 'product_line', 'foreignuser', 'missing_sources'])
async def test_user_revocation_blocks_stored_content(context_delivery, change):
    owned = context_delivery
    result = await write(owned, result_body([(await context(owned))['receipt_id']]))
    async with owned.factory(binding=owned.binding) as db:
        if change in ('factory', 'product_line'):
            await db.execute(delete(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == 'group'))
            await db.execute(update(User).where(User.user_id == owned.user_id).values(factory_id=None))
            if change == 'product_line':
                await db.execute(update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(bypass_row_level_security=False))
            await db.execute(delete(UserFactory).where(UserFactory.user_id == owned.user_id))
            if change == 'product_line':
                db.add(UserFactory(user_id=owned.user_id, factory_id=owned.factory_id))
                await db.execute(delete(UserProductLine).where(UserProductLine.user_id == owned.user_id))
                db.add(UserProductLine(user_id=owned.user_id, product_line_code='DC-DC-100'))
                await db.flush()
                await db.execute(delete(UserProductLine).where(UserProductLine.user_id == owned.user_id))
        else:
            changes = {'role': update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(is_active=False),
                'permission': update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == 'capa').values(permission_level=0),
                'foreignuser': update(AgentTask).values(initiator_id=None),
                'missing_sources': delete(AgentResultReceipt)}
            if change == 'foreignuser':
                user = User(email='other@example.test', username='other', password_hash='fixture', role_id=owned.role_id, legacy_role='viewer')
                db.add(user)
                await db.flush()
                await db.execute(update(AgentTask).values(initiator_id=user.user_id))
            else:
                await db.execute(changes[change])
        await db.commit()
    with pytest.raises((PermissionError, LookupError)):
        await read(owned, result['result_id'])


@pytest.mark.asyncio
async def test_plural_association_has_real_foreign_keys(context_delivery):
    owned = context_delivery
    async with owned.factory(binding=owned.binding) as db:
        db.add(AgentResultReceipt(result_id=uuid.uuid4(), receipt_id=uuid.uuid4()))
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
        db.add(AgentEventReceipt(event_id=uuid.uuid4(), receipt_id=uuid.uuid4()))
        with pytest.raises(IntegrityError):
            await db.flush()


@pytest.mark.asyncio
async def test_history_preserves_saved_generation_and_epoch_after_tenant_maintenance(context_delivery, monkeypatch):
    from dataclasses import replace
    from sqlalchemy import text
    from app.services.agent_runtime import runtime_access
    from app.services.agent.permissions import catalog
    from app.services.agent.permissions.types import ApprovalFloor
    from types import MappingProxyType

    owned = context_delivery
    result = await write(owned, result_body([(await context(owned))['receipt_id']]))
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentRun).values(status='completed', lease_epoch=2))
        await db.execute(update(AgentPluginInstallation).values(enabled=False))
        await db.commit()
    async with owned.engine.begin() as conn:
        await conn.execute(text('UPDATE public.tenants SET generation=generation+1 WHERE id=:id'), {'id': owned.binding.tenant_id})
    owned.binding = replace(owned.binding, generation=owned.binding.generation+1)
    # Historical user view survives removal of plugin delivery authorization.
    monkeypatch.setattr(runtime_access, 'TRUSTED_DELIVERY_DEPLOYMENTS', frozenset())
    monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', MappingProxyType({k: replace(v, approval_floor=ApprovalFloor.DENY) for k,v in catalog.CAPA_CAPABILITIES.items()}))
    assert await read(owned, result['result_id']) == result


@pytest.mark.asyncio
@pytest.mark.parametrize('event', [False, True])
@pytest.mark.parametrize('duplicate', [False, True])
async def test_final_authority_after_receipt_read_before_new_or_duplicate_reply(context_delivery, event, duplicate):
    from sqlalchemy import event as sql_event
    from sqlalchemy.util import await_only

    owned = context_delivery
    body = event_body([(await context(owned))['receipt_id']]) if event else result_body([(await context(owned))['receipt_id']])
    if duplicate:
        await write(owned, body, event)
    reached, release = asyncio.Event(), asyncio.Event()
    async def pause():
        reached.set()
        await release.wait()
    def intercept(conn, cursor, statement, parameters, ctx, many):
        if 'FROM agent_projection_receipts' in statement:
            await_only(pause())
    sql_event.listen(owned.engine.sync_engine, 'after_cursor_execute', intercept)
    future = asyncio.create_task(write(owned, body, event))
    try:
        await asyncio.wait_for(reached.wait(), 10)
        async with owned.factory(binding=owned.binding) as revoker:
            await revoker.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id,
                RolePermission.module == 'capa').values(permission_level=0))
            await revoker.commit()
        release.set()
        with pytest.raises(PermissionError):
            await asyncio.wait_for(future, 10)
    finally:
        release.set()
        await asyncio.gather(future, return_exceptions=True)
        sql_event.remove(owned.engine.sync_engine, 'after_cursor_execute', intercept)
    assert (await counts(owned))[:2] == ((1,0) if event and duplicate else (0,1) if duplicate else (0,0))


@pytest.mark.asyncio
@pytest.mark.parametrize('is_event', [False, True])
async def test_audit_failure_rolls_back_output_and_associations(context_delivery, is_event):
    from sqlalchemy import event
    owned = context_delivery
    receipts = [(await context(owned))['receipt_id']]
    inserts = []
    def fail_audit(conn, cursor, statement, params, ctx, many):
        if statement.startswith('INSERT'):
            inserts.append(statement)
        if statement.startswith('INSERT INTO audit_logs'):
            raise RuntimeError('fixture audit failure')
    event.listen(owned.engine.sync_engine, 'before_cursor_execute', fail_audit)
    try:
        with pytest.raises(RuntimeError, match='fixture audit failure'):
            await write(owned, event_body(receipts) if is_event else result_body(receipts), is_event)
    finally:
        event.remove(owned.engine.sync_engine, 'before_cursor_execute', fail_audit)
    assert any(('agent_run_events' if is_event else 'agent_results') in sql for sql in inserts)
    assert await counts(owned) == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_unrelated_integrity_error_is_not_idempotency_reply(context_delivery):
    owned = context_delivery
    body = result_body([(await context(owned))['receipt_id']])
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        db.add(AgentResultReceipt(result_id=uuid.uuid4(), receipt_id=uuid.uuid4()))
        with pytest.raises(IntegrityError):
            await readonly_delivery.save_result(db, identity, body)
    assert await counts(owned) == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_progress_without_receipts_is_bounded_idempotent_and_not_a_result_source(context_delivery):
    owned = context_delivery
    first = await write(owned, event_body([], kind='progress'), True)
    assert first['sources'] == []
    assert await write(owned, event_body([], kind='progress'), True) == first
    with pytest.raises(PermissionError):
        await write(owned, result_body([first['event_id']]))
    assert await counts(owned) == (1, 0, 0, 0)


@pytest.mark.asyncio
async def test_history_final_task_target_association_rechecked_after_source_read(context_delivery):
    from app.models.capa import CAPAEightD
    from sqlalchemy import event
    from sqlalchemy.util import await_only
    owned = context_delivery
    result = await write(owned, result_body([(await context(owned))['receipt_id']]))
    async with owned.factory(binding=owned.binding) as db:
        target = await db.get(CAPAEightD, owned.report_id)
        other = CAPAEightD(document_no='8D-MOVED', title='OTHER', factory_id=target.factory_id, product_line_code=target.product_line_code)
        db.add(other)
        await db.commit()
        other_id = other.report_id
    reached, release = asyncio.Event(), asyncio.Event()
    async def pause():
        reached.set()
        await release.wait()
    def intercept(conn, cursor, statement, parameters, ctx, many):
        if 'FROM agent_projection_receipts' in statement:
            await_only(pause())
    event.listen(owned.engine.sync_engine, 'after_cursor_execute', intercept)
    future = asyncio.create_task(read(owned, result['result_id']))
    try:
        await asyncio.wait_for(reached.wait(), 10)
        async with owned.factory(binding=owned.binding) as writer:
            await writer.execute(update(AgentTask).where(AgentTask.task_id == owned.task_id).values(target_capa_id=other_id))
            await writer.commit()
        release.set()
        with pytest.raises(PermissionError):
            await asyncio.wait_for(future, 10)
    finally:
        release.set()
        await asyncio.gather(future, return_exceptions=True)
        event.remove(owned.engine.sync_engine, 'after_cursor_execute', intercept)
