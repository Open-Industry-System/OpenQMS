from dataclasses import replace
from importlib import import_module
from io import BytesIO
from pathlib import Path
from time import monotonic

import pytest


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / 'deploy' / 'd4-acceptance'))
    return import_module('revoke_runtime')


def snapshots():
    from witness import Snapshot

    baseline = Snapshot(report_id='report', task_id='task', installation_id='installation',
                        grant_id='grant', run_id='run', task_status='ready', run_status='pending',
                        lease_epoch=0, accepted_message_seq=0, grant_enabled=True, grant_live=True,
                        receipts=0, committed_audits=0, revoke_audits=0, finish_audits=0, run_live=False)
    before = replace(baseline, run_status='active', lease_epoch=1, run_live=True,
                     receipts=1, committed_audits=1)
    after = replace(before, grant_enabled=False, grant_live=False, revoke_audits=1)
    return baseline, before, after


def test_revoke_pipe_authorizes_only_after_independent_database_read(runtime, monkeypatch):
    baseline, before, after = snapshots()
    identity = {name: getattr(baseline, name) for name in
                ('report_id', 'task_id', 'installation_id', 'grant_id', 'run_id')}
    frames = iter([dict(identity, stage='authorized'),
                   dict(identity, authorized_status=200, revoked_status=401, revoked_body_received=False)])
    monkeypatch.setattr(runtime, 'read_line', lambda *_: next(frames))

    class Pipe(BytesIO):
        def close(self):
            pass

    class Receiver:
        stdin = Pipe()
        stdout = object()

        def wait(self, *, timeout):
            assert timeout > 0
            assert self.stdin.getvalue().splitlines() == [b'{"receiver":"synthetic"}', b'revoke']
            return 0

    process = Receiver()
    readings = iter([before, after])

    def snapshot(deadline):
        assert deadline > monotonic()
        state = next(readings)
        assert process.stdin.getvalue().endswith(b'revoke\n') == (state == after)
        return state

    assert runtime.exchange(process, {'receiver': 'synthetic'}, baseline, snapshot,
                            monotonic() + 2) == (before, after)


@pytest.mark.parametrize('invalid', ['wrong-run', 'missing-delivery'])
def test_revoke_pipe_never_permits_a_mismatched_authorized_read(runtime, monkeypatch, invalid):
    from types import SimpleNamespace

    baseline, before, _ = snapshots()
    frame = dict(stage='authorized', task_id='task', run_id='run', report_id='report',
                 installation_id='installation', grant_id='grant')
    if invalid == 'wrong-run':
        frame['run_id'] = 'old-run'
    else:
        before = replace(before, receipts=0, committed_audits=0)
    monkeypatch.setattr(runtime, 'read_line', lambda *_: frame)
    process = SimpleNamespace(stdin=BytesIO(), stdout=object())
    with pytest.raises(RuntimeError, match='identity changed|not witnessed'):
        runtime.exchange(process, {'receiver': 'synthetic'}, baseline, lambda _: before, monotonic() + 2)
    assert process.stdin.getvalue() == b'{"receiver":"synthetic"}\n'


def test_linux_receiver_creation_is_lease_bound_and_has_no_host_inputs(runtime, monkeypatch):
    lease = 'a' * 32
    case = {'api_container_id': 'b' * 64, 'revoke_image_id': 'sha256:' + 'c' * 64}
    calls = []
    monkeypatch.setattr(runtime, 'docker', lambda *args: calls.append(args) or ('d' * 64))
    monkeypatch.setattr(runtime, 'docker_inventory', lambda *_: ([{
        'Id': case['api_container_id'], 'Name': '/openqms-d4-' + lease + '-revoke-api',
        'State': {'Running': True},
    }], [], []))
    assert runtime.create(case, lease) == 'd' * 64
    args, = calls
    assert args[-1] == case['revoke_image_id']
    assert all(flag in args for flag in ('--read-only', '--cap-drop', '--user', '--log-driver', '--pull=never'))
    assert args[args.index('--network') + 1] == 'container:' + case['api_container_id']
    assert not any(flag in args for flag in ('--mount', '--volume', '--env', '--privileged'))
