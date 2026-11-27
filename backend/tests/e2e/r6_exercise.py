"""Preserved, owner-bound C9 application/browser acceptance infrastructure."""
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
from uuid import uuid4
from urllib.parse import urlsplit

import httpx

from tests.ci.browser_runtime import browser_environment, resolve_browser

ROOT = Path(__file__).resolve().parents[3]


def write_private(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    path.chmod(0o600)


class Exercise:
    """Two normal app launches share one explicitly registered tenant/volume.

    No application dependency overrides, fake claims, seeded Root/P, model
    response substitutions, or direct phase mutations are used in this lane.
    """
    def __init__(self):
        from tests.capa.r6_support import registered_exercise_environment
        self.resource, self.directory, self.environment = registered_exercise_environment(os.environ)
        self.data = json.loads((self.directory / 'session.json').read_text())
        frozen_config = self.directory / 'config.json'
        previous = json.loads(frozen_config.read_text()).get('execution', {}) if frozen_config.exists() else {}
        self.frontend_port = previous.get('frontend_port')
        if self.frontend_port is None:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                self.frontend_port = probe.getsockname()[1]
        self.origin = None
        self.server = None
        self.clients = {}
        self.stack = AsyncExitStack()
        self.receipts = []

    async def __aenter__(self):
        from tests.ci.owned_resources import verify_owned_instance, verify_owned_database
        verify_owned_database(verify_owned_instance(self.environment))
        await self.stack.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self.stop()
        await self.stack.__aexit__(*exc)
        write_private(self.directory / ('process-receipt-' + uuid4().hex + '.json'), self.receipts)

    async def stop(self):
        for client in self.clients.values():
            await client.aclose()
        self.clients.clear()
        if self.server and self.server.returncode is None:
            self.server.terminate()
            try:
                await asyncio.wait_for(self.server.wait(), 15)
            except asyncio.TimeoutError:
                self.server.kill()
                await self.server.wait()
            self.receipts.append(dict(event='normal_app_stopped', pid=self.server.pid, exit=self.server.returncode))
        if getattr(self, 'log', None):
            self.log.close()

    async def start(self, *, live=False, profile='unconfigured'):
        await self.stop()
        if not self.origin:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                self.port = probe.getsockname()[1]
            self.origin = f'http://127.0.0.1:{self.port}'
        self.log = (self.directory / f'app-{profile}-{uuid4().hex}.log').open('wb')
        os.chmod(self.log.name, 0o600)
        args = [sys.executable, '-B', '-m', 'tests.e2e.r6_live_harness', str(self.directory), '--port', str(self.port)]
        if live:
            args.append('--live')
        self.server = await asyncio.create_subprocess_exec(*args, cwd=ROOT / 'backend',
            env=self.environment, stdout=self.log, stderr=self.log)
        async with httpx.AsyncClient(trust_env=False) as probe:
            for _ in range(400):
                if self.server.returncode is not None:
                    raise RuntimeError('owned normal application exited; inspect private log')
                try:
                    if (await probe.get(self.origin + '/api/health', timeout=1)).status_code < 500:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.05)
            else:
                raise RuntimeError('owned application failed to start')
        for actor in ['admin', *self.data['actors']]:
            username = self.data['admin'] if actor == 'admin' else self.data['actors'][actor]['username']
            client = httpx.AsyncClient(base_url=self.origin, trust_env=False, timeout=150,
                headers={'X-Tenant-ID': self.data['tenant']})
            login = await client.post('/api/auth/login', json=dict(username=username, password=self.data['password']))
            assert login.status_code == 200, f'normal {actor} login returned {login.status_code}'
            client.headers['Authorization'] = 'Bearer ' + login.json()['access_token']
            self.clients[actor] = client
        self.receipts.append(dict(event='normal_app_started', pid=self.server.pid, profile=profile,
            live=live, origin=self.origin))

    @property
    def root(self):
        return '/api/capa/' + self.data['report_id']

    async def request(self, method, path, body=None, *, actor='qe', expected=200):
        response = await self.clients[actor].request(method, path, json=body)
        assert response.status_code == expected, (method, path, response.status_code, response.text[:1200])
        value = response.json() if response.content else None
        self.receipts.append(dict(method=method, path=path, actor=actor, status=response.status_code,
            body_sha256=hashlib.sha256(response.content).hexdigest()))
        return value

    async def enroll(self, profile, version, *, live):
        """Normal admin registration followed by the real policy-file loader."""
        d4 = profile == 'model_d4_candidate_v1'
        caps = ['capa.d2.snapshot.v1', 'capa.d3.snapshot.v1'] + (
            ['capa.d4.candidate.propose.v1', 'capa.d4.fmea_input.masked.v1'] if d4 else
            ['capa.d4.root_cause_candidate.masked.v1', 'capa.d5.proposal.save.v1'])
        registered = await self.request('POST', '/api/admin/agent-plugins', dict(
            plugin_key='openqms.controlled-d5-model', plugin_version=version,
            manifest=dict(protocol_versions=['1'], required_capabilities=caps, optional_capabilities=[])),
            actor='admin', expected=201)
        installation = registered['plugin']['installation_id']
        expiry = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        from app.services.agent_runtime.r5_executor import ExecutorApproval
        approval = ExecutorApproval.approve(ROOT / 'backend/examples/d5_proposal_agent.py', sys.executable)
        policy = dict(schema_version=2, **{k: str(v) for k, v in vars(approval).items()},
            tenant_id=self.data['tenant_id'], tenant_generation=self.data['generation'],
            installation_id=installation, credential_epoch=0, plugin_version=version,
            platform_port=self.port, expires_at=expiry, profile=profile)
        write_private(self.directory / (profile + '.policy.json'), policy)
        write_private(self.directory / 'policy.json', policy)
        await self.start(live=live, profile=profile)
        scope = dict(target_report_id=self.data['report_id'], fmea_id=self.data['fmea_id'], cause_node_id='cause-a')
        for cap in caps:
            grant = dict(capability_id=cap, factory_ids=[self.data['factory_id']],
                object_ids=[self.data['report_id']], product_line_codes=[self.data['line']],
                enabled=True, expires_at=expiry)
            if cap in {'capa.d4.fmea_input.masked.v1', 'capa.d4.root_cause_candidate.masked.v1'}:
                grant['derived_source_scope'] = scope
            await self.request('POST', f'/api/admin/agent-plugins/{installation}/grants', grant, actor='admin', expected=201)
        await self.request('PATCH', f'/api/admin/agent-plugins/{installation}', dict(enabled=True), actor='admin')
        recipient = dict(kind='cloud', provider='openai', api_protocol='responses', model='gpt-6.1-terra',
            base_url='https://api.openai.com/v1', credential_ref='r5-env:R5_MODEL_CREDENTIAL_OPENAI_TRIAL')
        controlled = self.resource.get('r6_controlled_model')
        if controlled:
            if live or urlsplit(controlled['base_url']).hostname != '127.0.0.1':
                raise ValueError('controlled recipient is loopback-only and cannot be a live substitute')
            recipient.update(kind='local', api_protocol='chat_completions', model='synthetic',
                base_url=controlled['base_url'], credential_ref='r5-env:R5_MODEL_CREDENTIAL_SYNTHETIC')
        endpoint = urlsplit(recipient['base_url'])
        addresses = sorted({row[4][0] for row in socket.getaddrinfo(endpoint.hostname, endpoint.port or 443, type=socket.SOCK_STREAM)})
        model = await self.request('POST', '/api/agent/models', dict(name='C9 ' + profile,
            version=version, allowed_addresses=addresses, **recipient), actor='admin', expected=201)
        return dict(profile=profile, installation_id=installation, model_deployment_id=model['deployment_id'],
            derived_source_scope=scope, policy=policy)

    async def activate(self, enrollment, *, live):
        if self.origin is None:
            self.port = enrollment['policy']['platform_port']
            self.origin = f'http://127.0.0.1:{self.port}'
        write_private(self.directory / 'policy.json', enrollment['policy'])
        await self.start(live=live, profile=enrollment['profile'])

    async def task(self, enrollment, instruction):
        return await self.request('POST', '/api/agent/tasks', dict(report_id=self.data['report_id'],
            installation_id=enrollment['installation_id'], model_deployment_id=enrollment['model_deployment_id'],
            derived_source_scope=enrollment['derived_source_scope'], request_key=uuid4().hex,
            initial_text=instruction), expected=201)

    async def switch(self, enrollments):
        """Freeze the actual safety core and execute the real operator CLI."""
        from types import SimpleNamespace
        from uuid import UUID
        from app.core.tenant_transaction import TenantBinding
        from app.database import tenant_async_session
        from tests.capa.r6_switch_support import owned_cli, cli
        binding = TenantBinding(UUID(self.data['tenant_id']), self.data['schema'], self.data['generation'], 'business')
        case = SimpleNamespace(binding=binding,
            session=lambda: tenant_async_session(binding=binding),
            actor=lambda: SimpleNamespace(user_id=UUID(self.data['actors']['qe']['user_id'])))
        facts = dict(app_launcher='tests.e2e.r6_live_harness', app_port=self.port, frontend_port=self.frontend_port,
            generation='enabled', backend_only_credential_ref=('r5-env:R5_MODEL_CREDENTIAL_SYNTHETIC'
                if self.resource.get('r6_controlled_model') else 'r5-env:R5_MODEL_CREDENTIAL_OPENAI_TRIAL'),
            deployment_modes=dict(candidate=dict(R6_GENERATION_ENABLED=True),
                compatible=dict(R6_GENERATION_ENABLED=False)),
            enrollments=[dict(profile=e['profile'], installation_id=e['installation_id'],
                model_deployment_id=e['model_deployment_id'],
                policy_sha256=hashlib.sha256((self.directory / (e['profile'] + '.policy.json')).read_bytes()).hexdigest()) for e in enrollments],
            compatible_mode='same frozen safety core; generation disabled for Task10',
            launcher_sha256=hashlib.sha256(Path(__file__).with_name('r6_live_harness.py').read_bytes()).hexdigest())
        execution_paths = [
            'backend/tests/e2e/r6_live_harness.py', 'backend/tests/e2e/r6_exercise.py',
            'backend/tests/e2e/test_r6_live_chain.py', 'backend/tests/e2e/test_r6_entry_switch_browser.py',
            'backend/tests/e2e/test_r6_entry_switch_process.py', 'backend/tests/capa/r6_switch_support.py',
            'backend/tests/capa/r6_support.py',
            'frontend/playwright.agent.config.ts', 'frontend/e2e/specs/capa/r6-entry-switch.spec.ts',
        ]
        facts['execution_artifacts'] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in execution_paths}
        # Repository SDK sources are already in the complete runtime manifest.
        # Also bind the actually installed backend transport/client packages,
        # worker interpreter and browser/Node executables used by this lane.
        from importlib.metadata import distribution
        facts['backend_packages'] = {}
        for name in ['openai', 'httpx', 'httpcore']:
            package = distribution(name)
            files = {str(path): hashlib.sha256(package.locate_file(path).read_bytes()).hexdigest()
                for path in package.files if str(path).endswith(('.py', '.so')) and package.locate_file(path).is_file()}
            facts['backend_packages'][name] = dict(version=package.version, sources=files)
        node = Path(shutil.which('node')).resolve()
        browser = resolve_browser(ROOT / 'frontend', os.environ)
        facts['node'] = dict(path=str(node), sha256=hashlib.sha256(node.read_bytes()).hexdigest())
        facts['chromium'] = dict(path=str(browser), sha256=hashlib.sha256(browser.read_bytes()).hexdigest())
        facts['frontend_dependencies'] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in [
            'frontend/package-lock.json', 'frontend/node_modules/vite/bin/vite.js',
            'frontend/node_modules/@playwright/test/cli.js', 'frontend/node_modules/playwright/package.json',
        ]}
        facts['operator_adapters'] = {name: hashlib.sha256((self.directory / name).read_bytes()).hexdigest()
            for name in ['prepare.py', 'live.py', 'run.py']}
        facts['deployment_configurations'] = {mode: dict(path=str(self.directory / name),
            sha256=hashlib.sha256((self.directory / name).read_bytes()).hexdigest())
            for mode, name in [('candidate', 'environment.json'), ('compatible', 'environment.compat.json')]}
        self.switch_cli = await owned_cli(case, self.directory, runtime_pid=self.server.pid,
            deployment_config=facts, expiry_minutes=720)
        write_private(self.directory / 'switch-environment.json', self.switch_cli['env'])
        for command in ['status', 'close', 'renew', 'finish', 'status']:
            if command == 'renew':
                from datetime import datetime, timedelta, timezone
                from app.services.capa_switch_evidence import Document, digest
                original = json.loads(self.switch_cli['document'].read_text())
                initial_path = self.directory / 'exercise-initial.json'
                shutil.copyfile(self.switch_cli['document'], initial_path);initial_path.chmod(0o600)
                previous = Document.model_validate(original).model_dump(mode='json', by_alias=True)
                renewed = dict(original, expires_at=(datetime.now(timezone.utc)+timedelta(minutes=721)).isoformat(),
                    resume_of=dict(operation_ref=self.switch_cli['operation'],
                        previous_document_digest=digest(previous), draining_epoch=receipt['epoch']))
                write_private(self.switch_cli['document'], renewed)
                renewed_digest = self.switch_cli['authorize_document'](renewed)
                renewed_path = self.directory / 'exercise-renewed.json'
                shutil.copyfile(self.switch_cli['document'], renewed_path);renewed_path.chmod(0o600)
                write_private(self.directory / 'exercise-authority-chain.json', dict(
                    stage='renewal-authorized',
                    exercise_id=original['exercise_id'], operation_ref=self.switch_cli['operation'],
                    initial_document=dict(path=str(initial_path), canonical_digest=digest(previous),
                        sha256=hashlib.sha256(initial_path.read_bytes()).hexdigest()),
                    renewed_document=dict(path=str(renewed_path), canonical_digest=renewed_digest,
                        sha256=hashlib.sha256(renewed_path.read_bytes()).hexdigest()),
                    closed_epoch=receipt['epoch']))
            code, receipt = await cli(self.switch_cli, command)
            write_private(self.directory / ('switch-' + command + '-' + uuid4().hex + '.json'), receipt)
            assert code == 0, receipt
            self.receipts.append(dict(event='cli', command=command, receipt=receipt))
        from app.services.capa_entry_switch import status as entry_status
        async with case.session() as db:
            accepted = await entry_status(db)
        chain_path = self.directory / 'exercise-authority-chain.json'
        chain = json.loads(chain_path.read_text())
        assert accepted.state == 'switched' and accepted.epoch == chain['closed_epoch'] + 2
        assert accepted.operation_ref == chain['operation_ref']
        assert accepted.evidence['document_digest'] == chain['renewed_document']['canonical_digest']
        chain.update(stage='switched-confirmed', accepted=dict(state=accepted.state, epoch=accepted.epoch,
            operation_ref=accepted.operation_ref, document_digest=accepted.evidence['document_digest']),
            cli_receipts=[item for item in self.receipts if item.get('event')=='cli'])
        write_private(chain_path, chain)
        write_private(self.directory / 'build-and-switch.json', dict(target=self.switch_cli['target'],
            operation=self.switch_cli['operation'], registry=str(self.switch_cli['registry']),
            document=str(self.switch_cli['document']), base=self.switch_cli['base'], args=self.switch_cli['args'],
            exercise_authority_chain=dict(path=str(chain_path), sha256=hashlib.sha256(chain_path.read_bytes()).hexdigest()),
            original_exercise_digest=chain['initial_document']['canonical_digest'],
            current_accepted_document_digest=accepted.evidence['document_digest']))

    async def browser(self, phase, **details):
        frontend = ROOT / 'frontend'
        chromium = resolve_browser(frontend, os.environ)
        port = self.frontend_port
        log = (self.directory / ('browser-' + phase + '-' + uuid4().hex + '.log')).open('wb')
        os.chmod(log.name, 0o600)
        environment = browser_environment(os.environ, {'BACKEND_URL': self.origin})
        vite = await asyncio.create_subprocess_exec('node', str(frontend / 'node_modules/vite/bin/vite.js'),
            '--host', '127.0.0.1', '--port', str(port), '--strictPort', cwd=frontend, env=environment,
            stdout=log, stderr=log)
        try:
            async with httpx.AsyncClient(trust_env=False) as probe:
                for _ in range(300):
                    try:
                        if (await probe.get(f'http://127.0.0.1:{port}', timeout=1)).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(.05)
                else:
                    raise RuntimeError('owned Vite did not start')
            actor = details.pop('actor', 'qe')
            login = dict(username=self.data['actors'][actor]['username'], password=self.data['password'],
                phase=phase, fmea_id=self.data['fmea_id'], storage_file=str(self.directory / ('browser-session-' + actor + '.json')), **details)
            environment = browser_environment(os.environ, dict(BACKEND_URL=self.origin,
                AGENT_BACKEND_URL=self.origin, AGENT_BROWSER_URL=f'http://127.0.0.1:{port}',
                AGENT_BROWSER_TENANT=self.data['tenant'], AGENT_BROWSER_REPORT=self.data['report_id'],
                AGENT_BROWSER_LOGIN=json.dumps(login), AGENT_BROWSER_ARTIFACTS=str(self.directory / ('playwright-' + phase)),
                OPENQMS_AGENT_BROWSER_EXECUTABLE=str(chromium)))
            child = await asyncio.create_subprocess_exec('node', str(frontend / 'node_modules/@playwright/test/cli.js'),
                'test', '--config', 'playwright.agent.config.ts', 'r6-entry-switch.spec.ts',
                cwd=frontend, env=environment, stdout=log, stderr=log)
            try:
                code = await asyncio.wait_for(child.wait(), 180)
            finally:
                if child.returncode is None:
                    child.kill()
                    await child.wait()
            assert code == 0, 'actual Chromium R6 script failed; inspect private browser log'
            self.receipts.append(dict(event='chromium', phase=phase, pid=child.pid, exit=code))
        finally:
            vite.terminate()
            await vite.wait()
            log.close()
