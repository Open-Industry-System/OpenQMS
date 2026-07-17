"""Migration test for capa_docg_* tables (US-E2E-01.7).

Follows D3 migration test conventions (tests/conftest.py: mig_db_url fixture).
"""
import json
import uuid
from argparse import Namespace
from datetime import datetime, timedelta, timezone

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
    """Pre-items waiver is traced through its immutable historical event."""
    cfg = _cfg(mig_db_url)
    command.upgrade(cfg, "20260715_fmea_linkage_indexes")
    engine = create_engine(_sync_url(mig_db_url))
    capa_id, factory_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    analysis_id, decision_id, audit_run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    blocked_decision_id = uuid.uuid4()
    waiver_decided_at = datetime.now(timezone.utc)
    blocked_decided_at = waiver_decided_at - timedelta(seconds=30)
    _bootstrap_capa(engine, capa_id, factory_id, user_id)
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO capa_docg_analysis (analysis_id,capa_id,factory_id,is_current,status,"
            "affected_docs,analysis_input_hash,llm_available,attempt_token,started_at,completed_at,"
            "generated_by,generated_at,created_at) VALUES "
            "(:aid,:cid,:fid,true,'done','[]'::jsonb,'hash',true,gen_random_uuid(),now(),now(),:uid,now(),now())"
        ), {"aid": analysis_id, "cid": capa_id, "fid": factory_id, "uid": user_id})
        c.execute(text(
            "INSERT INTO capa_docg_decision (decision_id,analysis_id,audit_run_id,revision,factory_id,"
            "decision,no_affected_confirmed,version_snapshot,waiver_reason,decided_by,decided_at,created_at) "
            "VALUES (:did,:aid,:run,0,:fid,'blocked',false,'[]'::jsonb,NULL,:uid,:decided_at,:decided_at)"
        ), {"did": blocked_decision_id, "aid": analysis_id, "run": audit_run_id,
             "fid": factory_id, "uid": user_id, "decided_at": blocked_decided_at})
        c.execute(text(
            "INSERT INTO capa_docg_decision (decision_id,analysis_id,audit_run_id,revision,factory_id,"
            "decision,no_affected_confirmed,version_snapshot,waiver_reason,decided_by,decided_at,created_at) "
            "VALUES (:did,:aid,:run,1,:fid,'passed',false,CAST(:snap AS jsonb),:reason,:uid,:decided_at,:decided_at)"
        ), {"did": decision_id, "aid": analysis_id, "run": audit_run_id, "fid": factory_id,
             "snap": json.dumps([{"legacy": True}]), "reason": "legacy unstructured waiver",
             "uid": user_id, "decided_at": waiver_decided_at})
        c.execute(text(
            "INSERT INTO audit_logs (log_id,table_name,record_id,action,changed_fields,operated_by,factory_id,operated_at) "
            "VALUES (gen_random_uuid(),'capa_eightd',:cid,'DOC_GATE_WAIVER',CAST(:fields AS jsonb),:uid,:fid,:operated_at)"
        ), {"cid": capa_id, "uid": user_id, "fid": factory_id, "fields": json.dumps({
            "reason": "legacy unstructured waiver", "decision_from": "blocked",
            "decision_to": "passed", "audit_run_id": str(audit_run_id),
        }), "operated_at": waiver_decided_at})
    engine.dispose()
    command.upgrade(cfg, "head")
    engine = create_engine(_sync_url(mig_db_url))
    with engine.connect() as c:
        row = c.execute(text("SELECT decision,waiver_reason,waiver_items FROM capa_docg_decision WHERE decision_id=:did"), {"did": decision_id}).one()
        assert row == ("blocked", None, None)
        error = c.execute(text("SELECT error FROM capa_docg_analysis WHERE analysis_id=:aid"), {"aid": analysis_id}).scalar_one()
        assert "ROUND25_WAIVER_INVALIDATED" in error
        events = c.execute(text(
            "SELECT table_name,record_id,changed_fields FROM audit_logs "
            "WHERE action='DOC_GATE_WAIVER_INVALIDATED'"
        )).all()
        assert len(events) == 1
        event = events[0]
        assert event.table_name == "capa_eightd"
        assert event.record_id == capa_id
        assert event.changed_fields["decision_id"] == str(decision_id)
        assert event.changed_fields["audit_run_id"] == str(audit_run_id)
        assert event.changed_fields["waiver_reason"] == "legacy unstructured waiver"
        assert event.changed_fields["old_decision"] == "passed"
        assert event.changed_fields["evidence_source"] == "historical_doc_gate_waiver_event"
        assert event.changed_fields["old_version_snapshot"] is None
        assert event.changed_fields["old_version_snapshot_unavailable_reason"] == (
            "cleared_by_20260715_waiver_items_before_round25"
        )
        assert event.changed_fields["decision_id"] != str(blocked_decision_id)
        with pytest.raises(IntegrityError):
            with engine.begin() as c2:
                c2.execute(text(
                    "INSERT INTO capa_docg_decision (decision_id,analysis_id,revision,factory_id,decision,"
                    "no_affected_confirmed,version_snapshot,waiver_reason,waiver_items,decided_by,decided_at,created_at) "
                    "VALUES (gen_random_uuid(),:aid,2,:fid,'passed',false,'[]'::jsonb,'no items',NULL,:uid,now(),now())"
                ), {"aid": analysis_id, "fid": factory_id, "uid": user_id})
    engine.dispose()

    command.downgrade(cfg, "20260715_waiver_items")
    command.upgrade(cfg, "head")

    engine = create_engine(_sync_url(mig_db_url))
    with engine.connect() as c:
        event_count = c.execute(text(
            "SELECT count(*) FROM audit_logs "
            "WHERE action='DOC_GATE_WAIVER_INVALIDATED' "
            "AND changed_fields->>'decision_id'=:decision_id"
        ), {"decision_id": str(decision_id)}).scalar_one()
        error = c.execute(text(
            "SELECT error FROM capa_docg_analysis WHERE analysis_id=:aid"
        ), {"aid": analysis_id}).scalar_one()
    engine.dispose()

    assert event_count == 1
    assert error.count("[ROUND25_WAIVER_INVALIDATED]") == 1


def test_round25_upgrade_invalidates_all_existing_structured_waivers(mig_db_url):
    """Old-head structured waivers preserve all destroyed approval evidence."""
    cfg = _cfg(mig_db_url)
    command.upgrade(cfg, "20260715_waiver_items")
    engine = create_engine(_sync_url(mig_db_url))
    capa_id, factory_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    analysis_id, decision_id = uuid.uuid4(), uuid.uuid4()
    audit_id, audit_run_id, doc_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _bootstrap_capa(engine, capa_id, factory_id, user_id)
    waiver_items = [{"doc_type": "control_plan", "doc_id": str(doc_id), "target_key": "old-item",
                     "field": "control_method", "latest_version_id": str(uuid.uuid4()),
                     "latest_sha256": "a" * 64, "audit_run_id": str(audit_run_id)}]
    version_snapshot = [{"doc_type": "control_plan", "doc_id": str(doc_id),
                         "version_after_id": waiver_items[0]["latest_version_id"],
                         "sha256": waiver_items[0]["latest_sha256"]}]
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO capa_docg_analysis (analysis_id,capa_id,factory_id,is_current,status,affected_docs,"
            "analysis_input_hash,llm_available,attempt_token,started_at,completed_at,generated_by,generated_at,created_at) "
            "VALUES (:aid,:cid,:fid,true,'done','[]'::jsonb,'hash',true,gen_random_uuid(),now(),now(),:uid,now(),now())"
        ), {"aid": analysis_id, "cid": capa_id, "fid": factory_id, "uid": user_id})
        c.execute(text(
            "INSERT INTO capa_docg_audit (audit_id,analysis_id,audit_run_id,factory_id,doc_type,doc_id,"
            "doc_name,status,version_bump,coverage,covered_count,total_count,audited_by,audited_at,created_at) "
            "VALUES (:audit,:aid,:run,:fid,'control_plan',:doc,'CP','pending_update',false,'[]'::jsonb,0,1,:uid,now(),now())"
        ), {"audit": audit_id, "aid": analysis_id, "run": audit_run_id, "fid": factory_id,
             "doc": doc_id, "uid": user_id})
        c.execute(text(
            "INSERT INTO capa_docg_decision (decision_id,analysis_id,audit_run_id,revision,factory_id,decision,"
            "no_affected_confirmed,version_snapshot,waiver_reason,waiver_items,decided_by,decided_at,created_at) "
            "VALUES (:did,:aid,:run,1,:fid,'passed',false,CAST(:snapshot AS jsonb),:reason,CAST(:items AS jsonb),:uid,now(),now())"
        ), {"did": decision_id, "aid": analysis_id, "run": audit_run_id, "fid": factory_id,
             "snapshot": json.dumps(version_snapshot), "reason": "Round23 accepted",
             "items": json.dumps(waiver_items), "uid": user_id})
    engine.dispose()
    command.upgrade(cfg, "head")
    engine = create_engine(_sync_url(mig_db_url))
    with engine.connect() as c:
        decision = c.execute(text("SELECT decision,waiver_reason,waiver_items,version_snapshot FROM capa_docg_decision WHERE decision_id=:did"), {"did": decision_id}).one()
        assert decision == ("blocked", None, None, [])
        error = c.execute(text("SELECT error FROM capa_docg_analysis WHERE analysis_id=:aid"), {"aid": analysis_id}).scalar_one()
        assert "ROUND25_WAIVER_INVALIDATED" in error
        event = c.execute(text("SELECT table_name,record_id,changed_fields,factory_id,operated_by FROM audit_logs WHERE action='DOC_GATE_WAIVER_INVALIDATED'" )).one()
        assert event.table_name == "capa_eightd"
        assert event.record_id == capa_id
        assert event.factory_id == factory_id
        assert event.operated_by == user_id
        assert event.changed_fields["decision_id"] == str(decision_id)
        assert event.changed_fields["revision"] == 1
        assert event.changed_fields["audit_run_id"] == str(audit_run_id)
        assert event.changed_fields["waiver_reason"] == "Round23 accepted"
        assert event.changed_fields["waiver_items"] == waiver_items
        assert event.changed_fields["old_decision"] == "passed"
        assert event.changed_fields["old_version_snapshot"] == version_snapshot
        assert event.changed_fields["old_no_affected_confirmed"] is False
    engine.dispose()


def test_round25_upgrade_widens_schema_local_alembic_version(mig_db_url):
    """Tenant successor records its long revision in the tenant version table."""
    schema = f"tenant_round25_{uuid.uuid4().hex[:8]}"
    engine = create_engine(_sync_url(mig_db_url))
    with engine.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
        c.execute(text(
            f'CREATE TABLE "{schema}".alembic_version '
            "(version_num VARCHAR(32) PRIMARY KEY)"
        ))
        c.execute(text(
            f'INSERT INTO "{schema}".alembic_version (version_num) '
            "VALUES ('20260715_waiver_items')"
        ))
        c.execute(text(
            f'CREATE TABLE "{schema}".capa_docg_analysis ('
            "analysis_id UUID PRIMARY KEY, capa_id UUID, factory_id UUID, "
            "is_current BOOLEAN, error TEXT)"
        ))
        c.execute(text(
            f'CREATE TABLE "{schema}".capa_docg_decision ('
            "decision_id UUID PRIMARY KEY, analysis_id UUID, audit_run_id UUID, "
            "revision INTEGER, factory_id UUID, decision VARCHAR(10), "
            "no_affected_confirmed BOOLEAN, version_snapshot JSONB, "
            "defer_reason TEXT, defer_owner UUID, defer_deadline DATE, "
            "waiver_reason TEXT, waiver_items JSONB, decided_by UUID, "
            "decided_at TIMESTAMPTZ)"
        ))
        c.execute(text(
            f'CREATE TABLE "{schema}".audit_logs ('
            "log_id UUID PRIMARY KEY, table_name VARCHAR(100), record_id UUID, "
            "action VARCHAR(50), changed_fields JSONB, operated_by UUID, "
            "factory_id UUID, operated_at TIMESTAMPTZ)"
        ))
    engine.dispose()

    cfg = _cfg(mig_db_url)
    cfg.cmd_opts = Namespace(x=[f"schema={schema}"])
    command.upgrade(cfg, "head")

    engine = create_engine(_sync_url(mig_db_url))
    with engine.connect() as c:
        revision = c.execute(text(
            f'SELECT version_num FROM "{schema}".alembic_version'
        )).scalar_one()
        max_length = c.execute(text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_schema=:schema AND table_name='alembic_version' "
            "AND column_name='version_num'"
        ), {"schema": schema}).scalar_one()
    engine.dispose()

    # Dual-branch successor of 20260715_waiver_items is the merge tip that
    # joins knowledge_entries + doc_gate_waiver_hardening (scar/knowledge bodies
    # no-op when CAPA tables are absent in this schema-local fixture).
    assert revision == "20260717_merge_knowledge_and_doc_gate"
    assert max_length == 64
