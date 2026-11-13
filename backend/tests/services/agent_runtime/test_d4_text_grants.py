from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.access import authorize
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.derived_sources import DerivedSourceScope
from app.services.agent.permissions.types import AccessAttempt, Grant


@pytest.mark.parametrize('plugin,task,expected', [('A', 'B', False), ('B', 'A', False), ('B', 'B', True), (None, 'B', False), ('B', None, False)])
def test_body_authorization_intersects_both_explicit_source_scopes(plugin, task, expected):
    report, factory, fmea = uuid4(), uuid4(), uuid4()
    spec = get_capability('capa.d4.root_cause_candidate.masked.v1', profile='local_d4_root_cause_text_v1')
    grant = Grant(spec.id, frozenset({factory}), frozenset({report}), frozenset({'line'}))
    current = DerivedSourceScope(report, spec.id, Module.FMEA, 'fmea.failure_cause.reference.v1', fmea, 'B')
    scopes = {'A': replace(current, cause_node_id='A'), 'B': current, None: None}
    attempt = AccessAttempt(spec, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}), frozenset({'line'}), grant, grant, factory, report, 'line', datetime.now(UTC), catalog_profile='local_d4_root_cause_text_v1', current_source=current, plugin_source_scope=scopes[plugin], task_source_scope=scopes[task])
    assert authorize(attempt).allowed is expected


def test_body_authorization_cannot_use_scope_for_another_target():
    report, factory = uuid4(), uuid4()
    spec = get_capability('capa.d4.root_cause_candidate.masked.v1', profile='local_d4_root_cause_text_v1')
    grant = Grant(spec.id, frozenset({factory}), frozenset({report}), frozenset({'line'}))
    source = DerivedSourceScope(uuid4(), spec.id, Module.FMEA, 'fmea.failure_cause.reference.v1', uuid4(), 'B')
    attempt = AccessAttempt(spec, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}), frozenset({'line'}), grant, grant, factory, report, 'line', datetime.now(UTC), catalog_profile='local_d4_root_cause_text_v1', current_source=source, plugin_source_scope=source, task_source_scope=source)
    assert not authorize(attempt).allowed


def test_explicit_scope_uses_server_owned_projection_and_rejects_wrong_target():
    from app.schemas.agent_d4_text import DerivedSourceScopeInput
    from app.services.agent_runtime.derived_source_grants import explicit_source_scope
    report, fmea = uuid4(), uuid4()
    request = DerivedSourceScopeInput(target_report_id=report, fmea_id=fmea, cause_node_id='A')
    source = explicit_source_scope(report, request)
    assert source == DerivedSourceScope(report, 'capa.d4.root_cause_candidate.masked.v1', Module.FMEA,
        'fmea.failure_cause.reference.v1', fmea, 'A')
    with pytest.raises(ValueError):
        explicit_source_scope(uuid4(), request)


def test_registry_grant_target_query_does_not_select_whole_capa():
    import inspect
    from app.services.agent_runtime.plugin_registry import _require_grant_enableable
    assert 'select(CAPAEightD)' not in inspect.getsource(_require_grant_enableable)


def test_deployment_delivery_kind_cannot_cross_message_and_context():
    from datetime import timedelta
    from types import SimpleNamespace
    from app.core.tenant_transaction import TenantBinding
    from app.services.agent_runtime.runtime_access import require_installation_delivery
    from app.services.agent_runtime.trial_policy import TrialAdmission
    plugin_id = uuid4()
    plugin = SimpleNamespace(installation_id=plugin_id, plugin_version='1')
    binding = TenantBinding(uuid4(), 'tenant_test', 1, 'business')
    trial = TrialAdmission('local_d4_root_cause_text_v1', 'a' * 64, datetime.now(UTC) + timedelta(minutes=2), plugin_id)
    for kind, classification, projection in [('message', 'restricted', 'raw'), ('context', 'restricted', 'masked')]:
        require_installation_delivery(binding, plugin, classification, projection, controlled_egress=True, trial=trial, delivery_kind=kind)
    for kind, classification, projection in [('context', 'restricted', 'raw'), ('message', 'restricted', 'masked')]:
        with pytest.raises(PermissionError):
            require_installation_delivery(binding, plugin, classification, projection, controlled_egress=True, trial=trial, delivery_kind=kind)


@pytest.mark.parametrize('change', ['none', 'level', 'factory', 'line'])
def test_directory_and_execution_use_same_identity_scope(change):
    from app.services.agent.permissions.access import can_discover_source_plugin
    report, factory = uuid4(), uuid4()
    spec = get_capability('capa.d4.root_cause_candidate.masked.v1', profile='local_d4_root_cause_text_v1')
    grant = Grant(spec.id, frozenset({factory}), frozenset({report}), frozenset({'line'}))
    source = DerivedSourceScope(report, spec.id, Module.FMEA, 'fmea.failure_cause.reference.v1', uuid4(), 'A')
    attempt = AccessAttempt(spec, {Module.CAPA: PermissionLevel.VIEW}, frozenset({factory}), frozenset({'line'}),
        grant, grant, factory, report, 'line', datetime.now(UTC), catalog_profile='local_d4_root_cause_text_v1',
        current_source=source, plugin_source_scope=source, task_source_scope=source)
    if change == 'level': attempt = replace(attempt, identity_levels={})
    if change == 'factory': attempt = replace(attempt, identity_factories=frozenset())
    if change == 'line': attempt = replace(attempt, identity_product_lines=frozenset())
    assert can_discover_source_plugin(attempt) == authorize(attempt).allowed == (change == 'none')


from tests.capa.test_d4_source_proofs import proof_case, committed_runtime


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_admin_explicit_source_is_persisted_on_same_parent_grant(proof_case, committed_runtime):
    from sqlalchemy import select
    from app.models.agent_derived_source import AgentPluginDerivedSourceScope
    from app.schemas.agent_d4_text import DerivedSourceScopeInput
    from app.schemas.agent_plugin import PluginGrantCreate
    from app.services.agent_runtime.plugin_registry import create_plugin_grant
    c = proof_case
    source = DerivedSourceScopeInput(target_report_id=c.report.report_id, fmea_id=c.fmea.fmea_id, cause_node_id='cause-1')
    request = PluginGrantCreate(capability_id='capa.d4.root_cause_candidate.masked.v1',
        factory_ids=[c.report.factory_id], product_line_codes=[c.report.product_line_code],
        object_ids=[c.report.report_id], derived_source_scope=source)
    grant = await create_plugin_grant(c.db, c.user, committed_runtime.plugin_id, request)
    row = await c.db.scalar(select(AgentPluginDerivedSourceScope).where(AgentPluginDerivedSourceScope.plugin_grant_id == grant.grant_id))
    assert row is not None and row.target_report_id == c.report.report_id
    assert row.fmea_id == c.fmea.fmea_id and row.cause_node_id == 'cause-1'
    assert row.derived_projection_id == request.capability_id and row.source_module == 'fmea'


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('forged', [None, 'source_module', 'source_projection_id', 'derived_projection_id'])
async def test_text_grant_enabled_only_with_explicit_visible_source_and_matching_policy(proof_case, committed_runtime, forged):
    from datetime import timedelta
    from sqlalchemy import select
    from app.models.agent_plugin import AgentPluginInstallation
    from app.models.agent_derived_source import AgentPluginDerivedSourceScope
    from app.schemas.agent_d4_text import DerivedSourceScopeInput
    from app.schemas.agent_plugin import PluginGrantCreate
    from app.services.agent_runtime.local_d4_text_policy import TextEntry, TextPolicy, TEXT_PLUGIN_KEY, TEXT_WORKER_SHA256
    from app.services.agent_runtime.plugin_registry import create_plugin_grant, set_plugin_grant_enabled
    c = proof_case
    plugin = await c.db.get(AgentPluginInstallation, committed_runtime.plugin_id)
    plugin.plugin_key = TEXT_PLUGIN_KEY
    plugin.manifest = {'protocol_versions': ['1'], 'required_capabilities': ['capa.d4.root_cause_candidate.masked.v1']}
    await c.db.commit()
    expires = datetime.now(UTC) + timedelta(minutes=20)
    policy_expiry = expires + timedelta(minutes=10)
    entry = TextEntry(c.binding.tenant_id, c.binding.generation, plugin.installation_id, plugin.credential_epoch,
        plugin.plugin_key, plugin.plugin_version, c.user.user_id, c.report.report_id, c.report.factory_id,
        c.report.product_line_code, policy_expiry, TEXT_WORKER_SHA256, (), 'a' * 64)
    c.db.info['agent_d4_text_policy'] = TextPolicy((entry,), 'TEXT_POLICY_READY')
    source = DerivedSourceScopeInput(target_report_id=c.report.report_id, fmea_id=c.fmea.fmea_id, cause_node_id='cause-1')
    request = PluginGrantCreate(capability_id='capa.d4.root_cause_candidate.masked.v1', factory_ids=[c.report.factory_id],
        product_line_codes=[c.report.product_line_code], object_ids=[c.report.report_id], expires_at=expires,
        enabled=forged is None, derived_source_scope=source)
    grant = await create_plugin_grant(c.db, c.user, plugin.installation_id, request)
    row = await c.db.scalar(select(AgentPluginDerivedSourceScope).where(AgentPluginDerivedSourceScope.plugin_grant_id == grant.grant_id))
    assert row is not None
    if forged is not None:
        setattr(row, forged, 'forged')
        await c.db.flush()
        with pytest.raises(ValueError):
            await set_plugin_grant_enabled(c.db, c.user, plugin.installation_id, grant.grant_id, True)
    else:
        assert grant.enabled


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['create', 'reenable'])
async def test_admin_grant_final_source_revocation_rolls_back(proof_case, committed_runtime, monkeypatch, operation):
    from datetime import timedelta
    from sqlalchemy import func, select, update
    from app.models.agent_plugin import AgentPluginInstallation, AgentPluginGrant
    from app.models.agent_derived_source import AgentPluginDerivedSourceScope
    from app.models.role import RolePermission
    from app.schemas.agent_d4_text import DerivedSourceScopeInput
    from app.schemas.agent_plugin import PluginGrantCreate
    from app.services.agent_runtime.local_d4_text_policy import TextEntry, TextPolicy, TEXT_PLUGIN_KEY, TEXT_WORKER_SHA256
    from app.services.agent_runtime import plugin_registry
    c = proof_case
    plugin = await c.db.get(AgentPluginInstallation, committed_runtime.plugin_id)
    plugin.plugin_key = TEXT_PLUGIN_KEY
    await c.db.commit()
    expires = datetime.now(UTC) + timedelta(minutes=20)
    entry = TextEntry(c.binding.tenant_id, c.binding.generation, plugin.installation_id, plugin.credential_epoch,
        plugin.plugin_key, plugin.plugin_version, c.user.user_id, c.report.report_id, c.report.factory_id,
        c.report.product_line_code, expires + timedelta(minutes=10), TEXT_WORKER_SHA256, (), 'a' * 64)
    c.db.info['agent_d4_text_policy'] = TextPolicy((entry,), 'TEXT_POLICY_READY')
    source = DerivedSourceScopeInput(target_report_id=c.report.report_id, fmea_id=c.fmea.fmea_id, cause_node_id='cause-1')
    request = PluginGrantCreate(capability_id='capa.d4.root_cause_candidate.masked.v1', factory_ids=[c.report.factory_id],
        product_line_codes=[c.report.product_line_code], object_ids=[c.report.report_id], expires_at=expires,
        enabled=operation == 'create', derived_source_scope=source)
    grant = None
    if operation == 'reenable':
        grant = await plugin_registry.create_plugin_grant(c.db, c.user, plugin.installation_id, request)
        await c.db.commit()
    before = await c.db.scalar(select(func.count()).select_from(AgentPluginGrant))
    grant_id = None if grant is None else grant.grant_id
    original = plugin_registry._require_grant_enableable
    async def revoke_after_check(*args, **kwargs):
        result = await original(*args, **kwargs)
        async with c.factory(binding=c.binding) as other:
            await other.execute(update(RolePermission).where(RolePermission.role_id == c.user.role_id,
                RolePermission.module == 'fmea').values(permission_level=0))
            await other.commit()
        return result
    monkeypatch.setattr(plugin_registry, '_require_grant_enableable', revoke_after_check)
    with pytest.raises(PermissionError):
        if operation == 'create':
            await plugin_registry.create_plugin_grant(c.db, c.user, plugin.installation_id, request)
        else:
            await plugin_registry.set_plugin_grant_enabled(c.db, c.user, plugin.installation_id, grant_id, True)
    await c.db.rollback()
    async with c.factory(binding=c.binding) as fresh:
        assert await fresh.scalar(select(func.count()).select_from(AgentPluginGrant)) == before
        if grant_id:
            assert not (await fresh.get(AgentPluginGrant, grant_id)).enabled
            assert await fresh.scalar(select(func.count()).select_from(AgentPluginDerivedSourceScope).where(
                AgentPluginDerivedSourceScope.plugin_grant_id == grant_id)) == 1


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('revoke', ['scope', 'fmea', 'during_create', 'revision', 'verification', 'proof_swap', 'swap_during_authority'])
async def test_task_scope_is_bound_to_matching_parent_and_current_proof(proof_case, committed_runtime, monkeypatch, revoke):
    from datetime import timedelta
    from sqlalchemy import select
    from app.models.agent_plugin import AgentPluginInstallation
    from app.models.agent_task import AgentRun, AgentTaskGrant
    from app.models.agent_derived_source import AgentTaskDerivedSourceScope
    from app.models.factory import Factory
    from app.schemas.agent_d4_text import DerivedSourceScopeInput
    from app.schemas.agent_plugin import PluginGrantCreate
    from app.services.agent_runtime.local_d4_text_policy import TextEntry, TextPolicy, TEXT_PLUGIN_KEY, TEXT_WORKER_SHA256
    from app.services.agent_runtime.plugin_registry import create_plugin_grant
    from app.services.agent_runtime.task_service import create_task
    from tests.conftest import _scope_for
    c = proof_case
    assert (await c.client.post(c.url, json=c.body)).json()['source_proof_issued'] is True
    plugin = await c.db.get(AgentPluginInstallation, committed_runtime.plugin_id)
    plugin.plugin_key = TEXT_PLUGIN_KEY
    plugin.manifest = {'protocol_versions': ['1'], 'required_capabilities': ['capa.d4.root_cause_candidate.masked.v1']}
    await c.db.commit()
    expires = datetime.now(UTC) + timedelta(minutes=20)
    entry = TextEntry(c.binding.tenant_id, c.binding.generation, plugin.installation_id, plugin.credential_epoch,
        plugin.plugin_key, plugin.plugin_version, c.user.user_id, c.report.report_id, c.report.factory_id,
        c.report.product_line_code, expires + timedelta(minutes=10), TEXT_WORKER_SHA256, (), 'a' * 64)
    c.db.info['agent_d4_text_policy'] = TextPolicy((entry,), 'TEXT_POLICY_READY')
    source = DerivedSourceScopeInput(target_report_id=c.report.report_id, fmea_id=c.fmea.fmea_id, cause_node_id='cause-1')
    request = PluginGrantCreate(capability_id='capa.d4.root_cause_candidate.masked.v1', factory_ids=[c.report.factory_id],
        product_line_codes=[c.report.product_line_code], object_ids=[c.report.report_id], expires_at=expires,
        enabled=True, derived_source_scope=source)
    await create_plugin_grant(c.db, c.user, plugin.installation_id, request)
    await c.db.commit()
    factory = await c.db.get(Factory, c.report.factory_id)
    scope = _scope_for(c.user, factory, accessible_factory_ids=None)
    from app.services.agent_runtime.task_reads import list_installations
    choices = await list_installations(c.db, scope, c.report.report_id)
    assert str(plugin.installation_id) in {item['installation_id'] for item in choices['items']}
    key = uuid4().hex
    if revoke == 'during_create':
        from sqlalchemy import update, func
        from app.models.role import RolePermission
        from app.models.agent_task import AgentTask
        from app.services.agent_runtime import task_service
        original = task_service.current_source_for_target
        called = False
        async def revoke_after_source(*args, **kwargs):
            nonlocal called
            value = await original(*args, **kwargs)
            if not called:
                called = True
                async with c.factory(binding=c.binding) as other:
                    await other.execute(update(RolePermission).where(RolePermission.role_id == c.user.role_id,
                        RolePermission.module == 'fmea').values(permission_level=0))
                    await other.commit()
            return value
        monkeypatch.setattr(task_service, 'current_source_for_target', revoke_after_source)
        with pytest.raises(PermissionError):
            await create_task(c.db, scope, c.report.report_id, plugin.installation_id, key, 'start', derived_source_scope=source)
        await c.db.rollback()
        assert await c.db.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.request_key == key)) == 0
        return
    task = await create_task(c.db, scope, c.report.report_id, plugin.installation_id, key, 'start', derived_source_scope=source)
    assert task.status == 'ready'
    grant = await c.db.scalar(select(AgentTaskGrant).where(AgentTaskGrant.task_id == task.task_id))
    row = await c.db.scalar(select(AgentTaskDerivedSourceScope).where(AgentTaskDerivedSourceScope.task_grant_id == grant.grant_id))
    assert row is not None and row.fmea_id == c.fmea.fmea_id and row.cause_node_id == 'cause-1'
    run = await c.db.scalar(select(AgentRun).where(AgentRun.task_id == task.task_id))
    assert run is not None
    from app.services.agent_runtime.runtime_access import authorize_task
    if revoke == 'swap_during_authority':
        from app.database import get_db
        from app.services import fmea_agent_sources
        c.fmea.graph_data = {'nodes': [{'id': 'cause-1', 'type': 'FailureCause'},
                                       {'id': 'cause-B', 'type': 'FailureCause'}], 'edges': []}
        await c.db.commit()
        original = fmea_agent_sources.visible_fmea_source
        called = False
        async def swap_after_proof_read(*args, **kwargs):
            nonlocal called
            value = await original(*args, **kwargs)
            if not called:
                called = True
                c.body['source_ref']['cause_node_id'] = 'cause-B'
                async with c.factory(binding=c.binding) as other:
                    c.app.dependency_overrides[get_db] = lambda: other
                    try:
                        response = await c.client.post(c.url, json=c.body)
                        assert response.status_code == 200 and response.json()['source_proof_issued'] is True
                    finally:
                        c.app.dependency_overrides[get_db] = lambda: c.db
            return value
        monkeypatch.setattr(fmea_agent_sources, 'visible_fmea_source', swap_after_proof_read)
        with pytest.raises(PermissionError):
            await authorize_task(c.db, task, plugin)
        return
    authority = await authorize_task(c.db, task, plugin)
    assert any(item.id == request.capability_id and item.allowed for item in authority.capabilities)
    if revoke == 'scope':
        from sqlalchemy import update
        async with c.factory(binding=c.binding) as other:
            await other.execute(update(AgentTaskDerivedSourceScope).where(
                AgentTaskDerivedSourceScope.scope_id == row.scope_id).values(cause_node_id='another'))
            await other.commit()
    elif revoke == 'fmea':
        from sqlalchemy import update
        from app.models.role import RolePermission
        await c.db.execute(update(RolePermission).where(RolePermission.role_id == c.user.role_id,
            RolePermission.module == 'fmea').values(permission_level=0))
    elif revoke == 'revision':
        for value in ('changed', '\t原始根因\u00a0'):
            result = await c.client.put(f'/api/capa/{c.report.report_id}', json={'d4_root_cause': value})
            assert result.status_code == 200, result.text
    elif revoke == 'proof_swap':
        c.fmea.graph_data = {'nodes': [{'id': 'cause-1', 'type': 'FailureCause'},
                                       {'id': 'cause-B', 'type': 'FailureCause'}], 'edges': []}
        await c.db.commit()
        c.body['source_ref']['cause_node_id'] = 'cause-B'
        response = await c.client.post(c.url, json=c.body)
        assert response.status_code == 200 and response.json()['source_proof_issued'] is True
    else:
        from sqlalchemy import update
        from app.models.capa import CapaRootCauseVerification
        from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
        proof = await c.db.scalar(select(CapaD4RootCauseSourceProof).where(CapaD4RootCauseSourceProof.report_id == c.report.report_id))
        await c.db.execute(update(CapaRootCauseVerification).where(
            CapaRootCauseVerification.verification_id == proof.verification_id).values(conclusion='failed', is_verified=False))
    await c.db.commit()
    with pytest.raises(PermissionError):
        await authorize_task(c.db, task, plugin)
    from app.schemas.agent_control import TaskControl
    from app.services.agent_runtime.task_controls import control_task
    from tests.capa.test_d4_source_access import SQLSpy
    with SQLSpy(await c.db.connection()) as spy:
        paused = await control_task(c.db, scope, task.task_id, TaskControl(action='pause', run_id=run.run_id,
            expected_epoch=run.lease_epoch, idempotency_key=uuid4().hex))
    assert paused.task_status == 'paused'
    assert not any('d4_root_cause' in sql or 'graph_data' in sql or 'jsonb_array_elements' in sql for sql in spy.statements)
    if revoke == 'proof_swap':
        with pytest.raises(PermissionError):
            await control_task(c.db, scope, task.task_id, TaskControl(action='restart', run_id=paused.run_id,
                expected_epoch=paused.lease_epoch, checkpoint_id=uuid4(), idempotency_key=uuid4().hex))
        await c.db.refresh(row)
        assert row.cause_node_id == 'cause-1'
    with pytest.raises(PermissionError):
        await control_task(c.db, scope, task.task_id, TaskControl(action='resume', run_id=paused.run_id,
            expected_epoch=paused.lease_epoch, idempotency_key=uuid4().hex))
    with SQLSpy(await c.db.connection()) as spy:
        cancelled = await control_task(c.db, scope, task.task_id, TaskControl(action='cancel', run_id=paused.run_id,
            expected_epoch=paused.lease_epoch, idempotency_key=uuid4().hex))
    assert cancelled.task_status == 'cancelled' and cancelled.run_status == 'stopped'
    assert not any('d4_root_cause' in sql or 'graph_data' in sql or 'jsonb_array_elements' in sql for sql in spy.statements)


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_runtime_target_lookup_reads_coordinates_only(proof_case):
    from app.models.factory import Factory
    from app.services.agent_runtime.task_service import require_current_capa_view
    from tests.capa.test_d4_source_access import SQLSpy
    from tests.conftest import _scope_for
    c = proof_case
    factory = await c.db.get(Factory, c.report.factory_id)
    scope = _scope_for(c.user, factory, accessible_factory_ids=None)
    with SQLSpy(await c.db.connection()) as spy:
        target = await require_current_capa_view(c.db, scope, c.report.report_id)
    statements = [sql for sql in spy.statements if 'from capa_eightd' in sql]
    assert target.report_id == c.report.report_id and target.fmea_ref_id == c.fmea.fmea_id
    assert statements and all('d4_root_cause' not in sql for sql in statements)


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize('plugin_node,task_node,expected', [
    ('cause-1', 'cause-B', 'blocked_capability'),
    ('cause-B', 'cause-1', 'blocked_capability'),
    ('cause-B', 'cause-B', 'ready'),
])
async def test_distinct_plugin_task_scopes_intersect_current_proof(proof_case, committed_runtime, plugin_node, task_node, expected):
    from datetime import timedelta
    from sqlalchemy import func, select
    from app.models.agent_plugin import AgentPluginInstallation
    from app.models.agent_task import AgentRun, AgentTaskGrant
    from app.models.factory import Factory
    from app.schemas.agent_d4_text import DerivedSourceScopeInput
    from app.schemas.agent_plugin import PluginGrantCreate
    from app.services.agent_runtime.local_d4_text_policy import TextEntry, TextPolicy, TEXT_PLUGIN_KEY, TEXT_WORKER_SHA256
    from app.services.agent_runtime.plugin_registry import create_plugin_grant
    from app.services.agent_runtime.task_service import create_task
    from tests.conftest import _scope_for
    c = proof_case
    c.fmea.graph_data = {'nodes': [{'id': 'cause-1', 'type': 'FailureCause'},
                                   {'id': 'cause-B', 'type': 'FailureCause'}], 'edges': []}
    await c.db.commit()
    c.body['source_ref']['cause_node_id'] = 'cause-B'
    result = await c.client.post(c.url, json=c.body)
    assert result.status_code == 200 and result.json()['source_proof_issued'] is True
    plugin = await c.db.get(AgentPluginInstallation, committed_runtime.plugin_id)
    plugin.plugin_key = TEXT_PLUGIN_KEY
    plugin.manifest = {'protocol_versions':['1'], 'required_capabilities':['capa.d4.root_cause_candidate.masked.v1']}
    await c.db.commit()
    expires = datetime.now(UTC) + timedelta(minutes=20)
    entry = TextEntry(c.binding.tenant_id, c.binding.generation, plugin.installation_id, plugin.credential_epoch,
        plugin.plugin_key, plugin.plugin_version, c.user.user_id, c.report.report_id, c.report.factory_id,
        c.report.product_line_code, expires + timedelta(minutes=10), TEXT_WORKER_SHA256, (), 'a' * 64)
    c.db.info['agent_d4_text_policy'] = TextPolicy((entry,), 'TEXT_POLICY_READY')
    source = DerivedSourceScopeInput(target_report_id=c.report.report_id, fmea_id=c.fmea.fmea_id, cause_node_id=plugin_node)
    await create_plugin_grant(c.db, c.user, plugin.installation_id, PluginGrantCreate(
        capability_id='capa.d4.root_cause_candidate.masked.v1', factory_ids=[c.report.factory_id],
        product_line_codes=[c.report.product_line_code], object_ids=[c.report.report_id], expires_at=expires,
        enabled=True, derived_source_scope=source))
    await c.db.commit()
    scope = _scope_for(c.user, await c.db.get(Factory, c.report.factory_id), accessible_factory_ids=None)
    task = await create_task(c.db, scope, c.report.report_id, plugin.installation_id, uuid4().hex, 'start',
        derived_source_scope=source.model_copy(update={'cause_node_id':task_node}))
    assert task.status == expected
    count = await c.db.scalar(select(func.count()).select_from(AgentTaskGrant).where(AgentTaskGrant.task_id == task.task_id))
    run_count = await c.db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == task.task_id))
    assert (count, run_count) == ((1, 1) if expected == 'ready' else (0, 0))
