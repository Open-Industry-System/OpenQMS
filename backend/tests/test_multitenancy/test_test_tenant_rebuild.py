"""Test-only destructive maintenance on databases owned by mig_db_url, never qms_test."""
import asyncio
import importlib.util
import json
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.tenant_transaction import TenantBinding, TenantUnavailable, bind_business_transaction
from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator


@pytest_asyncio.fixture
async def rebuild_db(mig_db_url, monkeypatch):
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", mig_db_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    monkeypatch.setenv("ALLOW_TEST_TENANT_REBUILD", "1")
    from app.config import settings
    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def sample(rebuild_db):
    request = TenantCreateRequest(name="Disposable rebuild", slug="reset-" + uuid.uuid4().hex[:12],
                                 admin_email="admin@example.test", admin_password="private-reset-secret")
    tenant = await tenant_migrator.provision_new(request)
    async with rebuild_db.begin() as connection:
        await connection.execute(text(f'CREATE TABLE "{tenant.schema_name}".discard_me (id int)'))
        await connection.execute(text(f'INSERT INTO "{tenant.schema_name}".discard_me VALUES (42)'))
        await connection.execute(text("""INSERT INTO public.factories (id,code,name,is_active)
            VALUES (:id,'PUBLIC_KEEP','Preserved public content',true)"""), {"id": uuid.uuid4()})
    return tenant, request


def stopped_observer():
    from app.services.tenant_offline import ComposeOfflineObserver
    async def observe(project):
        return [{"Id": "backend-fixture", "Config": {"Labels": {
            "com.docker.compose.project": project, "com.docker.compose.service": "backend"}},
            "State": {"Status": "exited", "Running": False, "Paused": False, "Restarting": False}},
                {"Id": "worker-fixture", "Config": {"Labels": {
            "com.docker.compose.project": project, "com.docker.compose.service": "graph-worker"}},
            "State": {"Status": "exited", "Running": False, "Paused": False, "Restarting": False}}]
    return ComposeOfflineObserver(observe=observe)


async def invoke(engine, targets, requests, **kwargs):
    from app.services.tenant_test_rebuild import RebuildInventory, rebuild_test_tenants
    return await rebuild_test_tenants(targets, "discard-test-data", requests,
        inventory=kwargs.pop("inventory", RebuildInventory(True, tuple(targets))),
        compose_project="disposable-fixture", engine=engine,
        offline=kwargs.pop("offline", stopped_observer()), **kwargs)


@pytest.mark.asyncio
async def test_preview_exact_uuid_allowlist_is_read_only(rebuild_db, sample):
    assert importlib.util.find_spec("app.services.tenant_test_rebuild"), "read-only test-tenant rebuild preview is missing"
    from app.services.tenant_test_rebuild import preview_rebuild
    tenant, _ = sample
    async with rebuild_db.connect() as conn:
        before = (await conn.execute(text("SELECT * FROM public.tenants WHERE id=:id"), {"id": tenant.id})).one()
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    assert [(t.tenant_id, t.slug, t.schema_name, t.generation, t.status) for t in targets] == [
        (tenant.id, tenant.slug, tenant.schema_name, tenant.generation, "active")]
    async with rebuild_db.connect() as conn:
        assert (await conn.execute(text("SELECT * FROM public.tenants WHERE id=:id"), {"id": tenant.id})).one() == before
    for invalid in ([uuid.uuid4()], ["*"], [tenant.id, tenant.id], []):
        with pytest.raises((ValueError, PermissionError)):
            await preview_rebuild(invalid, engine=rebuild_db)


@pytest.mark.asyncio
@pytest.mark.parametrize("gate", ["production", "flag", "confirm", "actual_database"])
async def test_environment_guards_have_no_registry_or_schema_writes(rebuild_db, sample, monkeypatch, gate):
    from app.config import settings
    from app.services.tenant_test_rebuild import preview_rebuild, rebuild_test_tenants, RebuildInventory
    tenant, request = sample
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    confirmation = "discard-test-data"
    selected_engine = rebuild_db
    if gate == "production":
        monkeypatch.setattr(settings, "TENANT_MODE", "production")
    elif gate == "flag":
        monkeypatch.delenv("ALLOW_TEST_TENANT_REBUILD")
    elif gate == "confirm":
        confirmation = "yes"
    else:
        # The server, not the configured URL, decides the actual database name.
        selected_engine = create_async_engine(rebuild_db.url.set(database="postgres"), poolclass=NullPool)
    try:
        with pytest.raises(PermissionError):
            await rebuild_test_tenants(targets, confirmation, {tenant.id: request},
                inventory=RebuildInventory(True, tuple(targets)), compose_project="disposable-fixture",
                engine=selected_engine, offline=stopped_observer())
    finally:
        if selected_engine is not rebuild_db:
            await selected_engine.dispose()
    async with rebuild_db.connect() as conn:
        assert await conn.scalar(text(f'SELECT id FROM "{tenant.schema_name}".discard_me')) == 42
        assert (await conn.execute(text("SELECT status,generation FROM public.tenants WHERE id=:id"),
                                   {"id": tenant.id})).one() == ("active", tenant.generation)


@pytest.mark.asyncio
async def test_inventory_drift_nonallowlisted_and_missing_credentials_refuse(rebuild_db, sample):
    from app.services.tenant_test_rebuild import preview_rebuild, RebuildInventory
    tenant, request = sample
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    t = targets[0]
    for changes in [{"schema_name": "public"}, {"tenant_id": uuid.uuid4()},
                    {"slug": "*"}, {"generation": t.generation+1}, {"status": "failed"}]:
        with pytest.raises((PermissionError, ValueError)):
            await invoke(rebuild_db, [replace(t, **changes)], {tenant.id: request})
    with pytest.raises((PermissionError, ValueError)):
        await invoke(rebuild_db, targets, {tenant.id: request}, inventory=RebuildInventory(True, ()))
    with pytest.raises(PermissionError):
        await invoke(rebuild_db, targets, {})
    async with rebuild_db.connect() as conn:
        assert await conn.scalar(text(f'SELECT id FROM "{tenant.schema_name}".discard_me')) == 42


@pytest.mark.asyncio
@pytest.mark.parametrize("business", [False, True])
async def test_other_client_refuses_before_drop(rebuild_db, sample, business):
    from app.services.tenant_test_rebuild import preview_rebuild
    tenant, request = sample
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    async with rebuild_db.connect() as other:
        if business:
            await other.run_sync(lambda sync: bind_business_transaction(sync,
                TenantBinding(tenant.id, tenant.schema_name, tenant.generation, "business")))
        else:
            await other.execute(text("SELECT 1"))
        result = await invoke(rebuild_db, targets, {tenant.id: request})
        assert result[0].status == "refused" and result[0].error == "database_not_quiescent"
        assert await other.scalar(text(f'SELECT id FROM "{tenant.schema_name}".discard_me')) == 42
        assert await other.scalar(text("SELECT generation FROM public.tenants WHERE id=:id"), {"id": tenant.id}) == tenant.generation


@pytest.mark.asyncio
async def test_reset_preserves_identity_public_and_denies_old_request_and_worker(rebuild_db, sample):
    from app.services.tenant_test_rebuild import preview_rebuild
    from app.services.tenant_schema_diff import load_snapshot_manifest
    tenant, request = sample
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    owner_connections = []
    def observe_owner(connection, cursor, statement, parameters, context, executemany):
        if owner_connections or statement.startswith("DROP SCHEMA"):
            owner_connections.append(id(connection.connection.driver_connection))
    event.listen(rebuild_db.sync_engine, "before_cursor_execute", observe_owner)
    try:
        results = await invoke(rebuild_db, targets, {tenant.id: request})
    finally:
        event.remove(rebuild_db.sync_engine, "before_cursor_execute", observe_owner)
    assert len(owner_connections) > 20 and len(set(owner_connections)) == 1
    assert [(r.tenant_id, r.status, r.error) for r in results] == [(tenant.id, "active", None)]
    async with rebuild_db.connect() as conn:
        row = (await conn.execute(text("SELECT id,slug,schema_name,generation,status FROM public.tenants WHERE id=:id"),
                                   {"id": tenant.id})).one()
        assert row == (tenant.id, tenant.slug, tenant.schema_name, tenant.generation+1, "active")
        assert await conn.scalar(text("SELECT name FROM public.factories WHERE code='PUBLIC_KEEP'")) == "Preserved public content"
        assert await conn.scalar(text("SELECT to_regclass(:table)"), {"table": tenant.schema_name+".discard_me"}) is None
        assert await conn.scalar(text(f'SELECT count(*) FROM "{tenant.schema_name}".users')) == 1
    for entry in ("request", "worker"):
        async with rebuild_db.connect() as conn:
            with pytest.raises(TenantUnavailable):
                await conn.run_sync(lambda sync: bind_business_transaction(sync,
                    TenantBinding(tenant.id, tenant.schema_name, tenant.generation, "business")))
    from app.services.tenant_schema_diff import compare_business_schema
    async with rebuild_db.connect() as conn:
        assert await compare_business_schema(conn, "public", tenant.schema_name, load_snapshot_manifest()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["reset_commit", "migration_commit", "seed_precommit", "seed_commit", "final_platform_update"])
async def test_seed_failure_atomic_safe_and_explicit_refreshed_retry(rebuild_db, sample, failure_stage):
    from app.services.tenant_test_rebuild import preview_rebuild
    tenant, request = sample
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    def crash(stage):
        if stage == failure_stage:
            raise RuntimeError(request.admin_password)
    result = await invoke(rebuild_db, targets, {tenant.id: request}, after_stage_hook=crash)
    assert result[0].status == "failed" and result[0].error == "rebuild_failed"
    async with rebuild_db.connect() as conn:
        row = (await conn.execute(text("SELECT status,generation,provisioning_error FROM public.tenants WHERE id=:id"),
                                  {"id": tenant.id})).one()
        assert row.status == "failed" and row.generation == tenant.generation+1
        assert request.admin_password not in row.provisioning_error
        if failure_stage == "reset_commit":
            assert await conn.scalar(text("SELECT to_regnamespace(:schema)"), {"schema": tenant.schema_name}) is None
        elif failure_stage in {"migration_commit", "seed_precommit"}:
            for table in ("users", "factories", "product_lines", "role_definitions", "role_permissions"):
                assert await conn.scalar(text(f'SELECT count(*) FROM "{tenant.schema_name}"."{table}"')) == 0
        else:
            assert await conn.scalar(text(f'SELECT count(*) FROM "{tenant.schema_name}".users')) == 1
    with pytest.raises(TenantUnavailable, match="manual review"):
        await tenant_migrator.resume_tenant(tenant.id, bootstrap_request=request)
    with pytest.raises(PermissionError):
        await invoke(rebuild_db, targets, {tenant.id: request})
    fresh = await preview_rebuild([tenant.id], engine=rebuild_db)
    assert (await invoke(rebuild_db, fresh, {tenant.id: request}))[0].status == "active"


@pytest.mark.asyncio
async def test_offline_change_under_owner_and_multiple_target_results(rebuild_db, sample):
    from app.services.tenant_test_rebuild import preview_rebuild
    from app.services.tenant_offline import ComposeOfflineObserver
    tenant, request = sample
    other_request = request.model_copy(update={"slug": "reset-"+uuid.uuid4().hex[:12]})
    other = await tenant_migrator.provision_new(other_request)
    calls = 0
    base = stopped_observer()
    async def observe(project):
        nonlocal calls
        calls += 1
        rows = await base.observe(project)
        if calls == 2:
            rows[0]["State"].update(Status="running", Running=True)
        return rows
    targets = await preview_rebuild([tenant.id, other.id], engine=rebuild_db)
    results = await invoke(rebuild_db, targets, {tenant.id: request, other.id: other_request},
                           offline=ComposeOfflineObserver(observe=observe))
    assert [r.status for r in results] == ["failed", "active"]
    assert results[0].error == "services_not_offline"
    async with rebuild_db.connect() as conn:
        assert await conn.scalar(text(f'SELECT id FROM "{tenant.schema_name}".discard_me')) == 42


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["running", "paused", "restarting", "created", "dead", "unknown"])
async def test_offline_observer_refuses_unproven_states(state):
    from app.services.tenant_offline import TenantBusy
    observer = stopped_observer()
    original = observer.observe
    async def observe(project):
        rows = await original(project)
        rows[0]["State"]["Status"] = state
        return rows
    observer.observe = observe
    with pytest.raises(TenantBusy):
        await observer.require_stopped("fixture-project")


@pytest.mark.asyncio
async def test_offline_observer_requires_real_both_services_and_exact_project():
    from app.services.tenant_offline import TenantBusy
    for rows in ([], [{"Service": "backend", "State": "exited"}],
                 [{"Id": "x", "Config": {"Labels": {}}, "State": {"Status": "exited"}}]):
        observer = stopped_observer()
        async def observe(project):
            return rows
        observer.observe = observe
        with pytest.raises(TenantBusy):
            await observer.require_stopped("fixture-project")


def test_inventory_json_rejects_password_wildcards_duplicates_and_missing_test_intent():
    from app.services.tenant_test_rebuild import RebuildInventory
    entry = {"tenant_id": str(uuid.uuid4()), "slug": "sample", "schema_name": "tenant_sample",
             "generation": 1, "status": "active"}
    inventory = {"test_only": True, "targets": [entry]}
    assert RebuildInventory.from_json(json.dumps(inventory)).targets[0].tenant_id == uuid.UUID(entry["tenant_id"])
    for invalid in ({"targets": [entry]}, {"test_only": False, "targets": [entry]},
                    {"test_only": True, "targets": [dict(entry, password="secret")]},
                    {"test_only": True, "targets": [entry, entry]},
                    {"test_only": True, "targets": [dict(entry, slug="sample\n", schema_name="tenant_sample\n")]},
                    {"test_only": True, "targets": [dict(entry, tenant_id="*")]}):
        with pytest.raises((PermissionError, ValueError)):
            RebuildInventory.from_json(json.dumps(invalid))


@pytest.mark.asyncio
async def test_ordinary_maintenance_cannot_call_test_reset(rebuild_db, sample):
    tenant, _ = sample
    async with tenant_migrator.maintenance_connection(rebuild_db, tenant.id) as owner:
        with pytest.raises(PermissionError, match="rebuild authorization"):
            await owner.reset_test_schema(slug=tenant.slug, schema_name=tenant.schema_name,
                                          previous_generation=tenant.generation)
    async with rebuild_db.connect() as conn:
        assert await conn.scalar(text(f'SELECT id FROM "{tenant.schema_name}".discard_me')) == 42


@pytest.mark.asyncio
@pytest.mark.parametrize("shadow_catalog", [False, True])
async def test_other_client_appearing_under_owner_refuses_before_drop(rebuild_db, sample, shadow_catalog):
    from app.services.tenant_test_rebuild import preview_rebuild
    from app.services.tenant_offline import ComposeOfflineObserver
    tenant, request = sample
    if shadow_catalog:
        async with rebuild_db.begin() as conn:
            await conn.execute(text(f'CREATE TABLE "{tenant.schema_name}".pg_stat_activity '
                                    '(datname text, pid int, backend_type text)'))
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    base = stopped_observer()
    calls, other = 0, None
    async def observe(project):
        nonlocal calls, other
        calls += 1
        if calls == 2:
            other = await rebuild_db.connect()
            await other.execute(text("SELECT 1"))
        return await base.observe(project)
    try:
        results = await invoke(rebuild_db, targets, {tenant.id: request},
                               offline=ComposeOfflineObserver(observe=observe))
        assert len(results) == 1 and results[0].status == "failed"
        assert results[0].error == "database_not_quiescent"
        assert await other.scalar(text(f'SELECT id FROM "{tenant.schema_name}".discard_me')) == 42
    finally:
        if other is not None:
            await other.close()


@pytest.mark.asyncio
async def test_rival_rebuild_does_not_change_winning_claim(rebuild_db, sample):
    from app.services.tenant_test_rebuild import preview_rebuild
    from app.services.tenant_offline import ComposeOfflineObserver
    tenant, request = sample
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    base = stopped_observer()
    owner_ready, rival_done = asyncio.Event(), asyncio.Event()
    calls = 0
    async def observe(project):
        nonlocal calls
        calls += 1
        if calls == 2:
            owner_ready.set()
            await asyncio.wait_for(rival_done.wait(), 10)
        return await base.observe(project)
    async def winner():
        return await invoke(rebuild_db, targets, {tenant.id: request}, offline=ComposeOfflineObserver(observe=observe))
    async def rival():
        await asyncio.wait_for(owner_ready.wait(), 10)
        try:
            refreshed = await preview_rebuild([tenant.id], engine=rebuild_db)
            async with rebuild_db.connect() as conn:
                before = (await conn.execute(text("SELECT generation,status,provisioning_attempt_id FROM public.tenants WHERE id=:id"),
                                             {"id": tenant.id})).one()
            results = await invoke(rebuild_db, refreshed, {tenant.id: request})
            assert len(results) == 1 and results[0].status == "refused"
            async with rebuild_db.connect() as conn:
                assert (await conn.execute(text("SELECT generation,status,provisioning_attempt_id FROM public.tenants WHERE id=:id"),
                                           {"id": tenant.id})).one() == before
        finally:
            rival_done.set()
    win, _ = await asyncio.gather(winner(), rival())
    assert len(win) == 1 and win[0].status == "active"


@pytest.mark.asyncio
async def test_cli_defaults_to_read_only_and_never_prompts_password(rebuild_db, sample, tmp_path, monkeypatch, capsys):
    from dataclasses import asdict
    from app.cli import rebuild_test_tenants as cli
    from app.config import settings
    from app.services.tenant_test_rebuild import preview_rebuild
    tenant, _ = sample
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"test_only": True, "targets": [asdict(t) for t in targets]}, default=str))
    monkeypatch.setattr(settings, "DATABASE_URL", str(rebuild_db.url.render_as_string(hide_password=False)))
    args = cli.parser().parse_args(["--inventory", str(path), "--compose-project", "disposable-fixture"])
    assert not args.execute
    assert await cli.run(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["targets"][0]["generation"] == tenant.generation
    async with rebuild_db.connect() as conn:
        assert await conn.scalar(text(f'SELECT id FROM "{tenant.schema_name}".discard_me')) == 42


@pytest.mark.asyncio
async def test_resume_cannot_bypass_failed_rebuild_barrier_after_maintenance_mark(rebuild_db, sample):
    from app.services.tenant_test_rebuild import preview_rebuild
    tenant, request = sample
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    def crash(stage):
        if stage == "final_platform_update":
            raise RuntimeError()
    assert (await invoke(rebuild_db, targets, {tenant.id: request}, after_stage_hook=crash))[0].status == "failed"
    async with rebuild_db.begin() as conn:
        # A interrupted explicit retry may have persisted the maintenance mark,
        # but has not yet acquired the lock/new attempt. Its old failure remains.
        await conn.execute(text("UPDATE public.tenants SET status='maintenance' WHERE id=:id"), {"id": tenant.id})
        before = (await conn.execute(text("SELECT status,generation,provisioning_attempt_id FROM public.tenants WHERE id=:id"),
                                     {"id": tenant.id})).one()
    with pytest.raises(TenantUnavailable, match="manual review"):
        await tenant_migrator.resume_tenant(tenant.id, bootstrap_request=request)
    async with rebuild_db.connect() as conn:
        assert (await conn.execute(text("SELECT status,generation,provisioning_attempt_id FROM public.tenants WHERE id=:id"),
                                   {"id": tenant.id})).one() == before


@pytest.mark.asyncio
async def test_crash_after_mark_requires_explicit_retry_without_generation_change(rebuild_db, sample):
    from app.services.tenant_test_rebuild import preview_rebuild
    tenant, request = sample
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    def crash(stage):
        if stage == "maintenance_marked":
            raise RuntimeError(request.admin_password)
    result = await invoke(rebuild_db, targets, {tenant.id: request}, after_stage_hook=crash)
    assert len(result) == 1 and result[0].status == "refused"
    async with rebuild_db.connect() as conn:
        assert (await conn.execute(text("SELECT status,generation FROM public.tenants WHERE id=:id"),
                                   {"id": tenant.id})).one() == ("maintenance", tenant.generation)
        assert await conn.scalar(text(f'SELECT id FROM "{tenant.schema_name}".discard_me')) == 42
    with pytest.raises(TenantUnavailable, match="manual review"):
        await tenant_migrator.resume_tenant(tenant.id, bootstrap_request=request)
    fresh = await preview_rebuild([tenant.id], engine=rebuild_db)
    assert (await invoke(rebuild_db, fresh, {tenant.id: request}))[0].status == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("external_schema", ["public", "another_tenant"])
async def test_cascade_cannot_drop_objects_outside_allowlisted_schema(rebuild_db, sample, external_schema):
    from app.services.tenant_test_rebuild import preview_rebuild
    tenant, request = sample
    async with rebuild_db.begin() as conn:
        if external_schema != "public":
            await conn.execute(text(f'CREATE SCHEMA "{external_schema}"'))
        await conn.execute(text(f'CREATE VIEW "{external_schema}".external_view AS '
                                f'SELECT id FROM "{tenant.schema_name}".discard_me'))
    targets = await preview_rebuild([tenant.id], engine=rebuild_db)
    results = await invoke(rebuild_db, targets, {tenant.id: request})
    assert len(results) == 1 and results[0].status == "failed"
    assert results[0].error == "external_schema_dependency"
    async with rebuild_db.connect() as conn:
        assert await conn.scalar(text(f'SELECT id FROM "{external_schema}".external_view')) == 42
        assert await conn.scalar(text(f'SELECT id FROM "{tenant.schema_name}".discard_me')) == 42


@pytest.mark.asyncio
@pytest.mark.parametrize("last_committed_phase", ["claimed", "reset", "migrated", "seeded"])
async def test_interrupted_owner_persisted_state_requires_explicit_rebuild_retry(rebuild_db, sample, last_committed_phase):
    from app.services.tenant_test_rebuild import preview_rebuild, _mark_maintenance
    tenant, request = sample
    target = (await preview_rebuild([tenant.id], engine=rebuild_db))[0]
    precondition = await _mark_maintenance(rebuild_db, target)
    # Exercise the same committed owner operations, then lose the owner without
    # invoking the service's caught-failure handler. Unlock models backend death:
    # its persisted registry/schema state is identical after PostgreSQL releases
    # the dead backend's session lock, with no compensating platform write.
    async with tenant_migrator.maintenance_connection(rebuild_db, tenant.id,
                                                     rebuild_precondition=precondition) as owner:
        if last_committed_phase != "claimed":
            await owner.reset_test_schema(slug=tenant.slug, schema_name=tenant.schema_name,
                                          previous_generation=tenant.generation)
        if last_committed_phase in {"migrated", "seeded"}:
            await owner.create_schema()
            await owner.run_migration(tenant_migrator.REVISION)
            await owner.record_rebuild_phase("migrated")
        if last_committed_phase == "seeded":
            await owner.seed_tenant(request)
            await owner.record_rebuild_phase("seeded")
    async with rebuild_db.connect() as conn:
        before = (await conn.execute(text("SELECT status,generation,provisioning_attempt_id,provisioning_error FROM public.tenants WHERE id=:id"),
                                     {"id": tenant.id})).one()
    with pytest.raises(TenantUnavailable, match="manual review"):
        await tenant_migrator.resume_tenant(tenant.id, bootstrap_request=request)
    async with rebuild_db.connect() as conn:
        assert (await conn.execute(text("SELECT status,generation,provisioning_attempt_id,provisioning_error FROM public.tenants WHERE id=:id"),
                                   {"id": tenant.id})).one() == before
    fresh = await preview_rebuild([tenant.id], engine=rebuild_db)
    assert (await invoke(rebuild_db, fresh, {tenant.id: request}))[0].status == "active"
    async with rebuild_db.connect() as conn:
        assert await conn.scalar(text("SELECT provisioning_error FROM public.tenants WHERE id=:id"), {"id": tenant.id}) is None


@pytest.mark.asyncio
async def test_only_successful_test_schema_drop_records_exact_attachment_disposal(rebuild_db, sample, tmp_path):
    """The disposal authority is atomic with exactly the destructive test rebuild."""
    from app.services.tenant_test_rebuild import preview_rebuild

    tenant, request = sample
    target = (await preview_rebuild([tenant.id], engine=rebuild_db))[0]
    result = await invoke(rebuild_db, [target], {tenant.id: request})
    assert result[0].status == "active"
    async with rebuild_db.connect() as conn:
        row = (await conn.execute(text("""
            SELECT tenant_id,origin_generation,storage_namespace,reason
            FROM public.tenant_attachment_storage_disposals
            WHERE tenant_id=:id
        """), {"id": tenant.id})).one()
    assert row == (
        tenant.id,
        target.generation,
        f"tenant_{tenant.id.hex}_{target.generation}",
        "test_rebuild",
    )

    # Bytes in the old namespace are preserved until the exact committed
    # disposal record exists, then maintenance authority can remove the whole
    # generation without consulting an upload owner.
    from app.models.tenant_attachment_disposal import TenantAttachmentStorageDisposal
    from app.services.agent_runtime.attachment_recovery import reconcile_disposed_namespace
    from app.services.agent_runtime.attachment_storage import AttachmentNamespace, PrivateAttachmentStorage
    from sqlalchemy.ext.asyncio import AsyncSession

    namespace = AttachmentNamespace(tenant.id, target.generation, f"tenant_{tenant.id.hex}_{target.generation}")
    storage = PrivateAttachmentStorage(tmp_path / "attachments")
    orphan = uuid.uuid4()
    with storage.create_staging(namespace, orphan) as handle:
        handle.write(b"old")
    assert (tmp_path / "attachments" / namespace.storage_namespace / "staging" / orphan.hex).exists()
    async with AsyncSession(rebuild_db, expire_on_commit=False) as platform_db:
        disposal = await platform_db.scalar(text("""
            SELECT disposal_id FROM public.tenant_attachment_storage_disposals
            WHERE tenant_id=:id
        """), {"id": tenant.id})
        authority = await platform_db.get(TenantAttachmentStorageDisposal, disposal)
        assert authority is not None
        assert (await reconcile_disposed_namespace(platform_db, authority, storage)).disposed_namespaces == 1
    assert not (tmp_path / "attachments" / namespace.storage_namespace).exists()

    failed_request = request.model_copy(update={"slug": "reset-" + uuid.uuid4().hex[:12]})
    failed = await tenant_migrator.provision_new(failed_request)
    failed_target = (await preview_rebuild([failed.id], engine=rebuild_db))[0]

    def crash(stage):
        if stage == "maintenance_marked":
            raise RuntimeError()

    result = await invoke(
        rebuild_db, [failed_target], {failed.id: failed_request}, after_stage_hook=crash,
    )
    assert result[0].status == "failed"
    async with rebuild_db.connect() as conn:
        assert await conn.scalar(text("""
            SELECT count(*) FROM public.tenant_attachment_storage_disposals
            WHERE tenant_id=:id
        """), {"id": failed.id}) == 0
