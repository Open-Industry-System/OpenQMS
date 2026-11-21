"""Applied23/24 storage constraints and non-destructive rollback contracts."""
from pathlib import Path
from uuid import uuid4
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from alembic import command
from tests.migrations.test_agent_task_core import _migration_config,_sync_engine
from tests.migrations.test_r6_entry_contracts import _seed_r6


@pytest.mark.parametrize('public,tenant,parent,tparent',[
 ('20261116_r6_legacy_capture','tv023_r6_legacy_capture','20261116_r6_local_snapshot','tv022_r6_local_snapshot'),
 ('20261116_r6_local_capa_sources','tv024_r6_local_capa_sources','20261116_r6_legacy_capture','tv023_r6_legacy_capture')])
def test_applied_pair_bytes_are_equivalent(public,tenant,parent,tparent):
    root=Path(__file__).resolve().parents[2]
    assert (root/'alembic/versions'/f'{public}.py').read_text().replace(public,tenant).replace(parent,tparent)==(root/'alembic_tenant/versions'/f'{tenant}.py').read_text()


def test_capture_bounds_immutability_and_nonempty_downgrade(mig_db_url):
    cfg=_migration_config(mig_db_url);command.upgrade(cfg,'20261116_r6_legacy_capture')
    engine=_sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids=_seed_r6(db)
            sql=sa.text("""INSERT INTO capa_r6_legacy_captures
                (capture_id,report_id,actor_id,namespace,tenant_generation,stage,text_digest,target_material,source_bindings,binding_hmac)
                VALUES (:capture,:report_id,:created_by,:namespace,:generation,:stage,:digest,'material',CAST(:sources AS jsonb),:digest)""")
            valid=dict(ids,capture=uuid4(),namespace='single:public',generation=0,stage='d4',digest='a'*64,sources='[]')
            for delta in ({'generation':1},{'stage':'d3'},{'digest':'invalid'},{'sources':'{}'},{'sources':'[\"'+'x'*262144+'\"]'},{'sources':'['+','.join('{}' for _ in range(1001))+']'}):
                with pytest.raises(DBAPIError),db.begin_nested():db.execute(sql,dict(valid,**delta))
            db.execute(sql,valid)
            for mutation in ('UPDATE capa_r6_legacy_captures SET stage=stage','DELETE FROM capa_r6_legacy_captures'):
                with pytest.raises(DBAPIError),db.begin_nested():db.execute(sa.text(mutation))
        with pytest.raises(Exception,match='capture data must be retained'):command.downgrade(cfg,'20261116_r6_local_snapshot')
        with engine.connect() as db:assert db.scalar(sa.text('SELECT version_num FROM alembic_version'))=='20261116_r6_legacy_capture'
    finally:engine.dispose()


def test_typed_capa_pointer_has_no_new_fk_and_refuses_destructive_down(mig_db_url):
    cfg=_migration_config(mig_db_url);command.upgrade(cfg,'20261116_r6_local_capa_sources')
    engine=_sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids=_seed_r6(db);rid=uuid4();source=uuid4()
            db.execute(sa.text("""INSERT INTO capa_r6_local_revisions (revision_id,report_id,kind,revision_no,actor_id,
                operation_key,request_hmac,text,reason,basis,input_bindings,candidates,source_count)
                VALUES (:rid,:report_id,'prevention',1,:created_by,'capture-storage',:digest,'local','reason','basis','{}','[]',1)"""),dict(ids,rid=rid,digest='a'*64))
            insert=sa.text("""INSERT INTO capa_r6_local_sources
                (revision_id,report_id,module,object_id,factory_id,product_line_code,source_capa_id,source_capa_created_at)
                VALUES (:rid,:report_id,'capa',:object,:factory_id,'DC-DC-100',:source,:created)""")
            from datetime import datetime,timezone
            values=dict(ids,rid=rid,object=source,source=source,created=datetime.now(timezone.utc))
            for delta in ({'source':None},{'created':None},{'object':uuid4()}):
                with pytest.raises(DBAPIError),db.begin_nested():db.execute(insert,dict(values,**delta))
            # Retained pointer metadata is intentionally not an existence grant
            # or deletion pin; runtime validation owns current source authority.
            db.execute(insert,values)
            assert not db.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid='capa_r6_local_sources'::regclass AND contype='f' AND pg_get_constraintdef(oid) LIKE '%source_capa%')"))
        with pytest.raises(Exception,match='CAPA source evidence must be retained'):command.downgrade(cfg,'20261116_r6_legacy_capture')
        with engine.connect() as db:assert db.scalar(sa.text('SELECT version_num FROM alembic_version'))=='20261116_r6_local_capa_sources'
    finally:engine.dispose()
