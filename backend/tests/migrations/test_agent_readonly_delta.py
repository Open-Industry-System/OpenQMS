"""Owned upgrade from populated reviewed ancestors, rejecting partial deltas."""
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

LATEST = "tv003_agent_readonly_delivery"
NEW_TABLES = {"agent_projection_receipts", "agent_run_events", "agent_results",
              "agent_event_receipts", "agent_result_receipts"}


def test_public_readonly_delta_roundtrip(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, "20260930_agent_readonly_delivery")
    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as conn:
            assert NEW_TABLES <= set(sa.inspect(conn).get_table_names())
            assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "20260930_agent_readonly_delivery"
        command.downgrade(config, "20260926_agent_task_core")
        with engine.connect() as conn:
            assert not NEW_TABLES & set(sa.inspect(conn).get_table_names())
            assert "claim_key" not in {c["name"] for c in sa.inspect(conn).get_columns("agent_runs")}
        command.upgrade(config, "20260930_agent_readonly_delivery")
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("ancestor,public_head", [("tv001_business_snapshot", "20260927_tenant_attempt"),
    ("tv002_agent_task_core", "20260926_agent_task_core")])
async def test_populated_reviewed_ancestors_upgrade_with_full_parity(mig_db_url, monkeypatch, ancestor, public_head):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, public_head)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    monkeypatch.setattr(tenant_migrator, "REVISION", ancestor)
    request = TenantCreateRequest(name="Readonly ancestor", slug=f"readonly-{uuid.uuid4().hex[:10]}",
        admin_email="admin@example.test", admin_password="ReadonlyTest123")
    try:
        tenant = await tenant_migrator.provision_new(request)
        async with engine.connect() as conn:
            users = (await conn.execute(sa.text(f'SELECT user_id FROM "{tenant.schema_name}".users'))).scalars().all()
        await asyncio.to_thread(command.upgrade, config, "20260930_agent_readonly_delivery")
        monkeypatch.setattr(tenant_migrator, "REVISION", LATEST)
        tenant = await tenant_migrator.resume_tenant(tenant.id)
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == LATEST
            assert (await conn.execute(sa.text(f'SELECT user_id FROM "{tenant.schema_name}".users'))).scalars().all() == users
            assert await compare_business_schema(conn, "public", tenant.schema_name, load_snapshot_manifest()) == []
        for target in ("tv002_agent_task_core", "tv001_business_snapshot"):
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
                await maintenance.run_downgrade(target)
                await maintenance.run_migration(LATEST)
                assert await maintenance.compare_schema("public", load_snapshot_manifest()) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["extra", "partial", "missing", "different", "unknown"])
async def test_tv002_partial_or_unknown_never_filtered_on_tenant_side(mig_db_url, monkeypatch, damage):
    from app.core.tenant_transaction import TenantUnavailable
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, "20260926_agent_task_core")
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    monkeypatch.setattr(tenant_migrator, "REVISION", "tv002_agent_task_core")
    request = TenantCreateRequest(name="Damaged ancestor", slug=f"damaged-{uuid.uuid4().hex[:10]}",
        admin_email="admin@example.test", admin_password="ReadonlyTest123")
    try:
        tenant = await tenant_migrator.provision_new(request)
        schema = tenant.schema_name
        statements = {"extra": f'CREATE TABLE "{schema}".unexpected (id int)',
            "partial": f'ALTER TABLE "{schema}".agent_runs ADD claim_key varchar(100)',
            "missing": f'ALTER TABLE "{schema}".agent_tasks DROP COLUMN request_key CASCADE',
            "different": f'ALTER TABLE "{schema}".agent_runs ALTER COLUMN plugin_version TYPE varchar(41)',
            "unknown": f'UPDATE "{schema}".tenant_schema_version SET version_num=\'unreviewed\''}
        async with engine.begin() as conn:
            await conn.execute(sa.text(statements[damage]))
        await asyncio.to_thread(command.upgrade, config, "20260930_agent_readonly_delivery")
        monkeypatch.setattr(tenant_migrator, "REVISION", LATEST)
        with pytest.raises(TenantUnavailable):
            await tenant_migrator.resume_tenant(tenant.id)
        async with engine.connect() as conn:
            assert not await conn.scalar(sa.text("SELECT to_regclass(:name)"), {"name": f"{schema}.agent_projection_receipts"})
    finally:
        await engine.dispose()
