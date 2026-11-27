#!/usr/bin/env python3
"""Browser entry point for a dedicated D4 acceptance lease.

Run behind HTTPS on a distinct trusted origin. The executor socket belongs to
the audited Linux service. This process never runs commands supplied by a page
or reads the receiver's installation credential.
"""
import argparse
import base64
import binascii
import hashlib
import hmac
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import time
from urllib.parse import urlsplit
from uuid import UUID, uuid4


SCENARIOS = {'d4-deliver': '正常正文交付', 'd4-revoke': '撤权后交付'}
SHARED_ACCOUNT_ROLES = {'engineer': 'field_qe', 'manager': 'manager'}
MAX_MESSAGE = 8192


def read_config(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) not in {0o400, 0o600} or info.st_nlink != 1):
            raise ValueError('private acceptance configuration required')
        raw = stream.read(MAX_MESSAGE + 1)
    if len(raw) > MAX_MESSAGE:
        raise ValueError('invalid acceptance configuration length')
    return json.loads(raw)


def valid_password_verifier(record):
    return all(
        isinstance(record.get(name), str) and re.fullmatch(f'[0-9a-f]{{{size}}}', record[name])
        for name, size in (('salt', 32), ('password_digest', 128))
    )


def validate_accounts(config):
    legacy_fields = {'username', 'salt', 'password_digest'}
    if not {'accounts', 'scenario_roles'} & config.keys():
        username = config.get('username')
        if (not isinstance(username, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', username)
                or not valid_password_verifier(config)):
            raise ValueError('invalid dedicated acceptance credential')
        return

    accounts, roles = config.get('accounts'), config.get('scenario_roles')
    if (legacy_fields & config.keys() or not isinstance(accounts, dict) or not accounts
            or not accounts.keys() <= SHARED_ACCOUNT_ROLES.keys()
            or not isinstance(roles, dict) or not roles or not roles.keys() <= SCENARIOS.keys()
            or any(not isinstance(account, dict) or set(account) != {'role', 'salt', 'password_digest'}
                   or account['role'] != SHARED_ACCOUNT_ROLES[username] or not valid_password_verifier(account)
                   for username, account in accounts.items())):
        raise ValueError('invalid shared acceptance accounts')
    issued_roles = {account['role'] for account in accounts.values()}
    if any(not isinstance(role, str) or role not in issued_roles for role in roles.values()):
        raise ValueError('invalid shared acceptance scenario roles')


def validate_config(config):
    origin = urlsplit(config['origin'])
    if (origin.scheme != 'https' or not origin.hostname or origin.username is not None
            or origin.path or origin.query or origin.fragment):
        raise ValueError('an exact HTTPS acceptance origin is required')
    validate_accounts(config)
    if not Path(config['executor_socket']).is_absolute() or not 1 <= len(config['report_label']) <= 120:
        raise ValueError('invalid executor or report configuration')

    tasks = config.get('tasks')
    scenarios = config.get('scenario_roles', SCENARIOS)
    if tasks is not None and (not isinstance(tasks, dict) or tasks.keys() != scenarios.keys()
                              or not all(canonical_uuid(task) for task in tasks.values())
                              or len(set(tasks.values())) != len(tasks)):
        raise ValueError('invalid dedicated acceptance tasks')
    validate_binding(config['binding'])


def validate_binding(binding, *, now=None):
    if set(binding) != {'pr', 'head', 'merge', 'plan', 'lease', 'report_id', 'issued_at', 'expires_at'}:
        raise ValueError('invalid acceptance binding schema')
    if type(binding['pr']) is not int or not 0 < binding['pr'] < 10**9:
        raise ValueError('invalid PR number')
    for key, size in [('head', 40), ('merge', 40), ('plan', 64), ('lease', 32)]:
        if not re.fullmatch(f'[0-9a-f]{{{size}}}', binding[key]):
            raise ValueError('invalid acceptance binding')
    now = time.time() if now is None else now
    if (not canonical_uuid(binding['report_id'])
            or type(binding['issued_at']) is not int or type(binding['expires_at']) is not int
            or not 0 < binding['expires_at'] - binding['issued_at'] <= 3600
            or not binding['issued_at'] <= now < binding['expires_at']):
        raise ValueError('invalid or expired acceptance window')



def authenticated_role(header, config):
    if not header or not header.startswith('Basic ') or len(header) > 512:
        return None
    try:
        username, password = base64.b64decode(header[6:], validate=True).split(b':', 1)
        if len(password) > 128:
            return None
        if 'accounts' in config:
            account = config['accounts'].get(username.decode('ascii'))
            if account is None:
                return None
            role = account['role']
        else:
            if not hmac.compare_digest(username, config['username'].encode()):
                return None
            account, role = config, 'legacy'
        salt = bytes.fromhex(account['salt'])
        expected = bytes.fromhex(account['password_digest'])
        actual = hashlib.scrypt(password, salt=salt, n=2**14, r=8, p=1)
        return role if hmac.compare_digest(actual, expected) else None
    except (ValueError, binascii.Error):
        return None


def trusted_executor_socket(path):
    target = Path(path)
    parent, socket_info = target.parent.lstat(), target.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022
            or not stat.S_ISSOCK(socket_info.st_mode) or socket_info.st_uid != 0
            or socket_info.st_mode & 0o007):
        raise ValueError('executor socket must be owned by the trusted runtime')


def executor_call(path, payload, *, deadline=None):
    trusted_executor_socket(path)
    deadline = min(deadline, time.monotonic() + 50) if deadline is not None else time.monotonic() + 50

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError('trusted executor deadline elapsed')
        return seconds

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(remaining())
        channel.connect(path)
        channel.settimeout(remaining())
        channel.sendall(json.dumps(payload).encode())
        channel.shutdown(socket.SHUT_WR)
        response = bytearray()
        while len(response) <= MAX_MESSAGE:
            channel.settimeout(remaining())
            part = channel.recv(MAX_MESSAGE + 1 - len(response))
            if not part:
                break
            response.extend(part)
    if len(response) > MAX_MESSAGE:
        raise ValueError('invalid executor response length')
    return json.loads(response)


def canonical_uuid(value):
    return isinstance(value, str) and str(UUID(value)) == value


def validated_receipt(result, request):
    keys = {'binding', 'scenario', 'operation', 'task_id', 'run_id', 'delivery_before',
            'delivery_after', 'denial'}
    if not isinstance(result, dict) or set(result) != keys:
        raise ValueError('unexpected executor response fields')
    if any(result[key] != request[key] for key in ('binding', 'scenario', 'operation')):
        raise ValueError('executor receipt mismatched')
    if not all(canonical_uuid(result[key]) for key in ('task_id', 'run_id')):
        raise ValueError('invalid receipt identity')
    before, after = result['delivery_before'], result['delivery_after']
    if type(before) is not int or type(after) is not int or min(before, after) < 0:
        raise ValueError('invalid delivery counters')
    if request['scenario'] == 'd4-deliver':
        passed = after == before + 1 and result['denial'] is None
    else:
        passed = after == before and result['denial'] == 'source_revoked'
    return '通过' if passed else '失败'


def binding_fingerprint(binding):
    payload = json.dumps(binding, separators=(',', ':'), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def handler(config, invoke):
    binding = config['binding']
    tasks = config.get('tasks', {})
    scenario_roles = config.get('scenario_roles')

    def can_run(role, scenario):
        return scenario_roles is None or scenario_roles.get(scenario) == role

    class Browser(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def log_error(self, *_):
            pass

        def show(self, status, fragment, *, challenge=False):
            text = ('<!doctype html><html lang="zh"><meta charset="utf-8">'
                    '<title>D4 专用验收</title>' + fragment + '</html>').encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(text)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'none'; form-action 'self'; frame-ancestors 'none'")
            if challenge:
                self.send_header('WWW-Authenticate', 'Basic realm="D4 acceptance", charset="UTF-8"')
            self.end_headers()
            self.wfile.write(text)

        def authorize(self):
            if time.time() >= binding['expires_at']:
                self.show(410, '<p>本轮验收已到期</p>')
                return None
            role = authenticated_role(self.headers.get('Authorization'), config)
            if role is None:
                prompt = '请使用本轮共享测试账号登录' if scenario_roles is not None else '需要本轮验收账号'
                self.show(401, f'<p>{prompt}</p>', challenge=True)
                return None
            if scenario_roles is not None and role not in scenario_roles.values():
                self.show(403, '<p>该账号没有本轮 D4 验收权限</p>')
                return None
            return role

        def do_GET(self):
            if self.path == '/healthz':
                # An unauthenticated probe gets an opaque binding hash only.
                # Browser scenario operations still require the issued role.
                if time.time() >= binding['expires_at']:
                    self.show(410, '<p>本轮验收已到期</p>')
                    return
                try:
                    trusted_executor_socket(config['executor_socket'])
                except (OSError, ValueError):
                    self.show(503, '<p>专用执行器尚未就绪</p>')
                    return
                self.send_response(200)
                self.send_header('Content-Length', '0')
                self.send_header('X-OpenQMS-Test-PR', str(binding['pr']))
                self.send_header('X-OpenQMS-Test-Version', binding['merge'])
                self.send_header('X-OpenQMS-Test-Lease', binding['lease'])
                self.send_header('X-OpenQMS-D4-Binding', binding_fingerprint(binding))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                return
            role = self.authorize()
            if role is None:
                return
            if self.path != '/':
                self.show(404, '<p>页面不存在</p>')
                return
            forms = ''.join(
                f'<form method="post" action="/scenario/{key}"><button>{name}</button>'
                + (f' <span>任务 <code>{tasks[key]}</code></span>' if key in tasks else '')
                + '</form>'
                for key, name in SCENARIOS.items() if can_run(role, key)
            )
            self.show(200, f'<h1>PR #{binding["pr"]} 的 D4 验收</h1>'
                      f'<p>部署版本 <code>{html.escape(binding["merge"])}</code></p>'
                      f'<p>合成报告 {html.escape(config["report_label"])} <code>{binding["report_id"]}</code></p>{forms}')

        def do_POST(self):
            role = self.authorize()
            if role is None:
                return
            if self.headers.get('Origin') != config['origin']:
                self.show(403, '<p>请求来源不允许</p>')
                return
            scenario = self.path.removeprefix('/scenario/')
            if (not self.path.startswith('/scenario/') or scenario not in SCENARIOS
                    or self.headers.get('Content-Length', '0') != '0'
                    or self.headers.get('Transfer-Encoding')):
                self.show(400, '<p>仅可选择已登记的场景</p>')
                return
            if not can_run(role, scenario):
                self.show(403, '<p>该账号没有此项验收权限</p>')
                return
            request = dict(binding=binding, scenario=scenario, operation=uuid4().hex)
            try:
                receipt = invoke(request)
                result = validated_receipt(receipt, request)
                if scenario in tasks and receipt['task_id'] != tasks[scenario]:
                    raise ValueError('receipt task does not match the current report task')
            except (OSError, ValueError, TypeError, KeyError):
                self.show(503, '<h1>受阻</h1><p>专用执行器未返回本次操作的有效回执。</p>')
                return
            if time.time() >= binding['expires_at']:
                self.show(410, '<p>本轮验收已到期</p>')
                return
            self.show(200, f'<h1>{SCENARIOS[scenario]}：{result}</h1>'
                      f'<p>任务 <code>{receipt["task_id"]}</code></p>'
                      f'<p>运行 <code>{receipt["run_id"]}</code></p>'
                      f'<p>交付记录 {receipt["delivery_before"]} → {receipt["delivery_after"]}</p>'
                      '<a href="/">返回合成报告</a>')

    return Browser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--cert', required=True)
    parser.add_argument('--key', required=True)
    args = parser.parse_args()
    config = read_config(args.config)
    validate_config(config)
    server = HTTPServer(('127.0.0.1', args.port), handler(
        config, lambda request: executor_call(config['executor_socket'], request)
    ))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.cert, args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    with server:
        server.serve_forever()


if __name__ == '__main__':
    main()
