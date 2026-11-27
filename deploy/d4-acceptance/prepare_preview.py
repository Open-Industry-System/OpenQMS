#!/usr/bin/env python3
"""Provision only the D4 scenarios required by the active shared-test lease."""
import argparse
from contextlib import nullcontext
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.request

from allocate import allocate, approved_assets
from browser import SCENARIOS, SHARED_ACCOUNT_ROLES, binding_fingerprint, validate_binding, validate_config
from cleanup import RUN_ROOT, cleanup, command, database_binding
from executor import QUEUE_ROOT, hold_test_slot, load_profile, socket_path_for
from portal_issue import issue
from provision import provision
from runtime_launch import HEX64, IMAGE, SYSTEMCTL, decode, read_owned, require, trusted_directory


CONFIG = Path('/etc/openqms/d4-acceptance/preview-provider.json')
MAC_MARKER = Path('/etc/openqms/mac-shared-test')
MAC_ORIGIN = 'https://d4-test-openqms.smartindustry.world'
ORACLE_ORIGIN = 'https://d4.preview.openqms.smartindustry.world'
PROVIDER_FIELDS = {'origin', 'native_manifest_sha256', 'delivery_image', 'revoke_image',
                   'postgres_image', 'worker_sha256'}
ERRORS = (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError)
BINDING_FIELDS = ('pr', 'head', 'merge', 'plan', 'lease')


def request(raw):
    data = decode(raw)
    require(data.keys() == {'lease', 'roles'} and isinstance(data['lease'], str)
            and re.fullmatch('[a-f0-9]{32}', data['lease']), 'invalid D4 preparation identity')
    roles = data['roles']
    require(isinstance(roles, dict) and roles and roles.keys() <= SCENARIOS.keys()
            and all(value in SHARED_ACCOUNT_ROLES.values() for value in roles.values()),
            'invalid D4 preparation roles')
    return data['lease'], roles


def provider_config():
    trusted_directory(CONFIG.parent)
    config = decode(read_owned(CONFIG, 4096, private=True))
    require(config.keys() == PROVIDER_FIELDS and all(isinstance(value, str) for value in config.values()),
            'invalid provider configuration')
    mac = os.path.lexists(MAC_MARKER)
    if mac:
        trusted_directory(MAC_MARKER.parent)
        require(read_owned(MAC_MARKER, 0, private=True) == b'', 'invalid Mac preview profile')
    require(config['origin'] == (MAC_ORIGIN if mac else ORACLE_ORIGIN)
            and all(HEX64.fullmatch(config[key]) for key in ('native_manifest_sha256', 'worker_sha256'))
            and all(IMAGE.fullmatch(config[key]) for key in ('postgres_image', 'delivery_image', 'revoke_image')),
            'invalid approved provider origins or asset pins')
    return config


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_ingress(origin, binding):
    target = origin + '/healthz'
    # Ignore inherited proxy settings and never follow redirects to a different service.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
    probe = urllib.request.Request(target, headers={'User-Agent': 'OpenQMS-Preview-Health/1.0'})
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with opener.open(probe, timeout=4) as reply:
                if (reply.status == 200 and reply.url == target
                        and reply.headers.get('X-OpenQMS-D4-Binding') == binding_fingerprint(binding)
                        and reply.headers.get('X-OpenQMS-Test-Version') == binding['merge']
                        and reply.headers.get('X-OpenQMS-Test-Lease') == binding['lease']
                        and reply.headers.get('X-OpenQMS-Test-PR') == str(binding['pr'])):
                    return
        except (OSError, ValueError, http.client.HTTPException):
            pass
        time.sleep(1)
    raise ValueError('the exact D4 HTTPS route did not answer')


def start_portal(lease, profile, origin):
    executor = f'openqms-d4-acceptance-executor@{lease}.service'
    portal = f'openqms-d4-acceptance-portal@{lease}.service'
    command(SYSTEMCTL, 'start', executor, portal)
    endpoint = socket_path_for(lease)
    trusted_directory(endpoint.parent)
    until = time.monotonic() + 8
    while time.monotonic() < until and not endpoint.exists():
        time.sleep(0.25)
    socket_status = endpoint.lstat()
    require(stat.S_ISSOCK(socket_status.st_mode) and socket_status.st_uid == 0
            and socket_status.st_gid == profile['portal_gid']
            and stat.S_IMODE(socket_status.st_mode) == 0o660, 'D4 socket identity mismatch')
    for service in (executor, portal):
        require(command(SYSTEMCTL, 'show', '--property=ActiveState', '--value', service) == 'active',
                'D4 service unavailable')
    check_ingress(origin, profile['binding'])


def blocked(reason):
    return {'state': 'blocked', 'reason': reason}


def prepare(lease, roles):
    try:
        config = provider_config()
    except ERRORS:
        return blocked('provider-unconfigured')

    with hold_test_slot():
        slot = database_binding(lease, 'testing')
        allocation_root = QUEUE_ROOT / 'd4'
        allocation_root.mkdir(mode=0o700, exist_ok=True)
        trusted_directory(allocation_root, private=True)
        allocation = allocation_root / lease
        profile_path = allocation / 'profile.json'
        portal_path = RUN_ROOT / lease / 'portal.json'
        try:
            if os.path.lexists(profile_path):
                trusted_directory(allocation, private=True)
                previous = decode(read_owned(profile_path, 8192, private=True))['binding']
                validate_binding(previous, now=previous['issued_at'])
                require(all(previous[key] == slot[key] for key in BINDING_FIELDS), 'D4 lease identity changed')
                if previous['expires_at'] <= time.time():
                    # A renewed issuance gets new tasks, report IDs and proof
                    # files. Its previous browser window and receipts are gone.
                    cleanup(lease, phase='testing')
            if not os.path.lexists(profile_path):
                if os.path.lexists(allocation):
                    # An interrupted preparation was never issued to a browser.
                    cleanup(lease, phase='testing')
                try:
                    native = approved_assets(config, roles)
                except ERRORS:
                    return blocked('runtime-unavailable')
                allocate(slot, allocation, config, roles, native)
                provision(lease, guard=nullcontext)
            trusted_directory(allocation, private=True)
            binding = decode(read_owned(profile_path, 8192, private=True))['binding']
            require(all(binding[key] == slot[key] for key in BINDING_FIELDS), 'D4 lease identity changed')
            if type(binding['expires_at']) is int and binding['expires_at'] <= time.time():
                return blocked('allocation-expired')
            profile = load_profile(profile_path)
            require(profile['cases'].keys() == roles.keys(), 'D4 issued cases do not match the plan')
        except ERRORS:
            return blocked('allocation-failed')
        try:
            if not os.path.lexists(portal_path):
                issue(profile_path, config['origin'], scenario_roles=roles, guard=nullcontext)
            trusted_directory(portal_path.parent, private=True)
            portal = decode(read_owned(portal_path, 8192, private=True))
            validate_config(portal)
            require(portal['binding'] == profile['binding'] and portal['origin'] == config['origin']
                    and portal['scenario_roles'] == roles
                    and portal['executor_socket'] == str(socket_path_for(lease))
                    and portal['tasks'] == {name: case['task_id'] for name, case in profile['cases'].items()},
                    'D4 portal identity changed')
            start_portal(lease, profile, config['origin'])
        except ERRORS:
            return blocked('portal-unavailable')
        if time.time() >= binding['expires_at']:
            return blocked('allocation-expired')
        return {'state': 'ready', 'url': config['origin'] + '/', 'expires_at': binding['expires_at'],
                'scenarios': sorted(roles)}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0 or not shutil.rmtree.avoids_symlink_attacks:
        return blocked('provider-unconfigured')
    os.umask(0o077)
    try:
        raw = sys.stdin.buffer.read(4097)
        require(0 < len(raw) <= 4096, 'invalid D4 preparation request size')
        return prepare(*request(raw))
    except ERRORS:
        return blocked('allocation-failed')


if __name__ == '__main__':
    print(json.dumps(main(), separators=(',', ':')), flush=True)
