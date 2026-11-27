from contextlib import nullcontext
import importlib
import json
from pathlib import Path
import shutil
from time import time
from types import SimpleNamespace
from uuid import uuid4

import pytest


MODULES = Path(__file__).parents[1] / 'deploy' / 'd4-acceptance'
LEASE = 'a' * 32
SLOT = {'pr': 45, 'head': 'b' * 40, 'merge': 'c' * 40, 'plan': 'd' * 64, 'lease': LEASE}
ROLES = {'d4-revoke': 'field_qe'}
ORIGIN = 'https://d4-test-openqms.smartindustry.world'


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.syspath_prepend(str(MODULES))
    return importlib.import_module('prepare_preview')


def binding(**changes):
    now = int(time())
    return dict(SLOT, report_id=str(uuid4()), issued_at=now - 1, expires_at=now + 60) | changes


@pytest.mark.parametrize('change', [
    {'roles': {}}, {'roles': {'d4-execute-shell': 'manager'}},
    {'roles': {'d4-deliver': 'viewer'}}, {'lease': '../not-a-lease'},
    {'image': 'https://candidate.invalid/not-trusted'},
])
def test_provider_only_accepts_fixed_scenarios_and_roles(provider, change):
    base = {'lease': LEASE, 'roles': ROLES}
    assert provider.request(json.dumps(base)) == (LEASE, ROLES)
    with pytest.raises(RuntimeError):
        provider.request(json.dumps(base | change))


def test_preview_provisioner_issues_current_cases_once(provider, tmp_path, monkeypatch):
    test_binding = binding()
    queue_root = tmp_path / 'queue'
    queue_root.mkdir()
    run_root = tmp_path / 'run'
    run_root.mkdir()
    test_profile = {'binding': test_binding, 'portal_gid': 500, 'cases': {
        'd4-revoke': {'task_id': str(uuid4())},
    }}
    events = []
    monkeypatch.setattr(provider, 'QUEUE_ROOT', queue_root)
    monkeypatch.setattr(provider, 'RUN_ROOT', run_root)
    monkeypatch.setattr(provider, 'hold_test_slot', nullcontext)
    monkeypatch.setattr(provider, 'trusted_directory', lambda *args, **kwargs: None)
    monkeypatch.setattr(provider, 'database_binding', lambda *args: SLOT)
    monkeypatch.setattr(provider, 'read_owned', lambda path, *_args, **_kwargs: path.read_bytes())
    monkeypatch.setattr(provider, 'provider_config', lambda: {'origin': ORIGIN})
    monkeypatch.setattr(provider, 'validate_config', lambda _: None)
    monkeypatch.setattr(provider, 'load_profile', lambda path: json.loads(path.read_text()))

    def allocate(slot, allocation, _, roles, native):
        assert slot == SLOT and roles == ROLES and native == 'assets'
        events.append('allocate')
        allocation.mkdir()

    def provision(lease, *, guard):
        assert lease == LEASE and guard is nullcontext
        events.append('provision')
        (queue_root / 'd4' / lease / 'profile.json').write_text(json.dumps(test_profile))

    def issue(profile, origin, *, scenario_roles, guard):
        assert profile.parent.name == LEASE and origin == ORIGIN and scenario_roles == ROLES and guard is nullcontext
        events.append('issue')
        target = run_root / LEASE
        target.mkdir()
        portal = dict(binding=test_binding, origin=ORIGIN, scenario_roles=ROLES,
                      executor_socket=str(provider.socket_path_for(LEASE)),
                      tasks={'d4-revoke': test_profile['cases']['d4-revoke']['task_id']})
        (target / 'portal.json').write_text(json.dumps(portal))

    monkeypatch.setattr(provider, 'allocate', allocate)
    monkeypatch.setattr(provider, 'approved_assets', lambda config, scenarios: 'assets')
    monkeypatch.setattr(provider, 'provision', provision)
    monkeypatch.setattr(provider, 'issue', issue)
    monkeypatch.setattr(provider, 'start_portal', lambda *args: events.append('health'))

    expected = {'state': 'ready', 'url': ORIGIN + '/', 'expires_at': test_binding['expires_at'],
                'scenarios': ['d4-revoke']}
    assert provider.prepare(LEASE, ROLES) == expected
    assert provider.prepare(LEASE, ROLES) == expected
    assert events == ['allocate', 'provision', 'issue', 'health', 'health']
    assert provider.prepare(LEASE, {'d4-revoke': 'manager'}) == provider.blocked('portal-unavailable')
    allocation = queue_root / 'd4' / LEASE
    receipts = allocation / 'receipts'
    receipts.mkdir()
    old_receipt = receipts / 'd4-revoke.json'
    old_receipt.write_text('old issuance')
    previous = dict(test_binding)
    test_binding.update(issued_at=int(time()) - 600, expires_at=int(time()) - 1)
    (allocation / 'profile.json').write_text(json.dumps(test_profile))

    def retire(lease, *, phase):
        assert lease == LEASE and phase == 'testing' and old_receipt.exists()
        events.append('retire')
        shutil.rmtree(allocation)
        shutil.rmtree(run_root / lease)
        test_binding.update(binding(expires_at=previous['expires_at'] + 600))
        test_profile['cases']['d4-revoke']['task_id'] = str(uuid4())

    monkeypatch.setattr(provider, 'cleanup', retire)
    renewed = provider.prepare(LEASE, ROLES)
    assert renewed == expected | {'expires_at': test_binding['expires_at']}
    assert previous['report_id'] != test_binding['report_id']
    assert not old_receipt.exists()
    assert events == ['allocate', 'provision', 'issue', 'health', 'health',
                      'retire', 'allocate', 'provision', 'issue', 'health']


def test_missing_reviewed_runtime_does_not_allocate(provider, monkeypatch, tmp_path):
    def unavailable(*_):
        raise FileNotFoundError('a private host path')
    monkeypatch.setattr(provider, 'provider_config', lambda: {'origin': ORIGIN})
    monkeypatch.setattr(provider, 'QUEUE_ROOT', tmp_path)
    monkeypatch.setattr(provider, 'hold_test_slot', nullcontext)
    monkeypatch.setattr(provider, 'trusted_directory', lambda *args, **kwargs: None)
    monkeypatch.setattr(provider, 'database_binding', lambda *args: SLOT)
    monkeypatch.setattr(provider, 'approved_assets', unavailable)
    monkeypatch.setattr(provider, 'allocate', lambda *args: pytest.fail('tried to create a case'))
    assert provider.prepare(LEASE, ROLES) == {'state': 'blocked', 'reason': 'runtime-unavailable'}


def test_allocator_only_creates_the_requested_case(provider, monkeypatch, tmp_path):
    module = importlib.import_module('allocate')
    calls = []
    monkeypatch.setattr(module, 'published_images', lambda *args: ('candidate-image', 'database-image', (70, 70)))
    monkeypatch.setattr(module, 'docker_inventory', lambda *args: [])
    monkeypatch.setattr(module, 'create_network', lambda *args: ('network', '172.19.0.0/16'))

    def allocate_case(lease, name, *args):
        assert lease == LEASE
        calls.append(name)
        return {'api_container_id': 'candidate'}

    monkeypatch.setattr(module, 'allocate_case', allocate_case)
    monkeypatch.setattr(module, 'permitted_cells', lambda prepared, binding: None)
    allocation = tmp_path / 'd4' / LEASE
    allocation.parent.mkdir()
    module.allocate(SLOT, allocation, {'revoke_image': 'reviewed-receiver'}, ROLES, None)
    prepared = json.loads((allocation / 'prepared.json').read_text())
    assert calls == ['revoke']
    assert prepared['cases'] == {'d4-revoke': {'api_container_id': 'candidate', 'revoke_image_id': 'reviewed-receiver'}}
    assert all(prepared['binding'][key] == value for key, value in SLOT.items())


def test_health_is_bound_to_lease_and_requires_a_live_socket(provider, monkeypatch):
    browser = importlib.import_module('browser')
    test_binding = binding()
    path = '/run/fixture/executor.sock'
    config = dict(binding=test_binding, executor_socket=path)

    def no_invocation(_):
        pytest.fail('health invoked the scenario')

    handler_type = browser.handler(config, no_invocation)
    handler = handler_type.__new__(handler_type)
    handler.path = '/healthz'
    headers = {}
    statuses = []
    monkeypatch.setattr(handler, 'send_response', statuses.append)
    monkeypatch.setattr(handler, 'send_header', headers.__setitem__)
    monkeypatch.setattr(handler, 'end_headers', lambda: None)
    monkeypatch.setattr(handler, 'show', lambda status, *_: statuses.append(status))
    monkeypatch.setattr(browser, 'trusted_executor_socket', lambda socket: None)
    handler.do_GET()
    assert statuses == [200]
    assert headers['X-OpenQMS-Test-PR'] == str(SLOT['pr'])
    assert headers['X-OpenQMS-Test-Version'] == SLOT['merge']
    assert headers['X-OpenQMS-Test-Lease'] == LEASE
    assert headers['Cache-Control'] == 'no-store'
    assert not any(test_binding['report_id'] in value for value in headers.values())

    def no_socket(_):
        raise FileNotFoundError

    monkeypatch.setattr(browser, 'trusted_executor_socket', no_socket)
    handler.do_GET()
    assert statuses == [200, 503]
    test_binding['expires_at'] = 1
    handler.do_GET()
    assert statuses == [200, 503, 410]


def test_ingress_rejects_old_lease_on_the_same_published_commit(provider, monkeypatch):
    target = ORIGIN + '/healthz'
    test_binding = binding()
    headers = {
        'X-OpenQMS-D4-Binding': provider.binding_fingerprint(test_binding),
        'X-OpenQMS-Test-Version': SLOT['merge'],
        'X-OpenQMS-Test-PR': str(SLOT['pr']),
    }
    requests = []

    def open_probe(probe, *, timeout):
        requests.append(probe)
        assert probe.full_url == target
        assert timeout == 4
        lease = 'f' * 32 if len(requests) == 1 else LEASE
        return nullcontext(SimpleNamespace(
            status=200, url=target, headers=headers | {'X-OpenQMS-Test-Lease': lease},
        ))

    monkeypatch.setattr(provider.urllib.request, 'build_opener',
                        lambda *handlers: SimpleNamespace(open=open_probe))
    monkeypatch.setattr(provider, 'time', SimpleNamespace(monotonic=lambda: 0, sleep=lambda _: None))

    provider.check_ingress(ORIGIN, test_binding)
    assert len(requests) == 2


def test_testing_cleanup_only_accepts_an_expired_profile_for_this_lease(provider, tmp_path, monkeypatch):
    module = importlib.import_module('cleanup')
    monkeypatch.setattr(module, 'read_owned', lambda path, *_args, **_kwargs: path.read_bytes())
    profile_path = tmp_path / 'profile.json'
    profile_path.write_text(json.dumps({'binding': binding()}))
    with pytest.raises(RuntimeError, match='requires lease retirement or expiry'):
        module.verify_testing_cleanup(tmp_path, SLOT)
    expired = binding(issued_at=int(time()) - 100, expires_at=int(time()) - 1)
    profile_path.write_text(json.dumps({'binding': expired | {'plan': 'f' * 64}}))
    with pytest.raises(RuntimeError, match='requires lease retirement or expiry'):
        module.verify_testing_cleanup(tmp_path, SLOT)
    profile_path.write_text(json.dumps({'binding': expired}))
    module.verify_testing_cleanup(tmp_path, SLOT)


def test_cleanup_can_remove_recorded_incomplete_native_staging(provider, tmp_path, monkeypatch):
    module = importlib.import_module('cleanup')
    runtime = SimpleNamespace(root=tmp_path / 'active', nonce='a' * 64)
    staging = module.runtime_staging_path(runtime.root)
    staging.mkdir()
    (staging / 'partial-file').touch()
    monkeypatch.setattr(module, 'trusted_directory', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'objects', lambda *args: [])
    module.reclaim_runtime(runtime, None)
    assert not staging.exists()
