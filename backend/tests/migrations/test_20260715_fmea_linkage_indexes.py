import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine

REV = "20260715_fmea_linkage_indexes"
PARENT = "20260715_version_hash_backfill"


def _cfg(mig_url: str) -> Config:
    return Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))


def _indexes(conn) -> dict:
    rows = conn.execute(sa.text(
        "SELECT indexname FROM pg_indexes WHERE schemaname='public' "
        "AND indexname IN ('ix_capa_eightd_fmea_ref_id','ix_capa_eightd_factory_fmea',"
        "'ix_capa_d7_fmea_action','ix_capa_rcv_source_fmea','ix_capa_rcv_source_cause')"
    )).fetchall()
    return {r[0] for r in rows}


def test_upgrade_creates_indexes(mig_db_url):
    command.upgrade(_cfg(mig_db_url), REV)
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        assert _indexes(conn) == {
            "ix_capa_eightd_fmea_ref_id", "ix_capa_eightd_factory_fmea",
            "ix_capa_d7_fmea_action", "ix_capa_rcv_source_fmea", "ix_capa_rcv_source_cause",
        }
        # audit_logs.action remains VARCHAR(50) from 20260710_widen_audit_action
        col = conn.execute(sa.text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name='audit_logs' AND column_name='action'"
        )).one()
        assert col[0] == 50
    engine.dispose()


def test_downgrade_drops_indexes(mig_db_url):
    command.upgrade(_cfg(mig_db_url), REV)
    command.downgrade(_cfg(mig_db_url), PARENT)
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        assert _indexes(conn) == set()
        col = conn.execute(sa.text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name='audit_logs' AND column_name='action'"
        )).one()
        assert col[0] == 50
    engine.dispose()
