"""Real Engine objects with disclosed test-only visibility/session-I/O faults.

This is not native Docker creation timing and not an end-to-end daemon outage.
No platform authority, worker mutation, shared-daemon stop, or broad deletion.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex

import pytest

HERE = Path(__file__).resolve().parent
CASES = ('lost_create_reply', 'ambiguous_nonce', 'scoped_engine_io')


def local_probe():
    spec = importlib.util.spec_from_file_location('_create_faults_local', HERE / 'runtime_create_faults_probe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_visibility_fault_is_explicit_and_preserves_underlying_objects():
    probe = local_probe()
    nonce, cid = 'a' * 64, 'c' * 64
    class Engine:
        def __init__(self): self.calls = []
        def list_by_nonce(self, nonce, deadline_ns): self.calls.append(nonce); return (cid,)
    actual = Engine()
    records = []
    wrapped = probe.VisibilityEngine(actual, nonce, 3, records)
    assert [wrapped.list_by_nonce(nonce, 10) for _ in range(4)] == [(), (), (), (cid,)]
    assert [row['underlying_count'] for row in records] == [1, 1, 1, 1]
    assert [row['returned_count'] for row in records] == [0, 0, 0, 1]
    assert actual.calls == [nonce] * 4
    with pytest.raises(probe.CreateFaultFailure): wrapped.list_by_nonce('b' * 64, 10)


def test_local_registration_policy_never_erases_a_bad_initial_record():
    probe = local_probe()
    for value in ({'state': 'unresolved'}, {'state': 'bound'}, {'state': 'closed', 'closed_by': 'reclaim_verified'}):
        assert probe.retain_registration(value) is True


def test_local_cleanup_requires_complete_id_nonce_and_frozen_image():
    probe = local_probe()
    cid, nonce, image = 'c' * 64, 'a' * 64, 'sha256:' + 'd' * 64
    raw = {'Id': cid, 'Image': image, 'Config': {'Labels': {probe.RECEIVER_LABEL: nonce}}}
    probe.verify_owned(raw, cid, nonce, image)
    for field, value in (('Id', 'e' * 64), ('Image', 'sha256:' + 'e' * 64)):
        with pytest.raises(probe.CreateFaultFailure): probe.verify_owned({**raw, field: value}, cid, nonce, image)
    with pytest.raises(probe.CreateFaultFailure):
        probe.verify_owned({**raw, 'Config': {'Labels': {probe.RECEIVER_LABEL: 'f' * 64}}}, cid, nonce, image)


@pytest.mark.parametrize('case', CASES)
def test_real_runtime_create_fault_without_platform_authority(remote, case):
    image = os.environ.get('OPENQMS_ISOLATION_RECEIVER_IMAGE')
    assert image, 'explicit pinned receiver image required'
    spec = importlib.util.spec_from_file_location('_create_faults_bundle', HERE / 'test_runtime_wiring.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    bundle, digest = module._package_bundle()
    source = (HERE / 'runtime_create_faults_probe.py').read_text()
    values = dict(PACKAGE_B64=bundle, PACKAGE_SHA256=digest, CREATE_CASE=case,
        CREATE_PROBE_SHA256=hashlib.sha256(source.encode()).hexdigest(),
        WIRING_PROBE_SOURCE=(HERE / 'runtime_wiring_probe.py').read_text(),
        FAULT_PROBE_SOURCE=(HERE / 'runtime_faults_probe.py').read_text(),
        WIRE_FIXTURE_SOURCE=(HERE.parents[3] / 'backend/tests/e2e/d4_text_wire_fixture.py').read_text())
    script = ''.join(key + '=' + repr(value) + '\n' for key, value in values.items()) + source
    output = remote('sudo -n /usr/bin/python3 -I -S -B - ' + shlex.quote(image) +
                    " <<'D4_CREATE_FAULT'\n" + script + '\nD4_CREATE_FAULT\n', timeout=180, check=False)
    print(output)
    rows = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
    assert len(rows) == 1, output
    row = rows[0]
    assert row['case'] == case and row['verified'] is True and row['failure_code'] is None, row
    assert row['resources_cleaned'] and row['registration_retained'] and row['bad_initial_record_retained'], row
    assert row['secret_bytes_written'] == 0 and row['api_survived'] is True, row
    assert row['new_intent_blocked'] and row['delivery_blocked'], row
    assert row['journal_summary']['state'] != 'closed', row
    assert row['create_probe_sha256'] == values['CREATE_PROBE_SHA256'], row
    if case == 'lost_create_reply':
        assert row['timing_model'] == 'test_only_visibility_overlay_after_real_create', row
        assert [item['returned_count'] for item in row['visibility']] == [0, 0, 0, 1], row
        assert all(item['underlying_count'] == 1 for item in row['visibility']), row
        assert row['late_never_started_removed'] and row['create_converged'] is False, row
    elif case == 'ambiguous_nonce':
        assert row['ambiguous_exact_matches'] == 2 and row['all_three_unchanged'], row
    else:
        assert row['scope'] == 'direct_stop_adapter_session_io_not_whole_supervision_chain', row
        assert row['fresh_without_fd_unknown'] and row['fresh_target_survived'], row
        assert row['original_fd_kernel_empty'] and row['kernel_elapsed_ns'] <= 5_000_000_000, row
        assert row['infrastructure_result'] == 'isolation_unknown', row
    assert 'runtime_create_fault_verified:' + case in output.splitlines(), output


def test_local_management_failure_is_scoped_before_raising_unavailable():
    probe = local_probe()
    class EngineError(OSError): pass
    failed = probe.ScopedUnavailable('a' * 64, EngineError)
    with pytest.raises(EngineError, match='engine_unavailable'):
        failed.list_by_nonce('a' * 64, 10)
    assert failed.calls == 1
    with pytest.raises(probe.CreateFaultFailure):
        failed.list_by_nonce('b' * 64, 10)
    assert failed.calls == 1


def test_local_probe_does_not_delete_unknown_roots_or_guess_cleanup_targets():
    source = (HERE / 'runtime_create_faults_probe.py').read_text()
    assert 'shutil.rmtree' not in source and 'docker.service' not in source.replace('Never touch docker.service.', '')
    assert "for item in reversed(objects)" in source
    assert "verify_owned(raw, item['id'], item['nonce'], item['image_id'])" in source
    assert "engine.remove(item['id']" in source
    assert "bad-registration-initial.json" in source and "bad-session-initial.json" in source


def test_local_combined_delivery_gate_discloses_journal_and_registration(monkeypatch):
    import sys
    import types
    probe = local_probe()
    class SessionBlocked(Exception): pass
    monkeypatch.setitem(sys.modules, 'agent_d4_isolation', types.ModuleType('agent_d4_isolation'))
    monkeypatch.setitem(sys.modules, 'agent_d4_isolation.journal', types.SimpleNamespace(SessionBlocked=SessionBlocked))
    class Journal:
        def admission(self): return types.SimpleNamespace(may_open_session=False)
        def delivery_gate(self, nonce): return types.SimpleNamespace(allowed=True)
        def record_intent(self, nonce): raise SessionBlocked()
    class Store:
        invalidated = True
        def read(self, nonce): return {'invalidated': self.invalidated}
    store = Store()
    assert probe.prove_blocked(Journal(), 'a' * 64, store) == {
        'journal_delivery_gate_allowed': True, 'registration_invalidated': True}
    store.invalidated = False
    with pytest.raises(probe.CreateFaultFailure, match='unknown_allowed_delivery'):
        probe.prove_blocked(Journal(), 'a' * 64, store)


def test_local_first_inspect_failure_keeps_full_id_for_exact_created_cleanup():
    probe = local_probe()
    cid, nonce, image = 'c' * 64, 'a' * 64, 'sha256:' + 'd' * 64
    objects, persisted, removed = [], [], []
    class Engine:
        calls = 0
        def inspect(self, value, deadline_ns):
            self.calls += 1
            if self.calls == 1: raise OSError('engine_unavailable')
            return {'Id': cid, 'Image': image, 'Config': {'Labels': {probe.RECEIVER_LABEL: nonce}},
                    'State': {'Status': 'created', 'Running': False, 'Pid': 0}}
        def remove(self, value, deadline_ns): removed.append(value)
    class Collector:
        def verify_created(self, n, c, deadline_ns):
            assert (n, c) == (nonce, cid)
            return True
    engine = Engine()
    with pytest.raises(OSError):
        probe.observe_candidate(objects, cid, nonce, image, engine, lambda: persisted.append(objects[0]['id']))
    item = objects[0]
    probe.cleanup_candidate(item, engine, Collector(), [], lambda value: None)
    assert persisted == [cid] and removed == [cid] and objects == [item]


def test_local_start_then_first_bind_failure_rebinds_current_identity_for_cleanup():
    probe = local_probe()
    cid, nonce, image = 'c' * 64, 'a' * 64, 'sha256:' + 'd' * 64
    objects, bindings, events = [], [], []
    item = probe.register_candidate(objects, cid, nonce, image, lambda: None)
    class Engine:
        running = True
        def inspect(self, value, deadline_ns):
            assert value == cid
            return {'Id': cid, 'Image': image, 'Config': {'Labels': {probe.RECEIVER_LABEL: nonce}},
                    'State': {'Status': 'running' if self.running else 'exited', 'Running': self.running, 'Pid': 42 if self.running else 0}}
        def remove(self, value, deadline_ns):
            assert not self.running
            events.append(('remove', value))
    engine = Engine()
    class Binding:
        def signal(self, signal, deadline_ns):
            assert signal == 'SIGKILL'
            events.append(('signal', cid)); engine.running = False
        def tasks_remaining(self): return int(engine.running)
        def terminate(self, deadline_ns): raise AssertionError('fresh cleanup must use exact Engine signal')
    binding = Binding()
    class Collector:
        calls = 0
        def bind(self, n, c, deadline_ns):
            assert (n, c) == (nonce, cid)
            self.calls += 1
            if self.calls == 1: raise OSError('first_bind_failed')
            return binding
    collector = Collector()
    with pytest.raises(OSError): collector.bind(nonce, cid, 10)
    probe.cleanup_candidate(item, engine, collector, bindings, lambda value: events.append(('absent', value)))
    assert collector.calls == 2 and bindings == [binding]
    assert events == [('signal', cid), ('remove', cid), ('absent', cid)]


@pytest.mark.parametrize('mismatch', ('image', 'recipe'))
def test_local_cleanup_cannot_remove_unverified_current_candidate(mismatch):
    probe = local_probe()
    cid, nonce, image = 'c' * 64, 'a' * 64, 'sha256:' + 'd' * 64
    item = probe.register_candidate([], cid, nonce, image, lambda: None)
    removed = []
    class Engine:
        def inspect(self, value, deadline_ns):
            return {'Id': cid, 'Image': image if mismatch != 'image' else 'sha256:' + 'e' * 64,
                    'Config': {'Labels': {probe.RECEIVER_LABEL: nonce}},
                    'State': {'Status': 'created', 'Running': False, 'Pid': 0}}
        def remove(self, value, deadline_ns): removed.append(value)
    class Collector:
        def verify_created(self, n, c, deadline_ns): return mismatch == 'image'
    with pytest.raises(probe.CreateFaultFailure):
        probe.cleanup_candidate(item, Engine(), Collector(), [], lambda value: None)
    assert removed == []
