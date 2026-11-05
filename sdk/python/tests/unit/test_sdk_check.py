"""Gate contract tests; fake children are never actual SDK acceptance evidence."""
import importlib.util
from pathlib import Path
import socket
import json
import os
import signal
import subprocess
import sys
import time

import pytest

SDK = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('gate contract tests must not use network')
    for name in ('connect', 'connect_ex', 'bind', 'sendto', 'sendmsg'):
        if hasattr(socket.socket, name):
            monkeypatch.setattr(socket.socket, name, deny)
    for name in ('getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'gethostbyaddr', 'getnameinfo'):
        monkeypatch.setattr(socket, name, deny)


def load(name):
    path = SDK / 'scripts' / name
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('early_exit,ignore_term', [
    (False, False), (True, False), (False, True), (True, True)])
def test_execute_reclaims_actual_process_tree(tmp_path, early_exit, ignore_term):
    check = load('check-sdk.py')
    env = check.environment(tmp_path)
    heartbeat = tmp_path / 'heartbeat'
    stopped = tmp_path / 'stopped'
    identity = tmp_path / 'identity.json'
    grandchild = (
        "import os, signal, sys, time\n"
        "from pathlib import Path\n"
        "def stop(*args):\n"
        " Path(sys.argv[2]).write_text(str(os.getpid()))\n"
        " raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN if sys.argv[3] == 'True' else stop)\n"
        "while True:\n"
        " Path(sys.argv[1]).write_text(str(time.monotonic_ns()))\n"
        " time.sleep(.02)\n")
    child = (
        "import json, os, signal, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "p = subprocess.Popen([sys.executable, '-I', '-B', '-c', sys.argv[1], *sys.argv[2:4], sys.argv[6]])\n"
        "def stop(*args):\n"
        " p.wait(timeout=2)\n"
        " raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "while not Path(sys.argv[2]).exists(): time.sleep(.01)\n"
        "Path(sys.argv[4]).write_text(json.dumps({'child':os.getpid(), 'grandchild':p.pid, 'pgid':os.getpgrp()}))\n"
        "if sys.argv[5] == 'True': raise SystemExit(0)\n"
        "time.sleep(60)\n")
    # Test fallback signals only the exact grandchild whose provenance this child records.
    cleaned = False
    try:
        code = check.execute([sys.executable, '-I', '-B', '-c', child, grandchild,
                              str(heartbeat), str(stopped), str(identity), str(early_exit),
                              str(ignore_term)],
                             tmp_path, env, timeout=1)
        pids = json.loads(identity.read_text())
        assert code == (0 if early_exit else 124)
        if not ignore_term:
            assert stopped.exists(), pids
        before = heartbeat.read_text()
        time.sleep(.1)
        assert heartbeat.read_text() == before, pids
        assert pids['pgid'] == pids['child'] != os.getpgrp()
        with pytest.raises(ChildProcessError):
            os.waitpid(pids['child'], os.WNOHANG)
        # Record PID/state and stopped heartbeat evidence only in this test's own tmp.
        state = subprocess.run(['ps', '-o', 'stat=', '-p', str(pids['grandchild'])],
                               capture_output=True, text=True, check=False)
        assert state.returncode in (0, 1)
        assert not state.stdout.strip() or state.stdout.strip().startswith('Z')
        cleaned = True
        (tmp_path / 'cleanup-evidence.json').write_text(json.dumps(
            dict(pids, exit=code, ignore_term=ignore_term, heartbeat=before,
                 heartbeat_stopped=True, direct_child_reaped=True,
                 grandchild_state=state.stdout.strip())))
    finally:
        if identity.exists() and not cleaned:
            pid = json.loads(identity.read_text())['grandchild']
            try:
                os.kill(pid, signal.SIGKILL if ignore_term else signal.SIGTERM)
            except ProcessLookupError:
                pass


def test_readme_explicitly_discloses_default_claim_lease():
    readme = (SDK / 'README.md').read_text()
    assert 'claim_run is a platform write' in readme
    assert 'short-lived run lease' in readme
    assert 'does not release the lease' in readme
    assert 'fixture tasks you own' in readme


def test_execute_spawn_oserror_is_safe(tmp_path, monkeypatch):
    check = load('check-sdk.py')
    def fail(*args, **kwargs):
        raise OSError('private-credential-sentinel')
    def no_kill(*args):
        raise AssertionError('no group was created')
    monkeypatch.setattr(check.subprocess, 'Popen', fail)
    monkeypatch.setattr(check.os, 'killpg', no_kill)
    assert check.execute(['fixture'], tmp_path, check.environment(tmp_path)) == 125


def test_execute_unsupported_platform_does_not_spawn(tmp_path, monkeypatch):
    check = load('check-sdk.py')
    env = check.environment(tmp_path)
    def fail(*args, **kwargs):
        raise AssertionError('unsupported platform must not spawn')
    monkeypatch.setattr(check.subprocess, 'Popen', fail)
    monkeypatch.setattr(check.os, 'name', 'unsupported')
    assert check.execute(['fixture'], tmp_path, env) == 125


def test_check_entrypoints_exist():
    for name in ('check-sdk.py', 'check-sdk-pure.py'):
        assert (SDK / 'scripts' / name).is_file(), f'missing {name}'
    assert (SDK / 'examples' / 'metadata_session.py').is_file()


@pytest.mark.parametrize('change', [dict(selected=0), dict(passed=0), dict(failed=1),
    dict(errors=1), dict(skipped=1), dict(xfailed=1), dict(xpassed=1), dict(exit=1)])
def test_gate_rejects_incomplete_receipts(change):
    check = load('check-sdk.py')
    counts = dict(selected=1, passed=1, failed=0, errors=0, skipped=0,
                  xfailed=0, xpassed=0, deselected=0, warnings=0, exit=0, elapsed=0.1)
    counts.update(change)
    assert not check.pytest_passed(counts)


def test_gate_accepts_complete_receipt():
    check = load('check-sdk.py')
    assert check.pytest_passed(dict(selected=2, passed=2, failed=0, errors=0,
        skipped=0, xfailed=0, xpassed=0, deselected=3, warnings=1, exit=0, elapsed=1))


def test_environment_is_curated(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sentinel-never-in-child')
    monkeypatch.setenv('PYTEST_PLUGINS', 'ambient_plugin')
    monkeypatch.setenv('PYTHONPATH', '/untrusted')
    check = load('check-sdk.py')
    env = check.environment(tmp_path)
    assert env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'
    assert env['PIP_CONFIG_FILE'] == '/dev/null'
    assert not {'OPENAI_API_KEY', 'PYTEST_PLUGINS', 'PYTHONPATH'} & env.keys()
    assert Path(env['HOME']).is_relative_to(tmp_path)


@pytest.mark.parametrize('layer', ['unit', 'loopback'])
def test_pytest_flags_and_selection(layer):
    pure = load('check-sdk-pure.py')
    args = pure.pytest_arguments(layer)
    assert '-c' in args and args[args.index('-c') + 1] == '/dev/null'
    assert '-p' in args and 'no:cacheprovider' in args
    assert str(SDK / 'tests' / layer) in args
    assert ('--noconftest' in args) == (layer == 'unit')
    if layer == 'loopback':
        assert f'--confcutdir={SDK / "tests"}' in args


def test_audit_guard_rejects_supported_socket_events():
    pure = load('check-sdk-pure.py')
    for name in ('connect', 'connect_ex', 'getaddrinfo', 'gethostbyname',
                 'gethostbyname_ex', 'gethostbyaddr', 'getnameinfo', 'bind', 'sendto', 'sendmsg'):
        with pytest.raises(RuntimeError, match='pure_network_denied'):
            pure.network_audit('socket.' + name, ())
    pure.network_audit('open', ())


def test_artifacts_are_unique_private_and_do_not_chmod_parent(tmp_path):
    check = load('check-sdk.py')
    tmp_path.chmod(0o755)
    one, two = check.artifact_directory(tmp_path), check.artifact_directory(tmp_path)
    assert one != two
    assert one.stat().st_mode & 0o777 == 0o700
    assert tmp_path.stat().st_mode & 0o777 == 0o755


def fake_popen(monkeypatch, check, outcome):
    """Contract-only fake; cleanup proof uses the actual synthetic tree above."""
    class Child:
        pid = 987654321
        def __init__(self, command, **kwargs):
            assert kwargs['start_new_session'] is True
            assert kwargs['stdout'] == kwargs['stderr'] == subprocess.DEVNULL
            self.code = outcome(command, **kwargs)
            self.waits = 0
        def wait(self, timeout=None):
            self.waits += 1
            if isinstance(self.code, Exception):
                if self.waits == 1:
                    raise self.code
                return 0
            return self.code.returncode
    def absent(group, sig):
        assert group == Child.pid
        raise ProcessLookupError
    monkeypatch.setattr(check.subprocess, 'Popen', Child)
    monkeypatch.setattr(check.os, 'killpg', absent)


def test_fake_child_failure_cannot_pass(tmp_path, monkeypatch):
    check = load('check-sdk.py')
    def fake_run(command, **kwargs):
        return type('Result', (), {'returncode': 0})()
    fake_popen(monkeypatch, check, fake_run)
    result = check.pytest_layer('unit', tmp_path, check.environment(tmp_path))
    assert result['status'] == 'FAIL'  # no actual receipt, even with exit zero


@pytest.mark.parametrize('when,outcome,xfail,expected', [
    ('call', 'passed', False, 'passed'), ('call', 'failed', False, 'failed'),
    ('setup', 'failed', False, 'errors'), ('teardown', 'failed', False, 'errors'),
    ('setup', 'skipped', False, 'skipped'), ('call', 'skipped', True, 'xfailed'),
    ('call', 'passed', True, 'xpassed'),
])
def test_hook_counts_actual_reports(when, outcome, xfail, expected):
    from types import SimpleNamespace
    pure = load('check-sdk-pure.py')
    counter = pure.Counts()
    report = SimpleNamespace(when=when, passed=outcome == 'passed',
        failed=outcome == 'failed', skipped=outcome == 'skipped', longrepr='')
    if xfail:
        report.wasxfail = 'fixture'
    counter.pytest_runtest_logreport(report)
    assert counter.values[expected] == 1
    assert sum(counter.values.values()) == 1


def test_strict_xpass_is_counted_not_hidden_as_ordinary_failure():
    from types import SimpleNamespace
    counter = load('check-sdk-pure.py').Counts()
    counter.pytest_runtest_logreport(SimpleNamespace(when='call', passed=False,
        failed=True, skipped=False, longrepr='[XPASS(strict)] fixture'))
    assert counter.values['xpassed'] == 1


@pytest.mark.parametrize('code', [1, 5, 124])
def test_real_child_exit_overrides_passing_fake_receipt(tmp_path, monkeypatch, code):
    check = load('check-sdk.py')
    def fake_run(command, **kwargs):
        import json
        (tmp_path / 'unit-pytest.json').write_text(json.dumps(dict(selected=1,
            passed=1, failed=0, errors=0, skipped=0, xfailed=0, xpassed=0,
            deselected=0, warnings=0, exit=0, elapsed=0.01, layer='unit', pure=True)))
        return type('Result', (), {'returncode': code})()
    fake_popen(monkeypatch, check, fake_run)
    result = check.pytest_layer('unit', tmp_path, check.environment(tmp_path))
    assert result['status'] == 'FAIL' and result['exit'] == code


def test_timeout_is_controlled(tmp_path, monkeypatch):
    check = load('check-sdk.py')
    def timeout(*args, **kwargs):
        return check.subprocess.TimeoutExpired('private-credential-sentinel', 1)
    fake_popen(monkeypatch, check, timeout)
    result = check.pytest_layer('unit', tmp_path, check.environment(tmp_path))
    assert result['status'] == 'FAIL' and result['exit'] == 124
    assert 'sentinel' not in str(result)


def test_wheel_probe_failure_never_passes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    check = load('check-sdk.py')
    commands = []
    def fake_run(command, **kwargs):
        commands.append(command)
        if check.BUILD_METADATA in command:
            (tmp_path / 'wheel-build.json').write_text(json.dumps({
                'wheel_path': '/fixture/not-an-actual-wheel.whl', 'wheel_sha256': 'fixture',
                'source_manifest': {'README.md': 'fixture'}}))
        return SimpleNamespace(returncode=1 if check.PROBE in command else 0)
    fake_popen(monkeypatch, check, fake_run)
    result = check.wheel_layer(tmp_path, check.environment(tmp_path))
    assert result['status'] == 'FAIL' and result['probe_exit'] == 1
    assert check.BUILD_METADATA in commands[0]
    assert commands[0][1:3] == ['-I', '-B']
    assert '-m' in commands[1] and 'venv' in commands[1]
    install = commands[2]
    for flag in ('-I', '-B', '--isolated', '--disable-pip-version-check', '--no-index', '--no-deps'):
        assert flag in install
    assert commands[3][1:3] == ['-I', '-B']


def test_example_default_is_metadata_only_and_closes():
    path = SDK / 'examples' / 'metadata_session.py'
    spec = importlib.util.spec_from_file_location('metadata_example', path)
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    calls = []
    class Run:
        def capabilities(self):
            calls.append('capabilities')
            return type('Caps', (), {'capabilities': ()})()
        def close(self): calls.append('run_close')
    class Client:
        def __init__(self, *args): pass
        def claim_run(self, **kwargs): calls.append('claim'); return Run()
        def close(self): calls.append('close')
    result = example.session(dict(origin='http://127.0.0.1:1234', tenant='fixture',
        installation_id='00000000-0000-0000-0000-000000000001',
        secret='not-a-real-secret', request_key='fixture'), client_type=Client)
    assert calls == ['claim', 'capabilities', 'run_close', 'close']
    assert result == {'status': 'ok', 'capabilities': 0}
    assert 'not-a-real-secret' not in str(result)


def test_example_rejects_ack_before_delivery():
    path = SDK / 'examples' / 'metadata_session.py'
    spec = importlib.util.spec_from_file_location('metadata_example', path)
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    with pytest.raises(ValueError):
        example.validate_options({'operations': [{'operation': 'ack_messages'}]})
    with pytest.raises(ValueError):
        example.validate_options({'operations': [{'operation': 'finish'}]})


def test_pytest_child_does_not_expose_raw_failure(tmp_path, monkeypatch, capsys):
    import sys
    from types import SimpleNamespace
    pure = load('check-sdk-pure.py')
    def fake_pytest(args, plugins):
        print('raw-private-failure-sentinel')
        return 1
    monkeypatch.setitem(sys.modules, 'pytest', SimpleNamespace(main=fake_pytest))
    monkeypatch.setattr(sys, 'addaudithook', lambda hook: None)
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    assert pure.run_pytest('unit', tmp_path / 'receipt.json') == 1
    assert 'raw-private-failure-sentinel' not in capsys.readouterr().out


def test_wheel_probe_guard_precedes_sdk_import():
    probe = load('check-sdk.py').PROBE
    assert probe.index('sys.addaudithook') < probe.index('import openqms_agent_sdk')


def test_example_uses_only_existing_context_views():
    spec = importlib.util.spec_from_file_location('metadata_example', SDK / 'examples' / 'metadata_session.py')
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    for view in ('report', 'verifications'):
        options = {'operations': [{'operation': 'get_capa_context', 'params': {'view': view}}]}
        assert example.validate_options(options) == options['operations']
    with pytest.raises(ValueError):
        example.validate_options({'operations': [{'operation': 'get_capa_context', 'params': {'view': 'analysis'}}]})
