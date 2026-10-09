from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.permissions import Module, PermissionLevel
from app.core.tenant_transaction import TenantBinding
from app.services.agent.permissions.access import authorize
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import AccessAttempt, ApprovalFloor, Grant
from tests.services.agent_runtime.trial_support import UNIT_ENTRY, write_policy

SUMMARY = 'capa.d4.summary.masked.v1'
NOW = datetime(2030, 1, 1, tzinfo=UTC)


def test_profile_preserves_baseline_and_command_denial():
    assert get_capability(SUMMARY).approval_floor == ApprovalFloor.DENY
    summary = get_capability(SUMMARY, profile='local_metadata_v1')
    assert summary.approval_floor == ApprovalFloor.DIRECT
    assert get_capability('capa.d4.candidate.propose.v1', profile='local_metadata_v1').approval_floor == ApprovalFloor.DENY
    assert get_capability(SUMMARY, profile='caller-chosen') is None
    factory, report = uuid4(), uuid4()
    grant = Grant(SUMMARY, frozenset([factory]), frozenset([report]), frozenset(['LINE']))
    attempt = AccessAttempt(summary, {Module.CAPA: PermissionLevel.VIEW}, frozenset([factory]),
        frozenset(['LINE']), grant, grant, factory, report, 'LINE', NOW, catalog_profile='local_metadata_v1')
    assert authorize(attempt).allowed
    assert not authorize(replace(attempt, catalog_profile='baseline')).allowed
    assert not authorize(replace(attempt, catalog_profile='unknown')).allowed
    assert not authorize(replace(attempt, spec=replace(summary, required_level=PermissionLevel.NONE))).allowed
    assert not authorize(replace(attempt, task_grant=None)).allowed


def facts(tmp_path, monkeypatch):
    from app.config import settings
    from app.services.agent_runtime.trial_policy import load_policy
    monkeypatch.setattr(settings, 'TENANT_MODE', 'dev')
    policy = load_policy(write_policy(tmp_path / 'policy.json'), mode='local_metadata', tenant_mode='dev', now=NOW)
    plugin = SimpleNamespace(installation_id=UUID(UNIT_ENTRY['installation_id']), credential_epoch=0,
        plugin_key=UNIT_ENTRY['plugin_key'], plugin_version=UNIT_ENTRY['plugin_version'])
    binding = TenantBinding(UUID(UNIT_ENTRY['tenant_id']), 't_trial', 1, 'business')
    arguments = dict(binding=binding, installation=plugin, executor_user_id=UUID(UNIT_ENTRY['executor_user_id']),
        report_id=UUID(UNIT_ENTRY['report_id']), factory_id=UUID(UNIT_ENTRY['factory_id']),
        product_line_code='TRIAL-LINE', now=NOW)
    return policy, arguments


def test_only_exact_server_facts_select_admission(tmp_path, monkeypatch):
    from app.services.agent_runtime.trial_policy import EMPTY_POLICY, select_admission
    policy, args = facts(tmp_path, monkeypatch)
    admitted = select_admission(policy, **args)
    assert admitted.profile == 'local_metadata_v1'
    assert admitted.binding_sha256 == policy.entries[0].binding_sha256
    assert admitted.expires_at == datetime(2030, 1, 1, 0, 20, tzinfo=UTC)
    assert select_admission(EMPTY_POLICY, **args) is None
    assert select_admission(policy, **{**args, 'now': NOW + timedelta(minutes=20)}) is None
    monkeypatch.setattr(__import__('app.config', fromlist=['settings']).settings, 'TENANT_MODE', 'production')
    assert select_admission(policy, **args) is None


@pytest.mark.parametrize('field', ['tenant', 'generation', 'mode', 'installation', 'epoch', 'key', 'version',
    'executor_user_id', 'report_id', 'factory_id', 'product_line_code'])
def test_any_binding_mismatch_keeps_denied(tmp_path, monkeypatch, field):
    from app.services.agent_runtime.trial_policy import select_admission
    policy, args = facts(tmp_path, monkeypatch)
    binding, plugin = args['binding'], args['installation']
    if field == 'tenant': args['binding'] = replace(binding, tenant_id=uuid4())
    elif field == 'generation': args['binding'] = replace(binding, generation=2)
    elif field == 'mode': args['binding'] = replace(binding, mode='maintenance')
    elif field in ('installation', 'epoch', 'key', 'version'):
        values = {'installation': ('installation_id', uuid4()), 'epoch': ('credential_epoch', 1),
            'key': ('plugin_key', 'other'), 'version': ('plugin_version', '2.0.0')}
        setattr(plugin, *values[field])
    elif field == 'product_line_code': args[field] = 'OTHER'
    else: args[field] = uuid4()
    assert select_admission(policy, **args) is None
