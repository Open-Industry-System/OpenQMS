"""R5 actual-delivery basis is additive, tenant-parallel and never discarded."""
import asyncio
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

PUBLIC = '20261114_r5_d5_basis'
TENANT = 'tv011_r5_d5_basis'


@pytest.mark.parametrize('ancestor', [None, '20261114_r5_d5_proposals'])
def test_basis_receipts_upgrade(mig_db_url, ancestor):
    config = _migration_config(mig_db_url)
    if ancestor:
        command.upgrade(config, ancestor)
    command.upgrade(config, PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as conn:
            assert 'agent_d5_basis_receipts' in sa.inspect(conn).get_table_names()
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == PUBLIC
    finally:
        engine.dispose()


def test_nonempty_basis_downgrade_atomic_refusal(mig_db_url):
    from tests.migrations.test_r5_d5_delta import _seed_proposal
    from app.database import TenantBase
    config = _migration_config(mig_db_url)
    command.upgrade(config, PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_proposal(conn)
            conn.execute(TenantBase.metadata.tables['agent_d5_basis_receipts'].insert().values(
                receipt_id=uuid.uuid4(), task_id=ids['task_id'], run_id=ids['run_id'],
                report_id=ids['report_id'], revision_id=ids['revision_id'], proof_id=ids['proof_id'],
                lease_epoch=0, tenant_generation=1, sources=[{'synthetic': True}], basis_hmac='a'*64))
        with pytest.raises(Exception, match='nonempty'):
            command.downgrade(config, '20261114_r5_d5_proposals')
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT count(*) FROM agent_d5_basis_receipts')) == 1
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == PUBLIC
    finally:
        engine.dispose()


def test_public_tenant_basis_delta_identical():
    import ast
    from pathlib import Path
    base = Path(__file__).resolve().parents[2]
    trees = [ast.parse((base/path).read_text()) for path in (
        'alembic/versions/20261114_r5_d5_basis.py', 'alembic_tenant/versions/tv011_r5_d5_basis.py')]
    def functions(tree):
        return [ast.dump(node) for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert functions(trees[0]) == functions(trees[1])


@pytest.mark.asyncio
@pytest.mark.parametrize('ancestor', [False, True])
async def test_tenant_basis_upgrade_and_empty_downgrade(mig_db_url, monkeypatch, ancestor):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.services import tenant_migrator
    from app.schemas.platform import TenantCreateRequest
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, '20261114_r5_d5_proposals' if ancestor else PUBLIC)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    monkeypatch.setattr(tenant_migrator, 'REVISION', 'tv010_r5_d5_proposals' if ancestor else TENANT)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(name='Basis migration',
            slug='basis-'+uuid.uuid4().hex[:12], admin_email='basis@example.test', admin_password='SyntheticTestPassword123'))
        if ancestor:
            await asyncio.to_thread(command.upgrade, config, PUBLIC)
            monkeypatch.setattr(tenant_migrator, 'REVISION', TENANT)
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as m:
                assert await m.schema_state() == 'r5_basis_predecessor'
            tenant = await tenant_migrator.resume_tenant(tenant.id)
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as m:
            await m.run_downgrade('tv010_r5_d5_proposals')
            assert await m.schema_state() == 'r5_basis_predecessor'
            await m.run_migration(TENANT)
        from tests.migrations.test_r5_d5_delta import _seed_proposal
        from app.database import TenantBase
        def seed(conn):
            ids = _seed_proposal(conn, tenant.schema_name)
            conn.execute(TenantBase.metadata.tables['agent_d5_basis_receipts'].insert().values(
                receipt_id=uuid.uuid4(), task_id=ids['task_id'], run_id=ids['run_id'], report_id=ids['report_id'],
                revision_id=ids['revision_id'], proof_id=ids['proof_id'], lease_epoch=0, tenant_generation=1,
                sources=[{'synthetic': True}], basis_hmac='a'*64))
        async with engine.begin() as conn:
            await conn.run_sync(seed)
        with pytest.raises(Exception, match='nonempty'):
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as m:
                await m.run_downgrade('tv010_r5_d5_proposals')
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT
            assert await conn.scalar(sa.text(f'SELECT count(*) FROM "{tenant.schema_name}".agent_d5_basis_receipts')) == 1
    finally:
        await engine.dispose()


def test_basis_model_migration_types_foreign_keys_and_constraints(mig_db_url):
    from app.database import TenantBase
    from sqlalchemy.exc import IntegrityError
    from tests.migrations.test_r5_d5_delta import _seed_proposal
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            inspector = sa.inspect(conn)
            for name in ('agent_d5_basis_receipts', 'agent_d5_command_basis'):
                table = TenantBase.metadata.tables[name]
                actual = {column['name']: column for column in inspector.get_columns(name)}
                assert set(actual) == set(table.c.keys())
                for column in table.c:
                    assert actual[column.name]['nullable'] == column.nullable
                    assert actual[column.name]['type'].compile(dialect=conn.dialect) == column.type.compile(dialect=conn.dialect)
                assert all(fk['options']['ondelete'] == 'RESTRICT' for fk in inspector.get_foreign_keys(name))
            ids = _seed_proposal(conn)
            receipt = dict(receipt_id=uuid.uuid4(), task_id=ids['task_id'], run_id=ids['run_id'], report_id=ids['report_id'],
                revision_id=ids['revision_id'], proof_id=ids['proof_id'], lease_epoch=0, tenant_generation=1,
                sources=[{'synthetic': True}], basis_hmac='a'*64)
            table = TenantBase.metadata.tables['agent_d5_basis_receipts']
            for change in ({'sources': []}, {'sources': {}}, {'lease_epoch': -1}, {'tenant_generation': -1},
                           {'basis_hmac': 'wrong'}, {'proof_id': uuid.uuid4()}, {'task_id': None}):
                with pytest.raises(IntegrityError), conn.begin_nested():
                    conn.execute(table.insert().values(**(receipt | change)))
            conn.execute(table.insert().values(**receipt))
            links = TenantBase.metadata.tables['agent_d5_command_basis']
            conn.execute(links.insert().values(command_id=ids['command_id'], receipt_id=receipt['receipt_id']))
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(links.insert().values(command_id=ids['command_id'], receipt_id=receipt['receipt_id']))
    finally:
        engine.dispose()
