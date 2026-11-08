"""Migration contract for characteristic source references."""
from __future__ import annotations

import uuid
from pathlib import Path

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
        assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == REV
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
