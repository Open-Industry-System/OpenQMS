"""Common assertions for fresh and predecessor upgrades of Agent deltas."""

import asyncio
import uuid

import sqlalchemy as sa
from alembic import command
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from tests.migrations.test_agent_task_core import _migration_config, _sync_engine


def assert_public_delta(mig_db_url, *, predecessor, revision, tables):
    config = _migration_config(mig_db_url)
    if predecessor:
        command.upgrade(config, predecessor)
    command.upgrade(config, revision)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as conn:
            assert tables <= set(sa.inspect(conn).get_table_names())
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == revision
    finally:
        engine.dispose()


async def assert_tenant_delta(
    mig_db_url, monkeypatch, *, public_predecessor, public_revision,
    tenant_predecessor, tenant_revision, tables,
):
    config = _migration_config(mig_db_url)
    start = public_predecessor if tenant_predecessor else public_revision
    await asyncio.to_thread(command.upgrade, config, start)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    monkeypatch.setattr(tenant_migrator, 'REVISION', tenant_predecessor or tenant_revision)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name='Agent delta',
            slug='agent-delta-' + uuid.uuid4().hex[:10],
            admin_email='agent-delta@example.test',
            admin_password='AgentDeltaTestPassword123',
        ))
        if tenant_predecessor:
            await asyncio.to_thread(command.upgrade, config, public_revision)
            monkeypatch.setattr(tenant_migrator, 'REVISION', tenant_revision)
            tenant = await tenant_migrator.resume_tenant(tenant.id)
        async with engine.connect() as conn:
            names = await conn.run_sync(
                lambda c: set(sa.inspect(c).get_table_names(schema=tenant.schema_name)),
            )
            assert tables <= names
            version = await conn.scalar(sa.text(
                f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version',
            ))
            assert version == tenant_revision
    finally:
        await engine.dispose()
