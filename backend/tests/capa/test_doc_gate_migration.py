"""Migration test for capa_docg_* tables (US-E2E-01.7).

Follows D3 migration test conventions (tests/conftest.py: mig_db_url fixture).
"""
import json
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

    with pytest.raises(IntegrityError, match="uq_docg_analysis_current"):
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


def test_upgrade_invalidates_legacy_unstructured_waiver(mig_db_url):
    """Legacy waiver_reason without items is demoted to blocked before CHECK.

    Simulates a Round-21/22 row: upgrade to just-before waiver_items, insert a
    passed decision with waiver_reason and NULL items, then upgrade head.
    """
    # Stop just before waiver_items so the column does not exist yet.
    command.upgrade(_cfg(mig_db_url), "20260715_fmea_linkage_indexes")

    engine = create_engine(_sync_url(mig_db_url))
    capa_id = uuid.uuid4()
    factory_id = uuid.uuid4()
    user_id = uuid.uuid4()
    _bootstrap_capa(engine, capa_id, factory_id, user_id)
    analysis_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO capa_docg_analysis (analysis_id, capa_id, factory_id, is_current, status, "
            "affected_docs, analysis_input_hash, llm_available, attempt_token, started_at, "
            "completed_at, generated_by, generated_at, created_at) VALUES "
            "(:aid, :cid, :fid, true, 'done', '[]'::jsonb, 'hash', true, "
            "gen_random_uuid(), now(), now(), :uid, now(), now())"
        ), {"aid": analysis_id, "cid": capa_id, "fid": factory_id, "uid": user_id})
        # Pre-items schema: waiver_reason set, no waiver_items column yet.
        c.execute(text(
            "INSERT INTO capa_docg_decision (decision_id, analysis_id, revision, factory_id, "
            "decision, no_affected_confirmed, version_snapshot, waiver_reason, "
            "decided_by, decided_at, created_at) VALUES "
            "(gen_random_uuid(), :aid, 0, :fid, 'passed', false, '[]'::jsonb, "
            "'legacy unstructured waiver', :uid, now(), now())"
        ), {"aid": analysis_id, "fid": factory_id, "uid": user_id})
    engine.dispose()

    # Upgrade through waiver_items — must not fail CHECK; legacy row demoted.
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT decision, waiver_reason, waiver_items "
            "FROM capa_docg_decision WHERE analysis_id = :aid"
        ), {"aid": analysis_id}).one()
        assert row[0] == "blocked"
        assert row[1] is None
        assert row[2] is None
        # CHECK rejects new unstructured waivers
        with pytest.raises(IntegrityError):
            with engine.begin() as c2:
                c2.execute(text(
                    "INSERT INTO capa_docg_decision (decision_id, analysis_id, revision, factory_id, "
                    "decision, no_affected_confirmed, version_snapshot, waiver_reason, "
                    "waiver_items, decided_by, decided_at, created_at) VALUES "
                    "(gen_random_uuid(), :aid, 1, :fid, 'passed', false, '[]'::jsonb, "
                    "'no items', NULL, :uid, now(), now())"
                ), {"aid": analysis_id, "fid": factory_id, "uid": user_id})
    engine.dispose()


def test_round25_upgrade_invalidates_all_existing_structured_waivers(mig_db_url):
    """Old-head structured waivers are audited and invalidated fail-closed."""
    cfg = _cfg(mig_db_url)
    command.upgrade(cfg, "20260715_waiver_items")

    engine = create_engine(_sync_url(mig_db_url))
    capa_id, factory_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    analysis_id, decision_id = uuid.uuid4(), uuid.uuid4()
    audit_id, audit_run_id, doc_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _bootstrap_capa(engine, capa_id, factory_id, user_id)
    waiver_items = [{
        "doc_type": "control_plan",
        "doc_id": str(doc_id),
        "target_key": "old-item",
        "field": "control_method",
        "latest_version_id": str(uuid.uuid4()),
        "latest_sha256": "a" * 64,
        "audit_run_id": str(audit_run_id),
    }]
    version_snapshot = [{
        "doc_type": "control_plan",
        "doc_id": str(doc_id),
        "version_after_id": waiver_items[0]["latest_version_id"],
        "sha256": waiver_items[0]["latest_sha256"],
    }]
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO capa_docg_analysis (analysis_id, capa_id, factory_id, "
            "is_current, status, affected_docs, analysis_input_hash, llm_available, "
            "attempt_token, started_at, completed_at, generated_by, generated_at, created_at) "
            "VALUES (:aid, :cid, :fid, true, 'done', '[]'::jsonb, 'hash', true, "
            "gen_random_uuid(), now(), now(), :uid, now(), now())"
        ), {"aid": analysis_id, "cid": capa_id, "fid": factory_id, "uid": user_id})
        c.execute(text(
            "INSERT INTO capa_docg_audit (audit_id, analysis_id, audit_run_id, factory_id, "
            "doc_type, doc_id, doc_name, status, version_bump, coverage, covered_count, "
            "total_count, audited_by, audited_at, created_at) VALUES "
            "(:audit_id, :aid, :run_id, :fid, 'control_plan', :doc_id, 'CP', "
            "'pending_update', false, '[]'::jsonb, 0, 1, :uid, now(), now())"
        ), {
            "audit_id": audit_id, "aid": analysis_id, "run_id": audit_run_id,
            "fid": factory_id, "doc_id": doc_id, "uid": user_id,
        })
        c.execute(text(
            "INSERT INTO capa_docg_decision (decision_id, analysis_id, audit_run_id, "
            "revision, factory_id, decision, no_affected_confirmed, version_snapshot, "
            "waiver_reason, waiver_items, decided_by, decided_at, created_at) VALUES "
            "(:did, :aid, :run_id, 1, :fid, 'passed', false, CAST(:snapshot AS jsonb), "
            "'Round23 accepted', CAST(:items AS jsonb), :uid, now(), now())"
        ), {
            "did": decision_id, "aid": analysis_id, "run_id": audit_run_id,
            "fid": factory_id, "snapshot": json.dumps(version_snapshot),
            "items": json.dumps(waiver_items), "uid": user_id,
        })
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_engine(_sync_url(mig_db_url))
    with engine.connect() as c:
        decision = c.execute(text(
            "SELECT decision, waiver_reason, waiver_items, version_snapshot "
            "FROM capa_docg_decision WHERE decision_id=:did"
        ), {"did": decision_id}).one()
        assert decision == ("blocked", None, None, [])

        analysis_error = c.execute(text(
            "SELECT error FROM capa_docg_analysis WHERE analysis_id=:aid"
        ), {"aid": analysis_id}).scalar_one()
        assert "ROUND25_WAIVER_INVALIDATED" in analysis_error

        audit = c.execute(text(
            "SELECT table_name, record_id, action, changed_fields, factory_id, operated_by "
            "FROM audit_logs WHERE action='DOC_GATE_WAIVER_INVALIDATED'"
        )).one()
        assert audit.table_name == "capa_docg_decision"
        assert audit.record_id == capa_id
        assert audit.factory_id == factory_id
        assert audit.operated_by == user_id
        assert audit.changed_fields["analysis_id"] == str(analysis_id)
        assert audit.changed_fields["decision_id"] == str(decision_id)
        assert audit.changed_fields["revision"] == 1
        assert audit.changed_fields["audit_run_id"] == str(audit_run_id)
        assert audit.changed_fields["waiver_reason"] == "Round23 accepted"
        assert audit.changed_fields["waiver_items"] == waiver_items
    engine.dispose()
