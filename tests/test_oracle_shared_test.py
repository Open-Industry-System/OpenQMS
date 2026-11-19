import json
from pathlib import Path
import runpy

import pytest


ROOT = Path(__file__).parents[1]
client = runpy.run_path(str(ROOT / 'scripts/oracle-shared-test.py'))
core = runpy.run_path(str(ROOT / 'scripts/shared-test-queue.py'))


class API:
    repo = 'owner/OpenQMS'

    def get(self, path):
        return {'number': int(path.rsplit('/', 1)[-1])}

    def notice(self, number, text):
        assert text == f'ready {number}'


def fixture_row(pr):
    return (
        {'pr': pr, 'head': 'a' * 40, 'merge': 'b' * 40, 'plan': 'c' * 64},
        100 + pr, {'number': pr},
    )


def test_existing_prs_have_one_slot_and_confirmation_releases_before_next(tmp_path, monkeypatch):
    queue = core['Queue'](tmp_path / 'queue.sqlite')
    events = []
    published = {}
    confirmed = set()
    next_candidates = [fixture_row(46), fixture_row(45)]
    now = 200
    queue_client = client['reconcile'].__globals__
    monkeypatch.setattr(queue_client['time'], 'time', lambda: now)

    def host(request):
        action = request['action']
        if action == 'tick':
            return queue.tick(request['eligible'], now)
        if action == 'status':
            with queue.transaction() as conn:
                return queue.describe(queue.slot(conn))
        if action == 'release':
            events.append(('clean', request['lease']))
            return {}
        if action == 'released':
            return queue.acknowledge(request['lease'], action, now)
        slot = queue.acknowledge(request['lease'], action, now, ttl_seconds=1800,
                                 eligible=request.get('eligible'))
        return dict(slot, test_roles=['field_qe', 'manager']) if action == 'ready' else slot

    callbacks = {
        'deployment_notice': lambda api, pr, *args, **kwargs: events.append(('start', pr)),
        'publication': lambda api, pr, queue_lease: published.get(queue_lease),
        'shared_test_ready_notice': lambda api, pr, run, plan: api.notice(pr['number'], f'ready {pr["number"]}'),
        'verified_acceptance': lambda api, pr, run, plan: pr['number'] in confirmed,
        'shared_test_released_notice': lambda api, slot: events.append(('retired', slot['pr'])),
    }
    monkeypatch.setitem(queue_client, 'ACCEPTANCE', callbacks)
    receipt = tmp_path / 'evidence.json'

    def reconcile():
        client['reconcile'](
            API(), lambda: next_candidates, host,
            lambda slot, ci: events.append(('deploy', slot['pr'], ci)),
            lambda slot: events.append(('health', slot['pr'])), receipt,
        )

    reconcile()
    first = json.loads(receipt.read_text())
    assert first['pr'] == 45
    assert first['sha'] == next_candidates[1][0]['merge']
    assert events == [('start', 45), ('deploy', 45, 145), ('health', 45)]
    published[first['queue_lease']] = {'id': 12}

    reconcile()
    assert events[3:] == [('health', 45)]
    confirmed.add(45)
    reconcile()
    assert events[4:] == [
        ('health', 45), ('clean', first['queue_lease']), ('retired', 45),
        ('start', 46), ('deploy', 46, 146), ('health', 46),
    ]
    assert json.loads(receipt.read_text())['pr'] == 46


def test_only_preview_commands_can_include_shared_lease(tmp_path):
    release = client['RELEASE']
    key = tmp_path / 'key'
    key.write_text('fictional')
    key.chmod(0o600)
    cfg = dict(RELEASE_SHA='a' * 40, RELEASE_KIND='preview',
               ORACLE_SSH_TARGET='openqms-deploy@oracle.example', ORACLE_SSH_KEY=str(key),
               ORACLE_KNOWN_HOSTS=str(key), ORACLE_REVALIDATE_CMD='true', PREVIEW_PR='45',
               ORACLE_SHARED_TEST_LEASE='b' * 32)
    context = release['validate'](cfg)
    context.update(manifest_hash='c' * 64, controller_hash='d' * 64)
    assert release['remote_command'](context, 'lock')[:5] == [
        'preview', 'leased', 'b' * 32, 'lock', '45',
    ]
    with pytest.raises(ValueError, match='invalid shared test'):
        release['validate'](dict(cfg, RELEASE_KIND='production'))


def test_production_waits_for_shared_host_lock_but_not_auth_errors(monkeypatch):
    release = client['RELEASE']
    wait = release['wait_for_lease']
    functions = wait.__globals__
    calls = []

    def acquire(context):
        calls.append(context['RELEASE_KIND'])
        if len(calls) == 1:
            raise release['LeaseBusy']('locked')
        return object()

    monkeypatch.setenv('ORACLE_WAIT_FOR_DEPLOY_LEASE', 'true')
    monkeypatch.setitem(functions, 'acquire_lease', acquire)
    monkeypatch.setattr(functions['time'], 'sleep', lambda _: None)
    assert wait({'RELEASE_KIND': 'production'})
    assert calls == ['production', 'production']

    def reject(context):
        raise ValueError('authorization rejected')

    monkeypatch.setitem(functions, 'acquire_lease', reject)
    with pytest.raises(ValueError, match='authorization rejected'):
        wait({'RELEASE_KIND': 'production'})


def test_fixed_health_rejects_success_from_the_wrong_pr(monkeypatch):
    from contextlib import nullcontext
    from io import BytesIO

    slot = {'pr': 45, 'merge': 'a' * 40}
    response = BytesIO(b'{"status":"ok"}')
    response.url = client['URL'] + '/api/health'
    response.headers = {
        'X-OpenQMS-Test-PR': '46',
        'X-OpenQMS-Test-Version': slot['merge'],
    }
    monkeypatch.setattr(client['urllib'].request, 'urlopen',
                        lambda *args, **kwargs: nullcontext(response))
    with pytest.raises(RuntimeError, match='version|health'):
        client['public_health'](slot)
    response.headers['X-OpenQMS-Test-PR'] = '45'
    client['public_health'](slot)


def test_candidate_fetch_uses_scoped_git_https_basic_auth(monkeypatch):
    import base64

    monkeypatch.setenv('GH_TOKEN', 'test-placeholder-token')
    calls = []
    monkeypatch.setattr(client['subprocess'], 'run', lambda args, **params: calls.append((args, params)))
    slot = dict(fixture_row(45)[0], lease='d' * 32)
    client['deploy'](slot, 145)

    fetch, release = calls
    assert fetch[0] == ['git', 'fetch', '--no-tags', 'origin', slot['merge']]
    assert 'test-placeholder-token' not in ' '.join(fetch[0])
    environment = fetch[1]['env']
    assert environment['GIT_CONFIG_KEY_0'] == 'http.https://github.com/.extraheader'
    scheme, encoded = environment['GIT_CONFIG_VALUE_0'].removeprefix('AUTHORIZATION: ').split()
    assert scheme == 'basic'
    assert base64.b64decode(encoded).decode() == 'x-access-token:test-placeholder-token'
    assert environment['GIT_TERMINAL_PROMPT'] == '0'
    assert 'GIT_CONFIG_VALUE_0' not in release[1]['env']
    assert release[1]['env']['ORACLE_SHARED_TEST_LEASE'] == slot['lease']


def test_first_certificate_activation_allows_bounded_https_retry(monkeypatch):
    from contextlib import nullcontext
    from io import BytesIO
    from urllib.error import URLError

    slot = {'pr': 45, 'merge': 'a' * 40}
    response = BytesIO(b'{"status":"ok"}')
    response.url = client['URL'] + '/api/health'
    response.headers = {'X-OpenQMS-Test-PR': '45', 'X-OpenQMS-Test-Version': slot['merge']}
    requests = iter([URLError('TLS not yet available'), response])
    waits = []

    def open_url(*args, **kwargs):
        value = next(requests)
        if isinstance(value, Exception):
            raise value
        return nullcontext(value)

    monkeypatch.setattr(client['urllib'].request, 'urlopen', open_url)
    monkeypatch.setattr(client['time'], 'sleep', waits.append)
    client['public_health'](slot)
    assert waits == [3]
