"""Fixed D4 receiver against a normal-policy owned TCP application."""
import asyncio
import json
from pathlib import Path
import socket
import sys
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
import uvicorn
from sqlalchemy import func, select

from app.models.agent_task import AgentRun, AgentTaskMessage
from app.models.capa_d4_delivery import AgentRestrictedProjectionReceipt
from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
from tests.e2e.agent_local_trial_harness import business_snapshot, local_trial_server
from tests.e2e.d4_text_local_harness import d4_text_local_trial, d4_text_server, owned_local_trial
from tests.e2e.sdk_process_support import sdk_child, sdk_runtime

pytestmark = pytest.mark.requires_db


@pytest_asyncio.fixture
async def text_fault_server(d4_text_local_trial):
    """Fault only actual serialized responses, after the real handler has run."""
    c = d4_text_local_trial
    c.text_fault = None
    c.fault_calls = []
    async def witness(scope, receive, send):
        if scope['type'] != 'http':
            return await c.app(scope, receive, send)
        frames = []
        async def collect(message):
            frames.append(message)
        await c.app(scope, receive, collect)
        path = scope['path']
        start = next(m for m in frames if m['type'] == 'http.response.start')
        chunks = [m.get('body', b'') for m in frames if m['type'] == 'http.response.body']
        raw = b''.join(chunks)
        c.fault_calls.append((scope['method'], path, start['status']))
        kind = c.text_fault
        if path.endswith('/capa/d4/root-cause-text') and kind in ('bad-json', 'utf8', 'oversize', 'label', 'binding'):
            if kind == 'bad-json': raw = b'{'
            elif kind == 'utf8': raw = b'\xff'
            elif kind == 'oversize': raw = b'x' * (256 * 1024 + 1)
            else:
                body = json.loads(raw)
                if kind == 'label': body['data_class'] = 'internal'
                else: body['report_id'] = str(uuid4())
                raw = json.dumps(body).encode()
        elif path.endswith('/finish') and kind in ('finish-bad-json', 'finish-oversize', 'finish-disconnect'):
            raw = b'{' if kind == 'finish-bad-json' else b'x' * (256 * 1024 + 1)
            if kind == 'finish-disconnect':
                raw = b''
        start['headers'] = [(k, v) for k, v in start['headers'] if k.lower() != b'content-length']
        length = len(raw) + int(path.endswith('/finish') and kind == 'finish-disconnect')
        start['headers'].append((b'content-length', str(length).encode()))
        await send(start)
        if path.endswith('/capa/d4/root-cause-text') and kind == 'slow':
            await send({'type': 'http.response.body', 'body': raw[:1], 'more_body': True})
            await asyncio.sleep(11)
            raw = raw[1:]
        await send({'type': 'http.response.body', 'body': raw, 'more_body': False})
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(witness, log_level='critical', access_log=False,
                                           lifespan='off', proxy_headers=False))
    runner = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(300):
            if server.started: break
            if runner.done(): await runner
            await asyncio.sleep(.01)
        assert server.started
        c.text_base_url = f'http://127.0.0.1:{sock.getsockname()[1]}'
        yield c
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(runner, 15)
        finally:
            sock.close()


async def _run_receiver(c, *, request_key):
    receiver = Path(__file__).resolve().parents[2] / 'examples/readonly_d4_text_receiver.py'
    process = await asyncio.create_subprocess_exec(sys.executable, str(receiver),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    config = {'origin': c.text_base_url, 'tenant_slug': c.slug, 'installation_id': str(c.text_id),
              'secret': c.text_secret, 'request_key': request_key, 'expected_report_id': str(c.report_id)}
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(json.dumps(config).encode()), timeout=60)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert c.text_secret.encode() not in stdout + stderr
    return process.returncode, json.loads(stdout), stderr.decode()


@pytest.mark.asyncio
async def test_fixed_text_receiver_normal_http(d4_text_server):
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    task_id = UUID(created.json()['task_id'])
    before = await business_snapshot(c)
    code, result, stderr = await _run_receiver(c, request_key=uuid4().hex)
    assert code == 0 and stderr == '' and result['status'] == 'completed'
    assert [(method, path, status) for method, path, status in c.text_calls] == [
        ('POST', '/api/agent/runtime/claim', 200),
        ('GET', '/api/agent/runtime/capabilities', 200),
        ('POST', '/api/agent/runtime/messages/claim', 200),
        ('GET', '/api/agent/runtime/capa/d4/root-cause-text', 200),
        ('POST', '/api/agent/runtime/messages/ack', 200),
        ('POST', '/api/agent/runtime/finish', 200),
    ]
    assert 'synthetic candidate' not in json.dumps(result)
    assert await business_snapshot(c) == before
    async with c.session() as db:
        receipt = await db.get(AgentRestrictedProjectionReceipt, UUID(result['receipt_id']))
        run = await db.scalar(select(AgentRun).where(AgentRun.task_id == task_id))
        message = await db.scalar(select(AgentTaskMessage).where(AgentTaskMessage.task_id == task_id))
        assert receipt is not None and receipt.run_id == run.run_id
        assert message.state == 'accepted' and run.accepted_message_seq == 1
        assert run.status == 'completed'


@pytest.mark.asyncio
async def test_source_swap_never_widens_old_grants(d4_text_server):
    c = d4_text_server
    def task_request(scope):
        return {'report_id': str(c.report_id), 'installation_id': str(c.text_id),
                'request_key': uuid4().hex, 'initial_text': START_MESSAGE, 'derived_source_scope': scope}
    a, b = c.source_scope, {**c.source_scope, 'cause_node_id': 'cause-B'}
    first = await c.client.post('/api/agent/tasks', json=task_request(a))
    assert first.status_code == 201 and first.json()['status'] == 'ready', first.text
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        proof = await c.admin.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
            'root_cause_text': 'synthetic candidate', 'method': 'measurement', 'conclusion': 'passed',
            'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-B'},
            'source_declaration': {'declares_complete_coverage': True}})
        assert proof.status_code == 200 and proof.json()['source_proof_issued'] is True, proof.text
        before_denial = await business_snapshot(c)
        denied = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
                                  headers={'Authorization': 'Bearer ' + claim.json()['token']})
        assert denied.status_code in (401, 403) and 'synthetic candidate' not in denied.text
        assert await business_snapshot(c) == before_denial
    blocked_b = await c.client.post('/api/agent/tasks', json=task_request(b))
    assert blocked_b.status_code == 201 and blocked_b.json()['status'] == 'blocked_capability', blocked_b.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
    old_grant = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}',
                                    json={'enabled': False})
    assert old_grant.status_code == 200, old_grant.text
    from datetime import UTC, datetime, timedelta
    grant_b = await c.admin.post(f'/api/admin/agent-plugins/{c.text_id}/grants', json={
        'capability_id': 'capa.d4.root_cause_candidate.masked.v1', 'factory_ids': [str(c.factory_id)],
        'object_ids': [str(c.report_id)], 'product_line_codes': [c.line], 'enabled': True,
        'expires_at': (datetime.now(UTC) + timedelta(minutes=10)).isoformat(), 'derived_source_scope': b})
    assert grant_b.status_code == 201, grant_b.text
    blocked_a = await c.client.post('/api/agent/tasks', json=task_request(a))
    assert blocked_a.status_code in (403, 409) or (blocked_a.status_code == 201 and
                                                     blocked_a.json()['status'] == 'blocked_capability'), blocked_a.text
    ready_b = await c.client.post('/api/agent/tasks', json=task_request(b))
    assert ready_b.status_code == 201 and ready_b.json()['status'] == 'ready', ready_b.text
    before_receiver = await business_snapshot(c)
    code, result, stderr = await _run_receiver(c, request_key=uuid4().hex)
    assert code == 0 and stderr == '' and result['status'] == 'completed'
    assert await business_snapshot(c) == before_receiver


@pytest.mark.asyncio
async def test_revoked_text_grant_does_not_block_stop_controls(d4_text_server):
    from tests.e2e.test_d4_text_revocation_controls import test_revoked_text_grant_denies_body_but_allows_stop_and_cancel
    before = await business_snapshot(d4_text_server)
    await test_revoked_text_grant_denies_body_but_allows_stop_and_cancel(d4_text_server)
    assert await business_snapshot(d4_text_server) == before


@pytest.mark.asyncio
async def test_first_claimable_text_profile_has_message_gate(d4_text_server):
    from tests.e2e.test_d4_text_early_admission import test_first_claimable_text_profile_has_message_gate as exercise
    for case in ('first', 'retry', 'old_epoch', 'history', 'ack'):
        await exercise(d4_text_server, case)


@pytest.mark.asyncio
async def test_text_message_sentinel_never_crosses_tcp(d4_text_server):
    from tests.e2e.test_d4_text_early_admission import test_first_claimable_text_profile_has_message_gate as exercise
    for case in ('first', 'retry', 'old_epoch', 'history', 'ack'):
        await exercise(d4_text_server, case)


@pytest.mark.asyncio
async def test_text_scope_idempotency_and_restart_do_not_regrant(d4_text_server):
    from app.models.agent_derived_source import AgentTaskDerivedSourceScope
    c = d4_text_server
    key = uuid4().hex
    request = {'report_id': str(c.report_id), 'installation_id': str(c.text_id), 'request_key': key,
               'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope}
    first = await c.client.post('/api/agent/tasks', json=request)
    assert first.status_code == 201 and first.json()['status'] == 'ready', first.text
    other = {**request, 'derived_source_scope': {**c.source_scope, 'cause_node_id': 'cause-B'}}
    clash = await c.client.post('/api/agent/tasks', json=other)
    assert clash.status_code == 409, clash.text
    task_id = UUID(first.json()['task_id'])
    async with c.session() as db:
        scopes_before = [(row.task_grant_id, row.fmea_id, row.cause_node_id)
                         for row in (await db.scalars(select(AgentTaskDerivedSourceScope))).all()]
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as runtime:
        claim = await runtime.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200 and claim.json()['task_id'] == str(task_id), claim.text
        run = claim.json()
        auth = {'Authorization': 'Bearer ' + c.user_token}
        pause = await runtime.post(f'/api/agent/tasks/{task_id}/control', headers=auth, json={
            'action': 'pause', 'run_id': run['run_id'], 'expected_epoch': run['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        cp = await runtime.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints', headers=auth,
            json={'run_id': run['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert cp.status_code == 200, cp.text
        restart = await runtime.post(f'/api/agent/tasks/{task_id}/control', headers=auth, json={
            'action': 'restart', 'run_id': run['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
            'checkpoint_id': cp.json()['checkpoint_id'], 'idempotency_key': uuid4().hex})
        assert restart.status_code == 200 and restart.json()['run_id'] != run['run_id'], restart.text
        async with c.session() as db:
            scopes_after = [(row.task_grant_id, row.fmea_id, row.cause_node_id)
                            for row in (await db.scalars(select(AgentTaskDerivedSourceScope))).all()]
        assert scopes_before == scopes_after
        disabled = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}',
                                       json={'enabled': False})
        assert disabled.status_code == 200, disabled.text
        denied = await runtime.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert denied.status_code in (401, 403, 404, 409), denied.text
        assert 'synthetic candidate' not in denied.text
        from app.models.agent_plugin import AgentPluginGrant
        from datetime import UTC, datetime, timedelta
        from sqlalchemy import update
        async with c.session() as db:
            await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.grant_id == c.text_grant_id).values(
                enabled=True, expires_at=datetime.now(UTC) - timedelta(seconds=1)))
            await db.commit()
        expired = await runtime.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert expired.status_code in (401, 403, 404, 409) and 'synthetic candidate' not in expired.text


@pytest.mark.asyncio
async def test_blocked_task_source_request_replay(d4_text_server, monkeypatch):
    from app.models.agent_task import AgentRun, AgentTaskGrant
    from app.models.agent_task_request import AgentTaskSourceRequest
    from app.services.agent_runtime import task_service
    c = d4_text_server
    disabled = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}',
                                   json={'enabled': False})
    assert disabled.status_code == 200, disabled.text
    key = uuid4().hex
    body = {'report_id': str(c.report_id), 'installation_id': str(c.text_id), 'request_key': key,
            'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope}
    original = task_service._existing
    waiters = {}
    async def concurrent_read(db, user_id, request_key, *args, **kwargs):
        result = await original(db, user_id, request_key, *args, **kwargs)
        if result is None:
            count, barrier = waiters.setdefault(request_key, [0, asyncio.Event()])
            if count < 2:
                waiters[request_key][0] += 1
                if waiters[request_key][0] == 2:
                    barrier.set()
                await asyncio.wait_for(barrier.wait(), timeout=15)
        return result
    monkeypatch.setattr(task_service, '_existing', concurrent_read)
    first, same = await asyncio.gather(*(c.client.post('/api/agent/tasks', json=body) for _ in range(2)))
    assert first.status_code == same.status_code == 201, (first.text, same.text)
    assert first.json()['status'] == same.json()['status'] == 'blocked_capability'
    assert first.json()['task_id'] == same.json()['task_id']
    task_id = UUID(first.json()['task_id'])
    async with c.session() as db:
        original_request = await db.get(AgentTaskSourceRequest, task_id)
        assert original_request is not None
        original_fingerprint = original_request.request_fingerprint
    conflict = await c.client.post('/api/agent/tasks', json={**body, 'derived_source_scope':
                                  {**c.source_scope, 'cause_node_id': 'cause-B'}})
    assert conflict.status_code == 409, conflict.text
    other_key = uuid4().hex
    other = {**body, 'request_key': other_key}
    a, b = await asyncio.gather(c.client.post('/api/agent/tasks', json=other),
        c.client.post('/api/agent/tasks', json={**other, 'derived_source_scope':
                      {**c.source_scope, 'cause_node_id': 'cause-B'}}))
    assert sorted([a.status_code, b.status_code]) == [201, 409], (a.text, b.text)
    assert waiters[key][0] == waiters[other_key][0] == 2
    async with c.session() as db:
        row = await db.get(AgentTaskSourceRequest, task_id)
        assert row is not None and row.fingerprint_format == 'd4-source-request.v1'
        assert row.request_fingerprint == original_fingerprint
        assert await db.scalar(select(func.count()).select_from(AgentTaskGrant).where(AgentTaskGrant.task_id == task_id)) == 0
        assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == task_id)) == 0
        from app.models.agent_task import AgentTask
        winner = await db.scalar(select(AgentTask).where(AgentTask.request_key == other_key))
        assert winner is not None and winner.status == 'blocked_capability'
        assert await db.get(AgentTaskSourceRequest, winner.task_id) is not None
        assert await db.scalar(select(func.count()).select_from(AgentTaskSourceRequest).where(
            AgentTaskSourceRequest.task_id == winner.task_id)) == 1
        assert await db.scalar(select(func.count()).select_from(AgentTaskGrant).where(AgentTaskGrant.task_id == winner.task_id)) == 0
        assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == winner.task_id)) == 0
    enabled = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}',
                                  json={'enabled': True})
    assert enabled.status_code == 200, enabled.text
    replay = await c.client.post('/api/agent/tasks', json=body)
    assert replay.status_code == 201 and replay.json()['task_id'] == str(task_id)
    assert replay.json()['status'] == 'blocked_capability'
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentTaskGrant).where(AgentTaskGrant.task_id == task_id)) == 0
        assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.task_id == task_id)) == 0


@pytest.mark.asyncio
async def test_text_budget_and_response_faults_fail_closed(text_fault_server):
    from tests.services.agent_runtime.test_d4_text_delivery import (
        test_bad_or_oversized_current_field_never_releases_or_commits,
        test_real_redaction_expansion_exceeds_fixed_response_budget_without_receipt,
    )
    c = text_fault_server
    await test_bad_or_oversized_current_field_never_releases_or_commits(c, 'x' * (64 * 1024 + 1))
    await test_real_redaction_expansion_exceeds_fixed_response_budget_without_receipt(c)
    restored = await c.admin.put(f'/api/capa/{c.report_id}', json={'d4_root_cause': 'synthetic candidate'})
    assert restored.status_code == 200, restored.text
    proof = await c.admin.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
        'root_cause_text': 'synthetic candidate', 'method': 'measurement', 'conclusion': 'passed',
        'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-A'},
        'source_declaration': {'declares_complete_coverage': True}})
    assert proof.status_code == 200 and proof.json()['source_proof_issued'] is True, proof.text
    before = await business_snapshot(c)
    for fault in ('bad-json', 'utf8', 'oversize', 'label', 'binding', 'slow'):
        c.text_fault = fault
        created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
            'installation_id': str(c.text_id), 'request_key': uuid4().hex,
            'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
        assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
        start = len(c.fault_calls)
        code, result, stderr = await _run_receiver(c, request_key=uuid4().hex)
        assert code != 0 and result['status'] == 'unconfirmed', (fault, result, stderr)
        assert 'synthetic candidate' not in json.dumps(result) + stderr
        paths = [path for _, path, _ in c.fault_calls[start:]]
        assert paths.count('/api/agent/runtime/capa/d4/root-cause-text') == 1
        assert '/api/agent/runtime/messages/ack' not in paths and '/api/agent/runtime/finish' not in paths
    assert await business_snapshot(c) == before


@pytest.mark.asyncio
async def test_text_finish_commit_without_confirmation_is_unknown(text_fault_server):
    c = text_fault_server
    before = await business_snapshot(c)
    for fault in ('finish-bad-json', 'finish-oversize', 'finish-disconnect'):
        created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
            'installation_id': str(c.text_id), 'request_key': uuid4().hex,
            'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
        assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
        task_id = UUID(created.json()['task_id'])
        c.text_fault = fault
        start = len(c.fault_calls)
        code, result, stderr = await _run_receiver(c, request_key=uuid4().hex)
        assert code != 0 and result['status'] == 'unknown' and 'synthetic candidate' not in stderr
        assert [path for _, path, _ in c.fault_calls[start:]].count('/api/agent/runtime/finish') == 1
        async with c.session() as db:
            run = await db.scalar(select(AgentRun).where(AgentRun.task_id == task_id))
            assert run.status == 'completed'
            assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt).where(
                AgentRestrictedProjectionReceipt.run_id == run.run_id)) == 1
    assert await business_snapshot(c) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('denial', ['no-view', 'outside-line'])
async def test_declaration_denials_hide_node_existence(d4_text_server, denial):
    from app.models.audit import AuditLog
    from app.models.capa import CapaRootCauseVerification
    from app.models.capa_d4_delivery import CapaD4RootCauseRevision, CapaD4RootCauseSourceProof
    from app.models.fmea import FMEADocument
    from app.models.product_line import ProductLine
    from app.models.role import RoleDefinition, RolePermission
    from sqlalchemy import event, update
    c = d4_text_server
    async with c.session() as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
            RolePermission.module == 'capa').values(permission_level=3))
        await db.commit()
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={
            'X-Tenant-ID': c.slug, 'Authorization': 'Bearer ' + c.user_token}, timeout=15) as client:
        baseline = await client.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
            'root_cause_text': 'synthetic candidate', 'method': 'measurement', 'conclusion': 'passed',
            'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-A'},
            'source_declaration': {'declares_complete_coverage': True}})
        assert baseline.status_code == 200 and baseline.json()['source_proof_issued'] is True, baseline.text
    async with c.session() as db:
        if denial == 'no-view':
            await db.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                RolePermission.module == 'fmea').values(permission_level=0))
        else:
            role = await db.get(RoleDefinition, c.role_id)
            role.bypass_row_level_security = False
            await db.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                RolePermission.module == 'group').values(permission_level=0))
            line = ProductLine(code='HIDDEN-' + uuid4().hex[:8], name='hidden', factory_id=c.factory_id)
            db.add(line)
            await db.flush()
            doc = await db.get(FMEADocument, c.fmea_id)
            doc.product_line_code = line.code
        await db.commit()
    async def counts():
        async with c.session() as db:
            return tuple([await db.scalar(select(func.count()).select_from(model)) for model in
                          (CapaRootCauseVerification, CapaD4RootCauseRevision, CapaD4RootCauseSourceProof, AuditLog)])
    before = await counts()
    statements = []
    def watch(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(c.engine.sync_engine, 'before_cursor_execute', watch)
    try:
        async with httpx.AsyncClient(base_url=c.text_base_url, headers={
                'X-Tenant-ID': c.slug, 'Authorization': 'Bearer ' + c.user_token}, timeout=15) as client:
            responses = []
            for node in ('cause-A', 'fictional-node'):
                responses.append(await client.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
                    'root_cause_text': 'synthetic candidate', 'method': 'measurement', 'conclusion': 'passed',
                    'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': node},
                    'source_declaration': {'declares_complete_coverage': True}}))
    finally:
        event.remove(c.engine.sync_engine, 'before_cursor_execute', watch)
    assert [r.status_code for r in responses] == [403, 403]
    assert responses[0].content == responses[1].content == b'{"detail":"Source unavailable"}'
    assert not any('jsonb_array_elements' in statement for statement in statements)
    assert await counts() == before


@pytest.mark.asyncio
async def test_revision_and_verification_changes_fence_old_proofs(d4_text_server):
    from app.models.capa import CapaRootCauseVerification
    from app.models.capa_d4_delivery import CapaD4RootCauseSourceProof
    from sqlalchemy import update
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as runtime:
        claim = await runtime.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        headers = {'Authorization': 'Bearer ' + claim.json()['token']}
        assert (await runtime.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)).status_code == 200
        for value in ('synthetic alternate', 'synthetic candidate'):
            changed = await c.admin.put(f'/api/capa/{c.report_id}', json={'d4_root_cause': value})
            assert changed.status_code == 200, changed.text
        denied = await runtime.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
        assert denied.status_code in (401, 403) and 'synthetic candidate' not in denied.text
        issue = {'root_cause_text': 'synthetic candidate', 'method': 'measurement', 'conclusion': 'passed',
                 'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-A'},
                 'source_declaration': {'declares_complete_coverage': True}}
        proof = await c.admin.post(f'/api/capa/{c.report_id}/root-cause-verifications', json=issue)
        assert proof.status_code == 200 and proof.json()['source_proof_issued'] is True, proof.text
        vid = UUID(proof.json()['verification_id'])
        async with c.session() as db:
            v = await db.get(CapaRootCauseVerification, vid)
            original_time = v.updated_at
            active = await db.scalar(select(CapaD4RootCauseSourceProof).where(
                CapaD4RootCauseSourceProof.verification_id == vid))
            assert active is not None and active.invalidated_at is None
        assert (await runtime.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)).status_code == 200
        for patch in ({'conclusion': 'failed'}, {'conclusion': 'passed'},
                      {'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-B'}},
                      {'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-A'}}):
            changed = await c.admin.patch(f'/api/capa/{c.report_id}/root-cause-verifications/{vid}', json=patch)
            assert changed.status_code == 200, changed.text
            async with c.session() as db:
                await db.execute(update(CapaRootCauseVerification).where(
                    CapaRootCauseVerification.verification_id == vid).values(updated_at=original_time))
                await db.commit()
        denied = await runtime.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
        assert denied.status_code in (401, 403) and 'synthetic candidate' not in denied.text
        replacement = await c.admin.post(f'/api/capa/{c.report_id}/root-cause-verifications', json=issue)
        assert replacement.status_code == 200 and replacement.json()['source_proof_issued'] is True, replacement.text
        async with c.session() as db:
            old = await db.scalar(select(CapaD4RootCauseSourceProof).where(
                CapaD4RootCauseSourceProof.verification_id == vid))
            assert old.invalidated_at is not None and old.status == 'superseded'


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['cross-tenant', 'generation', 'fmea-acl', 'role', 'source-factory',
                                 'source-line', 'paused-epoch', 'policy', 'permanent'])
async def test_text_current_authority_and_tenant_boundaries(d4_text_server, monkeypatch, case):
    from tests.services.agent_runtime.test_d4_text_delivery import (
        test_same_report_uuid_in_another_owned_tenant_never_accepts_run_token,
        test_real_http_release_serializes_with_tenant_maintenance_generation,
    )
    from tests.services.agent_runtime.test_d4_recovery_restart import test_restart_refusal_or_fault_leaves_original_position
    if case == 'cross-tenant':
        before = await business_snapshot(d4_text_server)
        await test_same_report_uuid_in_another_owned_tenant_never_accepts_run_token(d4_text_server)
        assert await business_snapshot(d4_text_server) == before
    elif case == 'generation':
        from app.core.tenant_transaction import TenantUnavailable
        from app.services import tenant_migrator
        from app.services.agent_runtime import d4_text_delivery
        from types import SimpleNamespace
        from app.core.tenant_transaction import TenantBinding
        from sqlalchemy import text
        c = d4_text_server
        created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
            'installation_id': str(c.text_id), 'request_key': uuid4().hex,
            'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
        assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
        before = await business_snapshot(c)
        original = d4_text_delivery.build_root_candidate
        blocked = []
        async def attempt_maintenance(**kwargs):
            snapshot = await original(**kwargs)
            try:
                async with tenant_migrator.maintenance_connection(c.engine, c.binding.tenant_id):
                    raise AssertionError('maintenance acquired during active release')
            except TenantUnavailable:
                blocked.append(True)
            return snapshot
        monkeypatch.setattr(d4_text_delivery, 'build_root_candidate', attempt_maintenance)
        async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as runtime:
            claim = await runtime.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
                'secret': c.text_secret, 'request_key': uuid4().hex})
            assert claim.status_code == 200, claim.text
            headers = {'Authorization': 'Bearer ' + claim.json()['token']}
            released = await runtime.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
            assert released.status_code == 200 and blocked == [True], released.text
            async with tenant_migrator.maintenance_connection(c.engine, c.binding.tenant_id) as maintenance:
                denied = await runtime.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
                assert denied.status_code in (401, 403, 404, 503) and 'synthetic candidate' not in denied.text
                await tenant_migrator.mark_active(maintenance, maintenance.attempt)
            denied = await runtime.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
            assert denied.status_code in (401, 403, 404, 503) and 'synthetic candidate' not in denied.text
        async with c.engine.connect() as conn:
            current = (await conn.execute(text('SELECT id, schema_name, generation, status FROM public.tenants WHERE id=:id'),
                                          {'id': c.binding.tenant_id})).one()
        assert current.id == c.binding.tenant_id and current.schema_name == c.binding.schema_name
        assert current.generation == c.binding.generation + 1 and current.status == 'active'
        binding = TenantBinding(current.id, current.schema_name, current.generation, 'business')
        owned = SimpleNamespace(session=lambda: c.factory(binding=binding))
        assert await business_snapshot(owned) == before
    elif case == 'policy':
        before = await business_snapshot(d4_text_server)
        await test_restart_refusal_or_fault_leaves_original_position(d4_text_server, monkeypatch, 'policy')
        assert await business_snapshot(d4_text_server) == before
    else:
        from app.models.factory import Factory
        from app.models.fmea import FMEADocument
        from app.models.product_line import ProductLine
        from app.models.role import RolePermission
        from sqlalchemy import update
        c = d4_text_server
        created = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
            'installation_id': str(c.text_id), 'request_key': uuid4().hex,
            'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
        assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
        async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as runtime:
            claim = await runtime.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
                'secret': c.text_secret, 'request_key': uuid4().hex})
            assert claim.status_code == 200, claim.text
            headers = {'Authorization': 'Bearer ' + claim.json()['token']}
            assert (await runtime.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)).status_code == 200
            if case == 'permanent':
                revoked = await c.admin.post(f'/api/admin/agent-plugins/{c.text_id}/revoke-local-trial',
                                             json={'expected_credential_epoch': 0})
                assert revoked.status_code == 200 and revoked.json()['outcome'] == 'revoked', revoked.text
            elif case == 'paused-epoch':
                paused = await runtime.post(f'/api/agent/tasks/{created.json()["task_id"]}/control',
                    headers={'Authorization': 'Bearer ' + c.user_token}, json={'action': 'pause',
                    'run_id': claim.json()['run_id'], 'expected_epoch': claim.json()['lease_epoch'],
                    'idempotency_key': uuid4().hex})
                assert paused.status_code == 200 and paused.json()['lease_epoch'] > claim.json()['lease_epoch']
            else:
                async with c.session() as db:
                    if case in ('fmea-acl', 'role'):
                        await db.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                            RolePermission.module == ('fmea' if case == 'fmea-acl' else 'capa')).values(permission_level=0))
                    else:
                        doc = await db.get(FMEADocument, c.fmea_id)
                        if case == 'source-factory':
                            factory = Factory(code='T10-' + uuid4().hex[:8], name='other factory')
                            db.add(factory)
                            await db.flush()
                            doc.factory_id = factory.id
                        else:
                            line = ProductLine(code='T10-' + uuid4().hex[:8], name='other line', factory_id=c.factory_id)
                            db.add(line)
                            await db.flush()
                            doc.product_line_code = line.code
                    await db.commit()
            before = await business_snapshot(c)
            denied = await runtime.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
            assert denied.status_code in (401, 403) and 'synthetic candidate' not in denied.text
            assert await business_snapshot(c) == before
            if case == 'permanent':
                denied_claim = await runtime.post('/api/agent/runtime/claim', json={
                    'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
                assert denied_claim.status_code in (401, 403), denied_claim.text


@pytest.mark.asyncio
async def test_metadata_sdk_and_worker_contracts_remain_unchanged(sdk_child):
    import hashlib
    from tests.e2e.test_agent_sdk_process import test_sdk_ten_operations_sources_idempotency_and_terminal_fence
    worker = Path(__file__).resolve().parents[2] / 'examples/readonly_8d_plugin.py'
    assert hashlib.sha256(worker.read_bytes()).hexdigest() == 'ab4645b4a57a55f2d17117fad64bf1aabac8a450e34f445c8a718449b039ed54'
    await test_sdk_ten_operations_sources_idempotency_and_terminal_fence(sdk_child)
