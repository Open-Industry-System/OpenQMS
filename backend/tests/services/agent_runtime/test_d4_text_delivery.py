"""Restricted D4 delivery through the normal, source-bound runtime."""
import asyncio
import json
import logging
from pathlib import Path
import socket
import sys
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
import uvicorn
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import DBAPIError

from app.models.capa_d4_delivery import AgentRestrictedProjectionReceipt, CapaD4RootCauseSourceProof
from app.models.capa import CAPAEightD, CapaRootCauseVerification
from app.models.agent_derived_source import AgentTaskDerivedSourceScope
from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.services.agent_runtime.message_delivery_policy import START_MESSAGE
from tests.e2e.d4_text_local_harness import d4_text_local_trial, d4_text_server, owned_local_trial

pytestmark = pytest.mark.requires_db


@pytest_asyncio.fixture
async def d4_logged_server(d4_text_local_trial):
    owned = d4_text_local_trial
    records = []
    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)
    handler = Capture()
    access_logger = logging.getLogger('uvicorn.access')
    old_level = access_logger.level
    old_disabled = access_logger.disabled
    access_logger.disabled = False
    access_logger.setLevel(logging.INFO)
    access_logger.addHandler(handler)
    owned.access_records = records
    assert access_logger.isEnabledFor(logging.INFO), (access_logger.disabled, access_logger.level,
                                                     logging.root.manager.disable)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(owned.app, log_config=None, log_level='info',
                                          access_log=True, lifespan='off', proxy_headers=False))
    runner = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(300):
            if server.started:
                break
            if runner.done():
                await runner
            await asyncio.sleep(.01)
        assert server.started
        owned.text_base_url = f'http://127.0.0.1:{sock.getsockname()[1]}'
        yield owned
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(runner, 10)
        finally:
            sock.close()
            access_logger.removeHandler(handler)
            access_logger.setLevel(old_level)
            access_logger.disabled = old_disabled


@pytest.mark.asyncio
async def test_authorized_runtime_delivers_restricted_candidate_and_commits_receipt(d4_text_server):
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={
        'report_id': str(c.report_id), 'installation_id': str(c.text_id),
        'request_key': uuid4().hex, 'initial_text': START_MESSAGE,
        'derived_source_scope': c.source_scope,
    })
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex,
        })
        assert claim.status_code == 200, claim.text
        result = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
            headers={'Authorization': 'Bearer ' + claim.json()['token']})
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'no-store'
    payload = result.json()
    assert payload['text'] == 'synthetic candidate'
    assert payload['report_id'] == str(c.report_id)
    assert payload['run_id'] == claim.json()['run_id']
    assert payload['data_class'] == 'restricted'
    assert payload['model_delivery_allowed'] is False
    async with c.session() as db:
        receipt = await db.get(AgentRestrictedProjectionReceipt, UUID(payload['receipt_id']))
        assert receipt is not None and str(receipt.run_id) == claim.json()['run_id']
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['root', 'grant'])
async def test_release_rechecks_after_snapshot_and_does_not_persist_on_change(d4_text_server, monkeypatch, change):
    from app.services.agent_runtime import d4_text_delivery
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={
        'report_id': str(c.report_id), 'installation_id': str(c.text_id),
        'request_key': uuid4().hex, 'initial_text': START_MESSAGE,
        'derived_source_scope': c.source_scope,
    })
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    original = d4_text_delivery.build_root_candidate
    async def mutate_after_snapshot(**kwargs):
        snapshot = await original(**kwargs)
        if change == 'root':
            response = await c.admin.put(f'/api/capa/{c.report_id}', json={'d4_root_cause': 'new root'})
        else:
            response = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}',
                                           json={'enabled': False})
        assert response.status_code == 200, response.text
        return snapshot
    monkeypatch.setattr(d4_text_delivery, 'build_root_candidate', mutate_after_snapshot)
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex,
        })
        assert claim.status_code == 200, claim.text
        result = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
            headers={'Authorization': 'Bearer ' + claim.json()['token']})
    assert result.status_code in (401, 403), result.text
    assert 'synthetic candidate' not in result.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED')) == 0


@pytest.mark.asyncio
async def test_restart_fixed_receiver_reads_new_fact_and_creates_fresh_receipt(d4_text_server, monkeypatch):
    from app.services.agent_runtime import d4_text_delivery
    c = d4_text_server
    created = await c.client.post('/api/agent/tasks', json={
        'report_id': str(c.report_id), 'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert created.status_code == 201 and created.json()['status'] == 'ready', created.text
    task_id = created.json()['task_id']
    user_headers = {'Authorization': 'Bearer ' + c.user_token, 'X-Tenant-ID': c.slug}
    observed = []
    original = d4_text_delivery.encode_bounded_release
    def witness(identity, snapshot, *, limit):
        observed.append((identity.run.run_id, snapshot.text, snapshot.source_version))
        return original(identity, snapshot, limit=limit)
    monkeypatch.setattr(d4_text_delivery, 'encode_bounded_release', witness)
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claimed = await client.post('/api/agent/runtime/claim', json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claimed.status_code == 200, claimed.text
        old = claimed.json()
        old_headers = {'Authorization': 'Bearer ' + old['token']}
        first = await client.get('/api/agent/runtime/capa/d4/root-cause-text', headers=old_headers)
        assert first.status_code == 200 and first.json()['text'] == 'synthetic candidate', first.text
        old_receipt = first.json()['receipt_id']
        pause = await client.post(f'/api/agent/tasks/{task_id}/control', headers=user_headers, json={
            'action': 'pause', 'run_id': old['run_id'], 'expected_epoch': old['lease_epoch'],
            'idempotency_key': uuid4().hex})
        assert pause.status_code == 200, pause.text
        checkpoint = await client.post(f'/api/agent/tasks/{task_id}/d4-recovery-checkpoints',
            headers=user_headers, json={'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch']})
        assert checkpoint.status_code == 200, checkpoint.text
        changed = await c.admin.put(f'/api/capa/{c.report_id}', json={'d4_root_cause': 'fresh current candidate'})
        assert changed.status_code == 200, changed.text
        proof = await c.admin.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
            'root_cause_text': 'fresh current candidate', 'method': 'measurement', 'conclusion': 'passed',
            'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-A'},
            'source_declaration': {'declares_complete_coverage': True}})
        assert proof.status_code == 200 and proof.json()['source_proof_issued'] is True, proof.text
        restart = await client.post(f'/api/agent/tasks/{task_id}/control', headers=user_headers, json={
            'action': 'restart', 'run_id': old['run_id'], 'expected_epoch': pause.json()['lease_epoch'],
            'checkpoint_id': checkpoint.json()['checkpoint_id'], 'idempotency_key': uuid4().hex})
        assert restart.status_code == 200, restart.text
        new_run_id = restart.json()['run_id']
        assert new_run_id != old['run_id']
        assert (await client.get('/api/agent/runtime/capa/d4/root-cause-text', headers=old_headers)).status_code == 401
        request_key = uuid4().hex
        new_claim = await client.post('/api/agent/runtime/claim', json={
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': request_key})
        assert new_claim.status_code == 200 and new_claim.json()['run_id'] == new_run_id, new_claim.text
        new_headers = {'Authorization': 'Bearer ' + new_claim.json()['token']}
        old_event = await client.post('/api/agent/runtime/events', headers=new_headers, json={
            'event_type': 'query_completed', 'idempotency_key': uuid4().hex,
            'payload': {}, 'receipt_ids': [old_receipt]})
        assert old_event.status_code in (401, 403), old_event.text
        old_checkpoint = await client.post('/api/agent/runtime/checkpoints', headers=new_headers, json={
            'idempotency_key': uuid4().hex, 'receipt_ids': [old_receipt]})
        assert old_checkpoint.status_code in (401, 403), old_checkpoint.text
        old_result = await client.post('/api/agent/runtime/results', headers=new_headers, json={
            'idempotency_key': uuid4().hex, 'receipt_ids': [old_receipt], 'payload': {}})
        assert old_result.status_code in (401, 403), old_result.text
        worker = Path(__file__).resolve().parents[3] / 'examples' / 'readonly_d4_text_receiver.py'
        process = await asyncio.create_subprocess_exec(sys.executable, str(worker),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        configuration = {'origin': c.text_base_url, 'tenant_slug': c.slug,
            'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': request_key,
            'expected_report_id': str(c.report_id)}
        stdout, stderr = await asyncio.wait_for(process.communicate(json.dumps(configuration).encode()), timeout=60)
        assert process.returncode == 0, stderr.decode()
        result = json.loads(stdout)
        assert result['status'] == 'completed' and result['receipt_id'] != old_receipt
        assert [(row[0], row[1]) for row in observed] == [(UUID(old['run_id']), 'synthetic candidate'),
                                                          (UUID(new_run_id), 'fresh current candidate')]
        assert observed[0][2] != observed[1][2]
        async with c.session() as db:
            from app.services.agent_runtime.readonly_delivery import _sources
            old_row = await db.get(AgentRestrictedProjectionReceipt, UUID(old_receipt))
            new_row = await db.get(AgentRestrictedProjectionReceipt, UUID(result['receipt_id']))
            assert old_row is not None and str(old_row.run_id) == old['run_id']
            assert new_row is not None and str(new_row.run_id) == new_run_id
            assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 2
            with pytest.raises(PermissionError):
                await _sources(db, [UUID(old_receipt)], UUID(task_id), UUID(old['run_id']),
                               c.report_id, c.binding.generation, old['lease_epoch'])


@pytest.mark.asyncio
async def test_new_proof_outside_original_scopes_denied_before_root_or_node_read(d4_text_server):
    c = d4_text_server
    async with c.session() as db:
        doc = await db.get(FMEADocument, c.fmea_id)
        doc.graph_data = {'nodes': [{'id': 'cause-A', 'type': 'FailureCause'},
                                    {'id': 'cause-B', 'type': 'FailureCause'}], 'edges': []}
        await db.commit()
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        proof = await c.admin.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
            'root_cause_text': 'synthetic candidate', 'method': 'measurement', 'conclusion': 'passed',
            'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-B'},
            'source_declaration': {'declares_complete_coverage': True}})
        assert proof.status_code == 200 and proof.json()['source_proof_issued'] is True, proof.text
        statements = []
        def witness(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            denied = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
                headers={'Authorization': 'Bearer ' + claim.json()['token']})
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
    assert denied.status_code in (401, 403), denied.text
    assert 'synthetic candidate' not in denied.text
    assert not any('capa_eightd.d4_root_cause' in s or 'jsonb_array_elements' in s for s in statements)
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['x' * (64 * 1024 + 1), '', None], ids=['over-budget', 'empty', 'null'])
async def test_bad_or_oversized_current_field_never_releases_or_commits(d4_text_server, value):
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        async with c.session() as db:
            await db.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report_id).values(d4_root_cause=value))
            await db.commit()
        statements = []
        def witness(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            response = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
                headers={'Authorization': 'Bearer ' + claim.json()['token']})
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
    assert response.status_code in (401, 403), response.text
    assert 'synthetic candidate' not in response.text
    if value is not None and len(value) > 64 * 1024:
        assert not any(s.lstrip().startswith('select capa_eightd.d4_root_cause') for s in statements)
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED')) == 0


@pytest.mark.asyncio
async def test_receipt_constraint_failure_rolls_back_audit_and_never_returns_body(d4_text_server, monkeypatch):
    from app.services.agent_runtime import d4_text_delivery
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    original = d4_text_delivery.add_restricted_receipt_and_audit
    def violate_constraint(db, identity, latest, release):
        original(db, identity, latest, release)
        db.add(AgentRestrictedProjectionReceipt(receipt_id=uuid4()))
    monkeypatch.setattr(d4_text_delivery, 'add_restricted_receipt_and_audit', violate_constraint)
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        response = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
            headers={'Authorization': 'Bearer ' + claim.json()['token']})
    assert response.status_code == 503 and response.json() == {'detail': 'Delivery unavailable'}
    assert 'synthetic candidate' not in response.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED')) == 0


@pytest.mark.asyncio
async def test_source_node_writer_waits_for_release_commit(d4_text_server, monkeypatch):
    from app.services.agent_runtime import d4_text_delivery
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    original = d4_text_delivery.failure_cause_version
    timed_out = []
    async def mutate_with_timeout():
        async with c.session() as db:
            await db.execute(text("SET LOCAL lock_timeout = '200ms'"))
            try:
                await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == c.fmea_id).values(
                    graph_data={'nodes': [{'id': 'cause-A', 'type': 'FailureCause', 'name': 'changed'}], 'edges': []}))
                await db.commit()
            except DBAPIError as exc:
                timed_out.append(getattr(exc.orig, 'sqlstate', None) == '55P03')
    async def change_after_check(*args, **kwargs):
        digest = await original(*args, **kwargs)
        await asyncio.wait_for(mutate_with_timeout(), timeout=5)
        assert timed_out == [True]
        return digest
    monkeypatch.setattr(d4_text_delivery, 'failure_cause_version', change_after_check)
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        response = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
            headers={'Authorization': 'Bearer ' + claim.json()['token']})
    assert response.status_code == 200 and response.json()['text'] == 'synthetic candidate', response.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 1
        await db.execute(update(FMEADocument).where(FMEADocument.fmea_id == c.fmea_id).values(
            graph_data={'nodes': [{'id': 'cause-A', 'type': 'FailureCause', 'name': 'changed'}], 'edges': []}))
        await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['proof', 'verification', 'source_node', 'task_scope', 'capa_acl', 'fmea_acl'])
async def test_source_and_proof_changes_after_read_are_fenced(d4_text_server, monkeypatch, change):
    from datetime import UTC, datetime
    from app.services.agent_runtime import d4_text_delivery
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    task_id = UUID(task.json()['task_id'])
    original = d4_text_delivery.build_root_candidate
    async def mutate_after_snapshot(**kwargs):
        snapshot = await original(**kwargs)
        async with c.session() as db:
            if change == 'proof':
                await db.execute(update(CapaD4RootCauseSourceProof).where(
                    CapaD4RootCauseSourceProof.report_id == c.report_id).values(invalidated_at=datetime.now(UTC)))
            elif change == 'verification':
                await db.execute(update(CapaRootCauseVerification).where(
                    CapaRootCauseVerification.capa_id == c.report_id).values(root_cause_text='changed'))
            elif change == 'source_node':
                doc = await db.get(FMEADocument, c.fmea_id)
                doc.graph_data = {'nodes': [{'id': 'cause-A', 'type': 'FailureCause', 'name': 'changed'}], 'edges': []}
            elif change == 'task_scope':
                from app.models.agent_task import AgentTaskGrant
                grants = select(AgentTaskGrant.grant_id).where(AgentTaskGrant.task_id == task_id)
                await db.execute(update(AgentTaskDerivedSourceScope).where(
                    AgentTaskDerivedSourceScope.task_grant_id.in_(grants)).values(cause_node_id='cause-B'))
            else:
                from app.models.role import RolePermission
                await db.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                    RolePermission.module == change.removesuffix('_acl')).values(permission_level=0))
            await db.commit()
        return snapshot
    monkeypatch.setattr(d4_text_delivery, 'build_root_candidate', mutate_after_snapshot)
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        response = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
            headers={'Authorization': 'Bearer ' + claim.json()['token']})
    assert response.status_code in (401, 403), response.text
    assert 'synthetic candidate' not in response.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED')) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['grant', 'proof', 'coordinates'])
async def test_final_check_after_encoding_rejects_concurrent_changes(d4_text_server, monkeypatch, change):
    from datetime import UTC, datetime
    from app.services.agent_runtime import d4_text_delivery
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    original = d4_text_delivery.runtime_access.lock_runtime_identity
    async def change_after_encoding(db, identity):
        if change == 'grant':
            result = await c.admin.patch(f'/api/admin/agent-plugins/{c.text_id}/grants/{c.text_grant_id}',
                                         json={'enabled': False})
            assert result.status_code == 200, result.text
        else:
            async with c.session() as other:
                if change == 'proof':
                    await other.execute(update(CapaD4RootCauseSourceProof).where(
                        CapaD4RootCauseSourceProof.report_id == c.report_id).values(invalidated_at=datetime.now(UTC)))
                else:
                    await other.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report_id)
                                        .values(product_line_code='changed-line'))
                await other.commit()
        return await original(db, identity)
    monkeypatch.setattr(d4_text_delivery.runtime_access, 'lock_runtime_identity', change_after_encoding)
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        response = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
            headers={'Authorization': 'Bearer ' + claim.json()['token']})
    assert response.status_code in (401, 403), response.text
    assert 'synthetic candidate' not in response.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED')) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('revocation', ['user', 'fmea_permission', 'factory_delete', 'line_delete',
                                       'parent_grant', 'task_scope', 'factory_insert',
                                       'role_insert', 'plugin_grant_insert', 'task_grant_insert'])
async def test_final_authority_revocation_serializes_with_release(d4_text_server, monkeypatch, revocation):
    from sqlalchemy import delete
    from app.models.agent_plugin import AgentPluginGrant
    from app.models.agent_task import AgentTaskGrant
    from app.models.factory import Factory, UserFactory
    from app.models.role import RolePermission, UserProductLine
    from app.models.user import User
    from app.services.agent_runtime import d4_text_delivery
    c = d4_text_server
    other_factory_id = uuid4()
    if revocation in {'factory_delete', 'factory_insert'}:
        async with c.session() as db:
            if revocation == 'factory_delete':
                await db.execute(update(User).where(User.user_id == c.user_id).values(factory_id=None))
            else:
                await db.execute(delete(UserFactory).where(UserFactory.user_id == c.user_id))
                db.add(Factory(id=other_factory_id, code='D4-' + uuid4().hex[:12], name='D4 isolation factory'))
            await db.commit()
    elif revocation == 'role_insert':
        async with c.session() as db:
            await db.execute(delete(RolePermission).where(RolePermission.role_id == c.role_id,
                                                           RolePermission.module == 'group'))
            await db.commit()
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    task_id = UUID(task.json()['task_id'])
    original = d4_text_delivery.require_current_text_authority
    calls, conflicts = 0, []
    async def mutate(db):
        if revocation == 'user':
            await db.execute(update(User).where(User.user_id == c.user_id).values(is_active=False))
        elif revocation == 'fmea_permission':
            await db.execute(delete(RolePermission).where(RolePermission.role_id == c.role_id,
                RolePermission.module == 'fmea'))
        elif revocation == 'factory_delete':
            await db.execute(delete(UserFactory).where(UserFactory.user_id == c.user_id,
                UserFactory.factory_id == c.factory_id))
        elif revocation == 'line_delete':
            await db.execute(delete(UserProductLine).where(UserProductLine.user_id == c.user_id,
                UserProductLine.product_line_code == c.line))
        elif revocation == 'parent_grant':
            await db.execute(update(AgentPluginGrant).where(AgentPluginGrant.grant_id == c.text_grant_id)
                             .values(enabled=False))
        elif revocation == 'task_scope':
            grants = select(AgentTaskGrant.grant_id).where(AgentTaskGrant.task_id == task_id)
            await db.execute(update(AgentTaskDerivedSourceScope).where(
                AgentTaskDerivedSourceScope.task_grant_id.in_(grants)).values(cause_node_id='cause-B'))
        elif revocation == 'factory_insert':
            db.add(UserFactory(user_id=c.user_id, factory_id=other_factory_id))
            await db.flush()
        elif revocation == 'role_insert':
            db.add(RolePermission(role_id=c.role_id, module='group', permission_level=0))
            await db.flush()
        elif revocation == 'plugin_grant_insert':
            db.add(AgentPluginGrant(grant_id=uuid4(), installation_id=c.text_id,
                capability_id='capa.d4.summary.masked.v1', factory_ids=[str(c.factory_id)],
                enabled=False, granted_by=c.admin_user_id))
            await db.flush()
        else:
            db.add(AgentTaskGrant(grant_id=uuid4(), task_id=task_id,
                capability_id='capa.d4.summary.masked.v1', factory_ids=[str(c.factory_id)], access_kind='read'))
            await db.flush()
    async def attempt_revocation():
        async with c.session() as db:
            await db.execute(text("SET LOCAL lock_timeout = '200ms'"))
            try:
                await mutate(db)
                await db.commit()
            except DBAPIError as exc:
                conflicts.append(getattr(exc.orig, 'sqlstate', None))
    async def revoke_after_last_check(*args, **kwargs):
        nonlocal calls
        await original(*args, **kwargs)
        calls += 1
        if calls == 3:
            await asyncio.wait_for(attempt_revocation(), timeout=5)
            assert conflicts == ['55P03']
    monkeypatch.setattr(d4_text_delivery, 'require_current_text_authority', revoke_after_last_check)
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        headers = {'Authorization': 'Bearer ' + claim.json()['token']}
        response = await client.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
        assert calls == 3 and response.status_code == 200, response.text
        async with c.session() as db:
            await mutate(db)
            await db.commit()
        denied = await client.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
        unchanged = revocation in {'role_insert', 'plugin_grant_insert', 'task_grant_insert'}
        if unchanged:
            assert denied.status_code == 200, denied.text
        else:
            assert denied.status_code in (401, 403), denied.text
            assert 'synthetic candidate' not in denied.text
    async with c.session() as db:
        expected = 2 if unchanged else 1
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == expected
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED')) == expected


@pytest.mark.asyncio
async def test_factory_assignment_replace_and_delivery_do_not_invert_locks(d4_text_server):
    from sqlalchemy import delete
    from app.models.factory import UserFactory
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    entered = asyncio.Event()
    def witness(conn, cursor, statement, parameters, context, executemany):
        query = statement.lower()
        if 'from user_factories' in query and 'for update' in query:
            entered.set()
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            async with c.session() as writer:
                await writer.execute(text("SET LOCAL lock_timeout = '500ms'"))
                await writer.execute(delete(UserFactory).where(UserFactory.user_id == c.user_id))
                pending = asyncio.create_task(client.get('/api/agent/runtime/capa/d4/root-cause-text',
                    headers={'Authorization': 'Bearer ' + claim.json()['token']}))
                await asyncio.wait_for(entered.wait(), timeout=10)
                writer.add(UserFactory(user_id=c.user_id, factory_id=c.factory_id))
                try:
                    await writer.commit()
                    writer_error = None
                except DBAPIError as exc:
                    writer_error = getattr(exc.orig, 'sqlstate', None)
                    await writer.rollback()
                response = await asyncio.wait_for(pending, timeout=10)
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
    assert writer_error is None, f'factory assignment writer could not complete: {writer_error}'
    assert response.status_code in (200, 503), response.text
    if response.status_code == 503:
        assert response.json() == {'detail': 'Delivery unavailable'}
        async with c.session() as db:
            assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED')) == 0
        async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as retry:
            result = await retry.get('/api/agent/runtime/capa/d4/root-cause-text',
                                     headers={'Authorization': 'Bearer ' + claim.json()['token']})
            assert result.status_code == 200, result.text


@pytest.mark.asyncio
async def test_capa_writer_audit_and_delivery_do_not_invert_locks(d4_text_server):
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    entered = asyncio.Event()
    def witness(conn, cursor, statement, parameters, context, executemany):
        query = statement.lower()
        if 'from capa_eightd' in query and 'for update' in query:
            entered.set()
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            async with c.session() as writer:
                await writer.execute(text("SET LOCAL lock_timeout = '500ms'"))
                await writer.execute(update(CAPAEightD).where(CAPAEightD.report_id == c.report_id)
                                     .values(status=CAPAEightD.status))
                pending = asyncio.create_task(client.get('/api/agent/runtime/capa/d4/root-cause-text',
                    headers={'Authorization': 'Bearer ' + claim.json()['token']}))
                await asyncio.wait_for(entered.wait(), timeout=10)
                writer.add(AuditLog(table_name='capa_eightd', record_id=c.report_id, action='UPDATE',
                    operated_by=c.user_id, factory_id=c.factory_id, changed_fields={}))
                try:
                    await writer.commit()
                    writer_error = None
                except DBAPIError as exc:
                    writer_error = getattr(exc.orig, 'sqlstate', None)
                    await writer.rollback()
                response = await asyncio.wait_for(pending, timeout=10)
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
    assert writer_error is None, f'CAPA audit writer could not complete: {writer_error}'
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_user_service_mixed_update_and_delivery_do_not_invert_locks(d4_text_server):
    from sqlalchemy.sql.dml import Delete
    from app.services.user_service import update_user
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    user_updated, continue_writer, delivery_waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    def witness(conn, cursor, statement, parameters, context, executemany):
        query = statement.lower()
        if 'from users' in query and 'for update' in query:
            delivery_waiting.set()
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            async with c.session() as writer:
                await writer.execute(text("SET LOCAL lock_timeout = '500ms'"))
                execute = writer.execute
                async def gated_execute(statement, *args, **kwargs):
                    if isinstance(statement, Delete) and statement.table.name == 'user_factories':
                        await writer.flush()  # the service's normal autoflush before the DELETE
                        user_updated.set()
                        await asyncio.wait_for(continue_writer.wait(), timeout=10)
                    return await execute(statement, *args, **kwargs)
                writer.execute = gated_execute
                async def write():
                    try:
                        await update_user(writer, c.user_id,
                            {'display_name': 'updated executor', 'factory_ids': [c.factory_id]}, c.admin_user_id)
                        await writer.commit()
                        return None
                    except DBAPIError as exc:
                        await writer.rollback()
                        return getattr(exc.orig, 'sqlstate', None)
                pending_writer = asyncio.create_task(write())
                await asyncio.wait_for(user_updated.wait(), timeout=10)
                pending_delivery = asyncio.create_task(client.get('/api/agent/runtime/capa/d4/root-cause-text',
                    headers={'Authorization': 'Bearer ' + claim.json()['token']}))
                await asyncio.wait_for(delivery_waiting.wait(), timeout=10)
                continue_writer.set()
                writer_error = await asyncio.wait_for(pending_writer, timeout=10)
                response = await asyncio.wait_for(pending_delivery, timeout=10)
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
    assert writer_error is None, f'mixed user update could not complete: {writer_error}'
    assert response.status_code == 503 and response.json() == {'detail': 'Delivery unavailable'}
    assert 'synthetic candidate' not in response.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED')) == 0
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as retry:
        result = await retry.get('/api/agent/runtime/capa/d4/root-cause-text',
                                 headers={'Authorization': 'Bearer ' + claim.json()['token']})
        assert result.status_code == 200, result.text


@pytest.mark.asyncio
async def test_role_change_while_waiting_for_acl_rows_is_rejected(d4_text_server):
    from app.models.role import RoleDefinition, RolePermission
    from app.models.user import User
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    entered = asyncio.Event()
    def witness(conn, cursor, statement, parameters, context, executemany):
        query = statement.lower()
        if 'from role_permissions' in query and 'for update' in query:
            entered.set()
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        event.listen(c.engine.sync_engine, 'before_cursor_execute', witness)
        try:
            async with c.session() as writer:
                new_role = await writer.scalar(select(RoleDefinition.id).where(RoleDefinition.id != c.role_id).limit(1))
                assert new_role is not None
                await writer.execute(update(RolePermission).where(RolePermission.role_id == c.role_id,
                    RolePermission.module == 'fmea').values(permission_level=RolePermission.permission_level))
                pending = asyncio.create_task(client.get('/api/agent/runtime/capa/d4/root-cause-text',
                    headers={'Authorization': 'Bearer ' + claim.json()['token']}))
                await asyncio.wait_for(entered.wait(), timeout=10)
                await writer.execute(update(User).where(User.user_id == c.user_id).values(role_id=new_role))
                await writer.commit()
                response = await asyncio.wait_for(pending, timeout=10)
        finally:
            event.remove(c.engine.sync_engine, 'before_cursor_execute', witness)
    assert response.status_code in (401, 403, 503), response.text
    assert 'synthetic candidate' not in response.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0


def test_final_json_budget_counts_encoded_bytes_and_hides_candidate_repr():
    from types import SimpleNamespace
    from app.services.agent.permissions.derived_sources import SourceUnavailable
    from app.services.agent_runtime.d4_text_delivery import RootCandidateSnapshot, encode_bounded_release
    from app.services.capa_d4_redaction import RULE_VERSION
    identity = SimpleNamespace(run=SimpleNamespace(run_id=uuid4()), task=SimpleNamespace(task_id=uuid4()),
        installation=SimpleNamespace(installation_id=uuid4(), plugin_version='1.0.0'))
    secret = '保密内容' * 20
    snapshot = RootCandidateSnapshot(uuid4(), uuid4(), 'LINE', uuid4(), uuid4(), 'a' * 64,
        'b' * 64, 'c' * 64, 'd' * 64, RULE_VERSION, secret)
    release = encode_bounded_release(identity, snapshot, limit=256 * 1024)
    assert secret not in repr(snapshot) and secret not in repr(release)
    assert len(release.body) > len(release.body.decode('utf-8'))
    with pytest.raises(SourceUnavailable):
        encode_bounded_release(identity, snapshot, limit=len(release.body) - 1)


@pytest.mark.asyncio
async def test_verification_uses_python_unicode_strip_not_sql_btrim(d4_text_server):
    c = d4_text_server
    root = '\u2003synthetic candidate\u2003'
    changed = await c.admin.put(f'/api/capa/{c.report_id}', json={'d4_root_cause': root})
    assert changed.status_code == 200, changed.text
    proof = await c.admin.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
        'root_cause_text': 'synthetic candidate', 'method': 'measurement', 'conclusion': 'passed',
        'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-A'},
        'source_declaration': {'declares_complete_coverage': True}})
    assert proof.status_code == 200 and proof.json()['source_proof_issued'] is True, proof.text
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        response = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
            headers={'Authorization': 'Bearer ' + claim.json()['token']})
    assert response.status_code == 200 and response.json()['text'] == root, response.text


@pytest.mark.asyncio
async def test_real_redaction_expansion_exceeds_fixed_response_budget_without_receipt(d4_text_server):
    from app.config import settings
    c = d4_text_server
    policy = Path(settings.AGENT_D4_TEXT_LOCAL_TRIAL_POLICY_FILE)
    payload = json.loads(policy.read_text())
    payload['entries'][0]['redaction_terms'] = ['x']
    policy.write_text(json.dumps(payload))
    await c.restart()
    root = 'x' * 20000  # 20 KiB before redaction; each literal expands to a multibyte marker.
    changed = await c.admin.put(f'/api/capa/{c.report_id}', json={'d4_root_cause': root})
    assert changed.status_code == 200, changed.text
    proof = await c.admin.post(f'/api/capa/{c.report_id}/root-cause-verifications', json={
        'root_cause_text': root, 'method': 'measurement', 'conclusion': 'passed',
        'source_ref': {'fmea_id': str(c.fmea_id), 'cause_node_id': 'cause-A'},
        'source_declaration': {'declares_complete_coverage': True}})
    assert proof.status_code == 200 and proof.json()['source_proof_issued'] is True, proof.text
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=30) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        response = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
            headers={'Authorization': 'Bearer ' + claim.json()['token']})
    assert response.status_code == 403 and root[:100] not in response.text
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED')) == 0


@pytest.mark.asyncio
async def test_real_worker_and_server_error_hide_synthetic_body_and_exception(d4_logged_server, monkeypatch, caplog):
    from app.services.agent_runtime import d4_text_delivery
    c = d4_logged_server
    caplog.set_level(logging.INFO, logger='uvicorn.access')
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
    diagnostic = 'SYNTHETIC-D4-EXCEPTION-SENTINEL'
    calls = []
    def fail(*args, **kwargs):
        calls.append(True)
        raise RuntimeError(diagnostic + ': synthetic candidate')
    monkeypatch.setattr(d4_text_delivery, 'add_restricted_receipt_and_audit', fail)
    request_key = uuid4().hex
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': request_key})
        assert claim.status_code == 200, claim.text
        direct = await client.get('/api/agent/runtime/capa/d4/root-cause-text',
                                  headers={'Authorization': 'Bearer ' + claim.json()['token']})
        assert direct.status_code == 503 and direct.json() == {'detail': 'Delivery unavailable'}
        assert calls == [True]
        assert any('/api/agent/runtime/capa/d4/root-cause-text' in record.getMessage()
                   for record in c.access_records)
    worker = Path(__file__).resolve().parents[3] / 'examples' / 'readonly_d4_text_receiver.py'
    process = await asyncio.create_subprocess_exec(sys.executable, str(worker),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    config = {'origin': c.text_base_url, 'tenant_slug': c.slug, 'installation_id': str(c.text_id),
        'secret': c.text_secret, 'request_key': request_key, 'expected_report_id': str(c.report_id)}
    stdout, stderr = await asyncio.wait_for(process.communicate(json.dumps(config).encode()), timeout=60)
    assert process.returncode != 0 and json.loads(stdout)['status'] == 'unconfirmed'
    assert calls == [True, True]
    combined = (stdout.decode() + stderr.decode() + caplog.text
                + ''.join(logging.Formatter().format(record) for record in c.access_records))
    assert diagnostic not in combined and 'synthetic candidate' not in combined and c.text_secret not in combined
    assert any('/api/agent/runtime/capa/d4/root-cause-text' in record.getMessage()
               for record in c.access_records), [record.getMessage() for record in c.access_records]
    async with c.session() as db:
        assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'D4_TEXT_RELEASE_COMMITTED')) == 0


@pytest.mark.asyncio
async def test_readonly_snapshot_rejects_stale_tenant_generation(d4_text_server):
    from dataclasses import replace
    from app.core.tenant_transaction import TenantUnavailable
    from app.services.agent_runtime.d4_text_delivery import build_root_candidate
    c = d4_text_server
    stale = replace(c.binding, generation=c.binding.generation + 1)
    with pytest.raises(TenantUnavailable):
        await build_root_candidate(binding=stale, state=None)


@pytest.mark.asyncio
async def test_authority_parent_foreign_keys_are_immediate_in_real_tenant(d4_text_server):
    c = d4_text_server
    expected = {('user_factories', 'users'), ('user_product_lines', 'users'),
        ('role_permissions', 'role_definitions'), ('agent_plugin_grants', 'agent_plugin_installations'),
        ('agent_task_grants', 'agent_tasks'), ('agent_plugin_derived_source_scopes', 'agent_plugin_grants'),
        ('agent_task_derived_source_scopes', 'agent_task_grants'),
        ('agent_d4_task_parent_grants', 'agent_plugin_grants'),
        ('agent_d4_task_parent_grants', 'agent_task_grants')}
    async with c.session() as db:
        rows = (await db.execute(text('''
            SELECT child.relname AS child, parent.relname AS parent, con.condeferrable
            FROM pg_constraint con JOIN pg_class child ON child.oid = con.conrelid
            JOIN pg_namespace ns ON ns.oid = child.relnamespace
            JOIN pg_class parent ON parent.oid = con.confrelid
            WHERE con.contype = 'f' AND ns.nspname = :schema
        '''), {'schema': c.binding.schema_name})).all()
    found = {(row.child, row.parent): row.condeferrable for row in rows}
    assert expected <= found.keys()
    assert all(found[pair] is False for pair in expected)


@pytest.mark.asyncio
async def test_real_http_release_serializes_with_tenant_maintenance_generation(d4_text_server, monkeypatch):
    from app.core.tenant_transaction import TenantUnavailable
    from app.services import tenant_migrator
    from app.services.agent_runtime import d4_text_delivery
    c = d4_text_server
    task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
        'installation_id': str(c.text_id), 'request_key': uuid4().hex,
        'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
    assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
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
    async with httpx.AsyncClient(base_url=c.text_base_url, headers={'X-Tenant-ID': c.slug}, timeout=15) as client:
        claim = await client.post('/api/agent/runtime/claim', json={'installation_id': str(c.text_id),
            'secret': c.text_secret, 'request_key': uuid4().hex})
        assert claim.status_code == 200, claim.text
        headers = {'Authorization': 'Bearer ' + claim.json()['token']}
        response = await client.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
        assert response.status_code == 200 and blocked == [True], response.text
        async with tenant_migrator.maintenance_connection(c.engine, c.binding.tenant_id):
            async with c.engine.connect() as db:
                generation = await db.scalar(text('SELECT generation FROM public.tenants WHERE id=:id'),
                                             {'id': c.binding.tenant_id})
                assert generation == c.binding.generation + 1
            denied = await client.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
            assert denied.status_code in (401, 403, 404, 503), denied.text
            assert 'synthetic candidate' not in denied.text


@pytest.mark.asyncio
async def test_same_report_uuid_in_another_owned_tenant_never_accepts_run_token(d4_text_server):
    from app.core.tenant_transaction import TenantBinding
    from app.models.product_line import ProductLine
    from app.models.user import User
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator
    c = d4_text_server
    slug = 'd4-isolation-' + uuid4().hex[:12]
    tenant = await tenant_migrator.provision_new(TenantCreateRequest(name='D4 isolation test', slug=slug,
        admin_email='isolation@example.test', admin_password='owned-d4-isolation-password'))
    try:
        other_binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, 'business')
        async with c.factory(binding=other_binding) as db:
            owner = await db.scalar(select(User).where(User.email == 'isolation@example.test'))
            line = await db.scalar(select(ProductLine))
            db.add(CAPAEightD(report_id=c.report_id, document_no='OWNED-SECOND-TENANT',
                title='other tenant sentinel', status='D4_ROOT_CAUSE', d4_root_cause='other tenant secret',
                factory_id=line.factory_id, product_line_code=line.code, created_by=owner.user_id))
            await db.commit()
        task = await c.client.post('/api/agent/tasks', json={'report_id': str(c.report_id),
            'installation_id': str(c.text_id), 'request_key': uuid4().hex,
            'initial_text': START_MESSAGE, 'derived_source_scope': c.source_scope})
        assert task.status_code == 201 and task.json()['status'] == 'ready', task.text
        async with httpx.AsyncClient(base_url=c.text_base_url, timeout=15) as client:
            claim = await client.post('/api/agent/runtime/claim', headers={'X-Tenant-ID': c.slug}, json={
                'installation_id': str(c.text_id), 'secret': c.text_secret, 'request_key': uuid4().hex})
            assert claim.status_code == 200, claim.text
            headers = {'X-Tenant-ID': slug, 'Authorization': 'Bearer ' + claim.json()['token']}
            denied = await client.get('/api/agent/runtime/capa/d4/root-cause-text', headers=headers)
            assert denied.status_code == 401, denied.text
            assert 'synthetic candidate' not in denied.text and 'other tenant secret' not in denied.text
            allowed = await client.get('/api/agent/runtime/capa/d4/root-cause-text', headers={
                'X-Tenant-ID': c.slug, 'Authorization': 'Bearer ' + claim.json()['token']})
            assert allowed.status_code == 200 and allowed.json()['text'] == 'synthetic candidate', allowed.text
        async with c.factory(binding=other_binding) as db:
            assert await db.scalar(select(func.count()).select_from(AgentRestrictedProjectionReceipt)) == 0
    finally:
        async with c.engine.begin() as conn:
            row = (await conn.execute(text('SELECT id, schema_name FROM public.tenants WHERE id=:id AND slug=:slug'),
                                      {'id': tenant.id, 'slug': slug})).one_or_none()
            if row is not None:
                assert row.schema_name == tenant.schema_name
                await conn.execute(text(f'DROP SCHEMA "{tenant.schema_name}" CASCADE'))
                await conn.execute(text('DELETE FROM public.tenant_migrations WHERE tenant_id=:id'), {'id': tenant.id})
                await conn.execute(text('DELETE FROM public.tenants WHERE id=:id'), {'id': tenant.id})
