"""Real normal-policy HTTP acceptance of an installed SDK wheel, no provider.

These are default backend tests, not browser/live/scanner tests. The child is a
fixture-only protocol client; the policy's audited fixed-worker hash is unchanged.
"""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models.agent_task import AgentTask, AgentRun
from tests.e2e.agent_local_trial_harness import (
    owned_local_trial, local_trial_server, business_snapshot, MARKER,
)
from tests.e2e.sdk_process_support import (
    sdk_runtime, sdk_child, control, finish_fault, foreign_tenant,
)


async def start(child, *, extra_message=False):
    owned = child.owned
    assert not owned.app.dependency_overrides
    await owned.enable()
    task = await owned.create()
    if extra_message:
        response = await owned.client.post(f'/api/agent/tasks/{task["task_id"]}/messages',
            json={'content': MARKER + ' never execute', 'idempotency_key': uuid4().hex})
        assert response.status_code == 202
    claim = await child.command('claim')
    assert claim['task_id'] == task['task_id'] and claim['isolated']
    assert any(call[1] == '/api/agent/runtime/claim' and call[3] == 200 for call in owned.witness.calls)
    return task, claim


def denied(result, status):
    assert result['error'] == 'HTTPError' and result['status'] == status
    assert result['unknown'] is False and result['state'] == 'open'


@pytest.mark.asyncio
async def test_installed_sdk_claim_crosses_real_tcp(sdk_child):
    await start(sdk_child)


@pytest.mark.asyncio
async def test_sdk_ten_operations_sources_idempotency_and_terminal_fence(sdk_child):
    owned = sdk_child.owned
    task, claim = await start(sdk_child, extra_message=True)
    before = await business_snapshot(owned)
    assert (await sdk_child.command('capabilities'))['summary_allowed']
    assert await sdk_child.command('messages') == {'count': 2, 'accepted': 0, 'sequences': [1, 2]}
    denied(await sdk_child.command('finish'), 409)
    assert await sdk_child.command('ack', through=1) == {'accepted': 1}
    assert await sdk_child.command('ack', through=2) == {'accepted': 2}
    assert await sdk_child.command('ack', through=1) == {'accepted': 2}  # covered ACK
    first = await sdk_child.command('context')
    second = await sdk_child.command('context')
    assert first['receipt_id'] != second['receipt_id']
    assert first['verifications_none'] and second['verifications_none']
    verification = await sdk_child.command('context', view='verifications')
    assert not verification['verifications_none'] and verification['count'] == 2 and verification['tuple']
    for action in ('event', 'result', 'checkpoint'):
        saved = await sdk_child.command(action)
        assert saved['sources'] == 1 and saved['source_matches']
        assert await sdk_child.command(action) == saved
        denied(await sdk_child.command(action, alternate_source=True), 409)
        if action != 'checkpoint':
            denied(await sdk_child.command(action, changed=True), 409)
    assert await sdk_child.command('history') == {'count': 2, 'next': 2, 'complete': True, 'sequences': [1, 2]}
    assert await sdk_child.command('history', after=99) == {'count': 0, 'next': 2, 'complete': True, 'sequences': []}
    # A separate RunClient holds an old token: this is a remote fence, not local close.
    duplicate = await sdk_child.command('claim')
    assert duplicate['run_id'] == claim['run_id']
    assert await sdk_child.command('finish') == {'task_status': 'completed', 'run_status': 'completed',
        'state': 'closed_successfully'}
    rejected = await sdk_child.command('capabilities', previous=True)
    assert rejected['error'] == 'HTTPError' and rejected['status'] == 401
    async with owned.session() as db:
        assert (await db.get(AgentTask, UUID(task['task_id']))).status == 'completed'
        assert (await db.get(AgentRun, UUID(claim['run_id']))).status == 'completed'
        from app.database import TenantBase
        for name in ('agent_projection_receipts', 'agent_run_events', 'agent_results', 'agent_readonly_checkpoints'):
            table = TenantBase.metadata.tables[name]
            assert await db.scalar(select(func.count()).select_from(table)) > 0
    contexts = [call[4] for call in owned.witness.calls if call[1].endswith('/capa/context') and call[3] == 200]
    assert len(contexts) == 3 and MARKER not in str(contexts)
    assert all(len(item['projection_digest']) == 64 for item in contexts)
    assert await business_snapshot(owned) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', [
    'oversize', 'bad_json', 'wrong_run', 'wrong_task', 'wrong_status', 'schema',
    'disconnect', 'server_error', 'timeout',
])
async def test_sdk_finish_committed_but_confirmation_unknown(sdk_child, finish_fault, fault):
    owned = sdk_child.owned
    task, claim = await start(sdk_child)
    before = await business_snapshot(owned)
    await sdk_child.command('messages')
    await sdk_child.command('ack', through=1)
    finish_fault.mode = fault
    result = await sdk_child.command('finish')
    async with owned.session() as db:
        assert (await db.get(AgentTask, UUID(task['task_id']))).status == 'completed'
        assert (await db.get(AgentRun, UUID(claim['run_id']))).status == 'completed'
    assert result['error'] == 'UnknownOutcome'
    assert result['unknown'] and result['sent'] and result['state'] == 'uncertain'
    assert finish_fault.calls == 1
    assert (await sdk_child.command('finish'))['error'] == 'ClientClosed'
    assert len([call for call in owned.witness.calls if call[1].endswith('/finish')]) == 1
    assert await business_snapshot(owned) == before


@pytest.mark.asyncio
async def test_sdk_report_pause_restart_and_old_receipt_fences(sdk_child):
    owned = sdk_child.owned
    task, claim = await start(sdk_child)
    response = await owned.admin.post('/api/capa', json={'title': 'Other owned report',
        'document_no': '8D-SDK-OTHER', 'product_line_code': owned.line})
    assert response.status_code == 201
    other_report = response.json()['report_id']
    before = await business_snapshot(owned)
    denied(await sdk_child.command('context', report_id=other_report), 403)
    await sdk_child.command('messages')
    await sdk_child.command('ack', through=1)
    await sdk_child.command('context')
    checkpoint = await sdk_child.command('checkpoint')
    await control(owned, task['task_id'], claim['run_id'], 'pause')
    denied(await sdk_child.command('context'), 401)
    restarted = await control(owned, task['task_id'], claim['run_id'], 'restart', checkpoint['id'])
    denied(await sdk_child.command('context'), 401)
    fresh = await sdk_child.command('claim', key='after-restart')
    assert fresh['run_id'] == restarted['run_id'] != claim['run_id']
    denied(await sdk_child.command('result', old_receipt=True, key='old-source'), 403)
    await sdk_child.command('context')
    assert (await sdk_child.command('result', key='fresh-source'))['source_matches']
    assert await business_snapshot(owned) == before


@pytest.mark.asyncio
async def test_sdk_credentials_cannot_claim_in_another_real_tenant(sdk_child, foreign_tenant):
    owned = sdk_child.owned
    await start(sdk_child)
    before = await business_snapshot(owned)
    denied(await sdk_child.command('tenant_claim', tenant=foreign_tenant), 403)
    assert (await sdk_child.command('context'))['report_id'] == str(owned.report_id)
    assert await business_snapshot(owned) == before


@pytest.mark.asyncio
async def test_sdk_admin_grant_withdrawal_and_permanent_revoke(sdk_child):
    owned = sdk_child.owned
    await start(sdk_child)
    before = await business_snapshot(owned)
    await sdk_child.command('context')
    response = await owned.admin.patch(
        f'/api/admin/agent-plugins/{owned.installation_id}/grants/{owned.grant_id}', json={'enabled': False})
    assert response.status_code == 200
    denied(await sdk_child.command('context'), 401)
    # Restore the grant first, so permanent revoke is an independent fence.
    response = await owned.admin.patch(
        f'/api/admin/agent-plugins/{owned.installation_id}/grants/{owned.grant_id}', json={'enabled': True})
    assert response.status_code == 200
    assert (await sdk_child.command('context'))['report_id'] == str(owned.report_id)
    response = await owned.admin.post(f'/api/admin/agent-plugins/{owned.installation_id}/revoke-local-trial',
        json={'expected_credential_epoch': 0})
    assert response.status_code == 200
    denied(await sdk_child.command('context'), 401)
    denied(await sdk_child.command('claim', key='after-revoke'), 403)
    await owned.restart()  # stale policy file cannot undo the persisted epoch fence.
    denied(await sdk_child.command('claim', key='after-revoke-restart'), 403)
    assert await business_snapshot(owned) == before
