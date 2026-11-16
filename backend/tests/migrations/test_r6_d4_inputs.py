"""Actual PostgreSQL constraints for independent D4 delivery and withdrawal."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from alembic import command
from tests.migrations.test_agent_task_core import _migration_config,_sync_engine
from tests.migrations.test_r6_entry_contracts import _seed_r6


def test_append_pairs_preserve_exact_parents_and_tenant_equivalence():
    root=Path(__file__).resolve().parents[2]
    pairs=[('20261116_r6_d4_inputs','tv017_r6_d4_inputs','20261116_r6_source_epoch','tv016_r6_source_epoch'),
           ('20261116_r6_d4_withdraw','tv018_r6_d4_withdraw','20261116_r6_d4_inputs','tv017_r6_d4_inputs')]
    for public,tenant,parent,tparent in pairs:
        body=(root/'alembic/versions'/f'{public}.py').read_text()
        tbody=(root/'alembic_tenant/versions'/f'{tenant}.py').read_text()
        assert f"down_revision = '{parent}'" in body
        assert body.replace(public,tenant).replace(parent,tparent)==tbody


def _seed_receipt(db):
    ids=_seed_r6(db)
    ids.update(receipt_id=uuid4(),deployment_id=uuid4())
    installation=db.scalar(sa.text('SELECT installation_id FROM agent_runs WHERE run_id=:run_id'),ids)
    ids['installation_id']=installation
    db.execute(sa.text("""INSERT INTO agent_model_deployments (deployment_id,name,version,tenant_generation,kind,provider,
        model,base_url,allowed_addresses,credential_ref,executor_pins,config_hmac,created_by)
        VALUES (:deployment_id,'storage-only','1',1,'local','openai','synthetic','http://127.0.0.1:1','[]','synthetic','{}',:digest,:created_by)"""),dict(ids,digest='a'*64))
    sources=[ids['source_id']]
    for version in (2,3):
        snap,source=uuid4(),uuid4()
        db.execute(sa.text("INSERT INTO capa_r6_report_snapshots (snapshot_id,report_id,kind,version,body) VALUES (:snap,:report_id,'d2',:version,'storage')"),dict(ids,snap=snap,version=version))
        db.execute(sa.text("""INSERT INTO capa_r6_source_origins (source_id,report_id,kind,module,object_id,projection_id,version,
            factory_id,product_line_code,snapshot_id) VALUES (:source,:report_id,'report_snapshot','capa',:report_id,
            'capa.d2.snapshot.v1',:version,:factory_id,'DC-DC-100',:snap)"""),dict(ids,source=source,version=str(version),snap=snap))
        sources.append(source)
    ids['versions']=json.dumps({str(key):{} for key in sources})
    return ids,sources


def test_receipt_complete_set_immutable_history_and_nonempty_downgrade(mig_db_url):
    cfg=_migration_config(mig_db_url)
    command.upgrade(cfg,'20261116_r6_d4_withdraw')
    engine=_sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids,sources=_seed_receipt(db)
            db.execute(sa.text("""INSERT INTO agent_d4_input_receipts (receipt_id,report_id,task_id,run_id,executor_id,
                installation_id,deployment_id,lease_epoch,tenant_generation,deployment_config_hmac,source_count,input_versions,receipt_hmac)
                VALUES (:receipt_id,:report_id,:task_id,:run_id,:created_by,:installation_id,:deployment_id,1,1,:digest,3,CAST(:versions AS jsonb),:digest)"""),dict(ids,digest='a'*64))
            for source in sources:
                db.execute(sa.text('INSERT INTO agent_d4_input_receipt_sources (receipt_id,report_id,source_id) VALUES (:receipt_id,:report_id,:source)'),dict(ids,source=source))
            db.execute(sa.text('SET CONSTRAINTS ALL IMMEDIATE'))
            with pytest.raises(DBAPIError),db.begin_nested():
                db.execute(sa.text('UPDATE agent_d4_input_receipts SET source_count=4 WHERE receipt_id=:receipt_id'),ids)
            with pytest.raises(DBAPIError),db.begin_nested():
                db.execute(sa.text('DELETE FROM agent_d4_input_receipt_sources WHERE receipt_id=:receipt_id'),ids)
        with pytest.raises(Exception,match='R6 D4 input evidence exists'):
            command.downgrade(cfg,'20261116_r6_source_epoch')
    finally:
        engine.dispose()


def test_withdrawal_reason_requires_the_exact_typed_receipt_and_is_immutable(mig_db_url):
    command.upgrade(_migration_config(mig_db_url),'head')
    engine=_sync_engine(mig_db_url)
    try:
        with engine.begin() as db:
            ids=_seed_r6(db)
            receipt=uuid4()
            db.execute(sa.text("""INSERT INTO capa_r6_staff_receipts (receipt_id,actor_id,operation_key,operation,request_hmac,report_id,candidate_id)
                VALUES (:receipt,:created_by,'withdraw','d4_withdraw',:digest,:report_id,:candidate_id)"""),dict(ids,receipt=receipt,digest='a'*64))
            db.execute(sa.text("INSERT INTO capa_d4_candidate_withdrawals (receipt_id,candidate_id,report_id,reason) VALUES (:receipt,:candidate_id,:report_id,'restricted reason')"),dict(ids,receipt=receipt))
            with pytest.raises(DBAPIError),db.begin_nested():
                db.execute(sa.text("UPDATE capa_d4_candidate_withdrawals SET reason='changed' WHERE receipt_id=:receipt"),{'receipt':receipt})
            # A valid candidate/report FK is insufficient: the sidecar must also
            # name the same immutable staff decision, not another candidate.
            other_command,other_candidate=uuid4(),uuid4()
            db.execute(sa.text("""INSERT INTO agent_d4_candidate_commands (command_id,report_id,task_id,run_id,command_key,operation,sequence,request_hmac)
                VALUES (:command,:report_id,:task_id,:run_id,'second','save',2,:digest)"""),dict(ids,command=other_command,digest='a'*64))
            db.execute(sa.text("""INSERT INTO capa_d4_candidates (candidate_id,report_id,task_id,run_id,command_id,original_text,supporting,opposing,
                missing_information,input_versions,state,version,created_by) VALUES (:candidate,:report_id,:task_id,:run_id,:command,'storage','[]','[]','[]','{}','pending',1,:created_by)"""),dict(ids,candidate=other_candidate,command=other_command))
            db.execute(sa.text('INSERT INTO capa_d4_candidate_sources (candidate_id,report_id,source_id) VALUES (:candidate,:report_id,:source_id)'),dict(ids,candidate=other_candidate))
            wrong=uuid4()
            db.execute(sa.text("""INSERT INTO capa_r6_staff_receipts (receipt_id,actor_id,operation_key,operation,request_hmac,report_id,candidate_id)
                VALUES (:wrong,:created_by,'wrong','d4_withdraw',:digest,:report_id,:candidate_id)"""),dict(ids,wrong=wrong,digest='a'*64))
            with pytest.raises(DBAPIError,match='withdrawal receipt mismatch'),db.begin_nested():
                db.execute(sa.text("INSERT INTO capa_d4_candidate_withdrawals (receipt_id,candidate_id,report_id,reason) VALUES (:wrong,:candidate,:report_id,'wrong')"),dict(ids,wrong=wrong,candidate=other_candidate))
    finally:
        engine.dispose()
