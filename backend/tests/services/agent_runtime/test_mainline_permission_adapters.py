"""Pure adapter contracts; fake persistence never substitutes for DB acceptance."""
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from app.core.factory_scope import FactoryScope, ProductLineScope
from app.core.permissions import Module, PermissionLevel
from app.schemas.agent_plugin import PluginManifest
from app.services.agent.permissions import delivery
from app.services.agent_runtime import readonly_delivery, runtime_access, task_service

SUMMARY = task_service.TARGET_SUMMARY


def authority_data(mode='ALL', factories='limited', group=False):
    target = NS(report_id=uuid4(), factory_id=uuid4(), product_line_code='LINE')
    levels = {Module.CAPA: PermissionLevel.ADMIN}
    if group:
        levels[Module.GROUP] = PermissionLevel.ADMIN
    factory_scope = FactoryScope(None if factories == 'all' else [target.factory_id], target.factory_id)
    lines = ProductLineScope(mode, ['LINE'] if mode == 'EXPLICIT' else None)
    plugin = NS(grant_id=uuid4(), capability_id=SUMMARY, factory_ids=[str(target.factory_id)],
        object_ids=[str(target.report_id)], product_line_codes=['LINE'], expires_at=None, enabled=True)
    trial = NS(profile='local_metadata_v1', expires_at=datetime.now(UTC) + timedelta(hours=1))
    manifest = PluginManifest(protocol_versions=['1'], required_capabilities=[SUMMARY])
    return target, levels, factory_scope, lines, plugin, trial, manifest


@pytest.mark.parametrize('mode,expected', [('ALL', True), ('EXPLICIT', True), ('NONE', False)])
def test_task_adapter_explicitly_passes_fresh_line_mode(monkeypatch, mode, expected):
    target, levels, factories, lines, plugin, trial, manifest = authority_data(mode)
    seen = []
    real = task_service.authorize
    def inspect(value):
        seen.append(value)
        return real(value)
    monkeypatch.setattr(task_service, 'authorize', inspect)
    grants, ready = task_service._read_grants(uuid4(), target, manifest, levels, factories, lines, [plugin], trial=trial)
    assert ready is expected
    assert bool(grants) is expected
    assert len(seen) == 1
    assert seen[0].identity_bypass_row_level_security is (mode == 'ALL')
    assert seen[0].catalog_profile == 'local_metadata_v1'
    assert not hasattr(lines, 'bypass_row_level_security')


def test_task_adapter_does_not_infer_factory_or_enable_baseline():
    target, levels, factories, lines, plugin, trial, manifest = authority_data(factories='all')
    def derive():
        return task_service._read_grants(uuid4(), target, manifest, levels, factories, lines, [plugin], trial=trial)
    assert derive() == ([], False)
    levels[Module.GROUP] = PermissionLevel.ADMIN
    assert derive()[1]
    assert task_service._read_grants(uuid4(), target, manifest, levels, factories, lines, [plugin]) == ([], False)


class Rows:
    def __init__(self, values):
        self.values = values
    def all(self):
        return self.values


class ReadDB:
    no_autoflush = nullcontext()
    def __init__(self, user=None, batches=()):
        self.user, self.batches = user, iter(batches)
    async def scalar(self, query):
        return self.user
    async def scalars(self, query):
        return Rows(next(self.batches))


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,expected', [('ALL', True), ('EXPLICIT', True), ('NONE', False)])
async def test_runtime_adapter_uses_current_access_not_old_user_role(monkeypatch, mode, expected):
    target, levels, factories, lines, plugin, trial, manifest = authority_data(mode)
    user = NS(user_id=uuid4())  # No cached role or bypass attributes.
    task = NS(executor_user_id=user.user_id, target_capa_id=target.report_id, factory_id=target.factory_id, task_id=uuid4())
    installation = NS(installation_id=uuid4(), manifest=manifest.model_dump())
    task_grant = NS(**{**vars(plugin), 'grant_id': uuid4()})
    db = ReadDB(user, [[plugin], [task_grant]])
    fresh_calls, seen = [], []
    async def fresh(db, stale):
        fresh_calls.append(stale)
        return levels, factories, lines
    async def target_read(db, report_id, factory_scope, line_scope):
        assert factory_scope is factories and line_scope is lines
        return target
    real = runtime_access.authorize
    def inspect(value):
        seen.append(value)
        return real(value)
    monkeypatch.setattr(task_service, 'current_capa_access', fresh)
    monkeypatch.setattr(task_service, '_target', target_read)
    monkeypatch.setattr(task_service, 'trial_for_target', lambda *args: trial)
    monkeypatch.setattr(runtime_access, 'authorize', inspect)
    if expected:
        authority = await runtime_access.authorize_task(db, task, installation)
        assert authority.capabilities[0].allowed
        assert authority.scope.pl_scope is lines
    else:
        with pytest.raises(PermissionError):
            await runtime_access.authorize_task(db, task, installation)
    assert len(fresh_calls) == len(seen) == 1
    assert seen[0].identity_bypass_row_level_security is (mode == 'ALL')
    assert seen[0].catalog_profile == 'local_metadata_v1'


def source_data():
    task = NS(task_id=uuid4(), target_capa_id=uuid4(), factory_id=uuid4())
    receipt = NS(receipt_id=uuid4(), task_id=task.task_id, run_id=uuid4(), source_capa_id=task.target_capa_id,
        tenant_generation=7, lease_epoch=3, projection_id=SUMMARY, projection_digest='a' * 64, data_class='internal')
    return task, receipt


@pytest.mark.asyncio
async def test_historical_sources_bind_six_fields_and_four_authorization_keys(monkeypatch):
    task, receipt = source_data()
    db = ReadDB(batches=[[receipt]])
    acl_checks, observed = [], []
    async def source_acl(db, scope, report_id):
        acl_checks.append(report_id)
        return NS(factory_id=task.factory_id)
    real = delivery.can_view_derived
    def check(label, target_authorized, authorized):
        observed.append((label, authorized))
        return real(label, target_authorized, authorized)
    monkeypatch.setattr(task_service, 'require_current_capa_view', source_acl)
    monkeypatch.setattr(delivery, 'can_view_derived', check)
    rows = await readonly_delivery.admit_historical_sources(db, object(), task, receipt.run_id,
        [receipt.receipt_id], generation=7, epoch=3)
    assert rows == [receipt] and acl_checks == [receipt.source_capa_id]
    label, keys = observed[0]
    assert label.sources == (delivery.SourceLabel(owner=Module.CAPA, object_id=receipt.source_capa_id,
        sensitivity='internal', capability_id=receipt.projection_id, projection='masked', source_version='a' * 64),)
    assert keys == frozenset({(Module.CAPA, receipt.source_capa_id, SUMMARY, 'masked')})


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['missing', 'denied', 'factory'])
async def test_receipt_alone_never_authorizes_historical_source(monkeypatch, failure):
    task, receipt = source_data()
    async def denied(db, scope, report_id):
        if failure == 'missing':
            raise LookupError('missing source')
        if failure == 'denied':
            raise PermissionError('revoked')
        return NS(factory_id=uuid4())
    monkeypatch.setattr(task_service, 'require_current_capa_view', denied)
    with pytest.raises(PermissionError):
        await readonly_delivery.admit_historical_sources(ReadDB(batches=[[receipt]]), object(), task,
            receipt.run_id, [receipt.receipt_id], generation=7, epoch=3)


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['task_id', 'run_id', 'source_capa_id', 'tenant_generation', 'lease_epoch', 'projection_id', 'projection_digest'])
async def test_historical_receipt_binding_rejected_before_acl(monkeypatch, field):
    task, receipt = source_data()
    run_id = receipt.run_id
    setattr(receipt, field, 999 if field in {'tenant_generation', 'lease_epoch'} else 'invalid')
    async def unexpected(*args):
        pytest.fail('invalid receipt reached ACL')
    monkeypatch.setattr(task_service, 'require_current_capa_view', unexpected)
    with pytest.raises(PermissionError):
        await readonly_delivery.admit_historical_sources(ReadDB(batches=[[receipt]]), object(), task,
            run_id, [receipt.receipt_id], generation=7, epoch=3)


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke', [False, True])
async def test_historical_output_rechecks_real_source_acl_after_serialization(monkeypatch, revoke):
    task, receipt = source_data()
    task.initiator_id = task.executor_user_id = uuid4()
    task.preferred_installation_id = uuid4()
    row = NS(task_id=task.task_id, run_id=receipt.run_id, data_class='restricted')
    run = NS(task_id=task.task_id, installation_id=task.preferred_installation_id)
    scalars = iter([row, run])
    class OutputDB(ReadDB):
        async def scalar(self, query):
            return next(scalars)
    db = OutputDB(batches=[[receipt], [receipt]])
    task_checks, acl_checks, serialized = [], [], []
    async def current_task(db, scope, task_id):
        task_checks.append(task_id)
        return task
    async def source_acl(db, scope, source_id):
        acl_checks.append(source_id)
        if revoke and serialized:
            raise PermissionError('source revoked after serialization')
        return NS(factory_id=task.factory_id)
    async def stored(*args):
        return [receipt.receipt_id]
    def output(*args, **kwargs):
        serialized.append(True)
        return {'payload': 'saved text'}
    monkeypatch.setattr(task_service, 'get_task_for_view', current_task)
    monkeypatch.setattr(task_service, 'require_current_capa_view', source_acl)
    monkeypatch.setattr(readonly_delivery, '_stored_sources', stored)
    monkeypatch.setattr(readonly_delivery, '_output', output)
    if revoke:
        with pytest.raises(PermissionError, match='source revoked'):
            await readonly_delivery._historical_output(db, object(), task.task_id, uuid4(), event=False)
        assert len(task_checks) == 2
    else:
        result = await readonly_delivery._historical_output(db, object(), task.task_id, uuid4(), event=False)
        assert result['payload'] == 'saved text'
        assert result['sources'][0]['projection_digest'] == receipt.projection_digest
        assert len(task_checks) == 3
    assert acl_checks == [receipt.source_capa_id, receipt.source_capa_id]
    assert serialized == [True]
