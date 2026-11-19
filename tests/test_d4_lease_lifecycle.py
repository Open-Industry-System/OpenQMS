from contextlib import nullcontext
import importlib
import json
from pathlib import Path
import secrets
from time import time
from uuid import uuid4

import pytest


MODULES = Path(__file__).parents[1] / 'deploy' / 'd4-acceptance'
LEASE = 'a' * 32


@pytest.fixture
def services(monkeypatch):
    monkeypatch.syspath_prepend(str(MODULES))
    return (importlib.import_module('cleanup'), importlib.import_module('portal_issue'),
            importlib.import_module('provision'))


def binding():
    now = int(time())
    return dict(pr=45, head='b' * 40, merge='c' * 40, plan='d' * 64, lease=LEASE,
                report_id=str(uuid4()), issued_at=now - 1, expires_at=now + 60)


def test_portal_credential_is_generated_once_root_private_and_bound(tmp_path, services, monkeypatch, capsys):
    _, portal, _ = services
    test_binding = binding()
    monkeypatch.setattr(portal, 'QUEUE_ROOT', tmp_path)
    run_root = tmp_path / 'run'
    run_root.mkdir(mode=0o700)
    monkeypatch.setattr(portal, 'RUN_ROOT', run_root)
    monkeypatch.setattr(portal, 'hold_test_slot', nullcontext)
    monkeypatch.setattr(portal, 'trusted_directory', lambda *args, **kwargs: None)
    monkeypatch.setattr(portal, 'root_private', lambda *args, **kwargs: None)
    monkeypatch.setattr(portal, 'load_profile', lambda _: {'binding': test_binding, 'cases': {
        'd4-deliver': {'task_id': str(uuid4())}, 'd4-revoke': {'task_id': str(uuid4())},
    }})
    slot = dict(test_binding, head='e' * 40)
    monkeypatch.setattr(portal, 'database_binding', lambda *args: slot)
    profile = tmp_path / 'd4' / LEASE / 'profile.json'
    profile.parent.mkdir(parents=True)
    with pytest.raises(ValueError, match='active test slot'):
        portal.issue(profile, 'https://test.example')
    assert not (run_root / LEASE).exists()
    slot.update(test_binding)
    portal.issue(profile, 'https://test.example')
    handoff = profile.parent / 'portal-credential.json'
    handed = json.loads(handoff.read_text())
    verifier = json.loads((run_root / LEASE / 'portal.json').read_text())
    assert verifier['binding'] == test_binding and verifier['username'] == handed['username']
    assert handed['password'] not in json.dumps(verifier)
    assert handoff.stat().st_mode & 0o777 == 0o600
    assert capsys.readouterr() == ('', '')
    with pytest.raises(ValueError, match='already'):
        portal.issue(profile, 'https://test.example')
    assert json.loads(handoff.read_text()) == handed


def test_cleanup_only_reclaims_dedicated_owned_inventory(tmp_path, services, monkeypatch):
    cleanup, _, _ = services
    monkeypatch.setattr(cleanup, 'QUEUE_ROOT', tmp_path)
    monkeypatch.setattr(cleanup, 'RUN_ROOT', tmp_path / 'run')
    monkeypatch.setattr(cleanup, 'trusted_directory', lambda *args, **kwargs: None)
    allocation = tmp_path / 'd4' / LEASE
    allocation.mkdir(parents=True)
    other = allocation.with_name(secrets.token_hex(16))
    other.mkdir()
    portal = tmp_path / 'run' / LEASE
    portal.mkdir(parents=True)
    retired = False

    def verify(lease, phase):
        assert (lease, phase) == (LEASE, 'releasing')
        if not retired:
            raise ValueError('D4 lease phase does not authorize this action')
        return binding()

    monkeypatch.setattr(cleanup, 'database_binding', verify)

    def list_objects(kind, label, _):
        assert label == cleanup.LEASE_LABEL + '=' + LEASE
        return inventory[kind]

    prefix = 'openqms-d4-' + LEASE
    container_id = 'b' * 64
    inventory = {
        'container': [{
            'Id': container_id, 'Name': '/' + prefix + '-deliver-api',
            'Config': {'Labels': {cleanup.LEASE_LABEL: LEASE, cleanup.ROLE_LABEL: 'api'}},
            'NetworkSettings': {'Networks': {prefix: {}}}, 'HostConfig': {},
        }],
        'network': [{
            'Id': 'c' * 64, 'Name': prefix, 'Labels': {cleanup.LEASE_LABEL: LEASE},
            'Internal': True, 'Driver': 'bridge',
            'Containers': {container_id: {}},
        }],
        'volume': [{
            'Name': prefix + '-deliver-postgres-data', 'Labels': {cleanup.LEASE_LABEL: LEASE},
            'Driver': 'local',
        }],
    }
    monkeypatch.setattr(cleanup, 'objects', list_objects)
    monkeypatch.setattr(cleanup, 'native_runtimes', lambda *args: ())
    events = []
    monkeypatch.setattr(cleanup, 'stop_unit', lambda unit, run: events.append(unit))

    def remove(*args):
        assert args[:3] == cleanup.DOCKER and args[4] == 'rm'
        kind, identity = args[3], args[-1]
        assert identity == inventory[kind][0]['Name' if kind == 'volume' else 'Id']
        del inventory[kind][0]
        events.append(kind)

    with pytest.raises(ValueError, match='phase'):
        cleanup.cleanup(LEASE, run=remove)
    retired = True
    inventory['network'][0]['Containers']['f' * 64] = {}
    with pytest.raises(RuntimeError, match='network ownership'):
        cleanup.cleanup(LEASE, run=remove)
    assert not events and allocation.exists()
    del inventory['network'][0]['Containers']['f' * 64]
    cleanup.cleanup(LEASE, run=remove)
    assert events[-3:] == ['container', 'network', 'volume']
    assert all(LEASE in unit for unit in events[:2])
    assert not allocation.exists() and not portal.exists() and other.is_dir()
    cleanup.cleanup(LEASE, run=remove)
    assert len(events) == 5


def test_provision_rejects_a_task_from_a_different_report(services, monkeypatch):
    _, _, provision = services
    test_binding = binding()
    initial = {key: str(uuid4()) for key in ('tenant_id', 'installation_id', 'executor_user_id', 'report_id')}
    initial.update(schema='tenant_synthetic', generation=1)
    task = dict(initial, task_id=str(uuid4()), grant_id=str(uuid4()))
    stages = []

    def application(api, arguments, *, data):
        assert api == 'f' * 64
        assert json.loads(data)['binding'] == test_binding
        stages.append(arguments[-1])
        return json.dumps(initial if arguments[-1] == 'prepare' else task).encode()

    monkeypatch.setattr(provision, 'application', application)
    monkeypatch.setattr(provision, 'wait_health', lambda *args: None)
    monkeypatch.setattr(provision, 'command', lambda *args: None)
    cell = dict(api_container_id='f' * 64, db_host='isolated-postgres', db_system_identifier='99',
                api_port=8080)
    with pytest.raises(RuntimeError, match='seeded allocation'):
        provision.seed(cell, test_binding, 'reviewed helper', Path('/unused'))
    assert stages == ['prepare', 'task']
