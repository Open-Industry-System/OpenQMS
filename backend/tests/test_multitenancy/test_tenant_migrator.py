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
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.tenant_transaction import (
    TenantBinding, TenantUnavailable, bind_business_transaction, stable_tenant_lock_key,
)
from app.services.tenant_migrator import (
    MaintenanceAttempt, bind_maintenance_transaction, maintenance_connection, maintenance_seed_session,
)
from alembic_tenant import upgrade_tenant


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
    async with maintenance_connection(engine, attempt) as connection:
        pid = await connection.scalar(text("SELECT pg_backend_pid()"))
        await upgrade_tenant(connection, attempt.schema_name, "tv001_business_snapshot")
        await connection.commit()
        await bind_maintenance_transaction(connection, attempt)
        async with maintenance_seed_session(connection, attempt) as seed:
            await seed.execute(text("INSERT INTO factories (id,code,name) VALUES (:id,'MAINT','Maintenance')"),
                               {"id": uuid.uuid4()})
            await seed.commit()
        await bind_maintenance_transaction(connection, attempt)
        assert await connection.scalar(text("SELECT count(*) FROM factories WHERE code='MAINT'")) == 1
        assert await connection.scalar(text("SELECT pg_backend_pid()")) == pid == attempt.backend_pid
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
async def test_competing_owner_fails_immediately_and_does_not_inherit_pid(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt) as owner:
        rival = replace(attempt, backend_pid=0)
        with pytest.raises(TenantUnavailable, match="active transactions"):
            async with maintenance_connection(engine, rival):
                pytest.fail("competing owner admitted")
        assert rival.backend_pid == 0
        assert await owner.scalar(text("SELECT pg_backend_pid()")) == attempt.backend_pid


@pytest.mark.asyncio
async def test_wrong_attempt_generation_and_schema_cannot_bind(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt) as owner:
        for changed in (replace(attempt, attempt_id=uuid.uuid4()),
                        replace(attempt, generation=2),
                        replace(attempt, schema_name="tenant_wrong")):
            with pytest.raises(TenantUnavailable):
                await bind_maintenance_transaction(owner, changed)
            await owner.rollback()
        await bind_maintenance_transaction(owner, attempt)
        await owner.commit()
        async with engine.begin() as public:
            await public.execute(text("UPDATE public.tenants SET provisioning_attempt_id=:new WHERE id=:id"),
                                 {"id": attempt.tenant_id, "new": uuid.uuid4()})
        with pytest.raises(TenantUnavailable):
            await bind_maintenance_transaction(owner, attempt)


@pytest.mark.asyncio
async def test_lost_lock_and_wrong_physical_connection_cannot_bind(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt) as owner:
        async with engine.connect() as rival:
            with pytest.raises(TenantUnavailable):
                await bind_maintenance_transaction(rival, attempt)
        assert await owner.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": attempt.lock_key})
        await owner.commit()
        with pytest.raises(TenantUnavailable, match="lock"):
            await bind_maintenance_transaction(owner, attempt)


@pytest.mark.asyncio
async def test_disconnected_owner_cannot_reconnect_and_inherit_permission(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt) as owner:
        initial_pid = attempt.backend_pid
        await owner.invalidate()  # Drops the locked PostgreSQL backend/session.
        await owner.rollback()
        with pytest.raises(TenantUnavailable):
            await bind_maintenance_transaction(owner, attempt)
        assert attempt.backend_pid == initial_pid


@pytest.mark.asyncio
async def test_owner_exception_releases_session_lock(tenant_record):
    engine, attempt = tenant_record
    with pytest.raises(RuntimeError, match="stop"):
        async with maintenance_connection(engine, attempt) as owner:
            await bind_maintenance_transaction(owner, attempt)
            raise RuntimeError("stop")
    async with engine.connect() as ordinary:
        assert await ordinary.scalar(text("SELECT pg_try_advisory_xact_lock_shared(:key)"),
                                     {"key": attempt.lock_key})


@pytest.mark.asyncio
async def test_seed_rechecks_after_commit_and_rejects_stale_platform_state(tenant_record):
    engine, attempt = tenant_record
    async with maintenance_connection(engine, attempt) as owner:
        await upgrade_tenant(owner, attempt.schema_name, "tv001_business_snapshot")
        await owner.commit()
        async with maintenance_seed_session(owner, attempt) as seed:
            for code in ("FIRST", "SECOND"):
                await seed.execute(text("INSERT INTO factories (id,code,name) VALUES (:id,:code,'Seed')"),
                                   {"id": uuid.uuid4(), "code": code})
                await seed.commit()
            assert await seed.scalar(text("SELECT count(*) FROM factories")) == 2
            await seed.commit()
            async with engine.begin() as public:
                await public.execute(text("UPDATE public.tenants SET generation=2, status='active' WHERE id=:id"),
                                     {"id": attempt.tenant_id})
            with pytest.raises(TenantUnavailable, match="generation"):
                await seed.execute(text("INSERT INTO factories (id,code,name) VALUES (:id,'STALE','Denied')"),
                                   {"id": uuid.uuid4()})
            await seed.rollback()
    async with engine.connect() as public:
        assert await public.scalar(text(f'SELECT count(*) FROM "{attempt.schema_name}".factories')) == 2


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
        assert attempt.backend_pid == await owner.scalar(text("SELECT pg_backend_pid()"))


@pytest.mark.asyncio
async def test_migration_rejects_unowned_connection(tenant_record):
    engine, attempt = tenant_record
    async with engine.connect() as unowned:
        with pytest.raises(TenantUnavailable, match="lock owner"):
            await upgrade_tenant(unowned, attempt.schema_name, "tv001_business_snapshot")
