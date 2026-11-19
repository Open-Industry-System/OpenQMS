#!/usr/bin/env python3
"""Root-side shared-test control. Caller holds both Oracle deployment locks."""
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
D4_CLEANUP = Path('/usr/local/lib/openqms/d4-acceptance/cleanup.py')
ACCEPTANCE_SECONDS = 2 * 3600
LEASE = re.compile(r'[0-9a-f]{32}')
REQUEST_LIMIT = 128 * 1024

ACTION_FIELDS = {
    'status': {'action'},
    'retry': {'action', 'release'},
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
    return request


def route(slot):
    pr, merge = slot['pr'], slot['merge']
    return (
        f'{HOST} {{\n'
        f'\treverse_proxy openqms-pr-{pr}-web:8080 {{\n'
        f'\t\theader_down X-OpenQMS-Test-PR "{pr}"\n'
        f'\t\theader_down X-OpenQMS-Test-Version "{merge}"\n'
        '\t}\n'
        '}\n'
    )


def owned_route(path, slot, action):
    # Also inspect symlinks with missing targets. Never overwrite an unmanaged
    # route or remove something installed outside the shared scheduler.
    if path.is_symlink():
        raise ValueError('shared-test route cannot be a symlink')
    if exists(path) and (slot['phase'] == 'idle' or path.read_text() != route(slot)):
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
    if slot['phase'] != 'testing' or now >= slot['expires_at']:
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
                or not completed < binding['expires_at'] <= slot['expires_at']
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


def cleanup_d4(lease):
    try:
        for path in (D4_CLEANUP, *D4_CLEANUP.parents):
            info = path.lstat()
            kind = stat.S_ISREG if path == D4_CLEANUP else stat.S_ISDIR
            if not kind(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError('untrusted D4 cleanup installation')
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
    database = state_database()
    queue = queue_type(database)
    slot = current(queue, database)
    action = request['action']
    if action == 'status':
        return slot
    helper = preview.helper
    fixed_route = helper.ROUTES / 'shared-test.caddy'
    if action == 'retry':
        owned_route(fixed_route, slot, action)
        require_clean_start(preview)
        return queue.retry_failed(request['release'])
    if action == 'tick':
        owned_route(fixed_route, slot, action)
        if slot['phase'] == 'idle' and request['eligible']:
            require_clean_start(preview)
        return queue.tick(request['eligible'], int(time.time()))

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
        owned_route(fixed_route, slot, action)
        legacy_route = helper.ROUTES / f'pr-{slot["pr"]}.caddy'
        if exists(legacy_route) or helper.active_prs() != {str(slot['pr'])}:
            raise ValueError('shared-test runtime inventory is not exclusive')
        verify_rollout(preview, slot)
        roles = preview.shared_account_roles(slot['pr'], slot['merge'], lease)
        if slot['phase'] == 'testing':
            if now >= slot['expires_at'] or not exists(fixed_route):
                raise ValueError('shared-test route is no longer ready')
            return dict(slot, test_roles=roles)
        if not exists(fixed_route):
            helper.publish(fixed_route, route(slot), helper.validate, helper.reload)
        ready = queue.acknowledge(lease, 'ready', int(time.time()), ACCEPTANCE_SECONDS, request['eligible'])
        return dict(ready, test_roles=roles)
    if action == 'd4-passed':
        proofs = request['proofs']
        current_proofs = d4_evidence(slot, now)
        if (not isinstance(proofs, dict) or not proofs or not proofs.keys() <= current_proofs.keys()
                or any(current_proofs[key] != proof for key, proof in proofs.items())):
            raise ValueError('D4 receipts no longer match active lease')
    if action in {'passed', 'd4-passed'}:
        return queue.acknowledge(lease, 'passed', now, eligible=request['eligible'])
    if action == 'deploy-failed':
        return queue.acknowledge(lease, action, now)
    if action not in {'release', 'released'} or slot['phase'] != 'releasing':
        raise ValueError('shared-test release does not match slot phase')

    owned_route(fixed_route, slot, action)
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
    return queue.acknowledge(lease, 'released', int(time.time()))
