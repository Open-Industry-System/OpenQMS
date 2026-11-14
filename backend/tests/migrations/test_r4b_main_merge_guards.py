"""Tenant merge predecessor integrity and atomic downgrade guards."""
import asyncio
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.tenant_transaction import TenantUnavailable
from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from tests.migrations.test_agent_task_core import _migration_config
from tests.migrations.test_characteristic_refs import _seed_pre_upgrade_rows
from tests.migrations.test_d4_text_delivery_delta import _seed_delivery_row, TABLES as TEXT_TABLES
from tests.migrations.test_d4_recovery_delta import _seed_recovery, TABLES as RECOVERY_TABLES

PUBLIC = '20261114_production_merge'
TENANT = 'tv010_refresh_sessions'
CHAR = 'tv007_characteristic_refs'
RECOVERY = 'tv008_d4_recovery'
BASE = 'tv006_agent_read_tasks'
D4_TABLES = TEXT_TABLES | RECOVERY_TABLES
CHAR_COLUMNS = (
    ('control_plan_items', 'source_characteristic_ref'),
    ('special_characteristics', 'source_characteristic_id'),
)


def _request():
    return TenantCreateRequest(name='Merge guards', slug='merge-guard-' + uuid.uuid4().hex[:10],
        admin_email='merge-guard@example.test', admin_password='MigrationTest123!')


@pytest.mark.asyncio
@pytest.mark.parametrize('predecessor,public_parent,damage', [
    *((CHAR, '20261108_merge_characteristics', ('column', table, column)) for table, column in CHAR_COLUMNS),
    *((RECOVERY, '20261113_d4_recovery', ('table', table, 'unexpected_marker')) for table in sorted(D4_TABLES)),
    (CHAR, '20261108_merge_characteristics', ('extra', 'unknown_partial_table', None)),
    (RECOVERY, '20261113_d4_recovery', ('extra', 'unknown_partial_table', None)),
])
async def test_predecessor_damage_rejected_before_upgrade(mig_db_url, monkeypatch, predecessor, public_parent, damage):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, public_parent)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    monkeypatch.setattr(tenant_migrator, 'REVISION', predecessor)
    try:
        tenant = await tenant_migrator.provision_new(_request())
        await asyncio.to_thread(command.upgrade, config, PUBLIC)
        monkeypatch.setattr(tenant_migrator, 'REVISION', TENANT)
        schema = tenant.schema_name
        kind, table, column = damage
        async with engine.begin() as conn:
            if kind == 'column':
                await conn.execute(sa.text(f'ALTER TABLE "{schema}"."{table}" DROP COLUMN "{column}"'))
            elif kind == 'table':
                await conn.execute(sa.text(f'ALTER TABLE "{schema}"."{table}" ADD COLUMN "{column}" integer'))
            else:
                await conn.execute(sa.text(f'CREATE TABLE "{schema}"."{table}" (id integer)'))
        with pytest.raises(TenantUnavailable, match='partial or unknown tenant schema'):
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
                await tenant_migrator.migrate_if_needed(maintenance, maintenance.attempt)
        async with engine.connect() as conn:
            assert (await conn.execute(sa.text(f'SELECT version_num FROM "{schema}".tenant_schema_version'))).scalars().all() == [predecessor]
    finally:
        await engine.dispose()


def _snapshot(conn, schema, item, sc):
    tables = {name: conn.execute(sa.text(
        f'SELECT to_jsonb(t) FROM "{schema}"."{name}" t ORDER BY to_jsonb(t)::text'
    )).scalars().all() for name in D4_TABLES}
    values = conn.execute(sa.text(f'''SELECT c.source_characteristic_ref, s.source_characteristic_id
        FROM "{schema}".control_plan_items c CROSS JOIN "{schema}".special_characteristics s
        WHERE c.item_id=:item AND s.sc_id=:sc'''), {'item': item, 'sc': sc}).one()
    return tables, tuple(values)


@pytest.mark.asyncio
@pytest.mark.parametrize('evidence', sorted(TEXT_TABLES) + ['checkpoint-only', 'restart-with-checkpoint', 'binding-only'])
async def test_merged_downgrade_nonempty_d4_rolls_back_both_branches(mig_db_url, monkeypatch, evidence):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, PUBLIC)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    try:
        tenant = await tenant_migrator.provision_new(_request())
        schema = tenant.schema_name
        async with engine.begin() as conn:
            def seed(sync):
                if evidence in TEXT_TABLES:
                    _seed_delivery_row(sync, evidence, schema)
                else:
                    _seed_recovery(sync, schema, restart=evidence == 'restart-with-checkpoint',
                                   binding_only=evidence == 'binding-only')
                sync.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
                item, sc = _seed_pre_upgrade_rows(sync)
                sync.execute(sa.text('UPDATE control_plan_items SET source_characteristic_ref=CAST(:value AS jsonb) WHERE item_id=:id'),
                             {'value': '{"source":"preserved"}', 'id': item})
                sync.execute(sa.text('UPDATE special_characteristics SET source_characteristic_id=:value WHERE sc_id=:id'),
                             {'value': sc, 'id': sc})
                return item, sc, _snapshot(sync, schema, item, sc)
            item, sc, before = await conn.run_sync(seed)
        with pytest.raises(RuntimeError, match='D4 (delivery|recovery) evidence exists'):
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
                await maintenance.run_downgrade(BASE)
        async with engine.connect() as conn:
            assert (await conn.execute(sa.text(f'SELECT version_num FROM "{schema}".tenant_schema_version'))).scalars().all() == [TENANT]
            assert await conn.run_sync(lambda sync: _snapshot(sync, schema, item, sc)) == before
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.compare_schema('public', tenant_migrator.load_snapshot_manifest()) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('target', [CHAR, RECOVERY, 'tv007_d4_text_delivery'])
async def test_merged_downgrade_to_one_branch_rejected_before_ddl(mig_db_url, monkeypatch, target):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, PUBLIC)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    try:
        tenant = await tenant_migrator.provision_new(_request())
        schema = tenant.schema_name
        async with engine.begin() as conn:
            def seed(sync):
                _seed_recovery(sync, schema, restart=True)
                sync.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
                item, sc = _seed_pre_upgrade_rows(sync)
                sync.execute(sa.text('UPDATE control_plan_items SET source_characteristic_ref=CAST(:value AS jsonb) WHERE item_id=:id'),
                    {'value': '{"source":"preserved"}', 'id': item})
                sync.execute(sa.text('UPDATE special_characteristics SET source_characteristic_id=:value WHERE sc_id=:id'),
                    {'value': sc, 'id': sc})
                return item, sc, _snapshot(sync, schema, item, sc)
            item, sc, before = await conn.run_sync(seed)
        with pytest.raises(ValueError, match='single reviewed tenant revision'):
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
                await maintenance.run_downgrade(target)
        async with engine.connect() as conn:
            assert (await conn.execute(sa.text(f'SELECT version_num FROM "{schema}".tenant_schema_version'))).scalars().all() == [TENANT]
            assert await conn.run_sync(lambda sync: _snapshot(sync, schema, item, sc)) == before
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.compare_schema('public', tenant_migrator.load_snapshot_manifest()) == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('predecessor,public_parent', [
    (CHAR, '20261108_merge_characteristics'),
    (RECOVERY, '20261113_d4_recovery'),
])
async def test_branch_values_survive_merge_and_rejected_branch_downgrade(mig_db_url, monkeypatch, predecessor, public_parent):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, public_parent)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    monkeypatch.setattr(tenant_migrator, 'REVISION', predecessor)
    try:
        tenant = await tenant_migrator.provision_new(_request())
        schema = tenant.schema_name
        async with engine.begin() as conn:
            def seed(sync):
                if predecessor == RECOVERY:
                    ids = _seed_recovery(sync, schema, restart=True)
                    return ids['checkpoint']
                sync.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
                item, sc = _seed_pre_upgrade_rows(sync)
                sync.execute(sa.text('UPDATE control_plan_items SET source_characteristic_ref=CAST(:value AS jsonb) WHERE item_id=:id'),
                    {'value': '{"source":"branch"}', 'id': item})
                sync.execute(sa.text('UPDATE special_characteristics SET source_characteristic_id=:value WHERE sc_id=:id'),
                    {'value': sc, 'id': sc})
                return item, sc
            identifiers = await conn.run_sync(seed)
        await asyncio.to_thread(command.upgrade, config, PUBLIC)
        monkeypatch.setattr(tenant_migrator, 'REVISION', TENANT)
        await tenant_migrator.resume_tenant(tenant.id)

        async def assert_values(conn):
            if predecessor == RECOVERY:
                for table in ('agent_d4_recovery_checkpoints', 'agent_d4_recovery_restarts'):
                    assert await conn.scalar(sa.text(f'SELECT checkpoint_id FROM "{schema}"."{table}" WHERE checkpoint_id=:id'),
                                             {'id': identifiers}) == identifiers
            else:
                item, sc = identifiers
                assert await conn.scalar(sa.text(f'SELECT source_characteristic_ref FROM "{schema}".control_plan_items WHERE item_id=:id'),
                                         {'id': item}) == {'source': 'branch'}
                assert await conn.scalar(sa.text(f'SELECT source_characteristic_id FROM "{schema}".special_characteristics WHERE sc_id=:id'),
                                         {'id': sc}) == sc
            assert (await conn.execute(sa.text(f'SELECT version_num FROM "{schema}".tenant_schema_version'))).scalars().all() == [TENANT]

        async with engine.connect() as conn:
            await assert_values(conn)
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.compare_schema('public', tenant_migrator.load_snapshot_manifest()) == []
        with pytest.raises(ValueError, match='single reviewed tenant revision'):
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
                await maintenance.run_downgrade(predecessor)
        async with engine.connect() as conn:
            await assert_values(conn)
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.compare_schema('public', tenant_migrator.load_snapshot_manifest()) == []
    finally:
        await engine.dispose()
