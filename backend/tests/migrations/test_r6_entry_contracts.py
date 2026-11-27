"""R6 additive persistence contracts against real PostgreSQL migrations."""
from pathlib import Path
import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

PUBLIC = '20261115_r6_entry_contracts'
PARENT = '20261115_r5_responses'
TENANT = 'tv015_r6_entry_contracts'
TENANT_PARENT = 'tv014_r5_responses'
TABLES = {
    'capa_r6_material_versions', 'capa_r6_entry_switches',
    'capa_r6_report_snapshots', 'capa_r6_source_origins',
    'agent_d4_candidate_commands', 'agent_d4_candidate_checkpoint_positions',
    'capa_d4_candidates', 'capa_d4_candidate_sources',
    'capa_r6_root_revision_bodies', 'capa_r6_root_revision_sources',
    'capa_r6_staff_receipts', 'capa_d5_measure_revisions',
    'capa_r6_root_delivery_bindings',
}


def test_r6_pair_has_exact_reviewed_parents_and_unique_heads():
    root = Path(__file__).resolve().parents[2]
    assert (root / f'alembic/versions/{PUBLIC}.py').exists(), 'R6 public contract migration is missing'
    assert (root / f'alembic_tenant/versions/{TENANT}.py').exists(), 'R6 tenant contract migration is missing'
    public = (root / f'alembic/versions/{PUBLIC}.py').read_text()
    tenant = (root / f'alembic_tenant/versions/{TENANT}.py').read_text()
    assert public.replace(PUBLIC, TENANT).replace(PARENT, TENANT_PARENT) == tenant
    for directory, expected in [('alembic', '20261118_r6_security_merge'), ('alembic_tenant', 'tv024_r6_local_capa_sources')]:
        config = Config()
        config.set_main_option('script_location', str(root / directory))
        assert ScriptDirectory.from_config(config).get_heads() == [expected]


@pytest.mark.parametrize('model,fields', [
    ('D4Confirm', dict(expected_candidate_version='candidate-v1', mode='append')),
    ('D5Correct', dict(expected_measure_version='measure-v0', reason='correct reason')),
])
def test_staff_requests_validate_strict_utf8_and_server_owned_coordinates(model, fields):
    assert (Path(__file__).resolve().parents[2] / 'app/schemas/capa_r6.py').exists(), 'R6 employee request contracts are missing'
    from app.schemas import capa_r6
    schema = getattr(capa_r6, model)
    body = dict(operation_key='correct:one', expected_material_version='material-v1',
                final_text='新的正文', **fields)
    assert schema(**body).final_text == '新的正文'
    for overrides in [dict(final_text=' \n\t'), dict(final_text='界' * 5462),
                      dict(operation_key='has spaces'), dict(actor_id=str(uuid4())),
                      dict(expected_material_version='')]:
        with pytest.raises(ValueError):
            schema(**{**body, **overrides})
    if model == 'D5Correct':
        for reason in ['  ', '界' * 5462]:
            with pytest.raises(ValueError):
                schema(**{**body, 'reason': reason})


def test_candidate_command_is_bounded_and_cannot_self_declare_sources():
    from app.schemas import capa_r6
    assert hasattr(capa_r6, 'D4CandidateCommand'), 'R6 candidate command contract is missing'
    body = dict(command_key='candidate:one', text='candidate text', supporting=['evidence'],
                opposing=[], missing_information=['measurement'])
    assert capa_r6.D4CandidateCommand(**body).operation == 'save'
    for extra in [dict(sources=[]), dict(report_id=str(uuid4())), dict(text='\t'),
                  dict(text='界'*5462), dict(operation='replace')]:
        with pytest.raises(ValueError):
            capa_r6.D4CandidateCommand(**{**body, **extra})


def test_origin_dtos_are_typed_coordinates_without_authorization_or_bodies():
    from app.schemas import capa_r6
    assert hasattr(capa_r6, 'ReportSnapshotOrigin'), 'R6 typed report source contract is missing'
    assert hasattr(capa_r6, 'FmeaProjectionOrigin'), 'R6 typed FMEA source contract is missing'
    report = dict(kind='report_snapshot', module='capa', object_id=uuid4(), projection_id='capa.d2.snapshot.v1',
                  version='1', factory_id=uuid4(), product_line_code='line', snapshot_id=uuid4())
    assert capa_r6.ReportSnapshotOrigin(**report).module == 'capa'
    for extra in [dict(projection_id='capa.d4.root.v1'), dict(body='restricted'), dict(authorized=True)]:
        with pytest.raises(ValueError):
            capa_r6.ReportSnapshotOrigin(**{**report, **extra})
    doc = uuid4()
    source = dict(kind='fmea_projection', module='fmea', object_id=doc, fmea_id=doc,
                  projection_id='fmea.failure_cause.reference.v1', version='a'*64, factory_id=uuid4(),
                  product_line_code='line', node_id='cause')
    assert capa_r6.FmeaProjectionOrigin(**source).object_id == doc
    with pytest.raises(ValueError):
        capa_r6.FmeaProjectionOrigin(**{**source, 'object_id': uuid4()})


@pytest.mark.parametrize('ancestor', [None, PARENT])
def test_empty_and_nonempty_r5_upgrade_is_additive_and_repeatable(mig_db_url, ancestor):
    from tests.migrations.test_r5_d5_delta import _seed_proposal
    config = _migration_config(mig_db_url)
    engine = _sync_engine(mig_db_url)
    before = {}
    try:
        if ancestor:
            command.upgrade(config, ancestor)
            with engine.begin() as conn:
                ids = _seed_proposal(conn)
                conn.execute(sa.text("INSERT INTO capa_d5_measures (measure_id,proposal_id,final_text,adopted_by) VALUES (:id,:proposal,'original adoption',:actor)"),
                             dict(id=uuid4(), proposal=ids['proposal_id'], actor=ids['created_by']))
                for table in ['capa_eightd', 'capa_d5_measures', 'audit_logs']:
                    before[table] = conn.execute(sa.text(f'SELECT to_jsonb(t) FROM {table} t')).scalars().all()
        command.upgrade(config, PUBLIC)
        command.upgrade(config, PUBLIC)
        with engine.connect() as conn:
            assert TABLES <= set(sa.inspect(conn).get_table_names())
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == PUBLIC
            for table, rows in before.items():
                assert conn.execute(sa.text(f'SELECT to_jsonb(t) FROM {table} t')).scalars().all() == rows
            assert all(conn.scalar(sa.text(f'SELECT count(*) FROM {table}')) == 0 for table in TABLES)
    finally:
        engine.dispose()


def test_r6_models_match_actual_columns_foreign_keys_and_uniques(mig_db_url):
    from app.database import TenantBase
    command.upgrade(_migration_config(mig_db_url), 'head')
    engine = _sync_engine(mig_db_url)
    try:
        with engine.connect() as conn:
            inspector = sa.inspect(conn)
            for name in TABLES:
                table = TenantBase.metadata.tables[name]
                columns = {column['name']: column for column in inspector.get_columns(name)}
                assert set(columns) == set(table.c.keys())
                for column in table.c:
                    assert columns[column.name]['nullable'] == column.nullable
                    assert columns[column.name]['type'].compile(dialect=conn.dialect) == column.type.compile(dialect=conn.dialect)
                assert all(fk['options']['ondelete'] == 'RESTRICT' for fk in inspector.get_foreign_keys(name))
                assert {(tuple(fk['constrained_columns']), fk['referred_table'], tuple(fk['referred_columns']))
                        for fk in inspector.get_foreign_keys(name)} == {
                    (tuple(column.name for column in fk.columns), fk.referred_table.name,
                     tuple(element.column.name for element in fk.elements))
                    for fk in table.foreign_key_constraints}
                assert {tuple(c.columns.keys()) for c in table.constraints if isinstance(c, sa.UniqueConstraint)} == {
                    tuple(c['column_names']) for c in inspector.get_unique_constraints(name)}
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_predecessor_filter_rejects_partial_r6_structure(monkeypatch):
    from app.services import tenant_schema_diff
    old = {('table', 'capa_eightd'): 'old'}
    added = {('table', 'capa_r6_material_versions'): 'new',
             ('function', 'r6_immutable_history()'): 'new'}
    objects = {'public': {**old, **added}, 'tenant_r6': dict(old)}
    async def load(connection, schema):
        return objects[schema]
    monkeypatch.setattr(tenant_schema_diff, '_objects', load)
    compare = tenant_schema_diff.compare_business_schema
    manifest = tenant_schema_diff.load_snapshot_manifest()
    assert await compare(None, 'public', 'tenant_r6', manifest, predecessor=TENANT_PARENT) == []
    assert await compare(None, 'public', 'tenant_r6', manifest)
    objects['tenant_r6'][('table', 'capa_r6_material_versions')] = 'partial'
    assert await compare(None, 'public', 'tenant_r6', manifest, predecessor=TENANT_PARENT)
    with pytest.raises(ValueError, match='Unsupported schema predecessor'):
        await compare(None, 'public', 'tenant_r6', manifest, predecessor='tv099_unknown')


def _seed_r6(conn, schema='public'):
    """Storage-only contract seed; never evidence of authorized workflow use."""
    from tests.migrations.test_r5_d5_delta import _seed_proposal
    ids = _seed_proposal(conn, schema)
    ids.update(snapshot_id=uuid4(), source_id=uuid4(), candidate_id=uuid4(), r6_command_id=uuid4())
    ids['factory_id'] = conn.scalar(sa.text('SELECT factory_id FROM capa_eightd WHERE report_id=:report_id'), ids)
    conn.execute(sa.text("INSERT INTO capa_r6_report_snapshots (snapshot_id,report_id,kind,version,body) VALUES (:snapshot_id,:report_id,'d2',1,'problem snapshot')"), ids)
    conn.execute(sa.text("""INSERT INTO capa_r6_source_origins
        (source_id,report_id,kind,module,object_id,projection_id,version,factory_id,product_line_code,snapshot_id)
        VALUES (:source_id,:report_id,'report_snapshot','capa',:report_id,'capa.d2.snapshot.v1','1',:factory_id,'DC-DC-100',:snapshot_id)"""), ids)
    conn.execute(sa.text("""INSERT INTO agent_d4_candidate_commands
        (command_id,report_id,task_id,run_id,command_key,operation,sequence,request_hmac)
        VALUES (:r6_command_id,:report_id,:task_id,:run_id,'first','save',1,:digest)"""), {**ids, 'digest': 'a'*64})
    conn.execute(sa.text("""INSERT INTO capa_d4_candidates
        (candidate_id,report_id,task_id,run_id,command_id,original_text,supporting,opposing,missing_information,input_versions,state,version,created_by)
        VALUES (:candidate_id,:report_id,:task_id,:run_id,:r6_command_id,'original candidate','[]','[]','[]','{}','pending',1,:created_by)"""), ids)
    conn.execute(sa.text('INSERT INTO capa_d4_candidate_sources (candidate_id,report_id,source_id) VALUES (:candidate_id,:report_id,:source_id)'), ids)
    return ids


@pytest.mark.parametrize('violation', ['command_key', 'sequence', 'cross_report', 'missing_source',
                                         'history_update', 'history_delete', 'snapshot_d4', 'candidate_body'])
def test_real_r6_integrity_and_immutable_history(mig_db_url, violation):
    from sqlalchemy.exc import DBAPIError
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
            with pytest.raises(DBAPIError), conn.begin_nested():
                if violation in {'command_key', 'sequence'}:
                    conn.execute(sa.text("""INSERT INTO agent_d4_candidate_commands
                        (command_id,report_id,task_id,run_id,command_key,operation,sequence,request_hmac)
                        VALUES (:new,:report_id,:task_id,:run_id,:key,'save',:seq,:digest)"""),
                        {**ids, 'new': uuid4(), 'key': 'first' if violation == 'command_key' else 'second',
                         'seq': 2 if violation == 'command_key' else 1, 'digest': 'a'*64})
                elif violation == 'cross_report':
                    conn.execute(sa.text('INSERT INTO capa_d4_candidate_sources (candidate_id,report_id,source_id) VALUES (:candidate_id,:other,:source_id)'), {**ids, 'other': uuid4()})
                elif violation == 'missing_source':
                    conn.execute(sa.text('INSERT INTO capa_d4_candidate_sources (candidate_id,report_id,source_id) VALUES (:candidate_id,:report_id,:missing)'), {**ids, 'missing': uuid4()})
                elif violation == 'snapshot_d4':
                    conn.execute(sa.text("INSERT INTO capa_r6_report_snapshots (snapshot_id,report_id,kind,version,body) VALUES (:new,:report_id,'d4',2,'forbidden recursive source')"), {**ids, 'new': uuid4()})
                elif violation == 'candidate_body':
                    conn.execute(sa.text("UPDATE capa_d4_candidates SET original_text='rewritten'"))
                elif violation == 'history_update':
                    conn.execute(sa.text("UPDATE capa_r6_report_snapshots SET body='rewritten'"))
                else:
                    conn.execute(sa.text('DELETE FROM capa_d4_candidate_sources'))
    finally:
        engine.dispose()


def test_nonempty_r6_refuses_downgrade_and_preserves_history(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
        with pytest.raises(Exception, match='R6 evidence exists'):
            command.downgrade(config, PARENT)
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT version_num FROM alembic_version')) == PUBLIC
            assert conn.scalar(sa.text('SELECT original_text FROM capa_d4_candidates WHERE candidate_id=:candidate_id'), ids) == 'original candidate'
    finally:
        engine.dispose()


@pytest.mark.parametrize('violation', ['duplicate_version', 'duplicate_operation', 'revision_update',
                                         'revision_delete', 'base_text_update', 'cross_measure'])
def test_measure_correction_keeps_original_adoption_and_immutable_versions(mig_db_url, violation):
    from sqlalchemy.exc import DBAPIError
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
            ids.update(measure_id=uuid4(), correction_id=uuid4(), receipt_id=uuid4())
            conn.execute(sa.text("INSERT INTO capa_d5_measures (measure_id,proposal_id,final_text,adopted_by) VALUES (:measure_id,:proposal_id,'original adoption',:created_by)"), ids)
            conn.execute(sa.text("""INSERT INTO capa_d5_measure_revisions
                (revision_id,report_id,measure_id,revision_no,final_text,reason,actor_id)
                VALUES (:correction_id,:report_id,:measure_id,1,'corrected text','correction reason',:created_by)"""), ids)
            conn.execute(sa.text("""INSERT INTO capa_r6_staff_receipts
                (receipt_id,actor_id,operation_key,operation,request_hmac,report_id,measure_revision_id)
                VALUES (:receipt_id,:created_by,'correct-one','d5_correct',:digest,:report_id,:correction_id)"""), {**ids, 'digest': 'a'*64})
            with pytest.raises(DBAPIError), conn.begin_nested():
                if violation == 'duplicate_version':
                    conn.execute(sa.text("""INSERT INTO capa_d5_measure_revisions
                        (revision_id,report_id,measure_id,revision_no,final_text,reason,actor_id)
                        VALUES (:new,:report_id,:measure_id,1,'duplicate','reason',:created_by)"""), {**ids, 'new': uuid4()})
                elif violation == 'duplicate_operation':
                    conn.execute(sa.text("""INSERT INTO capa_r6_staff_receipts
                        (receipt_id,actor_id,operation_key,operation,request_hmac,report_id,measure_revision_id)
                        VALUES (:new,:created_by,'correct-one','d5_correct',:digest,:report_id,:correction_id)"""), {**ids, 'new': uuid4(), 'digest': 'a'*64})
                elif violation == 'cross_measure':
                    conn.execute(sa.text("""INSERT INTO capa_d5_measure_revisions
                        (revision_id,report_id,measure_id,revision_no,predecessor_id,final_text,reason,actor_id)
                        VALUES (:new,:report_id,:other,2,:correction_id,'cross measure','reason',:created_by)"""), {**ids, 'new': uuid4(), 'other': uuid4()})
                elif violation == 'revision_update':
                    conn.execute(sa.text("UPDATE capa_d5_measure_revisions SET final_text='rewritten'"))
                elif violation == 'revision_delete':
                    conn.execute(sa.text('DELETE FROM capa_d5_measure_revisions'))
                else:
                    conn.execute(sa.text("UPDATE capa_d5_measures SET final_text='rewritten adoption'"))
            assert conn.scalar(sa.text('SELECT final_text FROM capa_d5_measures WHERE measure_id=:measure_id'), ids) == 'original adoption'
            assert conn.scalar(sa.text('SELECT final_text FROM capa_d5_measure_revisions WHERE revision_id=:correction_id'), ids) == 'corrected text'
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('ancestor', [None, TENANT_PARENT])
async def test_tenant_empty_or_nonempty_predecessor_upgrade_has_exact_public_parity(mig_db_url, monkeypatch, ancestor):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator
    from app.services.tenant_schema_diff import load_snapshot_manifest
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, PARENT if ancestor else PUBLIC)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    monkeypatch.setattr(tenant_migrator, 'REVISION', ancestor or TENANT)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name='R6 contract', slug='r6-contract-' + uuid4().hex[:10],
            admin_email='r6@example.test', admin_password='R6SyntheticPassword123!'))
        original = None
        if ancestor:
            async with engine.begin() as conn:
                original = await conn.run_sync(lambda c: _seed_r5_preservation(c, tenant.schema_name))
            await asyncio.to_thread(command.upgrade, config, PUBLIC)
            monkeypatch.setattr(tenant_migrator, 'REVISION', TENANT)
            tenant = await tenant_migrator.resume_tenant(tenant.id)
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.schema_state() == 'current'
            assert await maintenance.compare_schema('public', load_snapshot_manifest()) == []
            await maintenance.run_migration(TENANT)
            assert await maintenance.compare_schema('public', load_snapshot_manifest()) == []
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT
            if original is not None:
                for table, before in original.items():
                    actual = (await conn.execute(sa.text(f'SELECT to_jsonb(t) FROM "{tenant.schema_name}".{table} t'))).scalars().all()
                    assert actual == before
    finally:
        await engine.dispose()


def _seed_r5_preservation(conn, schema):
    # A real nonempty R5 tenant, separate from any R6 controlled source.
    from tests.migrations.test_r5_d5_delta import _seed_proposal
    ids = _seed_proposal(conn, schema)
    conn.execute(sa.text("UPDATE capa_eightd SET d4_root_cause='historical root',d5_correction='historical correction' WHERE report_id=:report_id"), ids)
    conn.execute(sa.text("INSERT INTO capa_d5_measures (measure_id,proposal_id,final_text,adopted_by) VALUES (:id,:proposal,'historical adoption',:actor)"),
                 dict(id=uuid4(), proposal=ids['proposal_id'], actor=ids['created_by']))
    return {table: conn.execute(sa.text(f'SELECT to_jsonb(t) FROM {table} t')).scalars().all()
            for table in ('capa_eightd', 'capa_d5_measures', 'audit_logs')}


@pytest.mark.parametrize('violation', ['missing_document', 'wrong_factory', 'missing_node', 'wrong_node_type', 'unsupported_projection'])
def test_typed_fmea_origins_require_real_same_scope_failure_cause_projection(mig_db_url, violation):
    from sqlalchemy.exc import DBAPIError
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
            ids['fmea_id'] = uuid4()
            conn.execute(sa.text("""INSERT INTO fmea_documents (fmea_id,document_no,title,fmea_type,status,version,lock_version,factory_id,product_line_code,graph_data)
                VALUES (:fmea_id,'R6-SOURCE','live projection','PFMEA','draft',1,0,:factory_id,'DC-DC-100',
                  '{"nodes":[{"id":"cause","type":"FailureCause"},{"id":"step","type":"ProcessStep"}],"edges":[]}')"""), ids)
            # Existing live draft FMEAs are supported; approval is the projection
            # owner's access decision, not a new document status gate.
            row = dict(ids, source=uuid4(), object=ids['fmea_id'], factory=ids['factory_id'], node='cause',
                       projection='fmea.failure_cause.reference.v1', digest='a'*64)
            statement = sa.text("""INSERT INTO capa_r6_source_origins
                (source_id,report_id,kind,module,object_id,projection_id,version,factory_id,product_line_code,fmea_id,node_id)
                VALUES (:source,:report_id,'fmea_projection','fmea',:object,:projection,:digest,:factory,'DC-DC-100',:object,:node)""")
            conn.execute(statement, row)
            invalid = {**row, 'source': uuid4()}
            if violation == 'missing_document': invalid['object'] = uuid4()
            elif violation == 'wrong_factory': invalid['factory'] = uuid4()
            elif violation == 'missing_node': invalid['node'] = 'missing'
            elif violation == 'wrong_node_type': invalid['node'] = 'step'
            else: invalid['projection'] = 'fmea.full_body.unapproved.v1'
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(statement, invalid)
    finally:
        engine.dispose()


@pytest.mark.parametrize('violation', ['candidate_without_sources', 'controlled_root_without_sources',
                                     'material_decrease', 'material_delete', 'switch_duplicate_epoch'])
def test_missing_complete_sets_and_nonmonotonic_material_are_rejected(mig_db_url, violation):
    from sqlalchemy.exc import DBAPIError
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
            conn.execute(sa.text('INSERT INTO capa_r6_material_versions (report_id,counter) VALUES (:report_id,2)'), ids)
            conn.execute(sa.text("INSERT INTO capa_r6_entry_switches (switch_id,epoch,state,actor_id,evidence) VALUES (:id,0,'legacy',:created_by,'{}')"), {**ids, 'id': uuid4()})
            with pytest.raises(DBAPIError), conn.begin_nested():
                if violation == 'candidate_without_sources':
                    conn.execute(sa.text("""INSERT INTO agent_d4_candidate_commands
                        (command_id,report_id,task_id,run_id,command_key,operation,sequence,request_hmac)
                        VALUES (:new,:report_id,:task_id,:run_id,'missing-source','save',2,:digest)"""), {**ids, 'new': uuid4(), 'digest': 'a'*64})
                    conn.execute(sa.text("""INSERT INTO capa_d4_candidates
                        (candidate_id,report_id,task_id,run_id,command_id,original_text,supporting,opposing,missing_information,input_versions,state,created_by)
                        SELECT :new,report_id,task_id,run_id,command_id,'incomplete','[]','[]','[]','{}','pending',:created_by
                        FROM agent_d4_candidate_commands WHERE command_key='missing-source'"""), {**ids, 'new': uuid4()})
                    conn.execute(sa.text('SET CONSTRAINTS r6_complete_candidate_sources IMMEDIATE'))
                elif violation == 'controlled_root_without_sources':
                    conn.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                        (revision_id,report_id,binding_state,body,source_count,origin_digest)
                        VALUES (:revision_id,:report_id,'controlled','controlled snapshot',1,:digest)"""), {**ids, 'digest': 'a'*64})
                    conn.execute(sa.text('SET CONSTRAINTS r6_complete_root_sources IMMEDIATE'))
                elif violation == 'material_decrease':
                    conn.execute(sa.text('UPDATE capa_r6_material_versions SET counter=1'))
                elif violation == 'material_delete':
                    conn.execute(sa.text('DELETE FROM capa_r6_material_versions'))
                else:
                    conn.execute(sa.text("INSERT INTO capa_r6_entry_switches (switch_id,epoch,state,actor_id,evidence) VALUES (:id,0,'draining',:created_by,'{}')"), {**ids, 'id': uuid4()})
    finally:
        engine.dispose()


@pytest.mark.parametrize('violation', ['skip_predecessor', 'subtract_source'])
def test_formal_root_cannot_skip_or_subtract_complete_previous_origins(mig_db_url, violation):
    from sqlalchemy.exc import DBAPIError
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
            ids['next_revision'] = uuid4()
            conn.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                (revision_id,report_id,binding_state,body,source_count,origin_digest)
                VALUES (:revision_id,:report_id,'controlled','first body',1,:digest)"""), {**ids, 'digest': 'a'*64})
            conn.execute(sa.text('INSERT INTO capa_r6_root_revision_sources (revision_id,report_id,source_id) VALUES (:revision_id,:report_id,:source_id)'), ids)
            conn.execute(sa.text('SET CONSTRAINTS r6_complete_root_sources IMMEDIATE'))
            conn.execute(sa.text('SET CONSTRAINTS r6_complete_root_sources DEFERRED'))
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(sa.text("""INSERT INTO capa_d4_root_cause_revisions
                    (revision_id,report_id,revision_no,field_hmac,actor_id,write_path)
                    SELECT :next_revision,report_id,revision_no+1,field_hmac,actor_id,'r6-contract'
                    FROM capa_d4_root_cause_revisions WHERE revision_id=:revision_id"""), ids)
                if violation == 'skip_predecessor':
                    conn.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                        (revision_id,report_id,binding_state,body,source_count,origin_digest)
                        VALUES (:next_revision,:report_id,'controlled','unlinked replacement',1,:digest)"""), {**ids, 'digest': 'a'*64})
                    conn.execute(sa.text('INSERT INTO capa_r6_root_revision_sources (revision_id,report_id,source_id) VALUES (:next_revision,:report_id,:source_id)'), ids)
                else:
                    conn.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                        (revision_id,report_id,binding_state,body,source_count,origin_digest,predecessor_id)
                        VALUES (:next_revision,:report_id,'legacy_unattested','',0,:digest,:revision_id)"""), {**ids, 'digest': 'a'*64})
                conn.execute(sa.text('SET CONSTRAINTS r6_complete_root_sources IMMEDIATE'))
    finally:
        engine.dispose()


def test_root_history_preserves_full_accumulated_text_beyond_one_command(mig_db_url):
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    body = '完整累积正式根因' * 4096
    assert len(body.encode('utf-8')) > 16384
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
            conn.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                (revision_id,report_id,binding_state,body,source_count,origin_digest)
                VALUES (:revision_id,:report_id,'controlled',:body,1,:digest)"""), {**ids, 'body': body, 'digest': 'a'*64})
            conn.execute(sa.text('INSERT INTO capa_r6_root_revision_sources (revision_id,report_id,source_id) VALUES (:revision_id,:report_id,:source_id)'), ids)
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT body FROM capa_r6_root_revision_bodies WHERE revision_id=:revision_id'), ids) == body
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_actual_partial_r6_tenant_is_refused_without_applying_delta(mig_db_url, monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.core.tenant_transaction import TenantUnavailable
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, PARENT)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    monkeypatch.setattr(tenant_migrator, 'REVISION', TENANT_PARENT)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name='R6 partial', slug='r6-partial-' + uuid4().hex[:10],
            admin_email='partial@example.test', admin_password='R6SyntheticPassword123!'))
        async with engine.begin() as conn:
            await conn.execute(sa.text(f'CREATE TABLE "{tenant.schema_name}".capa_r6_material_versions (report_id uuid)'))
        await asyncio.to_thread(command.upgrade, config, PUBLIC)
        monkeypatch.setattr(tenant_migrator, 'REVISION', TENANT)
        with pytest.raises(TenantUnavailable, match='partial or unknown'):
            await tenant_migrator.resume_tenant(tenant.id)
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT_PARENT
            names = await conn.run_sync(lambda c: set(sa.inspect(c).get_table_names(schema=tenant.schema_name)))
            assert TABLES & names == {'capa_r6_material_versions'}
    finally:
        await engine.dispose()


def test_empty_r6_downgrade_roundtrip_keeps_r5_report_adoption_and_audit(mig_db_url):
    config = _migration_config(mig_db_url)
    command.upgrade(config, PARENT)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            original = _seed_r5_preservation(conn, 'public')
        command.upgrade(config, PUBLIC)
        command.downgrade(config, PARENT)
        with engine.connect() as conn:
            assert not TABLES & set(sa.inspect(conn).get_table_names())
            for table, before in original.items():
                assert conn.execute(sa.text(f'SELECT to_jsonb(t) FROM {table} t')).scalars().all() == before
        command.upgrade(config, PUBLIC)
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_owned_tenant_empty_downgrade_and_populated_atomic_guard(mig_db_url, monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator
    monkeypatch.setattr(tenant_migrator, 'REVISION', TENANT)
    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, PUBLIC)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name='R6 rollback guard', slug='r6-rollback-' + uuid4().hex[:10],
            admin_email='rollback@example.test', admin_password='R6SyntheticPassword123!'))
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            await maintenance.run_downgrade(TENANT_PARENT)
            assert await maintenance.schema_state() == 'r5_responses_predecessor'
            await maintenance.run_migration(TENANT)
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: _seed_r6(c, tenant.schema_name))
        with pytest.raises(RuntimeError, match='R6 evidence exists'):
            async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
                await maintenance.run_downgrade(TENANT_PARENT)
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT
            assert await conn.scalar(sa.text(f'SELECT count(*) FROM "{tenant.schema_name}".capa_d4_candidates')) == 1
    finally:
        await engine.dispose()


def test_delivery_sidecar_preserves_exact_r5_receipt_and_rejects_cross_report_binding(mig_db_url):
    from sqlalchemy.exc import DBAPIError
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
            ids.update(receipt_id=uuid4(), digest='a'*64)
            conn.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                (revision_id,report_id,binding_state,body,source_count,origin_digest)
                VALUES (:revision_id,:report_id,'controlled','root body',1,:digest)"""), ids)
            conn.execute(sa.text('INSERT INTO capa_r6_root_revision_sources (revision_id,report_id,source_id) VALUES (:revision_id,:report_id,:source_id)'), ids)
            conn.execute(sa.text("""INSERT INTO agent_d5_basis_receipts
                (receipt_id,task_id,run_id,report_id,revision_id,proof_id,lease_epoch,tenant_generation,sources,basis_hmac)
                VALUES (:receipt_id,:task_id,:run_id,:report_id,:revision_id,:proof_id,0,1,'[{"legacy":"unchanged"}]',:digest)"""), ids)
            before = conn.scalar(sa.text('SELECT to_jsonb(r) FROM agent_d5_basis_receipts r WHERE receipt_id=:receipt_id'), ids)
            statement = sa.text("""INSERT INTO capa_r6_root_delivery_bindings
                (receipt_id,report_id,revision_id,origin_digest,input_bindings,binding_hmac)
                VALUES (:receipt_id,:report_id,:revision_id,:digest,'[]',:digest)""")
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(statement, {**ids, 'report_id': uuid4()})
            conn.execute(statement, ids)
            assert conn.scalar(sa.text('SELECT to_jsonb(r) FROM agent_d5_basis_receipts r WHERE receipt_id=:receipt_id'), ids) == before
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(sa.text('DELETE FROM capa_r6_root_delivery_bindings'))
    finally:
        engine.dispose()


def test_later_transaction_cannot_backfill_root_body_behind_recorded_history(mig_db_url):
    from sqlalchemy.exc import DBAPIError
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
            ids['later_revision'] = uuid4()
            conn.execute(sa.text("""INSERT INTO capa_d4_root_cause_revisions
                (revision_id,report_id,revision_no,field_hmac,actor_id,write_path)
                SELECT :later_revision,report_id,revision_no+1,field_hmac,actor_id,'r6-contract'
                FROM capa_d4_root_cause_revisions WHERE revision_id=:revision_id"""), ids)
            conn.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                (revision_id,report_id,binding_state,body,source_count,origin_digest)
                VALUES (:later_revision,:report_id,'controlled','later body source A',1,:digest)"""), {**ids, 'digest': 'a'*64})
            conn.execute(sa.text('INSERT INTO capa_r6_root_revision_sources (revision_id,report_id,source_id) VALUES (:later_revision,:report_id,:source_id)'), ids)
        # A distinct committed transaction supplies the missing older body and
        # another legitimate same-report source B. Its existence must not make
        # the already recorded successor silently skip inherited restrictions.
        with engine.begin() as conn:
            ids.update(source_b=uuid4(), snapshot_b=uuid4())
            conn.execute(sa.text("""INSERT INTO capa_r6_report_snapshots
                (snapshot_id,report_id,kind,version,body) VALUES (:snapshot_b,:report_id,'d3',1,'source B')"""), ids)
            conn.execute(sa.text("""INSERT INTO capa_r6_source_origins
                (source_id,report_id,kind,module,object_id,projection_id,version,factory_id,product_line_code,snapshot_id)
                VALUES (:source_b,:report_id,'report_snapshot','capa',:report_id,'capa.d3.snapshot.v1','1',:factory_id,'DC-DC-100',:snapshot_b)"""), ids)
        with pytest.raises(DBAPIError):
            with engine.begin() as conn:
                conn.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                    (revision_id,report_id,binding_state,body,source_count,origin_digest)
                    VALUES (:revision_id,:report_id,'controlled','older body source B',1,:digest)"""), {**ids, 'digest': 'b'*64})
                conn.execute(sa.text('INSERT INTO capa_r6_root_revision_sources (revision_id,report_id,source_id) VALUES (:revision_id,:report_id,:source_b)'), ids)
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT count(*) FROM capa_r6_root_revision_bodies WHERE revision_id=:revision_id'), ids) == 0
            assert conn.execute(sa.text('SELECT source_id FROM capa_r6_root_revision_sources WHERE revision_id=:later_revision'), ids).scalars().all() == [ids['source_id']]
    finally:
        engine.dispose()


@pytest.mark.parametrize('kind', ['d2', 'd3'])
def test_report_snapshot_preserves_full_input_beyond_one_command_limit(mig_db_url, kind):
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    body = '完整输入快照' * 4096
    assert len(body.encode('utf-8')) > 16384
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
            conn.execute(sa.text("""INSERT INTO capa_r6_report_snapshots
                (snapshot_id,report_id,kind,version,body) VALUES (:id,:report_id,:kind,2,:body)"""),
                         {**ids, 'id': uuid4(), 'kind': kind, 'body': body})
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT body FROM capa_r6_report_snapshots WHERE report_id=:report_id AND kind=:kind AND version=2'), {**ids, 'kind': kind}) == body
    finally:
        engine.dispose()


def test_competing_root_body_insert_waits_then_rechecks_report_history(mig_db_url):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import time
    from sqlalchemy.exc import DBAPIError
    command.upgrade(_migration_config(mig_db_url), PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as conn:
            ids = _seed_r6(conn)
            ids['later_revision'] = uuid4()
            conn.execute(sa.text("""INSERT INTO capa_d4_root_cause_revisions
                (revision_id,report_id,revision_no,field_hmac,actor_id,write_path)
                SELECT :later_revision,report_id,revision_no+1,field_hmac,actor_id,'r6-contract'
                FROM capa_d4_root_cause_revisions WHERE revision_id=:revision_id"""), ids)
        ready = threading.Event()
        worker_pid = []
        def insert_older():
            try:
                with engine.begin() as conn:
                    worker_pid.append(conn.scalar(sa.text('SELECT pg_backend_pid()')))
                    ready.set()
                    conn.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                        (revision_id,report_id,binding_state,body,source_count,origin_digest)
                        VALUES (:revision_id,:report_id,'controlled','older concurrent body',1,:digest)"""), {**ids, 'digest': 'b'*64})
                    conn.execute(sa.text('INSERT INTO capa_r6_root_revision_sources (revision_id,report_id,source_id) VALUES (:revision_id,:report_id,:source_id)'), ids)
            except DBAPIError:
                return 'rejected'
            return 'committed'
        with engine.connect() as newer, ThreadPoolExecutor(max_workers=1) as executor:
            transaction = newer.begin()
            future = None
            try:
                newer_pid = newer.scalar(sa.text('SELECT pg_backend_pid()'))
                newer.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                    (revision_id,report_id,binding_state,body,source_count,origin_digest)
                    VALUES (:later_revision,:report_id,'controlled','newer concurrent body',1,:digest)"""), {**ids, 'digest': 'a'*64})
                newer.execute(sa.text('INSERT INTO capa_r6_root_revision_sources (revision_id,report_id,source_id) VALUES (:later_revision,:report_id,:source_id)'), ids)
                future = executor.submit(insert_older)
                assert ready.wait(5), 'competing connection did not start'
                blocked = False
                deadline = time.monotonic() + 5
                with engine.connect() as observer:
                    while time.monotonic() < deadline and not future.done():
                        blocked = observer.scalar(sa.text('SELECT :newer = ANY(pg_blocking_pids(:older))'),
                                                  dict(newer=newer_pid, older=worker_pid[0]))
                        if blocked:
                            break
                        time.sleep(0.01)
                assert blocked, 'root bodies must serialize through their report parent'
                transaction.commit()
                assert future.result(timeout=5) == 'rejected'
            finally:
                if transaction.is_active:
                    transaction.rollback()
                if future is not None:
                    future.result(timeout=5)
        with engine.connect() as conn:
            assert conn.scalar(sa.text('SELECT count(*) FROM capa_r6_root_revision_bodies WHERE revision_id=:revision_id'), ids) == 0
    finally:
        engine.dispose()
