"""PostgreSQL evidence for isolated D4 recovery metadata."""
import asyncio
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

PUBLIC = '20261113_d4_recovery'
PUBLIC_PARENT = '20261109_d4_text_delivery'
TENANT = 'tv008_d4_recovery'
TENANT_PARENT = 'tv007_d4_text_delivery'
TABLES = {'agent_d4_recovery_checkpoints', 'agent_d4_recovery_restarts', 'agent_d4_task_parent_grants'}


@pytest.mark.parametrize('ancestor', [None, PUBLIC_PARENT])
def test_public_recovery_tables_at_head(mig_db_url, ancestor):
    config = _migration_config(mig_db_url)
    if ancestor:
        command.upgrade(config, ancestor)
    command.upgrade(config, PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as conn:
            assert TABLES <= set(sa.inspect(conn).get_table_names())
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == PUBLIC
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('ancestor', [None, TENANT_PARENT])
async def test_tenant_recovery_tables_at_head(mig_db_url, monkeypatch, ancestor):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, PUBLIC_PARENT if ancestor else PUBLIC)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    monkeypatch.setattr(tenant_migrator, 'REVISION', ancestor or TENANT)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name='Recovery delta', slug='recovery-' + uuid.uuid4().hex[:10],
            admin_email='recovery@example.test', admin_password='D4TestPassword123',
        ))
        if ancestor:
            await asyncio.to_thread(command.upgrade, config, PUBLIC)
            monkeypatch.setattr(tenant_migrator, 'REVISION', TENANT)
            tenant = await tenant_migrator.resume_tenant(tenant.id)
        async with engine.connect() as conn:
            names = await conn.run_sync(lambda c: set(sa.inspect(c).get_table_names(schema=tenant.schema_name)))
            assert TABLES <= names
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT
    finally:
        await engine.dispose()


def _seed_recovery(conn, schema='public', *, restart=False, binding_only=False):
    from tests.migrations.test_agent_readonly_controls_delta import _seed_history
    ids = _seed_history(conn, schema)
    ids.update(grant=uuid.uuid4(), checkpoint=uuid.uuid4(), control=uuid.uuid4(), new_run=uuid.uuid4())
    conn.execute(sa.text("""INSERT INTO agent_task_grants
        (grant_id,task_id,capability_id,factory_ids,access_kind)
        VALUES (:grant,:task,'capa.d4.root_cause_candidate.masked.v1',:factories,'read')"""),
        {**ids, 'factories': '["' + str(ids['factory']) + '"]'})
    if binding_only:
        ids['parent'] = uuid.uuid4()
        conn.execute(sa.text("""INSERT INTO agent_plugin_grants
            (grant_id,installation_id,capability_id,factory_ids,granted_by,enabled)
            VALUES (:parent,:plugin,'capa.d4.root_cause_candidate.masked.v1',:factories,:user,true)"""),
            {**ids, 'factories': '["' + str(ids['factory']) + '"]'})
        conn.execute(sa.text("INSERT INTO agent_d4_task_parent_grants (task_grant_id,plugin_grant_id) VALUES (:grant,:parent)"), ids)
        return ids
    conn.execute(sa.text("""INSERT INTO agent_d4_recovery_checkpoints
        (checkpoint_id,task_id,run_id,task_grant_id,tenant_generation,lease_epoch,
         accepted_message_seq,update_sequence,protocol,resume_position,created_by)
        VALUES (:checkpoint,:task,:run,:grant,1,7,1,1,'d4-recovery.v1','restart_from_start',:user)"""), ids)
    if restart:
        conn.execute(sa.text("UPDATE agent_runs SET status='stopped' WHERE run_id=:run"), ids)
        conn.execute(sa.text("""INSERT INTO agent_runs (run_id,task_id,installation_id,plugin_version,status)
            VALUES (:new_run,:task,:plugin,'1.0','pending')"""), ids)
        conn.execute(sa.text("""INSERT INTO agent_task_controls
            (control_id,task_id,run_id,key,action,expected_epoch,resulting_run_id)
            VALUES (:control,:task,:run,'recovery','restart',7,:new_run)"""), ids)
        conn.execute(sa.text("""INSERT INTO agent_d4_recovery_restarts
            (control_id,checkpoint_id,task_id,old_run_id,new_run_id,start_message_id)
            VALUES (:control,:checkpoint,:task,:run,:new_run,:message)"""), ids)
    return ids


@pytest.mark.parametrize('restart,binding_only', [(False, False), (True, False), (False, True)], ids=['checkpoint-only', 'restart-with-checkpoint', 'binding-only'])
def test_public_empty_downgrade_and_populated_guard(mig_db_url, restart, binding_only):
    config = _migration_config(mig_db_url)
    command.upgrade(config, PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        command.downgrade(config, PUBLIC_PARENT)
        with engine.connect() as conn:
            assert not TABLES & set(sa.inspect(conn).get_table_names())
        command.upgrade(config, PUBLIC)
        with engine.begin() as conn:
            _seed_recovery(conn, restart=restart, binding_only=binding_only)
            before = {name: conn.scalar(sa.text(f'SELECT count(*) FROM {name}')) for name in TABLES}
        with pytest.raises(RuntimeError, match='D4 recovery evidence exists'):
            command.downgrade(config, PUBLIC_PARENT)
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == PUBLIC
            assert {name: conn.scalar(sa.text(f'SELECT count(*) FROM {name}')) for name in TABLES} == before
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('restart,binding_only', [(False, False), (True, False), (False, True)], ids=['checkpoint-only', 'restart-with-checkpoint', 'binding-only'])
async def test_tenant_empty_downgrade_and_populated_guard(mig_db_url, monkeypatch, restart, binding_only):
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, PUBLIC)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    monkeypatch.setattr(tenant_migrator, 'REVISION', TENANT)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name='Recovery guard', slug='recovery-' + uuid.uuid4().hex[:10],
            admin_email='recovery@example.test', admin_password='D4TestPassword123'))
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as m:
            await m.run_downgrade(TENANT_PARENT)
            assert await m.schema_state() == 'recovery_predecessor'
            await m.run_migration(TENANT)
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: _seed_recovery(c, tenant.schema_name, restart=restart, binding_only=binding_only))
        with pytest.raises(RuntimeError, match='D4 recovery evidence exists'):
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as m:
                await m.run_downgrade(TENANT_PARENT)
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT
            assert await conn.scalar(sa.text(f'SELECT count(*) FROM "{tenant.schema_name}".agent_d4_recovery_checkpoints')) == int(not binding_only)
            assert await conn.scalar(sa.text(f'SELECT count(*) FROM "{tenant.schema_name}".agent_d4_recovery_restarts')) == int(restart)
            assert await conn.scalar(sa.text(f'SELECT count(*) FROM "{tenant.schema_name}".agent_d4_task_parent_grants')) == int(binding_only)
    finally:
        await engine.dispose()


def test_recovery_postgres_matches_named_model_constraints(mig_db_url):
    from app.database import TenantBase, PlatformBase
    import app.models
    config = _migration_config(mig_db_url)
    command.upgrade(config, 'head')
    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as conn:
            inspector = sa.inspect(conn)
            assert not TABLES & set(PlatformBase.metadata.tables)
            for name in TABLES:
                model = TenantBase.metadata.tables[name]
                actual = {c['name']: c for c in inspector.get_columns(name)}
                assert set(actual) == set(model.c.keys())
                for column in model.c:
                    assert actual[column.name]['nullable'] == column.nullable
                    assert actual[column.name]['type'].compile(dialect=conn.dialect) == column.type.compile(dialect=conn.dialect)
                assert inspector.get_pk_constraint(name)['name'] == model.primary_key.name
                assert {x['name'] for x in inspector.get_unique_constraints(name)} == {x.name for x in model.constraints if isinstance(x, sa.UniqueConstraint)}
                assert {x['name'] for x in inspector.get_check_constraints(name)} == {x.name for x in model.constraints if isinstance(x, sa.CheckConstraint)}
                assert {x['name'] for x in inspector.get_foreign_keys(name)} == {x.name for x in model.foreign_key_constraints}
                assert all(x['options'].get('ondelete') == 'RESTRICT' for x in inspector.get_foreign_keys(name))
    finally:
        engine.dispose()


def test_public_and_tenant_recovery_migration_bodies_identical():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    paths = [root / 'alembic/versions/20261113_d4_recovery.py', root / 'alembic_tenant/versions/tv008_d4_recovery.py']
    trees = [ast.parse(path.read_text()) for path in paths]
    for name in ('upgrade', 'downgrade'):
        nodes = [next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name) for tree in trees]
        assert ast.dump(nodes[0]) == ast.dump(nodes[1])
    for tree in trees:
        downgrade = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'downgrade')
        guards = [n for n in downgrade.body if isinstance(n, ast.If)]
        assert len(guards) == 3
        assert all(g.end_lineno < min(n.lineno for n in ast.walk(downgrade) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'drop_table') for g in guards)


def test_frozen_tenant_revisions_and_snapshot_match_t3_signoff():
    """Frozen SHA-256 values from T3 signoff, including shallow checkouts."""
    import hashlib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    expected = {
        'alembic_tenant/versions/tv001_business_snapshot.py': 'a6450f9db5ed8a60e781932a3141fa9a0fb098ac0d7e46aac08a9e815d40df86',
        'alembic_tenant/versions/tv002_agent_task_core.py': 'fea1e2a6c2a417beee4b30eae7c82c3fd4aba893f10e3134e3fde9f07aec4192',
        'alembic_tenant/versions/tv003_agent_readonly_delivery.py': '60dd0e4aa4902420ae533313e3ffef64acbc8d8b3b657f0e46f8569703cb5f42',
        'alembic_tenant/versions/tv004_agent_readonly_controls.py': 'e7572324e47bdc209e43cdbb9d5b22ebaa269a655cd5fdcc8216d45453736086',
        'alembic_tenant/versions/tv005_agent_task_attachments.py': 'f93116fa552b29ed2d6154c3d847ade679e57ee58853a399e1b8288c043ae9c6',
        'alembic_tenant/versions/tv006_agent_read_tasks.py': '4336ad07244aeb314e4784060c7e28f78ef63a7e2564e91d9756587865841d8f',
        'alembic_tenant/versions/tv007_d4_text_delivery.py': '8b1d975d615496d01aee79b32418584b51780ec2d79ddc88127c9a68e6e757de',
        'alembic_tenant/snapshot/business_20260927.py': 'adc4cdf379bc23994245f5c57aa118fce8a8323437a529d63d8a04c088658dbb',
        'alembic_tenant/snapshot/manifest.json': '6bafeb41f15069a422b7d8e1f366e74bede9c4558959a2b799c5b01745bc296f',
    }
    paths = {root / name for name in expected if name.startswith('alembic_tenant/versions/')}
    paths.update((root / 'alembic_tenant/snapshot').glob('*.py'))
    paths.update((root / 'alembic_tenant/snapshot').glob('*.json'))
    assert {str(path.relative_to(root)) for path in paths} == set(expected)
    # tv006 preserves main's published bytes; R4b changed only its docstring.
    # The R4b historical SHA-256 was 7992fc048151ae638e671f49a5f4e358c003061adfb2badbb8f051f3bf43217a.
    for path in paths:
        relative = str(path.relative_to(root))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected[relative], relative


@pytest.mark.asyncio
async def test_tv007_predecessor_filters_recovery_only_from_public(monkeypatch):
    from unittest.mock import AsyncMock
    from app.services import tenant_schema_diff
    old = {('table', 'agent_task_source_requests'): 'old'}
    added = {('table', name): 'new' for name in TABLES}
    reader = AsyncMock(side_effect=[old | added, old])
    monkeypatch.setattr(tenant_schema_diff, '_objects', reader)
    manifest = tenant_schema_diff.load_snapshot_manifest()
    assert await tenant_schema_diff.compare_business_schema(None, 'public', 'tenant_recovery', manifest, predecessor=TENANT_PARENT) == []
    reader.side_effect = [old | added, old | added]
    assert len(await tenant_schema_diff.compare_business_schema(None, 'public', 'tenant_recovery', manifest, predecessor=TENANT_PARENT)) == len(TABLES)


def test_recovery_constraints_reject_invalid_and_duplicate_rows(mig_db_url):
    from sqlalchemy.exc import IntegrityError
    from app.database import TenantBase
    import app.models
    config = _migration_config(mig_db_url)
    command.upgrade(config, 'head')
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_recovery(conn, restart=True)
            checkpoint = TenantBase.metadata.tables['agent_d4_recovery_checkpoints']
            restart = TenantBase.metadata.tables['agent_d4_recovery_restarts']
            def rejected(statement):
                nested = conn.begin_nested()
                with pytest.raises(IntegrityError):
                    conn.execute(statement)
                nested.rollback()
            for change in ({'tenant_generation': -1}, {'lease_epoch': -1},
                           {'accepted_message_seq': -1}, {'update_sequence': 0},
                           {'protocol': 'other'}, {'resume_position': 'other'}):
                rejected(checkpoint.update().where(checkpoint.c.checkpoint_id == ids['checkpoint']).values(**change))
            row = conn.execute(sa.select(checkpoint).where(checkpoint.c.checkpoint_id == ids['checkpoint'])).mappings().one()
            rejected(checkpoint.insert().values(**{**row, 'checkpoint_id': uuid.uuid4()}))
            row = conn.execute(sa.select(restart)).mappings().one()
            control2 = uuid.uuid4()
            conn.execute(sa.text("""INSERT INTO agent_task_controls
                (control_id,task_id,run_id,key,action,expected_epoch,resulting_run_id)
                VALUES (:control,:task,:run,'recovery-2','restart',7,:new_run)"""), {**ids, 'control': control2})
            rejected(restart.insert().values(**{**row, 'control_id': control2}))
    finally:
        engine.dispose()
