import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine


WIDEN_REV = "20260710_widen_audit_action"
CHECK_REV = "20260710_verification_check"


def _cfg(mig_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url)
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def _constraint_names(conn) -> set:
    return {
        r[0]
        for r in conn.execute(sa.text(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'capa_root_cause_verification'::regclass"
        ))
    }


def test_check_constraint_upgrade_downgrade(mig_db_url):
    """CHECK_REV 含 conclusion-is_verified CHECK；downgrade 到 widen 后该 CHECK 被移除。

    Stops at CHECK_REV rather than head: later irreversible migrations
    (e.g. 20260715_version_hash_backfill) refuse downgrade past them.
    """
    command.upgrade(_cfg(mig_db_url), CHECK_REV)

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        assert "chk_verification_conclusion_is_verified" in _constraint_names(conn)
    engine.dispose()

    command.downgrade(_cfg(mig_db_url), WIDEN_REV)

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        assert "chk_verification_conclusion_is_verified" not in _constraint_names(conn)
    engine.dispose()
