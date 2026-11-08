from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.agent_task import AgentRun, AgentTaskGrant
from tests.e2e.agent_local_trial_harness import owned_local_trial, SUMMARY


@pytest.mark.asyncio
async def test_normal_grant_directory_and_task_are_ready_without_authority_patches(owned_local_trial):
    owned = owned_local_trial
    await owned.enable()
    response = await owned.client.get('/api/agent/tasks/installations', params={'report_id': str(owned.report_id)})
    assert response.status_code == 200
    assert [item['installation_id'] for item in response.json()['items']] == [str(owned.installation_id)]
    task = await owned.create()
    assert task['status'] == 'ready'
    async with owned.session() as db:
        run = await db.scalar(select(AgentRun).where(AgentRun.task_id == task['task_id']))
        grants = list((await db.scalars(select(AgentTaskGrant).where(AgentTaskGrant.task_id == run.task_id))).all())
        assert run.status == 'pending'
        assert len(grants) == 1 and grants[0].capability_id == SUMMARY
        assert grants[0].object_ids == [str(owned.report_id)]
        assert grants[0].factory_ids == [str(owned.factory_id)]
        assert grants[0].product_line_codes == [owned.line]


@pytest.mark.asyncio
async def test_trial_grants_require_exact_real_targets_and_finite_bounded_expiry(owned_local_trial):
    owned = owned_local_trial
    for changes in [
        {'object_ids': None}, {'product_line_codes': None}, {'expires_at': None},
        {'expires_at': (datetime.now(UTC)+timedelta(hours=1)).isoformat()},
        {'object_ids': [str(uuid4())]}, {'factory_ids': [str(uuid4())]},
        {'product_line_codes': ['OTHER']}, {'capability_id': 'capa.d4.candidate.propose.v1'},
    ]:
        response = await owned.admin.post(f'/api/admin/agent-plugins/{owned.installation_id}/grants',
            json=owned.grant_body(**changes))
        assert response.status_code == 409, changes
    await owned.enable()
    # Disabling remains possible after policy expiry/absence.
    await owned.restart([])
    response = await owned.admin.patch(f'/api/admin/agent-plugins/{owned.installation_id}/grants/{owned.grant_id}',
        json={'enabled': False})
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['executor_user_id', 'report_id', 'factory_id', 'product_line_code', 'credential_epoch', 'tenant_generation'])
async def test_directory_and_create_agree_after_exact_binding_change(owned_local_trial, field):
    owned = owned_local_trial
    await owned.enable()
    entry = dict(owned.entry)
    if field in ('credential_epoch', 'tenant_generation'):
        entry[field] += 1
    elif field == 'product_line_code': entry[field] = 'OTHER'
    else: entry[field] = str(uuid4())
    await owned.restart([entry])
    response = await owned.client.get('/api/agent/tasks/installations', params={'report_id': str(owned.report_id)})
    assert response.status_code == 200 and response.json()['items'] == []
    task = await owned.create()
    assert task['status'] == 'blocked_capability'
    async with owned.session() as db:
        assert await db.scalar(select(AgentRun).where(AgentRun.task_id == task['task_id'])) is None
