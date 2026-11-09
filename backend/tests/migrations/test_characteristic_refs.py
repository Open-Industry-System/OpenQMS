"""Migration contract for characteristic source references."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine


REV = "20261101_char_refs"


def _cfg(mig_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url)
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def _engine(mig_url: str):
    return create_engine(mig_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))


def _parent_revision(cfg: Config) -> str:
    script = ScriptDirectory.from_config(cfg)
    revision = script.get_revision(REV)
    assert revision is not None
    parents = revision._versioned_down_revisions
    assert len(parents) == 1
    return parents[0]


def _seed_pre_upgrade_rows(conn):
    factory_id, cp_id, item_id, sc_id = (uuid.uuid4() for _ in range(4))
    conn.execute(sa.text(
        "INSERT INTO factories (id, code, name) VALUES (:id, 'CHAR-MIG', 'CHAR-MIG')"
    ), {"id": factory_id})
    conn.execute(sa.text(
        "INSERT INTO control_plans "
        "(cp_id, document_no, title, product_line_code, factory_id, status, phase) "
        "VALUES (:cp_id, 'CP-CHAR-MIG', 'old row', 'CHAR-MIG', :factory_id, 'draft', 'production')"
    ), {"cp_id": cp_id, "factory_id": factory_id})
    conn.execute(sa.text(
        "INSERT INTO control_plan_items (item_id, cp_id, factory_id, step_no, sort_order) "
        "VALUES (:item_id, :cp_id, :factory_id, 'OP10', 0)"
    ), {"item_id": item_id, "cp_id": cp_id, "factory_id": factory_id})
    conn.execute(sa.text(
        "INSERT INTO special_characteristics "
        "(sc_id, sc_code, sc_name, sc_type, source_node_id, source_type, product_line_code, factory_id) "
        "VALUES (:sc_id, 'SC-CHAR-MIG', 'old special', 'SC', 'legacy-node', 'PFMEA', 'CHAR-MIG', :factory_id)"
    ), {"sc_id": sc_id, "factory_id": factory_id})
    return item_id, sc_id


def test_upgrade_preserves_old_rows_and_adds_nullable_typed_columns(mig_db_url):
    """Changing either column to non-null or backfilling old records would break historical data."""
    cfg = _cfg(mig_db_url)
    parent = _parent_revision(cfg)
    command.upgrade(cfg, parent)
    engine = _engine(mig_db_url)
    with engine.begin() as conn:
        item_id, sc_id = _seed_pre_upgrade_rows(conn)

    command.upgrade(cfg, REV)
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        cp_column = {c["name"]: c for c in inspector.get_columns("control_plan_items")}["source_characteristic_ref"]
        sc_column = {c["name"]: c for c in inspector.get_columns("special_characteristics")}["source_characteristic_id"]
        assert cp_column["nullable"]
        assert sc_column["nullable"]
        assert cp_column["type"].__class__.__name__ == "JSONB"
        assert sc_column["type"].__class__.__name__ == "UUID"
        assert conn.execute(sa.text(
            "SELECT source_characteristic_ref FROM control_plan_items WHERE item_id=:item_id"
        ), {"item_id": item_id}).scalar_one() is None
        assert conn.execute(sa.text(
            "SELECT source_characteristic_id FROM special_characteristics WHERE sc_id=:sc_id"
        ), {"sc_id": sc_id}).scalar_one() is None
        assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == ScriptDirectory.from_config(cfg).get_current_head()
    engine.dispose()


def test_empty_database_downgrade_removes_only_characteristic_columns(mig_db_url):
    """The reversible schema-only migration must remove its two nullable columns on an empty DB."""
    cfg = _cfg(mig_db_url)
    parent = _parent_revision(cfg)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, parent)

    engine = _engine(mig_db_url)
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        assert "source_characteristic_ref" not in {
            c["name"] for c in inspector.get_columns("control_plan_items")
        }
        assert "source_characteristic_id" not in {
            c["name"] for c in inspector.get_columns("special_characteristics")
        }
        assert "control_plan_items" in inspector.get_table_names()
        assert "special_characteristics" in inspector.get_table_names()
    engine.dispose()


def test_tenant_characteristic_delta_matches_public_and_preserves_predecessor():
    from tests.migrations.test_agent_main_integration import ROOT
    from alembic.script import ScriptDirectory
    import io
    import runpy
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "alembic_tenant"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["tv007_characteristic_refs"]
    assert script.get_revision("tv007_characteristic_refs").down_revision == "tv006_agent_read_tasks"
    def ddl(path, action):
        output = io.StringIO()
        context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
        migration = runpy.run_path(str(path))
        with Operations.context(context):
            migration[action]()
        return output.getvalue()
    for action in ("upgrade", "downgrade"):
        assert ddl(ROOT / "alembic_tenant/versions/tv007_characteristic_refs.py", action) == ddl(ROOT / "alembic/versions/20261101_characteristic_refs.py", action)


@pytest.mark.asyncio
async def test_historical_characteristic_parity_never_hides_current_or_partial_drift(monkeypatch):
    from app.services import tenant_schema_diff as diff
    existing = ("column", "control_plan_items.control_method")
    added = ("column", "control_plan_items.source_characteristic_ref")
    objects = {"public": {existing: "text", added: "jsonb"},
               "tenant_contract": {existing: "text"}}

    async def load(connection, schema):
        return objects[schema]

    monkeypatch.setattr(diff, "_objects", load)
    manifest = diff.load_snapshot_manifest()
    assert await diff.compare_business_schema(None, "public", "tenant_contract", manifest,
                                              predecessor="tv006_agent_read_tasks") == []
    # The very same old schema is not current; a missing provenance column is drift.
    assert await diff.compare_business_schema(None, "public", "tenant_contract", manifest)
    objects["tenant_contract"][added] = "wrong partial column"
    assert await diff.compare_business_schema(None, "public", "tenant_contract", manifest,
                                              predecessor="tv006_agent_read_tasks")
    objects["tenant_contract"][added] = "jsonb"
    assert await diff.compare_business_schema(None, "public", "tenant_contract", manifest) == []
