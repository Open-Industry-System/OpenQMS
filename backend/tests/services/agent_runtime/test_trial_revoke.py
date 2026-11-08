import asyncio

import pytest
from sqlalchemy import func, select, update

from app.models.agent_plugin import AgentPluginInstallation
from app.models.audit import AuditLog
from app.models.user import User
from tests.e2e.agent_local_trial_harness import owned_local_trial
from tests.services.agent_runtime.test_task_controls import wait_lock


async def revoke(owned, expected=0, *, commit=True):
    from app.services.agent_runtime.plugin_registry import revoke_local_trial
    async with owned.session() as db:
        actor = await db.get(User, owned.admin_user_id)
        result = await revoke_local_trial(db, actor, owned.installation_id, expected)
        if commit: await db.commit()
        return result


async def facts(owned):
    async with owned.session() as db:
        plugin = await db.get(AgentPluginInstallation, owned.installation_id)
        audits = list((await db.scalars(select(AuditLog.changed_fields).where(AuditLog.action == 'REVOKE_LOCAL_TRIAL'))).all())
        return plugin.enabled, plugin.credential_epoch, plugin.secret_hash, audits


@pytest.mark.asyncio
async def test_permanent_revoke_retry_has_single_epoch_audit_and_never_returns_secret(owned_local_trial):
    owned = owned_local_trial
    await owned.enable()
    before = await facts(owned)
    first = await revoke(owned)
    second = await revoke(owned)
    assert first.outcome == 'revoked' and second.outcome == 'already_fenced'
    enabled, epoch, hashed, audits = await facts(owned)
    assert enabled is False and epoch == 1 and hashed != before[2] and len(audits) == 1
    assert owned.secret not in str(first.model_dump())+str(audits[0])
    assert audits[0]['old_credential_epoch'] == 0
    assert audits[0]['credential_epoch'] == 1


@pytest.mark.asyncio
async def test_concurrent_same_expected_fences_once(owned_local_trial):
    owned = owned_local_trial
    await owned.enable()
    results = await asyncio.gather(revoke(owned), revoke(owned))
    assert sorted(row.outcome for row in results) == ['already_fenced', 'revoked']
    enabled, epoch, _, audits = await facts(owned)
    assert enabled is False and epoch == 1 and len(audits) == 1


@pytest.mark.asyncio
async def test_caller_rollback_preserves_credential_epoch_enabled_and_audit(owned_local_trial):
    owned = owned_local_trial
    await owned.enable()
    before = await facts(owned)
    await revoke(owned, commit=False)
    after = await facts(owned)
    assert before[:3] == after[:3] and after[3] == []


@pytest.mark.asyncio
async def test_admin_withdrawal_during_install_lock_wait_prevents_fence(owned_local_trial):
    owned = owned_local_trial
    await owned.enable()
    async with owned.session() as blocker:
        await blocker.scalar(select(AgentPluginInstallation).where(
            AgentPluginInstallation.installation_id == owned.installation_id).with_for_update())
        contender = asyncio.create_task(revoke(owned))
        try:
            await wait_lock(owned, 'agent_plugin_installations')
            async with owned.session() as writer:
                await writer.execute(update(User).where(User.user_id == owned.admin_user_id).values(is_active=False))
                await writer.commit()
            await blocker.commit()
            with pytest.raises(PermissionError): await contender
        finally:
            await blocker.rollback()
            await asyncio.gather(contender, return_exceptions=True)
    enabled, epoch, _, audits = await facts(owned)
    assert enabled is True and epoch == 0 and audits == []


@pytest.mark.asyncio
@pytest.mark.parametrize('winner', ['revoke', 'delivery'])
async def test_real_revoke_and_final_delivery_commit_in_both_orders(owned_local_trial, monkeypatch, winner):
    from app.services import capa_agent_projection
    from app.models.agent_runtime_event import AgentProjectionReceipt
    owned = owned_local_trial
    await owned.enable()
    await owned.create()
    token = (await owned.claim()).json()['token']
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
        await asyncio.wait_for(ready.wait(), 3)
        if winner == 'revoke':
            await revoke(owned)
            release.set()
            response = await asyncio.wait_for(request, 5)
            assert response.status_code in (401, 403) and 'receipt_id' not in response.text
        else:
            release.set()
            response = await asyncio.wait_for(request, 5)
            assert response.status_code == 200
            await revoke(owned)
        async with owned.session() as db:
            assert await db.scalar(select(func.count()).select_from(AgentProjectionReceipt)) == (1 if winner == 'delivery' else 0)
            assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'QUERY_AGENT_CAPA_CONTEXT')) == (1 if winner == 'delivery' else 0)
        denied = await owned.client.get('/api/agent/runtime/capabilities', headers={'Authorization': 'Bearer '+token})
        assert denied.status_code == 401
    finally:
        release.set()
        await asyncio.gather(request, return_exceptions=True)
