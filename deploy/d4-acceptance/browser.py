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
MAX_MESSAGE = 8192


def read_config(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError('private acceptance configuration required')
        raw = stream.read(MAX_MESSAGE + 1)
    if len(raw) > MAX_MESSAGE:
        raise ValueError('invalid acceptance configuration length')
    return json.loads(raw)


def validate_config(config):
    origin = urlsplit(config['origin'])
    if (origin.scheme != 'https' or not origin.hostname or origin.username is not None
            or origin.path or origin.query or origin.fragment):
        raise ValueError('an exact HTTPS acceptance origin is required')
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', config['username']):
        raise ValueError('invalid dedicated acceptance account')
    sizes = {'salt': 32, 'password_digest': 128}
    if any(not re.fullmatch(f'[0-9a-f]{{{size}}}', config[name]) for name, size in sizes.items()):
        raise ValueError('invalid dedicated acceptance password verifier')
    if not Path(config['executor_socket']).is_absolute() or not 1 <= len(config['report_label']) <= 120:
        raise ValueError('invalid executor or report configuration')

    binding = config['binding']
    if set(binding) != {'pr', 'head', 'merge', 'plan', 'lease', 'report_id', 'issued_at', 'expires_at'}:
        raise ValueError('invalid acceptance binding schema')
    if type(binding['pr']) is not int or not 0 < binding['pr'] < 10**9:
        raise ValueError('invalid PR number')
    for key, size in [('head', 40), ('merge', 40), ('plan', 64), ('lease', 32)]:
        if not re.fullmatch(f'[0-9a-f]{{{size}}}', binding[key]):
            raise ValueError('invalid acceptance binding')
    if (not canonical_uuid(binding['report_id'])
            or type(binding['issued_at']) is not int or type(binding['expires_at']) is not int
            or not 0 < binding['expires_at'] - binding['issued_at'] <= 3600
            or not binding['issued_at'] <= time.time() < binding['expires_at']):
        raise ValueError('invalid or expired acceptance window')



def authenticated(header, config):
    if not header or not header.startswith('Basic ') or len(header) > 512:
        return False
    try:
        username, password = base64.b64decode(header[6:], validate=True).split(b':', 1)
        if len(password) > 128:
            return False
        salt = bytes.fromhex(config['salt'])
        expected = bytes.fromhex(config['password_digest'])
        actual = hashlib.scrypt(password, salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(username, config['username'].encode()) and hmac.compare_digest(actual, expected)
    except (ValueError, binascii.Error):
        return False


def executor_call(path, payload):
    target = Path(path)
    parent, socket_info = target.parent.lstat(), target.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022
            or not stat.S_ISSOCK(socket_info.st_mode) or socket_info.st_uid != 0
            or socket_info.st_mode & 0o007):
        raise ValueError('executor socket must be owned by the trusted runtime')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(50)
        channel.connect(path)
        channel.sendall(json.dumps(payload).encode())
        channel.shutdown(socket.SHUT_WR)
        with channel.makefile('rb') as reply:
            response = reply.read(MAX_MESSAGE + 1)
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


def handler(config, invoke):
    binding = config['binding']

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
                return False
            if not authenticated(self.headers.get('Authorization'), config):
                self.show(401, '<p>需要本轮验收账号</p>', challenge=True)
                return False
            return True

        def do_GET(self):
            if not self.authorize():
                return
            if self.path != '/':
                self.show(404, '<p>页面不存在</p>')
                return
            forms = ''.join(
                f'<form method="post" action="/scenario/{key}"><button>{name}</button></form>'
                for key, name in SCENARIOS.items()
            )
            self.show(200, f'<h1>PR #{binding["pr"]} 的 D4 验收</h1>'
                      f'<p>部署版本 <code>{html.escape(binding["merge"])}</code></p>'
                      f'<p>合成报告 {html.escape(config["report_label"])}</p>{forms}')

        def do_POST(self):
            if not self.authorize():
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
            request = dict(binding=binding, scenario=scenario, operation=uuid4().hex)
            try:
                receipt = invoke(request)
                result = validated_receipt(receipt, request)
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
