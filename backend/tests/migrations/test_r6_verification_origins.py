"""Actual PostgreSQL monotonic verification restrictions, without history backfill."""
import json
from pathlib import Path
from uuid import uuid4
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from alembic import command
from tests.migrations.test_agent_task_core import _migration_config,_sync_engine
from tests.migrations.test_r6_entry_contracts import _seed_r6

PUBLIC='20261116_r6_verify_origins'
PARENT='20261116_r6_d4_withdraw'
TENANT='tv019_r6_verify_origins'
TPARENT='tv018_r6_d4_withdraw'


def test_verification_origin_pair_is_additive_and_tenant_identical():
    root=Path(__file__).resolve().parents[2]
    public=(root/'alembic/versions'/f'{PUBLIC}.py').read_text()
    tenant=(root/'alembic_tenant/versions'/f'{TENANT}.py').read_text()
    assert public.replace(PUBLIC,TENANT).replace(PARENT,TPARENT)==tenant
    assert 'UPDATE capa_root_cause_verification' not in public


def _document(db,ids,name):
    fid=uuid4()
    db.execute(sa.text("""INSERT INTO fmea_documents (fmea_id,document_no,title,fmea_type,status,version,lock_version,
        factory_id,product_line_code,graph_data) VALUES (:fid,:name,'source','PFMEA','draft',1,0,:factory_id,'DC-DC-100',
        '{"nodes":[{"id":"cause","type":"FailureCause"}],"edges":[]}')"""),dict(ids,fid=fid,name=name))
    return fid


def test_legacy_null_stays_unattested_then_clear_and_replace_retain_known_origins(mig_db_url):
    cfg=_migration_config(mig_db_url)
    command.upgrade(cfg,PARENT)
    engine=_sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids=_seed_r6(db)
            fid=_document(db,ids,'old-A')
            vid=db.scalar(sa.text('SELECT verification_id FROM capa_root_cause_verification LIMIT 1'))
            db.execute(sa.text('UPDATE capa_root_cause_verification SET source_ref=CAST(:ref AS jsonb) WHERE verification_id=:vid'),
                {'vid':vid,'ref':json.dumps(dict(fmea_id=str(fid),cause_node_id='cause'))})
            before=db.scalar(sa.text('SELECT to_jsonb(v) FROM capa_root_cause_verification v WHERE verification_id=:vid'),{'vid':vid})
        command.upgrade(cfg,PUBLIC)
        with engine.begin() as db:
            after=db.scalar(sa.text('SELECT to_jsonb(v) FROM capa_root_cause_verification v WHERE verification_id=:vid'),{'vid':vid})
            assert after.pop('r6_source_origins') is None and after==before
            db.execute(sa.text('UPDATE capa_root_cause_verification SET source_ref=NULL WHERE verification_id=:vid'),{'vid':vid})
            origins=db.scalar(sa.text('SELECT r6_source_origins FROM capa_root_cause_verification WHERE verification_id=:vid'),{'vid':vid})
            assert len(origins)==1 and origins[0]['fmea_id']==str(fid)
            b_id=_document(db,ids,'new-B')
            db.execute(sa.text('UPDATE capa_root_cause_verification SET source_ref=CAST(:ref AS jsonb) WHERE verification_id=:vid'),
                {'vid':vid,'ref':json.dumps(dict(fmea_id=str(b_id),cause_node_id='cause'))})
            origins=db.scalar(sa.text('SELECT r6_source_origins FROM capa_root_cause_verification WHERE verification_id=:vid'),{'vid':vid})
            assert len(origins)==2 and {o['fmea_id'] for o in origins}=={str(fid),str(b_id)}
            for mutation in ["r6_source_origins=NULL","r6_source_origins='null'::jsonb","r6_source_origins='[]'::jsonb",
                    "capa_id='00000000-0000-0000-0000-000000000001'::uuid","verification_id='00000000-0000-0000-0000-000000000001'::uuid",
                    "r6_source_origins='{}'::jsonb"]:
                with pytest.raises(DBAPIError),db.begin_nested():
                    db.execute(sa.text(f'UPDATE capa_root_cause_verification SET {mutation} WHERE verification_id=:vid'),{'vid':vid})
        with pytest.raises(Exception,match='verification source restrictions exist'):
            command.downgrade(cfg,PARENT)
        with engine.connect() as db: assert db.scalar(sa.text('SELECT version_num FROM alembic_version'))==PUBLIC
    finally: engine.dispose()


def test_insert_normalizes_null_and_rejects_unknown_or_forged_source_shapes(mig_db_url):
    command.upgrade(_migration_config(mig_db_url),PUBLIC)
    engine=_sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids=_seed_r6(db)
            fid=_document(db,ids,'source-A')
            for ref in ['[]','{}','{"fmea_id":"invalid","cause_node_id":"cause"}',
                    json.dumps(dict(fmea_id=str(fid),cause_node_id='cause',source_type='unknown'))]:
                with pytest.raises(DBAPIError),db.begin_nested():
                    db.execute(sa.text("""INSERT INTO capa_root_cause_verification (verification_id,capa_id,factory_id,root_cause_text,source_ref)
                        VALUES (:vid,:report_id,:factory_id,'not written',CAST(:ref AS jsonb))"""),dict(ids,vid=uuid4(),ref=ref))
            vid=uuid4()
            db.execute(sa.text("""INSERT INTO capa_root_cause_verification (verification_id,capa_id,factory_id,root_cause_text,r6_source_origins)
                VALUES (:vid,:report_id,:factory_id,'manual','null'::jsonb)"""),dict(ids,vid=vid))
            assert db.scalar(sa.text('SELECT r6_source_origins FROM capa_root_cause_verification WHERE verification_id=:vid'),{'vid':vid})==[]
            # Normal deletion/cascade semantics remain unchanged; no DELETE trigger.
            db.execute(sa.text('DELETE FROM capa_root_cause_verification WHERE verification_id=:vid'),{'vid':vid})
    finally: engine.dispose()

@pytest.mark.asyncio
async def test_predecessor_filter_uses_real_function_identity_and_keeps_partial_delta(monkeypatch):
    from app.services import tenant_schema_diff as service
    base={('table','capa_eightd'):'baseline'}
    delta={('column','capa_root_cause_verification.r6_source_origins'):'jsonb',
        ('trigger','capa_root_cause_verification.r6_retain_verification_origins'):'trigger',
        ('function','r6_retain_verification_origins()'):'function',
        ('function','r6_verification_ref_origin(ref jsonb)'):'function'}
    schemas={'public':{**base,**delta},'tenant_r6':dict(base)}
    async def objects(connection,schema): return schemas[schema]
    monkeypatch.setattr(service,'_objects',objects)
    manifest=service.load_snapshot_manifest()
    assert await service.compare_business_schema(None,'public','tenant_r6',manifest,predecessor=TPARENT)==[]
    schemas['tenant_r6'][('column','capa_root_cause_verification.r6_source_origins')]='corrupt partial delta'
    assert await service.compare_business_schema(None,'public','tenant_r6',manifest,predecessor=TPARENT)
