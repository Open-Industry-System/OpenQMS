"""Lease-fenced restricted instructions, using committed tenant transactions."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import uuid
from types import MappingProxyType

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text, update

from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant, AgentTaskMessage
from app.models.audit import AuditLog
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User
from app.services.agent_runtime import message_queue, run_dispatch, runtime_access
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned


def service():
    try:
        from app.services.agent_runtime import runtime_messages
    except ImportError:
        pytest.fail("runtime message delivery is not implemented")
    return runtime_messages


@pytest_asyncio.fixture
async def delivery(ready_owned, monkeypatch):
    owned = ready_owned
    monkeypatch.setattr(runtime_access, "TRUSTED_DELIVERY_DEPLOYMENTS", frozenset({
        (str(owned.binding.tenant_id), owned.plugin_id, "1.0.0")}))
    async with owned.factory(binding=owned.binding) as db:
        result = await run_dispatch.claim_run(db, owned.binding, owned.plugin_id, owned.secret, "messages")
    owned.token = result.token
    return owned


async def append(owned, content, key=None):
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        return await message_queue.append_task_message(db, identity.task, identity.scope, content, key or uuid.uuid4().hex)


async def claim(owned, limit=20):
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        return await service().claim_messages(db, identity, limit)


async def ack(owned, batch, sequence):
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        return await service().ack_messages(db, identity, batch, sequence)


async def snapshot(owned):
    async with owned.factory(binding=owned.binding) as db:
        rows = list((await db.scalars(select(AgentTaskMessage).where(AgentTaskMessage.task_id == owned.task_id).order_by(AgentTaskMessage.sequence))).all())
        accepted = await db.scalar(select(AgentRun.accepted_message_seq).where(AgentRun.run_id == owned.run_id))
        audits = list((await db.scalars(select(AuditLog).where(AuditLog.action == "ACK_AGENT_TASK_MESSAGES"))).all())
        return accepted, [(r.sequence, r.state, r.delivery_batch_id, r.delivery_epoch) for r in rows], [a.changed_fields for a in audits]


def test_strict_bounded_message_schemas():
    try:
        from app.schemas.agent_runtime import MessageClaim, MessageAck
    except ImportError:
        pytest.fail("message schemas are not implemented")
    assert MessageClaim().limit == 20
    for value in (0, 21, True, "2", 2.5):
        with pytest.raises(ValidationError):
            MessageClaim(limit=value)
    fields = dict(batch_id=uuid.uuid4(), through_sequence=1)
    assert MessageAck(**fields).through_sequence == 1
    for value in (0, True, "1", 1.1):
        with pytest.raises(ValidationError):
            MessageAck(**{**fields, "through_sequence": value})
    for name in ("actor_id", "task_id", "run_id", "lease_epoch", "controlled_egress", "policy"):
        with pytest.raises(ValidationError):
            MessageClaim(**{name: "spoof"})
        with pytest.raises(ValidationError):
            MessageAck(**fields, **{name: "spoof"})


@pytest.mark.asyncio
async def test_stable_batch_partial_ack_pending_append_and_new_session_persistence(delivery):
    owned = delivery
    for value in ("restricted original 1", "restricted original 2"):
        await append(owned, value)
    batch = await claim(owned)
    assert [m.sequence for m in batch.messages] == [1, 2]
    assert [m.content for m in batch.messages] == ["restricted original 1", "restricted original 2"]
    assert set(batch.model_dump()) == {"batch_id", "messages", "accepted_sequence"}
    assert set(batch.messages[0].model_dump()) == {"message_id", "sequence", "content"}
    assert (await claim(owned, 1)).model_dump() == batch.model_dump()
    await append(owned, "restricted original 3")
    assert (await claim(owned)).model_dump() == batch.model_dump()
    assert (await ack(owned, batch.batch_id, 1)).accepted_sequence == 1
    remaining = await claim(owned, 20)
    assert remaining.batch_id == batch.batch_id
    assert [m.sequence for m in remaining.messages] == [2]
    assert remaining.accepted_sequence == 1
    before = await snapshot(owned)
    assert (await ack(owned, batch.batch_id, 1)).accepted_sequence == 1
    assert await snapshot(owned) == before
    assert (await ack(owned, batch.batch_id, 2)).accepted_sequence == 2
    next_batch = await claim(owned)
    assert next_batch.batch_id != batch.batch_id and [m.sequence for m in next_batch.messages] == [3]
    await ack(owned, next_batch.batch_id, 3)
    empty = await claim(owned)
    assert empty.batch_id is None and empty.messages == [] and empty.accepted_sequence == 3
    accepted, rows, audits = await snapshot(owned)
    assert accepted == 3 and all(r[1] == "accepted" for r in rows)
    assert len(audits) == 3
    assert all(set(a) == {"batch_id", "task_id", "run_id", "through_sequence", "lease_epoch", "executor_user_id"} for a in audits)
    assert "restricted original" not in str(audits)


@pytest.mark.asyncio
async def test_bounded_claims_never_include_unseen_rows_and_invalid_ack_is_unchanged(delivery):
    owned = delivery
    for n in range(22):
        await append(owned, str(n))
    batch = await claim(owned)
    assert [m.sequence for m in batch.messages] == list(range(1, 21))
    for identifier, sequence in ((uuid.uuid4(), 1), (batch.batch_id, 21), (batch.batch_id, 0)):
        before = await snapshot(owned)
        with pytest.raises(ValueError):
            await ack(owned, identifier, sequence)
        assert await snapshot(owned) == before
    await ack(owned, batch.batch_id, 20)
    before = await snapshot(owned)
    with pytest.raises(ValueError):
        await ack(owned, uuid.uuid4(), 1)
    assert await snapshot(owned) == before
    # A delayed prefix is safe only with this actual batch's durable proof.
    before = await snapshot(owned)
    assert (await ack(owned, batch.batch_id, 19)).accepted_sequence == 20
    assert await snapshot(owned) == before
    await ack(owned, batch.batch_id, 20)
    assert [m.sequence for m in (await claim(owned)).messages] == [21, 22]


@pytest.mark.asyncio
async def test_foreign_batch_cannot_ack_this_task(delivery):
    owned = delivery
    await append(owned, "own")
    await claim(owned)
    foreign_batch = uuid.uuid4()
    async with owned.factory(binding=owned.binding) as db:
        original = await db.get(AgentTask, owned.task_id)
        other = AgentTask(initiator_id=owned.user_id, executor_user_id=owned.user_id,
            preferred_installation_id=owned.plugin_id, target_capa_id=original.target_capa_id,
            factory_id=original.factory_id, request_key=uuid.uuid4().hex, status="ready")
        db.add(other)
        await db.flush()
        db.add(AgentTaskMessage(task_id=other.task_id, author_id=owned.user_id, sequence=1,
            content="foreign secret", idempotency_key="foreign", state="claimed",
            delivery_batch_id=foreign_batch, delivery_epoch=1))
        await db.commit()
    before = await snapshot(owned)
    with pytest.raises(ValueError):
        await ack(owned, foreign_batch, 1)
    assert await snapshot(owned) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["claim", "ack"])
async def test_sequence_gap_fails_closed_without_skipping(delivery, operation):
    owned = delivery
    for n in range(3):
        await append(owned, str(n))
    batch = await claim(owned) if operation == "ack" else None
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(delete(AgentTaskMessage).where(AgentTaskMessage.task_id == owned.task_id, AgentTaskMessage.sequence == 2))
        await db.commit()
    before = await snapshot(owned)
    with pytest.raises(ValueError):
        if batch:
            await ack(owned, batch.batch_id, 3)
        else:
            await claim(owned)
    assert await snapshot(owned) == before


@pytest.mark.asyncio
async def test_concurrent_claim_and_same_ack_have_one_durable_effect(delivery):
    owned = delivery
    await asyncio.gather(append(owned, "one", "one"), append(owned, "two", "two"))
    batches = await asyncio.gather(claim(owned), claim(owned))
    assert batches[0].model_dump() == batches[1].model_dump()
    results = await asyncio.gather(ack(owned, batches[0].batch_id, 2), ack(owned, batches[0].batch_id, 2))
    assert [r.accepted_sequence for r in results] == [2, 2]
    accepted, rows, audits = await snapshot(owned)
    assert accepted == 2 and [r[0] for r in rows] == [1, 2] and len(audits) == 1


@pytest.mark.asyncio
async def test_effective_claims_are_audited_without_original_text_or_retry_duplicates(delivery):
    owned = delivery
    await append(owned, "restricted audit must not contain this")
    first, second = await asyncio.gather(claim(owned), claim(owned))
    assert first.batch_id == second.batch_id
    async with owned.factory(binding=owned.binding) as db:
        audits = list((await db.scalars(select(AuditLog).where(AuditLog.action == "CLAIM_AGENT_TASK_MESSAGES"))).all())
    assert len(audits) == 1
    assert audits[0].changed_fields == {
        "batch_id": str(first.batch_id), "task_id": str(owned.task_id), "run_id": str(owned.run_id),
        "from_sequence": 1, "through_sequence": 1, "lease_epoch": 1, "executor_user_id": str(owned.user_id)}
    assert audits[0].old_values is None and audits[0].new_values is None
    await ack(owned, first.batch_id, 1)
    assert (await claim(owned)).messages == []
    async with owned.factory(binding=owned.binding) as db:
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "CLAIM_AGENT_TASK_MESSAGES")) == 1


@pytest.mark.asyncio
async def test_append_claim_ack_concurrency_preserves_contiguous_queue(delivery):
    owned = delivery
    await append(owned, "first")
    first = await claim(owned)
    _, repeated, _ = await asyncio.gather(append(owned, "second"), claim(owned), ack(owned, first.batch_id, 1))
    assert [m.sequence for m in repeated.messages] in ([1], [2], [])
    next_batch = await claim(owned)
    assert [m.sequence for m in next_batch.messages] == [2]
    await ack(owned, next_batch.batch_id, 2)
    assert (await snapshot(owned))[0] == 2


@pytest.mark.asyncio
async def test_reclaim_resets_only_unaccepted_old_batch_and_fences_old_jwt(delivery):
    owned = delivery
    await append(owned, "first")
    await append(owned, "second")
    original = await claim(owned)
    await ack(owned, original.batch_id, 1)
    async with owned.factory(binding=owned.binding) as cached:
        identity = await runtime_access.verify_runtime_identity(cached, owned.token, owned.binding)
        async with owned.factory(binding=owned.binding) as db:
            await db.execute(update(AgentRun).where(AgentRun.run_id == owned.run_id).values(lease_expires_at=datetime.now(UTC)-timedelta(seconds=1)))
            await db.commit()
        async with owned.factory(binding=owned.binding) as db:
            newer = await run_dispatch.claim_run(db, owned.binding, owned.plugin_id, owned.secret, "new-lease")
        for op in (lambda: service().claim_messages(cached, identity), lambda: service().ack_messages(cached, identity, original.batch_id, 2)):
            with pytest.raises(PermissionError):
                await op()
            await cached.rollback()
    owned.token = newer.token
    batch = await claim(owned)
    assert batch.batch_id != original.batch_id and batch.accepted_sequence == 1
    assert [m.sequence for m in batch.messages] == [2]
    with pytest.raises(ValueError):
        await ack(owned, original.batch_id, 1)
    await ack(owned, batch.batch_id, 2)
    assert (await snapshot(owned))[1] == [(1, "accepted", original.batch_id, 1), (2, "accepted", batch.batch_id, 2)]


@pytest.mark.asyncio
async def test_later_run_same_epoch_cannot_ack_or_reuse_previous_runs_batch(delivery):
    owned = delivery
    await append(owned, "first")
    await append(owned, "second")
    original = await claim(owned)
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentRun).where(AgentRun.run_id == owned.run_id).values(status="stopped"))
        later = AgentRun(task_id=owned.task_id, installation_id=owned.plugin_id,
            plugin_version="1.0.0", status="pending")
        db.add(later)
        await db.commit()
        later_id = later.run_id
    async with owned.factory(binding=owned.binding) as db:
        result = await run_dispatch.claim_run(db, owned.binding, owned.plugin_id, owned.secret, "later-run")
        assert result.run_id == later_id and result.lease_epoch == 1
    owned.token = result.token
    before = await snapshot(owned)
    with pytest.raises(ValueError):
        await ack(owned, original.batch_id, 1)
    assert await snapshot(owned) == before
    fresh = await claim(owned)
    assert fresh.batch_id != original.batch_id and [m.sequence for m in fresh.messages] == [1, 2]
    with pytest.raises(ValueError):
        await ack(owned, original.batch_id, 1)
    assert (await ack(owned, fresh.batch_id, 2)).accepted_sequence == 2
    async with owned.factory(binding=owned.binding) as db:
        assert await db.scalar(select(AgentRun.accepted_message_seq).where(AgentRun.run_id == owned.run_id)) == 0
        assert await db.scalar(select(AgentRun.accepted_message_seq).where(AgentRun.run_id == later_id)) == 2


@pytest.mark.asyncio
async def test_empty_trusted_policy_and_canonical_deny_never_deliver(delivery, monkeypatch):
    owned = delivery
    await append(owned, "secret")
    monkeypatch.setattr(runtime_access, "TRUSTED_DELIVERY_DEPLOYMENTS", frozenset())
    before = await snapshot(owned)
    with pytest.raises(PermissionError):
        await claim(owned)
    assert await snapshot(owned) == before


@pytest.mark.asyncio
async def test_default_canonical_capability_denies_delivery_and_ack(delivery, monkeypatch):
    from app.services.agent.permissions import catalog
    from app.services.agent.permissions.types import ApprovalFloor
    owned = delivery
    await append(owned, "secret")
    batch = await claim(owned)
    monkeypatch.setattr(catalog, "CAPA_CAPABILITIES", MappingProxyType({
        key: replace(spec, approval_floor=ApprovalFloor.DENY) for key, spec in catalog.CAPA_CAPABILITIES.items()}))
    before = await snapshot(owned)
    for op in (lambda: claim(owned), lambda: ack(owned, batch.batch_id, 1)):
        with pytest.raises(PermissionError):
            await op()
    assert await snapshot(owned) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("membership", ["factory", "line"])
@pytest.mark.parametrize("operation", ["claim", "ack"])
async def test_current_target_membership_with_default_other_factory(delivery, membership, operation):
    from app.models.factory import Factory, UserFactory
    from app.models.role import UserProductLine
    owned = delivery
    await append(owned, "secret")
    async with owned.factory(binding=owned.binding) as db:
        task = await db.get(AgentTask, owned.task_id)
        factory_a = Factory(id=uuid.uuid4(), name="Default A", code="msg-A-"+uuid.uuid4().hex[:8])
        db.add(factory_a)
        await db.flush()
        await db.execute(update(User).where(User.user_id == owned.user_id).values(factory_id=factory_a.id))
        await db.execute(update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(bypass_row_level_security=False))
        await db.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == "group").values(permission_level=0))
        # B is the current target, despite default A; only explicit B/line memberships allow it.
        await db.execute(delete(UserFactory).where(UserFactory.user_id == owned.user_id))
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id == owned.user_id))
        db.add(UserFactory(user_id=owned.user_id, factory_id=factory_a.id))
        db.add(UserFactory(user_id=owned.user_id, factory_id=task.factory_id))
        db.add(UserProductLine(user_id=owned.user_id, product_line_code="DC-DC-100"))
        await db.commit()
    batch = await claim(owned)  # prove the non-bypass scope is legitimate before revocation
    before = await snapshot(owned)
    async with owned.factory(binding=owned.binding) as cached:
        identity = await runtime_access.verify_runtime_identity(cached, owned.token, owned.binding)
        async with owned.factory(binding=owned.binding) as db:
            if membership == "factory":
                await db.execute(delete(UserFactory).where(UserFactory.user_id == owned.user_id, UserFactory.factory_id != factory_a.id))
            else:
                await db.execute(delete(UserProductLine).where(UserProductLine.user_id == owned.user_id))
            await db.commit()
        with pytest.raises(PermissionError):
            if operation == "claim":
                await service().claim_messages(cached, identity)
            else:
                await service().ack_messages(cached, identity, batch.batch_id, 1)
    assert await snapshot(owned) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["claim", "ack"])
@pytest.mark.parametrize("change", ["paused", "stopped", "disabled", "role", "permission", "plugin_grant", "task_grant"])
async def test_cached_authority_revoked_while_real_row_lock_waits(delivery, operation, change):
    owned = delivery
    await append(owned, "secret never released after revoke")
    batch = await claim(owned) if operation == "ack" else None
    before = await snapshot(owned)
    async with owned.factory(binding=owned.binding) as cached:
        identity = await runtime_access.verify_runtime_identity(cached, owned.token, owned.binding)
        async with owned.factory(binding=owned.binding) as blocker:
            await blocker.scalar(select(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).with_for_update())
            async def waiting():
                with pytest.raises(PermissionError):
                    if batch:
                        await service().ack_messages(cached, identity, batch.batch_id, 1)
                    else:
                        await service().claim_messages(cached, identity)
                await cached.rollback()
            future = asyncio.create_task(waiting())
            try:
                for _ in range(200):
                    async with owned.engine.connect() as conn:
                        waiting_count = await conn.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%agent_plugin_installations%FOR UPDATE%'"))
                    if waiting_count:
                        break
                    await asyncio.sleep(.01)
                assert waiting_count, "message operation did not await real installation lock"
                query = {
                    "paused": update(AgentTask).where(AgentTask.task_id == owned.task_id).values(status="paused"),
                    "stopped": update(AgentRun).where(AgentRun.run_id == owned.run_id).values(status="stopped"),
                    "disabled": update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).values(enabled=False),
                    "role": update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(is_active=False),
                    "permission": update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == "capa").values(permission_level=0),
                    "plugin_grant": update(AgentPluginGrant).where(AgentPluginGrant.installation_id == owned.plugin_id).values(enabled=False),
                    "task_grant": delete(AgentTaskGrant).where(AgentTaskGrant.task_id == owned.task_id),
                }[change]
                await blocker.execute(query)
                await blocker.commit()
                await asyncio.wait_for(future, 10)
            finally:
                if not future.done():
                    future.cancel()
                await asyncio.gather(future, return_exceptions=True)
    assert await snapshot(owned) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["claim", "ack"])
@pytest.mark.parametrize("change", ["role", "grant", "generation", "policy"])
async def test_final_guard_rechecks_revocation_after_message_read(delivery, operation, change, monkeypatch):
    owned = delivery
    await append(owned, "must not escape after revocation")
    batch = await claim(owned) if operation == "ack" else None
    before = await snapshot(owned)
    reached, release = asyncio.Event(), asyncio.Event()
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        original_scalars = db.scalars
        async def read_barrier(statement, *args, **kwargs):
            result = await original_scalars(statement, *args, **kwargs)
            if "FROM agent_task_messages" in str(statement):
                reached.set()
                await release.wait()
            return result
        monkeypatch.setattr(db, "scalars", read_barrier)
        async def waiting():
            with pytest.raises(PermissionError):
                if batch:
                    await service().ack_messages(db, identity, batch.batch_id, 1)
                else:
                    await service().claim_messages(db, identity)
            await db.rollback()
        future = asyncio.create_task(waiting())
        try:
            await asyncio.wait_for(reached.wait(), 10)
            if change == "policy":
                monkeypatch.setattr(runtime_access, "TRUSTED_DELIVERY_DEPLOYMENTS", frozenset())
            elif change == "generation":
                async with owned.engine.begin() as conn:
                    await conn.execute(text("UPDATE public.tenants SET generation=generation+1 WHERE id=:id"), {"id": owned.binding.tenant_id})
            else:
                async with owned.factory(binding=owned.binding) as revoker:
                    query = (update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(is_active=False)
                        if change == "role" else delete(AgentTaskGrant).where(AgentTaskGrant.task_id == owned.task_id))
                    await revoker.execute(query)
                    await revoker.commit()
            release.set()
            await asyncio.wait_for(future, 10)
        finally:
            release.set()
            if not future.done():
                future.cancel()
            await asyncio.gather(future, return_exceptions=True)
            if change == "generation":
                async with owned.engine.begin() as conn:
                    await conn.execute(text("UPDATE public.tenants SET generation=:generation WHERE id=:id"), {"id": owned.binding.tenant_id, "generation": owned.binding.generation})
    assert await snapshot(owned) == before
