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
    MaintenanceAttempt, bind_maintenance_transaction, maintenance_connection,
)
from alembic_tenant import upgrade_tenant
from app.services.tenant_schema_diff import load_snapshot_manifest


@pytest_asyncio.fixture
async def tenant_record(mig_db_url):
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    cfg.set_main_option("sqlalchemy.url", mig_db_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")
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
