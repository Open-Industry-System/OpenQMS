"""Isolated launcher file and process lifecycle contracts."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from test_d4_text_receiver import load, fx


@pytest.fixture
def launcher():
    return load(ROOT / 'scripts/agent_d4_text_local.py', 'd4_launcher_test')


def test_launcher_exists():
    assert (ROOT / 'scripts/agent_d4_text_local.py').is_file()


def private_config(tmp_path, origin):
    tmp_path.chmod(0o700)
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(fx.config(origin)))
    path.chmod(0o600)
    return path


def test_real_isolated_receiver(launcher, tmp_path):
    worker = ROOT / 'examples/readonly_d4_text_receiver.py'
    with fx.server(fx.responses()) as (origin, requests):
        cfg = private_config(tmp_path, origin)
        result = launcher.launch(cfg, hashlib.sha256(worker.read_bytes()).hexdigest())
    assert result == dict(status='completed', receipt_id=fx.RECEIPT, received_fields=1)
    assert len(requests) == 6
    assert sorted(p.name for p in tmp_path.iterdir()) == ['config.json']
    assert all(value not in repr(result) for value in (fx.TEXT, fx.SECRET, fx.TOKEN))


@pytest.mark.parametrize('mode', [0o644, 0o666, 0o400])
def test_unsafe_config_mode(launcher, tmp_path, mode):
    cfg = private_config(tmp_path, 'http://127.0.0.1:1')
    cfg.chmod(mode)
    assert launcher.launch(cfg, '0'*64)['status'] == 'configuration_invalid'


def test_symlink_rejected(launcher, tmp_path):
    cfg = private_config(tmp_path, 'http://127.0.0.1:1')
    link = tmp_path / 'link'
    link.symlink_to(cfg)
    with pytest.raises(launcher.LaunchFailure):
        launcher.read_private_config(link)


def test_wrong_hash_never_starts(launcher, tmp_path, monkeypatch):
    cfg = private_config(tmp_path, 'http://127.0.0.1:1')
    def forbidden(*args, **kwargs):
        pytest.fail('wrong hash started process')
    monkeypatch.setattr(launcher.subprocess, 'Popen', forbidden)
    assert launcher.launch(cfg, '0'*64)['status'] == 'configuration_invalid'


def test_child_has_only_private_runtime_and_no_secrets_in_argv_env(launcher, tmp_path, monkeypatch):
    audit = tmp_path / 'audit.json'
    source = ('''import json, os, sys
from pathlib import Path
config = json.loads(sys.stdin.buffer.read())
audit = dict(flags=[sys.flags.isolated, sys.flags.no_site, sys.dont_write_bytecode],
             outside_repo='OpenQMS' not in os.getcwd(),
             private_home=os.environ['HOME'] == os.getcwd(),
             private_tmp=os.environ['TMPDIR'] == os.getcwd(),
             env_keys=sorted(os.environ),
             leaked=any(config['secret'] in value for value in [*sys.argv, *os.environ.values()]),
             mode=oct(Path.cwd().stat().st_mode & 0o777))
Path(AUDIT).write_text(json.dumps(audit))
print('{"status":"unconfirmed","received_fields":0}')
'''.replace('AUDIT', repr(str(audit)))).encode()
    monkeypatch.setenv('OPENAI_API_KEY', fx.SECRET)
    assert launcher.supervise(source, json.dumps(fx.config('http://127.0.0.1:1')).encode())['status'] == 'unconfirmed'
    result = json.loads(audit.read_text())
    assert result['flags'] == [1, 1, True]
    assert all(result[k] for k in ('outside_repo', 'private_home', 'private_tmp'))
    assert result['leaked'] is False and result['mode'] == '0o700'
    assert set(result['env_keys']) <= {'HOME', 'TMPDIR', 'LC_CTYPE', '__CF_USER_TEXT_ENCODING'}


@pytest.mark.parametrize('mode', ['normal', 'early-exit', 'timeout'])
def test_own_process_group_cleaned_even_when_leader_exits(launcher, tmp_path, monkeypatch, mode):
    import subprocess
    import time
    audit = tmp_path / 'child.pid'
    source = ('''import json, os, subprocess, sys, time
from pathlib import Path
sys.stdin.buffer.read()
child = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', 'import time; time.sleep(30)'],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
Path(AUDIT).write_text(str(child.pid))
if MODE == 'timeout': time.sleep(30)
if MODE == 'early-exit': os._exit(1)
print('{"status":"unconfirmed","received_fields":0}')
'''.replace('AUDIT', repr(str(audit))).replace('MODE', repr(mode))).encode()
    monkeypatch.setattr(launcher, 'SESSION_SECONDS', .3)
    started = time.monotonic()
    if mode == 'normal':
        assert launcher.supervise(source, b'{}')['status'] == 'unconfirmed'
    else:
        with pytest.raises(Exception):
            launcher.supervise(source, b'{}')
    assert time.monotonic()-started < 2
    pid = int(audit.read_text())
    process = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
    assert process.returncode == 1 or process.stdout.strip().startswith('Z')


def test_private_config_rejects_directory_mode_and_hardlinks(launcher, tmp_path):
    cfg = private_config(tmp_path, 'http://127.0.0.1:1')
    os.link(cfg, tmp_path / 'hardlink')
    with pytest.raises(launcher.LaunchFailure):
        launcher.read_private_config(cfg)
    (tmp_path / 'hardlink').unlink()
    tmp_path.chmod(0o755)
    with pytest.raises(launcher.LaunchFailure):
        launcher.read_private_config(cfg)


def test_real_cli_never_outputs_received_text_or_credentials(tmp_path):
    import subprocess
    worker = ROOT / 'examples/readonly_d4_text_receiver.py'
    with fx.server(fx.responses()) as (origin, requests):
        cfg = private_config(tmp_path, origin)
        command = [sys.executable, '-I', '-S', '-B', str(ROOT / 'scripts/agent_d4_text_local.py'),
                   '--config', str(cfg), '--worker-sha256', hashlib.sha256(worker.read_bytes()).hexdigest()]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stderr == ''
    assert json.loads(result.stdout)['status'] == 'completed'
    assert all(s not in result.stdout+result.stderr+repr(command) for s in (fx.TEXT, fx.SECRET, fx.TOKEN))
    assert len(requests) == 6


def test_invalid_child_output_never_passes_through(launcher):
    source = ('print('+repr(fx.TEXT+fx.SECRET+fx.TOKEN)+')').encode()
    with pytest.raises(Exception) as caught:
        launcher.supervise(source, b'{}')
    # The public launch boundary discards the underlying JSON decoder exception.
    assert not hasattr(caught.value, 'response')
    assert launcher.SESSION_SECONDS == 60
