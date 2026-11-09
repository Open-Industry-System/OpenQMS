import asyncio
from datetime import UTC, datetime, timedelta

from jose import jwt
import pytest
from sqlalchemy import func, select

from app.models.agent_runtime_event import AgentProjectionReceipt
from app.models.audit import AuditLog
from tests.e2e.agent_local_trial_harness import owned_local_trial, MARKER


@pytest.mark.asyncio
async def test_trial_claim_binds_current_policy_and_caps_lease_without_retry_extension(owned_local_trial):
    owned = owned_local_trial
    owned.entry['expires_at'] = (datetime.now(UTC)+timedelta(seconds=90)).isoformat()
    await owned.restart()
    await owned.enable()
    await owned.create()
    response = await owned.claim()
    assert response.status_code == 200, response.text
    claim = response.json()
    claims = jwt.get_unverified_claims(claim['token'])
    assert claims.get('trial_binding_sha256') == owned.policy.entries[0].binding_sha256
    assert datetime.fromisoformat(claim['lease_expires_at']) <= owned.policy.entries[0].expires_at
    assert claims['exp'] <= owned.policy.entries[0].expires_at.timestamp()
    assert set(claim) == {'run_id', 'task_id', 'token', 'lease_epoch', 'lease_expires_at',
        'accepted_message_seq', 'has_resume_checkpoint'}
    retry = (await owned.claim()).json()
    assert retry['lease_expires_at'] == claim['lease_expires_at'] and retry['lease_epoch'] == claim['lease_epoch']


@pytest.mark.asyncio
async def test_normal_trial_metadata_delivery_uses_real_policy_and_keeps_body_private(owned_local_trial):
    owned = owned_local_trial
    await owned.enable()
    task = await owned.create()
    claim = (await owned.claim()).json()
    auth = {'Authorization': 'Bearer '+claim['token']}
    report = await owned.client.get('/api/agent/runtime/capa/context', headers=auth)
    assert report.status_code == 200, report.text
    children = await owned.client.get('/api/agent/runtime/capa/context', headers=auth, params={'view': 'verifications'})
    assert children.status_code == 200
    assert report.json()['projection_digest'] == children.json()['projection_digest']
    assert len(children.json()['verifications']) == 2 and MARKER not in report.text+children.text
    response = await owned.client.post('/api/agent/runtime/messages/claim', headers=auth, json={})
    assert response.status_code == 200, response.text
    assert MARKER in response.text  # Input is explicitly restricted/raw, not metadata.
    activity = await owned.client.get(f'/api/agent/tasks/{task["task_id"]}/activity')
    assert activity.status_code == 200


@pytest.mark.asyncio
async def test_snapshot_started_before_expiry_cannot_commit_receipt_after_expiry(owned_local_trial, monkeypatch):
    from app.services import capa_agent_projection
    owned = owned_local_trial
    await owned.enable()
    await owned.create()
    owned.entry['expires_at'] = (datetime.now(UTC)+timedelta(seconds=3)).isoformat()
    await owned.restart()
    response = await owned.claim()
    assert response.status_code == 200, response.text
    token = response.json()['token']
    ready, release = asyncio.Event(), asyncio.Event()
    original = capa_agent_projection.build_masked_d4_projection
    async def held_snapshot(*args, **kwargs):
        payload = await original(*args, **kwargs)
        ready.set()
        await release.wait()
        return payload
    monkeypatch.setattr(capa_agent_projection, 'build_masked_d4_projection', held_snapshot)
    request = asyncio.create_task(owned.client.get('/api/agent/runtime/capa/context',
        headers={'Authorization': 'Bearer '+token}))
    try:
        await asyncio.wait_for(ready.wait(), 2)
        remaining = (owned.policy.entries[0].expires_at-datetime.now(UTC)).total_seconds()
        await asyncio.sleep(max(0, remaining)+.05)
        release.set()
        result = await asyncio.wait_for(request, 5)
        assert result.status_code in (401, 403) and 'receipt_id' not in result.text and MARKER not in result.text
        async with owned.session() as db:
            assert await db.scalar(select(func.count()).select_from(AgentProjectionReceipt)) == 0
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'QUERY_AGENT_CAPA_CONTEXT')) == 0
    finally:
        release.set()
        await asyncio.gather(request, return_exceptions=True)
