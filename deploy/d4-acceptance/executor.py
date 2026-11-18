#!/usr/bin/env python3
"""Trusted local broker between the D4 browser and the reviewed Linux runtime."""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import socket
from socketserver import BaseRequestHandler, UnixStreamServer
import sqlite3
import stat
import struct
import time

from browser import MAX_MESSAGE, SCENARIOS, validate_binding, validated_receipt


QUEUE_ROOT = Path('/var/lib/openqms-shared-test')
QUEUE_LOCK = Path('/run/lock/openqms-deploy.lock')
SOCKET_DIR = Path('/run/openqms-d4-acceptance')
SOCKET_PATH = SOCKET_DIR / 'executor.sock'


def root_private(path, directory=False):
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    mode = 0o700 if directory else 0o600
    if (not expected(info.st_mode) or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != mode or (not directory and info.st_nlink != 1)):
        raise ValueError('protected D4 runtime configuration unavailable')


def load_profile(path):
    root_private(path.parent, directory=True)
    root_private(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        raw = stream.read(MAX_MESSAGE + 1)
    if len(raw) > MAX_MESSAGE:
        raise ValueError('oversized D4 profile')
    profile = json.loads(raw)
    if set(profile) != {'binding', 'portal_uid', 'portal_gid', 'cases'}:
        raise ValueError('invalid D4 profile fields')
    validate_binding(profile['binding'])
    if set(profile['cases']) != set(SCENARIOS):
        raise ValueError('expected exactly two prepared D4 cases')
    for field in ('portal_uid', 'portal_gid'):
        if type(profile[field]) is not int or profile[field] <= 0:
            raise ValueError('dedicated non-root portal identity required')
    cases = tuple(profile['cases'].values())
    for field in ('nonce', 'api_container_id', 'task_id', 'db_container_id'):
        if cases[0][field] == cases[1][field]:
            raise ValueError('D4 scenarios require independently prepared runtime identities')
    return profile


def current_binding(binding, now):
    if not binding['issued_at'] <= now < binding['expires_at']:
        return False
    root_private(QUEUE_ROOT, directory=True)
    path = QUEUE_ROOT / 'queue.sqlite3'
    root_private(path)
    with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
        slot = connection.execute(
            'SELECT lease, release, phase, expires_at FROM slot WHERE singleton = 1'
        ).fetchone()
    if not slot or slot[0] != binding['lease'] or slot[2] != 'testing' or now >= slot[3]:
        return False
    identity = json.loads(slot[1])
    return all(identity[key] == binding[key] for key in ('pr', 'head', 'merge', 'plan'))


@contextlib.contextmanager
def hold_test_slot():
    # Reuse the host lock so preview cleanup cannot retire a running case.
    with QUEUE_LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def persist_receipt(directory, receipt):
    root_private(directory, directory=True)
    path = directory / (receipt['scenario'] + '.json')
    flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL
    with os.fdopen(os.open(path, flags, 0o600), 'w') as stream:
        json.dump(receipt, stream, separators=(',', ':'))
        stream.flush()
        os.fsync(stream.fileno())


class Executor:
    def __init__(self, profile, execute, *, is_current=current_binding, guard=hold_test_slot, clock=time.time, record=None):
        self.profile = profile
        self.execute = execute
        self.is_current = is_current
        self.guard = guard
        self.clock = clock
        self.record = record

    def handle(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'binding', 'scenario', 'operation'}:
            raise ValueError('invalid D4 executor request')
        if payload['binding'] != self.profile['binding']:
            raise ValueError('request does not match the prepared test allocation')
        scenario, operation = payload['scenario'], payload['operation']
        if scenario not in SCENARIOS or not isinstance(operation, str) or not re.fullmatch('[a-f0-9]{32}', operation):
            raise ValueError('invalid D4 browser action')
        binding = self.profile['binding']
        with self.guard():
            if not self.is_current(binding, int(self.clock())):
                raise ValueError('D4 acceptance allocation is no longer current')
            observation = self.execute(scenario, self.profile['cases'][scenario], binding)
            response = dict(payload, **observation)
            outcome = validated_receipt(response, payload)
            if not self.is_current(binding, int(self.clock())):
                raise ValueError('D4 acceptance allocation expired during execution')
            if self.record and outcome == '通过':
                self.record(response)
            return response


class Request(BaseRequestHandler):
    def handle(self):
        self.request.settimeout(55)
        try:
            with self.request.makefile('rb') as stream:
                payload = stream.read(MAX_MESSAGE + 1)
            if not payload or len(payload) > MAX_MESSAGE:
                raise ValueError('invalid D4 request size')
            reply = self.server.executor.handle(json.loads(payload))
            encoded = json.dumps(reply, separators=(',', ':')).encode()
        except Exception:
            # Native diagnostics and install credentials are never returned.
            encoded = b'{}'
        try:
            self.request.sendall(encoded)
        except OSError:
            pass


class Broker(UnixStreamServer):
    def verify_request(self, request, client_address):
        credentials = request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
        _, uid, gid = struct.unpack('3i', credentials)
        return (uid, gid) == (self.portal_uid, self.portal_gid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    args = parser.parse_args()
    if os.getuid() != 0 or not hasattr(socket, 'SO_PEERCRED'):
        raise SystemExit('root Linux broker required')
    from cases import execute_case
    profile = load_profile(args.profile)
    evidence = args.profile.parent / 'receipts'
    evidence.mkdir(mode=0o700, exist_ok=True)
    root_private(evidence, directory=True)
    info = SOCKET_DIR.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o750:
        raise SystemExit('protected broker socket directory required')
    os.umask(0o117)
    with Broker(str(SOCKET_PATH), Request) as server:
        server.executor = Executor(
            profile, execute_case, record=lambda receipt: persist_receipt(evidence, receipt)
        )
        server.portal_uid, server.portal_gid = profile['portal_uid'], profile['portal_gid']
        os.chown(SOCKET_PATH, 0, server.portal_gid)
        os.chmod(SOCKET_PATH, 0o660)
        try:
            server.serve_forever()
        finally:
            SOCKET_PATH.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
