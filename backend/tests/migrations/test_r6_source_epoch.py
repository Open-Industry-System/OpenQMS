"""R6 source capture epochs are additive, monotonic, and never backfilled."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations.test_agent_task_core import _migration_config, _sync_engine
from tests.migrations.test_r6_entry_contracts import _seed_r6

PUBLIC = '20261116_r6_source_epoch'
PARENT = '20261115_r6_entry_contracts'
TENANT = 'tv016_r6_source_epoch'
TENANT_PARENT = 'tv015_r6_entry_contracts'


def test_source_epoch_pair_preserves_published_parents():
    root = Path(__file__).resolve().parents[2]
    for directory, revision in [('alembic', PUBLIC), ('alembic_tenant', TENANT)]:
        assert (root / directory / 'versions' / f'{revision}.py').exists(), 'R6 capture epoch migration missing'
        cfg = Config()
        cfg.set_main_option('script_location', str(root / directory))
        expected = '20261116_r6_verify_origins' if directory == 'alembic' else 'tv019_r6_verify_origins'
        assert ScriptDirectory.from_config(cfg).get_heads() == [expected]
    public = (root / 'alembic/versions' / f'{PUBLIC}.py').read_text()
    tenant = (root / 'alembic_tenant/versions' / f'{TENANT}.py').read_text()
    assert public.replace(PUBLIC, TENANT).replace(PARENT, TENANT_PARENT) == tenant


def test_source_epoch_upgrade_preserves_nonempty_old_r6_and_refuses_downgrade(mig_db_url):
    root = Path(__file__).resolve().parents[2]
    assert (root / 'alembic/versions' / f'{PUBLIC}.py').exists(), 'R6 capture epoch migration missing'
    config = _migration_config(mig_db_url)
    command.upgrade(config, PARENT)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids = _seed_r6(db)
            before = db.scalar(sa.text('SELECT to_jsonb(s) FROM capa_r6_source_origins s WHERE source_id=:source_id'), ids)
        command.upgrade(config, PUBLIC)
        command.upgrade(config, PUBLIC)
        with engine.connect() as db:
            after = db.scalar(sa.text('SELECT to_jsonb(s) FROM capa_r6_source_origins s WHERE source_id=:source_id'), ids)
            assert after.pop('source_version_counter') is None
            assert after == before
        with pytest.raises(Exception, match='R6 source evidence exists'):
            command.downgrade(config, PARENT)
        with engine.connect() as db:
            assert db.scalar(sa.text('SELECT version_num FROM alembic_version')) == PUBLIC
    finally:
        engine.dispose()


def test_every_graph_writer_advances_epoch_and_decrement_is_rejected(mig_db_url):
    root = Path(__file__).resolve().parents[2]
    assert (root / 'alembic/versions' / f'{PUBLIC}.py').exists(), 'R6 capture epoch migration missing'
    from sqlalchemy.exc import DBAPIError
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids = _seed_r6(db)
            from uuid import uuid4
            fmea_id = uuid4()
            db.execute(sa.text("""INSERT INTO fmea_documents
                (fmea_id,document_no,title,factory_id,product_line_code,graph_data,lock_version,fmea_type,status,version)
                VALUES (:id,'R6-EPOCH','Epoch',:factory_id,'DC-DC-100','{}',0,'PFMEA','draft',1)"""),
                {'id': fmea_id, 'factory_id': ids['factory_id']})
            old = db.scalar(sa.text('SELECT lock_version FROM fmea_documents WHERE fmea_id=:id'), {'id': fmea_id})
            original = db.scalar(sa.text('SELECT graph_data FROM fmea_documents WHERE fmea_id=:id'), {'id': fmea_id})
            import json
            for body in ({'nodes': [], 'edges': [], 'changed': True}, original):
                db.execute(sa.text('UPDATE fmea_documents SET graph_data=CAST(:body AS jsonb) WHERE fmea_id=:id'),
                    {'id': fmea_id, 'body': json.dumps(body)})
            assert db.scalar(sa.text('SELECT lock_version FROM fmea_documents WHERE fmea_id=:id'), {'id': fmea_id}) == old + 2
            with pytest.raises(DBAPIError), db.begin_nested():
                db.execute(sa.text('UPDATE fmea_documents SET lock_version=0 WHERE fmea_id=:id'), {'id': fmea_id})
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_nonempty_old_r6_tenant_upgrades_with_null_epochs_and_exact_parity(mig_db_url):
    import asyncio
    from uuid import uuid4
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.tenant_transaction import stable_tenant_lock_key
    from app.services.tenant_migrator import MaintenanceAttempt, maintenance_connection
    from app.services.tenant_schema_diff import load_snapshot_manifest
    await asyncio.to_thread(command.upgrade, _migration_config(mig_db_url), PUBLIC)
    schema = 'tenant_epoch_' + uuid4().hex[:12]
    tenant_id, attempt_id = uuid4(), uuid4()
    attempt = MaintenanceAttempt(tenant_id=tenant_id, schema_name=schema, generation=1,
        attempt_id=attempt_id, backend_pid=0, lock_key=stable_tenant_lock_key(tenant_id))
    engine = create_async_engine(mig_db_url)
    try:
        async with engine.begin() as setup:
            await setup.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            await setup.execute(sa.text("""INSERT INTO public.tenants
                (id,name,slug,subdomain,schema_name,status,generation,provisioning_attempt_id)
                VALUES (:id,'R6 old epoch',:slug,:slug,:schema,'provisioning',1,:attempt)"""),
                dict(id=tenant_id, slug='r6-epoch-' + uuid4().hex[:12], schema=schema, attempt=attempt_id))
        async with maintenance_connection(engine, attempt) as maintenance:
            await maintenance.run_migration(TENANT_PARENT)
            assert await maintenance.schema_state() == 'r6_contract_predecessor'
            assert await maintenance.compare_schema('public', load_snapshot_manifest(), predecessor=TENANT_PARENT) == []
            async with engine.begin() as setup:
                def seed(db):
                    ids = _seed_r6(db, schema)
                    fmea_id = uuid4()
                    db.execute(sa.text("""INSERT INTO fmea_documents
                        (fmea_id,document_no,title,factory_id,product_line_code,graph_data,lock_version,fmea_type,status,version)
                        VALUES (:id,'R6-OLD-EPOCH','Old epoch',:factory_id,'DC-DC-100',CAST(:graph AS jsonb),0,'PFMEA','draft',1)"""),
                        dict(id=fmea_id, factory_id=ids['factory_id'],
                            graph='{"nodes":[{"id":"cause","type":"FailureCause","name":"Old version"}],"edges":[]}'))
                    db.execute(sa.text("""INSERT INTO capa_r6_source_origins
                        (source_id,report_id,kind,module,object_id,projection_id,version,factory_id,
                         product_line_code,fmea_id,node_id)
                        VALUES (:source,:report_id,'fmea_projection','fmea',:fmea,
                            'fmea.failure_cause.reference.v1',:version,:factory_id,'DC-DC-100',:fmea,'cause')"""),
                        dict(ids, source=uuid4(), fmea=fmea_id, version='a' * 64))
                    return db.execute(sa.text('SELECT to_jsonb(s) FROM capa_r6_source_origins s ORDER BY source_id')).scalars().all()
                before = await setup.run_sync(seed)
            await maintenance.run_migration(TENANT)
            assert await maintenance.schema_state() == 'r6_epoch_predecessor'
            assert await maintenance.compare_schema('public', load_snapshot_manifest()) == []
            with pytest.raises(RuntimeError, match='R6 source evidence exists'):
                await maintenance.run_downgrade(TENANT_PARENT)
        async with engine.connect() as check:
            after = (await check.execute(sa.text(f'SELECT to_jsonb(s) FROM "{schema}".capa_r6_source_origins s ORDER BY source_id'))).scalars().all()
            assert all(item.pop('source_version_counter') is None for item in after)
            assert before == after
            assert await check.scalar(sa.text(f'SELECT version_num FROM "{schema}".tenant_schema_version')) == TENANT
    finally:
        async with engine.begin() as cleanup:
            await cleanup.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await cleanup.execute(sa.text('DELETE FROM public.tenants WHERE id=:id'), dict(id=tenant_id))
        await engine.dispose()


def _seed_legacy_sidecar(db, schema='public'):
    """Storage-only seed; authorized legacy sidecars have separate real runtime coverage."""
    from uuid import uuid4
    from tests.migrations.test_r5_d5_delta import _seed_proposal
    ids = _seed_proposal(db, schema)
    import json
    ids.update(receipt_id=uuid4(), digest='a' * 64, inputs=json.dumps([dict(
        version=1, mode='legacy_root', report_inputs=[], context_source_epochs=[])]))
    db.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
        (revision_id,report_id,binding_state,body,source_count,origin_digest)
        VALUES (:revision_id,:report_id,'legacy_unattested','legacy root',0,:digest)"""), ids)
    db.execute(sa.text("""INSERT INTO agent_d5_basis_receipts
        (receipt_id,task_id,run_id,report_id,revision_id,proof_id,lease_epoch,tenant_generation,sources,basis_hmac)
        VALUES (:receipt_id,:task_id,:run_id,:report_id,:revision_id,:proof_id,0,1,'[{}]',:digest)"""), ids)
    db.execute(sa.text("""INSERT INTO capa_r6_root_delivery_bindings
        (receipt_id,report_id,revision_id,origin_digest,input_bindings,binding_hmac)
        VALUES (:receipt_id,:report_id,:revision_id,:digest,
            CAST(:inputs AS jsonb),:digest)"""), ids)
    assert db.scalar(sa.text('SELECT count(*) FROM capa_r6_source_origins')) == 0
    assert db.scalar(sa.text('SELECT count(*) FROM capa_r6_root_delivery_bindings')) == 1
    return ids


def _epoch_fingerprint(db, schema, version_table):
    """All objects/data affected by this one downgrade, before any DDL."""
    namespace = {'schema': schema}
    quoted = db.dialect.identifier_preparer.quote_schema(schema)
    columns = [(row['name'], str(row['type']), row['nullable']) for row in
               sa.inspect(db).get_columns('capa_r6_source_origins', schema=schema)]
    constraints = db.execute(sa.text("""SELECT c.conname,pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
        WHERE n.nspname=:schema AND c.conrelid=CAST(:table AS regclass) ORDER BY c.conname"""),
        dict(namespace, table=f'{quoted}.capa_r6_source_origins')).all()
    functions = db.execute(sa.text("""SELECT pg_get_functiondef(p.oid) FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname=:schema AND p.proname='r6_fmea_source_epoch'"""), namespace).scalars().all()
    triggers = db.execute(sa.text("""SELECT pg_get_triggerdef(t.oid) FROM pg_trigger t
        JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND c.relname='fmea_documents'
        AND t.tgname='r6_fmea_source_epoch'"""), namespace).scalars().all()
    sidecars = db.execute(sa.text(f'SELECT to_jsonb(b) FROM {quoted}.capa_r6_root_delivery_bindings b ORDER BY receipt_id')).scalars().all()
    version = db.scalar(sa.text(f'SELECT version_num FROM {quoted}.{version_table}'))
    assert len(functions) == len(triggers) == 1
    return dict(columns=columns, constraints=constraints, functions=functions,
                triggers=triggers, sidecars=sidecars, version=version)


def test_public_legacy_sidecar_without_origins_refuses_epoch_downgrade_atomically(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            _seed_legacy_sidecar(db)
        with engine.connect() as db:
            before = _epoch_fingerprint(db, 'public', 'alembic_version')
        with pytest.raises(RuntimeError, match='R6 .*evidence exists'):
            command.downgrade(config, PARENT)
        with engine.connect() as db:
            assert _epoch_fingerprint(db, 'public', 'alembic_version') == before
            assert db.scalar(sa.text('SELECT count(*) FROM capa_r6_source_origins')) == 0
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_tenant_legacy_sidecar_without_origins_refuses_epoch_downgrade_atomically(mig_db_url):
    import asyncio
    from uuid import uuid4
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.tenant_transaction import stable_tenant_lock_key
    from app.services.tenant_migrator import MaintenanceAttempt, maintenance_connection
    await asyncio.to_thread(command.upgrade, _migration_config(mig_db_url), PUBLIC)
    schema, tenant_id, attempt_id = 'tenant_sidecar_' + uuid4().hex[:12], uuid4(), uuid4()
    attempt = MaintenanceAttempt(tenant_id=tenant_id, schema_name=schema, generation=1,
        attempt_id=attempt_id, backend_pid=0, lock_key=stable_tenant_lock_key(tenant_id))
    engine = create_async_engine(mig_db_url, hide_parameters=True)
    try:
        async with engine.begin() as setup:
            await setup.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            await setup.execute(sa.text("""INSERT INTO public.tenants
                (id,name,slug,subdomain,schema_name,status,generation,provisioning_attempt_id)
                VALUES (:id,'R6 sidecar',:slug,:slug,:schema,'provisioning',1,:attempt)"""),
                dict(id=tenant_id, slug='r6-sidecar-' + uuid4().hex[:12], schema=schema, attempt=attempt_id))
        async with maintenance_connection(engine, attempt) as maintenance:
            await maintenance.run_migration(TENANT)
            async with engine.begin() as setup:
                await setup.run_sync(lambda db: _seed_legacy_sidecar(db, schema))
            async with engine.connect() as check:
                before = await check.run_sync(lambda db: _epoch_fingerprint(db, schema, 'tenant_schema_version'))
            with pytest.raises(RuntimeError, match='R6 .*evidence exists'):
                await maintenance.run_downgrade(TENANT_PARENT)
            async with engine.connect() as check:
                assert await check.run_sync(lambda db: _epoch_fingerprint(db, schema, 'tenant_schema_version')) == before
                assert await check.scalar(sa.text(f'SELECT count(*) FROM "{schema}".capa_r6_source_origins')) == 0
    finally:
        async with engine.begin() as cleanup:
            await cleanup.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await cleanup.execute(sa.text('DELETE FROM public.tenants WHERE id=:id'), dict(id=tenant_id))
        await engine.dispose()
