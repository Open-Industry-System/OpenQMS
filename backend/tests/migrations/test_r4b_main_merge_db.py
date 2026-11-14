"""PostgreSQL integration coverage for independently published branch heads."""
import asyncio
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from app.services.tenant_schema_diff import load_snapshot_manifest
from tests.migrations.test_agent_task_core import _migration_config, _sync_engine
from tests.migrations.test_characteristic_refs import _seed_pre_upgrade_rows
from tests.migrations.test_d4_recovery_delta import _seed_recovery

PUBLIC_HEAD = '20261114_r4b_main_merge'
TENANT_HEAD = 'tv009_r4b_main_merge'


@pytest.mark.parametrize('source', [None, '20261108_merge_characteristics', '20261113_d4_recovery'])
def test_public_merge_keeps_branch_values_and_is_repeatable(mig_db_url, source):
    config = _migration_config(mig_db_url)
    engine = _sync_engine(mig_db_url)
    try:
        if source:
            command.upgrade(config, source)
        if source == '20261108_merge_characteristics':
            with engine.begin() as conn:
                item, sc = _seed_pre_upgrade_rows(conn)
                conn.execute(sa.text("UPDATE control_plan_items SET source_characteristic_ref=CAST(:ref AS jsonb) WHERE item_id=:id"), {'id': item, 'ref': '{"node":"kept"}'})
                conn.execute(sa.text('UPDATE special_characteristics SET source_characteristic_id=:ref WHERE sc_id=:id'), {'id': sc, 'ref': sc})
        elif source:
            with engine.begin() as conn:
                ids = _seed_recovery(conn, restart=True)
        command.upgrade(config, PUBLIC_HEAD)
        command.upgrade(config, PUBLIC_HEAD)
        with engine.connect() as conn:
            assert conn.execute(sa.text('SELECT version_num FROM alembic_version')).scalars().all() == [PUBLIC_HEAD]
            assert 'agent_d4_recovery_checkpoints' in sa.inspect(conn).get_table_names()
            if source == '20261108_merge_characteristics':
                assert conn.scalar(sa.text('SELECT source_characteristic_ref FROM control_plan_items WHERE item_id=:id'), {'id': item}) == {'node': 'kept'}
                assert conn.scalar(sa.text('SELECT source_characteristic_id FROM special_characteristics WHERE sc_id=:id'), {'id': sc}) == sc
            elif source:
                assert conn.scalar(sa.text('SELECT checkpoint_id FROM agent_d4_recovery_checkpoints WHERE checkpoint_id=:id'), {'id': ids['checkpoint']}) == ids['checkpoint']
                assert conn.scalar(sa.text('SELECT checkpoint_id FROM agent_d4_recovery_restarts WHERE checkpoint_id=:id'), {'id': ids['checkpoint']}) == ids['checkpoint']
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_empty_tenant_created_at_merged_revision_has_full_parity(mig_db_url, monkeypatch):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, PUBLIC_HEAD)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name='Merged migration', slug='merged-' + uuid.uuid4().hex[:12],
            admin_email='merge@example.test', admin_password='MigrationTest123!',
        ))
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.schema_state() == 'current'
            assert await maintenance.compare_schema('public', load_snapshot_manifest()) == []
            await maintenance.run_migration(TENANT_HEAD)
            assert await maintenance.compare_schema('public', load_snapshot_manifest()) == []
    finally:
        await engine.dispose()
