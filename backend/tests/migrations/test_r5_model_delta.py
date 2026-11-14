"""Actual paired T6 schema deltas, immutable recipient pins and guarded rollback."""
import asyncio
import uuid
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

PUBLIC='20261114_r5_models'
PARENT='20261114_r5_d5_basis'
TENANT='tv012_r5_models'
TABLES={'agent_model_deployments','agent_task_model_bindings'}


@pytest.mark.parametrize('parent',[None,PARENT])
def test_public_model_delta_empty_or_actual_parent(mig_db_url,parent):
    cfg=_migration_config(mig_db_url)
    if parent:command.upgrade(cfg,parent)
    command.upgrade(cfg,PUBLIC)
    engine=_sync_engine(mig_db_url)
    try:
        with engine.connect() as db:
            assert TABLES<=set(sa.inspect(db).get_table_names())
            assert db.scalar(sa.text('SELECT version_num FROM alembic_version'))==PUBLIC
    finally:engine.dispose()


def test_model_delta_pair_is_static_and_has_actual_T4_predecessors():
    root=Path(__file__).resolve().parents[2]
    public=(root/'alembic/versions/20261114_r5_models.py').read_text()
    tenant=(root/'alembic_tenant/versions/tv012_r5_models.py').read_text()
    assert public.replace(PUBLIC,TENANT).replace(PARENT,'tv011_r5_d5_basis')==tenant


def test_immutable_config_task_pin_and_nonempty_downgrade(mig_db_url):
    from tests.migrations.test_r5_d5_delta import _seed_proposal
    from app.database import TenantBase
    from sqlalchemy.exc import DBAPIError
    cfg=_migration_config(mig_db_url);command.upgrade(cfg,PUBLIC)
    engine=_sync_engine(mig_db_url)
    key=uuid.uuid4()
    try:
        with engine.begin() as db:
            ids=_seed_proposal(db)
            db.execute(TenantBase.metadata.tables['agent_model_deployments'].insert().values(
                deployment_id=key,name='synthetic',version='1',tenant_generation=1,kind='local',provider='openai',
                model='synthetic',base_url='http://127.0.0.1:1/v1',allowed_addresses=['127.0.0.1'],credential_ref='synthetic-reference',
                executor_pins={},config_hmac='a'*64,created_by=ids['created_by']))
            db.execute(TenantBase.metadata.tables['agent_task_model_bindings'].insert().values(task_id=ids['task_id'],deployment_id=key,config_hmac='a'*64))
            for sql in ["UPDATE agent_model_deployments SET model='different'",'DELETE FROM agent_model_deployments',
                        "UPDATE agent_task_model_bindings SET config_hmac=repeat('b',64)",'DELETE FROM agent_task_model_bindings']:
                with pytest.raises(DBAPIError),db.begin_nested():db.execute(sa.text(sql))
            db.execute(sa.text('UPDATE agent_model_deployments SET enabled=false'))
            with pytest.raises(DBAPIError),db.begin_nested():db.execute(sa.text('UPDATE agent_model_deployments SET enabled=true'))
        with pytest.raises(Exception,match='nonempty R5 model bindings'):command.downgrade(cfg,PARENT)
        with engine.connect() as db:
            assert db.scalar(sa.text('SELECT version_num FROM alembic_version'))==PUBLIC
            assert db.scalar(sa.text('SELECT count(*) FROM agent_task_model_bindings'))==1
    finally:engine.dispose()


@pytest.mark.asyncio
async def test_current_tenant_models_match_public(mig_db_url,monkeypatch):
    from app.services import tenant_migrator
    from app.services.tenant_schema_diff import compare_business_schema,load_snapshot_manifest
    from app.schemas.platform import TenantCreateRequest
    await asyncio.to_thread(command.upgrade,_migration_config(mig_db_url),PUBLIC)
    engine=create_async_engine(mig_db_url,poolclass=NullPool);monkeypatch.setattr(tenant_migrator,'engine',engine)
    try:
        tenant=await tenant_migrator.provision_new(TenantCreateRequest(name='Model parity',slug='model-'+uuid.uuid4().hex[:10],admin_email='model@example.test',admin_password='D4TestPassword123'))
        async with engine.connect() as db:
            assert await compare_business_schema(db,'public',tenant.schema_name,load_snapshot_manifest())==[]
            assert await db.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version'))==TENANT
    finally:await engine.dispose()
