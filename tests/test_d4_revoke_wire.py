"""Real HTTP exchanges with synthetic replies exercise the fixed revoke witness."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import runpy
import select
import shutil
import subprocess
import sys
from threading import Thread
import time
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).parents[1]
WORKER = SimpleNamespace(**runpy.run_path(str(ROOT / 'backend/examples/readonly_d4_text_receiver.py')))
OBSERVE = runpy.run_path(str(ROOT / 'deploy/d4-acceptance/revoke_wire.py'))['observe_revocation']
STAMP = '2030-01-01T00:00:00Z'
RUN = '11111111-1111-4111-8111-111111111111'
TASK = '22222222-2222-4222-8222-222222222222'
REPORT = '33333333-3333-4333-8333-333333333333'
INSTALL = '44444444-4444-4444-8444-444444444444'
GRANT = '55555555-5555-4555-8555-555555555555'
ADMIN_TOKEN = 'synthetic.cookie.admin-0123456789'
PASSWORD = 'synthetic-issue-cli-password'
SECRET = 'synthetic-install-secret'
SOURCE = '/api/agent/runtime/capa/d4/root-cause-text'
REVOKE = f'/api/admin/agent-plugins/{INSTALL}/grants/{GRANT}'


@pytest.fixture
def endpoint():
    state = SimpleNamespace(calls=[], revoke_status=200, revoked=False, denied_status=401,
                            denied_body={'detail': 'Invalid run credential'}, first_status=200,
                            first_report=REPORT, claim_run=RUN, grant_id=GRANT)

    class Server(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def dispatch(self):
            count = int(self.headers.get('Content-Length', '0'))
            body = json.loads(self.rfile.read(count)) if count else None
            state.calls.append((self.command, self.path, self.headers.get('Authorization'),
                                self.headers.get('X-Tenant-ID'), body))
            status = 200
            if self.path == '/api/auth/login':
                reply = {'access_token': ADMIN_TOKEN}
            elif self.path.endswith('/claim') and self.path != '/api/agent/runtime/messages/claim':
                reply = dict(lease_epoch=1, accepted_message_seq=0, has_resume_checkpoint=False,
                             lease_expires_at=STAMP, run_id=state.claim_run, task_id=TASK, token='run-test-token')
            elif self.path.endswith('/capabilities'):
                reply = dict(capabilities=[dict(id=WORKER.TEXT_CAPABILITY, allowed=True, required=True,
                                                projection='masked')])
            elif self.path.endswith('/messages/claim'):
                reply = dict(accepted_sequence=0, batch_id=GRANT, messages=[
                    dict(message_id=RUN, sequence=1, content=WORKER.START_MESSAGE),
                ])
            elif self.path == REVOKE:
                status = state.revoke_status
                state.revoked = status == 200
                reply = dict(enabled=False, grant_id=state.grant_id, installation_id=INSTALL,
                             capability_id=WORKER.TEXT_CAPABILITY)
            elif self.path == SOURCE and state.revoked:
                status, reply = state.denied_status, state.denied_body
            else:
                status = state.first_status
                reply = dict(WORKER.LABELS, **dict.fromkeys(WORKER.VERSIONS, 'a' * 64),
                             plugin_version='1.0.0', generated_at=STAMP, text='synthetic masked body',
                             receipt_id=GRANT, report_id=state.first_report, run_id=RUN, task_id=TASK,
                             recipient_installation_id=INSTALL)
            encoded = json.dumps(reply, separators=(',', ':')).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        do_GET = do_POST = do_PATCH = dispatch

    with ThreadingHTTPServer(('127.0.0.1', 0), Server) as server:
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        config = WORKER.Config(origin=f'http://127.0.0.1:{server.server_port}', tenant_slug='d4-synthetic',
                               installation_id=INSTALL, secret=SECRET,
                               request_key='fixture-key', expected_report_id=REPORT)
        state.config = config

        def exercise():
            return OBSERVE(WORKER, config, admin_token='synthetic-admin-token', task_id=TASK, run_id=RUN,
                           grant_id=GRANT, deadline=time.monotonic() + 5)

        try:
            yield exercise, state
        finally:
            server.shutdown()
            thread.join()


def test_control_witness_uses_exact_grant_and_same_run_without_body_or_secrets(endpoint):
    exercise, state = endpoint
    report = exercise()
    assert report == dict(task_id=TASK, run_id=RUN, report_id=REPORT, installation_id=INSTALL,
                          grant_id=GRANT, authorized_status=200, revoked_status=401, revoked_body_received=False)
    assert state.calls[-3:] == [
        ('GET', SOURCE, 'Bearer run-test-token', 'd4-synthetic', None),
        ('PATCH', REVOKE, 'Bearer synthetic-admin-token', 'd4-synthetic', {'enabled': False}),
        ('GET', SOURCE, 'Bearer run-test-token', 'd4-synthetic', None),
    ]
    assert len(state.calls) == 6


@pytest.mark.parametrize('field,value,requests', [
    ('claim_run', GRANT, 1),
    ('first_status', 201, 4),
    ('first_report', GRANT, 4),
    ('revoke_status', 403, 5),
    ('grant_id', TASK, 5),
    ('denied_status', 403, 6),
    ('denied_body', {'detail': 'Invalid run credential', 'text': 'synthetic masked body'}, 6),
])
def test_control_witness_fails_closed_without_echoing_reply(endpoint, field, value, requests):
    exercise, state = endpoint
    setattr(state, field, value)
    with pytest.raises(ValueError, match='^D4 revocation could not be witnessed$'):
        exercise()
    assert len(state.calls) == requests


@pytest.mark.parametrize('command', [b'revoke\n', b'reject\n', None])
def test_receiver_waits_for_controller_before_touching_exact_grant(endpoint, tmp_path, command):
    _, state = endpoint
    package = ROOT / 'deploy' / 'd4-acceptance'
    for path in (package / 'revoke_receiver.py', package / 'revoke_wire.py',
                 ROOT / 'backend' / 'examples' / 'readonly_d4_text_receiver.py'):
        shutil.copy(path, tmp_path)
    with subprocess.Popen([sys.executable, '-I', '-S', '-B', str(tmp_path / 'revoke_receiver.py')],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
        try:
            receiver = {field: getattr(state.config, field) for field in WORKER.Config.__dataclass_fields__}
            receiver['tenant_slug'] = 'd4-' + 'a' * 32
            identities = dict(task_id=TASK, run_id=RUN, grant_id=GRANT)
            payload = dict(receiver=receiver, admin_username='d4-admin@example.test',
                           admin_password=PASSWORD, **identities)
            child.stdin.write(json.dumps(payload).encode() + b'\n')
            child.stdin.flush()
            assert select.select([child.stdout], [], [], 5)[0]
            authorized = json.loads(child.stdout.readline())
            assert authorized == dict(identities, report_id=REPORT, installation_id=INSTALL, stage='authorized')
            assert [call[1] for call in state.calls] == [
                '/api/auth/login', '/api/agent/runtime/claim', '/api/agent/runtime/capabilities',
                '/api/agent/runtime/messages/claim', SOURCE,
            ]
            assert not state.revoked

            output, error = child.communicate(input=command, timeout=5)
            if command == b'revoke\n':
                expected = dict(identities, report_id=REPORT, installation_id=INSTALL, authorized_status=200,
                                revoked_status=401, revoked_body_received=False)
                assert child.returncode == 0 and json.loads(output) == expected and not error
                assert state.calls[-2][0:3] == ('PATCH', REVOKE, 'Bearer ' + ADMIN_TOKEN)
                assert state.calls[-2][-1] == {'enabled': False}
                assert state.calls[-1][0:3] == ('GET', SOURCE, 'Bearer run-test-token')
            else:
                assert child.returncode == 1 and not output and error == b'D4_REVOCATION_BLOCKED\n'
                assert not state.revoked
            emitted = (json.dumps(authorized).encode() + output + error).decode()
            assert all(secret not in emitted for secret in (
                ADMIN_TOKEN, PASSWORD, SECRET, 'run-test-token', 'synthetic masked body',
            ))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
