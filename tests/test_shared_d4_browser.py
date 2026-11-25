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


def fetch(port, method, route='/', *, username='fixture-reviewer', password='fixture-password',
          origin=None, headers=None):
    headers = dict(headers or {})
    if username:
        credentials = base64.b64encode(f'{username}:{password}'.encode()).decode()
        headers['Authorization'] = 'Basic ' + credentials
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



@pytest.fixture
def shared_config():
    config = fixture_config()
    for key in ('username', 'salt', 'password_digest'):
        del config[key]
    accounts = {}
    for username, role, seed in [('engineer', 'field_qe', 2), ('manager', 'manager', 3)]:
        salt = bytes([seed]) * 16
        digest = hashlib.scrypt(f'{username}-fixture'.encode(), salt=salt, n=2**14, r=8, p=1)
        accounts[username] = dict(role=role, salt=salt.hex(), password_digest=digest.hex())
    config.update(accounts=accounts, scenario_roles={'d4-deliver': 'field_qe', 'd4-revoke': 'manager'})
    return config


def test_shared_accounts_get_only_their_assigned_scenario(shared_config):
    MODULE['validate_config'](shared_config)
    requests = []

    def invoke(request):
        requests.append(request)
        return receipt(request, revoke=request['scenario'] == 'd4-revoke')

    with portal(shared_config, invoke) as port:
        assert fetch(port, 'GET', username='viewer', password='viewer-fixture')[0] == 401
        for username in ('demo-engineer', 'demo-manager'):
            assert fetch(port, 'POST', '/scenario/d4-deliver', username=username, password='public-fixture',
                         origin=shared_config['origin'])[0] == 401
        assert fetch(port, 'GET', username=None, headers={
            'Authorization': 'Bearer candidate-fixture', 'X-Role': 'manager',
        })[0] == 401
        assert fetch(port, 'GET', username='engineer', password='manager-fixture')[0] == 401
        for username, allowed, blocked in [('engineer', 'd4-deliver', 'd4-revoke'),
                                            ('manager', 'd4-revoke', 'd4-deliver')]:
            login = dict(username=username, password=f'{username}-fixture')
            status, body = fetch(port, 'GET', **login)
            assert status == 200 and f'/scenario/{allowed}' in body and f'/scenario/{blocked}' not in body
            assert fetch(port, 'POST', f'/scenario/{blocked}', origin=shared_config['origin'], **login)[0] == 403
            assert fetch(port, 'POST', f'/scenario/{allowed}', origin='https://wrong.test', **login)[0] == 403
            status, body = fetch(port, 'POST', f'/scenario/{allowed}', origin=shared_config['origin'], **login)
            assert status == 200 and '通过' in body
    assert [item['scenario'] for item in requests] == ['d4-deliver', 'd4-revoke']


def test_shared_account_without_assigned_scenario_is_denied(shared_config):
    shared_config['scenario_roles']['d4-revoke'] = 'field_qe'
    MODULE['validate_config'](shared_config)
    with portal(shared_config, lambda _: pytest.fail('executor was invoked')) as port:
        login = dict(username='manager', password='manager-fixture')
        assert fetch(port, 'GET', **login)[0] == 403
        assert fetch(port, 'POST', '/scenario/d4-deliver', origin=shared_config['origin'], **login)[0] == 403


@pytest.mark.parametrize('violation', ['wrong-role', 'viewer', 'missing-role', 'missing-scenario', 'legacy'])
def test_invalid_shared_credential_configuration_fails_closed(shared_config, violation):
    if violation == 'wrong-role':
        shared_config['accounts']['engineer']['role'] = 'manager'
    elif violation == 'viewer':
        shared_config['accounts']['viewer'] = shared_config['accounts']['engineer']
    elif violation == 'missing-role':
        del shared_config['accounts']['manager']
    elif violation == 'missing-scenario':
        del shared_config['scenario_roles']['d4-revoke']
    else:
        shared_config.update(username='legacy-fixture')
    with pytest.raises(ValueError, match='invalid shared acceptance'):
        MODULE['validate_config'](shared_config)
