from datetime import UTC, datetime, timedelta

from jose import jwt
import pytest

from app.config import settings
from tests.e2e.agent_local_trial_harness import owned_local_trial, MARKER


@pytest.mark.asyncio
async def test_trial_token_requires_private_current_binding_and_rotated_epoch(owned_local_trial):
    owned = owned_local_trial
    await owned.enable()
    await owned.create()
    response = await owned.claim()
    assert response.status_code == 200
    token = response.json()['token']
    original = jwt.get_unverified_claims(token)
    assert original.get('trial_binding_sha256') == owned.policy.entries[0].binding_sha256
    for value in (None, False, 'bad', 'f'*64):
        claims = {**original, 'trial_binding_sha256': value}
        if value is None: claims.pop('trial_binding_sha256')
        forged = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        result = await owned.client.get('/api/agent/runtime/capabilities', headers={'Authorization': 'Bearer '+forged})
        assert result.status_code == 401 and MARKER not in result.text
    rotated = await owned.admin.post(f'/api/admin/agent-plugins/{owned.installation_id}/rotate-secret')
    assert rotated.status_code == 200
    result = await owned.client.get('/api/agent/runtime/capabilities', headers={'Authorization': 'Bearer '+token})
    assert result.status_code == 401
    response = await owned.claim('post-rotation')
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_policy_restart_changes_binding_without_renewing_existing_grants(owned_local_trial):
    owned = owned_local_trial
    await owned.enable()
    await owned.create()
    token = (await owned.claim()).json()['token']
    owned.entry['expires_at'] = (datetime.now(UTC)+timedelta(minutes=21)).isoformat()
    await owned.restart()
    result = await owned.client.get('/api/agent/runtime/capabilities', headers={'Authorization': 'Bearer '+token})
    assert result.status_code == 401
    retry = await owned.claim()
    assert retry.status_code == 200
    assert jwt.get_unverified_claims(retry.json()['token'])['trial_binding_sha256'] == owned.policy.entries[0].binding_sha256
