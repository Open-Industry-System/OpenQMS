"""Database-backed tenant admission checks on an isolated disposable _test DB."""
import os
import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.tenant_transaction import (
    TenantBinding, TenantUnavailable, stable_tenant_lock_key, strict_tenant_search_path_sql,
)


@pytest_asyncio.fixture
async def tenant_registry():
    url = os.environ["TEST_DATABASE_URL"]
    assert url.rsplit("/", 1)[-1].endswith("_test"), "disposable test database required"
    engine = create_async_engine(url, poolclass=NullPool)
    suffix = uuid.uuid4().hex[:12]
    tenants = [
        TenantBinding(uuid.uuid4(), f"tenant_tx_{suffix}_a", 0, "business"),
        TenantBinding(uuid.uuid4(), f"tenant_tx_{suffix}_b", 0, "business"),
    ]
    try:
        async with engine.begin() as conn:
            for binding in tenants:
                await conn.execute(text(f'CREATE SCHEMA "{binding.schema_name}"'))
                await conn.execute(text(
                    f'CREATE TABLE "{binding.schema_name}".factories '
                    '(id uuid PRIMARY KEY, code text NOT NULL, name text NOT NULL)'
                ))
                await conn.execute(text(
                    "INSERT INTO public.tenants (id, name, slug, schema_name, subdomain, status, generation) "
                    "VALUES (:id, :name, :slug, :schema, :slug, 'active', 0)"
                ), {"id": binding.tenant_id, "name": suffix, "slug": f"{suffix}-{binding.schema_name[-1]}", "schema": binding.schema_name})
        yield engine, tenants
    finally:
        await engine.dispose()
        cleanup = create_async_engine(url, poolclass=NullPool)
        try:
            async with cleanup.begin() as conn:
                for binding in tenants:
                    await conn.execute(text("DELETE FROM public.tenants WHERE id=:id"), {"id": binding.tenant_id})
                    await conn.execute(text(f'DROP SCHEMA IF EXISTS "{binding.schema_name}" CASCADE'))
        finally:
            await cleanup.dispose()


@pytest.fixture
def tenant_session_factory(tenant_registry):
    engine, _ = tenant_registry
    from app.database import tenant_async_session

    @asynccontextmanager
    async def create(binding):
        async with tenant_async_session(bind=engine, binding=binding) as session:
            yield session

    return create


@pytest.fixture
def platform_session_factory(tenant_registry):
    engine, _ = tenant_registry
    from app.database import async_session

    @asynccontextmanager
    async def create():
        async with async_session(bind=engine) as session:
            yield session

    return create


@pytest.mark.asyncio
async def test_commit_rollback_and_recheckout_rebind_tenant(tenant_registry, tenant_session_factory, platform_session_factory):
    _, (tenant_a, tenant_b) = tenant_registry
    async with tenant_session_factory(tenant_a) as session:
        await session.execute(text("INSERT INTO factories (id,code,name) VALUES (:id,'TX-A','A')"), {"id": uuid.uuid4()})
        await session.commit()
        assert await session.scalar(text("SELECT count(*) FROM factories WHERE code='TX-A'")) == 1
        await session.rollback()
        assert await session.scalar(text("SELECT count(*) FROM factories WHERE code='TX-A'")) == 1
        await session.commit()
        assert await session.scalar(text("SELECT count(*) FROM factories WHERE code='TX-A'")) == 1
    async with tenant_session_factory(tenant_b) as other:
        assert await other.scalar(text("SELECT count(*) FROM factories WHERE code='TX-A'")) == 0
    async with platform_session_factory() as public:
        assert await public.scalar(text("SELECT count(*) FROM factories WHERE code='TX-A'")) == 0


@pytest.mark.asyncio
async def test_stale_generation_and_inactive_status_deny_before_business_sql(tenant_registry, tenant_session_factory, platform_session_factory):
    _, (tenant_a, _) = tenant_registry
    async with platform_session_factory() as public:
        await public.execute(text("UPDATE public.tenants SET generation=1 WHERE id=:id"), {"id": tenant_a.tenant_id})
        await public.commit()
    async with tenant_session_factory(tenant_a) as stale:
        with pytest.raises(TenantUnavailable):
            await stale.execute(text("INSERT INTO factories (id,code,name) VALUES (:id,'DENIED','Denied')"), {"id": uuid.uuid4()})
    fresh = TenantBinding(tenant_a.tenant_id, tenant_a.schema_name, 1, "business")
    async with platform_session_factory() as public:
        await public.execute(text("UPDATE public.tenants SET status='suspended' WHERE id=:id"), {"id": tenant_a.tenant_id})
        await public.commit()
    async with tenant_session_factory(fresh) as inactive:
        with pytest.raises(TenantUnavailable):
            await inactive.scalar(text("SELECT count(*) FROM factories"))


@pytest.mark.asyncio
async def test_missing_binding_and_maintenance_mode_fail_closed(tenant_registry):
    engine, (tenant_a, _) = tenant_registry
    from app.database import tenant_async_session

    async with tenant_async_session(bind=engine) as missing:
        with pytest.raises(TenantUnavailable):
            await missing.scalar(text("SELECT count(*) FROM factories"))
    maintenance = TenantBinding(tenant_a.tenant_id, tenant_a.schema_name, 0, "maintenance")
    async with tenant_async_session(bind=engine, binding=maintenance) as forbidden:
        with pytest.raises(TenantUnavailable):
            await forbidden.scalar(text("SELECT count(*) FROM factories"))


def test_strict_search_path_and_stable_lock_key():
    tenant_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert stable_tenant_lock_key(tenant_id) == stable_tenant_lock_key(tenant_id)
    assert -(1 << 63) <= stable_tenant_lock_key(tenant_id) < (1 << 63)
    assert strict_tenant_search_path_sql("tenant_acme") == 'SET LOCAL search_path TO "tenant_acme", pg_catalog'
    for bad in ("public", "tenant_acme;DROP TABLE public.tenants", "tenant_\"evil"):
        with pytest.raises(ValueError):
            strict_tenant_search_path_sql(bad)


@pytest.mark.asyncio
async def test_generation_rechecked_after_commit_and_exclusive_lock_denies(tenant_registry, tenant_session_factory, platform_session_factory):
    engine, (tenant_a, _) = tenant_registry
    async with tenant_session_factory(tenant_a) as session:
        assert await session.scalar(text("SELECT count(*) FROM factories")) == 0
        await session.commit()
        async with platform_session_factory() as public:
            await public.execute(text("UPDATE public.tenants SET generation=1 WHERE id=:id"), {"id": tenant_a.tenant_id})
            await public.commit()
        with pytest.raises(TenantUnavailable):
            await session.scalar(text("SELECT count(*) FROM factories"))

    updated = TenantBinding(tenant_a.tenant_id, tenant_a.schema_name, 1, "business")
    async with engine.connect() as owner:
        await owner.execute(text("SELECT pg_advisory_lock(:key)"), {"key": stable_tenant_lock_key(tenant_a.tenant_id)})
        try:
            async with tenant_session_factory(updated) as blocked:
                with pytest.raises(TenantUnavailable, match="maintenance"):
                    await blocked.scalar(text("SELECT count(*) FROM factories"))
        finally:
            await owner.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": stable_tenant_lock_key(tenant_a.tenant_id)})


@pytest.mark.asyncio
async def test_queued_log_cannot_write_after_generation_changes(tenant_registry, platform_session_factory, monkeypatch):
    import asyncio
    from app.config import settings
    from app.core.logging_handler import drain_log_queue
    from app.database import async_session

    monkeypatch.setattr(settings, "TENANT_MODE", "dev")
    engine, (tenant_a, _) = tenant_registry
    async with engine.begin() as conn:
        await conn.execute(text(
            f'CREATE TABLE "{tenant_a.schema_name}".system_logs '
            '(log_id uuid PRIMARY KEY, logger_name varchar(100) NOT NULL, '
            'level varchar(20) NOT NULL, message text NOT NULL, '
            'module varchar(200), traceback text, occurred_at timestamptz NOT NULL DEFAULT now())'
        ))
    async with platform_session_factory() as public:
        await public.execute(text("UPDATE public.tenants SET generation=1 WHERE id=:id"), {"id": tenant_a.tenant_id})
        await public.commit()

    queue = asyncio.Queue()
    queue.put_nowait({"schema": tenant_a.schema_name, "binding": tenant_a,
                      "logger_name": "test", "level": "WARNING", "message": "stale-queued-log",
                      "module": None, "traceback": None})
    drainer = asyncio.create_task(drain_log_queue(queue, async_session))
    await asyncio.wait_for(queue.join(), timeout=5)
    drainer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await drainer
    async with engine.connect() as conn:
        assert await conn.scalar(text(
            f'SELECT count(*) FROM "{tenant_a.schema_name}".system_logs WHERE message=\'stale-queued-log\''
        )) == 0
        assert await conn.scalar(text(
            "SELECT count(*) FROM public.system_logs WHERE message='stale-queued-log'"
        )) == 0


@pytest.mark.asyncio
async def test_pending_and_mismatched_schema_are_not_admitted(tenant_registry, tenant_session_factory, platform_session_factory):
    _, (tenant_a, tenant_b) = tenant_registry
    wrong_schema = TenantBinding(tenant_a.tenant_id, tenant_b.schema_name, 0, "business")
    async with tenant_session_factory(wrong_schema) as wrong:
        with pytest.raises(TenantUnavailable):
            await wrong.scalar(text("SELECT count(*) FROM factories"))
    async with platform_session_factory() as public:
        await public.execute(text("UPDATE public.tenants SET status='pending' WHERE id=:id"), {"id": tenant_a.tenant_id})
        await public.commit()
    async with tenant_session_factory(tenant_a) as pending:
        with pytest.raises(TenantUnavailable):
            await pending.scalar(text("SELECT count(*) FROM factories"))
