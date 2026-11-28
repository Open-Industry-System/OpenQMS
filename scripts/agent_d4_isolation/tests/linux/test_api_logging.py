"""Full-chain logging test for the isolated API's logging policy.

This runs a real uvicorn process on IPv4 loopback with the same install order,
`log_config=None` and the pinned h11 parser, then sends requests whose path,
query, header and raw HTTP frame all carry a sentinel secret, plus a request that
makes the application raise with the secret in the body.

Scope, stated plainly:
- it exercises the chain that matters for leakage — parser, uvicorn.access,
  uvicorn.error, ASGI exception handling and the process's own
  stdout/stderr — with the real policy installed before any of it;
- it uses a minimal Starlette app, **not** `app.main`. The real application
  cannot start in this environment because its lifespan connects to PostgreSQL,
  so the full production chain is NOT_RUN here and must be covered where a
  dedicated database is authorised.

The sentinel is only ever sent to 127.0.0.1.
"""
import http.client
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

SECRET = 'sk-live-SENTINEL-0123456789abcdef'
ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / 'backend'

APP = r'''
import os, sys
sys.path.insert(0, os.getcwd())
from app.core import agent_isolation_logging
agent_isolation_logging.install()
import uvicorn
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

async def ok(request):
    return PlainTextResponse("ok")

async def boom(request):
    raise RuntimeError("boom " + (await request.body()).decode())

app = Starlette(routes=[Route("/claim", ok),
                          Route("/boom", boom, methods=["POST"])])
uvicorn.run(app, host="127.0.0.1", port=int(os.environ["PORT"]),
            log_config=None, http="h11", access_log=True)
'''


def _free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def _wait_until_listening(port, timeout=25.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def test_a_planted_secret_never_reaches_the_process_output():
    port = _free_port()
    env = {'PATH': '/usr/bin:/bin', 'PORT': str(port)}
    process = subprocess.Popen(
        [sys.executable, '-I', '-B', '-c', APP],
        cwd=str(BACKEND), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        assert _wait_until_listening(port), 'the logging-policy app never started'

        # 1. unknown path, secret in the query string and in a header
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        connection.request('GET', '/nope?token=' + SECRET, headers={'X-Secret': SECRET})
        connection.getresponse().read()
        connection.close()

        # 2. an application exception whose message contains the secret
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        connection.request('POST', '/boom', body=('body ' + SECRET).encode())
        assert connection.getresponse().status == 500
        connection.close()

        # 3. a malformed HTTP frame carrying the secret in the request line
        with socket.create_connection(('127.0.0.1', port), timeout=5) as raw:
            raw.sendall(('GARBAGE ' + SECRET + ' HTTP/1.1\r\nHost: x\r\n\r\n').encode())
            raw.recv(1024)
    finally:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()

    output = output or ''
    assert SECRET not in output, 'the sentinel reached the process output'
    assert 'Traceback' not in output, 'a traceback reached the process output'
    # Silence would be a false pass: the chain must actually have logged.
    assert 'level=' in output, output


def test_the_process_refuses_to_bind_anything_but_loopback():
    """The bind check runs before the app is imported, so no database is needed."""
    entrypoint = BACKEND / 'scripts' / 'agent_d4_isolated_api.py'
    if not entrypoint.is_file():
        pytest.skip('isolated API entrypoint missing')
    env = {
        'PATH': '/usr/bin:/bin',
        'SECRET_KEY': 'test-secret-key-for-isolation-only',
        'OPENQMS_ISOLATION_API_HOST': '0.0.0.0',
        'OPENQMS_ISOLATION_API_PORT': str(_free_port()),
    }
    completed = subprocess.run(
        [sys.executable, '-I', '-B', str(entrypoint)],
        cwd=str(BACKEND), env=env, capture_output=True, text=True, timeout=60)
    assert completed.returncode != 0
    assert 'refuses to bind' in (completed.stdout + completed.stderr)
