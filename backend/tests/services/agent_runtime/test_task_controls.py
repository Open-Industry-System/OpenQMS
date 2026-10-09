"""User controls and plugin finish, on committed real tenant connections."""
import asyncio
from dataclasses import replace
from types import MappingProxyType
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.agent_readonly_control import AgentTaskControl, AgentTaskUpdate
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant, AgentTaskMessage
from app.models.audit import AuditLog
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User
from app.services.agent_runtime import message_queue, run_dispatch, runtime_access, task_updates
from tests.services.agent_runtime.test_runtime_access import direct_caps, ready_owned
from tests.services.agent_runtime.test_runtime_messages import delivery, append, claim, ack, snapshot


def service():
    try:
        from app.services.agent_runtime import task_controls
    except ImportError:
        pytest.fail("task control service is not implemented")
    return task_controls


def request(**fields):
    try:
        from app.schemas.agent_control import TaskControl
    except ImportError:
        pytest.fail("strict task control schema is not implemented")
    return TaskControl(**fields)


async def scope(db, owned):
    from app.core.deps import RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    return RequestScope(FactoryScope(None, None), None, ProductLineScope("ALL", None), await db.get(User, owned.user_id))


async def control(owned, action, epoch=1, key=None, run_id="own"):
    async with owned.factory(binding=owned.binding) as db:
        return await service().control_task(db, await scope(db, owned), owned.task_id,
            request(action=action, run_id=owned.run_id if run_id == "own" else run_id,
                    expected_epoch=epoch, idempotency_key=key or uuid4().hex))


async def finish(owned, status="completed"):
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        return await service().finish_run(db, identity, status)


async def state(owned):
    async with owned.factory(binding=owned.binding) as db:
        task, run = await db.get(AgentTask, owned.task_id), await db.get(AgentRun, owned.run_id)
        controls = await db.scalar(select(func.count()).select_from(AgentTaskControl))
        updates = list((await db.execute(select(AgentTaskUpdate.kind, AgentTaskUpdate.object_id).order_by(AgentTaskUpdate.sequence))).all())
        audits = list((await db.execute(select(AuditLog.action, AuditLog.changed_fields).order_by(AuditLog.operated_at, AuditLog.log_id))).all())
        return (task.status, run.status, run.lease_epoch, run.claim_key, run.lease_expires_at,
                run.accepted_message_seq, controls, updates, audits)


def test_strict_control_and_finish_contracts():
    req = request(action="cancel", idempotency_key="blocked")
    assert req.run_id is None and req.expected_epoch is None
    for action in ("pause", "resume"):
        with pytest.raises(ValidationError):
            request(action=action, idempotency_key="missing")
    valid = dict(action="pause", run_id=uuid4(), expected_epoch=0, idempotency_key="key")
    for value in (True, "1", -1, 1.1):
        with pytest.raises(ValidationError):
            request(**{**valid, "expected_epoch": value})
    for field in ("executor_user_id", "task_id", "target_capa_id", "grants", "status", "checkpoint_id"):
        with pytest.raises(ValidationError):
            request(**valid, **{field: "spoof"})
    for fields in ({"action": "restart"}, {"idempotency_key": ""}, {"idempotency_key": "x"*101}, {"run_id": None}):
        with pytest.raises(ValidationError):
            request(**{**valid, **fields})
    from app.schemas.agent_control import RuntimeFinish
    for status in ("completed", "failed"):
        assert RuntimeFinish(status=status).status == status
    for fields in ({"status": "cancelled"}, {"status": "failed", "reason": "private"},
                   {"status": "completed", "idempotency_key": "retry"}):
        with pytest.raises(ValidationError):
            RuntimeFinish(**fields)


@pytest.mark.asyncio
async def test_pause_resume_same_run_preserves_accepted_proof_and_fences_old_tokens(delivery):
    owned = delivery
    await append(owned, "accepted private")
    await append(owned, "unaccepted private")
    batch = await claim(owned)
    await ack(owned, batch.batch_id, 1)
    paused = await control(owned, "pause", key="pause")
    assert paused.task_status == "paused" and paused.run_status == "paused" and paused.lease_epoch == 2
    after = await snapshot(owned)
    assert after[0] == 1 and after[1] == [(1, "accepted", batch.batch_id, 1), (2, "queued", None, None)]
    async with owned.factory(binding=owned.binding) as db:
        with pytest.raises(PermissionError):
            await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
    async with owned.factory(binding=owned.binding) as db:
        await message_queue.append_task_message(db, await db.get(AgentTask, owned.task_id), await scope(db, owned), "while paused", "paused")
    resumed = await control(owned, "resume", epoch=2)
    assert resumed.run_id == owned.run_id and resumed.run_status == "pending" and resumed.lease_epoch == 3
    async with owned.factory(binding=owned.binding) as db:
        with pytest.raises(PermissionError):
            await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
    async with owned.factory(binding=owned.binding) as db:
        newer = await run_dispatch.claim_run(db, owned.binding, owned.plugin_id, owned.secret, "resumed")
    owned.token = newer.token
    assert newer.lease_epoch == 4 and (await claim(owned)).accepted_sequence == 1


@pytest.mark.asyncio
async def test_control_retry_uses_original_parameters_and_current_authority_state(delivery):
    owned = delivery
    first = await control(owned, "pause", key="retry")
    before = await state(owned)
    again = await control(owned, "pause", key="retry")
    assert first.model_dump() == again.model_dump() and await state(owned) == before
    await control(owned, "resume", epoch=2)
    again = await control(owned, "pause", key="retry")
    assert again.control_id == first.control_id and again.task_status == "ready" and again.run_status == "pending"
    for params in (("cancel", 1, owned.run_id), ("pause", 2, owned.run_id), ("pause", 1, uuid4())):
        with pytest.raises(ValueError):
            await control(owned, params[0], params[1], "retry", params[2])
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == "capa").values(permission_level=0))
        await db.commit()
    with pytest.raises(PermissionError):
        await control(owned, "pause", key="retry")
    assert (await state(owned))[6] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["disabled", "version", "plugin_grant", "task_grant", "policy", "canonical"])
async def test_resume_requires_current_pinned_grants_and_trusted_delivery(delivery, monkeypatch, change):
    owned = delivery
    await control(owned, "pause")
    if change == "policy":
        monkeypatch.setattr(runtime_access, "TRUSTED_DELIVERY_DEPLOYMENTS", frozenset())
    elif change == "canonical":
        from app.services.agent.permissions import catalog
        from app.services.agent.permissions.types import ApprovalFloor
        monkeypatch.setattr(catalog, "CAPA_CAPABILITIES", MappingProxyType({k: replace(v, approval_floor=ApprovalFloor.DENY) for k,v in catalog.CAPA_CAPABILITIES.items()}))
    else:
        query = {
            "disabled": update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).values(enabled=False),
            "version": update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).values(plugin_version="new"),
            "plugin_grant": delete(AgentPluginGrant).where(AgentPluginGrant.installation_id == owned.plugin_id),
            "task_grant": delete(AgentTaskGrant).where(AgentTaskGrant.task_id == owned.task_id),
        }[change]
        async with owned.factory(binding=owned.binding) as db:
            await db.execute(query); await db.commit()
    before = await state(owned)
    with pytest.raises(PermissionError):
        await control(owned, "resume", epoch=2)
    assert await state(owned) == before
    # Cancellation still belongs to the user and does not need runtime grants.
    assert (await control(owned, "cancel", epoch=2)).task_status == "cancelled"


@pytest.mark.asyncio
async def test_disabled_plugin_allows_pause_and_cancel_even_expired_lease(delivery):
    owned = delivery
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).values(enabled=False))
        await db.execute(update(AgentRun).where(AgentRun.run_id == owned.run_id).values(lease_expires_at=None))
        await db.commit()
    await control(owned, "pause")
    await control(owned, "cancel", epoch=2)
    assert (await state(owned))[:5] == ("cancelled", "stopped", 3, None, None)


@pytest.mark.asyncio
async def test_stale_run_epoch_and_terminal_controls_have_no_side_effects(delivery):
    owned = delivery
    before = await state(owned)
    for run_id, epoch in ((uuid4(), 1), (owned.run_id, 0), (None, None)):
        with pytest.raises(ValueError):
            await control(owned, "cancel", epoch=epoch, run_id=run_id)
        assert await state(owned) == before
    await control(owned, "cancel")
    before = await state(owned)
    for action in ("pause", "resume", "cancel"):
        with pytest.raises(ValueError):
            await control(owned, action, epoch=2)
    assert await state(owned) == before


@pytest.mark.asyncio
async def test_blocked_task_only_cancel_without_run(ready_owned):
    owned = ready_owned
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(delete(AgentRun).where(AgentRun.run_id == owned.run_id))
        await db.execute(update(AgentTask).where(AgentTask.task_id == owned.task_id).values(status="blocked_capability"))
        await db.commit()
    result = await control(owned, "cancel", epoch=None, run_id=None)
    assert result.task_status == "cancelled" and result.run_id is None and result.lease_epoch is None
    with pytest.raises(ValueError):
        await control(owned, "cancel", epoch=None, run_id=None, key="other")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed"])
async def test_finish_commits_synchronized_terminal_state_and_invalidates_retry(delivery, status):
    owned = delivery
    await append(owned, "accepted")
    batch = await claim(owned)
    await ack(owned, batch.batch_id, 1)
    before = await snapshot(owned)
    result = await finish(owned, status)
    assert result.task_status == result.run_status == status and result.lease_epoch == 2
    assert (await state(owned))[:6] == (status, status, 2, None, None, 1)
    assert await snapshot(owned) == before
    with pytest.raises(PermissionError):
        await finish(owned, status)
    after = await state(owned)
    assert len([u for u in after[7] if u[0] == "finish"]) == 1
    audit = [a for a in after[8] if a[0] == "FINISH_AGENT_RUN"]
    assert len(audit) == 1 and "accepted" not in str(audit)
    if status == "failed":
        assert audit[0][1]["failure_code"] == "plugin_failure"


@pytest.mark.asyncio
@pytest.mark.parametrize("input_state", ["queued", "claimed", "gap", "watermark", "above_watermark"])
async def test_success_rejects_actual_unconfirmed_or_inconsistent_inputs_unchanged(delivery, input_state):
    owned = delivery
    await append(owned, "first")
    await append(owned, "second")
    if input_state != "queued":
        batch = await claim(owned)
        if input_state != "claimed":
            await ack(owned, batch.batch_id, 2)
            async with owned.factory(binding=owned.binding) as db:
                if input_state == "gap":
                    await db.execute(delete(AgentTaskMessage).where(AgentTaskMessage.task_id == owned.task_id, AgentTaskMessage.sequence == 1))
                else:
                    await db.execute(update(AgentRun).where(AgentRun.run_id == owned.run_id).values(accepted_message_seq=3 if input_state == "watermark" else 1))
                await db.commit()
    before, messages = await state(owned), await snapshot(owned)
    with pytest.raises(ValueError):
        await finish(owned)
    assert await state(owned) == before and await snapshot(owned) == messages


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cancel", "failed"])
async def test_unconfirmed_termination_retains_input_and_accepted_batch_proof(delivery, action):
    owned = delivery
    await append(owned, "accepted input")
    await append(owned, "unconfirmed input")
    batch = await claim(owned)
    await ack(owned, batch.batch_id, 1)
    await append(owned, "queued input")
    before_messages = await snapshot(owned)
    if action == "cancel":
        result = await control(owned, "cancel", key="terminate")
    else:
        await finish(owned, "failed")
    accepted, rows, _ = await snapshot(owned)
    assert accepted == 1 and rows[0] == (1, "accepted", batch.batch_id, 1)
    assert rows[1] == (2, "claimed", batch.batch_id, 1)
    assert rows[2] == (3, "queued", None, None)
    assert await snapshot(owned) == before_messages
    after = await state(owned)
    assert after[:6] == ("cancelled" if action == "cancel" else "failed",
        "stopped" if action == "cancel" else "failed", 2, None, None, 1)
    async with owned.factory(binding=owned.binding) as db:
        with pytest.raises(PermissionError):
            await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
    if action == "cancel":
        assert len([u for u in after[7] if u[0] == "control"]) == 1
        assert len([a for a in after[8] if a[0] == "CONTROL_AGENT_TASK"]) == 1
        assert after[6] == 1
        again = await control(owned, "cancel", key="terminate")
        assert again.model_dump() == result.model_dump()
        assert await state(owned) == after
        assert await snapshot(owned) == before_messages
    async with owned.factory(binding=owned.binding) as db:
        assert list((await db.scalars(select(AgentTaskMessage.content).where(AgentTaskMessage.task_id == owned.task_id).order_by(AgentTaskMessage.sequence))).all()) == ["accepted input", "unconfirmed input", "queued input"]


async def wait_lock(owned, table):
    for _ in range(300):
        async with owned.engine.connect() as conn:
            count = await conn.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE :pattern"), {"pattern": "%"+table+"%FOR UPDATE%"})
        if count:
            return
        await asyncio.sleep(.01)
    pytest.fail("no actual PostgreSQL lock wait observed for "+table)


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed", [False, True])
async def test_append_commit_while_finish_waits_rejects_new_input_without_side_effect(delivery, claimed):
    owned = delivery
    await append(owned, "old accepted")
    batch = await claim(owned)
    await ack(owned, batch.batch_id, 1)
    async with owned.factory(binding=owned.binding) as writer:
        task = await writer.scalar(select(AgentTask).where(AgentTask.task_id == owned.task_id).with_for_update())
        original_commit = writer.commit
        async def hold_commit():
            await writer.flush()
        writer.commit = hold_commit
        await message_queue.append_task_message(writer, task, await scope(writer, owned), "new input", "new-input")
        if claimed:
            # Same writer simulates a real newly claimed marker without acquiring INSTALL out of order.
            await writer.execute(update(AgentTaskMessage).where(AgentTaskMessage.task_id == owned.task_id, AgentTaskMessage.sequence == 2).values(state="claimed", delivery_batch_id=uuid4(), delivery_epoch=1))
        async def waiting():
            with pytest.raises(ValueError):
                await finish(owned)
        future = asyncio.create_task(waiting())
        try:
            await wait_lock(owned, "agent_tasks")
            await original_commit()
            expected = await state(owned)
            await asyncio.wait_for(future, 10)
        finally:
            if not future.done():
                future.cancel()
            await asyncio.gather(future, return_exceptions=True)
    assert await state(owned) == expected
    assert (await snapshot(owned))[1][1][1] == ("claimed" if claimed else "queued")


@pytest.mark.asyncio
async def test_finish_commit_while_append_waits_rejects_message_without_side_effect(delivery):
    owned = delivery
    await append(owned, "old accepted")
    batch = await claim(owned)
    await ack(owned, batch.batch_id, 1)
    async with owned.factory(binding=owned.binding) as writer:
        identity = await runtime_access.verify_runtime_identity(writer, owned.token, owned.binding)
        original_commit = writer.commit
        async def hold_commit():
            await writer.flush()
        writer.commit = hold_commit
        await service().finish_run(writer, identity, "completed")
        async def waiting():
            async with owned.factory(binding=owned.binding) as db:
                with pytest.raises(ValueError):
                    await message_queue.append_task_message(db, await db.get(AgentTask, owned.task_id), await scope(db, owned), "too late", "late")
        future = asyncio.create_task(waiting())
        try:
            await wait_lock(owned, "agent_tasks")
            await original_commit()
            expected = await state(owned)
            await asyncio.wait_for(future, 10)
        finally:
            if not future.done():
                future.cancel()
            await asyncio.gather(future, return_exceptions=True)
    assert await state(owned) == expected and len((await snapshot(owned))[1]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["role", "permission", "executor", "installation", "run_task"])
async def test_control_rechecks_authority_and_association_after_install_lock_wait(delivery, change):
    owned = delivery
    before = await state(owned)
    async with owned.factory(binding=owned.binding) as holder:
        await holder.scalar(select(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).with_for_update())
        if change in {"executor", "installation", "run_task"}:
            task = await holder.get(AgentTask, owned.task_id)
            if change == "executor":
                other = User(user_id=uuid4(), username=uuid4().hex, password_hash="fixture", role_id=owned.role_id, legacy_role="admin", is_active=True)
            elif change == "installation":
                other = AgentPluginInstallation(installation_id=uuid4(), plugin_key="other", plugin_version="1", manifest={}, secret_hash="fixture", enabled=False, created_by=owned.user_id)
            else:
                other = AgentTask(initiator_id=owned.user_id, executor_user_id=owned.user_id, preferred_installation_id=owned.plugin_id, factory_id=task.factory_id, target_capa_id=task.target_capa_id, status="ready", request_key=uuid4().hex)
            holder.add(other); await holder.flush()
        future = asyncio.create_task(control(owned, "pause"))
        try:
            await wait_lock(owned, "agent_plugin_installations")
            query = {
                "role": update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(is_active=False),
                "permission": update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == "capa").values(permission_level=0),
                "executor": update(AgentTask).where(AgentTask.task_id == owned.task_id).values(executor_user_id=other.user_id) if change == "executor" else None,
                "installation": update(AgentTask).where(AgentTask.task_id == owned.task_id).values(preferred_installation_id=other.installation_id) if change == "installation" else None,
                "run_task": update(AgentRun).where(AgentRun.run_id == owned.run_id).values(task_id=other.task_id) if change == "run_task" else None,
            }[change]
            await holder.execute(query); await holder.commit()
            with pytest.raises((PermissionError, LookupError, ValueError)):
                await asyncio.wait_for(future, 10)
        finally:
            if not future.done():
                future.cancel()
            await asyncio.gather(future, return_exceptions=True)
    assert (await state(owned))[6:] == before[6:]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["control", "finish"])
async def test_update_flush_then_fault_rolls_back_whole_operation(delivery, operation, monkeypatch):
    owned = delivery
    await append(owned, "accepted")
    batch = await claim(owned); await ack(owned, batch.batch_id, 1)
    before = await state(owned)
    original = task_updates.append_update
    async def fail_after_flush(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("injected transaction failure")
    monkeypatch.setattr(task_updates, "append_update", fail_after_flush)
    with pytest.raises(RuntimeError, match="injected"):
        if operation == "control":
            await control(owned, "pause")
        else:
            await finish(owned)
    assert await state(owned) == before


@pytest.mark.asyncio
async def test_plain_session_cannot_control_by_forged_binding(delivery):
    owned = delivery
    async with AsyncSession(owned.engine) as db:
        db.info["tenant_binding"] = owned.binding
        with pytest.raises(PermissionError):
            await service().control_task(db, await scope(db, owned), owned.task_id,
                request(action="pause", run_id=owned.run_id, expected_epoch=1, idempotency_key="spoof"))


@pytest.mark.asyncio
@pytest.mark.parametrize("actions", [("pause", "pause"), ("pause", "cancel"), ("resume", "cancel")])
async def test_competing_controls_serialize_one_effect_for_same_expected_epoch(delivery, actions):
    owned = delivery
    epoch = 1
    if "resume" in actions:
        await control(owned, "pause")
        epoch = 2
    before = await state(owned)
    async def one(action):
        try:
            return await control(owned, action, epoch=epoch)
        except ValueError:
            return None
    results = await asyncio.gather(*(one(action) for action in actions))
    assert len([r for r in results if r is not None]) == 1
    after = await state(owned)
    assert after[2] == epoch + 1 and after[6] == before[6]+1
    assert len(after[7]) == len(before[7])+1 and len(after[8]) == len(before[8])+1


@pytest.mark.asyncio
async def test_parallel_identical_key_has_one_control_audit_update(delivery):
    owned = delivery
    before = await state(owned)
    results = await asyncio.gather(control(owned, "pause", key="parallel"), control(owned, "pause", key="parallel"))
    assert results[0].model_dump() == results[1].model_dump()
    after = await state(owned)
    assert after[6] == 1 and len(after[7]) == len(before[7])+1 and len(after[8]) == len(before[8])+1
    assert after[8][-1][0] == "CONTROL_AGENT_TASK"
    assert set(after[8][-1][1]) == {"control_id", "task_id", "run_id", "action", "lease_epoch"}


@pytest.mark.asyncio
@pytest.mark.parametrize("membership", ["factory", "line"])
async def test_control_membership_revoked_while_task_lock_waits(delivery, membership):
    from app.models.factory import Factory, UserFactory
    from app.models.role import UserProductLine
    owned = delivery
    async with owned.factory(binding=owned.binding) as db:
        task = await db.get(AgentTask, owned.task_id)
        other = Factory(name="Default A", code="control-A-"+uuid4().hex[:8])
        db.add(other); await db.flush()
        await db.execute(update(User).where(User.user_id == owned.user_id).values(factory_id=other.id))
        await db.execute(update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(bypass_row_level_security=False))
        await db.execute(update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == "group").values(permission_level=0))
        await db.execute(delete(UserFactory).where(UserFactory.user_id == owned.user_id))
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id == owned.user_id))
        db.add_all([UserFactory(user_id=owned.user_id, factory_id=task.factory_id), UserFactory(user_id=owned.user_id, factory_id=other.id), UserProductLine(user_id=owned.user_id, product_line_code="DC-DC-100")])
        await db.commit()
        target_factory = task.factory_id
    before = await state(owned)
    async with owned.factory(binding=owned.binding) as holder:
        await holder.scalar(select(AgentTask).where(AgentTask.task_id == owned.task_id).with_for_update())
        future = asyncio.create_task(control(owned, "pause"))
        try:
            await wait_lock(owned, "agent_tasks")
            if membership == "factory":
                query = delete(UserFactory).where(UserFactory.user_id == owned.user_id, UserFactory.factory_id == target_factory)
            else:
                query = delete(UserProductLine).where(UserProductLine.user_id == owned.user_id)
            await holder.execute(query); await holder.commit()
            with pytest.raises((PermissionError, LookupError)):
                await asyncio.wait_for(future, 10)
        finally:
            if not future.done():
                future.cancel()
            await asyncio.gather(future, return_exceptions=True)
    assert await state(owned) == before


@pytest.mark.asyncio
async def test_pause_during_actual_rr_context_read_denies_receipt_audit_and_content(delivery, monkeypatch):
    import app.database as database
    from sqlalchemy import event
    from sqlalchemy.util import await_only
    from app.models.agent_runtime_event import AgentProjectionReceipt
    from app.services.agent_runtime import readonly_delivery
    owned = delivery
    monkeypatch.setattr(database, "engine", owned.engine)
    reached, release = asyncio.Event(), asyncio.Event()
    async def stop_snapshot():
        reached.set(); await release.wait()
    def intercept(conn, cursor, statement, parameters, ctx, many):
        if "FROM capa_root_cause_verification" in statement:
            await_only(stop_snapshot())
    event.listen(owned.engine.sync_engine, "before_cursor_execute", intercept)
    async def read():
        async with owned.factory(binding=owned.binding) as db:
            identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
            with pytest.raises(PermissionError):
                await readonly_delivery.get_capa_context(db, identity)
    future = asyncio.create_task(read())
    try:
        await asyncio.wait_for(reached.wait(), 10)
        await control(owned, "pause")
        release.set(); await asyncio.wait_for(future, 10)
    finally:
        release.set(); event.remove(owned.engine.sync_engine, "before_cursor_execute", intercept)
        if not future.done():
            future.cancel()
        await asyncio.gather(future, return_exceptions=True)
    async with owned.factory(binding=owned.binding) as db:
        assert await db.scalar(select(func.count()).select_from(AgentProjectionReceipt)) == 0
        assert await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "QUERY_AGENT_CAPA_CONTEXT")) == 0


@pytest.mark.asyncio
async def test_output_committed_before_pause_is_retained_and_old_identity_writes_deny(delivery):
    from app.models.agent_runtime_event import AgentRunEvent
    from app.services.agent_runtime import readonly_delivery, runtime_messages
    from app.schemas.agent_runtime import RuntimeEventCreate
    owned = delivery
    body = RuntimeEventCreate(idempotency_key="progress", event_type="progress", payload={"stage": "D4"})
    async with owned.factory(binding=owned.binding) as cached:
        identity = await runtime_access.verify_runtime_identity(cached, owned.token, owned.binding)
        output = await readonly_delivery.record_event(cached, identity, body)
        await control(owned, "pause")
        for call in (lambda: readonly_delivery.record_event(cached, identity, body),
                     lambda: runtime_messages.claim_messages(cached, identity),
                     lambda: service().finish_run(cached, identity, "failed")):
            with pytest.raises(PermissionError):
                await call()
            await cached.rollback()
    async with owned.factory(binding=owned.binding) as db:
        assert await db.get(AgentRunEvent, output["event_id"]) is not None
        assert await db.scalar(select(func.count()).select_from(AgentRunEvent)) == 1


@pytest.mark.asyncio
async def test_unrelated_integrity_error_propagates_and_rolls_back(delivery):
    owned = delivery
    before = await state(owned)
    async with owned.factory(binding=owned.binding) as db:
        current_scope = await scope(db, owned)
        db.add(AgentTaskMessage(task_id=owned.task_id, author_id=owned.user_id, sequence=0, content="invalid unrelated", idempotency_key="bad"))
        with pytest.raises(IntegrityError):
            await service().control_task(db, current_scope, owned.task_id,
                request(action="pause", run_id=owned.run_id, expected_epoch=1, idempotency_key="not-retry"))
        await db.rollback()
    assert await state(owned) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["pause", "cancel", "retry", "resume"])
async def test_final_control_read_rechecks_revoked_user_before_mutation_or_retry(delivery, monkeypatch, action):
    owned = delivery
    if action in {"retry", "resume"}:
        await control(owned, "pause", key="retry")
    before = await state(owned)
    reached, release = asyncio.Event(), asyncio.Event()
    async with owned.factory(binding=owned.binding) as db:
        actor = await scope(db, owned)
        original_scalar, original_scalars = db.scalar, db.scalars
        armed = False
        grant_reads = 0
        async def stop_run_read(statement, *args, **kwargs):
            nonlocal armed
            result = await original_scalar(statement, *args, **kwargs)
            if "FROM agent_task_controls" in str(statement):
                armed = True
            elif armed and action != "resume" and "FROM agent_runs" in str(statement) and "FOR UPDATE" not in str(statement):
                armed = False
                reached.set(); await release.wait()
            return result
        async def stop_grant_read(statement, *args, **kwargs):
            nonlocal grant_reads
            result = await original_scalars(statement, *args, **kwargs)
            if armed and action == "resume" and "FROM agent_task_grants" in str(statement):
                grant_reads += 1
                if grant_reads == 2:
                    reached.set(); await release.wait()
            return result
        monkeypatch.setattr(db, "scalar", stop_run_read)
        monkeypatch.setattr(db, "scalars", stop_grant_read)
        command = request(action="pause" if action == "retry" else action,
            run_id=owned.run_id, expected_epoch=2 if action == "resume" else 1,
            idempotency_key="retry" if action == "retry" else "final")
        async def waiting():
            with pytest.raises(PermissionError):
                await service().control_task(db, actor, owned.task_id, command)
            await db.rollback()
        future = asyncio.create_task(waiting())
        try:
            await asyncio.wait_for(reached.wait(), 10)
            async with owned.factory(binding=owned.binding) as revoker:
                await revoker.execute(update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(is_active=False)); await revoker.commit()
            release.set(); await asyncio.wait_for(future, 10)
        finally:
            release.set()
            if not future.done():
                future.cancel()
            await asyncio.gather(future, return_exceptions=True)
    assert await state(owned) == before


@pytest.mark.asyncio
async def test_final_finish_input_read_rechecks_revocation_before_dirty_changes(delivery, monkeypatch):
    owned = delivery
    before = await state(owned)
    reached, release = asyncio.Event(), asyncio.Event()
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        original_execute = db.execute
        read_count = 0
        async def stop_input_read(statement, *args, **kwargs):
            nonlocal read_count
            result = await original_execute(statement, *args, **kwargs)
            if "FROM agent_task_messages" in str(statement):
                read_count += 1
                if read_count == 2:
                    reached.set(); await release.wait()
            return result
        monkeypatch.setattr(db, "execute", stop_input_read)
        async def waiting():
            with pytest.raises(PermissionError):
                await service().finish_run(db, identity, "completed")
            await db.rollback()
        future = asyncio.create_task(waiting())
        try:
            await asyncio.wait_for(reached.wait(), 10)
            async with owned.factory(binding=owned.binding) as revoker:
                await revoker.execute(update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(is_active=False)); await revoker.commit()
            release.set(); await asyncio.wait_for(future, 10)
        finally:
            release.set()
            if not future.done():
                future.cancel()
            await asyncio.gather(future, return_exceptions=True)
    assert await state(owned) == before
