"""The real orchestration must refuse secrets before every observed safety gate."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('runtime_controller_helpers', Path(__file__).parents[1] / 'helpers.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
p = Path(__file__).parents[2] / 'runtime_controller.py'
r = h.load('runtime_controller') if p.exists() else None
c = h.load('contracts')
j = h.load('journal')
NONCE, CID = 'a' * 64, 'c' * 64
PERMIT = c.DeploymentPermit('sha256:' + 'f' * 64, c.WORKER_SHA256, 2001, 2002, 18777)
CONFIG = c.PrivateConfig('http://127.0.0.1:18777', 'synthetic',
                         '00000000-0000-0000-0000-000000000001', 'synthetic-private-secret',
                         'request', '00000000-0000-0000-0000-000000000002')


class Store:
    def __init__(self):
        self.value = dict(nonce=NONCE, revision=0, phase='prepare', deadline_ns=30 * 10**9,
                          invalidated=False, receiver_id=None, snapshot=None,
                          create_converged=False, watchdog_bound_verified=False, preparation={'boot_id': 'synthetic-boot'},
                          controller_invocation_id=None, watchdog_invocation_id='b' * 32)
    def read(self, nonce): return dict(self.value)
    def update(self, nonce, revision, **changes):
        assert revision == self.value['revision']
        self.value.update(changes)
        self.value['revision'] += 1
        return self.read(nonce)
    def merge(self, nonce, **changes):
        return self.update(nonce, self.value['revision'], **changes)
    def claim_invocation(self, nonce, field, value):
        assert self.value[field] in (None, value)
        return self.merge(nonce, **{field: value})
    def begin_delivery(self, nonce):
        assert self.value['watchdog_bound_verified']
        return self.update(nonce, self.value['revision'], phase='delivery', deadline_ns=60 * 10**9)


def exercise(tmp_path, *, watchdog=True, identity=True, network=True, preparation=True, overflow=False, lose_on_partial=False, invalidate_during_network=False, busy_reads=0):
    assert r is not None, 'real controller adapter missing'
    folder = tmp_path / 'journal'
    folder.mkdir(mode=0o700)
    journal = j.IntentJournal(folder, clock=lambda: 0)
    journal.record_intent(NONCE)
    store, writes, events = Store(), [], []
    original_read = store.read
    remaining_busy = [busy_reads]
    def contended(nonce):
        if remaining_busy[0]:
            remaining_busy[0] -= 1
            raise h.load('runtime_state').StateBusy()
        return original_read(nonce)
    store.read = contended
    class Api:
        def create(self, nonce, expected_revision):
            events.append('create')
            journal.transition(nonce, expected_revision, j.CREATE_INFLIGHT)
            return SimpleNamespace(kind='created', container_id=CID)
        def start(self, locator): events.append('start'); return SimpleNamespace(done=True)
        def attach(self, locator): events.append('attach')
    class Channel:
        def write(self, data, deadline_ns):
            writes.append(bytes(data[:2] if lose_on_partial else data))
            return len(writes[-1])
        def close_stdin(self): events.append('stdin_closed')
        def chunks(self, deadline_ns):
            yield b'x' * (4097 if overflow else 40)
        def close(self): events.append('channel_closed')
    binding = SimpleNamespace(snapshot=lambda: {'safe': True, 'boot_id': 'synthetic-boot'}, close=lambda: events.append('binding_closed'))
    class Collector:
        def bind(self, nonce, cid, deadline_ns): events.append('bind'); return binding
        def revalidate(self, value, deadline_ns, delivery=True): return object() if identity else None
    def watched(state, deadline):
        if state['snapshot'] is not None:
            store.value['watchdog_bound_verified'] = watchdog
        return watchdog and not (lose_on_partial and writes)
    network_calls = []
    def network_checked(binding, deadline):
        network_calls.append(True)
        if invalidate_during_network and len(network_calls) == 2:
            store.value['invalidated'] = True
        return network
    result = r.drive(NONCE, store=store, journal=journal, api=Api(),
                     transport=SimpleNamespace(take_attach=lambda cid: Channel()),
                     collector=Collector(), permit=PERMIT,
                     config_loader=lambda: CONFIG, invocation_id='d' * 32,
                     watchdog_probe=watched, network_probe=network_checked,
                     preparation_probe=lambda state, deadline: preparation,
                     exited_probe=lambda cid, deadline: True,
                     stop=lambda binding: events.append('stop') or 'isolation_terminated',
                     clock=lambda: 0, sleep=lambda delay: None)
    return result, writes, events


def test_verified_real_sequence_sends_once_and_only_infrastructure(tmp_path):
    result, writes, events = exercise(tmp_path)
    assert result.as_dict() == {'status': 'isolation_exited'}
    assert writes == [CONFIG.to_stdin()]
    assert events.index('bind') < events.index('stdin_closed') < events.index('stop')
    assert events.index('stop') < events.index('binding_closed')


@pytest.mark.parametrize('gate', ['watchdog', 'identity', 'network', 'preparation'])
def test_failure_at_any_real_gate_prevents_config_write(tmp_path, gate):
    result, writes, _ = exercise(tmp_path, **{gate: False})
    assert not writes
    assert result.status != 'isolation_exited'


def test_watchdog_loss_during_partial_stdin_never_continues(tmp_path):
    result, writes, _ = exercise(tmp_path, lose_on_partial=True)
    assert len(writes) == 1 and writes[0] == CONFIG.to_stdin()[:2]
    assert result.status != 'isolation_exited'


def test_output_overflow_is_reclaimed_without_forwarding_payload(tmp_path):
    result, _, events = exercise(tmp_path, overflow=True)
    assert result.as_dict() == {'status': 'isolation_terminated'}
    assert 'stop' in events
    # Configuration was already fully delivered and half-closed. Release the
    # overflowing output pipe before Engine exit verification, retaining kernel
    # identity until that verification is finished.
    assert events.index('stdin_closed') < events.index('channel_closed') < events.index('stop')
    assert events.index('stop') < events.index('binding_closed')


def test_invalidation_during_slow_verification_is_checked_again_before_write(tmp_path):
    result, writes, _ = exercise(tmp_path, invalidate_during_network=True)
    assert writes == []
    assert result.status != 'isolation_exited'


def test_normal_short_state_lock_contention_is_retried_without_replay(tmp_path):
    result, writes, events = exercise(tmp_path, busy_reads=2)
    assert result.status == 'isolation_exited'
    assert len(writes) == 1 and events.count('create') == 1


def test_interrupted_partial_stdin_is_reclaimed_before_eof(tmp_path):
    result, writes, events = exercise(tmp_path, lose_on_partial=True)
    assert len(writes) == 1
    assert events.index('stop') < events.index('stdin_closed')
    assert events.index('stop') < events.index('binding_closed')


def test_stop_signal_uses_a_content_free_internal_exception():
    assert hasattr(r, 'StopRequested'), 'missing graceful stop signal contract'
    assert hasattr(r, '_stop_signal')
    with pytest.raises(r.StopRequested, match='controller_stopping'):
        r._stop_signal(15, None)
