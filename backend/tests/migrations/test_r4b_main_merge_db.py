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

PUBLIC_HEAD = '20261114_production_merge'
TENANT_HEAD = 'tv010_refresh_sessions'


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


@pytest.mark.parametrize("source", ["20260913_user_refresh_sessions", "20261114_r4b_main_merge"])
def test_production_merge_preserves_both_deployed_histories(mig_db_url, source):
    config = _migration_config(mig_db_url)
    command.upgrade(config, source)
    engine = _sync_engine(mig_db_url)
    user_id, role_id, session_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO role_definitions (id,role_key,name_zh,name_en) VALUES (:id,:key,'合并验证','Merge validation')"),
                         {"id": role_id, "key": uuid.uuid4().hex[:25]})
            conn.execute(sa.text("INSERT INTO users (user_id,username,password_hash,role_id,legacy_role,is_active) VALUES (:id,:name,'preserved-password-hash',:role,'viewer',true)"),
                         {"id": user_id, "name": uuid.uuid4().hex, "role": role_id})
            if source == "20260913_user_refresh_sessions":
                conn.execute(sa.text("INSERT INTO user_refresh_sessions (session_id,user_id,token_hash,expires_at) VALUES (:id,:user,:hash,now() + interval '1 day')"),
                             {"id": session_id, "user": user_id, "hash": "a" * 64})
                old_session = conn.scalar(sa.text("SELECT to_jsonb(s) FROM user_refresh_sessions s WHERE session_id=:id"), {"id": session_id})
            old_user = conn.scalar(sa.text("SELECT to_jsonb(u) FROM users u WHERE user_id=:id"), {"id": user_id})
        command.upgrade(config, PUBLIC_HEAD)
        command.upgrade(config, PUBLIC_HEAD)
        with engine.connect() as conn:
            assert conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == PUBLIC_HEAD
            assert conn.scalar(sa.text("SELECT to_jsonb(u) FROM users u WHERE user_id=:id"), {"id": user_id}) == old_user
            if source == "20260913_user_refresh_sessions":
                assert conn.scalar(sa.text("SELECT to_jsonb(s) FROM user_refresh_sessions s WHERE session_id=:id"), {"id": session_id}) == old_session
            assert {"user_refresh_sessions", "agent_read_tasks", "agent_task_attachments", "agent_d4_recovery_checkpoints"} <= set(sa.inspect(conn).get_table_names())
    finally:
        engine.dispose()
