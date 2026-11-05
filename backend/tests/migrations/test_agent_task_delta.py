"""Real PostgreSQL task delta and owned independent tenant upgrade coverage."""
import asyncio
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests.migrations.test_agent_task_core import _migration_config, _sync_engine
from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from app.services.tenant_schema_diff import compare_business_schema, load_snapshot_manifest

TASK_TABLES = {"agent_tasks", "agent_runs", "agent_task_grants", "agent_task_messages"}
PUBLIC_REVISION = "20260926_agent_task_core"
TENANT_REVISION = "tv002_agent_task_core"


def test_public_task_delta_upgrade_and_downgrade(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, PUBLIC_REVISION)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as connection:
            assert TASK_TABLES <= set(sa.inspect(connection).get_table_names())
            assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == PUBLIC_REVISION
        command.downgrade(config, "20260927_tenant_attempt")
        with engine.connect() as connection:
            assert not TASK_TABLES & set(sa.inspect(connection).get_table_names())
            assert "agent_plugin_installations" in sa.inspect(connection).get_table_names()
        command.upgrade(config, PUBLIC_REVISION)
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_valid_ancestor_is_forward_upgraded_without_reseeding(mig_db_url, monkeypatch):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, "20260927_tenant_attempt")
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    monkeypatch.setattr(tenant_migrator, "REVISION", "tv001_business_snapshot")
    request = TenantCreateRequest(name="Ancestor", slug=f"ancestor-{uuid.uuid4().hex[:10]}",
        admin_email="admin@example.test", admin_password="AncestorTest123")
    try:
        tenant = await tenant_migrator.provision_new(request)
        async with engine.connect() as connection:
            users_before = (await connection.execute(sa.text(f'SELECT user_id FROM "{tenant.schema_name}".users'))).scalars().all()
            public_users = await connection.scalar(sa.text("SELECT count(*) FROM public.users"))
            public_factories = await connection.scalar(sa.text("SELECT count(*) FROM public.factories"))
        await asyncio.to_thread(command.upgrade, config, PUBLIC_REVISION)
        monkeypatch.setattr(tenant_migrator, "REVISION", TENANT_REVISION)
        upgraded = await tenant_migrator.resume_tenant(tenant.id)
        assert upgraded.status == "active" and upgraded.generation == tenant.generation + 1
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT_REVISION
            assert (await connection.execute(sa.text(f'SELECT user_id FROM "{tenant.schema_name}".users'))).scalars().all() == users_before
            assert await compare_business_schema(connection, "public", tenant.schema_name, load_snapshot_manifest()) == []
            assert await connection.scalar(sa.text("SELECT count(*) FROM public.users")) == public_users
            assert await connection.scalar(sa.text("SELECT count(*) FROM public.factories")) == public_factories
        # Downgrade through the same owner-bound runner, retaining all baseline tables.
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            await maintenance.run_downgrade("tv001_business_snapshot")
            assert await maintenance.schema_state() == "ancestor"
            await maintenance.run_migration(TENANT_REVISION)
            assert await maintenance.compare_schema("public", load_snapshot_manifest()) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_partial_ancestor_refused_before_forward_ddl(mig_db_url, monkeypatch):
    from app.core.tenant_transaction import TenantUnavailable
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, "20260927_tenant_attempt")
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    monkeypatch.setattr(tenant_migrator, "REVISION", "tv001_business_snapshot")
    request = TenantCreateRequest(name="Partial ancestor", slug=f"partial-{uuid.uuid4().hex[:10]}",
        admin_email="admin@example.test", admin_password="PartialTest123")
    try:
        tenant = await tenant_migrator.provision_new(request)
        await asyncio.to_thread(command.upgrade, config, PUBLIC_REVISION)
        monkeypatch.setattr(tenant_migrator, "REVISION", TENANT_REVISION)
        async with engine.begin() as connection:
            await connection.execute(sa.text(f'ALTER TABLE "{tenant.schema_name}".users DROP COLUMN display_name'))
        with pytest.raises(TenantUnavailable, match="partial"):
            await tenant_migrator.resume_tenant(tenant.id)
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == "tv001_business_snapshot"
            assert not await connection.scalar(sa.text("SELECT to_regclass(:name)"), {"name": f"{tenant.schema_name}.agent_tasks"})
    finally:
        await engine.dispose()
