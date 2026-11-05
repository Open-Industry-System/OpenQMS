"""Task creation uses current database admission facts, never cached request scopes."""
import asyncio
import uuid
from dataclasses import replace
from types import MappingProxyType

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text, update

from app.config import settings
from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.models.agent_plugin import AgentPluginGrant
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant, AgentTaskMessage
from app.models.audit import AuditLog
from app.models.capa import CAPAEightD
from app.models.factory import Factory, UserFactory
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition, RolePermission, UserProductLine
from app.models.user import User
from app.services.agent.permissions import catalog
from app.services.agent.permissions.types import ApprovalFloor

SUMMARY = 'capa.d4.summary.masked.v1'


def service():
    try:
        from app.services.agent_runtime import task_service
    except ImportError:
        pytest.fail('task service is not implemented')
    return task_service


@pytest_asyncio.fixture
async def scope(db, admin_user, default_factory, monkeypatch):
    monkeypatch.setattr(settings, 'TENANT_MODE', 'single')
    return RequestScope(FactoryScope([default_factory.id], default_factory.id),
        default_factory.id, ProductLineScope('ALL', None), admin_user)

@pytest.fixture
def direct_summary(monkeypatch):
    spec = replace(catalog.get_capability(SUMMARY), approval_floor=ApprovalFloor.DIRECT)
    monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', MappingProxyType({
        **catalog.CAPA_CAPABILITIES, SUMMARY: spec}))
    return spec


async def add_grant(db, scope, capa, plugin, **changes):
    fields = dict(grant_id=uuid.uuid4(), installation_id=plugin.installation_id,
        capability_id=SUMMARY, enabled=True, factory_ids=[str(capa.factory_id)],
        product_line_codes=[capa.product_line_code], object_ids=[str(capa.report_id)],
        granted_by=scope.user.user_id)
    fields.update(changes)
    grant = AgentPluginGrant(**fields)
    db.add(grant)
    await db.flush()
    return grant


async def create(db, scope, capa, plugin, key=None, message='调查'):
    return await service().create_task(db, scope, capa.report_id, plugin.installation_id,
        key or uuid.uuid4().hex, message)


def test_task_dto_forbids_caller_identity_and_bounds_text():
    try:
        from app.schemas.agent_task import TaskCreate
    except ImportError:
        pytest.fail('task schemas are not implemented')
    fields = dict(report_id=uuid.uuid4(), installation_id=uuid.uuid4(),
        request_key='key', initial_text='调查')
    assert TaskCreate(**fields).initial_text == '调查'
    for key in ['user', 'actor', 'executor_user_id', 'scope', 'factory_id']:
        with pytest.raises(ValidationError):
            TaskCreate(**fields, **{key: 'untrusted'})
    for field, value in [('request_key', 'x'*101), ('initial_text', 'x'*10001)]:
        with pytest.raises(ValidationError):
            TaskCreate(**{**fields, field: value})


@pytest.mark.asyncio
async def test_default_deny_is_durable_blocked_task(db, scope, sample_capa, enabled_plugin):
    task = await create(db, scope, sample_capa, enabled_plugin)
    assert task.status == 'blocked_capability'
    assert (task.initiator_id, task.executor_user_id) == (scope.user.user_id,)*2
    assert (task.target_capa_id, task.factory_id) == (sample_capa.report_id, sample_capa.factory_id)
    assert await db.scalar(select(func.count()).select_from(AgentRun)) == 0
    assert await db.scalar(select(func.count()).select_from(AgentTaskGrant)) == 0
    message = await db.scalar(select(AgentTaskMessage))
    assert (message.sequence, message.sensitivity, message.idempotency_key, message.state) == (
        1, 'restricted', task.request_key, 'queued')
    audit = await db.scalar(select(AuditLog).where(AuditLog.record_id == task.task_id))
    assert audit.operated_by == scope.user.user_id
    assert '调查' not in str(audit.changed_fields)
    assert sample_capa.status == 'D1_TEAM'


@pytest.mark.asyncio
@pytest.mark.parametrize('field,values', [
    ('factory_ids', [str(uuid.uuid4())]), ('product_line_codes', ['wrong-line']),
    ('object_ids', [str(uuid.uuid4())]), ('object_ids', []), ('enabled', False),
])
async def test_required_grant_must_cover_target(db, scope, sample_capa, enabled_plugin,
                                             direct_summary, field, values):
    await add_grant(db, scope, sample_capa, enabled_plugin, **{field: values})
    task = await create(db, scope, sample_capa, enabled_plugin)
    assert task.status == 'blocked_capability'
    assert await db.scalar(select(func.count()).select_from(AgentRun)) == 0


@pytest.mark.asyncio
async def test_direct_target_grant_is_minimum_scope_pending_run(db, scope, sample_capa,
                                                             enabled_plugin, direct_summary):
    await add_grant(db, scope, sample_capa, enabled_plugin, object_ids=None,
        product_line_codes=None)
    task = await create(db, scope, sample_capa, enabled_plugin)
    assert task.status == 'ready'
    grant = await db.scalar(select(AgentTaskGrant).where(AgentTaskGrant.task_id == task.task_id))
    assert grant.factory_ids == [str(sample_capa.factory_id)]
    assert grant.product_line_codes == [sample_capa.product_line_code]
    assert grant.object_ids == [str(sample_capa.report_id)]
    assert grant.access_kind == 'read'
    run = await db.scalar(select(AgentRun).where(AgentRun.task_id == task.task_id))
    assert (run.status, run.plugin_version, run.lease_epoch, run.accepted_message_seq) == (
        'pending', enabled_plugin.plugin_version, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('required', [[], [SUMMARY, 'capa.unknown.v1'],
    [SUMMARY, 'capa.d4.candidate.propose.v1']])
async def test_every_required_capability_is_needed_even_with_optional_summary(
    db, scope, sample_capa, enabled_plugin, direct_summary, required,
):
    enabled_plugin.manifest = dict(protocol_versions=['1'], required_capabilities=required,
        optional_capabilities=[SUMMARY])
    await add_grant(db, scope, sample_capa, enabled_plugin)
    task = await create(db, scope, sample_capa, enabled_plugin)
    assert task.status == 'blocked_capability'
    assert await db.scalar(select(func.count()).select_from(AgentRun)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke', ['permission', 'user', 'role'])
async def test_current_permission_loss_blocks_create_retry_detail_count(
    db, scope, sample_capa, enabled_plugin, revoke,
):
    task = await create(db, scope, sample_capa, enabled_plugin)
    if revoke == 'permission':
        await db.execute(update(RolePermission).where(RolePermission.role_id == scope.user.role_id,
            RolePermission.module == 'capa').values(permission_level=0))
    elif revoke == 'user':
        await db.execute(update(User).where(User.user_id == scope.user.user_id).values(is_active=False))
    else:
        await db.execute(update(RoleDefinition).where(RoleDefinition.id == scope.user.role_id)
            .values(is_active=False))
    for operation in [create(db, scope, sample_capa, enabled_plugin, task.request_key),
        service().require_current_capa_view(db, scope, sample_capa.report_id),
        service().get_task_for_view(db, scope, task.task_id),
        service().list_for_initiator(db, scope, 1, 20)]:
        with pytest.raises(PermissionError):
            await operation


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke', ['factory', 'line'])
async def test_current_membership_loss_hides_detail_and_count(db, scope, sample_capa,
                                                           enabled_plugin, revoke):
    role = await db.get(RoleDefinition, scope.user.role_id)
    role.bypass_row_level_security = False
    scope.user.factory_id = None
    db.add(UserFactory(user_id=scope.user.user_id, factory_id=sample_capa.factory_id))
    db.add(UserProductLine(user_id=scope.user.user_id, product_line_code=sample_capa.product_line_code))
    await db.flush()
    task = await create(db, scope, sample_capa, enabled_plugin)
    model = UserFactory if revoke == 'factory' else UserProductLine
    await db.execute(delete(model).where(model.user_id == scope.user.user_id))
    # Admin GROUP ADMIN must be revoked as well to make factory memberships binding.
    await db.execute(update(RolePermission).where(RolePermission.role_id == scope.user.role_id,
        RolePermission.module == 'group').values(permission_level=0))
    with pytest.raises(LookupError):
        await service().get_task_for_view(db, scope, task.task_id)
    with pytest.raises(LookupError):
        await create(db, scope, sample_capa, enabled_plugin, task.request_key)
    result = await service().list_for_initiator(db, scope, 1, 20)
    assert result == dict(items=[], total=0, page=1, page_size=20)


@pytest.mark.asyncio
async def test_selected_factory_does_not_narrow_authorized_target(db, scope, sample_capa,
                                                               enabled_plugin):
    await db.execute(update(RolePermission).where(RolePermission.role_id == scope.user.role_id,
        RolePermission.module == 'group').values(permission_level=0))
    other = Factory(id=uuid.uuid4(), code=uuid.uuid4().hex[:12], name='Other')
    db.add(other)
    await db.flush()
    db.add_all([UserFactory(user_id=scope.user.user_id, factory_id=other.id),
        UserFactory(user_id=scope.user.user_id, factory_id=sample_capa.factory_id)])
    await db.flush()
    scope.effective_factory_id = other.id
    scope.factory_scope = FactoryScope([other.id], other.id)  # stale UI cache
    task = await create(db, scope, sample_capa, enabled_plugin)
    assert task.factory_id == sample_capa.factory_id
    assert (await service().list_for_initiator(db, scope, 1, 20))['total'] == 1


@pytest.mark.asyncio
async def test_missing_wrong_factory_and_foreign_executor_are_hidden(db, scope, sample_capa,
                                                                  enabled_plugin):
    with pytest.raises(LookupError):
        await service().require_current_capa_view(db, scope, uuid.uuid4())
    task = await create(db, scope, sample_capa, enabled_plugin)
    other = User(user_id=uuid.uuid4(), username=uuid.uuid4().hex, password_hash='fixture',
        role_id=scope.user.role_id, legacy_role='admin', is_active=True, factory_id=scope.user.factory_id)
    db.add(other)
    await db.flush()
    task.executor_user_id = other.user_id
    await db.flush()
    with pytest.raises(LookupError):
        await service().get_task_for_view(db, scope, task.task_id)
    assert (await service().list_for_initiator(db, scope, 1, 20))['total'] == 0
    await db.execute(update(RolePermission).where(RolePermission.role_id == scope.user.role_id,
        RolePermission.module == 'group').values(permission_level=0))
    other_factory = Factory(id=uuid.uuid4(), code=uuid.uuid4().hex[:12], name='Hidden')
    db.add(other_factory)
    await db.flush()
    hidden = CAPAEightD(document_no='8D-HIDDEN-'+uuid.uuid4().hex[:8], title='Hidden',
        factory_id=other_factory.id, product_line_code=sample_capa.product_line_code)
    db.add(hidden)
    await db.flush()
    with pytest.raises(LookupError):
        await service().require_current_capa_view(db, scope, hidden.report_id)

@pytest.mark.asyncio
async def test_idempotent_create_conflict_and_disabled_retry(db, scope, sample_capa, enabled_plugin):
    first = await create(db, scope, sample_capa, enabled_plugin, 'same')
    second = await create(db, scope, sample_capa, enabled_plugin, 'same')
    assert first.task_id == second.task_id
    assert await db.scalar(select(func.count()).select_from(AgentTaskMessage)) == 1
    assert await db.scalar(select(func.count()).select_from(AuditLog).where(
        AuditLog.table_name == 'agent_tasks')) == 1
    with pytest.raises(ValueError):
        await create(db, scope, sample_capa, enabled_plugin, 'same', 'different')
    enabled_plugin.enabled = False
    await db.flush()
    with pytest.raises(PermissionError):
        await create(db, scope, sample_capa, enabled_plugin, 'same')


@pytest.mark.asyncio
async def test_manifest_is_strict_even_on_retry(db, scope, sample_capa, enabled_plugin):
    task = await create(db, scope, sample_capa, enabled_plugin)
    enabled_plugin.manifest = {'protocol_versions': ['1'], 'executor': str(scope.user.user_id)}
    await db.flush()
    with pytest.raises(ValueError):
        await create(db, scope, sample_capa, enabled_plugin, task.request_key)


@pytest.mark.asyncio
async def test_multitenant_plain_session_fails_before_identity_sql(db, scope, monkeypatch):
    from sqlalchemy import event
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    statements = []
    connection = await db.connection()
    event.listen(connection.sync_connection, 'before_cursor_execute',
        lambda conn, cursor, statement, parameters, context, executemany: statements.append(statement))
    with pytest.raises(PermissionError):
        await service().require_current_capa_view(db, scope, uuid.uuid4())
    assert not statements


@pytest.mark.asyncio
async def test_single_rebinds_public_before_business_reads(db, scope, sample_capa):
    await db.execute(text('SET LOCAL search_path TO pg_catalog'))
    target = await service().require_current_capa_view(db, scope, sample_capa.report_id)
    assert target.report_id == sample_capa.report_id
    assert await db.scalar(text('SHOW search_path')) == 'public, pg_catalog'


@pytest.mark.asyncio
async def test_real_committed_concurrent_create_is_durable_and_unique(
    committed_runtime, direct_summary, monkeypatch,
):
    fixture = committed_runtime
    async with fixture.factory(binding=fixture.binding) as db:
        user = await db.get(User, fixture.user_id)
        existing = await db.get(AgentTask, fixture.task_id)
        from app.models.agent_plugin import AgentPluginInstallation
        plugin = await db.get(AgentPluginInstallation, fixture.plugin_id)
        plugin.manifest = dict(protocol_versions=['1'], required_capabilities=[SUMMARY])
        target = await db.get(CAPAEightD, existing.target_capa_id)
        grant_scope = RequestScope(FactoryScope([], None), None, ProductLineScope('NONE', None), user)
        await add_grant(db, grant_scope, target, plugin)
        await db.commit()
        target_id, factory_id = existing.target_capa_id, existing.factory_id
    key = uuid.uuid4().hex
    # Both sessions must finish their first absence query before either inserts.
    original_existing = service()._existing
    both_absent = asyncio.Event()
    absent_count = 0
    async def simultaneous_absence(*args):
        nonlocal absent_count
        result = await original_existing(*args)
        if result is None:
            absent_count += 1
            if absent_count == 2:
                both_absent.set()
            await both_absent.wait()
        return result
    monkeypatch.setattr(service(), '_existing', simultaneous_absence)
    async def create_independently():
        async with fixture.factory(binding=fixture.binding) as db:
            # Intentionally cached user and bogus scope grants, service resolves current DB facts.
            scope = RequestScope(FactoryScope([], None), None, ProductLineScope('NONE', None), user)
            task = await service().create_task(db, scope, target_id, fixture.plugin_id, key, 'private text')
            return task.task_id
    results = await asyncio.wait_for(asyncio.gather(create_independently(), create_independently()), 20)
    assert results[0] == results[1]
    async with fixture.factory(binding=fixture.binding) as db:
        task = await db.get(AgentTask, results[0])
        assert task.status == 'ready'
        assert task.factory_id == factory_id
        assert await db.scalar(select(func.count()).select_from(AgentTaskMessage).where(
            AgentTaskMessage.task_id == task.task_id)) == 1
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.record_id == task.task_id)) == 1
        assert await db.scalar(select(func.count()).select_from(AgentRun).where(
            AgentRun.task_id == task.task_id)) == 1
        run = await db.scalar(select(AgentRun).where(AgentRun.task_id == task.task_id))
        assert (run.status, run.lease_epoch, run.accepted_message_seq) == ('pending', 0, 0)
        await db.execute(update(RolePermission).where(RolePermission.role_id == fixture.role_id,
            RolePermission.module == 'capa').values(permission_level=0))
        await db.commit()
    async with fixture.factory(binding=fixture.binding) as db:
        scope = RequestScope(FactoryScope(None, factory_id), None, ProductLineScope('ALL', None), user)
        with pytest.raises(PermissionError):
            await service().create_task(db, scope, target_id, fixture.plugin_id, key, 'private text')

@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['paused', 'generation', 'schema'])
async def test_current_registry_rechecked_within_existing_tenant_transaction(committed_runtime, change):
    fixture = committed_runtime
    async with fixture.factory(binding=fixture.binding) as db:
        user = await db.get(User, fixture.user_id)
        task = await db.get(AgentTask, fixture.task_id)
        scope = RequestScope(FactoryScope(None, task.factory_id), None, ProductLineScope('ALL', None), user)
        await service().require_current_capa_view(db, scope, task.target_capa_id)
        assignments = dict(paused="status='suspended'", generation='generation=generation+1',
            schema="schema_name='tenant_other'")
        # Same transaction: transaction-entry gate alone is insufficient.
        await db.execute(text(f'UPDATE public.tenants SET {assignments[change]} WHERE id=:id'),
            {'id': fixture.binding.tenant_id})
        with pytest.raises(PermissionError):
            await service().require_current_capa_view(db, scope, task.target_capa_id)
        await db.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['expired', 'future_review', 'command'])
async def test_non_direct_unexpired_context_grants_never_become_effective(
    db, scope, sample_capa, enabled_plugin, direct_summary, monkeypatch, condition,
):
    from datetime import UTC, datetime, timedelta
    changes = {}
    if condition == 'expired':
        changes['expires_at'] = datetime.now(UTC) - timedelta(seconds=1)
    else:
        spec = replace(direct_summary, approval_floor=ApprovalFloor.HUMAN) if condition == 'future_review' else replace(direct_summary, kind='command')
        monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', MappingProxyType({SUMMARY: spec}))
    await add_grant(db, scope, sample_capa, enabled_plugin, **changes)
    task = await create(db, scope, sample_capa, enabled_plugin)
    assert task.status == 'blocked_capability'
    assert await db.scalar(select(func.count()).select_from(AgentTaskGrant)) == 0
    assert await db.scalar(select(func.count()).select_from(AgentRun)) == 0


@pytest.mark.asyncio
async def test_second_required_context_uses_its_current_module_permission(
    db, scope, sample_capa, enabled_plugin, direct_summary, monkeypatch,
):
    from app.core.permissions import Module
    other = replace(direct_summary, id='test.audit.read.v1', owner=Module.AUDIT)
    monkeypatch.setattr(catalog, 'CAPA_CAPABILITIES', MappingProxyType({
        **catalog.CAPA_CAPABILITIES, other.id: other}))
    enabled_plugin.manifest = dict(protocol_versions=['1'], required_capabilities=[SUMMARY, other.id])
    await add_grant(db, scope, sample_capa, enabled_plugin)
    missing = await create(db, scope, sample_capa, enabled_plugin)
    assert missing.status == 'blocked_capability'
    await add_grant(db, scope, sample_capa, enabled_plugin, capability_id=other.id)
    await db.execute(update(RolePermission).where(RolePermission.role_id == scope.user.role_id,
        RolePermission.module == 'audit').values(permission_level=0))
    denied = await create(db, scope, sample_capa, enabled_plugin)
    assert denied.status == 'blocked_capability'
    assert await db.scalar(select(func.count()).select_from(AgentRun)) == 0
    await db.execute(update(RolePermission).where(RolePermission.role_id == scope.user.role_id,
        RolePermission.module == 'audit').values(permission_level=1))
    ready = await create(db, scope, sample_capa, enabled_plugin)
    assert ready.status == 'ready'


@pytest.mark.asyncio
async def test_idempotent_target_and_installation_must_match(db, scope, sample_capa,
                                                          enabled_plugin):
    from app.models.agent_plugin import AgentPluginInstallation
    task = await create(db, scope, sample_capa, enabled_plugin, 'fixed')
    other = CAPAEightD(document_no='8D-OTHER-'+uuid.uuid4().hex[:8], title='Other',
        factory_id=sample_capa.factory_id, product_line_code=sample_capa.product_line_code)
    plugin = AgentPluginInstallation(installation_id=uuid.uuid4(), plugin_key='other',
        plugin_version='1', manifest=enabled_plugin.manifest, secret_hash='fixture', enabled=True,
        created_by=scope.user.user_id)
    db.add_all([other, plugin])
    await db.flush()
    with pytest.raises(ValueError):
        await create(db, scope, other, enabled_plugin, task.request_key)
    with pytest.raises(ValueError):
        await create(db, scope, sample_capa, plugin, task.request_key)


@pytest.mark.asyncio
async def test_pending_unrelated_failure_is_not_translated_as_task_conflict(
    db, scope, sample_capa, enabled_plugin,
):
    from sqlalchemy.exc import IntegrityError
    # Duplicate unrelated unique business record, still pending before service reads.
    db.add(Factory(id=uuid.uuid4(), code='TEST', name='Duplicate'))
    with pytest.raises(IntegrityError):
        await create(db, scope, sample_capa, enabled_plugin)
