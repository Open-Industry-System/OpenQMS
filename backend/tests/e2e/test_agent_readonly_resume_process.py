"""Owned PostgreSQL + real HTTP + independent stdlib/browser R3 acceptance.

No auth overrides, fake commit, provider initialization, shared E2E lifecycle or
business commands from the plugin. All helper controls below are test owned.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import uvicorn

from app.api import agent_runtime, agent_tasks, auth
from app.models.agent_readonly_control import AgentReadonlyCheckpoint
from app.models.agent_task import AgentRun, AgentTask, AgentTaskMessage
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.user import User
from tests.e2e.test_readonly_agent_process import (
    process_tenant, Witness, execute, business_snapshot, outputs, MARKER,
)
from tests.services.agent_runtime.test_task_controls import state, wait_lock


class WireDamage:
    """Optional corruption after actual server execution, at the wire boundary."""
    def __init__(self, app):
        self.app, self.path, self.mutate = app, None, None

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] != self.path:
            return await self.app(scope, receive, send)
        messages = []
        async def capture(message):
            messages.append(message)
        await self.app(scope, receive, capture)
        start = next(m for m in messages if m['type']=='http.response.start')
        if start['status'] != 200:
            for message in messages:
                await send(message)
            return
        body = json.loads(b''.join(m.get('body',b'') for m in messages))
        raw = json.dumps(self.mutate(body)).encode()
        await send({'type':'http.response.start','status':200,'headers':[
            (b'content-type',b'application/json'),(b'content-length',str(len(raw)).encode())]})
        await send({'type':'http.response.body','body':raw})


@pytest_asyncio.fixture
async def resume_server(process_tenant, monkeypatch):
    owned = process_tenant
    # The current eight-D state machine calls the real D4 phase D4_ROOT_CAUSE.
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(CAPAEightD).where(CAPAEightD.report_id==owned.report_id).values(status='D4_ROOT_CAUSE'))
        await db.commit()
    from collections import defaultdict
    monkeypatch.setattr(auth, '_login_attempts', defaultdict(list))
    app = FastAPI()
    for router in (auth.router, agent_tasks.router, agent_runtime.router):
        app.include_router(router)
    app.add_middleware(__import__('app.core.tenant_context', fromlist=['TenantContextMiddleware']).TenantContextMiddleware)
    assert not app.dependency_overrides
    wire = WireDamage(app)
    witness = Witness(wire, owned)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(witness, log_level='critical', access_log=False, lifespan='off'))
    runner = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(200):
            if server.started:
                break
            if runner.done():
                await runner
            await asyncio.sleep(.01)
        assert server.started
        instance = SimpleNamespace(owned=owned, witness=witness, app=app, wire=wire,
            url=f'http://127.0.0.1:{sock.getsockname()[1]}')
        async with owned.factory(binding=owned.binding) as db:
            username = (await db.get(User, owned.user_id)).username
        async with httpx.AsyncClient(base_url=instance.url, timeout=15,
                headers={'X-Tenant-ID': owned.slug}) as client:
            response = await client.post('/api/auth/login', json={
                'username': username, 'password': 'process-bootstrap-password'})
            assert response.status_code == 200, response.text
            login = response.json()
            instance.login = login
            client.headers['Authorization'] = 'Bearer '+login['access_token']
            instance.user = client
            yield instance
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(runner, 10)
        finally:
            sock.close()


async def control(server, action, *, run_id=None, epoch=None, checkpoint_id=None, key=None):
    if epoch is None:
        async with server.owned.factory(binding=server.owned.binding) as db:
            run = await db.get(AgentRun, run_id or server.owned.run_id)
            epoch, run_id = run.lease_epoch, run.run_id
    body = dict(action=action, run_id=str(run_id or server.owned.run_id),
        expected_epoch=epoch, idempotency_key=key or uuid.uuid4().hex)
    if checkpoint_id:
        body['checkpoint_id'] = str(checkpoint_id)
    response = await server.user.post(f'/api/agent/tasks/{server.owned.task_id}/control', json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def append(server, content='new instruction', key=None):
    response = await server.user.post(f'/api/agent/tasks/{server.owned.task_id}/messages',
        json={'content': content, 'idempotency_key': key or uuid.uuid4().hex})
    assert response.status_code == 202, response.text
    return response.json()


async def runtime(server, token, method, path, body=None, tenant=None):
    async with httpx.AsyncClient(base_url=server.url, timeout=15) as client:
        return await client.request(method, '/api/agent/runtime'+path, json=body,
            headers={'Authorization': 'Bearer '+token, 'X-Tenant-ID': tenant or server.owned.slug})


async def denied_old_token(server, token, batch, receipt):
    for method, path, body in (
        ('GET', '/capa/context', None), ('GET', '/messages/history', None),
        ('POST', '/messages/ack', {'batch_id': batch, 'through_sequence': 2}),
        ('POST', '/results', {'idempotency_key': 'old-denied', 'receipt_ids': [receipt], 'payload': {}}),
        ('POST', '/finish', {'status': 'completed'})):
        response = await runtime(server, token, method, path, body)
        assert response.status_code == 401 and MARKER not in response.text
        assert not {'receipt_id', 'payload', 'sources'} & response.json().keys()


@pytest.mark.asyncio
async def test_actual_user_pause_resume_rebuilds_history_before_new_batch_and_fences_old_epoch(resume_server):
    server, owned = resume_server, resume_server.owned
    before = await business_snapshot(owned)
    async def pause_after_report():
        await control(server, 'pause', key='pause-between-rounds')
    server.witness.after_first = pause_after_report
    code, stdout, stderr = await execute(server)
    assert code == 1 and stdout == '' and stderr == 'Readonly plugin stopped safely.\n'
    calls = server.witness.calls
    contexts = [c for c in calls if c[1].endswith('/capa/context')]
    assert [c[3] for c in contexts] == [200, 401]
    token = server.witness.tokens[0]
    batch = next(c[4]['batch_id'] for c in calls if c[1].endswith('/messages/claim'))
    receipt = contexts[0][4]['receipt_id']
    assert [len(rows) for rows in await outputs(owned)] == [1, 0, 0, 0, 0]
    await denied_old_token(server, token, batch, receipt)
    await append(server, MARKER+' appended while paused')
    resumed = await control(server, 'resume')
    assert resumed['run_id'] == str(owned.run_id) and resumed['run_status'] == 'pending'
    server.witness.after_first = None
    start = len(calls)
    assert (await execute(server, OPENQMS_CLAIM_KEY='resume-new-epoch'))[0] == 0
    new = calls[start:]
    history = next(c for c in new if c[1].endswith('/messages/history'))
    assert history[2] == {'after_sequence': ['0'], 'limit': ['20']}
    assert [m['sequence'] for m in history[4]['messages']] == [1, 2]
    assert new.index(history) < next(i for i,c in enumerate(new) if c[1].endswith('/messages/claim'))
    new_batch = next(c[4] for c in new if c[1].endswith('/messages/claim'))
    assert new_batch['accepted_sequence'] == 2 and [m['sequence'] for m in new_batch['messages']] == [3]
    assert new_batch['batch_id'] != batch
    async with owned.factory(binding=owned.binding) as db:
        rows = list((await db.scalars(select(AgentTaskMessage).order_by(AgentTaskMessage.sequence))).all())
        assert [(m.sequence, str(m.delivery_batch_id), m.delivery_epoch) for m in rows[:2]] == [(1,batch,1),(2,batch,1)]
        assert (await db.get(AgentRun, owned.run_id)).accepted_message_seq == 3
    await denied_old_token(server, token, batch, receipt)
    assert await business_snapshot(owned) == before


async def cross_tenant_collisions(server, old_run, new_run, tokens):
    """Same source/installation/task/run UUIDs in a second actual tenant."""
    from app.models.agent_plugin import AgentPluginInstallation
    from app.models.agent_runtime_event import AgentProjectionReceipt
    from app.models.product_line import ProductLine
    owned=server.owned
    foreign,binding=await owned.provision()
    async with owned.factory(binding=binding) as db:
        user=await db.scalar(select(User).where(User.email=='process@example.test'))
        line=await db.scalar(select(ProductLine))
        db.add(CAPAEightD(report_id=owned.report_id,document_no='OTHER-TENANT-METADATA',title=MARKER,
            factory_id=line.factory_id,product_line_code=line.code))
        db.add(AgentPluginInstallation(installation_id=owned.plugin_id,plugin_key='foreign-collision',
            plugin_version='1.0.0',manifest={},secret_hash='not-a-credential',enabled=False,created_by=user.user_id))
        await db.flush()
        db.add(AgentTask(task_id=owned.task_id,initiator_id=user.user_id,executor_user_id=user.user_id,
            preferred_installation_id=owned.plugin_id,target_capa_id=owned.report_id,factory_id=line.factory_id,
            request_key='foreign-task',status='ready'))
        await db.flush()
        db.add_all([AgentRun(run_id=old_run,task_id=owned.task_id,installation_id=owned.plugin_id,
            plugin_version='1.0.0',status='stopped'),AgentRun(run_id=new_run,task_id=owned.task_id,
            installation_id=owned.plugin_id,plugin_version='1.0.0',status='active')])
        await db.commit()
    for token in tokens:
        for path in ('/capa/context','/messages/history'):
            response=await runtime(server,token,'GET',path,tenant=foreign.slug)
            assert response.status_code==401 and 'OTHER-TENANT' not in response.text and MARKER not in response.text
    response=await server.user.get(f'/api/agent/tasks/{owned.task_id}/activity',headers={'X-Tenant-ID':foreign.slug})
    assert response.status_code in {401,403} and 'OTHER-TENANT' not in response.text and MARKER not in response.text
    async with owned.factory(binding=binding) as db:
        assert not list((await db.scalars(select(AgentProjectionReceipt))).all())


@pytest.mark.asyncio
async def test_checkpoint_restart_new_process_reads_old_input_and_current_facts_with_new_sources(resume_server):
    server, owned = resume_server, resume_server.owned
    before = await business_snapshot(owned)
    code, stdout, stderr = await execute(server, OPENQMS_READONLY_CHECKPOINT='save')
    assert code == 0, stderr
    old_output = json.loads(stdout)
    checkpoint_id = old_output['checkpoint_id']
    calls = server.witness.calls
    old_claim = next(c[4] for c in calls if c[1] == '/api/agent/runtime/claim')
    old_receipts = [c[4]['receipt_id'] for c in calls if c[1].endswith('/capa/context')]
    old_digest = next(c[4]['projection_digest'] for c in calls if c[2].get('view') == ['verifications'])
    batch = next(c[4]['batch_id'] for c in calls if c[1].endswith('/messages/claim'))
    async with owned.factory(binding=owned.binding) as db:
        checkpoint = await db.get(AgentReadonlyCheckpoint, uuid.UUID(checkpoint_id))
        assert checkpoint.accepted_message_seq == 2 and checkpoint.run_id == owned.run_id
    await control(server, 'pause')
    await append(server, MARKER+' new post-checkpoint instruction')
    # An explicitly authorized fixture business edit, never performed by plugin.
    async with owned.factory(binding=owned.binding) as db:
        verification = await db.scalar(select(CapaRootCauseVerification).where(
            CapaRootCauseVerification.capa_id == owned.report_id,
            CapaRootCauseVerification.conclusion == 'pending'))
        verification.conclusion, verification.is_verified = 'failed', False
        await db.commit()
    changed = await business_snapshot(owned)
    assert changed[0] == before[0] and changed[1] != before[1]
    restarted = await control(server, 'restart', checkpoint_id=checkpoint_id)
    new_run = uuid.UUID(restarted['run_id'])
    assert new_run != owned.run_id and restarted['run_status'] == 'pending'
    async with owned.factory(binding=owned.binding) as db:
        run = await db.get(AgentRun, new_run)
        assert run.accepted_message_seq == 2 and str(run.resume_checkpoint_id) == checkpoint_id
    async def reject_old_sources_and_prove_read_only_history():
        current_token=server.witness.tokens[-1]
        before_history=await state(owned)
        response=await runtime(server,current_token,'GET','/messages/history')
        assert response.status_code==200 and [m['sequence'] for m in response.json()['messages']]==[1,2,3]
        assert await state(owned)==before_history
        stale_ack=await runtime(server,current_token,'POST','/messages/ack',{'batch_id':batch,'through_sequence':2})
        assert stale_ack.status_code==409 and await state(owned)==before_history
        before_outputs=[len(rows) for rows in await outputs(owned)]
        old_source=await runtime(server,current_token,'POST','/results',{
            'idempotency_key':'reject-old-run-sources','receipt_ids':old_receipts,'payload':{}})
        assert old_source.status_code==403 and MARKER not in old_source.text
        assert [len(rows) for rows in await outputs(owned)]==before_outputs
        await cross_tenant_collisions(server,owned.run_id,new_run,[old_claim['token'],current_token])
    server.witness.after_first=reject_old_sources_and_prove_read_only_history
    start = len(calls)
    code, stdout, stderr = await execute(server, OPENQMS_CLAIM_KEY='checkpoint-restart', OPENQMS_READONLY_FINISH='completed')
    assert code == 0, stderr
    new_output = json.loads(stdout)
    assert new_output['run_id'] == str(new_run) and new_output['task_status'] == 'completed'
    new = calls[start:]
    claim = next(c[4] for c in new if c[1] == '/api/agent/runtime/claim')
    assert claim['accepted_message_seq'] == 2 and claim['has_resume_checkpoint'] is True
    history = next(c for c in new if c[1].endswith('/messages/history'))
    assert [m['sequence'] for m in history[4]['messages']] == [1, 2]
    assert new.index(history) < next(i for i,c in enumerate(new) if c[1].endswith('/messages/claim'))
    new_receipts = [c[4]['receipt_id'] for c in new if c[1].endswith('/capa/context') and c[3]==200]
    assert len(new_receipts) == 2 and not set(new_receipts) & set(old_receipts)
    assert next(c[4]['projection_digest'] for c in new if c[2].get('view') == ['verifications']) != old_digest
    new_result = next(c[4] for c in new if c[1].endswith('/results') and c[3]==200)
    assert '1 failed' in new_result['payload']['explanations'][0]
    await denied_old_token(server, old_claim['token'], batch, old_receipts[0])
    historical = await server.user.get(f'/api/agent/tasks/{owned.task_id}/results/{old_output["result_id"]}')
    assert historical.status_code == 200 and historical.json()['run_id'] == str(owned.run_id)
    assert await business_snapshot(owned) == changed


async def http_finish_append_race(server, monkeypatch, winner):
    owned = server.owned
    assert (await execute(server))[0] == 0
    token = server.witness.tokens[-1]
    entered, release = asyncio.Event(), asyncio.Event()
    original_commit = AsyncSession.commit
    original_operation = (__import__('app.services.agent_runtime.message_queue', fromlist=['append_task_message'])
        if winner == 'append' else __import__('app.services.agent_runtime.task_controls', fromlist=['finish_run']))
    operation_name = 'append_task_message' if winner == 'append' else 'finish_run'
    operation = getattr(original_operation, operation_name)
    async def mark_operation(db, *args, **kwargs):
        db.info['acceptance_commit_barrier'] = True
        return await operation(db, *args, **kwargs)
    async def held_commit(db):
        if db.info.pop('acceptance_commit_barrier', False):
            await db.flush()
            entered.set()
            await asyncio.wait_for(release.wait(), 15)
        await original_commit(db)
    monkeypatch.setattr(original_operation, operation_name, mark_operation)
    monkeypatch.setattr(AsyncSession, 'commit', held_commit)
    async def append_http():
        return await server.user.post(f'/api/agent/tasks/{owned.task_id}/messages',
            json={'content': 'real racing new instruction', 'idempotency_key': 'race-input'})
    async def finish_http():
        return await runtime(server, token, 'POST', '/finish', {'status': 'completed'})
    first = asyncio.create_task(append_http() if winner == 'append' else finish_http())
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 15)
        second = asyncio.create_task(finish_http() if winner == 'append' else append_http())
        await wait_lock(owned, 'agent_tasks')
        assert not second.done()
        release.set()
        response = await asyncio.wait_for(first, 15)
        assert response.status_code == (202 if winner == 'append' else 200)
        expected = await state(owned)
        rejected = await asyncio.wait_for(second, 15)
        assert rejected.status_code == 409 and await state(owned) == expected
        page = await server.user.get(f'/api/agent/tasks/{owned.task_id}/activity')
        assert page.status_code == 200
        assert page.json()['task_status'] == ('ready' if winner == 'append' else 'completed')
        if winner == 'append':
            assert any(i['kind']=='message' and i['data']['state']=='queued' for i in page.json()['items'])
        else:
            assert len([i for i in page.json()['items'] if i['kind']=='message']) == 2
        return {'winner':winner,'task_status':page.json()['task_status']}
    finally:
        release.set()
        await asyncio.gather(*[task for task in (first,second) if task], return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('winner', ['append', 'finish'])
async def test_actual_http_finish_append_task_lock_race(resume_server,monkeypatch,winner):
    await http_finish_append_race(resume_server,monkeypatch,winner)


@pytest.mark.asyncio
async def test_same_run_after_prior_result_uses_new_epoch_output_keys_and_bounded_history(resume_server):
    server, owned = resume_server, resume_server.owned
    # More than one bounded input/history page, genuinely queued via User HTTP.
    for sequence in range(3, 46):
        await append(server, MARKER+f' input {sequence}')
    assert (await execute(server))[0] == 0  # default deliberately accepts one batch
    await control(server, 'pause')
    await control(server, 'resume')
    assert (await execute(server, OPENQMS_CLAIM_KEY='second-epoch', OPENQMS_READONLY_CHECKPOINT='save'))[0] == 0
    await control(server, 'pause')
    await control(server, 'resume')
    start = len(server.witness.calls)
    code, stdout, stderr = await execute(server, OPENQMS_CLAIM_KEY='third-epoch', OPENQMS_READONLY_FINISH='completed')
    assert code == 0, stderr
    new = server.witness.calls[start:]
    histories = [c for c in new if c[1].endswith('/messages/history')]
    assert [len(c[4]['messages']) for c in histories] == [20,20]
    assert [c[2]['after_sequence'] for c in histories] == [['0'],['20']]
    assert all(c[2]['limit'] == ['20'] for c in histories)
    assert all(c[3] == 200 for c in new)
    receipts, events, results, _, _ = await outputs(owned)
    assert len(receipts) == 6 and len(events) == len(results) == 3
    assert len({r.idempotency_key for r in results}) == 3
    assert json.loads(stdout)['task_status'] == 'completed'


class BrowserHarness:
    """Nonce-bound local fixture operations; real APIs supply every UI response."""
    def __init__(self, server, monkeypatch):
        self.monkeypatch = monkeypatch
        self.server, self.owned = server, server.owned
        self.nonce = uuid.uuid4().hex
        self.process = None
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.report_b = self.report_c = None
        self.before, self.changed = None, None

    async def prepare(self, scenario):
        from app.api import capa, product_line, fmea, knowledge
        from app.models.factory import Factory
        from app.models.product_line import ProductLine
        from app.models.agent_plugin import AgentPluginGrant
        # Mirror main's multi-tenant NONE state without running its lifespan.
        self.server.app.state.llm_provider=None
        self.server.app.state.embedding_provider=None
        from app.services.ai_config_service import get_raw_ai_config
        async with self.owned.factory(binding=self.owned.binding) as db:
            config=await get_raw_ai_config(db)
            provider_configured=bool(config.llm_provider)
            del config
            assert not provider_configured, 'Owned browser tenant must not initialize any provider'
        # Actual product routers, without main lifespan or providers.
        for router in (capa.router, product_line.router, fmea.router, knowledge.router):
            self.server.app.include_router(router)
        async with self.owned.factory(binding=self.owned.binding) as db:
            second = Factory(code='BROWSER-OTHER', name='浏览器第二工厂', location='synthetic')
            db.add(second)
            await db.flush()
            second_line = ProductLine(code='BROWSER-OTHER', name='浏览器第二产品线', factory_id=second.id)
            db.add(second_line)
            await db.flush()
            other = CAPAEightD(document_no='8D-BROWSER-B', title='Synthetic browser B', status='D4_ROOT_CAUSE',
                factory_id=second.id, product_line_code=second_line.code, created_by=self.owned.user_id)
            db.add(other)
            await db.flush()
            self.report_b = other.report_id
            if scenario=='authority-capa':
                moved = CAPAEightD(document_no='8D-BROWSER-MOVED', title='Synthetic moved source', status='D4_ROOT_CAUSE',
                    factory_id=self.owned.factory_id,product_line_code=self.owned.line,created_by=self.owned.user_id)
                db.add(moved)
                await db.flush()
                self.report_c = moved.report_id
            grant = await db.get(AgentPluginGrant, self.owned.grant_id)
            grant.factory_ids = [str(self.owned.factory_id),str(second.id)]
            grant.product_line_codes = [self.owned.line,second_line.code]
            grant.object_ids = [str(self.owned.report_id),str(other.report_id)]
            for verification in (await db.scalars(select(CapaRootCauseVerification).where(
                    CapaRootCauseVerification.capa_id==self.owned.report_id))).all():
                # R2's metadata-only fixture used list[str]; the real human DTO
                # requires list[dict]. Keep free text present but outside projection.
                verification.evidence_attachments=[{'name':MARKER,'url':'/synthetic-evidence'}]
            await db.commit()
        verification_response=await self.server.user.get(f'/api/capa/{self.owned.report_id}/root-cause-verifications')
        assert verification_response.status_code==200
        assert len(verification_response.json())==2 and MARKER in verification_response.text
        recommendation_response=await self.server.user.get(f'/api/capa/{self.owned.report_id}/d4-fmea-recommendations')
        self.recommendation_status=recommendation_response.status_code
        assert recommendation_response.status_code==422
        blocked=recommendation_response.json()['detail']
        assert blocked['blocked'] is True and blocked['reason']=='LLM credentials not configured'
        # Refresh actual auth/me will discover the added factory and product line.
        self.before = await business_snapshot(self.owned)
        if scenario.startswith('authority'):
            assert (await execute(self.server))[0] == 0
        if scenario == 'window':
            await self.seed_to(100)

    async def seed_to(self, target):
        from sqlalchemy import func
        from app.models.agent_readonly_control import AgentTaskUpdate
        async with self.owned.factory(binding=self.owned.binding) as db:
            maximum = await db.scalar(select(func.coalesce(func.max(AgentTaskUpdate.sequence),0)))
        assert maximum <= target
        for sequence in range(maximum+1, target+1):
            await append(self.server, f'浏览器活动 {sequence}', key=f'window-{sequence}')
        async with self.owned.factory(binding=self.owned.binding) as db:
            assert await db.scalar(select(func.max(AgentTaskUpdate.sequence))) == target
        return {'watermark':target}

    async def handle(self, action, body):
        server, owned = self.server, self.owned
        if action == 'start':
            assert self.process is None or self.process.done()
            self.entered, self.release = asyncio.Event(), asyncio.Event()
            async def hold():
                self.entered.set()
                await asyncio.wait_for(self.release.wait(), 30)
            server.witness.after_first = hold if body.get('hold') else None
            kwargs = {'OPENQMS_CLAIM_KEY': uuid.uuid4().hex}
            if body.get('checkpoint'):
                kwargs['OPENQMS_READONLY_CHECKPOINT'] = 'save'
            if body.get('finish'):
                kwargs['OPENQMS_READONLY_FINISH'] = 'completed'
            self.start_index = len(server.witness.calls)
            self.process = asyncio.create_task(execute(server, **kwargs))
            if body.get('hold'):
                await asyncio.wait_for(self.entered.wait(), 15)
                assert not self.process.done()
            return {'alive': not self.process.done()}
        if action == 'release':
            assert self.process and not self.process.done()
            self.release.set()
            return {'released':True}
        if action == 'join':
            code, stdout, stderr = await asyncio.wait_for(self.process, 30)
            calls = server.witness.calls[self.start_index:]
            return {'code':code, 'output':json.loads(stdout) if stdout else None,
                'safe_failure':stderr == 'Readonly plugin stopped safely.\n',
                'history':[[m['sequence'] for m in c[4]['messages']] for c in calls if c[1].endswith('/messages/history')],
                'contexts':[c[3] for c in calls if c[1].endswith('/capa/context')]}
        if action == 'edit':
            async with owned.factory(binding=owned.binding) as db:
                row = await db.scalar(select(CapaRootCauseVerification).where(
                    CapaRootCauseVerification.capa_id==owned.report_id, CapaRootCauseVerification.conclusion=='pending'))
                row.conclusion, row.is_verified = 'failed', False
                await db.commit()
            self.changed = await business_snapshot(owned)
            return {'edited':True}
        if action == 'seed':
            return await self.seed_to(body['target'])
        if action == 'withdraw':
            from sqlalchemy import delete
            from app.models.role import RoleDefinition, RolePermission, UserProductLine
            from app.models.factory import UserFactory
            async with owned.factory(binding=owned.binding) as db:
                change=body['change']
                if change=='role':
                    await db.execute(update(RolePermission).where(RolePermission.role_id==owned.role_id,
                        RolePermission.module=='capa').values(permission_level=0))
                elif change=='capa':
                    # The previously sourced CAPA no longer belongs to this fixed task.
                    await db.execute(update(AgentTask).where(AgentTask.task_id==owned.task_id).values(target_capa_id=self.report_c))
                elif change=='factory':
                    await db.execute(update(RolePermission).where(RolePermission.role_id==owned.role_id,
                        RolePermission.module=='group').values(permission_level=0))
                    await db.execute(delete(UserFactory).where(UserFactory.user_id==owned.user_id))
                    await db.execute(update(User).where(User.user_id==owned.user_id).values(factory_id=None))
                elif change=='line':
                    await db.execute(update(RoleDefinition).where(RoleDefinition.id==owned.role_id).values(bypass_row_level_security=False))
                    await db.execute(delete(UserProductLine).where(UserProductLine.user_id==owned.user_id))
                else:
                    raise AssertionError('Unknown fixture withdrawal')
                await db.commit()
            return {'withdrawn':True}
        if action == 'race':
            return await http_finish_append_race(server,self.monkeypatch,body['winner'])
        if action == 'state':
            from sqlalchemy import func
            from app.models.agent_readonly_control import AgentTaskControl
            from app.models.audit import AuditLog
            async with owned.factory(binding=owned.binding) as db:
                tasks = list((await db.scalars(select(AgentTask).order_by(AgentTask.created_at))).all())
                return {'tasks':[{'id':str(t.task_id),'target':str(t.target_capa_id),'status':t.status} for t in tasks],
                    'controls':await db.scalar(select(func.count()).select_from(AgentTaskControl).where(AgentTaskControl.task_id==owned.task_id)),
                    'pause_audits':await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='CONTROL_AGENT_TASK', AuditLog.changed_fields['action'].astext=='pause'))}
        raise AssertionError('Unknown test harness command')


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['lifecycle','window','authority-role','authority-capa','authority-factory','authority-line','race-append','race-finish'])
async def test_actual_local_browser_sidebar_acceptance(resume_server, scenario, tmp_path, monkeypatch):
    """Node Playwright drives Chromium, Vite and actual authenticated tenant APIs."""
    from fastapi import Request, HTTPException
    chromium=Path(os.environ.get('OPENQMS_AGENT_BROWSER_EXECUTABLE') or
        '/Users/sam/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')
    if not chromium.is_file():
        pytest.fail('Installed Chromium missing; set OPENQMS_AGENT_BROWSER_EXECUTABLE. No browser is installed by this harness.')
    server = resume_server
    harness = BrowserHarness(server,monkeypatch)
    await harness.prepare(scenario)
    @server.app.post('/__agent_acceptance/{action}')
    async def command(action: str, request: Request):
        if request.headers.get('X-Acceptance-Nonce') != harness.nonce:
            raise HTTPException(status_code=404)
        return await harness.handle(action, await request.json())
    # Our test router lives only in this allocated fixture app and is not checked
    # into or mounted by any product module.
    frontend = Path(__file__).resolve().parents[3] / 'frontend'
    socket_probe = socket.socket()
    socket_probe.bind(('127.0.0.1',0))
    port = socket_probe.getsockname()[1]
    socket_probe.close()
    env = {key:value for key,value in os.environ.items() if key not in {
        'DATABASE_URL','TEST_DATABASE_URL','SECRET_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'}}
    env.update(BACKEND_URL=server.url)
    vite_log = (tmp_path/'vite.log').open('wb')
    vite = await asyncio.create_subprocess_exec('node', str(frontend/'node_modules/vite/bin/vite.js'),
        '--host','127.0.0.1','--port',str(port),'--strictPort',cwd=frontend,env=env,stdout=vite_log,stderr=vite_log)
    browser = None
    try:
        async with httpx.AsyncClient() as readiness:
            for _ in range(300):
                if vite.returncode is not None:
                    pytest.fail('owned Vite exited: '+(tmp_path/'vite.log').read_text())
                try:
                    if (await readiness.get(f'http://127.0.0.1:{port}',timeout=1)).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.05)
            else:
                pytest.fail('owned Vite did not start')
        env.update(AGENT_BROWSER_URL=f'http://127.0.0.1:{port}', AGENT_BACKEND_URL=server.url,
            AGENT_HARNESS_NONCE=harness.nonce, AGENT_BROWSER_SCENARIO=scenario,
            AGENT_BROWSER_LOGIN=json.dumps(server.login), AGENT_BROWSER_TENANT=server.owned.slug,
            AGENT_BROWSER_TASK=str(server.owned.task_id),AGENT_BROWSER_REPORT=str(server.owned.report_id),
            AGENT_BROWSER_REPORT_B=str(harness.report_b), AGENT_BROWSER_ARTIFACTS=str(tmp_path/'playwright'))
        browser = await asyncio.create_subprocess_exec('node',str(frontend/'node_modules/@playwright/test/cli.js'),
            'test','--config','playwright.agent.config.ts','readonly-sidebar.spec.ts',cwd=frontend,env=env,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(browser.communicate(),180)
        (tmp_path/'browser.log').write_bytes(stdout+stderr)
        assert browser.returncode == 0, (stdout+stderr).decode()
        assert b'1 passed' in stdout and b'skipped' not in stdout
        print(f'Actual browser {scenario}: verification=200, recommendation={harness.recommendation_status} (LLM credentials not configured), Playwright=1 passed')
        # A plugin never changes business rows. Only explicit fixture edit differs.
        if scenario=='lifecycle':
            assert await business_snapshot(server.owned) == harness.changed
        else:
            assert await business_snapshot(server.owned) == harness.before
    finally:
        harness.release.set()
        if harness.process and not harness.process.done():
            await asyncio.gather(harness.process,return_exceptions=True)
        if browser and browser.returncode is None:
            browser.kill()
            await browser.wait()
        if vite.returncode is None:
            vite.terminate()
            try:
                await asyncio.wait_for(vite.wait(),10)
            except asyncio.TimeoutError:
                vite.kill()
                await vite.wait()
        vite_log.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['sequence','cursor','complete','empty'])
async def test_malformed_actual_history_stops_before_pending_claim_with_constant_failure(resume_server, damage):
    server = resume_server
    assert (await execute(server))[0] == 0
    await control(server,'pause')
    await control(server,'resume')
    def mutate(body):
        if damage=='sequence': body['messages'][0]['sequence']=True
        elif damage=='cursor': body['next_sequence']=True
        elif damage=='complete': body['complete']=False
        else: body['messages']=[]
        return body
    server.wire.path,server.wire.mutate='/api/agent/runtime/messages/history',mutate
    start=len(server.witness.calls)
    code,stdout,stderr=await execute(server,OPENQMS_CLAIM_KEY='damaged-history')
    assert (code,stdout,stderr)==(1,'','Readonly plugin stopped safely.\n')
    assert [c[1] for c in server.witness.calls[start:]]==['/api/agent/runtime/claim','/api/agent/runtime/messages/history']


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary,damage', [('checkpoints','epoch_bool'),('checkpoints','extra'),
    ('checkpoints','source_digest'),('finish','epoch_bool'),('finish','missing_epoch'),('finish','extra')])
async def test_malformed_actual_checkpoint_finish_response_has_constant_failure(resume_server,boundary,damage):
    server=resume_server
    def mutate(body):
        if damage=='epoch_bool': body['lease_epoch']=True
        elif damage=='extra': body['instructions']=MARKER
        elif damage=='missing_epoch': del body['lease_epoch']
        else: body['sources'][0]['projection_digest']='invalid'
        return body
    server.wire.path,server.wire.mutate='/api/agent/runtime/'+boundary,mutate
    options=({'OPENQMS_READONLY_CHECKPOINT':'save'} if boundary=='checkpoints'
        else {'OPENQMS_READONLY_FINISH':'completed'})
    code,stdout,stderr=await execute(server,**options)
    assert (code,stdout,stderr)==(1,'','Readonly plugin stopped safely.\n')


@pytest.mark.asyncio
async def test_process_completed_option_rejects_append_after_input_drain_without_finish_write(resume_server):
    server,owned=resume_server,resume_server.owned
    async def append_between_queries():
        await append(server,'actual late queued instruction',key='late-after-drain')
    server.witness.after_first=append_between_queries
    code,stdout,stderr=await execute(server,OPENQMS_READONLY_FINISH='completed')
    assert (code,stdout,stderr)==(1,'','Readonly plugin stopped safely.\n')
    finish=next(c for c in server.witness.calls if c[1].endswith('/finish'))
    assert finish[3]==409
    saved=await state(owned)
    assert saved[:3]==('ready','active',1)
    assert not any(kind=='finish' for kind,_ in saved[7])
    assert not any(action=='FINISH_AGENT_RUN' for action,_ in saved[8])
    assert [len(rows) for rows in await outputs(owned)]==[2,1,1,2,2]


@pytest.mark.asyncio
@pytest.mark.parametrize('env', [{'OPENQMS_READONLY_CHECKPOINT':'arbitrary-selector'}, {'OPENQMS_READONLY_FINISH':'failed'}])
async def test_process_rejects_unbounded_protocol_options_before_network(resume_server,env):
    server=resume_server
    start=len(server.witness.calls)
    assert await execute(server,**env)==(1,'','Readonly plugin stopped safely.\n')
    assert len(server.witness.calls)==start


@pytest.mark.asyncio
async def test_canonical_real_d4_phase_is_accepted_by_independent_process(resume_server):
    server=resume_server
    code,stdout,stderr=await execute(server)
    assert code==0,stderr
    contexts=[c for c in server.witness.calls if c[1].endswith('/capa/context')]
    assert len(contexts)==2 and all(c[4]['status']=='D4_ROOT_CAUSE' for c in contexts)
    assert json.loads(stdout)['task_id']==str(server.owned.task_id)
