import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


remote = load('oracle-shared-test-remote')
Queue = load('shared-test-queue').Queue
receiver = load('oracle-deploy-receiver')


def identity(pr, head='a'):
    return {'pr': pr, 'head': head * 40, 'merge': 'b' * 40, 'plan': 'c' * 64}


@pytest.fixture
def host(tmp_path, monkeypatch):
    db = tmp_path / 'queue.sqlite3'
    monkeypatch.setattr(remote, 'state_database', lambda: db)
    monkeypatch.setattr(remote, 'time', SimpleNamespace(time=lambda: 100))
    helper = load('oracle-preview')
    helper.ROUTES = tmp_path / 'routes'
    helper.ROUTES.mkdir()
    helper.active_prs = Mock(return_value=set())
    helper.validate = Mock()
    helper.reload = Mock()
    helper.cleanup = Mock(side_effect=lambda _: setattr(helper.active_prs, 'return_value', set()))
    base = tmp_path / 'projects'
    base.mkdir()
    release = Mock(spec=['verify', 'assert_images', 'assert_application_running'])
    preview = SimpleNamespace(
        helper=helper, BASE=base, PreviewRelease=Mock(return_value=release),
        prod=SimpleNamespace(regular=lambda path: path),
        shared_account_roles=Mock(return_value=['field_qe', 'manager']),
        shared_account_path=lambda lease: tmp_path / f'{lease}.json',
        remove_shared_accounts=Mock(side_effect=lambda lease: (tmp_path / f'{lease}.json').unlink(missing_ok=True)),
    )
    return preview, release


def run(host, action, **fields):
    return remote.run({'action': action, **fields}, host[0], Queue)


def stage_runtime(host, slot, sha=None):
    preview, release = host
    preview.helper.active_prs.return_value = {str(slot['pr'])}
    project = preview.BASE / f'pr-{slot["pr"]}'
    project.mkdir()
    (project / 'current-release.json').write_text(json.dumps({
        'sha': sha or slot['merge'], 'shared_lease': slot['lease'],
        'manifest': 'd' * 64, 'controller': 'e' * 64,
        'images': {'web': 'sha256:' + 'f' * 64, 'backend': 'sha256:' + '1' * 64},
    }))
    return release


def test_host_assigns_fixed_route_and_releases_before_next_pr(host):
    eligible = [identity(46), identity(45)]
    first = run(host, 'tick', eligible=eligible)
    assert first['pr'] == 45
    stage_runtime(host, first)
    ready = run(host, 'ready', lease=first['lease'], eligible=eligible)
    path = host[0].helper.ROUTES / 'shared-test.caddy'
    assert remote.HOST in path.read_text()
    assert 'openqms-pr-45-web:8080' in path.read_text()
    assert f'X-OpenQMS-Test-Version "{first["merge"]}"' in path.read_text()
    assert not (path.parent / 'pr-45.caddy').exists()
    assert ready['expires_at'] == 100 + 7200
    assert ready['test_roles'] == ['field_qe', 'manager']
    host[0].shared_account_roles.assert_called_once_with(45, first['merge'], first['lease'])
    assert run(host, 'ready', lease=first['lease'], eligible=eligible) == ready
    assert host[0].helper.reload.call_count == 1

    with pytest.raises(ValueError, match='stale'):
        run(host, 'release', lease='0' * 32)
    assert path.exists()
    assert run(host, 'passed', lease=first['lease'], eligible=eligible)['phase'] == 'releasing'
    assert run(host, 'tick', eligible=eligible)['pr'] == 45
    with pytest.raises(ValueError, match='not complete'):
        run(host, 'released', lease=first['lease'])
    run(host, 'release', lease=first['lease'])
    assert not path.exists()
    host[0].helper.cleanup.assert_called_once_with('45')
    assert run(host, 'tick', eligible=eligible)['phase'] == 'releasing'
    run(host, 'release', lease=first['lease'])  # Retriable after notice failure.
    run(host, 'released', lease=first['lease'])
    assert run(host, 'tick', eligible=eligible)['pr'] == 46


def test_bootstrap_preserves_existing_preview_and_unknown_fixed_route(host):
    helper = host[0].helper
    helper.active_prs.return_value = {'45'}
    with pytest.raises(ValueError, match='drained'):
        run(host, 'tick', eligible=[identity(46)])
    assert run(host, 'status') == {'phase': 'idle'}
    helper.active_prs.return_value = set()
    path = helper.ROUTES / 'shared-test.caddy'
    path.write_text('unrelated content')
    with pytest.raises(ValueError, match='unrelated'):
        run(host, 'tick', eligible=[identity(46)])
    assert path.read_text() == 'unrelated content'
    helper.cleanup.assert_not_called()
    helper.reload.assert_not_called()


def test_old_version_and_unrelated_inventory_cannot_be_published(host):
    eligible = [identity(45)]
    slot = run(host, 'tick', eligible=eligible)
    stage_runtime(host, slot, '0' * 40)
    with pytest.raises(ValueError, match='match shared-test version'):
        run(host, 'ready', lease=slot['lease'], eligible=eligible)
    with pytest.raises(ValueError, match='no longer eligible'):
        run(host, 'ready', lease=slot['lease'], eligible=[identity(45, 'd')])
    host[0].helper.active_prs.return_value = {'45', '46'}
    with pytest.raises(ValueError, match='not exclusive'):
        run(host, 'ready', lease=slot['lease'], eligible=eligible)
    assert run(host, 'status')['phase'] == 'deploying'
    host[0].helper.reload.assert_not_called()


def test_failed_cleanup_preserves_slot_across_retries(host):
    eligible = [identity(45), identity(46)]
    slot = run(host, 'tick', eligible=eligible)
    stage_runtime(host, slot)
    run(host, 'ready', lease=slot['lease'], eligible=eligible)
    run(host, 'passed', lease=slot['lease'], eligible=eligible)
    helper = host[0].helper
    helper.cleanup.side_effect = RuntimeError('cleanup failed')
    with pytest.raises(RuntimeError):
        run(host, 'release', lease=slot['lease'])
    assert run(host, 'tick', eligible=eligible)['phase'] == 'releasing'
    helper.cleanup.side_effect = lambda _: setattr(helper.active_prs, 'return_value', set())
    run(host, 'release', lease=slot['lease'])
    run(host, 'released', lease=slot['lease'])
    assert run(host, 'tick', eligible=eligible)['pr'] == 46


def test_current_deploying_lease_required_and_legacy_cleanup_rejected(host):
    eligible = [identity(45)]
    slot = run(host, 'tick', eligible=eligible)
    remote.require_deploying(Queue, '45', slot['merge'], slot['lease'])
    for pr, merge, lease in [
        ('46', slot['merge'], slot['lease']),
        ('45', '0' * 40, slot['lease']),
        ('45', slot['merge'], '0' * 32),
    ]:
        with pytest.raises(ValueError, match='not the current'):
            remote.require_deploying(Queue, pr, merge, lease)
    with pytest.raises(ValueError, match='active lease'):
        remote.guard_legacy_cleanup(Queue, '45')
    remote.guard_legacy_cleanup(Queue, '46')
    stage_runtime(host, slot)
    run(host, 'ready', lease=slot['lease'], eligible=eligible)
    with pytest.raises(ValueError, match='not the current'):
        remote.require_deploying(Queue, '45', slot['merge'], slot['lease'])


@pytest.mark.parametrize('payload', [
    b'', b' ' * (remote.REQUEST_LIMIT + 1),
    b'{"action":"status","action":"tick","eligible":[]}',
    b'{"action":"status","extra":true}',
    b'{"action":"release","lease":"../unsafe"}',
    b'{"action":[]}',
])
def test_host_request_is_bounded_and_strict(payload):
    with pytest.raises(ValueError):
        remote.read_request(io.BytesIO(payload))


def test_receiver_uses_exact_queue_lease_without_granting_route(monkeypatch, tmp_path):
    hash_args = f'{"a" * 40} {"b" * 64} {"c" * 64}'
    raw = f'preview leased {"d" * 32} rollout 45 {hash_args} {{}}'
    monkeypatch.setattr(receiver.sys, 'argv', ['receiver', 'preview', raw])
    monkeypatch.setattr(receiver, 'shared_mode', lambda: True)
    monkeypatch.setattr(receiver, 'shared_modules', lambda: (remote, Queue))
    monkeypatch.setattr(receiver, 'OPERATION', tmp_path / 'operation.lock')
    lease_required = Mock()
    authorize = Mock()
    dispatch = Mock()
    monkeypatch.setattr(receiver, 'require_lease', lease_required)
    monkeypatch.setattr(receiver, 'dispatch', dispatch)
    monkeypatch.setattr(remote, 'require_deploying', authorize)

    receiver.main()
    assert lease_required.call_args.args[0] == ['preview', '45', *hash_args.split(), 'd' * 32]
    authorize.assert_called_once_with(Queue, '45', 'a' * 40, 'd' * 32)
    assert dispatch.call_args.kwargs == {'shared_lease': 'd' * 32}
    monkeypatch.setattr(receiver.sys, 'argv', ['receiver', 'preview', f'preview rollout 45 {hash_args} {{}}'])
    with pytest.raises(ValueError, match='requires|require'):
        receiver.main()
    monkeypatch.setattr(receiver.sys, 'argv', ['receiver', 'production', 'preview queue'])
    with pytest.raises(ValueError, match='cross-role'):
        receiver.main()


def test_existing_legacy_release_is_not_reused_for_shared_slot(monkeypatch, tmp_path):
    preview = load('oracle-preview-remote')
    monkeypatch.setattr(preview, 'BASE', tmp_path)
    merge = 'a' * 40
    lease = 'd' * 32
    legacy = preview.PreviewRelease('45', merge, 'b' * 64, 'c' * 64)
    legacy.control.mkdir(parents=True)
    legacy_manifest = legacy.control / 'controller.sha256'
    legacy_manifest.write_text('legacy-controller')
    shared = preview.PreviewRelease('45', merge, 'b' * 64, 'e' * 64, shared_lease=lease)
    assert shared.root == legacy.project / 'shared-test' / lease / 'releases' / merge
    assert shared.project == legacy.project
    assert not shared.root.exists()
    assert legacy_manifest.read_text() == 'legacy-controller'

    monkeypatch.setattr(receiver, 'installed', lambda _: preview)
    stage = Mock()
    monkeypatch.setattr(receiver, 'stage', stage)
    receiver.dispatch('preview', '45', ['stage', merge, 'b' * 64, 'e' * 64], shared_lease=lease)
    _, factory, base = stage.call_args.args
    assert base / 'releases' / merge == shared.root
    assert factory(merge, 'b' * 64, 'e' * 64).root == shared.root

    (legacy.project / 'shared-test').symlink_to(tmp_path / 'outside')
    with pytest.raises(ValueError, match='unsafe preview release namespace'):
        receiver.dispatch('preview', '45', ['stage', merge, 'b' * 64, 'e' * 64], shared_lease=lease)
    assert stage.call_count == 1


def test_metadata_from_legacy_or_another_lease_cannot_activate_fixed_route(host):
    eligible = [identity(45)]
    slot = run(host, 'tick', eligible=eligible)
    stage_runtime(host, slot)
    preview, _ = host
    path = preview.BASE / 'pr-45' / 'current-release.json'
    metadata = json.loads(path.read_text())
    for stale in ({}, {'shared_lease': '0' * 32}):
        old = {key: value for key, value in metadata.items() if key != 'shared_lease'}
        path.write_text(json.dumps({**old, **stale}))
        with pytest.raises(ValueError, match='version and lease'):
            run(host, 'ready', lease=slot['lease'], eligible=eligible)
    preview.helper.reload.assert_not_called()


def test_shared_lease_cannot_be_released_with_issued_credentials_left_behind(host):
    eligible = [identity(45), identity(46)]
    first = run(host, 'tick', eligible=eligible)
    opened = host[0].shared_account_path(first['lease'])
    opened.write_text('placeholder')
    other = host[0].shared_account_path('f' * 32)
    other.write_text('another lease')
    run(host, 'deploy-failed', lease=first['lease'])
    with pytest.raises(ValueError, match='cleanup is not complete'):
        run(host, 'released', lease=first['lease'])
    run(host, 'release', lease=first['lease'])
    assert not opened.exists() and other.exists()
    assert run(host, 'released', lease=first['lease'])['phase'] == 'idle'
    assert run(host, 'tick', eligible=eligible)['pr'] == 46
