"""Runtime tokens bind trusted tenant admission and fresh database-owned identity."""
from datetime import UTC, datetime
import uuid

import pytest
from jose import jwt
from pydantic import ValidationError
from sqlalchemy import event, update
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from dataclasses import replace

from app.config import Settings, settings
from app.core.security import create_access_token, create_platform_admin_token, create_refresh_token
from app.core.tenant_transaction import TenantBinding
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_task import AgentRun, AgentTask
from app.models.user import User


def auth():
    from app.services.agent_runtime import run_auth
    return run_auth


def token_for(active_run, **changes):
    run, _, installation, _ = active_run
    token = auth().issue_run_token(run, installation, "single", 0)
    if not changes:
        return token
    payload = jwt.get_unverified_claims(token)
    payload.update(changes)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def test_ttl_has_bounded_configuration():
    assert Settings(SECRET_KEY="test", _env_file=None).AGENT_RUN_TOKEN_TTL_MINUTES == 5
    for ttl in (0, 31):
        with pytest.raises(ValidationError):
            Settings(SECRET_KEY="test", AGENT_RUN_TOKEN_TTL_MINUTES=ttl, _env_file=None)


@pytest.mark.asyncio
async def test_runtime_token_has_short_lifetime_and_db_owned_identity(db, active_run):
    token = token_for(active_run)
    payload = jwt.get_unverified_claims(token)
    assert payload["iss"] == payload["aud"] == "openqms-agent-runtime"
    assert payload["type"] == "agent_run"
    assert 0 < payload["exp"] - datetime.now(UTC).timestamp() <= settings.AGENT_RUN_TOKEN_TTL_MINUTES * 60
    assert "sub" not in payload and "executor_user_id" not in payload and "schema_name" not in payload
    assert await auth().verify_run_token(db, token, None) is active_run[0]


@pytest.mark.asyncio
async def test_user_refresh_and_platform_tokens_cannot_authenticate_runtime(db, admin_user):
    tokens = [create_access_token({"sub": str(admin_user.user_id)}),
        create_refresh_token(str(admin_user.user_id))[0], create_platform_admin_token(str(admin_user.user_id))]
    for token in tokens:
        with pytest.raises(PermissionError):
            await auth().verify_run_token(db, token, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"iss": "openqms-tenant"}, {"aud": "openqms-platform"},
    {"aud": ["openqms-agent-runtime"]}, {"type": "access"}, {"exp": 1},
    {"tenant_id": None}, {"tenant_generation": -1}, {"tenant_generation": "0"},
    {"tenant_generation": False}, {"lease_epoch": -1}, {"lease_epoch": "0"},
    {"credential_epoch": True}, {"run_id": "not-uuid"}, {"installation_id": []},
    {"plugin_version": 1}, {"plugin_version": ""}, {"exp": "9999999999"}, {"exp": True}])
async def test_claims_require_exact_domain_types_and_values(db, active_run, changes):
    with pytest.raises(PermissionError):
        await auth().verify_run_token(db, token_for(active_run, **changes), None)


@pytest.mark.asyncio
@pytest.mark.parametrize("claim", ["iss", "aud", "type", "exp", "tenant_id", "tenant_generation",
    "run_id", "installation_id", "plugin_version", "lease_epoch", "credential_epoch"])
async def test_required_claims_cannot_be_omitted(db, active_run, claim):
    payload = jwt.get_unverified_claims(token_for(active_run))
    payload.pop(claim)
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    with pytest.raises(PermissionError):
        await auth().verify_run_token(db, token, None)


@pytest.mark.asyncio
async def test_bad_signature_rejected(db, active_run):
    payload = jwt.get_unverified_claims(token_for(active_run))
    token = jwt.encode(payload, "wrong-secret", algorithm=settings.ALGORITHM)
    with pytest.raises(PermissionError):
        await auth().verify_run_token(db, token, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("model,field,value", [
    (AgentRun, "status", "pending"), (AgentRun, "status", "paused"), (AgentRun, "status", "stopped"),
    (AgentRun, "status", "completed"), (AgentRun, "status", "failed"),
    (AgentTask, "status", "paused"), (AgentTask, "status", "completed"), (AgentTask, "status", "cancelled"),
    (AgentTask, "status", "failed"), (AgentTask, "status", "blocked_capability"),
    (User, "is_active", False), (AgentPluginInstallation, "enabled", False),
    (AgentPluginInstallation, "credential_epoch", 1), (AgentRun, "lease_epoch", 1),
    (AgentRun, "plugin_version", "2"), (AgentPluginInstallation, "plugin_version", "2")])
async def test_current_state_overrides_cached_rows(db, active_run, model, field, value):
    token = token_for(active_run)
    assert await auth().verify_run_token(db, token, None) is active_run[0]
    row = {AgentRun: active_run[0], AgentTask: active_run[1], AgentPluginInstallation: active_run[2], User: active_run[3]}[model]
    pk = {AgentRun: "run_id", AgentTask: "task_id", AgentPluginInstallation: "installation_id", User: "user_id"}[model]
    await db.execute(update(model).where(getattr(model, pk) == getattr(row, pk)).values(**{field: value}).execution_options(synchronize_session=False))
    with pytest.raises(PermissionError):
        await auth().verify_run_token(db, token, None)


@pytest.mark.asyncio
async def test_installation_and_task_association_are_pinned(db, active_run, admin_user):
    from app.services.agent_runtime.plugin_registry import register_plugin
    run, task, plugin, _ = active_run
    other, _ = await register_plugin(db, admin_user, "other", "1.0.0", {"protocol_versions": ["1"]})
    token = token_for(active_run)
    task.preferred_installation_id = other.installation_id
    await db.flush()
    with pytest.raises(PermissionError):
        await auth().verify_run_token(db, token, None)
    task.preferred_installation_id = plugin.installation_id
    await db.flush()
    for changes in ({"installation_id": str(other.installation_id)}, {"run_id": str(uuid.uuid4())},
                    {"plugin_version": "2"}, {"lease_epoch": 9}, {"credential_epoch": 9}):
        with pytest.raises(PermissionError):
            await auth().verify_run_token(db, token_for(active_run, **changes), None)


@pytest.mark.asyncio
async def test_rotation_invalidates_runtime_token(db, active_run):
    from app.services.agent_runtime.plugin_registry import rotate_plugin_secret
    token = token_for(active_run)
    _, _, plugin, user = active_run
    await rotate_plugin_secret(db, user, plugin.installation_id)
    with pytest.raises(PermissionError):
        await auth().verify_run_token(db, token, None)
    assert await auth().verify_run_token(db, token_for(active_run), None) is active_run[0]


@pytest.mark.asyncio
async def test_single_mode_requires_explicit_sentinel_and_unbound_session(db, active_run):
    binding = TenantBinding(uuid.uuid4(), "tenant_untrusted", 0, "business")
    for changes in ({"tenant_id": str(binding.tenant_id)}, {"tenant_generation": 1}):
        with pytest.raises(PermissionError):
            await auth().verify_run_token(db, token_for(active_run, **changes), None)
    with pytest.raises(PermissionError):
        await auth().verify_run_token(db, token_for(active_run), binding)
    db.info["tenant_binding"] = binding
    with pytest.raises(PermissionError):
        await auth().verify_run_token(db, token_for(active_run), None)


@pytest.mark.asyncio
async def test_multi_mode_rejects_missing_or_spoofed_binding_before_any_sql(db, active_run, monkeypatch):
    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    binding = TenantBinding(uuid.uuid4(), "tenant_untrusted", 0, "business")
    token = auth().issue_run_token(active_run[0], active_run[2], str(binding.tenant_id), 0)
    connection = await db.connection()
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(connection.sync_connection, "before_cursor_execute", capture)
    try:
        for supplied in (None, binding):
            with pytest.raises(PermissionError):
                await auth().verify_run_token(db, token, supplied)
        db.info["tenant_binding"] = binding
        with pytest.raises(PermissionError):
            await auth().verify_run_token(db, token, binding)
        assert statements == []
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", capture)


async def committed_token(owned, db):
    run = await db.get(AgentRun, owned.run_id)
    plugin = await db.get(AgentPluginInstallation, owned.plugin_id)
    return auth().issue_run_token(run, plugin, str(owned.binding.tenant_id), owned.binding.generation)


@pytest.mark.asyncio
async def test_complete_tenant_runtime_admission_and_mismatch_before_business_sql(committed_runtime):
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as db:
        token = await committed_token(owned, db)
        assert (await auth().verify_run_token(db, token, owned.binding)).run_id == owned.run_id
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(owned.engine.sync_engine, "before_cursor_execute", capture)
        try:
            for binding in (None, replace(owned.binding, generation=owned.binding.generation + 1),
                            replace(owned.binding, tenant_id=uuid.uuid4()), replace(owned.binding, mode="maintenance")):
                with pytest.raises(PermissionError):
                    await auth().verify_run_token(db, token, binding)
            claims = jwt.get_unverified_claims(token)
            for changes in ({"tenant_id": str(uuid.uuid4())}, {"tenant_generation": owned.binding.generation + 1}):
                forged = jwt.encode(dict(claims, **changes), settings.SECRET_KEY, algorithm=settings.ALGORITHM)
                with pytest.raises(PermissionError):
                    await auth().verify_run_token(db, forged, owned.binding)
            assert statements == []
        finally:
            event.remove(owned.engine.sync_engine, "before_cursor_execute", capture)


@pytest.mark.asyncio
async def test_single_mode_unbound_session_cannot_authenticate_from_tenant_shadow(committed_runtime, monkeypatch):
    owned = committed_runtime
    # Load identity through the production tenant gate before switching to the
    # deliberately contaminated plain session that this regression exercises.
    async with owned.factory(binding=owned.binding) as tenant_db:
        run = await tenant_db.get(AgentRun, owned.run_id)
        plugin = await tenant_db.get(AgentPluginInstallation, owned.plugin_id)
        token = auth().issue_run_token(run, plugin, "single", 0)
    monkeypatch.setattr(settings, "TENANT_MODE", "single")
    async with AsyncSession(owned.engine, expire_on_commit=False) as unbound:
        # Session has no binding but a preceding operation left a tenant path.
        await unbound.execute(text(f'SET LOCAL search_path TO "{owned.binding.schema_name}", pg_catalog'))
        # There is no public run with this UUID. A single credential must not
        # authenticate the real tenant shadow with the same signed run UUID.
        with pytest.raises(PermissionError, match="^Invalid run credential$"):
            await auth().verify_run_token(unbound, token, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["status", "generation", "schema_name"])
async def test_registry_rechecked_within_already_open_transaction(committed_runtime, changed):
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as db:
        token = await committed_token(owned, db)
        await auth().verify_run_token(db, token, owned.binding)
        # Change only fixture-owned public registry; business rows always use TenantSession.
        values = {"status": "suspended", "generation": owned.binding.generation + 1,
                  "schema_name": "tenant_changed"}
        async with owned.engine.begin() as connection:
            await connection.execute(text(f"UPDATE public.tenants SET {changed}=:value WHERE id=:id"),
                {"value": values[changed], "id": owned.binding.tenant_id})
        statements = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(owned.engine.sync_engine, "before_cursor_execute", capture)
        try:
            with pytest.raises(PermissionError):
                await auth().verify_run_token(db, token, owned.binding)
            assert len(statements) == 1 and "public.tenants" in statements[0]
        finally:
            event.remove(owned.engine.sync_engine, "before_cursor_execute", capture)


@pytest.mark.asyncio
async def test_transaction_gate_rejects_stale_registry_before_run_query(committed_runtime):
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as db:
        token = await committed_token(owned, db)
        await db.commit()
        async with owned.engine.begin() as connection:
            await connection.execute(text("UPDATE public.tenants SET generation=generation+1 WHERE id=:id"), {"id": owned.binding.tenant_id})
        with pytest.raises(PermissionError):
            await auth().verify_run_token(db, token, owned.binding)


@pytest.mark.asyncio
@pytest.mark.parametrize("model,field,value", [(AgentRun, "status", "stopped"),
    (AgentTask, "status", "cancelled"), (AgentPluginInstallation, "enabled", False),
    (AgentPluginInstallation, "credential_epoch", 1), (User, "is_active", False)])
async def test_external_commits_invalidate_cached_rows_in_same_transaction(committed_runtime, model, field, value):
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as db:
        token = await committed_token(owned, db)
        run = await auth().verify_run_token(db, token, owned.binding)
        async with owned.factory(binding=owned.binding) as other:
            pk, identity = {AgentRun: (AgentRun.run_id, owned.run_id), AgentTask: (AgentTask.task_id, owned.task_id),
                AgentPluginInstallation: (AgentPluginInstallation.installation_id, owned.plugin_id),
                User: (User.user_id, owned.user_id)}[model]
            await other.execute(update(model).where(pk == identity).values(**{field: value}))
            await other.commit()
        assert run in db
        with pytest.raises(PermissionError):
            await auth().verify_run_token(db, token, owned.binding)


@pytest.mark.asyncio
async def test_legacy_active_run_without_lease_is_rejected(db, active_run):
    active_run[0].lease_expires_at = None
    await db.flush()
    token = token_for(active_run)
    with pytest.raises(PermissionError):
        await auth().verify_run_token(db, token, None)


def test_run_token_is_capped_by_persisted_lease(active_run):
    from datetime import timedelta
    run = active_run[0]
    run.lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)
    claims = jwt.get_unverified_claims(token_for(active_run))
    assert claims['exp'] <= run.lease_expires_at.timestamp()
