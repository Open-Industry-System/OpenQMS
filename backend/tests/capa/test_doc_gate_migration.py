"""Migration test for capa_docg_* tables (US-E2E-01.7).

Follows D3 migration test conventions (tests/conftest.py: mig_db_url fixture).
"""
import uuid

import pytest
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def _cfg(mig_url: str) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url.replace("postgresql+asyncpg://", "postgresql://"))
    # Override script_location to absolute path (alembic resolves relative to CWD)
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    return cfg


def _sync_url(mig_url: str) -> str:
    return mig_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


def _bootstrap_capa(engine, capa_id: uuid.UUID, factory_id: uuid.UUID, user_id: uuid.UUID):
    """Insert factory, role, user and a capa_eightd row required by doc-gate rows."""
    role_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO factories (id, code, name, is_active) "
            "VALUES (:fid, 'F', 'F', true)"
        ), {"fid": factory_id})
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
    capa_id = uuid.uuid4()
    factory_id = uuid.uuid4()
    user_id = uuid.uuid4()
    _bootstrap_capa(engine, capa_id, factory_id, user_id)

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


def test_analysis_current_partial_uq(mig_db_url):
    """uq_docg_analysis_current: at most one is_current=true per capa_id."""
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))
    capa_id = uuid.uuid4()
    factory_id = uuid.uuid4()
    user_id = uuid.uuid4()
    _bootstrap_capa(engine, capa_id, factory_id, user_id)

    base = (
        "INSERT INTO capa_docg_analysis (analysis_id, capa_id, factory_id, is_current, status, "
        "affected_docs, analysis_input_hash, llm_available, attempt_token, started_at, "
        "completed_at, generated_by, generated_at, created_at) VALUES "
        "(gen_random_uuid(), :cid, :fid, true, 'done', '[]'::jsonb, 'hash', true, "
        "gen_random_uuid(), now(), now(), :uid, now(), now())"
    )

    with engine.begin() as c:
        c.execute(text(base), {"cid": capa_id, "fid": factory_id, "uid": user_id})

    with pytest.raises(IntegrityError, match="uq_docg_analysis"):
        with engine.begin() as c:
            c.execute(text(base), {"cid": capa_id, "fid": factory_id, "uid": user_id})

    engine.dispose()


def test_analysis_done_completeness_check(mig_db_url):
    """chk_docg_analysis_done_complete: status='done' requires affected_docs."""
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))
    capa_id = uuid.uuid4()
    factory_id = uuid.uuid4()
    user_id = uuid.uuid4()
    _bootstrap_capa(engine, capa_id, factory_id, user_id)

    stmt = (
        "INSERT INTO capa_docg_analysis (analysis_id, capa_id, factory_id, is_current, status, "
        "affected_docs, analysis_input_hash, llm_available, attempt_token, started_at, "
        "completed_at, generated_by, generated_at, created_at) VALUES "
        "(gen_random_uuid(), :cid, :fid, false, 'done', NULL, 'hash', true, "
        "gen_random_uuid(), now(), now(), :uid, now(), now())"
    )

    with pytest.raises(IntegrityError, match="chk_docg_analysis_done_complete"):
        with engine.begin() as c:
            c.execute(text(stmt), {"cid": capa_id, "fid": factory_id, "uid": user_id})

    engine.dispose()
