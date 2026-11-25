#!/usr/bin/env python3
"""Bind the D4 browser to the active shared test accounts and scenario roles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import secrets
import sys

from browser import SHARED_ACCOUNT_ROLES, validate_config
from cleanup import RUN_ROOT, database_binding
from executor import QUEUE_ROOT, hold_test_slot, load_profile, root_private, socket_path_for
from runtime_launch import read_owned, trusted_directory


PREVIEW_CONTROLLER = Path('/usr/local/lib/openqms/oracle-production/scripts/oracle-preview-remote.py')


def shared_passwords(binding):
    trusted_directory(PREVIEW_CONTROLLER.parent)
    read_owned(PREVIEW_CONTROLLER, 262144)
    # Reuse the controller's exact root-owned credential and lease checks.
    # Importing these trusted files must not create cache entries in the release tree.
    bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        preview = runpy.run_path(str(PREVIEW_CONTROLLER))
    finally:
        sys.dont_write_bytecode = bytecode
    return preview['load_shared_accounts'](str(binding['pr']), binding['merge'], binding['lease'])


def write_private(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(data, stream, separators=(',', ':'))
        stream.flush()
        os.fsync(stream.fileno())


def issue(profile_path, origin, *, scenario_roles):
    lease = profile_path.parent.name
    if profile_path != QUEUE_ROOT / 'd4' / lease / 'profile.json':
        raise ValueError('fixed D4 profile path required')
    with hold_test_slot():
        trusted_directory(profile_path.parent, private=True)
        profile = load_profile(profile_path)
        binding = profile['binding']
        slot = database_binding(lease, 'testing')
        if any(binding[key] != slot[key] for key in ('pr', 'head', 'merge', 'plan', 'lease')):
            raise ValueError('D4 profile does not match the active test slot')

        directory = RUN_ROOT / lease
        credential = profile_path.parent / 'portal-credential.json'
        if directory.exists() or directory.is_symlink() or credential.exists() or credential.is_symlink():
            raise ValueError('D4 portal has already been issued')
        passwords = shared_passwords(binding)
        accounts = {}
        for username, role in SHARED_ACCOUNT_ROLES.items():
            salt = secrets.token_bytes(16)
            digest = hashlib.scrypt(passwords[username].encode(), salt=salt, n=16384, r=8, p=1)
            accounts[username] = dict(role=role, salt=salt.hex(), password_digest=digest.hex())
        config = dict(binding=binding, origin=origin, accounts=accounts, scenario_roles=scenario_roles,
                      executor_socket=str(socket_path_for(lease)), report_label=f"PR #{binding['pr']} D4",
                      tasks={scenario: case['task_id'] for scenario, case in profile['cases'].items()})
        validate_config(config)

        # PID 1 reads the root-protected config as a service credential and
        # presents a read-only copy owned by the unprivileged browser service.
        trusted_directory(RUN_ROOT, private=True)
        directory.mkdir(mode=0o700)
        root_private(directory, directory=True)
        write_private(directory / 'portal.json', config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--origin', required=True)
    roles = sorted(SHARED_ACCOUNT_ROLES.values())
    parser.add_argument('--deliver-role', required=True, choices=roles)
    parser.add_argument('--revoke-role', required=True, choices=roles)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('trusted D4 portal operator required')
    try:
        issue(args.profile, args.origin, scenario_roles={
            'd4-deliver': args.deliver_role,
            'd4-revoke': args.revoke_role,
        })
    except (ValueError, OSError, RuntimeError, KeyError):
        raise SystemExit('D4 portal could not bind the shared test accounts for this lease') from None


if __name__ == '__main__':
    main()
