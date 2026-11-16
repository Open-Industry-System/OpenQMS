"""Additive protocol pin: preserve old HMACs and strictly pair public/tenant DDL."""
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import settings
from app.services.agent_runtime import model_egress
from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

PUBLIC = "20261115_r5_responses"
PARENT = "20261115_r5_main_merge"
TENANT = "tv014_r5_responses"
TENANT_PARENT = "tv013_r5_main_merge"


def test_protocol_is_explicit_and_old_request_defaults_to_chat():
    request = dict(name="Synthetic", version="1", kind="cloud", provider="openai", model="gpt-6.1-terra",
        base_url="https://api.openai.com/v1", allowed_addresses=["127.0.0.1"], credential_ref="synthetic-only")
    assert model_egress.DeploymentCreate(**request).api_protocol == "chat_completions"
    assert model_egress.DeploymentCreate(**request, api_protocol="responses").api_protocol == "responses"
    with pytest.raises(ValueError):
        model_egress.DeploymentCreate(**request, api_protocol="guess-from-model-name")


def test_old_hmac_serialization_remains_exact_but_responses_is_bound(monkeypatch):
    tenant_id = uuid4()
    monkeypatch.setattr(model_egress, "_namespace", lambda db: SimpleNamespace(tenant_id=tenant_id))
    row = SimpleNamespace(deployment_id=uuid4(), name="Synthetic", version="1", tenant_generation=1,
        kind="cloud", provider="openai", model="gpt-6.1-terra", base_url="https://api.openai.com/v1",
        allowed_addresses=["127.0.0.1"], credential_ref="synthetic-only", executor_pins={}, created_by=uuid4())
    data = {key: str(getattr(row, key)) if key.endswith('_id') or key == 'created_by' else getattr(row, key)
            for key in model_egress.CONFIG_FIELDS}
    data['tenant_id'] = str(tenant_id)
    def digest(value):
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        return hmac.new(settings.SECRET_KEY.encode(), b'openqms.r5.model-deployment.v1\n' + raw, hashlib.sha256).hexdigest()
    legacy = digest(data)
    assert model_egress._digest(None, row) == legacy
    row.api_protocol = 'chat_completions'
    assert model_egress._digest(None, row) == legacy
    row.api_protocol = 'responses'
    assert model_egress._digest(None, row) == digest({**data, 'api_protocol': 'responses'}) != legacy
    row.api_protocol = 'unknown'
    with pytest.raises(PermissionError):
        model_egress._digest(None, row)


def test_paired_protocol_deltas_preserve_published_parents_and_single_heads():
    root = Path(__file__).resolve().parents[2]
    public = (root / 'alembic/versions/20261115_r5_responses.py').read_text()
    tenant = (root / 'alembic_tenant/versions/tv014_r5_responses.py').read_text()
    assert public.replace(PUBLIC, TENANT).replace(PARENT, TENANT_PARENT) == tenant
    for directory, expected in [('alembic', '20261116_security_main_merge'), ('alembic_tenant', TENANT)]:
        config = Config(); config.set_main_option('script_location', str(root / directory))
        assert ScriptDirectory.from_config(config).get_heads() == [expected]


@pytest.mark.asyncio
@pytest.mark.parametrize('predecessor', ['tv012_r5_models', 'tv013_r5_main_merge'])
async def test_legacy_protocol_objects_are_filtered_only_on_reference(monkeypatch, predecessor):
    from app.services import tenant_schema_diff
    present = {('table', 'agent_model_deployments'): 'existing',
               ('function', 'r5_immutable_deployment()'): 'existing-function'}
    added = {('column', 'agent_model_deployments.api_protocol'): 'chat-default',
             ('constraint', 'agent_model_deployments.ck_model_deployment_api_protocol'): 'check'}
    objects = {'public': {**present, **added}, 'tenant_protocol': dict(present)}
    async def load(connection, schema): return objects[schema]
    monkeypatch.setattr(tenant_schema_diff, '_objects', load)
    compare = tenant_schema_diff.compare_business_schema
    manifest = tenant_schema_diff.load_snapshot_manifest()
    assert await compare(None, 'public', 'tenant_protocol', manifest, predecessor=predecessor) == []
    assert await compare(None, 'public', 'tenant_protocol', manifest)
    objects['tenant_protocol'][('column', 'agent_model_deployments.api_protocol')] = 'partial'
    assert await compare(None, 'public', 'tenant_protocol', manifest, predecessor=predecessor)


def test_existing_rows_hmac_and_binding_survive_protocol_migration(mig_db_url):
    from app.database import TenantBase
    from sqlalchemy.exc import DBAPIError
    from tests.migrations.test_r5_d5_delta import _seed_proposal
    config = _migration_config(mig_db_url)
    command.upgrade(config, PARENT)
    engine = _sync_engine(mig_db_url)
    key = uuid4()
    try:
        with engine.begin() as connection:
            ids = _seed_proposal(connection)
            connection.execute(TenantBase.metadata.tables['agent_model_deployments'].insert().values(
                deployment_id=key, name='synthetic', version='legacy', tenant_generation=1,
                kind='cloud', provider='openai', model='legacy', base_url='https://api.openai.com/v1',
                allowed_addresses=['127.0.0.1'], credential_ref='synthetic-only', executor_pins={},
                config_hmac='a' * 64, created_by=ids['created_by']))
            connection.execute(TenantBase.metadata.tables['agent_task_model_bindings'].insert().values(
                task_id=ids['task_id'], deployment_id=key, config_hmac='a' * 64))
            original = connection.scalar(sa.text('SELECT to_jsonb(d) FROM agent_model_deployments d'))
            binding = connection.scalar(sa.text('SELECT to_jsonb(b) FROM agent_task_model_bindings b'))
        command.upgrade(config, PUBLIC)
        with engine.begin() as connection:
            actual = connection.scalar(sa.text('SELECT to_jsonb(d) FROM agent_model_deployments d'))
            assert actual.pop('api_protocol') == 'chat_completions'
            assert actual == original
            assert connection.scalar(sa.text('SELECT to_jsonb(b) FROM agent_task_model_bindings b')) == binding
            with pytest.raises(DBAPIError), connection.begin_nested():
                connection.execute(sa.text("UPDATE agent_model_deployments SET api_protocol='responses'"))
        command.downgrade(config, PARENT)
        with engine.connect() as connection:
            assert connection.scalar(sa.text('SELECT to_jsonb(d) FROM agent_model_deployments d')) == original
    finally:
        engine.dispose()


def test_nonempty_responses_refuses_downgrade_atomically(mig_db_url):
    from app.database import TenantBase
    from tests.migrations.test_r5_d5_delta import _seed_proposal
    config = _migration_config(mig_db_url); command.upgrade(config, PUBLIC)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as connection:
            ids = _seed_proposal(connection)
            connection.execute(TenantBase.metadata.tables['agent_model_deployments'].insert().values(
                deployment_id=uuid4(), name='synthetic', version='responses', tenant_generation=1,
                kind='cloud', provider='openai', model='gpt-6.1-terra', api_protocol='responses',
                base_url='https://api.openai.com/v1', allowed_addresses=['127.0.0.1'],
                credential_ref='synthetic-only', executor_pins={}, config_hmac='a'*64, created_by=ids['created_by']))
        with pytest.raises(Exception, match='nonempty R5 Responses'):
            command.downgrade(config, PARENT)
        with engine.connect() as connection:
            assert connection.scalar(sa.text('SELECT version_num FROM alembic_version')) == PUBLIC
            assert connection.scalar(sa.text("SELECT api_protocol FROM agent_model_deployments")) == 'responses'
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_current_tenant_protocol_column_has_full_parity(mig_db_url, monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator
    from app.services.tenant_schema_diff import load_snapshot_manifest
    await asyncio.to_thread(command.upgrade, _migration_config(mig_db_url), PUBLIC)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, 'engine', engine)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name='Synthetic Responses', slug='r5-responses-'+uuid4().hex[:12],
            admin_email='responses@example.test', admin_password='SyntheticResponses123!'))
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.schema_state() == 'current'
            assert await maintenance.compare_schema('public', load_snapshot_manifest()) == []
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT
    finally:
        await engine.dispose()
