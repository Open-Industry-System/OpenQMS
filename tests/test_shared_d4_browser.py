import base64
from contextlib import contextmanager
import hashlib
import http.client
from pathlib import Path
import runpy
import threading
import time
from uuid import uuid4

import pytest


MODULE = runpy.run_path(str(Path(__file__).parents[1] / 'deploy/d4-acceptance/browser.py'))
from http.server import HTTPServer


def fixture_config():
    now = int(time.time())
    salt = b'\x01' * 16
    return dict(
        origin='https://test-acceptance.example.test',
        username='fixture-reviewer', salt=salt.hex(),
        password_digest=hashlib.scrypt(b'fixture-password', salt=salt, n=2**14, r=8, p=1).hex(),
        report_label='合成 D4 试验报告', executor_socket='/run/openqms-test-fixture.sock',
        binding=dict(pr=45, head='a' * 40, merge='b' * 40, plan='c' * 64, lease='d' * 32,
                     report_id=str(uuid4()), issued_at=now, expires_at=now + 3600),
    )


def receipt(request, *, revoke=False):
    return dict(**request, task_id=str(uuid4()), run_id=str(uuid4()), delivery_before=1,
                delivery_after=1 if revoke else 2, denial='source_revoked' if revoke else None)


@contextmanager
def portal(config, invoke):
    server = HTTPServer(('127.0.0.1', 0), MODULE['handler'](config, invoke))
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


def fetch(port, method, route='/', *, username='fixture-reviewer', origin=None):
    headers = {}
    if username:
        headers['Authorization'] = 'Basic ' + base64.b64encode((username + ':fixture-password').encode()).decode()
    if origin:
        headers['Origin'] = origin
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        connection.request(method, route, headers=headers)
        response = connection.getresponse()
        return response.status, response.read().decode()
    finally:
        connection.close()


def test_browser_action_requires_operator_and_origin_before_executor():
    config = fixture_config()
    calls = []

    def invoke(request):
        calls.append(request)
        return receipt(request, revoke=request['scenario'] == 'd4-revoke')

    with portal(config, invoke) as port:
        assert fetch(port, 'GET', username='viewer')[0] == 401
        assert fetch(port, 'POST', '/scenario/d4-deliver', origin='https://wrong.test')[0] == 403
        assert fetch(port, 'POST', '/scenario/arbitrary', origin=config['origin'])[0] == 400
        assert not calls
        assert '合成 D4 试验报告' in fetch(port, 'GET')[1]
        for scenario, count in [('d4-deliver', '1 → 2'), ('d4-revoke', '1 → 1')]:
            status, body = fetch(port, 'POST', '/scenario/' + scenario, origin=config['origin'])
            assert status == 200 and '通过' in body and count in body
            assert calls[-1]['binding'] == config['binding']
            assert calls[-1]['scenario'] == scenario
            assert len(calls[-1]['operation']) == 32


def test_stale_receipt_or_expired_session_cannot_pass():
    config = fixture_config()

    def invoke(request):
        return receipt(dict(request, binding=dict(config['binding'], merge='e' * 40)))

    with portal(config, invoke) as port:
        status, message = fetch(port, 'POST', '/scenario/d4-deliver', origin=config['origin'])
        assert status == 503 and '受阻' in message
        config['binding']['expires_at'] = 1
        assert fetch(port, 'POST', '/scenario/d4-deliver', origin=config['origin'])[0] == 410


def test_d4_policy_ttl_cannot_exceed_one_hour():
    config = fixture_config()
    MODULE['validate_config'](config)
    config['binding']['expires_at'] += 1
    with pytest.raises(ValueError, match='acceptance window'):
        MODULE['validate_config'](config)
