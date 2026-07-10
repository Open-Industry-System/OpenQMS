import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine


WIDEN_REV = "20260710_widen_audit_action"
CHECK_REV = "20260710_verification_check"


def _cfg(mig_url: str) -> Config:
    return Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))


def _constraint_names(conn) -> set:
    return {
        r[0]
        for r in conn.execute(sa.text(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'capa_root_cause_verification'::regclass"
        ))
    }


def test_check_constraint_upgrade_downgrade(mig_db_url):
    """head 含 conclusion-is_verified CHECK；downgrade 到 widen 后该 CHECK 被移除。"""
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        assert "chk_verification_conclusion_is_verified" in _constraint_names(conn)
    engine.dispose()

    command.downgrade(_cfg(mig_db_url), WIDEN_REV)

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        assert "chk_verification_conclusion_is_verified" not in _constraint_names(conn)
    engine.dispose()
