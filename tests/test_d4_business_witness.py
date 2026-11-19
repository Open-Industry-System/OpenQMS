from dataclasses import replace
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / 'deploy/d4-acceptance/witness.py'
spec = importlib.util.spec_from_file_location('d4_business_witness', PATH)
witness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(witness)
ids = tuple(f'00000000-0000-4000-8000-{i:012d}' for i in range(1, 7))
report, task, installation, grant, run_id, tenant = ids
lease = 'a' * 32
container = 'b' * 64
network = 'c' * 64
image = 'sha256:' + 'd' * 64
system_identifier = '7812345678901234567'
scope = (report, task, installation, grant)
BASELINE = witness.Snapshot(*scope, run_id, 'ready', 'pending', 0, 0, True, True, 0, 0, 0, 0, False)
COMPLETED = replace(BASELINE, task_status='completed', run_status='completed', lease_epoch=2,
                    accepted_message_seq=1, receipts=1, committed_audits=1, finish_audits=1)
ACTIVE = replace(BASELINE, run_status='active', lease_epoch=1, run_live=True, receipts=1, committed_audits=1)
REVOKED = replace(ACTIVE, grant_enabled=False, grant_live=False, revoke_audits=1)
OBSERVATION = dict(report_id=report, task_id=task, installation_id=installation, grant_id=grant,
                   run_id=run_id, authorized_status=200, revoked_status=401, revoked_body_received=False)


def owned():
    return witness.PsqlWitness(container, image, system_identifier, lease, tenant, 'tenant_synthetic', 8)


def test_proof_requires_exact_real_commit_and_denial():
    witness.verify_delivery(BASELINE, COMPLETED)
    witness.verify_revocation(ACTIVE, REVOKED, OBSERVATION)
    for edit in [{'committed_audits': 0}, {'receipts': 2}, {'accepted_message_seq': 0},
                 {'finish_audits': 0}, {'lease_epoch': 1}, {'run_status': 'active'}, {'task_id': report}]:
        with pytest.raises(ValueError):
            witness.verify_delivery(BASELINE, replace(COMPLETED, **edit))
    for edit in [{'revoke_audits': 0}, {'receipts': 2}, {'lease_epoch': 2}, {'run_id': grant},
                 {'run_live': False}, {'grant_enabled': True}, {'committed_audits': 2}]:
        with pytest.raises(ValueError):
            witness.verify_revocation(ACTIVE, replace(REVOKED, **edit), OBSERVATION)
    for edit in [{'revoked_body_received': True}, {'authorized_status': 404}, {'run_id': task},
                 {'revoked_status': 403}, {'extra': 'rejected'}]:
        with pytest.raises(ValueError):
            witness.verify_revocation(ACTIVE, REVOKED, dict(OBSERVATION, **edit))


@pytest.mark.parametrize('unsafe', ['extra-network', 'published-port', 'external-network', 'wrong-lease', None])
def test_snapshot_never_runs_sql_on_unowned_database(monkeypatch, unsafe):
    commands = []
    labels = {witness.LEASE_LABEL: lease, witness.ROLE_LABEL: 'postgres'}
    container_data = {
        'Id': container, 'Image': image, 'State': {'Running': True}, 'Config': {'Labels': labels},
        'HostConfig': {'PortBindings': None},
        'NetworkSettings': {'Networks': {'openqms-d4-' + lease: {'NetworkID': network}}, 'Ports': {}},
    }
    network_data = {
        'Id': network, 'Name': 'openqms-d4-' + lease, 'Internal': True, 'Driver': 'bridge',
        'Labels': {witness.LEASE_LABEL: lease},
    }
    if unsafe == 'extra-network':
        container_data['NetworkSettings']['Networks']['production'] = {}
    elif unsafe == 'published-port':
        container_data['HostConfig']['PortBindings'] = {'5432': []}
    elif unsafe == 'external-network':
        network_data['Internal'] = False
    elif unsafe == 'wrong-lease':
        labels[witness.LEASE_LABEL] = 'f' * 32

    def checked(*args, text=None, deadline=None):
        assert deadline == 100
        commands.append((args, text))
        if args[-3:-1] == ('container', 'inspect'):
            return [container_data]
        if args[-3:-1] == ('network', 'inspect'):
            return [network_data]
        assert unsafe is None
        assert '--no-password' in args and '65534:65534' in args
        assert witness.DATABASE in args and witness.ROLE in args
        assert 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;' in text
        assert text.index('pg_control_system') < text.index('agent_tasks')
        assert 'public.tenants' in text and 'generation = 8' in text
        assert 'd4_root_cause' not in text and 'secret_hash' not in text
        return dict(COMPLETED.__dict__)

    monkeypatch.setattr(witness, 'checked_output', checked)
    if unsafe:
        with pytest.raises(ValueError):
            owned().snapshot(*scope, run_id, deadline=100)
        assert not any(text is not None for _, text in commands)
    else:
        assert owned().snapshot(*scope, run_id, deadline=100) == COMPLETED
        with pytest.raises(ValueError, match='identity mismatch'):
            owned().snapshot(*scope, installation, deadline=100)


def test_no_schema_or_subject_injection():
    with pytest.raises(ValueError, match='dedicated tenant'):
        witness.PsqlWitness(container, image, system_identifier, lease, tenant, 'public', 0)
    with pytest.raises(ValueError, match='UUID'):
        owned().snapshot_sql(report, "x'; SELECT 1--", installation, grant)


def test_command_failure_does_not_disclose_subprocess_output(monkeypatch):
    monkeypatch.setattr(witness.subprocess, 'run', lambda *_, **__: SimpleNamespace(
        returncode=1, stdout='private evidence', stderr='private config',
    ))
    with pytest.raises(ValueError, match='^trusted witness command failed$'):
        witness.checked_output('/usr/bin/false')


def test_expired_deadline_skips_the_command(monkeypatch):
    monkeypatch.setattr(witness.time, 'monotonic', lambda: 100)
    monkeypatch.setattr(witness.subprocess, 'run', lambda *_, **__: pytest.fail('command executed'))
    with pytest.raises(TimeoutError, match='deadline expired'):
        witness.checked_output('/usr/bin/false', deadline=100)
