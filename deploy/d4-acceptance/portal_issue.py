#!/usr/bin/env python3
"""Issue private browser credentials for the currently active D4 allocation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets

from browser import validate_config
from cleanup import RUN_ROOT, database_binding
from executor import QUEUE_ROOT, hold_test_slot, load_profile, root_private, socket_path_for
from runtime_launch import trusted_directory


def write_private(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(data, stream, separators=(',', ':'))
        stream.flush()
        os.fsync(stream.fileno())


def issue(profile_path, origin):
    lease = profile_path.parent.name
    if profile_path != QUEUE_ROOT / 'd4' / lease / 'profile.json':
        raise ValueError('fixed D4 profile path required')
    with hold_test_slot():
        trusted_directory(profile_path.parent, private=True)
        profile = load_profile(profile_path)
        binding = profile['binding']
        slot = database_binding(lease, 'testing')
        if (any(binding[key] != slot[key] for key in ('pr', 'head', 'merge', 'plan', 'lease'))
                or binding['expires_at'] > slot['expires_at']):
            raise ValueError('D4 profile does not match the active test slot')

        directory = RUN_ROOT / lease
        credential = profile_path.parent / 'portal-credential.json'
        if directory.exists() or directory.is_symlink() or credential.exists() or credential.is_symlink():
            raise ValueError('D4 portal has already been issued')
        salt = secrets.token_bytes(16)
        password = secrets.token_urlsafe(36)
        username = 'tester-' + secrets.token_hex(6)
        config = dict(binding=binding, origin=origin, username=username, salt=salt.hex(),
                      password_digest=hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex(),
                      executor_socket=str(socket_path_for(lease)), report_label=f"PR #{binding['pr']} D4",
                      tasks={scenario: case['task_id'] for scenario, case in profile['cases'].items()})
        validate_config(config)

        # PID 1 reads the root-protected config as a service credential and
        # presents a read-only copy owned by the unprivileged browser service.
        trusted_directory(RUN_ROOT, private=True)
        directory.mkdir(mode=0o700)
        root_private(directory, directory=True)
        write_private(directory / 'portal.json', config)
        write_private(credential, dict(username=username, password=password, origin=origin,
                                       expires_at=binding['expires_at']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--origin', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('trusted D4 portal operator required')
    try:
        issue(args.profile, args.origin)
    except (ValueError, OSError, RuntimeError):
        raise SystemExit('D4 portal credentials could not be issued for this lease') from None


if __name__ == '__main__':
    main()
