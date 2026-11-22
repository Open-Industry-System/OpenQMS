"""PostgreSQL evidence for isolated R5 proposal metadata."""
import asyncio
import os
import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from tests.ci.database_template import fixture_database
from tests.migrations.agent_delta_support import assert_public_delta, assert_tenant_delta
from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

PUBLIC = '20261114_r5_d5_proposals'
PUBLIC_PARENT = '20261114_r4b_main_merge'
TENANT = 'tv010_r5_d5_proposals'
TENANT_PARENT = 'tv009_r4b_main_merge'
TABLES = {'capa_d5_proposals', 'capa_d5_proposal_sources', 'capa_d5_measures', 'capa_d5_withdrawals', 'agent_d5_commands', 'agent_d5_checkpoint_positions', 'capa_d5_staff_receipts'}


@pytest.mark.parametrize('ancestor', [None, PUBLIC_PARENT])
def test_public_recovery_tables_at_head(mig_db_url, ancestor):
    assert_public_delta(mig_db_url, predecessor=ancestor, revision=PUBLIC, tables=TABLES)


@pytest.mark.asyncio
@pytest.mark.parametrize('ancestor', [None, TENANT_PARENT])
async def test_tenant_recovery_tables_at_head(mig_db_url, monkeypatch, ancestor):
    await assert_tenant_delta(
        mig_db_url,
        monkeypatch,
        public_predecessor=PUBLIC_PARENT,
        public_revision=PUBLIC,
        tenant_predecessor=ancestor,
        tenant_revision=TENANT,
        tables=TABLES,
    )


def _seed_proposal(conn, schema="public"):
    conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}", public'))
    from tests.migrations.test_d4_text_delivery_delta import _seed_delivery_row
    from app.database import TenantBase
    proof = _seed_delivery_row(conn, 'capa_d4_root_cause_source_proofs', schema)
    ids = dict(command_id=uuid.uuid4(), proposal_id=uuid.uuid4(), task_id=proof['task_id'] if 'task_id' in proof else conn.scalar(sa.text('SELECT task_id FROM agent_tasks LIMIT 1')),
               run_id=conn.scalar(sa.text('SELECT run_id FROM agent_runs LIMIT 1')),
               report_id=proof['report_id'], revision_id=proof['revision_id'], proof_id=proof['proof_id'],
               created_by=proof['actor_id'])
    conn.execute(TenantBase.metadata.tables['agent_d5_commands'].insert().values(
        **{k: ids[k] for k in ('command_id','task_id','run_id','proposal_id')},
        operation='save', command_key='first', request_hmac='a'*64, sequence=1))
    conn.execute(TenantBase.metadata.tables['capa_d5_proposals'].insert().values(
        **{k:v for k,v in ids.items() if k != 'run_id'}, original_text='restricted original', state='pending'))
    return ids


@pytest.fixture(scope='module')
def migrated_proposal_constraints():
    """Migrate and seed once. Each constraint case rolls back its own transaction."""
    with fixture_database(os.environ) as database:
        # Alembic gives DATABASE_URL precedence over its explicit config URL.
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv('DATABASE_URL', database.async_url)
            command.upgrade(_migration_config(database.async_url), PUBLIC)
        engine = _sync_engine(database.async_url)
        try:
            with engine.begin() as conn:
                ids = _seed_proposal(conn)
            yield engine, ids
        finally:
            engine.dispose()


@pytest.mark.parametrize('violation', ['key', 'sequence', 'delete', 'null', 'state', 'hmac', 'missing_proof'])
def test_real_constraints_reject_invalid_writes(migrated_proposal_constraints, violation):
    engine, ids = migrated_proposal_constraints
    with engine.connect() as conn:
        with pytest.raises(IntegrityError), conn.begin_nested():
            if violation in {'key', 'sequence'}:
                command_row = dict(ids, new=uuid.uuid4(), key='first' if violation == 'key' else 'second',
                                   hmac='a'*64, seq=2 if violation == 'key' else 1)
                conn.execute(sa.text("""
                    INSERT INTO agent_d5_commands
                        (command_id, task_id, run_id, proposal_id, operation, command_key, request_hmac, sequence)
                    VALUES (:new, :task_id, :run_id, :proposal_id, 'save', :key, :hmac, :seq)
                """), command_row)
            elif violation == 'delete':
                conn.execute(sa.text('DELETE FROM agent_tasks WHERE task_id=:task_id'), ids)
            elif violation == 'null':
                conn.execute(sa.text('UPDATE capa_d5_proposals SET original_text=NULL'))
            elif violation == 'missing_proof':
                conn.execute(sa.text('UPDATE capa_d5_proposals SET proof_id=:missing'), {'missing': uuid.uuid4()})
            elif violation == 'state':
                conn.execute(sa.text("UPDATE capa_d5_proposals SET state='invalid'"))
            else:
                conn.execute(sa.text("UPDATE agent_d5_commands SET request_hmac='invalid'"))


def test_populated_downgrade_refused_atomically(mig_db_url):
    cfg = _migration_config(mig_db_url)
    command.upgrade(cfg, PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            _seed_proposal(conn)
        with pytest.raises(RuntimeError, match='R5 D5 evidence exists'):
            command.downgrade(cfg, PUBLIC_PARENT)
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT count(*) FROM capa_d5_proposals')) == 1
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == PUBLIC
    finally:
        engine.dispose()


def test_models_and_migrations_match_foreign_keys_and_uniques(mig_db_url):
    from app.database import TenantBase
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as conn:
            inspector = sa.inspect(conn)
            for name in TABLES:
                table = TenantBase.metadata.tables[name]
                actual = {c['name']: c for c in inspector.get_columns(name)}
                assert set(table.c.keys()) == set(actual)
                for column in table.c:
                    assert actual[column.name]['nullable'] == column.nullable
                    assert actual[column.name]['type'].compile(dialect=conn.dialect) == column.type.compile(dialect=conn.dialect)
                assert all(fk['options']['ondelete'] == 'RESTRICT' for fk in inspector.get_foreign_keys(name))
                assert {tuple(u.columns.keys()) for u in table.constraints if isinstance(u, sa.UniqueConstraint)} == {tuple(u['column_names']) for u in inspector.get_unique_constraints(name)}
    finally:
        engine.dispose()


def test_empty_downgrade_preserves_legacy_d5(mig_db_url):
    cfg = _migration_config(mig_db_url)
    command.upgrade(cfg, PUBLIC_PARENT)
    engine = _sync_engine(mig_db_url)
    try:
        from tests.migrations.test_agent_readonly_controls_delta import _seed_history
        with engine.begin() as conn:
            ids = _seed_history(conn)
            conn.execute(sa.text("UPDATE capa_eightd SET d5_correction='legacy unchanged' WHERE report_id=:capa"), ids)
        command.upgrade(cfg, PUBLIC)
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT count(*) FROM capa_d5_measures')) == 0
        command.downgrade(cfg, PUBLIC_PARENT)
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT d5_correction FROM capa_eightd WHERE report_id=:capa'),ids) == 'legacy unchanged'
            assert not TABLES & set(sa.inspect(conn).get_table_names())
    finally:
        engine.dispose()


def test_measure_source_and_staff_receipt_uniqueness(mig_db_url):
    from app.database import TenantBase
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_proposal(conn)
            values = {
                'capa_d5_proposal_sources': dict(source_id=uuid.uuid4(),proposal_id=ids['proposal_id'],projection_id='fmea.cause_node.masked.v1',factory_id=conn.scalar(sa.text('SELECT id FROM factories LIMIT 1')),product_line_code='DC-DC-100',fmea_id=uuid.uuid4(),node_id='cause',node_hmac='a'*64),
                'capa_d5_measures': dict(measure_id=uuid.uuid4(),proposal_id=ids['proposal_id'],final_text='final',adopted_by=ids['created_by']),
            }
            for name, row in values.items():
                table = TenantBase.metadata.tables[name]
                conn.execute(table.insert().values(**row))
                with pytest.raises(IntegrityError), conn.begin_nested():
                    conn.execute(table.insert().values(**dict(row, **{list(table.primary_key.columns)[0].name:uuid.uuid4()})))
            table=TenantBase.metadata.tables['capa_d5_staff_receipts']
            row=dict(receipt_id=uuid.uuid4(),actor_id=ids['created_by'],operation_key='adopt-one',operation='adopt',request_hmac='a'*64,proposal_id=ids['proposal_id'],measure_id=values['capa_d5_measures']['measure_id'])
            conn.execute(table.insert().values(**row))
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(table.insert().values(**dict(row,receipt_id=uuid.uuid4())))
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_tenant_empty_downgrade_and_populated_guard(mig_db_url, monkeypatch):
    monkeypatch.setattr(tenant_migrator, 'REVISION', TENANT)
    await asyncio.to_thread(command.upgrade, _migration_config(mig_db_url), PUBLIC)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name='R5 guard', slug='r5-' + uuid.uuid4().hex[:10],
            admin_email='r5@example.test', admin_password='D5TestPassword123'))
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as m:
            await m.run_downgrade(TENANT_PARENT)
            assert await m.schema_state() == 'r5_predecessor'
            await m.run_migration(TENANT)
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: _seed_proposal(c,tenant.schema_name))
        with pytest.raises(RuntimeError, match='R5 D5 evidence exists'):
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as m:
                await m.run_downgrade(TENANT_PARENT)
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT
            assert await conn.scalar(sa.text(f'SELECT count(*) FROM "{tenant.schema_name}".capa_d5_proposals')) == 1
    finally:
        await engine.dispose()


def test_public_and_tenant_deltas_identical_and_guard_all_evidence():
    import ast
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    trees=[ast.parse((root/path).read_text()) for path in (
        'alembic/versions/20261114_r5_d5_proposals.py',
        'alembic_tenant/versions/tv010_r5_d5_proposals.py')]
    for action in ('upgrade','downgrade'):
        bodies=[next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==action) for tree in trees]
        assert ast.dump(bodies[0]) == ast.dump(bodies[1])
    downgrade=next(n for n in trees[0].body if isinstance(n,ast.FunctionDef) and n.name=='downgrade')
    guards=[n for n in downgrade.body if isinstance(n,ast.If)]
    assert len(guards) == len(TABLES)
    assert {next(n.value for n in ast.walk(guard) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('SELECT')).split('FROM ')[1].split(')')[0] for guard in guards} == TABLES
    first_drop=min(n.lineno for n in ast.walk(downgrade) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr.startswith('drop_'))
    assert all(g.end_lineno < first_drop for g in guards)
