"""Preserve both published R5 and current-main histories without rewriting them."""
from pathlib import Path
import asyncio
import uuid

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import sqlalchemy as sa

from tests.migrations.test_agent_task_core import _migration_config, _sync_engine

PUBLIC = "20261115_r5_main_merge"
TENANT = "tv013_r5_main_merge"
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("directory,head,parents", [
    ("alembic", PUBLIC, {"20261114_r5_models", "20261114_production_merge"}),
    ("alembic_tenant", TENANT, {"tv012_r5_models", "tv010_refresh_sessions"}),
])
def test_single_head_preserves_both_published_parents(directory, head, parents):
    config = Config()
    config.set_main_option("script_location", str(ROOT / directory))
    graph = ScriptDirectory.from_config(config)
    assert graph.get_heads() == ["20261116_r6_local_capa_sources" if directory == "alembic" else "tv024_r6_local_capa_sources"]
    assert set(graph.get_revision(head).down_revision) == parents
    assert parents <= {revision.revision for revision in graph.walk_revisions()}


@pytest.mark.parametrize("source", ["20261114_r5_models", "20261114_production_merge"])
def test_public_upgrade_from_either_branch_preserves_rows(mig_db_url, source):
    from tests.migrations.test_d4_recovery_delta import _seed_recovery

    config = _migration_config(mig_db_url)
    command.upgrade(config, source)
    engine = _sync_engine(mig_db_url)
    try:
        with engine.begin() as connection:
            ids = _seed_recovery(connection, restart=True)
            before = connection.scalar(sa.text(
                "SELECT to_jsonb(c) FROM agent_d4_recovery_checkpoints c WHERE checkpoint_id=:id"
            ), {"id": ids["checkpoint"]})
        command.upgrade(config, PUBLIC)
        command.upgrade(config, PUBLIC)
        with engine.connect() as connection:
            assert connection.scalars(sa.text("SELECT version_num FROM alembic_version")).all() == [PUBLIC]
            assert connection.scalar(sa.text(
                "SELECT to_jsonb(c) FROM agent_d4_recovery_checkpoints c WHERE checkpoint_id=:id"
            ), {"id": ids["checkpoint"]}) == before
            assert {"user_refresh_sessions", "capa_d5_proposals", "capa_d5_measures",
                    "agent_model_deployments", "agent_task_model_bindings"} <= set(
                        sa.inspect(connection).get_table_names())
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("predecessor", ["tv012_r5_models", "tv010_refresh_sessions"])
async def test_branch_parity_keeps_present_objects_and_rejects_partial_tenant(monkeypatch, predecessor):
    from app.services import tenant_schema_diff

    r5 = {("table", "agent_model_deployments"): "r5",
          ("table", "capa_d5_proposals"): "proposal",
          ("function", "r5_immutable_deployment()"): "immutable"}
    refresh = {("table", "user_refresh_sessions"): "session"}
    present, missing = (r5, refresh) if predecessor == "tv012_r5_models" else (refresh, r5)
    objects = {"public": {**present, **missing}, "tenant_merge": dict(present)}

    async def load(connection, schema):
        return objects[schema]

    monkeypatch.setattr(tenant_schema_diff, "_objects", load)
    compare = tenant_schema_diff.compare_business_schema
    manifest = tenant_schema_diff.load_snapshot_manifest()
    assert await compare(None, "public", "tenant_merge", manifest, predecessor=predecessor) == []
    key = next(iter(present))
    objects["tenant_merge"][key] = "damaged"
    assert await compare(None, "public", "tenant_merge", manifest, predecessor=predecessor)
    objects["tenant_merge"] = {**present, next(iter(missing)): "partial"}
    assert await compare(None, "public", "tenant_merge", manifest, predecessor=predecessor)


@pytest.mark.asyncio
@pytest.mark.parametrize("source,public_source,state", [
    ("tv012_r5_models", "20261114_r5_models", "r5_head"),
    ("tv010_refresh_sessions", "20261114_production_merge", "refresh_head"),
])
async def test_owned_tenant_from_either_branch_preserves_material(mig_db_url, monkeypatch, source, public_source, state):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.schemas.platform import TenantCreateRequest
    from app.services import tenant_migrator
    from app.services.tenant_schema_diff import load_snapshot_manifest
    from tests.migrations.test_r5_d5_delta import _seed_proposal

    config = _migration_config(mig_db_url)
    await asyncio.to_thread(command.upgrade, config, public_source)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    monkeypatch.setattr(tenant_migrator, "REVISION", source)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name="Synthetic R5 integration", slug="r5-merge-" + uuid.uuid4().hex[:12],
            admin_email="merge@example.test", admin_password="SyntheticMerge123!",
        ))
        schema = tenant.schema_name
        async with engine.begin() as connection:
            if source == "tv012_r5_models":
                ids = await connection.run_sync(lambda c: _seed_proposal(c, schema))
                table, column, item = "capa_d5_proposals", "proposal_id", ids["proposal_id"]
            else:
                item = uuid.uuid4()
                user = await connection.scalar(sa.text(f'SELECT user_id FROM "{schema}".users LIMIT 1'))
                await connection.execute(sa.text(
                    f'INSERT INTO "{schema}".user_refresh_sessions '
                    '(session_id,user_id,token_hash,expires_at) VALUES (:id,:user,:hash,now()+interval \'1 day\')'
                ), {"id": item, "user": user, "hash": "b" * 64})
                table, column = "user_refresh_sessions", "session_id"
            query = sa.text(f'SELECT to_jsonb(t) FROM "{schema}"."{table}" t WHERE "{column}"=:id')
            original = await connection.scalar(query, {"id": item})
        await asyncio.to_thread(command.upgrade, config, PUBLIC)
        monkeypatch.setattr(tenant_migrator, "REVISION", TENANT)
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.schema_state() == state
            assert await maintenance.compare_schema("public", load_snapshot_manifest(), predecessor=source) == []
        tenant = await tenant_migrator.resume_tenant(tenant.id)
        assert tenant.status == "active"
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.schema_state() == "current"
            assert await maintenance.compare_schema("public", load_snapshot_manifest()) == []
        async with engine.connect() as connection:
            assert await connection.scalar(query, {"id": item}) == original
            assert await connection.scalar(sa.text(f'SELECT version_num FROM "{schema}".tenant_schema_version')) == TENANT
    finally:
        await engine.dispose()
