"""Opt-in original-cgroup-FD removal/replacement evidence, never I9 evidence."""
import hashlib
import json
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[2]


def test_deleted_original_cgroup_is_empty_without_following_replacement(remote):
    # Only current reviewed stdlib modules; no checkout, configuration or secrets.
    names = ('contracts', 'journal', 'identity', 'cgroup', 'linux_identity')
    sources = {name: (PACKAGE / (name + '.py')).read_text() for name in names}
    digest = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    probe = ('SOURCES = ' + repr(sources) + '\nSOURCE_SHA256 = ' + repr(digest) + '\n' +
             Path(__file__).with_name('cgroup_retained_fd_probe.py').read_text())
    output = remote("sudo -n /usr/bin/python3 -I -S -B - <<'D4_RETAINED_CGROUP'\n" +
                    probe + '\nD4_RETAINED_CGROUP\n', timeout=120, check=False)
    print(output)
    receipts = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
    assert len(receipts) == 1, output
    receipt = receipts[0]
    assert set(receipt) == {'unit', 'cgroup', 'replacement', 'cleanup_errors'}, receipt
    assert receipt['unit'].startswith('oqms-d4-cgfd-') and receipt['unit'].endswith('.service'), receipt
    assert receipt['cgroup'] == '/system.slice/' + receipt['unit'], receipt
    assert set(receipt['replacement']) == {'device', 'inode'}, receipt
    assert all(type(value) is int and value >= 0 for value in receipt['replacement'].values()), receipt
    assert receipt['cleanup_errors'] == [], receipt
    for marker in ('live_group_not_empty', 'deleted_original_empty',
                   'replacement_not_followed', 'cleanup_verified'):
        assert marker in output.splitlines(), output
    assert digest in output, output


def _local_probe():
    # The probe is intentionally a standalone stdin script. Remove only its
    # final invocation when loading functions for authority-free local tests.
    import ast
    import types
    path = Path(__file__).with_name('cgroup_retained_fd_probe.py')
    tree = ast.parse(path.read_text(), str(path))
    if isinstance(tree.body[-1], ast.Raise):
        tree.body.pop()
    module = types.ModuleType('_retained_cleanup_local')
    exec(compile(tree, str(path), 'exec'), module.__dict__)
    return module


def test_cleanup_local_accepts_gc_only_with_current_inactive_not_found(monkeypatch):
    from types import SimpleNamespace
    probe = _local_probe()
    responses = iter((SimpleNamespace(returncode=5, stdout='', stderr=''),
                      SimpleNamespace(returncode=4, stdout='ActiveState=inactive\nLoadState=not-found\n', stderr='')))
    monkeypatch.setattr(probe, 'run', lambda *a, **kw: next(responses))
    probe._stop_owned_unit()


def test_cleanup_local_rejects_permission_active_and_unknown_states(monkeypatch):
    import pytest
    from types import SimpleNamespace
    for stop_rc, show_rc, active, loaded in ((1, 0, 'inactive', 'loaded'),
                                           (5, 1, 'inactive', 'not-found'),
                                           (5, 0, 'active', 'loaded'),
                                           (5, 4, 'inactive', 'loaded')):
        probe = _local_probe()
        responses = iter((SimpleNamespace(returncode=stop_rc, stdout='', stderr='permission sentinel'),
                          SimpleNamespace(returncode=show_rc, stdout='ActiveState=' + active + '\nLoadState=' + loaded + '\n', stderr='')))
        monkeypatch.setattr(probe, 'run', lambda *a, **kw: next(responses))
        with pytest.raises(probe.ProbeFailure):
            probe._stop_owned_unit()


def test_cleanup_local_population_settles_within_one_fixed_second():
    from types import SimpleNamespace
    probe = _local_probe()
    class Clock:
        value = 0
        def __call__(self): return self.value
        def sleep(self, seconds): self.value += int(seconds * 10**9)
    clock = Clock()
    observations = iter(('populated 1\n', 'populated 1\n', 'populated 0\n'))
    collector = SimpleNamespace(_read_at=lambda fd, name: next(observations))
    probe._wait_replacement_empty(collector, 10, clock=clock, sleep=clock.sleep)
    assert 0 < clock.value <= 10**9


def test_cleanup_local_population_timeout_and_read_error_are_not_empty():
    import pytest
    from types import SimpleNamespace
    probe = _local_probe()
    class Clock:
        value = 0
        def __call__(self): return self.value
        def sleep(self, seconds): self.value += int(seconds * 10**9)
    clock = Clock()
    collector = SimpleNamespace(_read_at=lambda fd, name: 'populated 1\n')
    with pytest.raises(probe.ProbeFailure):
        probe._wait_replacement_empty(collector, 10, clock=clock, sleep=clock.sleep)
    assert clock.value <= 10**9
    def denied(fd, name): raise PermissionError('sensitive permission text')
    collector._read_at = denied
    with pytest.raises(PermissionError):
        probe._wait_replacement_empty(collector, 10, clock=clock, sleep=clock.sleep)


def test_cleanup_local_failure_still_prints_safe_receipt_and_every_error(monkeypatch, capsys):
    from types import SimpleNamespace
    probe = _local_probe()
    monkeypatch.setattr(probe.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(probe.os, 'uname', lambda: SimpleNamespace(release='unreviewed'))
    def failed(): raise OSError('do-not-print-raw-error')
    monkeypatch.setattr(probe, '_stop_owned_unit', failed)
    monkeypatch.setattr(probe, 'stop_child', failed)
    monkeypatch.setattr(probe, '_reset_owned_unit', failed)
    assert probe.main() == 1
    output = capsys.readouterr().out
    receipts = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt['unit'] == probe.UNIT and receipt['cgroup'] == probe.CGROUP
    assert receipt['replacement'] is None
    assert receipt['cleanup_errors'] == ['unit_stop_unknown', 'child_stop_unknown', 'unit_reset_unknown']
    assert all('cleanup_failed:' + code in output for code in receipt['cleanup_errors'])
    assert 'do-not-print-raw-error' not in output and 'cleanup_verified' not in output.splitlines()


def test_cleanup_local_stop_timeout_is_rejected(monkeypatch):
    import pytest
    import subprocess
    probe = _local_probe()
    def timeout(*a, **kw): raise subprocess.TimeoutExpired('fixed-command', 10)
    monkeypatch.setattr(probe, 'run', timeout)
    with pytest.raises(subprocess.TimeoutExpired): probe._stop_owned_unit()


def test_cleanup_local_reset_skips_already_garbage_collected_unit(monkeypatch):
    from types import SimpleNamespace
    probe = _local_probe()
    calls = []
    def run(*args, **kw):
        calls.append(args)
        return SimpleNamespace(returncode=4, stdout='ActiveState=inactive\nLoadState=not-found\n', stderr='')
    monkeypatch.setattr(probe, 'run', run)
    probe._reset_owned_unit()
    assert all('reset-failed' not in call for call in calls)
