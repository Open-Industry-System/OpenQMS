"""Migration test for capa_docg_* tables (US-E2E-01.7).

Follows D3 migration test conventions (tests/migrations/conftest.py: mig_db_url fixture).
"""
import uuid

import pytest
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import _test_db_url


def _cfg(mig_url: str) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url.replace("postgresql+asyncpg://", "postgresql://"))
    # Override script_location to absolute path (alembic resolves relative to CWD)
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    return cfg


def _sync_url(mig_url: str) -> str:
    return mig_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


# ===== Fixtures =====


@pytest.fixture
def mig_db_url(monkeypatch):
    """Create one-shot PG db (no migrations applied), return async URL. Teardown drops it."""
    from urllib.parse import urlparse

    pg = _parse_pg(_test_db_url)
    mig_dbname = f"qms_migtest_{uuid.uuid4().hex}"
    admin = create_engine(
        f"postgresql+psycopg://{pg['user']}:{pg['password'] or ''}@{pg['host']}:{pg['port']}/postgres",
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{mig_dbname}"'))
    admin.dispose()

    mig_url = f"postgresql+asyncpg://{pg['user']}:{pg['password'] or ''}@{pg['host']}:{pg['port']}/{mig_dbname}"
    monkeypatch.setenv("DATABASE_URL", mig_url)
    try:
        yield mig_url
    finally:
        admin = create_engine(
            f"postgresql+psycopg://{pg['user']}:{pg['password'] or ''}@{pg['host']}:{pg['port']}/postgres",
            isolation_level="AUTOCOMMIT",
        )
        with admin.connect() as c:
            c.execute(text(
                f"SELECT pg_terminate_backend(pg_stat_activity.pid) "
                f"FROM pg_stat_activity "
                f"WHERE pg_stat_activity.datname = '{mig_dbname}' "
                f"AND pid <> pg_backend_pid()"
            ))
            c.execute(text(f'DROP DATABASE IF EXISTS "{mig_dbname}"'))
        admin.dispose()


def _parse_pg(url: str) -> dict:
    from urllib.parse import urlparse

    p = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": p.username,
        "password": p.password,
        "dbname": p.path.lstrip("/"),
    }


# ===== Table Existence Tests =====


def test_upgrade_creates_doc_gate_tables(mig_db_url):
    """alembic upgrade head creates capa_docg_analysis/audit/decision."""
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name LIKE 'capa_docg_%' ORDER BY table_name"
        )).fetchall()
    engine.dispose()

    names = {r[0] for r in rows}
    assert "capa_docg_analysis" in names
    assert "capa_docg_audit" in names
    assert "capa_docg_decision" in names


# ===== Analysis Constraint Tests =====


def test_analysis_running_partial_uq(mig_db_url):
    """uq_docg_analysis_running: at most one running per capa_id."""
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))
    factory_id = uuid.uuid4()
    role_id = uuid.uuid4()
    user_id = uuid.uuid4()
    capa_id = uuid.uuid4()

    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO factories (id, code, name, is_active) "
            "VALUES (:fid, 'F', 'F', true)"
        ), {"fid": factory_id})
        # users requires role_id FK and legacy_role NOT NULL
        c.execute(text(
            "INSERT INTO role_definitions (id, role_key, name_zh, name_en, "
            "description, is_system, is_editable, is_active, created_at) "
            "VALUES (:rid, 'test', '测试', 'Test', 'test role', false, true, true, now())"
        ), {"rid": role_id})
        c.execute(text(
            "INSERT INTO users (user_id, username, password_hash, is_active, "
            "legacy_role, role_id) VALUES (:uid, 'u', 'h', true, 'test', :rid)"
        ), {"uid": user_id, "rid": role_id})
        c.execute(text(
            "INSERT INTO capa_eightd (report_id, document_no, title, product_line_code, factory_id, severity, d1_team, status) "
            "VALUES (:cid, '8D-T-001', 't', 'DC-DC-100', :fid, 'general', '[]'::jsonb, 'D8_GATE_PENDING')"
        ), {"cid": capa_id, "fid": factory_id})

    base = (
        "INSERT INTO capa_docg_analysis (analysis_id, capa_id, factory_id, is_current, status, "
        "attempt_token, started_at, llm_available, generated_by, generated_at, created_at) VALUES "
        "(gen_random_uuid(), :cid, :fid, false, 'running', gen_random_uuid(), now(), false, "
        ":uid, now(), now())"
    )

    with engine.begin() as c:
        c.execute(text(base), {"cid": capa_id, "fid": factory_id, "uid": user_id})

    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(base), {"cid": capa_id, "fid": factory_id, "uid": user_id})

    engine.dispose()
