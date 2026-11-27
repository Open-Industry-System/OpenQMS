#!/usr/bin/env python3
"""Root-side shared-test control."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from uuid import UUID

MODE = Path('/var/lib/openqms-shared-test')
HOST = 'test.preview.openqms.smartindustry.world'
MAC_ORIGIN = 'http://test-openqms.smartindustry.world:8080'
D4_CLEANUP = Path('/usr/local/lib/openqms/d4-acceptance/cleanup.py')
D4_PREPARE = D4_CLEANUP.with_name('prepare_preview.py')
D4_ORACLE_URL = 'https://d4.preview.openqms.smartindustry.world/'
D4_MAC_URL = 'https://d4-test-openqms.smartindustry.world/'
D4_SCENARIOS = {'d4-deliver', 'd4-revoke'}
D4_ROLES = {'field_qe', 'manager'}
D4_BLOCKERS = {
    'provider-unavailable', 'provider-failed', 'role-unavailable',
    'provider-unconfigured', 'runtime-unavailable', 'allocation-failed',
    'portal-unavailable', 'allocation-expired',
}
D4_PREPARE_TIMEOUT = 900
LEASE = re.compile(r'[0-9a-f]{32}')
REQUEST_LIMIT = 128 * 1024

ACTION_FIELDS = {
    'status': {'action'},
    'retry': {'action', 'release'},
    'switch': {'action', 'comment_id', 'release', 'eligible'},
    'prepare-d4': {'action', 'lease', 'roles'},
    'd4-evidence': {'action', 'lease'},
    'd4-passed': {'action', 'lease', 'eligible', 'proofs'},
    'tick': {'action', 'eligible'},
    'ready': {'action', 'lease', 'eligible'},
    'passed': {'action', 'lease', 'eligible'},
    'deploy-failed': {'action', 'lease'},
    'release': {'action', 'lease'},
    'released': {'action', 'lease'},
}


def exists(path):
    return path.exists() or path.is_symlink()


def enabled():
    if not exists(MODE):
        return False
    info = MODE.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('shared-test mode requires a root-owned 0700 directory')
    return True


def state_database():
    if not enabled():
        raise ValueError('shared-test mode unavailable')
    path = MODE / 'queue.sqlite3'
    if exists(path):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('invalid shared-test state file')
    return path


def current(queue, path):
    if not exists(path):
        return {'phase': 'idle'}
    with queue.transaction() as connection:
        return queue.describe(queue.slot(connection))


def require_deploying(queue_type, pr, merge, lease):
    path = state_database()
    slot = current(queue_type(path), path)
    if (slot['phase'], slot.get('pr'), slot.get('merge'), slot.get('lease')) != (
        'deploying', int(pr), merge, lease,
    ):
        raise ValueError('shared-test deployment is not the current exact release')


def guard_legacy_cleanup(queue_type, pr):
    path = state_database()
    slot = current(queue_type(path), path)
    if slot.get('pr') == int(pr):
        raise ValueError('shared-test resources must be released by their active lease')


def distinct_fields(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError('duplicate shared-test request field')
    return result


def read_request(source):
    raw = source.read(REQUEST_LIMIT + 1)
    if not raw or len(raw) > REQUEST_LIMIT:
        raise ValueError('invalid shared-test request size')
    request = json.loads(raw, object_pairs_hook=distinct_fields)
    if not isinstance(request, dict):
        raise ValueError('shared-test request must be an object')
    action = request.get('action')
    if not isinstance(action, str) or action not in ACTION_FIELDS or set(request) != ACTION_FIELDS[action]:
        raise ValueError('invalid shared-test action fields')
    if 'lease' in request and (not isinstance(request['lease'], str) or not LEASE.fullmatch(request['lease'])):
        raise ValueError('invalid shared-test lease')
    if action == 'prepare-d4':
        roles = request['roles']
        if (not isinstance(roles, dict) or not roles or not roles.keys() <= D4_SCENARIOS
                or any(not isinstance(role, str) or role not in D4_ROLES for role in roles.values())):
            raise ValueError('invalid D4 acceptance roles')
    return request


def route(slot, *, mac=False):
    pr, merge = slot['pr'], slot['merge']
    return (
        f'{MAC_ORIGIN if mac else HOST} {{\n'
        f'\treverse_proxy openqms-pr-{pr}-web:8080 {{\n'
        f'\t\theader_down X-OpenQMS-Test-PR "{pr}"\n'
        f'\t\theader_down X-OpenQMS-Test-Version "{merge}"\n'
        '\t}\n'
        '}\n'
    )


def owned_route(path, slot, action, *, mac=False):
    # Also inspect symlinks with missing targets. Never overwrite an unmanaged
    # route or remove something installed outside the shared scheduler.
    if path.is_symlink():
        raise ValueError('shared-test route cannot be a symlink')
    if exists(path) and (slot['phase'] == 'idle' or path.read_text() != route(slot, mac=mac)):
        raise ValueError(f'unrelated shared-test route during {action}')


def require_clean_start(preview):
    helper = preview.helper
    if (helper.active_prs() or any(preview.BASE.glob('pr-*/preview.env'))
            or any(helper.ROUTES.glob('pr-*.caddy'))):
        raise ValueError('existing preview stacks must be drained before claiming the shared test slot')


def verify_rollout(preview, slot):
    pr = str(slot['pr'])
    metadata_path = preview.BASE / ('pr-' + pr) / 'current-release.json'
    metadata = json.loads(preview.prod.regular(metadata_path).read_text())
    if metadata.get('sha') != slot['merge'] or metadata.get('shared_lease') != slot['lease']:
        raise ValueError('completed deployment does not match shared-test version and lease')
    release = preview.PreviewRelease(
        pr, metadata['sha'], metadata['manifest'], metadata['controller'],
        shared_lease=slot['lease'],
    )
    release.verify()
    release.assert_images(metadata['images'])
    release.assert_application_running(metadata['images'])


def private_file(path):
    for parent in (MODE / 'd4', path.parent.parent, path.parent):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('invalid D4 evidence directory')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError('invalid D4 evidence file')
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise ValueError('invalid D4 evidence size')
    return raw


def d4_evidence(slot, now):
    if slot['phase'] != 'testing':
        return {}
    directory = MODE / 'd4' / slot['lease'] / 'receipts'
    evidence = {}
    for scenario in ('d4-deliver', 'd4-revoke'):
        try:
            raw = private_file(directory / (scenario + '.json'))
        except FileNotFoundError:
            continue
        receipt = json.loads(raw, object_pairs_hook=distinct_fields)
        binding = receipt['binding']
        completed = receipt['completed_at']
        before, after = receipt['delivery_before'], receipt['delivery_after']
        expected_delta, denial = (1, None) if scenario == 'd4-deliver' else (0, 'source_revoked')
        if (set(receipt) != {'binding', 'scenario', 'operation', 'task_id', 'run_id',
                             'delivery_before', 'delivery_after', 'denial', 'completed_at'}
                or set(binding) != {'pr', 'head', 'merge', 'plan', 'lease', 'report_id',
                                    'issued_at', 'expires_at'}
                or any(binding[key] != slot[key] for key in ('pr', 'head', 'merge', 'plan', 'lease'))
                or not all(type(value) is int for value in (completed, binding['issued_at'], binding['expires_at']))
                or not binding['issued_at'] <= completed <= now
                or not completed < binding['expires_at']
                or not 0 < binding['expires_at'] - binding['issued_at'] <= 3600
                or receipt['scenario'] != scenario
                or not LEASE.fullmatch(receipt['operation'])
                or any(str(UUID(value)) != value for value in
                       (receipt['task_id'], receipt['run_id'], binding['report_id']))
                or type(before) is not int or type(after) is not int or before < 0
                or after != before + expected_delta or receipt['denial'] != denial):
            raise ValueError('invalid D4 receipt for active lease')
        if now < binding['expires_at']:
            evidence[scenario] = dict(sha256=sha256(raw).hexdigest(), completed_at=completed,
                                      expires_at=binding['expires_at'])
    return evidence


def trusted_script(script):
    for path in (script, *script.parents):
        info = path.lstat()
        kind = stat.S_ISREG if path == script else stat.S_ISDIR
        if not kind(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('invalid trusted D4 installation')


def d4_blocked(reason):
    return {'state': 'blocked', 'reason': reason}


def d4_preparation_result(raw, roles, expected_url, now):
    if len(raw) > 4096:
        raise ValueError('invalid D4 response size')
    result = json.loads(raw, object_pairs_hook=distinct_fields)
    if isinstance(result, dict):
        state = result.get('state')
        if state == 'blocked' and result.keys() == {'state', 'reason'}:
            if isinstance(result['reason'], str) and result['reason'] in D4_BLOCKERS:
                return result
        if state == 'ready' and result.keys() == {'state', 'url', 'expires_at', 'scenarios'}:
            expires, scenarios = result['expires_at'], result['scenarios']
            if (result['url'] == expected_url and type(expires) is int and now < expires <= now + 3600
                    and isinstance(scenarios, list) and scenarios == sorted(roles)):
                return result
    raise ValueError('invalid D4 readiness response')


def invoke_d4_preparer(lease, roles, expected_url):
    try:
        trusted_script(D4_PREPARE)
    except (OSError, ValueError):
        return d4_blocked('provider-unavailable')
    try:
        result = subprocess.run(
            ['/usr/bin/python3', '-E', '-s', '-B', str(D4_PREPARE)],
            cwd='/', env={}, input=json.dumps({'lease': lease, 'roles': roles}).encode(),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=D4_PREPARE_TIMEOUT, check=False,
        )
        if result.returncode:
            return d4_blocked('provider-failed')
        return d4_preparation_result(result.stdout, roles, expected_url, int(time.time()))
    except (OSError, ValueError, subprocess.SubprocessError):
        return d4_blocked('provider-failed')


def prepare_d4(request, load_preview, queue_type, locks):
    lease, roles = request['lease'], request['roles']
    with locks():
        database = state_database()
        queue = queue_type(database)
        slot = current(queue, database)
        if slot['phase'] != 'testing' or slot.get('lease') != lease:
            raise ValueError('D4 preparation requires the current testing lease')
        preview = load_preview()
        helper = preview.helper
        mac = helper.mac_shared_profile()
        fixed_route = helper.ROUTES / 'shared-test.caddy'
        owned_route(fixed_route, slot, request['action'], mac=mac)
        if not exists(fixed_route):
            raise ValueError('D4 preparation requires a published preview')
        verify_rollout(preview, slot)
        issued = preview.shared_account_roles(slot['pr'], slot['merge'], lease)
        if any(role not in issued for role in roles.values()):
            return d4_blocked('role-unavailable')

    # The reviewed provider acquires the deployment lock itself and binds all
    # resource mutations to the exact lease. Do not hold it while we wait.
    result = invoke_d4_preparer(lease, roles, D4_MAC_URL if mac else D4_ORACLE_URL)
    with locks():
        if current(queue, state_database()) != slot:
            raise ValueError('shared-test lease changed during D4 preparation')
        owned_route(fixed_route, slot, request['action'], mac=mac)
        if not exists(fixed_route):
            raise ValueError('shared-test route changed during D4 preparation')
    return result


def cleanup_d4(lease):
    try:
        trusted_script(D4_CLEANUP)
        result = subprocess.run(
            ['/usr/bin/python3', '-E', '-s', '-B', str(D4_CLEANUP), '--lease', lease],
            cwd='/', env={}, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=180, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError('D4 allocation still requires trusted cleanup') from None
    if result.returncode:
        raise ValueError('D4 allocation still requires trusted cleanup')


def run(request, preview, queue_type):
    """Reconcile a queue operation with both host deployment locks held."""
    database = state_database()
    queue = queue_type(database)
    slot = current(queue, database)
    action = request['action']
    if action == 'status':
        return slot
    helper = preview.helper
    mac = helper.mac_shared_profile()
    fixed_route = helper.ROUTES / 'shared-test.caddy'
    if action == 'switch':
        owned_route(fixed_route, slot, action, mac=mac)
        if slot['phase'] == 'idle':
            require_clean_start(preview)
        return queue.request_switch(request['comment_id'], request['release'], request['eligible'])
    if action == 'retry':
        owned_route(fixed_route, slot, action, mac=mac)
        require_clean_start(preview)
        return queue.retry_failed(request['release'])
    if action == 'tick':
        owned_route(fixed_route, slot, action, mac=mac)
        if slot['phase'] == 'idle' and request['eligible']:
            require_clean_start(preview)
        return queue.tick(request['eligible'])

    lease = request['lease']
    if slot.get('lease') != lease:
        raise ValueError('stale or unknown shared-test lease')
    now = int(time.time())
    if action == 'd4-evidence':
        return d4_evidence(slot, now)
    if action == 'ready':
        if slot['phase'] not in {'deploying', 'testing'}:
            raise ValueError('shared-test readiness does not match slot phase')
        identity = {field: slot[field] for field in ('pr', 'head', 'merge', 'plan')}
        queue.snapshot(request['eligible'])
        if identity not in request['eligible']:
            raise ValueError('shared-test version is no longer eligible')
        owned_route(fixed_route, slot, action, mac=mac)
        legacy_route = helper.ROUTES / f'pr-{slot["pr"]}.caddy'
        if exists(legacy_route) or helper.active_prs() != {str(slot['pr'])}:
            raise ValueError('shared-test runtime inventory is not exclusive')
        verify_rollout(preview, slot)
        roles = preview.shared_account_roles(slot['pr'], slot['merge'], lease)
        if slot['phase'] == 'testing':
            if not exists(fixed_route):
                raise ValueError('shared-test route is no longer ready')
            return dict(slot, test_roles=roles)
        if not exists(fixed_route):
            helper.publish(fixed_route, route(slot, mac=mac), helper.validate, helper.reload)
        ready = queue.acknowledge(lease, 'ready', eligible=request['eligible'])
        return dict(ready, test_roles=roles)
    if action == 'd4-passed':
        proofs = request['proofs']
        current_proofs = d4_evidence(slot, now)
        if (not isinstance(proofs, dict) or not proofs or not proofs.keys() <= current_proofs.keys()
                or any(current_proofs[key] != proof for key, proof in proofs.items())):
            raise ValueError('D4 receipts no longer match active lease')
    if action in {'passed', 'd4-passed'}:
        return queue.acknowledge(lease, 'passed', eligible=request['eligible'])
    if action == 'deploy-failed':
        return queue.acknowledge(lease, action)
    if action not in {'release', 'released'} or slot['phase'] != 'releasing':
        raise ValueError('shared-test release does not match slot phase')

    owned_route(fixed_route, slot, action, mac=mac)
    pr = str(slot['pr'])
    d4_allocation = MODE / 'd4' / lease
    if action == 'release':
        if exists(fixed_route):
            helper.publish(fixed_route, None, helper.validate, helper.reload)
        # Cleanup validates every resource label and scopes deletion to this PR.
        helper.cleanup(pr)
        preview.remove_shared_accounts(lease)
        if exists(d4_allocation):
            cleanup_d4(lease)
        if exists(d4_allocation):
            raise ValueError('D4 allocation still requires trusted cleanup')
        return slot

    # The notification may fail after physical cleanup. Keep the lease held
    # until the caller acknowledges and the actual owned inventory is empty.
    if (exists(fixed_route) or exists(helper.ROUTES / f'pr-{pr}.caddy')
            or exists(preview.BASE / f'pr-{pr}' / 'preview.env')
            or exists(preview.shared_account_path(lease))
            or exists(d4_allocation)
            or pr in helper.active_prs()):
        raise ValueError('shared-test cleanup is not complete')
    return queue.acknowledge(lease, 'released')
