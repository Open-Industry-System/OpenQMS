import pytest

from tests.e2e.agent_local_trial_harness import owned_local_trial


@pytest.mark.asyncio
async def test_revoke_current_admin_strict_epoch_and_reenable_does_not_restore_old_authority(owned_local_trial):
    owned = owned_local_trial
    await owned.enable()
    await owned.create()
    token = (await owned.claim()).json()['token']
    path = f'/api/admin/agent-plugins/{owned.installation_id}/revoke-local-trial'
    for epoch in (True, -1, 2147483647, '0', 1.5):
        response = await owned.admin.post(path, json={'expected_credential_epoch': epoch})
        assert response.status_code == 422
    assert (await owned.client.post(path, json={'expected_credential_epoch': 0})).status_code == 403
    # Revoke must work even with no valid startup declaration.
    await owned.restart([])
    response = await owned.admin.post(path, json={'expected_credential_epoch': 0})
    assert response.status_code == 200, response.text
    assert response.json() == {'installation_id': str(owned.installation_id), 'credential_epoch': 1,
        'enabled': False, 'outcome': 'revoked'}
    retry = await owned.admin.post(path, json={'expected_credential_epoch': 0})
    assert retry.status_code == 200 and retry.json()['outcome'] == 'already_fenced'
    assert (await owned.admin.patch(f'/api/admin/agent-plugins/{owned.installation_id}', json={'enabled': True})).status_code == 200
    assert (await owned.admin.post(path, json={'expected_credential_epoch': 0})).status_code == 409
    await owned.restart()
    assert (await owned.claim()).status_code == 403
    assert (await owned.client.get('/api/agent/runtime/capabilities', headers={'Authorization': 'Bearer '+token})).status_code == 401
