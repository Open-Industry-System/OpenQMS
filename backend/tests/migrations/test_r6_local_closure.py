"""Append-only020 paired schema and historical019 compatibility, real PostgreSQL."""
from pathlib import Path
from uuid import uuid4
import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.exc import DBAPIError
from tests.migrations.test_agent_task_core import _migration_config,_sync_engine
from tests.migrations.test_r6_entry_contracts import _seed_r6

PUBLIC='20261116_r6_local_closure'
PARENT='20261116_r6_verify_origins'
TENANT='tv020_r6_local_closure'
TPARENT='tv019_r6_verify_origins'


def test_local_pair_preserves_nineteen_and_matches_exactly():
    root=Path(__file__).resolve().parents[2]
    public=(root/'alembic/versions'/f'{PUBLIC}.py').read_text()
    tenant=(root/'alembic_tenant/versions'/f'{TENANT}.py').read_text()
    assert public.replace(PUBLIC,TENANT).replace(PARENT,TPARENT)==tenant
    assert f"down_revision = '{PARENT}'" in public
    assert 'UPDATE capa_docg_analysis' not in public


def test_manual_requires_genuine_local_record_and_old_model_bytes_preserved(mig_db_url):
    cfg=_migration_config(mig_db_url)
    command.upgrade(cfg,PARENT)
    engine=_sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids=_seed_r6(db)
            aid=uuid4()
            db.execute(sa.text("""INSERT INTO capa_docg_analysis (analysis_id,capa_id,factory_id,is_current,status,
                affected_docs,analysis_input_hash,llm_available,completed_at,generated_by,attempt_token)
                VALUES (:aid,:report_id,:factory_id,true,'done','[]',:digest,true,now(),:created_by,gen_random_uuid())"""),dict(ids,aid=aid,digest='a'*64))
            before=db.scalar(sa.text('SELECT to_jsonb(a) FROM capa_docg_analysis a WHERE analysis_id=:aid'),{'aid':aid})
        command.upgrade(cfg,PUBLIC)
        with engine.begin() as db:
            after=db.scalar(sa.text('SELECT to_jsonb(a) FROM capa_docg_analysis a WHERE analysis_id=:aid'),{'aid':aid})
            assert after.pop('analysis_method')=='model' and after==before
            with pytest.raises(DBAPIError),db.begin_nested():
                db.execute(sa.text("""INSERT INTO capa_docg_analysis (analysis_id,capa_id,factory_id,is_current,status,
                    affected_docs,analysis_input_hash,llm_available,analysis_method,completed_at,generated_by,attempt_token)
                    VALUES (:aid,:report_id,:factory_id,false,'done','[]',:digest,false,'manual',now(),:created_by,gen_random_uuid())"""),dict(ids,aid=uuid4(),digest='b'*64))
                db.execute(sa.text('SET CONSTRAINTS ALL IMMEDIATE'))
    finally:engine.dispose()


def test_local_source_completeness_immutability_and_nonempty_rollback_refusal(mig_db_url):
    cfg=_migration_config(mig_db_url)
    command.upgrade(cfg,PUBLIC)
    engine=_sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids=_seed_r6(db)
            rid=uuid4()
            db.execute(sa.text("""INSERT INTO capa_r6_local_revisions (revision_id,report_id,kind,revision_no,actor_id,
                operation_key,request_hmac,text,reason,basis,input_bindings,candidates,source_count)
                VALUES (:rid,:report_id,'prevention',1,:created_by,'first-local',:digest,'local','reason','basis','{}','[]',1)"""),dict(ids,rid=rid,digest='c'*64))
            db.execute(sa.text("""INSERT INTO capa_r6_local_sources (revision_id,report_id,module,object_id,factory_id,product_line_code)
                VALUES (:rid,:report_id,'fmea',:fid,:factory_id,'DC-DC-100')"""),dict(ids,rid=rid,fid=uuid4()))
        with engine.begin() as db:
            for table,column in [('capa_r6_local_revisions','reason'),('capa_r6_local_sources','product_line_code')]:
                for operation in [f"UPDATE {table} SET {column}='mutated'",f'DELETE FROM {table}']:
                    with pytest.raises(DBAPIError),db.begin_nested():db.execute(sa.text(operation))
        with pytest.raises(Exception,match='local closure evidence exists'):
            command.downgrade(cfg,PARENT)
        with engine.connect() as db:assert db.scalar(sa.text('SELECT version_num FROM alembic_version'))==PUBLIC
    finally:engine.dispose()


def test_021_pair_is_append_only_with_exact_twenty_predecessor():
    root=Path(__file__).resolve().parents[2]
    public=(root/'alembic/versions/20261116_r6_manual_receipts.py').read_text()
    tenant=(root/'alembic_tenant/versions/tv021_r6_manual_receipts.py').read_text()
    assert public.replace('20261116_r6_manual_receipts','tv021_r6_manual_receipts').replace(PUBLIC,TENANT)==tenant
    assert f"down_revision = '{PUBLIC}'" in public


@pytest.mark.asyncio
@pytest.mark.parametrize('predecessor',['tv019_r6_verify_origins','tv020_r6_local_closure'])
async def test_local_predecessor_filter_keeps_partial_deltas_visible(monkeypatch,predecessor):
    from app.services import tenant_schema_diff as service
    base={('table','capa_eightd'):'baseline',
        ('constraint','capa_docg_analysis.chk_docg_analysis_done_complete'):"c|CHECK (status::text <> 'done'::text OR affected_docs IS NOT NULL AND analysis_input_hash IS NOT NULL AND llm_available = true AND completed_at IS NOT NULL)|false|false"}
    twenty={('table','capa_r6_local_revisions'):'local',('column','capa_docg_analysis.analysis_method'):'method',
        ('constraint','capa_docg_analysis.r6_complete_local_record'):'deferred trigger',
        ('constraint','capa_docg_analysis.chk_docg_analysis_done_complete'):'explicit manual/model done'}
    twentyone={('table','capa_r6_manual_decision_receipts'):'receipt',('function','r6_validate_manual_decision_receipt()'):'validator'}
    schemas={'public':{**base,**twenty,**twentyone},'tenant_r6':dict(base) if predecessor.startswith('tv019') else {**base,**twenty}}
    async def objects(connection,schema):return schemas[schema]
    monkeypatch.setattr(service,'_objects',objects)
    manifest=service.load_snapshot_manifest()
    assert await service.compare_business_schema(None,'public','tenant_r6',manifest,predecessor=predecessor)==[]
    schemas['tenant_r6'][('table','capa_r6_manual_decision_receipts')]='partial'
    assert await service.compare_business_schema(None,'public','tenant_r6',manifest,predecessor=predecessor)


def test_022_pair_is_append_only_with_exact_twentyone_predecessor():
    root=Path(__file__).resolve().parents[2]
    public=(root/'alembic/versions/20261116_r6_local_snapshot.py').read_text()
    tenant=(root/'alembic_tenant/versions/tv022_r6_local_snapshot.py').read_text()
    assert public.replace('20261116_r6_local_snapshot','tv022_r6_local_snapshot').replace('20261116_r6_manual_receipts','tv021_r6_manual_receipts')==tenant
    assert 'AFTER INSERT ON' in public and 'AFTER INSERT OR UPDATE' not in public


def _snapshot_root(db):
    """Actual immutable source relations; no disabled constraints or fake parents."""
    from app.services.capa_d4_material import origin_digest
    ids=_seed_r6(db)
    digest=origin_digest([ids['source_id']])
    db.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
        (revision_id,report_id,binding_state,body,source_count,origin_digest)
        VALUES (:revision_id,:report_id,'controlled','snapshot root',1,:digest)"""),dict(ids,digest=digest))
    db.execute(sa.text('INSERT INTO capa_r6_root_revision_sources (revision_id,report_id,source_id) VALUES (:revision_id,:report_id,:source_id)'),ids)
    return ids


def _zero_local(db,ids,*,key='zero-local',bindings=None,witness=None,kind='prevention',analysis_id=None):
    import json
    bindings=bindings if bindings is not None else dict(root_revision_id=str(ids['revision_id']),root_origin_ids=[str(ids['source_id'])])
    rid=uuid4()
    db.execute(sa.text("""INSERT INTO capa_r6_local_revisions (revision_id,report_id,kind,revision_no,actor_id,
        operation_key,request_hmac,text,reason,basis,input_bindings,candidates,source_count,root_snapshot_revision_id,analysis_id)
        VALUES (:rid,:report_id,:kind,1,:created_by,:key,:digest,:body,'reason',:basis,CAST(:bindings AS jsonb),'[]',0,:witness,:analysis)"""),
        dict(ids,rid=rid,kind=kind,key=key,digest='d'*64,body='local' if kind=='prevention' else None,
            basis='basis' if kind=='prevention' else None,bindings=json.dumps(bindings),
            witness=ids['revision_id'] if witness is None else witness,analysis=analysis_id))
    return rid


@pytest.mark.parametrize('violation',['missing_root','wrong_binding','missing_origin','omitted_verification','omitted_formal_source','manual_live_candidate','stale_root','mixed_origin'])
def test_snapshot_zero_source_witness_rejects_forged_or_omitted_inputs(mig_db_url,violation):
    command.upgrade(_migration_config(mig_db_url),'20261116_r6_local_snapshot')
    engine=_sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids=_snapshot_root(db)
        with engine.begin() as db:
            with pytest.raises(DBAPIError,match='snapshot origins incomplete' if violation=='mixed_origin' else None),db.begin_nested():
                witness=None
                bindings=None
                aid=None
                kind='prevention'
                if violation=='missing_root':witness=uuid4()
                elif violation=='wrong_binding':bindings=dict(root_revision_id=str(uuid4()),root_origin_ids=[str(ids['source_id'])])
                elif violation=='missing_origin':bindings=dict(root_revision_id=str(ids['revision_id']),root_origin_ids=[])
                elif violation in {'omitted_verification','omitted_formal_source','manual_live_candidate'}:
                    from tests.migrations.test_r6_verification_origins import _document
                    fid=_document(db,ids,'witness-external')
                    if violation=='omitted_verification':
                        import json
                        db.execute(sa.text("""INSERT INTO capa_root_cause_verification
                            (verification_id,capa_id,factory_id,root_cause_text,source_ref)
                            VALUES (:vid,:report_id,:factory_id,'external',CAST(:ref AS jsonb))"""),
                            dict(ids,vid=uuid4(),ref=json.dumps(dict(fmea_id=str(fid),cause_node_id='cause'))))
                    elif violation=='omitted_formal_source':
                        db.execute(sa.text("""INSERT INTO capa_d5_proposal_sources (source_id,proposal_id,projection_id,factory_id,product_line_code,fmea_id,node_id,node_hmac)
                            VALUES (:sid,:proposal_id,'fmea.failure_cause.reference.v1',:factory_id,'DC-DC-100',:fid,'cause',:digest)"""),dict(ids,sid=uuid4(),fid=fid,digest='a'*64))
                        db.execute(sa.text("UPDATE capa_d5_proposals SET state='adopted' WHERE proposal_id=:proposal_id"),ids)
                        db.execute(sa.text("""INSERT INTO capa_d5_measures (measure_id,proposal_id,final_text,adopted_by)
                            VALUES (:mid,:proposal_id,'formal',:created_by)"""),dict(ids,mid=uuid4()))
                    else:
                        aid=uuid4();kind='manual_analysis'
                        db.execute(sa.text("""INSERT INTO capa_docg_analysis (analysis_id,capa_id,factory_id,is_current,status,
                            affected_docs,analysis_input_hash,llm_available,analysis_method,completed_at,generated_by,attempt_token)
                            VALUES (:aid,:report_id,:factory_id,true,'done','[]',:digest,false,'manual',now(),:created_by,gen_random_uuid())"""),dict(ids,aid=aid,digest='a'*64))
                elif violation=='mixed_origin':
                    from tests.migrations.test_r6_verification_origins import _document
                    from app.services.capa_d4_material import origin_digest
                    fid=_document(db,ids,'mixed-source')
                    external=uuid4();new=uuid4()
                    db.execute(sa.text("""INSERT INTO capa_r6_source_origins
                        (source_id,report_id,kind,module,object_id,projection_id,version,source_version_counter,factory_id,product_line_code,fmea_id,node_id)
                        VALUES (:sid,:report_id,'fmea_projection','fmea',:fid,'fmea.failure_cause.reference.v1',:digest,0,:factory_id,'DC-DC-100',:fid,'cause')"""),dict(ids,sid=external,fid=fid,digest='a'*64))
                    db.execute(sa.text("""INSERT INTO capa_d4_root_cause_revisions
                        (revision_id,report_id,revision_no,field_hmac,actor_id,write_path)
                        VALUES (:new,:report_id,1,:digest,:created_by,'r6:storage-mixed')"""),dict(ids,new=new,digest='b'*64))
                    db.execute(sa.text("""INSERT INTO capa_r6_root_revision_bodies
                        (revision_id,report_id,binding_state,body,predecessor_id,source_count,origin_digest)
                        VALUES (:new,:report_id,'controlled','mixed',:revision_id,2,:digest)"""),dict(ids,new=new,digest=origin_digest([ids['source_id'],external])))
                    for sid in [ids['source_id'],external]:
                        db.execute(sa.text('INSERT INTO capa_r6_root_revision_sources (revision_id,report_id,source_id) VALUES (:new,:report_id,:sid)'),dict(ids,new=new,sid=sid))
                    db.execute(sa.text('SET CONSTRAINTS ALL IMMEDIATE'))
                    db.execute(sa.text('SET CONSTRAINTS ALL DEFERRED'))
                    witness=new
                    bindings=dict(root_revision_id=str(new),root_origin_ids=sorted([str(ids['source_id']),str(external)]))
                elif violation=='stale_root':
                    new=uuid4()
                    db.execute(sa.text("""INSERT INTO capa_d4_root_cause_revisions
                        (revision_id,report_id,revision_no,field_hmac,actor_id,write_path)
                        VALUES (:new,:report_id,1,:digest,:created_by,'employee')"""),dict(ids,new=new,digest='b'*64))
                _zero_local(db,ids,bindings=bindings,witness=witness,kind=kind,analysis_id=aid)
                db.execute(sa.text('SET CONSTRAINTS ALL IMMEDIATE'))
    finally:engine.dispose()


def test_snapshot_witness_is_immutable_and_downgrade_refuses_data(mig_db_url):
    cfg=_migration_config(mig_db_url)
    command.upgrade(cfg,'20261116_r6_local_snapshot')
    engine=_sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids=_snapshot_root(db)
            _zero_local(db,ids)
        with engine.begin() as db:
            with pytest.raises(DBAPIError),db.begin_nested():db.execute(sa.text('UPDATE capa_r6_local_revisions SET root_snapshot_revision_id=NULL'))
        with pytest.raises(Exception,match='snapshot witnesses exist'):
            command.downgrade(cfg,'20261116_r6_manual_receipts')
        with engine.connect() as db:assert db.scalar(sa.text('SELECT version_num FROM alembic_version'))=='20261116_r6_local_snapshot'
    finally:engine.dispose()


@pytest.mark.asyncio
async def test_022_predecessor_filter_restores_only_reviewed_delta_and_current_is_strict(monkeypatch):
    from app.services import tenant_schema_diff as service
    key=('constraint','capa_r6_local_revisions.ck_r6_local_inputs')
    base={('table','capa_r6_local_revisions'):'table',key:'CHECK (source_count > 0 AND complete_inputs)'}
    witness={('column','capa_r6_local_revisions.root_snapshot_revision_id'):'uuid',
        ('constraint','capa_r6_local_revisions.fk_r6_local_snapshot_root'):'real composite fk',
        ('constraint','capa_r6_local_revisions.ck_r6_local_snapshot_count'):'witness iff zero',
        ('constraint','capa_r6_local_revisions.r6_validate_local_snapshot_witness'):'deferred constraint trigger',
        ('trigger','capa_r6_local_revisions.r6_validate_local_snapshot_witness'):'insert only',
        ('function','r6_validate_local_snapshot_witness()'):'complete validator'}
    schemas={'public':{**base,**witness,key:'CHECK (source_count >= 0 AND complete_inputs)'},'tenant_r6':dict(base)}
    async def objects(connection,schema):return schemas[schema]
    monkeypatch.setattr(service,'_objects',objects)
    manifest=service.load_snapshot_manifest()
    assert await service.compare_business_schema(None,'public','tenant_r6',manifest,predecessor='tv021_r6_manual_receipts')==[]
    schemas['tenant_r6'][('column','capa_r6_local_revisions.root_snapshot_revision_id')]='partial'
    assert await service.compare_business_schema(None,'public','tenant_r6',manifest,predecessor='tv021_r6_manual_receipts')
    schemas['tenant_r6']=dict(schemas['public'])
    schemas['tenant_r6'][key]=base[key]
    differences=await service.compare_business_schema(None,'public','tenant_r6',manifest)
    assert any(d.object_key==key[1] for d in differences)


@pytest.mark.asyncio
@pytest.mark.parametrize('predecessor,state',[
    ('tv017_r6_d4_inputs','r6_input_predecessor'),('tv018_r6_d4_withdraw','r6_withdraw_predecessor'),
    ('tv019_r6_verify_origins','r6_verify_predecessor'),('tv020_r6_local_closure','r6_local_predecessor'),
    ('tv021_r6_manual_receipts','r6_receipt_predecessor'),('tv022_r6_local_snapshot','r6_snapshot_predecessor'),('tv023_r6_legacy_capture','r6_capture_predecessor')])
async def test_actual_nonempty_historical_tenants_upgrade_to_current_without_history_rewrite(mig_db_url,predecessor,state):
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.tenant_transaction import stable_tenant_lock_key
    from app.services.tenant_migrator import MaintenanceAttempt,maintenance_connection,migrate_if_needed
    from app.services.tenant_schema_diff import load_snapshot_manifest
    await asyncio.to_thread(command.upgrade,_migration_config(mig_db_url),'head')
    schema='tenant_local_'+uuid4().hex[:12]
    tenant_id,attempt_id=uuid4(),uuid4()
    attempt=MaintenanceAttempt(tenant_id=tenant_id,schema_name=schema,generation=1,attempt_id=attempt_id,
        backend_pid=0,lock_key=stable_tenant_lock_key(tenant_id))
    engine=create_async_engine(mig_db_url)
    try:
        async with engine.begin() as setup:
            await setup.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            await setup.execute(sa.text("""INSERT INTO public.tenants
                (id,name,slug,subdomain,schema_name,status,generation,provisioning_attempt_id)
                VALUES (:id,'Local predecessor',:slug,:slug,:schema,'provisioning',1,:attempt)"""),
                dict(id=tenant_id,slug='local-'+uuid4().hex[:12],schema=schema,attempt=attempt_id))
        async with maintenance_connection(engine,attempt) as maintenance:
            await maintenance.run_migration(predecessor)
            assert await maintenance.schema_state()==state
            assert await maintenance.compare_schema('public',load_snapshot_manifest(),predecessor=predecessor)==[]
            async with engine.begin() as setup:
                def seed(db):
                    _seed_r6(db,schema)
                    return db.execute(sa.text('SELECT to_jsonb(s) FROM capa_r6_source_origins s ORDER BY source_id')).scalars().all()
                before=await setup.run_sync(seed)
            await migrate_if_needed(maintenance,attempt)
            assert await maintenance.schema_state()=='current'
            assert await maintenance.compare_schema('public',load_snapshot_manifest())==[]
        async with engine.connect() as check:
            after=(await check.execute(sa.text(f'SELECT to_jsonb(s) FROM "{schema}".capa_r6_source_origins s ORDER BY source_id'))).scalars().all()
            assert after==before
            assert await check.scalar(sa.text(f'SELECT version_num FROM "{schema}".tenant_schema_version'))=='tv026_r7_iqc_facts'
    finally:
        async with engine.begin() as cleanup:
            await cleanup.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await cleanup.execute(sa.text('DELETE FROM public.tenants WHERE id=:id'),dict(id=tenant_id))
        await engine.dispose()
