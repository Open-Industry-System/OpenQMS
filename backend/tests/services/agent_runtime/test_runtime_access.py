"""Dedicated lease-bound runtime identity and claim using current server authority."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
import uuid

import pytest
import pytest_asyncio
from jose import jwt
from pydantic import ValidationError
from sqlalchemy import delete, select, update

from app.config import settings
from app.core.security import create_access_token, create_platform_admin_token, create_refresh_token, hash_password
from app.models.agent_plugin import AgentPluginGrant, AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask, AgentTaskGrant
from app.models.role import RoleDefinition, RolePermission
from app.models.user import User
from app.services.agent.permissions import catalog
from app.services.agent.permissions.types import ApprovalFloor

SUMMARY = "capa.d4.summary.masked.v1"


def dispatch():
    try:
        from app.services.agent_runtime import run_dispatch
    except ImportError:
        pytest.fail("runtime claim service is not implemented")
    return run_dispatch


def access():
    try:
        from app.services.agent_runtime import runtime_access
    except ImportError:
        pytest.fail("runtime identity service is not implemented")
    return runtime_access


@pytest.fixture
def direct_caps(monkeypatch):
    monkeypatch.setattr(catalog, "CAPA_CAPABILITIES", MappingProxyType({
        key: replace(spec, approval_floor=ApprovalFloor.DIRECT) if spec.kind == "context" else spec
        for key, spec in catalog.CAPA_CAPABILITIES.items()}))


@pytest_asyncio.fixture
async def pending(db, active_run, monkeypatch):
    monkeypatch.setattr(settings, "TENANT_MODE", "single")
    run, task, plugin, user = active_run
    run.status = "pending"
    plugin.secret_hash = hash_password("runtime-fixture-secret-long")
    grant = dict(capability_id=SUMMARY, factory_ids=[str(task.factory_id)],
        object_ids=[str(task.target_capa_id)], product_line_codes=["DC-DC-100"])
    db.add(AgentPluginGrant(grant_id=uuid.uuid4(), installation_id=plugin.installation_id, enabled=True,
        granted_by=user.user_id, **grant))
    db.add(AgentTaskGrant(task_id=task.task_id, access_kind="read", **grant))
    await db.flush()
    return run, task, plugin, user


async def claim(db, pending, key="claim-1"):
    return await dispatch().claim_run(db, None, pending[2].installation_id,
        "runtime-fixture-secret-long", key)


def test_claim_schema_is_bounded_and_rejects_caller_authority():
    try:
        from app.schemas.agent_runtime import RunClaim
    except ImportError:
        pytest.fail("runtime schemas are not implemented")
    fields = dict(installation_id=uuid.uuid4(), secret="s"*20, request_key="retry")
    assert RunClaim(**fields).request_key == "retry"
    for name in ("user", "actor", "scope", "schema", "report_id", "tenant_id", "controlled_egress"):
        with pytest.raises(ValidationError):
            RunClaim(**fields, **{name: "spoof"})
    for name, value in (("secret", "s"*19), ("secret", "s"*201), ("request_key", ""),
                         ("request_key", "s"*101), ("secret", 123)):
        with pytest.raises(ValidationError):
            RunClaim(**{**fields, name: value})


@pytest.mark.asyncio
async def test_claim_has_lease_idempotency_and_no_business_object_selector(db, pending, direct_caps):
    result = await claim(db, pending)
    assert set(result.model_dump()) == {"run_id", "task_id", "token", "lease_epoch", "lease_expires_at", "accepted_message_seq", "has_resume_checkpoint"}
    assert result.run_id == pending[0].run_id and result.lease_epoch == 1
    assert 0 < (result.lease_expires_at - datetime.now(UTC)).total_seconds() <= 300
    claims = jwt.get_unverified_claims(result.token)
    assert claims["exp"] <= result.lease_expires_at.timestamp()
    retry = await claim(db, pending)
    assert retry.run_id == result.run_id and retry.lease_epoch == result.lease_epoch
    with pytest.raises(LookupError):
        await claim(db, pending, "different-key")
    identity = await access().verify_runtime_identity(db, result.token, None)
    assert identity.task.task_id == pending[1].task_id
    assert identity.scope.user.user_id == pending[3].user_id


@pytest.mark.asyncio
async def test_default_deny_claim_refuses_before_any_delivery(db, pending):
    with pytest.raises(PermissionError):
        await claim(db, pending)
    assert pending[0].status == "pending" and pending[0].lease_epoch == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["plugin", "user", "role", "permission", "taskgrant", "plugingrant", "expiry", "version", "task", "run"])
async def test_runtime_revocation_reloads_all_cached_authority(db, pending, direct_caps, change):
    result = await claim(db, pending)
    identity = await access().verify_runtime_identity(db, result.token, None)
    run, task, plugin, user = pending
    queries = {
        "plugin": update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == plugin.installation_id).values(enabled=False),
        "user": update(User).where(User.user_id == user.user_id).values(is_active=False),
        "role": update(RoleDefinition).where(RoleDefinition.id == user.role_id).values(is_active=False),
        "permission": update(RolePermission).where(RolePermission.role_id == user.role_id, RolePermission.module == "capa").values(permission_level=0),
        "taskgrant": delete(AgentTaskGrant).where(AgentTaskGrant.task_id == task.task_id),
        "plugingrant": update(AgentPluginGrant).where(AgentPluginGrant.installation_id == plugin.installation_id).values(enabled=False),
        "expiry": update(AgentRun).where(AgentRun.run_id == run.run_id).values(lease_expires_at=datetime.now(UTC)-timedelta(seconds=1)),
        "version": update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == plugin.installation_id).values(plugin_version="2.0"),
        "task": update(AgentTask).where(AgentTask.task_id == task.task_id).values(status="paused"),
        "run": update(AgentRun).where(AgentRun.run_id == run.run_id).values(status="stopped"),
    }
    await db.execute(queries[change].execution_options(synchronize_session=False))
    with pytest.raises(PermissionError):
        await access().refresh_runtime_identity(db, identity)


@pytest.mark.asyncio
async def test_nullable_legacy_lease_never_runtime_authority(db, pending, direct_caps):
    result = await claim(db, pending)
    await db.execute(update(AgentRun).where(AgentRun.run_id == pending[0].run_id)
        .values(lease_expires_at=None).execution_options(synchronize_session=False))
    with pytest.raises(PermissionError):
        await access().verify_runtime_identity(db, result.token, None)


@pytest.mark.asyncio
async def test_reclaim_fences_old_token_and_same_key_cannot_select_another_run(db, pending, direct_caps):
    result = await claim(db, pending)
    await db.execute(update(AgentRun).where(AgentRun.run_id == result.run_id)
        .values(lease_expires_at=datetime.now(UTC)-timedelta(seconds=1)))
    reclaimed = await claim(db, pending, "new-claim")
    assert reclaimed.run_id == result.run_id and reclaimed.lease_epoch == 2
    with pytest.raises(PermissionError):
        await access().verify_runtime_identity(db, result.token, None)
    assert (await access().verify_runtime_identity(db, reclaimed.token, None)).run.lease_epoch == 2


@pytest.mark.asyncio
async def test_all_required_capabilities_and_grant_expiry_are_checked(db, pending, direct_caps):
    run, task, plugin, _ = pending
    plugin.manifest = {**plugin.manifest, "required_capabilities": [SUMMARY, "capa.d4.verifications.masked.v1"]}
    await db.flush()
    with pytest.raises(PermissionError):
        await claim(db, pending)
    plugin.manifest = {**plugin.manifest, "required_capabilities": [SUMMARY]}
    await db.flush()
    await db.execute(update(AgentTaskGrant).where(AgentTaskGrant.task_id == task.task_id)
        .values(expires_at=datetime.now(UTC)-timedelta(seconds=1)))
    with pytest.raises(PermissionError):
        await claim(db, pending)


@pytest.mark.asyncio
async def test_user_platform_refresh_and_spoofed_run_claims_reject(db, pending, direct_caps):
    result = await claim(db, pending)
    tokens = [create_access_token({"sub": str(pending[3].user_id)}),
        create_platform_admin_token(str(pending[3].user_id)), create_refresh_token(str(pending[3].user_id))[0]]
    claims = jwt.get_unverified_claims(result.token)
    for overrides in ({"tenant_generation": 1}, {"installation_id": str(uuid.uuid4())},
                      {"plugin_version": "other"}, {"aud": ["openqms-agent-runtime"]}):
        tokens.append(jwt.encode({**claims, **overrides}, settings.SECRET_KEY, algorithm=settings.ALGORITHM))
    for token in tokens:
        with pytest.raises(PermissionError):
            await access().verify_runtime_identity(db, token, None)


@pytest.mark.asyncio
async def test_delivery_policy_empty_and_manifest_cannot_self_certify(db, pending, direct_caps, monkeypatch):
    result = await claim(db, pending)
    identity = await access().verify_runtime_identity(db, result.token, None)
    with pytest.raises(PermissionError):
        access().require_delivery(identity, "internal", "masked")
    deployment = ("single", pending[2].installation_id, pending[2].plugin_version)
    monkeypatch.setattr(access(), "TRUSTED_DELIVERY_DEPLOYMENTS", frozenset({deployment}))
    access().require_delivery(identity, "internal", "masked")
    with pytest.raises(PermissionError):
        access().require_delivery(identity, "restricted", "masked")
    access().require_delivery(identity, "restricted", "raw", controlled_egress=True)
    with pytest.raises(PermissionError):
        access().require_delivery(identity, "internal", "raw")


@pytest_asyncio.fixture
async def ready_owned(committed_runtime, direct_caps):
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as db:
        task = await db.get(AgentTask, owned.task_id)
        plugin = await db.get(AgentPluginInstallation, owned.plugin_id)
        plugin.manifest = {"protocol_versions": ["1"], "required_capabilities": [SUMMARY]}
        await db.execute(update(AgentRun).where(AgentRun.run_id == owned.run_id).values(status="pending"))
        grant = dict(capability_id=SUMMARY, factory_ids=[str(task.factory_id)], object_ids=[str(task.target_capa_id)], product_line_codes=["DC-DC-100"])
        db.add(AgentPluginGrant(grant_id=uuid.uuid4(), installation_id=owned.plugin_id, enabled=True, granted_by=owned.user_id, **grant))
        db.add(AgentTaskGrant(task_id=owned.task_id, access_kind="read", **grant))
        await db.commit()
    return owned


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [True, False])
async def test_real_two_connection_claim_serialization(ready_owned, same_key):
    owned = ready_owned
    async def one(key):
        async with owned.factory(binding=owned.binding) as db:
            try:
                return await dispatch().claim_run(db, owned.binding, owned.plugin_id, owned.secret, key)
            except LookupError:
                return None
    results = await asyncio.gather(one("key"), one("key" if same_key else "other"))
    assert len([r for r in results if r is not None]) == (2 if same_key else 1)
    assert {r.lease_epoch for r in results if r is not None} == {1}


@pytest.mark.asyncio
async def test_plain_session_info_spoof_cannot_claim(ready_owned):
    from sqlalchemy.ext.asyncio import AsyncSession
    owned = ready_owned
    async with AsyncSession(owned.engine) as db:
        db.info["tenant_binding"] = owned.binding
        with pytest.raises(PermissionError):
            await dispatch().claim_run(db, owned.binding, owned.plugin_id, owned.secret, "spoof")


@pytest.mark.asyncio
async def test_real_rotation_while_claim_waits_denies_old_secret(ready_owned):
    from app.services.agent_runtime.plugin_registry import rotate_plugin_secret
    owned = ready_owned
    async with owned.factory(binding=owned.binding) as blocker:
        actor = await blocker.get(User, owned.user_id)
        await rotate_plugin_secret(blocker, actor, owned.plugin_id)
        started = asyncio.Event()
        async def waiting():
            async with owned.factory(binding=owned.binding) as db:
                started.set()
                with pytest.raises(PermissionError):
                    await dispatch().claim_run(db, owned.binding, owned.plugin_id, owned.secret, "rotation")
        future = asyncio.create_task(waiting())
        await started.wait()
        # Actual lock acquisition wait is observed in PostgreSQL, never guessed via sleeps.
        from sqlalchemy import text
        for _ in range(100):
            async with owned.engine.connect() as control:
                waiting_count = await control.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%agent_plugin_installations%FOR UPDATE%'"))
            if waiting_count:
                break
            await asyncio.sleep(.01)
        assert waiting_count, "claim did not wait on installation lock"
        await blocker.commit()
        await asyncio.wait_for(future, 10)


@pytest.mark.asyncio
async def test_same_claim_key_cannot_move_to_second_pending_task(ready_owned):
    owned = ready_owned
    async with owned.factory(binding=owned.binding) as db:
        original = await db.get(AgentTask, owned.task_id)
        task = AgentTask(initiator_id=owned.user_id, executor_user_id=owned.user_id,
            preferred_installation_id=owned.plugin_id, target_capa_id=original.target_capa_id,
            factory_id=original.factory_id, request_key="second-task", status="ready")
        db.add(task)
        await db.flush()
        run = AgentRun(task_id=task.task_id, installation_id=owned.plugin_id, plugin_version="1.0.0", status="pending")
        db.add(run)
        db.add(AgentTaskGrant(task_id=task.task_id, access_kind="read", capability_id=SUMMARY,
            factory_ids=[str(task.factory_id)], object_ids=[str(task.target_capa_id)], product_line_codes=["DC-DC-100"]))
        await db.commit()
        second_id = run.run_id
    async def one():
        async with owned.factory(binding=owned.binding) as db:
            return await dispatch().claim_run(db, owned.binding, owned.plugin_id, owned.secret, "same")
    results = await asyncio.gather(one(), one())
    assert len({r.run_id for r in results}) == 1
    claimed_id = results[0].run_id
    async with owned.factory(binding=owned.binding) as db:
        await db.execute(update(AgentRun).where(AgentRun.run_id == claimed_id).values(status="completed"))
        await db.commit()
    async with owned.factory(binding=owned.binding) as db:
        with pytest.raises(LookupError):
            await dispatch().claim_run(db, owned.binding, owned.plugin_id, owned.secret, "same")
        assert await db.scalar(select(AgentRun.status).where(AgentRun.run_id == (second_id if claimed_id == owned.run_id else owned.run_id))) == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("membership", ["factory", "line"])
async def test_runtime_revocation_of_target_b_with_default_factory_a(db, pending, direct_caps, membership):
    from app.models.factory import Factory, UserFactory
    from app.models.role import UserProductLine
    run, task, plugin, user = pending
    # B is the target; default A must not revive a removed B membership.
    factory_a = Factory(id=uuid.uuid4(), name="Factory A", code="runtime-A-"+uuid.uuid4().hex[:8])
    db.add(factory_a)
    await db.flush()
    await db.execute(update(User).where(User.user_id == user.user_id).values(factory_id=factory_a.id))
    await db.execute(update(RoleDefinition).where(RoleDefinition.id == user.role_id).values(bypass_row_level_security=False))
    await db.execute(update(RolePermission).where(RolePermission.role_id == user.role_id, RolePermission.module == "group").values(permission_level=0))
    db.add(UserFactory(user_id=user.user_id, factory_id=factory_a.id))
    db.add(UserFactory(user_id=user.user_id, factory_id=task.factory_id))
    db.add(UserProductLine(user_id=user.user_id, product_line_code="DC-DC-100"))
    await db.flush()
    result = await claim(db, pending)
    identity = await access().verify_runtime_identity(db, result.token, None)
    if membership == "factory":
        await db.execute(delete(UserFactory).where(UserFactory.user_id == user.user_id, UserFactory.factory_id == task.factory_id))
    else:
        await db.execute(delete(UserProductLine).where(UserProductLine.user_id == user.user_id))
    with pytest.raises(PermissionError):
        await access().refresh_runtime_identity(db, identity)


@pytest.mark.asyncio
async def test_runtime_guards_require_fresh_identity_and_lock_order(db, pending, direct_caps):
    result = await claim(db, pending)
    identity = await access().verify_runtime_identity(db, result.token, None)
    current = await access().lock_runtime_identity(db, identity)
    access().require_capability(current, SUMMARY)
    with pytest.raises(PermissionError):
        access().require_capability(current, "unknown")
    assert (await access().get_capabilities(db, current)).capabilities[0].allowed


@pytest.mark.asyncio
async def test_trusted_restricted_raw_task_delivery_needs_controlled_egress(db, pending, direct_caps, monkeypatch):
    result = await claim(db, pending)
    identity = await access().verify_runtime_identity(db, result.token, None)
    with pytest.raises(PermissionError):
        access().require_delivery(identity, "restricted", "raw", controlled_egress=True)
    monkeypatch.setattr(access(), "TRUSTED_DELIVERY_DEPLOYMENTS", frozenset({
        ("single", pending[2].installation_id, pending[2].plugin_version)}))
    with pytest.raises(PermissionError):
        access().require_delivery(identity, "restricted", "raw")
    access().require_delivery(identity, "restricted", "raw", controlled_egress=True)
    with pytest.raises(PermissionError):
        access().require_delivery(identity, "restricted", "masked", controlled_egress=True)


@pytest.mark.asyncio
async def test_committed_expired_lease_reclaim_fences_old_cached_identity(ready_owned):
    owned = ready_owned
    async with owned.factory(binding=owned.binding) as writer:
        first = await dispatch().claim_run(writer, owned.binding, owned.plugin_id, owned.secret, "first")
    async with owned.factory(binding=owned.binding) as cached:
        identity = await access().verify_runtime_identity(cached, first.token, owned.binding)
        async with owned.factory(binding=owned.binding) as revoker:
            await revoker.execute(update(AgentRun).where(AgentRun.run_id == owned.run_id)
                .values(lease_expires_at=datetime.now(UTC)-timedelta(seconds=1)))
            await revoker.commit()
        async with owned.factory(binding=owned.binding) as reclaimer:
            second = await dispatch().claim_run(reclaimer, owned.binding, owned.plugin_id, owned.secret, "second")
            assert second.run_id == first.run_id and second.lease_epoch == first.lease_epoch+1
        with pytest.raises(PermissionError):
            await access().refresh_runtime_identity(cached, identity)
        assert (await access().verify_runtime_identity(cached, second.token, owned.binding)).run.lease_epoch == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["version", "plugin_grant", "task_grant", "permission", "role"])
async def test_external_commits_invalidate_full_runtime_identity(ready_owned, change):
    owned = ready_owned
    async with owned.factory(binding=owned.binding) as writer:
        result = await dispatch().claim_run(writer, owned.binding, owned.plugin_id, owned.secret, "external")
    async with owned.factory(binding=owned.binding) as cached:
        identity = await access().verify_runtime_identity(cached, result.token, owned.binding)
        async with owned.factory(binding=owned.binding) as revoker:
            query = {
                "version": update(AgentPluginInstallation).where(AgentPluginInstallation.installation_id == owned.plugin_id).values(plugin_version="2"),
                "plugin_grant": update(AgentPluginGrant).where(AgentPluginGrant.installation_id == owned.plugin_id).values(enabled=False),
                "task_grant": delete(AgentTaskGrant).where(AgentTaskGrant.task_id == owned.task_id),
                "permission": update(RolePermission).where(RolePermission.role_id == owned.role_id, RolePermission.module == "capa").values(permission_level=0),
                "role": update(RoleDefinition).where(RoleDefinition.id == owned.role_id).values(is_active=False),
            }[change]
            await revoker.execute(query)
            await revoker.commit()
        with pytest.raises(PermissionError):
            await access().refresh_runtime_identity(cached, identity)


@pytest.mark.asyncio
async def test_mutation_lock_target_is_reloaded_from_signed_run_not_cached_task(db, pending, direct_caps):
    from sqlalchemy import event
    result = await claim(db, pending)
    identity = await access().verify_runtime_identity(db, result.token, None)
    original = pending[1]
    unrelated = AgentTask(initiator_id=original.initiator_id, executor_user_id=original.executor_user_id,
        preferred_installation_id=original.preferred_installation_id, target_capa_id=original.target_capa_id,
        factory_id=original.factory_id, request_key="unrelated", status="ready")
    db.add(unrelated)
    await db.flush()
    connection = await db.connection()
    locks = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement:
            locks.append((statement, parameters))
    event.listen(connection.sync_connection, "before_cursor_execute", capture)
    try:
        await access().lock_runtime_identity(db, replace(identity, task=unrelated))
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", capture)
    assert len(locks) == 3
    assert "FROM agent_plugin_installations" in locks[0][0]
    assert "FROM agent_tasks" in locks[1][0]
    assert "FROM agent_runs" in locks[2][0]
    assert locks[1][1][0] == original.task_id


@pytest.mark.asyncio
async def test_claim_run_task_reference_changed_during_task_wait_denies(ready_owned):
    from sqlalchemy import event
    owned = ready_owned
    async with owned.factory(binding=owned.binding) as setup:
        original = await setup.get(AgentTask, owned.task_id)
        other = AgentTask(initiator_id=owned.user_id, executor_user_id=owned.user_id,
            preferred_installation_id=owned.plugin_id, target_capa_id=original.target_capa_id,
            factory_id=original.factory_id, request_key="other-target-task", status="ready")
        setup.add(other)
        await setup.commit()
        other_task_id = other.task_id
    attempted = asyncio.Event()
    def notice_task_lock(conn, cursor, statement, parameters, context, executemany):
        if "FROM agent_tasks" in statement and "FOR UPDATE" in statement:
            attempted.set()
    async with owned.factory(binding=owned.binding) as blocker:
        await blocker.scalar(select(AgentTask).where(AgentTask.task_id == owned.task_id).with_for_update())
        event.listen(owned.engine.sync_engine, "before_cursor_execute", notice_task_lock)
        async def waiting_claim():
            async with owned.factory(binding=owned.binding) as db:
                with pytest.raises(PermissionError):
                    await dispatch().claim_run(db, owned.binding, owned.plugin_id, owned.secret, "relation-race")
        future = asyncio.create_task(waiting_claim())
        notice = asyncio.create_task(attempted.wait())
        try:
            done, _ = await asyncio.wait({future, notice}, timeout=10, return_when=asyncio.FIRST_COMPLETED)
            assert notice in done and not future.done(), "claim did not wait on original TASK"
            await blocker.execute(update(AgentRun).where(AgentRun.run_id == owned.run_id).values(task_id=other_task_id))
            await blocker.commit()
            await asyncio.wait_for(future, 10)
        finally:
            event.remove(owned.engine.sync_engine, "before_cursor_execute", notice_task_lock)
            for pending_task in (future, notice):
                if not pending_task.done():
                    pending_task.cancel()
            await asyncio.gather(future, notice, return_exceptions=True)
    async with owned.factory(binding=owned.binding) as observer:
        run = await observer.get(AgentRun, owned.run_id)
        assert run.status == "pending" and run.claim_key is None and run.lease_epoch == 0


@pytest.mark.asyncio
async def test_capabilities_omit_unknown_optional_manifest_ids(db, pending, direct_caps):
    plugin = pending[2]
    plugin.manifest = {**plugin.manifest, "optional_capabilities": ["unknown.optional.v1"]}
    await db.flush()
    result = await claim(db, pending)
    identity = await access().verify_runtime_identity(db, result.token, None)
    capabilities = await access().get_capabilities(db, identity)
    assert [item.id for item in capabilities.capabilities] == [SUMMARY]


@pytest.mark.asyncio
async def test_unknown_required_denies_claim_and_identity_alongside_known_summary(db, pending, direct_caps):
    result = await claim(db, pending)
    plugin = pending[2]
    plugin.manifest = {**plugin.manifest, "required_capabilities": [SUMMARY, "unknown.required.v1"]}
    await db.flush()
    with pytest.raises(PermissionError):
        await claim(db, pending)
    with pytest.raises(PermissionError):
        await access().verify_runtime_identity(db, result.token, None)


@pytest.mark.asyncio
async def test_canonical_optional_command_is_denied_without_projection(db, pending, direct_caps):
    plugin = pending[2]
    command = "capa.d4.candidate.propose.v1"
    plugin.manifest = {**plugin.manifest, "optional_capabilities": [command]}
    await db.flush()
    result = await claim(db, pending)
    identity = await access().verify_runtime_identity(db, result.token, None)
    capabilities = await access().get_capabilities(db, identity)
    entry = next(item for item in capabilities.capabilities if item.id == command)
    assert entry.allowed is False and entry.required is False and entry.projection is None


def test_runtime_capability_projection_is_bounded_enum():
    from app.schemas.agent_runtime import RuntimeCapability
    fields = dict(id=SUMMARY, allowed=False, required=False)
    for projection in ("masked", "raw", None):
        assert RuntimeCapability(**fields, projection=projection).projection == projection
    for projection in ("arbitrary-string", "none", "", 123):
        with pytest.raises(ValidationError):
            RuntimeCapability(**fields, projection=projection)
