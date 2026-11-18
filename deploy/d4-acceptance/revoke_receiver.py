#!/usr/bin/env python3
"""Run the fixed synthetic D4 revocation case using one private stdin pipe."""
import json
import os
from pathlib import Path
import re
import runpy
import select
import sys
import time
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
MAX_INPUT = 8192
SECONDS = 35


def read_line(fd, deadline, limit):
    data = bytearray()
    while len(data) < limit:
        if not select.select([fd], [], [], deadline.remaining())[0]:
            raise TimeoutError('D4 control frame timed out')
        part = os.read(fd, limit - len(data))
        if not part:
            break
        data.extend(part)
        if b'\n' in part:
            if data.count(b'\n') == 1 and data[-1] == 10:
                return bytes(data)
            break
    raise ValueError('invalid D4 control frame')


def send(value):
    print(json.dumps(value, separators=(',', ':')), flush=True)


def execute(worker, wire, fd, end):
    deadline = wire['Deadline'](end)
    payload = worker.parse_json(read_line(fd, deadline, MAX_INPUT))
    worker.require(set(payload) == {'receiver', 'admin_username', 'admin_password',
                                    'task_id', 'run_id', 'grant_id'})
    config = worker.Config.from_mapping(payload['receiver'])
    host, port, tls = worker.origin_parts(config.origin)
    username, password = payload['admin_username'], payload['admin_password']
    identities = {key: worker.uuid(payload[key]) for key in ('task_id', 'run_id', 'grant_id')}
    worker.require(host == '127.0.0.1' and not tls and port >= 1024
                   and re.fullmatch(r'd4-[0-9a-f]{32}', config.tenant_slug)
                   and username == 'd4-admin@example.test'
                   and isinstance(password, str) and re.fullmatch(r'[a-zA-Z0-9_-]{20,128}', password))
    login = wire['request'](
        worker, config, 'POST', '/api/auth/login', None,
        {'username': username, 'password': password}, deadline, status=200, limit=8192,
    )
    token = login['access_token']
    worker.require(isinstance(token, str) and re.fullmatch(r'[a-zA-Z0-9._-]{20,4096}', token))
    del payload, password, login

    def barrier(identity, remaining):
        send(dict(identity, stage='authorized'))
        worker.require(read_line(fd, remaining, 7) == b'revoke\n')

    return wire['observe_revocation'](
        worker, config, admin_token=token, deadline=end, before_revoke=barrier, **identities,
    )


def main():
    end = time.monotonic() + SECONDS
    try:
        worker = SimpleNamespace(**runpy.run_path(str(ROOT / 'readonly_d4_text_receiver.py')))
        wire = runpy.run_path(str(ROOT / 'revoke_wire.py'))
        send(execute(worker, wire, sys.stdin.fileno(), end))
    except Exception:
        print('D4_REVOCATION_BLOCKED', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
