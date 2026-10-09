import asyncio
import json
import sys
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import update

from app.models.agent_task import AgentRun
from app.models.capa import CapaRootCauseVerification
from tests.e2e.agent_local_trial_harness import (
    owned_local_trial, local_trial_server, execute_cli, business_snapshot, MARKER,
)


async def control(owned, task_id, run_id, action, checkpoint_id=None):
    async with owned.session() as db:
        run = await db.get(AgentRun, UUID(run_id))
        epoch = run.lease_epoch
    body = {'action': action, 'run_id': run_id, 'expected_epoch': epoch, 'idempotency_key': uuid4().hex}
    if checkpoint_id: body['checkpoint_id'] = checkpoint_id
    response = await owned.client.post(f'/api/agent/tasks/{task_id}/control', json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def revoke_cli(owned, tmp_path):
    path = tmp_path / 'admin.jwt'
    if not path.exists():
        with path.open('x') as stream:
            path.chmod(0o600)
            stream.write(owned.admin_token)
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'app.cli.agent_local_trial', 'revoke',
        '--installation-id', str(owned.installation_id), '--expected-credential-epoch', '0',
        '--tenant-slug', owned.slug, '--api-base-url', owned.base_url, '--admin-token-file', str(path),
        env={'LANG': 'C', 'LC_ALL': 'C'}, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 20)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode == 0 and stderr == b'', stderr.decode()
    assert owned.admin_token.encode() not in stdout
    return json.loads(stdout)


@pytest.mark.asyncio
async def test_normal_policy_real_cli_rounds_same_run_resume_and_checkpoint_new_run(local_trial_server, tmp_path):
    owned = local_trial_server
    await owned.enable()
    task = await owned.create()
    owned.task_id = UUID(task['task_id'])
    before = await business_snapshot(owned)
    code, stdout, stderr = await execute_cli(owned, tmp_path, checkpoint='save')
    assert code == 0 and stderr == '', stderr
    first = json.loads(stdout)
    contexts = [call[4] for call in owned.witness.calls if call[1].endswith('/capa/context') and call[3] == 200]
    assert len(contexts) == 2 and contexts[0]['projection_digest'] == contexts[1]['projection_digest']
    assert contexts[0]['receipt_id'] != contexts[1]['receipt_id']
    assert len(contexts[0]['projection_digest']) == 64 and MARKER not in json.dumps(contexts)
    assert await business_snapshot(owned) == before
    await control(owned, task['task_id'], first['run_id'], 'pause')
    response = await owned.client.post(f'/api/agent/tasks/{task["task_id"]}/messages',
        json={'content': 'input while paused, never evaluated', 'idempotency_key': uuid4().hex})
    assert response.status_code == 202
    await control(owned, task['task_id'], first['run_id'], 'resume')
    code, stdout, stderr = await execute_cli(owned, tmp_path, checkpoint='save', key='same-run-resume')
    assert code == 0 and stderr == ''
    resumed = json.loads(stdout)
    assert resumed['run_id'] == first['run_id'] and resumed['checkpoint_id'] != first['checkpoint_id']
    await control(owned, task['task_id'], resumed['run_id'], 'pause')
    async with owned.session() as db:
        await db.execute(update(CapaRootCauseVerification).where(CapaRootCauseVerification.capa_id == owned.report_id,
            CapaRootCauseVerification.conclusion == 'pending').values(conclusion='failed'))
        await db.commit()
    changed = await business_snapshot(owned)
    assert changed != before
    restarted = await control(owned, task['task_id'], resumed['run_id'], 'restart', resumed['checkpoint_id'])
    assert restarted['run_id'] != first['run_id']
    code, stdout, stderr = await execute_cli(owned, tmp_path, finish='completed', key='checkpoint-new-run')
    assert code == 0 and stderr == ''
    output = json.loads(stdout)
    assert output['run_id'] == restarted['run_id'] and output['task_status'] == 'completed'
    last = [call[4] for call in owned.witness.calls if call[1].endswith('/capa/context') and call[3] == 200][-1]
    assert last['projection_digest'] != contexts[0]['projection_digest']
    assert 'failed' in [row['conclusion'] for row in last['verifications']]
    histories = [call[4]['messages'] for call in owned.witness.calls if call[1].endswith('/messages/history')]
    assert [message['sequence'] for message in histories[-1]] == [1, 2]
    assert await business_snapshot(owned) == changed


@pytest.mark.asyncio
async def test_cli_permanent_revoke_between_actual_rounds_prevents_later_delivery(local_trial_server, tmp_path):
    owned = local_trial_server
    await owned.enable()
    await owned.create()
    before = await business_snapshot(owned)
    async def fence():
        assert (await revoke_cli(owned, tmp_path))['outcome'] == 'revoked'
    owned.witness.after_first = fence
    code, stdout, stderr = await execute_cli(owned, tmp_path)
    assert code == 1 and stdout == '' and stderr == 'TRIAL_RUN_FAILED\n'
    contexts = [call for call in owned.witness.calls if call[1].endswith('/capa/context')]
    assert [call[3] for call in contexts] == [200, 401]
    assert (await revoke_cli(owned, tmp_path))['outcome'] == 'already_fenced'
    assert (await execute_cli(owned, tmp_path, key='revoked-claim'))[0] == 1
    assert await business_snapshot(owned) == before


@pytest.mark.asyncio
async def test_actual_tcp_forwarded_identity_is_rejected_before_invalid_tenant_or_body(local_trial_server):
    owned = local_trial_server
    async with httpx.AsyncClient(base_url=owned.base_url, trust_env=False) as client:
        for path in ('/api/agent/runtime/claim', '/api/agent/tasks', '/api/admin/agent-plugins'):
            response = await client.post(path, content='invalid JSON', headers={
                'X-Tenant-ID': 'must-not-resolve', 'X-Forwarded-For': '127.0.0.1'})
            assert response.status_code == 403
