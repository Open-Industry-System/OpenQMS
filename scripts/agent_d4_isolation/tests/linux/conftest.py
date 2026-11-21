"""Fixtures for the Linux-only isolation tests.

These tests talk to a real Docker daemon and a real kernel, so they are opt-in.
Without the environment variables every test fails; nothing is skipped, so a
green run cannot be produced by simply omitting the host.

Run with:
    OPENQMS_ISOLATION_LINUX=1 OPENQMS_ISOLATION_HOST=user@host \
    OPENQMS_ISOLATION_KEY=/path/to/key \
    pytest scripts/agent_d4_isolation/tests/linux -q
"""
import os
import ipaddress
import json
import re
import shlex
import subprocess

import pytest

HOST = os.environ.get('OPENQMS_ISOLATION_HOST')
KEY = os.environ.get('OPENQMS_ISOLATION_KEY')
ENABLED = os.environ.get('OPENQMS_ISOLATION_LINUX') == '1'


def _require_environment():
    if not ENABLED:
        pytest.fail('OPENQMS_ISOLATION_LINUX is not 1: Linux isolation tests are NOT run')
    if not HOST or not KEY:
        pytest.fail('OPENQMS_ISOLATION_HOST/KEY are not set')


@pytest.fixture(scope='session')
def remote():
    """Run one shell script on the host and return its stdout."""
    _require_environment()
    key = os.path.expanduser(KEY)

    def run(script, *, timeout=600, check=True):
        result = subprocess.run(
            ['ssh', '-i', key, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
             HOST, 'bash -s'],
            input=script, text=True, capture_output=True, timeout=timeout)
        if check and result.returncode != 0:
            raise AssertionError('remote script failed (%d): %s' %
                                 (result.returncode, result.stderr[-2000:]))
        return result.stdout

    return run


@pytest.fixture
def nonce():
    """One unique canonical 64-hex identity per test."""
    return os.urandom(32).hex()


BASE_IMAGE = 'python@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89'
EXPERIMENT_NONCE_LABEL = 'openqms.d4.experiment.nonce'
EXPERIMENT_ROLE_LABEL = 'openqms.d4.experiment.role'


def _docker(remote, *arguments):
    return remote('docker ' + ' '.join(shlex.quote(item) for item in arguments)).strip()


def _exact_present(remote, identity):
    rows = _docker(remote, 'container', 'ls', '-a', '--no-trunc', '--filter',
                   'id=' + identity, '--format', '{{.ID}}').splitlines()
    if rows not in ([], [identity]):
        raise AssertionError('experiment_identity_listing_invalid')
    return bool(rows)


def _remove_owned(remote, identity, image_id, nonce, role):
    if not _exact_present(remote, identity):
        return  # Successful fresh Engine enumeration proves this ID absent.
    projection = '{{.Id}}\n{{.Image}}\n{{json .Config.Labels}}'
    lines = _docker(remote, 'inspect', '--format', projection, identity).splitlines()
    if len(lines) != 3:
        raise AssertionError('experiment_cleanup_identity_invalid')
    labels = json.loads(lines[2])
    if (lines[:2] != [identity, image_id] or type(labels) is not dict
            or labels.get(EXPERIMENT_NONCE_LABEL) != nonce
            or labels.get(EXPERIMENT_ROLE_LABEL) != role):
        raise AssertionError('experiment_cleanup_identity_invalid')
    _docker(remote, 'rm', '-f', identity)
    if _exact_present(remote, identity):
        raise AssertionError('experiment_cleanup_absence_unproved')


@pytest.fixture
def experiment(remote, nonce):
    """Two local pinned-image containers; reclaim only their initial full IDs."""
    if re.fullmatch('[a-f0-9]{64}', nonce) is None:
        raise AssertionError('experiment_nonce_invalid')
    api, target = 'api-' + nonce[:16], 'tgt-' + nonce[:16]
    # image inspect never pulls. Match subsequent fresh container Image facts
    # against this immutable local content ID, not a mutable repository tag.
    image_id = _docker(remote, 'image', 'inspect', '--format', '{{.Id}}', BASE_IMAGE)
    if re.fullmatch('sha256:[a-f0-9]{64}', image_id) is None:
        raise AssertionError('experiment_local_image_invalid')
    target_program = """
import http.server,socketserver
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b't')
    def log_message(self,*a): pass
socketserver.TCPServer.allow_reuse_address=True
socketserver.TCPServer(('0.0.0.0',9000),H).serve_forever()
"""
    api_program = """
import http.server,socketserver,threading,time
def serve(port):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
        def log_message(self,*a): pass
    s=socketserver.TCPServer(('127.0.0.1',port),H)
    threading.Thread(target=s.serve_forever,daemon=True).start()
serve(18777); serve(18778); time.sleep(900)
"""
    class Experiment:
        pass
    state = Experiment()
    state.api, state.target, state.nonce = api, target, nonce
    created = {}
    try:
        for role, name, program, options in (
                ('target', target, target_program, ()),
                ('api', api, api_program, ('--user', '2002', '--cap-drop', 'ALL',
                 '--security-opt', 'no-new-privileges', '--pids-limit', '16',
                 '--memory', '128m', '--cpus', '1'))):
            identity = _docker(remote, 'create', '--pull=never', '--name', name,
                '--label', EXPERIMENT_NONCE_LABEL + '=' + nonce,
                '--label', EXPERIMENT_ROLE_LABEL + '=' + role,
                *options, '--entrypoint', 'python', BASE_IMAGE, '-c', program)
            if re.fullmatch('[a-f0-9]{64}', identity) is None:
                raise AssertionError('experiment_create_identity_unknown')
            # No remote call may fall between receipt and this registration.
            created[role] = identity
            _docker(remote, 'start', identity)
        remote('sleep 3')
        state.target_ip = _docker(remote, 'inspect', '--format',
            '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', created['target'])
        ipaddress.IPv4Address(state.target_ip)
        state.pid = _docker(remote, 'inspect', '--format', '{{.State.Pid}}', created['api'])
        if re.fullmatch('[0-9]+', state.pid) is None or int(state.pid) <= 1:
            raise AssertionError('experiment_api_pid_invalid')
        yield state
    finally:
        failures = []
        for role, identity in created.items():
            try:
                _remove_owned(remote, identity, image_id, nonce, role)
            except Exception:
                failures.append(role)
        if failures:
            raise AssertionError('experiment_cleanup_failed:' + ','.join(failures))
