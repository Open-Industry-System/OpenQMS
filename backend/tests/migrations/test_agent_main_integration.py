"""No-DB contracts for reconciling the two already-shipped Agent foundations."""
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.services import tenant_migrator, tenant_schema_diff

PUBLIC_HEAD = "20261108_merge_characteristics"
TENANT_HEAD = "tv007_characteristic_refs"
ROOT = Path(__file__).resolve().parents[2]


def test_integrated_public_head_retains_both_existing_branches():
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [PUBLIC_HEAD]
    revisions = {rev.revision for rev in script.walk_revisions()}
    assert {"20260929_agent_read_task", "20261009_agent_task_attachments"} <= revisions
    assert set(script.get_revision(PUBLIC_HEAD).down_revision) == {
        "20261101_char_refs", "20261103_merge_agent_foundations",
    }


def test_integrated_tenant_head_is_reviewed_and_preserves_frozen_chain():
    from alembic_tenant import REVIEWED_REVISIONS

    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "alembic_tenant"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [TENANT_HEAD]
    assert REVIEWED_REVISIONS == (
        "tv001_business_snapshot", "tv002_agent_task_core", "tv003_agent_readonly_delivery",
        "tv004_agent_readonly_controls", "tv005_agent_task_attachments", "tv006_agent_read_tasks", TENANT_HEAD,
    )
    assert tenant_migrator.REVISION == TENANT_HEAD


@pytest.mark.asyncio
async def test_tv005_upgrade_rechecks_predecessor_and_uses_owned_delta():
    calls = []

    class Maintenance:
        async def schema_state(self):
            return "latest_predecessor"

        async def compare_schema(self, reference, manifest, **kwargs):
            calls.append(("compare", reference, kwargs))
            return []

        async def run_migration(self, revision):
            calls.append(("upgrade", revision))

    await tenant_migrator.migrate_if_needed(Maintenance(), None)
    assert calls == [
        ("compare", "public", {"predecessor": "tv005_agent_task_attachments"}),
        ("upgrade", TENANT_HEAD),
    ]


@pytest.mark.asyncio
async def test_tv005_parity_excludes_only_reviewed_reference_addition(monkeypatch):
    read_task = ("table", "agent_read_tasks")
    existing = ("table", "agent_tasks")
    objects = {"public": {existing: "existing", read_task: "new"},
               "tenant_contract": {existing: "existing"}}

    async def load(connection, schema):
        return objects[schema]

    monkeypatch.setattr(tenant_schema_diff, "_objects", load)
    compare = tenant_schema_diff.compare_business_schema
    kwargs = dict(predecessor="tv005_agent_task_attachments")
    assert await compare(None, "public", "tenant_contract", tenant_schema_diff.load_snapshot_manifest(), **kwargs) == []
    # A partially applied tenant delta must never be hidden by filtering both sides.
    objects["tenant_contract"][read_task] = "partial"
    assert await compare(None, "public", "tenant_contract", tenant_schema_diff.load_snapshot_manifest(), **kwargs)


def test_model_registry_includes_both_foundations_without_duplicate_exports():
    import app.models as models
    from app.database import TenantBase

    expected = {"agent_read_tasks", "agent_tasks", "agent_runs", "agent_plugin_installations",
                "agent_task_attachments", "agent_readonly_checkpoints"}
    assert expected <= set(TenantBase.metadata.tables)
    assert "AgentReadTask" in models.__all__
    assert len(models.__all__) == len(set(models.__all__))


def test_tenant_read_task_ddl_and_downgrade_equal_main_contract():
    import io
    import runpy
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    def ddl(path, action):
        output = io.StringIO()
        context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
        migration = runpy.run_path(str(path))
        with Operations.context(context):
            migration[action]()
        return output.getvalue()

    public = ROOT / "alembic/versions/20260929_agent_read_task.py"
    tenant = ROOT / "alembic_tenant/versions/tv006_agent_read_tasks.py"
    for action in ("upgrade", "downgrade"):
        assert ddl(tenant, action) == ddl(public, action)
    rollback = ddl(tenant, "downgrade")
    assert "DROP TABLE agent_read_tasks" in rollback
    assert "DROP TABLE agent_tasks" not in rollback


@pytest.mark.asyncio
async def test_tv005_damage_refuses_before_running_any_delta():
    from app.core.tenant_transaction import TenantUnavailable

    class Damaged:
        async def schema_state(self):
            return "latest_predecessor"

        async def compare_schema(self, *args, **kwargs):
            return ["unexpected object"]

        async def run_migration(self, revision):
            pytest.fail("damaged predecessor must not run a migration")

    with pytest.raises(TenantUnavailable, match="partial or unknown"):
        await tenant_migrator.migrate_if_needed(Damaged(), None)


@pytest.mark.requires_db
@pytest.mark.parametrize("source", ["20260929_agent_read_task", "20261009_agent_task_attachments"])
def test_each_existing_public_branch_upgrades_to_integrated_head(mig_db_url, source):
    import sqlalchemy as sa
    from alembic import command

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", mig_db_url)
    command.upgrade(cfg, source)
    command.upgrade(cfg, PUBLIC_HEAD)
    engine = sa.create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    try:
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == PUBLIC_HEAD
            assert {"agent_read_tasks", "agent_tasks", "agent_task_attachments"} <= set(sa.inspect(connection).get_table_names())
    finally:
        engine.dispose()


@pytest.mark.requires_db
@pytest.mark.asyncio
@pytest.mark.parametrize("predecessor,public_predecessor", [("tv005_agent_task_attachments", "20261009_agent_task_attachments"), ("tv006_agent_read_tasks", "20261103_merge_agent_foundations")])
async def test_owned_upgrade_parity_and_roundtrip_preserve_existing_history(mig_db_url, monkeypatch, predecessor, public_predecessor):
    import asyncio
    from uuid import uuid4
    import sqlalchemy as sa
    from alembic import command
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.schemas.platform import TenantCreateRequest
    from tests.migrations.test_agent_readonly_controls_delta import _seed_history, _history_rows

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", mig_db_url)
    await asyncio.to_thread(command.upgrade, cfg, public_predecessor)
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    monkeypatch.setattr(tenant_migrator, "REVISION", predecessor)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name="Integrated upgrade", slug="integration-" + uuid4().hex[:12],
            admin_email="integration@example.test", admin_password="IntegrationTest123!",
        ))
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: _seed_history(sync, tenant.schema_name, True, True))
            before = await connection.run_sync(lambda sync: _history_rows(sync, tenant.schema_name, True, True))
        await asyncio.to_thread(command.upgrade, cfg, PUBLIC_HEAD)
        monkeypatch.setattr(tenant_migrator, "REVISION", TENANT_HEAD)
        tenant = await tenant_migrator.resume_tenant(tenant.id)
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.compare_schema("public", tenant_schema_diff.load_snapshot_manifest()) == []
            await maintenance.run_downgrade(predecessor)
            assert await maintenance.compare_schema("public", tenant_schema_diff.load_snapshot_manifest(),
                                                     predecessor=predecessor) == []
            await maintenance.run_migration(TENANT_HEAD)
            assert await maintenance.compare_schema("public", tenant_schema_diff.load_snapshot_manifest()) == []
        async with engine.connect() as connection:
            assert await connection.scalar(sa.text(f'SELECT version_num FROM "{tenant.schema_name}".tenant_schema_version')) == TENANT_HEAD
            assert await connection.run_sync(lambda sync: _history_rows(sync, tenant.schema_name, True, True)) == before
    finally:
        await engine.dispose()
