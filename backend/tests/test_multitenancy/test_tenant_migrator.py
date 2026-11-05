"""Real PostgreSQL ownership checks on disposable test databases."""
import asyncio
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.tenant_transaction import (
    TenantBinding, TenantUnavailable, bind_business_transaction, stable_tenant_lock_key,
)
from app.services.tenant_migrator import (
    MaintenanceAttempt, REVISION, bind_maintenance_transaction, maintenance_connection,
)
from alembic_tenant import upgrade_tenant
from app.services.tenant_schema_diff import load_snapshot_manifest


@pytest_asyncio.fixture
async def tenant_record(mig_db_url):
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", mig_db_url)
    await asyncio.to_thread(command.upgrade, cfg, "20260927_tenant_attempt")
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    tenant_id = uuid.uuid4()
    schema = f"tenant_lock_{uuid.uuid4().hex[:16]}"
    attempt = MaintenanceAttempt(tenant_id=tenant_id, schema_name=schema, generation=1,
                                 attempt_id=uuid.uuid4(), backend_pid=0,
                                 lock_key=stable_tenant_lock_key(tenant_id))
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text("""INSERT INTO public.tenants
                (id,name,slug,subdomain,schema_name,status,generation,provisioning_attempt_id)
                VALUES (:id,'Maintenance','lock-test-' || :slug,'lock-test-' || :slug,
                        :schema,'provisioning',1,:attempt)"""),
                {"id": tenant_id, "slug": uuid.uuid4().hex[:12], "schema": schema,
                 "attempt": attempt.attempt_id})
        yield engine, attempt
    finally:
        await engine.dispose()  # mig_db_url owns deletion of this entire disposable DB.


@pytest.mark.asyncio
async def test_maintenance_uses_one_lock_owner(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt) as maintenance:
        assert not hasattr(maintenance, "execute")
        assert not hasattr(maintenance, "seed_session")
        pid = maintenance.backend_pid
        await maintenance.run_migration("tv001_business_snapshot")
        differences = await maintenance.compare_schema("public", load_snapshot_manifest())
        assert differences == []
        assert maintenance.backend_pid == pid == attempt.backend_pid
        async with engine.connect() as ordinary:
            assert not await ordinary.scalar(text("SELECT pg_try_advisory_xact_lock_shared(:key)"),
                                             {"key": attempt.lock_key})
            with pytest.raises(TenantUnavailable, match="maintenance"):
                await ordinary.run_sync(lambda sync: bind_business_transaction(
                    sync, TenantBinding(attempt.tenant_id, attempt.schema_name, 1, "business")))
    async with engine.connect() as ordinary:
        assert await ordinary.scalar(text("SELECT pg_try_advisory_xact_lock_shared(:key)"),
                                     {"key": attempt.lock_key})


@pytest.mark.asyncio
async def test_preheld_pooled_session_lock_is_invalidated(tenant_record):
    engine, attempt = tenant_record
    pool = create_async_engine(engine.url, pool_size=1, max_overflow=0)
    try:
        async with pool.connect() as contaminated:
            pid = await contaminated.scalar(text("SELECT pg_backend_pid()"))
            assert await contaminated.scalar(text("SELECT pg_try_advisory_lock(:key)"),
                                             {"key": attempt.lock_key})
            await contaminated.commit()
        with pytest.raises(TenantUnavailable, match="pre-held"):
            async with maintenance_connection(pool, attempt):
                pytest.fail("pre-held pooled lock admitted")
        async with pool.connect() as fresh:
            assert await fresh.scalar(text("SELECT pg_backend_pid()")) != pid
            assert await fresh.scalar(text("SELECT pg_try_advisory_lock_shared(:key)"),
                                      {"key": attempt.lock_key})
        async with engine.connect() as inspector:
            assert await inspector.scalar(text("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND pid=:pid"),
                                          {"pid": pid}) == 0
    finally:
        await pool.dispose()


@pytest.mark.asyncio
async def test_cancelled_precheck_never_returns_preheld_backend(tenant_record, monkeypatch):
    engine, attempt = tenant_record
    pool = create_async_engine(engine.url, pool_size=1, max_overflow=0)
    original = AsyncConnection.scalar
    try:
        async with pool.connect() as contaminated:
            pid = await contaminated.scalar(text("SELECT pg_backend_pid()"))
            assert await contaminated.scalar(text("SELECT pg_try_advisory_lock(:key)"),
                                             {"key": attempt.lock_key})
            await contaminated.commit()

        async def cancel_after_precheck(self, statement, *args, **kwargs):
            result = await original(self, statement, *args, **kwargs)
            if "FROM pg_locks" in str(statement) and "ShareLock" in str(statement):
                raise asyncio.CancelledError("precheck result lost")
            return result

        with monkeypatch.context() as patch:
            patch.setattr(AsyncConnection, "scalar", cancel_after_precheck)
            with pytest.raises(asyncio.CancelledError, match="precheck result lost"):
                async with maintenance_connection(pool, attempt):
                    pytest.fail("cancelled precheck admitted")
        async with pool.connect() as fresh:
            assert await fresh.scalar(text("SELECT pg_backend_pid()")) != pid
            assert await fresh.scalar(text("SELECT pg_try_advisory_lock_shared(:key)"),
                                      {"key": attempt.lock_key})
    finally:
        await pool.dispose()


@pytest.mark.asyncio
async def test_cancelled_uncertain_acquisition_invalidates_backend(tenant_record, monkeypatch):
    engine, attempt = tenant_record
    pool = create_async_engine(engine.url, pool_size=1, max_overflow=0)
    original = AsyncConnection.scalar
    captured_pid = []

    async def cancel_after_acquire(self, statement, *args, **kwargs):
        value = await original(self, statement, *args, **kwargs)
        if "pg_try_advisory_lock(" in str(statement):
            captured_pid.append(await original(self, text("SELECT pg_backend_pid()")))
            raise asyncio.CancelledError("acquisition result lost")
        return value

    try:
        with monkeypatch.context() as patch:
            patch.setattr(AsyncConnection, "scalar", cancel_after_acquire)
            with pytest.raises(asyncio.CancelledError, match="acquisition result lost"):
                async with maintenance_connection(pool, attempt):
                    pytest.fail("cancelled acquisition admitted")
        assert len(captured_pid) == 1
        async with pool.connect() as fresh:
            assert await fresh.scalar(text("SELECT pg_backend_pid()")) != captured_pid[0]
            assert await fresh.scalar(text("SELECT pg_try_advisory_lock_shared(:key)"),
                                      {"key": attempt.lock_key})
    finally:
        await pool.dispose()


@pytest.mark.asyncio
async def test_competing_owner_fails_immediately_and_does_not_inherit_pid(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt) as owner:
        rival = replace(attempt, backend_pid=0)
        with pytest.raises(TenantUnavailable, match="active transactions"):
            async with maintenance_connection(engine, rival):
                pytest.fail("competing owner admitted")
        assert rival.backend_pid == 0
        assert owner.backend_pid == attempt.backend_pid


@pytest.mark.asyncio
async def test_wrong_attempt_generation_and_schema_cannot_bind(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt) as maintenance:
        original_id, original_generation, original_schema = attempt.attempt_id, attempt.generation, attempt.schema_name
        for field, value in (("attempt_id", uuid.uuid4()), ("generation", 2),
                             ("schema_name", "tenant_wrong")):
            setattr(attempt, field, value)
            with pytest.raises(TenantUnavailable):
                await maintenance.compare_schema("public", {})
            setattr(attempt, field, {"attempt_id": original_id, "generation": original_generation,
                                     "schema_name": original_schema}[field])
        # After a committed maintenance transaction, the platform can change
        # independently and the next context method must deny its SQL.
        async with engine.begin() as public:
            await public.execute(text("UPDATE public.tenants SET provisioning_attempt_id=:new WHERE id=:id"),
                                 {"id": attempt.tenant_id, "new": uuid.uuid4()})
        with pytest.raises(TenantUnavailable):
            await maintenance.run_migration("tv001_business_snapshot")


@pytest.mark.asyncio
async def test_wrong_physical_connection_cannot_bind(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt):
        async with engine.connect() as rival:
            with pytest.raises(TenantUnavailable):
                await bind_maintenance_transaction(rival, attempt)


@pytest.mark.asyncio
async def test_disconnected_owner_cannot_reconnect_and_inherit_permission(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt) as maintenance:
        initial_pid = maintenance.backend_pid
        async with engine.connect() as ordinary:
            assert await ordinary.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": initial_pid})
        with pytest.raises((DBAPIError, TenantUnavailable)):
            await maintenance.compare_schema("public", {})
        assert attempt.backend_pid == initial_pid


@pytest.mark.asyncio
async def test_owner_exception_releases_session_lock(tenant_record):
    engine, attempt = tenant_record
    with pytest.raises(RuntimeError, match="stop"):
        async with maintenance_connection(engine, attempt):
            raise RuntimeError("stop")
    async with engine.connect() as ordinary:
        assert await ordinary.scalar(text("SELECT pg_try_advisory_xact_lock_shared(:key)"),
                                     {"key": attempt.lock_key})


@pytest.mark.asyncio
async def test_context_rechecks_after_migration_commit(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt) as maintenance:
        await maintenance.run_migration("tv001_business_snapshot")
        async with engine.begin() as public:
            await public.execute(text("UPDATE public.tenants SET generation=2, status='active' WHERE id=:id"),
                                 {"id": attempt.tenant_id})
        with pytest.raises(TenantUnavailable, match="generation"):
            await maintenance.compare_schema("public", load_snapshot_manifest())


@pytest.mark.asyncio
async def test_shared_business_transaction_blocks_maintenance_without_waiting(tenant_record):
    engine, attempt = tenant_record
    async with engine.connect() as business:
        assert await business.scalar(text("SELECT pg_try_advisory_xact_lock_shared(:key)"),
                                     {"key": attempt.lock_key})
        with pytest.raises(TenantUnavailable, match="active transactions"):
            async with maintenance_connection(engine, attempt):
                pytest.fail("owner admitted while business transaction holds shared lock")
        assert attempt.backend_pid == 0
    async with maintenance_connection(engine, attempt) as owner:
        assert attempt.backend_pid == owner.backend_pid


@pytest.mark.asyncio
async def test_migration_rejects_unowned_connection(tenant_record):
    engine, attempt = tenant_record
    async with engine.connect() as unowned:
        with pytest.raises(TenantUnavailable, match="lock owner"):
            await upgrade_tenant(unowned, attempt.schema_name, "tv001_business_snapshot")


class SimulatedCrash(Exception):
    pass


@pytest_asyncio.fixture
async def disposable_public_db(mig_db_url, monkeypatch):
    """A fresh, migrated public database; fixture owns its entire disposal."""
    from app.services import tenant_migrator

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", mig_db_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine, raising=False)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def tenant_request():
    from app.schemas.platform import TenantCreateRequest
    slug = "recovery-" + uuid.uuid4().hex[:12]
    return TenantCreateRequest(name="Recovery test", slug=slug,
                               admin_email="admin@example.test", admin_password="private-password-123")


@pytest.mark.asyncio
async def test_seed_commit_then_platform_status_retry_uses_same_tenant(disposable_public_db, tenant_request):
    from app.services.tenant_migrator import provision_new, resume_tenant
    from app.core.tenant_utils import slug_to_schema_name

    def fail_after_seed(stage):
        if stage == "seed_commit":
            raise SimulatedCrash()

    with pytest.raises(SimulatedCrash):
        await provision_new(tenant_request, after_stage_hook=fail_after_seed)
    async with disposable_public_db.connect() as connection:
        row = (await connection.execute(text(
            "SELECT id,status FROM public.tenants WHERE slug=:slug"), {"slug": tenant_request.slug})).one()
        tenant_id = row.id
        assert row.status != "active"
    tenant = await resume_tenant(tenant_id)
    assert tenant.id == tenant_id and tenant.status == "active"
    schema = slug_to_schema_name(tenant_request.slug)
    async with disposable_public_db.connect() as connection:
        admin_count = await connection.scalar(text(
            f'SELECT count(*) FROM "{schema}".users u JOIN "{schema}".role_definitions r '
            'ON r.id=u.role_id WHERE r.role_key=:role_key'), {"role_key": "admin"})
        factory_count = await connection.scalar(text(
            f'SELECT count(*) FROM "{schema}".factories WHERE code=:code'), {"code": "DEFAULT"})
        count = await connection.scalar(text("SELECT count(*) FROM public.tenants WHERE slug=:slug"),
                                        {"slug": tenant_request.slug})
    assert (admin_count, factory_count, count) == (1, 1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["registration", "schema_created", "migration_commit",
                                   "seed_precommit", "final_platform_update"])
async def test_resume_each_crash_stage_requires_credentials_only_before_seed(
        disposable_public_db, tenant_request, stage):
    from app.services.tenant_migrator import provision_new, resume_tenant

    def crash(current):
        if current == stage:
            raise SimulatedCrash()

    with pytest.raises(SimulatedCrash):
        await provision_new(tenant_request, after_stage_hook=crash)
    async with disposable_public_db.connect() as connection:
        row = (await connection.execute(text(
            "SELECT id,status,generation,provisioning_attempt_id FROM public.tenants WHERE slug=:slug"),
            {"slug": tenant_request.slug})).one()
        assert row.status != "active"
        assert row.generation <= 1
        assert tenant_request.admin_password not in str(row)
    if stage != "final_platform_update":
        with pytest.raises(TenantUnavailable, match="credentials"):
            await resume_tenant(row.id)
        async with disposable_public_db.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM public.tenants WHERE id=:id"),
                                           {"id": row.id}) == 1
    tenant = await resume_tenant(row.id, bootstrap_request=tenant_request if stage != "final_platform_update" else None)
    assert tenant.id == row.id and tenant.status == "active"
    assert tenant.generation > row.generation
    with pytest.raises(ValueError, match="already exists"):
        await provision_new(tenant_request)


@pytest.mark.asyncio
async def test_unknown_version_and_partial_schema_refuse_without_reset(disposable_public_db, tenant_request):
    from app.services.tenant_migrator import provision_new, resume_tenant
    from app.core.tenant_utils import slug_to_schema_name
    with pytest.raises(SimulatedCrash):
        await provision_new(tenant_request, after_stage_hook=lambda stage: (
            (_ for _ in ()).throw(SimulatedCrash()) if stage == "registration" else None))
    schema = slug_to_schema_name(tenant_request.slug)
    async with disposable_public_db.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text(f'CREATE TABLE "{schema}".unreviewed (id integer)'))
    async with disposable_public_db.connect() as connection:
        tenant_id = await connection.scalar(text("SELECT id FROM public.tenants WHERE slug=:slug"),
                                            {"slug": tenant_request.slug})
    with pytest.raises(TenantUnavailable, match="partial"):
        await resume_tenant(tenant_id, bootstrap_request=tenant_request)
    async with disposable_public_db.connect() as connection:
        assert await connection.scalar(text(f'SELECT count(*) FROM "{schema}".unreviewed')) == 0
        assert await connection.scalar(text("SELECT status FROM public.tenants WHERE id=:id"),
                                       {"id": tenant_id}) == "failed"
        assert await connection.scalar(text("SELECT to_regclass(:name)"),
                                       {"name": f"{schema}.tenant_schema_version"}) is None


@pytest.mark.asyncio
async def test_crash_after_lock_before_attempt_does_not_change_registry(disposable_public_db, tenant_request):
    from app.services.tenant_migrator import provision_new, resume_tenant
    with pytest.raises(SimulatedCrash):
        await provision_new(tenant_request, after_stage_hook=lambda stage: (
            (_ for _ in ()).throw(SimulatedCrash()) if stage == "registration" else None))
    async with disposable_public_db.connect() as connection:
        before = (await connection.execute(text("""
            SELECT id,status,generation,provisioning_attempt_id FROM public.tenants WHERE slug=:slug
        """), {"slug": tenant_request.slug})).one()
    with pytest.raises(SimulatedCrash):
        await resume_tenant(before.id, bootstrap_request=tenant_request,
                            after_stage_hook=lambda stage: (
                                (_ for _ in ()).throw(SimulatedCrash())
                                if stage == "lock_acquired" else None))
    async with disposable_public_db.connect() as connection:
        after = (await connection.execute(text("""
            SELECT id,status,generation,provisioning_attempt_id FROM public.tenants WHERE id=:id
        """), {"id": before.id})).one()
        assert before == after
        assert await connection.scalar(text("SELECT pg_try_advisory_xact_lock_shared(:key)"),
                                       {"key": stable_tenant_lock_key(before.id)})
    assert (await resume_tenant(before.id, bootstrap_request=tenant_request)).status == "active"


@pytest.mark.asyncio
async def test_competing_resume_does_not_change_owner_claim(disposable_public_db, tenant_request, monkeypatch):
    from app.services import tenant_migrator
    with pytest.raises(SimulatedCrash):
        await tenant_migrator.provision_new(tenant_request, after_stage_hook=lambda stage: (
            (_ for _ in ()).throw(SimulatedCrash()) if stage == "registration" else None))
    async with disposable_public_db.connect() as connection:
        tenant_id = await connection.scalar(text("SELECT id FROM public.tenants WHERE slug=:slug"),
                                            {"slug": tenant_request.slug})
    entered, release = asyncio.Event(), asyncio.Event()
    original = tenant_migrator.MaintenanceContext.seed_tenant

    async def paused_seed(self, request, **kwargs):
        entered.set()
        await release.wait()
        return await original(self, request, **kwargs)

    monkeypatch.setattr(tenant_migrator.MaintenanceContext, "seed_tenant", paused_seed)
    winner = asyncio.create_task(tenant_migrator.resume_tenant(tenant_id, bootstrap_request=tenant_request))
    try:
        await asyncio.wait_for(entered.wait(), timeout=15)
        async with disposable_public_db.connect() as connection:
            before = (await connection.execute(text(
                "SELECT generation,provisioning_attempt_id FROM public.tenants WHERE id=:id"),
                {"id": tenant_id})).one()
        with pytest.raises(TenantUnavailable, match="active transactions"):
            await tenant_migrator.resume_tenant(tenant_id, bootstrap_request=tenant_request)
        async with disposable_public_db.connect() as connection:
            after = (await connection.execute(text(
                "SELECT generation,provisioning_attempt_id FROM public.tenants WHERE id=:id"),
                {"id": tenant_id})).one()
        assert before == after
    finally:
        release.set()
        assert (await winner).status == "active"


@pytest.mark.asyncio
async def test_seed_failure_rolls_back_all_rows_and_retry_same_tenant(
        disposable_public_db, tenant_request, monkeypatch):
    from app.services import tenant_service, tenant_migrator
    from app.core.tenant_utils import slug_to_schema_name

    original = tenant_service._seed_first_admin

    async def crash_after_factory(*args, **kwargs):
        raise SimulatedCrash("no credentials in stored failure")

    monkeypatch.setattr(tenant_service, "_seed_first_admin", crash_after_factory)
    with pytest.raises(SimulatedCrash):
        await tenant_migrator.provision_new(tenant_request)
    schema = slug_to_schema_name(tenant_request.slug)
    async with disposable_public_db.connect() as connection:
        row = (await connection.execute(text(
            "SELECT id,status,provisioning_error FROM public.tenants WHERE slug=:slug"),
            {"slug": tenant_request.slug})).one()
        assert row.status == "failed" and row.provisioning_error == "SimulatedCrash"
        for table in ("users", "role_definitions", "role_permissions", "factories", "product_lines"):
            assert await connection.scalar(text(f'SELECT count(*) FROM "{schema}"."{table}"')) == 0
    with pytest.raises(TenantUnavailable, match="credentials"):
        await tenant_migrator.resume_tenant(row.id)
    monkeypatch.setattr(tenant_service, "_seed_first_admin", original)
    assert (await tenant_migrator.resume_tenant(row.id, bootstrap_request=tenant_request)).status == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["unknown_version", "missing_column"])
async def test_committed_schema_corruption_never_stamped_or_deleted(
        disposable_public_db, tenant_request, corruption):
    from app.services.tenant_migrator import provision_new, resume_tenant
    from app.core.tenant_utils import slug_to_schema_name

    def crash(stage):
        if stage == "migration_commit":
            raise SimulatedCrash()

    with pytest.raises(SimulatedCrash):
        await provision_new(tenant_request, after_stage_hook=crash)
    schema = slug_to_schema_name(tenant_request.slug)
    async with disposable_public_db.begin() as connection:
        tenant_id = await connection.scalar(text("SELECT id FROM public.tenants WHERE slug=:slug"),
                                            {"slug": tenant_request.slug})
        if corruption == "unknown_version":
            await connection.execute(text(f'UPDATE "{schema}".tenant_schema_version '
                                          "SET version_num='unknown_revision'"))
        else:
            await connection.execute(text(f'ALTER TABLE "{schema}".users DROP COLUMN display_name'))
    with pytest.raises(TenantUnavailable, match="unknown|partial|match"):
        await resume_tenant(tenant_id, bootstrap_request=tenant_request)
    async with disposable_public_db.connect() as connection:
        assert await connection.scalar(text("SELECT status FROM public.tenants WHERE id=:id"),
                                       {"id": tenant_id}) == "failed"
        if corruption == "unknown_version":
            assert await connection.scalar(text(
                f'SELECT version_num FROM "{schema}".tenant_schema_version')) == "unknown_revision"
        else:
            assert await connection.scalar(text("SELECT to_regclass(:table)"),
                                           {"table": f"{schema}.users"}) is not None


@pytest.mark.asyncio
async def test_service_provision_uses_coordinator_and_never_falls_back_public(
        disposable_public_db, tenant_request):
    from app.services.tenant_service import TenantService
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.tenant_utils import slug_to_schema_name

    async with AsyncSession(disposable_public_db) as platform:
        tenant = await TenantService.provision(platform, tenant_request)
    assert tenant.status == "active"
    schema = slug_to_schema_name(tenant_request.slug)
    async with disposable_public_db.connect() as connection:
        count = await connection.scalar(text(f'SELECT count(*) FROM "{schema}".users'))
        public_admin = await connection.scalar(text(
            'SELECT count(*) FROM public.users WHERE email=:email'),
            {"email": tenant_request.admin_email})
        assert count == 1 and public_admin == 0


@pytest.mark.asyncio
async def test_cli_resumes_postseed_tenant_without_legacy_subprocess(
        disposable_public_db, tenant_request, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.cli import tenant_migrate
    from app.services.tenant_migrator import provision_new

    with pytest.raises(SimulatedCrash):
        await provision_new(tenant_request, after_stage_hook=lambda stage: (
            (_ for _ in ()).throw(SimulatedCrash()) if stage == "seed_commit" else None))
    monkeypatch.setattr(tenant_migrate, "async_session", async_sessionmaker(disposable_public_db))
    await tenant_migrate.main(slug=tenant_request.slug)
    async with disposable_public_db.connect() as connection:
        assert await connection.scalar(text(
            "SELECT status FROM public.tenants WHERE slug=:slug"),
            {"slug": tenant_request.slug}) == "active"


@pytest.mark.asyncio
async def test_active_current_resume_and_cli_are_read_only_noops(
        disposable_public_db, tenant_request, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.tenant_migrator import provision_new, resume_tenant
    from app.cli import tenant_migrate

    tenant = await provision_new(tenant_request)
    schema = tenant.schema_name
    async with disposable_public_db.connect() as connection:
        before = (await connection.execute(text("""
            SELECT status,generation,provisioning_attempt_id,provisioning_step
            FROM public.tenants WHERE id=:id
        """), {"id": tenant.id})).one()
        version = await connection.scalar(text(
            f'SELECT version_num FROM "{schema}".tenant_schema_version'))
    assert (await resume_tenant(tenant.id)).id == tenant.id
    monkeypatch.setattr(tenant_migrate, "async_session", async_sessionmaker(disposable_public_db))
    await tenant_migrate.main(slug=tenant_request.slug)
    async with disposable_public_db.connect() as connection:
        after = (await connection.execute(text("""
            SELECT status,generation,provisioning_attempt_id,provisioning_step
            FROM public.tenants WHERE id=:id
        """), {"id": tenant.id})).one()
        assert before == after
        assert await connection.scalar(text(
            f'SELECT version_num FROM "{schema}".tenant_schema_version')) == version
        assert await connection.scalar(text(f'SELECT count(*) FROM "{schema}".users')) == 1
        assert await connection.scalar(text(f'SELECT count(*) FROM "{schema}".factories')) == 1
        assert await connection.scalar(text(f'SELECT count(*) FROM "{schema}".role_definitions')) == 7
        assert await connection.scalar(text(
            "SELECT count(*) FROM public.tenant_migrations WHERE tenant_id=:id"),
            {"id": tenant.id}) == 0


@pytest.mark.asyncio
async def test_active_fast_path_refuses_stale_generation_and_exclusive_owner(
        disposable_public_db, tenant_request):
    from app.services.tenant_migrator import _active_current, provision_new, resume_tenant

    tenant = await provision_new(tenant_request)
    async with disposable_public_db.begin() as connection:
        await connection.execute(text(
            'UPDATE public.tenants SET generation=generation+1 WHERE id=:id'), {"id": tenant.id})
    with pytest.raises(TenantUnavailable, match="generation"):
        await _active_current(tenant)
    async with disposable_public_db.connect() as owner:
        key = stable_tenant_lock_key(tenant.id)
        assert await owner.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
        await owner.commit()
        try:
            with pytest.raises(TenantUnavailable, match="maintenance"):
                await resume_tenant(tenant.id)
        finally:
            assert await owner.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    async with disposable_public_db.connect() as connection:
        assert await connection.scalar(text('SELECT generation FROM public.tenants WHERE id=:id'),
                                       {"id": tenant.id}) == tenant.generation + 1


@pytest.mark.asyncio
async def test_active_parity_drift_is_not_a_noop(disposable_public_db, tenant_request):
    from app.services.tenant_migrator import provision_new, resume_tenant

    tenant = await provision_new(tenant_request)
    async with disposable_public_db.begin() as connection:
        await connection.execute(text(f'ALTER TABLE "{tenant.schema_name}".users DROP COLUMN display_name'))
    with pytest.raises(TenantUnavailable, match="match"):
        await resume_tenant(tenant.id)
    async with disposable_public_db.connect() as connection:
        assert await connection.scalar(text("SELECT status FROM public.tenants WHERE id=:id"),
                                       {"id": tenant.id}) == "failed"
        assert await connection.scalar(text(
            f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == REVISION


@pytest.mark.asyncio
async def test_active_tenant_growth_and_permission_edit_keep_resume_read_only(
        disposable_public_db, tenant_request, monkeypatch):
    """Ordinary tenant edits cannot turn a complete bootstrap into a failed tenant."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database import TenantSession
    from app.cli import tenant_migrate
    from app.services.tenant_migrator import provision_new, resume_tenant

    tenant = await provision_new(tenant_request)
    binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, "business")
    extra_factory, extra_user, extra_role = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with AsyncSession(bind=disposable_public_db, sync_session_class=TenantSession,
                            binding=binding) as ordinary:
        admin_role = await ordinary.scalar(text(
            "SELECT id FROM role_definitions WHERE role_key='admin'"))
        await ordinary.execute(text("""
            INSERT INTO factories (id,code,name,is_active)
            VALUES (:id,'ADDED','Additional factory',true)
        """), {"id": extra_factory})
        await ordinary.execute(text("""
            INSERT INTO product_lines (code,name,factory_id,is_active)
            VALUES ('ADDED-LINE','Additional line',:factory,true)
        """), {"factory": extra_factory})
        await ordinary.execute(text("""
            INSERT INTO role_definitions (id,role_key,name_zh,name_en,is_system,is_editable,is_active,sort_order)
            VALUES (:id,'extra_role','额外角色','Extra role',false,true,true,99)
        """), {"id": extra_role})
        await ordinary.execute(text("""
            INSERT INTO role_permissions (id,role_id,module,permission_level)
            VALUES (:id,:role,'dashboard',1)
        """), {"id": uuid.uuid4(), "role": extra_role})
        await ordinary.execute(text("""
            INSERT INTO users (user_id,username,email,display_name,password_hash,role_id,
                               legacy_role,factory_id,is_active)
            VALUES (:id,'extra@example.test','extra@example.test','Additional user',
                    'test-hash',:role,'viewer',:factory,true)
        """), {"id": extra_user, "role": extra_role, "factory": extra_factory})
        await ordinary.execute(text("""
            INSERT INTO user_factories (id,user_id,factory_id) VALUES (:id,:user,:factory)
        """), {"id": uuid.uuid4(), "user": extra_user, "factory": extra_factory})
        await ordinary.execute(text("""
            INSERT INTO user_product_lines (id,user_id,product_line_code)
            VALUES (:id,:user,'ADDED-LINE')
        """), {"id": uuid.uuid4(), "user": extra_user})
        await ordinary.execute(text("""
            UPDATE role_permissions SET permission_level=4
            WHERE role_id=:role AND module='dashboard'
        """), {"role": admin_role})
        await ordinary.commit()

    async with disposable_public_db.connect() as connection:
        before = (await connection.execute(text("""
            SELECT status,generation,provisioning_attempt_id,provisioning_step
            FROM public.tenants WHERE id=:id
        """), {"id": tenant.id})).one()
        version = await connection.scalar(text(
            f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version'))
    assert (await resume_tenant(tenant.id)).status == "active"
    from sqlalchemy.ext.asyncio import async_sessionmaker
    monkeypatch.setattr(tenant_migrate, "async_session", async_sessionmaker(disposable_public_db))
    await tenant_migrate.main(all_tenants=True)
    async with disposable_public_db.connect() as connection:
        after = (await connection.execute(text("""
            SELECT status,generation,provisioning_attempt_id,provisioning_step
            FROM public.tenants WHERE id=:id
        """), {"id": tenant.id})).one()
        assert before == after
        assert await connection.scalar(text(
            f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == version
        assert await connection.scalar(text(f'SELECT count(*) FROM "{tenant.schema_name}".users')) == 2
        assert await connection.scalar(text(f'SELECT count(*) FROM "{tenant.schema_name}".factories')) == 2
        assert await connection.scalar(text(f'SELECT count(*) FROM "{tenant.schema_name}".role_definitions')) == 8
        assert await connection.scalar(text(
            "SELECT count(*) FROM public.tenant_migrations WHERE tenant_id=:id"),
            {"id": tenant.id}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["admin_assignment", "bootstrap_permission"])
async def test_incomplete_seed_relationship_refuses_without_reseeding(
        disposable_public_db, tenant_request, missing):
    from app.services.tenant_migrator import provision_new, resume_tenant
    from app.database import TenantSession
    from sqlalchemy.ext.asyncio import AsyncSession

    tenant = await provision_new(tenant_request)
    binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, "business")
    async with AsyncSession(bind=disposable_public_db, sync_session_class=TenantSession,
                            binding=binding) as ordinary:
        if missing == "admin_assignment":
            await ordinary.execute(text("DELETE FROM user_factories"))
        else:
            await ordinary.execute(text("""
                DELETE FROM role_permissions WHERE module='dashboard'
                AND role_id=(SELECT id FROM role_definitions WHERE role_key='admin')
            """))
        await ordinary.commit()

    with pytest.raises(TenantUnavailable, match="partial tenant seed"):
        await resume_tenant(tenant.id)
    async with disposable_public_db.connect() as connection:
        assert await connection.scalar(text(
            "SELECT status FROM public.tenants WHERE id=:id"), {"id": tenant.id}) == "failed"
        if missing == "admin_assignment":
            query = f'SELECT count(*) FROM "{tenant.schema_name}".user_factories'
        else:
            query = (f'SELECT count(*) FROM "{tenant.schema_name}".role_permissions '
                     f'WHERE module=\'dashboard\' AND role_id=(SELECT id FROM '
                     f'"{tenant.schema_name}".role_definitions WHERE role_key=\'admin\')')
        assert await connection.scalar(text(query)) == 0


@pytest.mark.asyncio
async def test_empty_seed_of_previously_active_tenant_requires_manual_review(
        disposable_public_db, tenant_request):
    from app.services.tenant_migrator import provision_new, resume_tenant
    from app.database import TenantSession
    from sqlalchemy.ext.asyncio import AsyncSession

    tenant = await provision_new(tenant_request)
    binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, "business")
    async with AsyncSession(bind=disposable_public_db, sync_session_class=TenantSession,
                            binding=binding) as ordinary:
        for table in ("users", "role_permissions", "role_definitions", "product_lines", "factories"):
            await ordinary.execute(text(f'DELETE FROM {table}'))
        await ordinary.commit()

    with pytest.raises(TenantUnavailable, match="manual review"):
        await resume_tenant(tenant.id, bootstrap_request=tenant_request)
    async with disposable_public_db.connect() as connection:
        assert await connection.scalar(text(
            'SELECT status FROM public.tenants WHERE id=:id'), {"id": tenant.id}) == "failed"
        assert await connection.scalar(text(f'SELECT count(*) FROM "{tenant.schema_name}".users')) == 0
        generation = await connection.scalar(text(
            'SELECT generation FROM public.tenants WHERE id=:id'), {"id": tenant.id})
    with pytest.raises(TenantUnavailable, match="manual review"):
        await resume_tenant(tenant.id, bootstrap_request=tenant_request)
    async with disposable_public_db.connect() as connection:
        assert await connection.scalar(text(
            'SELECT generation FROM public.tenants WHERE id=:id'), {"id": tenant.id}) == generation
        assert await connection.scalar(text(f'SELECT count(*) FROM "{tenant.schema_name}".users')) == 0


@pytest.mark.asyncio
async def test_active_seed_loss_failure_is_recorded_before_owner_unlock(
        disposable_public_db, tenant_request, monkeypatch):
    """A second resume cannot rebootstrap in the failure-recording gap."""
    from app.database import TenantSession
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.services import tenant_migrator

    tenant = await tenant_migrator.provision_new(tenant_request)
    binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, "business")
    async with AsyncSession(bind=disposable_public_db, sync_session_class=TenantSession,
                            binding=binding) as ordinary:
        for table in ("users", "role_permissions", "role_definitions", "product_lines", "factories"):
            await ordinary.execute(text(f'DELETE FROM {table}'))
        await ordinary.commit()

    entered, release = asyncio.Event(), asyncio.Event()
    original = tenant_migrator._record_failure

    async def paused_failure(attempt, exc):
        entered.set()
        await release.wait()
        await original(attempt, exc)

    monkeypatch.setattr(tenant_migrator, "_record_failure", paused_failure)
    first = asyncio.create_task(tenant_migrator.resume_tenant(tenant.id,
                                                              bootstrap_request=tenant_request))
    try:
        await asyncio.wait_for(entered.wait(), timeout=15)
        with pytest.raises(TenantUnavailable):
            await tenant_migrator.resume_tenant(tenant.id, bootstrap_request=tenant_request)
    finally:
        release.set()
        with pytest.raises(TenantUnavailable, match="manual review"):
            await first
    async with disposable_public_db.connect() as connection:
        assert await connection.scalar(text(f'SELECT count(*) FROM "{tenant.schema_name}".users')) == 0
