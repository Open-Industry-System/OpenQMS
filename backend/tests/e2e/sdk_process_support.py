"""Fixture-only isolated wheel client; never a trusted production worker."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio

from tests.e2e.agent_local_trial_harness import MARKER


@pytest.fixture(scope='session')
def sdk_runtime():
    wheel = Path(os.environ.get('OPENQMS_SDK_WHEEL', ''))
    assert os.environ.get('OPENQMS_SDK_WHEEL') and wheel.is_absolute() and wheel.is_file(), 'explicit SDK wheel required'
    repository = Path(__file__).resolve().parents[3]
    with TemporaryDirectory(prefix='openqms-sdk-process-') as directory:
        root = Path(directory).resolve()
        # This fixture owns this exact temporary path and its eventual cleanup.
        assert repository not in root.parents and root != repository
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(root), 'TMPDIR': str(root), 'LANG': 'C.UTF-8'}
        # Even ensurepip's helper must not inherit the parent's DB/admin env.
        created = subprocess.run([sys.executable, '-I', '-B', '-c',
            'import sys, venv; venv.EnvBuilder(with_pip=True, system_site_packages=False).create(sys.argv[1])',
            str(root / 'venv')], cwd=root, env=env, capture_output=True, timeout=60)
        assert created.returncode == 0, 'offline standard-library venv creation failed'
        python = root / 'venv' / 'bin' / 'python'
        assert 'include-system-site-packages = false' in (root / 'venv/pyvenv.cfg').read_text()
        installed = subprocess.run([str(python), '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check',
            'install', '--no-index', '--no-deps', str(wheel)], cwd=root, env=env,
            capture_output=True, timeout=60)
        assert installed.returncode == 0, 'offline wheel installation failed'
        source = repository / 'sdk/python/tests/support/protocol_probe.py'
        probe = root / 'protocol_probe.py'
        probe.write_bytes(source.read_bytes())
        yield python, probe, root, env


class SDKProcess:
    def __init__(self, process, owned):
        self.process, self.owned = process, owned

    async def command(self, action, **parameters):
        self.process.stdin.write(json.dumps({'action': action, **parameters}).encode() + b'\n')
        await self.process.stdin.drain()
        line = await asyncio.wait_for(self.process.stdout.readline(), 15)
        assert line and len(line) < 8192, 'missing/bounded protocol response'
        for secret in (self.owned.secret, self.owned.admin_token, self.owned.user_token,
                MARKER, *self.owned.witness.tokens):
            assert secret.encode() not in line, 'unsafe child output'
        result = json.loads(line)
        assert 'fatal' not in result, result
        return result


@pytest_asyncio.fixture
async def sdk_child(local_trial_server, sdk_runtime):
    owned = local_trial_server
    python, probe, root, env = sdk_runtime
    process = await asyncio.create_subprocess_exec(str(python), '-I', '-B', str(probe), cwd=root, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        limit=8192)
    child = SDKProcess(process, owned)
    try:
        process.stdin.write(json.dumps({'origin': owned.base_url, 'tenant': owned.slug,
            'installation_id': str(owned.installation_id), 'secret': owned.secret}).encode() + b'\n')
        await process.stdin.drain()
        yield child
    finally:
        if process.returncode is None:
            process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        stderr = await process.stderr.read()
        assert stderr == b'', 'child must not emit diagnostic payloads'
        assert process.returncode == 0, 'child did not exit cleanly'
        assert await process.stdout.read() == b'', 'unexpected child output'


async def control(owned, task_id, run_id, action, checkpoint_id=None):
    from uuid import UUID, uuid4
    from app.models.agent_task import AgentRun
    async with owned.session() as db:
        run = await db.get(AgentRun, UUID(run_id))
        epoch = run.lease_epoch
    body = {'action': action, 'run_id': run_id, 'expected_epoch': epoch, 'idempotency_key': uuid4().hex}
    if checkpoint_id:
        body['checkpoint_id'] = checkpoint_id
    response = await owned.client.post(f'/api/agent/tasks/{task_id}/control', json=body)
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def finish_fault(local_trial_server, monkeypatch):
    """Wrap only this server's response boundary, after Witness/handler commit.

    No request header, plugin-controlled setting, handler or SDK is patched.
    The original Witness still records the genuine successful response.
    """
    witness = local_trial_server.witness
    original = type(witness).__call__
    fault = SimpleNamespace(mode=None, calls=0)

    class ResponseBoundary(type(witness)):
        async def __call__(self, scope, receive, send):
            if scope['type'] != 'http' or scope['path'] != '/api/agent/runtime/finish' or fault.mode is None:
                return await original(self, scope, receive, send)
            messages = []

            async def capture(message):
                messages.append(message)

            await original(self, scope, receive, capture)
            assert messages[0]['status'] == 200, 'fault must follow successful real handler'
            fault.calls += 1
            raw = b''.join(message.get('body', b'') for message in messages[1:])
            status = 200
            if fault.mode == 'oversize':
                raw = b' ' * (64 * 1024 + 1)
            elif fault.mode == 'bad_json':
                raw = b'{'
            elif fault.mode in ('wrong_run', 'wrong_task'):
                body = json.loads(raw)
                body['run_id' if fault.mode == 'wrong_run' else 'task_id'] = str(uuid4())
                raw = json.dumps(body).encode()
            elif fault.mode in ('wrong_status', 'schema'):
                body = json.loads(raw)
                if fault.mode == 'wrong_status':
                    body['task_status'] = body['run_status'] = 'failed'
                else:
                    del body['lease_epoch']
                raw = json.dumps(body).encode()
            elif fault.mode == 'server_error':
                status, raw = 503, b'{}'
            elif fault.mode == 'timeout':
                await asyncio.sleep(5.2)  # SDK's single total operation deadline is 5s.
            elif fault.mode != 'disconnect':
                raise AssertionError('unknown parent fault')
            await send({'type': 'http.response.start', 'status': status, 'headers': [
                (b'content-type', b'application/json'), (b'content-length', str(len(raw)).encode())]})
            if fault.mode == 'disconnect':
                # The socket closes with an incomplete declared body, not a 5xx
                # synthesized before the finish handler executes.
                await send({'type': 'http.response.body', 'body': raw[:1], 'more_body': True})
                raise ConnectionResetError('fixture-only post-commit disconnect')
            await send({'type': 'http.response.body', 'body': raw})

    monkeypatch.setattr(witness, '__class__', ResponseBoundary)
    return fault


@pytest_asyncio.fixture
async def foreign_tenant(owned_local_trial):
    """One normal provisioned, separately owned tenant; never copy credentials."""
    from sqlalchemy import text
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator

    owned = owned_local_trial
    slug = 'sdkforeign-' + uuid4().hex[:12]
    tenant = await tenant_migrator.provision_new(TenantCreateRequest(name='SDK foreign tenant',
        slug=slug, admin_email='foreign@example.test', admin_password='fixture-only-foreign-password'))
    try:
        yield slug
    finally:
        async with owned.engine.begin() as connection:
            row = (await connection.execute(text('SELECT id,schema_name FROM public.tenants WHERE slug=:slug'),
                {'slug': slug})).one()
            assert row.id == tenant.id and row.schema_name == tenant.schema_name
            await connection.execute(text(f'DROP SCHEMA "{row.schema_name}" CASCADE'))
            await connection.execute(text('DELETE FROM public.tenant_migrations WHERE tenant_id=:id'), {'id': row.id})
            await connection.execute(text('DELETE FROM public.tenants WHERE id=:id'), {'id': row.id})
