from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

from tests.services.agent_runtime.trial_support import UNIT_ENTRY, write_policy


def private_file(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(value)
    path.chmod(0o600)
    return path


def test_fixed_launcher_does_not_inherit_parent_secrets_or_expose_worker_errors(tmp_path, monkeypatch, capsys):
    from app.services.agent_runtime import trial_launcher
    secret = private_file(tmp_path, 'installation.secret', 's'*43)
    for name in ('DATABASE_URL', 'ADMIN_TOKEN', 'ANTHROPIC_API_KEY', 'HTTPS_PROXY', 'PYTHONPATH', 'HOME'):
        monkeypatch.setenv(name, 'PARENT-SENTINEL-NOT-IN-CHILD')
    original = subprocess.Popen
    observed = []
    def real_spawn(*args, **kwargs):
        observed.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', real_spawn)
    code = trial_launcher.run_fixed_worker(installation_id=uuid4(), secret_file=secret,
        tenant_slug='owned', api_base_url='http://127.0.0.1:1', claim_key='fixture', checkpoint='off', finish='off')
    assert code == 1
    output = capsys.readouterr()
    assert output.out == '' and output.err == 'TRIAL_RUN_FAILED\n'
    assert len(observed) == 1
    args, kwargs = observed[0]
    assert args[0][0:2] == [sys.executable, '-I']
    assert set(kwargs['env']) == {'LANG', 'LC_ALL', 'OPENQMS_API_BASE_URL', 'OPENQMS_INSTALLATION_ID',
        'OPENQMS_INSTALLATION_SECRET', 'OPENQMS_TENANT_SLUG', 'OPENQMS_CLAIM_KEY',
        'OPENQMS_READONLY_CHECKPOINT', 'OPENQMS_READONLY_FINISH'}
    assert 'PARENT-SENTINEL' not in str(kwargs['env'])
    assert 's'*43 not in str(args)
    assert not Path(kwargs['cwd']).exists()


@pytest.mark.parametrize('damage', ['worker', 'symlink', 'mode'])
def test_launcher_denies_unsafe_bytes_or_credential_file_before_spawn(tmp_path, monkeypatch, capsys, damage):
    from app.services.agent_runtime import trial_launcher
    secret = private_file(tmp_path, 'installation.secret', 's'*43)
    marker = tmp_path / 'must-not-execute'
    if damage == 'worker':
        worker = tmp_path / 'untrusted.py'
        worker.write_text(f'from pathlib import Path; Path({str(marker)!r}).touch()')
        monkeypatch.setattr(trial_launcher, 'WORKER_PATH', worker)
    elif damage == 'symlink':
        linked = tmp_path / 'linked'
        linked.symlink_to(secret)
        secret = linked
    else:
        secret.chmod(0o644)
    assert trial_launcher.run_fixed_worker(installation_id=uuid4(), secret_file=secret, tenant_slug='owned',
        api_base_url='http://127.0.0.1:1', claim_key='fixture', checkpoint='off', finish='off') == 1
    assert not marker.exists()
    assert capsys.readouterr().err == 'TRIAL_LAUNCH_DENIED\n'


@pytest.mark.parametrize('url', ['http://example.com', 'http://localhost', 'http://127.0.0.2',
    'http://127.0.0.1@evil.test', 'http://127.0.0.1/?', 'http://127.0.0.1/#',
    'http://127.0.0.1/api', ' http://127.0.0.1', 'http://127.0.0.1:0'])
def test_only_unambiguous_literal_loopback_origins_are_accepted(url):
    from app.services.agent_runtime.trial_launcher import local_origin
    with pytest.raises(ValueError): local_origin(url)


@pytest.mark.parametrize('pipe', [1, 2])
def test_actual_child_output_overflow_is_bounded_and_child_reaped(pipe):
    from app.services.agent_runtime.trial_launcher import collect_worker
    process = subprocess.Popen([sys.executable, '-I', '-c',
        f'import os,time; os.write({pipe}, b"x"*(2*1024*1024)); time.sleep(20)'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with pytest.raises(ValueError): collect_worker(process, timeout=5, limit=1024*1024)
    assert process.poll() is not None


def test_actual_child_timeout_is_reaped_without_unbounded_communicate():
    from app.services.agent_runtime.trial_launcher import collect_worker
    process = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(20)'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with pytest.raises(ValueError): collect_worker(process, timeout=.05, limit=1024*1024)
    assert process.poll() is not None


def test_collect_interrupt_still_reaps_the_owned_child(monkeypatch):
    import selectors
    from app.services.agent_runtime.trial_launcher import collect_worker
    process = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(20)'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    def interrupted(*args, **kwargs): raise KeyboardInterrupt
    monkeypatch.setattr(selectors.DefaultSelector, 'select', interrupted)
    try:
        with pytest.raises(KeyboardInterrupt): collect_worker(process)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_actual_check_policy_cli_prints_only_diagnostic_count_and_snapshot_hash(tmp_path):
    path = write_policy(tmp_path / 'policy.json', {**UNIT_ENTRY,
        'expires_at': (datetime.now(UTC)+timedelta(minutes=20)).isoformat()})
    result = subprocess.run([sys.executable, '-m', 'app.cli.agent_local_trial', 'check-policy',
        '--policy-file', str(path)], capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == {'diagnostic': 'TRIAL_READY', 'entries': 1,
        'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    assert UNIT_ENTRY['report_id'].encode() not in result.stdout


def test_actual_cli_rejects_arbitrary_report_selector_and_commands(tmp_path):
    result = subprocess.run([sys.executable, '-m', 'app.cli.agent_local_trial', 'run',
        '--installation-id', str(uuid4()), '--installation-secret-file', str(tmp_path/'not-read'),
        '--tenant-slug', 'owned', '--api-base-url', 'http://127.0.0.1:1', '--report-id', str(uuid4())],
        capture_output=True, timeout=10)
    assert result.returncode == 2 and result.stdout == b''


@pytest.mark.parametrize('damage', ['bad-status', 'redirect', 'wrong-installation', 'string-epoch',
    'boolean-enabled', 'unknown-field', 'duplicate-key'])
def test_revoke_cli_refuses_malformed_wire_proof_and_never_follows_redirect_or_proxy(tmp_path, damage):
    import socketserver
    import threading
    from contextlib import contextmanager
    calls = []
    @contextmanager
    def server(raw):
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                first = self.rfile.readline()
                size = 0
                while line := self.rfile.readline():
                    if line == b'\r\n': break
                    if line.lower().startswith(b'content-length:'): size = int(line.split(b':', 1)[1])
                self.rfile.read(size)
                calls.append(first)
                self.wfile.write(raw)
        with socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler) as instance:
            thread = threading.Thread(target=instance.serve_forever, daemon=True)
            thread.start()
            try: yield f'http://127.0.0.1:{instance.server_address[1]}'
            finally:
                instance.shutdown()
                thread.join()
    installation = uuid4()
    payload = {'installation_id': str(installation), 'credential_epoch': 1, 'enabled': False, 'outcome': 'revoked'}
    if damage == 'wrong-installation': payload['installation_id'] = str(uuid4())
    if damage == 'string-epoch': payload['credential_epoch'] = '1'
    if damage == 'boolean-enabled': payload['enabled'] = 0
    if damage == 'unknown-field': payload['secret'] = 'PEER-CONTENT-MUST-NOT-LEAK'
    body = json.dumps(payload).encode()
    if damage == 'duplicate-key': body = body[:-1]+b',"credential_epoch":1}'
    token = private_file(tmp_path, 'admin.jwt', 'AAA.BBB.CCC')
    with server(b'HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\n\r\n') as forbidden:
        raw = b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
        if damage == 'redirect': raw = b'HTTP/1.1 307 Temporary Redirect\r\nLocation: '+forbidden.encode()+b'\r\nContent-Length: 0\r\n\r\n'
        if damage == 'bad-status': raw = b'PEER-CONTENT-MUST-NOT-LEAK\r\n\r\n'
        with server(raw) as origin:
            result = subprocess.run([sys.executable, '-m', 'app.cli.agent_local_trial', 'revoke',
                '--installation-id', str(installation), '--expected-credential-epoch', '0',
                '--tenant-slug', 'owned', '--api-base-url', origin, '--admin-token-file', str(token)],
                capture_output=True, timeout=10, env={'LANG': 'C', 'LC_ALL': 'C',
                    'HTTP_PROXY': forbidden, 'HTTPS_PROXY': forbidden})
    assert len(calls) == 1
    assert result.returncode == 1 and result.stdout == b''
    assert result.stderr == b'TRIAL_REVOKE_DENIED\n'
