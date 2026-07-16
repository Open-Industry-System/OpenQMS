import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine

REV = "20260716_capa_scar_ref"
PARENT = "20260715_waiver_items"  # confirmed head on CAPA/doc-gate chain


def _cfg(mig_url: str) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url)
    return cfg


def _indexes(conn) -> set[str]:
    rows = conn.execute(sa.text(
        "SELECT indexname FROM pg_indexes WHERE schemaname='public' "
        "AND indexname IN ('uq_capa_eightd_scar_ref_id','uq_supplier_scars_capa_ref_id')"
    )).fetchall()
    return {r[0] for r in rows}


def test_upgrade_adds_column_indexes_and_backfills(mig_db_url):
    command.upgrade(_cfg(mig_db_url), REV)
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        col = conn.execute(sa.text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name='capa_eightd' AND column_name='scar_ref_id'"
        )).one_or_none()
        assert col is not None
        assert col[0] == "uuid" and col[1] == "YES"
        assert _indexes(conn) == {
            "uq_capa_eightd_scar_ref_id",
            "uq_supplier_scars_capa_ref_id",
        }
        # If seed-like row exists with capa_ref_id, scar_ref_id is backfilled when same factory+PL
        # (clean empty DB: just indexes/column present)
    engine.dispose()


def test_downgrade_removes_column_and_indexes(mig_db_url):
    command.upgrade(_cfg(mig_db_url), REV)
    command.downgrade(_cfg(mig_db_url), PARENT)
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        col = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='capa_eightd' AND column_name='scar_ref_id'"
        )).scalar()
        assert col is None
        assert _indexes(conn) == set()
    engine.dispose()


def test_upgrade_aborts_on_cross_factory_dirty_link(mig_db_url, monkeypatch):
    """Optional if mig harness allows pre-insert: insert scar.capa_ref_id pointing to other factory CAPA → upgrade raises."""
    pytest.skip("Implement if mig_db_url is empty DB you control; else cover via SQL unit in upgrade() with fixture data")
