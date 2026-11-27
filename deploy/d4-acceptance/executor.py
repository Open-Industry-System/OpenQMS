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
def socket_path_for(lease):
    if not isinstance(lease, str) or not re.fullmatch('[a-f0-9]{32}', lease):
        raise ValueError('invalid D4 socket lease')
    return SOCKET_DIR / ('executor-' + lease + '.sock')


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
    cases_by_scenario = profile['cases']
    if not isinstance(cases_by_scenario, dict) or not cases_by_scenario or not cases_by_scenario.keys() <= SCENARIOS.keys():
        raise ValueError('expected prepared D4 cases for the requested scenarios')
    for field in ('portal_uid', 'portal_gid'):
        if type(profile[field]) is not int or profile[field] <= 0:
            raise ValueError('dedicated non-root portal identity required')
    cases = cases_by_scenario.values()
    for field in ('api_container_id', 'task_id', 'db_container_id'):
        if len({case[field] for case in cases}) != len(cases_by_scenario):
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
            'SELECT lease, release, phase FROM slot WHERE singleton = 1'
        ).fetchone()
    if not slot or slot[0] != binding['lease'] or slot[2] != 'testing':
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
        if (not isinstance(scenario, str) or scenario not in self.profile['cases']
                or not isinstance(operation, str) or not re.fullmatch('[a-f0-9]{32}', operation)):
            raise ValueError('invalid D4 browser action')
        binding = self.profile['binding']
        with self.guard():
            if not self.is_current(binding, int(self.clock())):
                raise ValueError('D4 acceptance allocation is no longer current')
            observation = self.execute(scenario, self.profile['cases'][scenario], binding)
            response = dict(payload, **observation)
            outcome = validated_receipt(response, payload)
            completed_at = int(self.clock())
            if not self.is_current(binding, completed_at):
                raise ValueError('D4 acceptance allocation expired during execution')
            if self.record and outcome == '通过':
                self.record(dict(response, completed_at=completed_at))
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
    expected_profile = QUEUE_ROOT / 'd4' / profile['binding']['lease'] / 'profile.json'
    if args.profile != expected_profile:
        raise SystemExit('profile must use the protected shared-test lease path')
    evidence = args.profile.parent / 'receipts'
    evidence.mkdir(mode=0o700, exist_ok=True)
    root_private(evidence, directory=True)
    info = SOCKET_DIR.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o750:
        raise SystemExit('protected broker socket directory required')
    os.umask(0o117)
    socket_path = socket_path_for(profile['binding']['lease'])
    with Broker(str(socket_path), Request) as server:
        server.executor = Executor(
            profile, execute_case, record=lambda receipt: persist_receipt(evidence, receipt)
        )
        server.portal_uid, server.portal_gid = profile['portal_uid'], profile['portal_gid']
        os.chown(socket_path, 0, server.portal_gid)
        os.chmod(socket_path, 0o660)
        try:
            server.serve_forever()
        finally:
            socket_path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
