import uuid

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine


WIDEN_REV = "20260710_widen_audit_action"
WIDEN_PARENT = "20260709_conclusion_retrycount"


def _cfg(mig_url: str) -> Config:
    return Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))


def test_widen_audit_action_downgrade_blocked_with_long_action(mig_db_url):
    """升级后存在 action >20 chars 的审计行时，downgrade 必须显式拒绝。"""
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        conn.execute(sa.text(
            "INSERT INTO audit_logs (log_id, table_name, record_id, action, operated_at) "
            "VALUES (gen_random_uuid(), 'capa_eightd', gen_random_uuid(), 'D4_VERIFICATION_PASSED', now())"
        ))
        conn.commit()
    engine.dispose()

    with pytest.raises(RuntimeError, match="action >20 chars"):
        command.downgrade(_cfg(mig_db_url), WIDEN_PARENT)


def test_widen_audit_action_downgrade_succeeds_without_long_action(mig_db_url):
    """无长 action 行时 downgrade 可正常缩窄列。"""
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        conn.execute(sa.text(
            "INSERT INTO audit_logs (log_id, table_name, record_id, action, operated_at) "
            "VALUES (gen_random_uuid(), 'capa_eightd', gen_random_uuid(), 'CREATE', now())"
        ))
        conn.commit()
    engine.dispose()

    command.downgrade(_cfg(mig_db_url), WIDEN_PARENT)

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        col = conn.execute(sa.text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name='audit_logs' AND column_name='action'"
        )).one()
        assert col[0] == 20
    engine.dispose()
