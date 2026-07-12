"""D3 Containment 7-table migration tests (Task 1: ORM + migration + tests)

Tests verify:
- All 7 tables created with correct columns
- Partial unique indexes (is_current, status='running')
- Comprehensive CHECK constraints
- Composite foreign keys for factory consistency
- Unique constraints for composite FK parent references
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
    return cfg


def _sync_url(mig_url: str) -> str:
    return mig_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


# ===== Fixtures =====


@pytest.fixture
def e2e_user_id(mig_db_url):
    """Create a test user and return its UUID. Runs migrations first."""
    # Run migrations to create users table
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))
    user_id = uuid.uuid4()
    role_id = uuid.uuid4()
    with engine.begin() as c:
        # Create a role first (required for user.role_id FK)
        c.execute(text(
            "INSERT INTO role_definitions (id, role_key, name_zh, name_en, description, is_system, is_editable, is_active, created_at) "
            "VALUES (:rid, 'test_role', '测试角色', 'Test Role', 'Test role for D3 migration tests', false, true, true, now())"
        ), {"rid": role_id})
        # Create user with role_id
        c.execute(text(
            "INSERT INTO users (user_id, username, password_hash, display_name, email, role_id, legacy_role, is_active, created_at) "
            "VALUES (:uid, 'test_d3_user', 'hash', 'Test D3 User', 'test@example.com', :rid, 'viewer', true, now())"
        ), {"uid": user_id, "rid": role_id})
    engine.dispose()
    yield user_id
    # Cleanup handled by DB drop


@pytest.fixture
def capa_e2e_factory_with_user(mig_db_url, e2e_user_id):
    """Create factory + CAPA + user, return (capa_id, factory_id, user_id)."""
    engine = create_engine(_sync_url(mig_db_url))
    factory_id = uuid.uuid4()
    capa_id = uuid.uuid4()

    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO factories (id, code, name, is_active, created_at, updated_at) "
            "VALUES (:fid, 'FAC-D3', 'D3 Test Factory', true, now(), now())"
        ), {"fid": factory_id})
        c.execute(text(
            "INSERT INTO capa_eightd (report_id, document_no, title, product_line_code, status, severity, "
            "factory_id, d1_team, created_at, updated_at) "
            "VALUES (:cid, '8D-D3-001', 'D3 Test CAPA', 'DC-DC-100', 'D3_INTERIM', 'general', "
            ":fid, '[]'::jsonb, now(), now())"
        ), {"cid": capa_id, "fid": factory_id})

    engine.dispose()
    yield capa_id, factory_id, e2e_user_id


@pytest.fixture
def capa_e2e_with_run_and_user(mig_db_url, capa_e2e_factory_with_user):
    """Create import run + return (run_id, factory_id, user_id)."""
    capa_id, factory_id, user_id = capa_e2e_factory_with_user
    engine = create_engine(_sync_url(mig_db_url))
    run_id = uuid.uuid4()

    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO capa_d3_import_run (run_id, capa_id, factory_id, is_current, status, "
            "imported_types, analysis_context, imported_by, started_at, completed_at, created_at) "
            "VALUES (:rid, :cid, :fid, true, 'completed', '[]'::jsonb, "
            "'{\"capa_severity\":\"general\",\"risk_mapping_version\":\"v1\"}'::jsonb, "
            ":uid, now(), now(), now())"
        ), {"rid": run_id, "cid": capa_id, "fid": factory_id, "uid": user_id})

    engine.dispose()
    yield run_id, factory_id, user_id


@pytest.fixture
def capa_e2e_with_done_report_and_user(mig_db_url, capa_e2e_with_run_and_user):
    """Create done report + return (report_id, factory_id, user_id)."""
    run_id, factory_id, user_id = capa_e2e_with_run_and_user
    engine = create_engine(_sync_url(mig_db_url))
    report_id = uuid.uuid4()

    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO capa_d3_impact_report (report_id, run_id, factory_id, is_current, status, "
            "attempt_token, batches, impact_qty, customer_impact, time_window, risk_level, risk_floor, "
            "risk_explanation, llm_available, generated_by, started_at, completed_at, created_at) "
            "VALUES (:rid, :run_id, :fid, true, 'done', gen_random_uuid(), "
            "'[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, 'high', 'high', 'test explanation', "
            "true, :uid, now(), now(), now())"
        ), {"rid": report_id, "run_id": run_id, "fid": factory_id, "uid": user_id})

    engine.dispose()
    yield report_id, factory_id, user_id


@pytest.fixture
def capa_e2e_with_advice_and_user(mig_db_url, capa_e2e_with_done_report_and_user):
    """Create advice generation + advice + return (advice_id, factory_id, user_id)."""
    report_id, factory_id, user_id = capa_e2e_with_done_report_and_user
    engine = create_engine(_sync_url(mig_db_url))
    generation_id = uuid.uuid4()
    advice_id = uuid.uuid4()

    with engine.begin() as c:
        # Create advice_generation
        c.execute(text(
            "INSERT INTO capa_d3_advice_generation (generation_id, report_id, factory_id, is_current, "
            "advice_count, rejected_advice_count, stage_runs, status, attempt_token, llm_available, "
            "generated_by, started_at, completed_at, created_at) "
            "VALUES (:gid, :rid, :fid, true, 1, 0, '[]'::jsonb, 'done', gen_random_uuid(), true, "
            ":uid, now(), now(), now())"
        ), {"gid": generation_id, "rid": report_id, "fid": factory_id, "uid": user_id})

        # Create advice
        c.execute(text(
            "INSERT INTO capa_d3_ai_advice (advice_id, generation_id, factory_id, advice_type, "
            "advice_text, source_provenance, llm_available, generated_by, generated_at, created_at) "
            "VALUES (:aid, :gid, :fid, 'recall', 'test advice', "
            "'[{\"snapshot_id\": null, \"record_key\": \"test\", \"source_type\": \"report\", \"stage\": \"llm_advice\"}]'::jsonb, "
            "true, :uid, now(), now())"
        ), {"aid": advice_id, "gid": generation_id, "fid": factory_id, "uid": user_id})

    engine.dispose()
    yield advice_id, factory_id, user_id


@pytest.fixture
def capa_e2e_two_factories_with_user(mig_db_url, e2e_user_id):
    """Create two factories + run in factory_a, return (run_id, factory_a, factory_b, user_id)."""
    engine = create_engine(_sync_url(mig_db_url))
    factory_a = uuid.uuid4()
    factory_b = uuid.uuid4()
    capa_id = uuid.uuid4()
    run_id = uuid.uuid4()

    with engine.begin() as c:
        # Create two factories
        c.execute(text(
            "INSERT INTO factories (id, code, name, is_active, created_at, updated_at) "
            "VALUES (:fid, 'FAC-A', 'Factory A', true, now(), now())"
        ), {"fid": factory_a})
        c.execute(text(
            "INSERT INTO factories (id, code, name, is_active, created_at, updated_at) "
            "VALUES (:fid, 'FAC-B', 'Factory B', true, now(), now())"
        ), {"fid": factory_b})

        # Create CAPA in factory_a
        c.execute(text(
            "INSERT INTO capa_eightd (report_id, document_no, title, product_line_code, status, severity, "
            "factory_id, d1_team, created_at, updated_at) "
            "VALUES (:cid, '8D-D3-002', 'D3 Cross-Factory Test', 'DC-DC-100', 'D3_INTERIM', 'general', "
            ":fid, '[]'::jsonb, now(), now())"
        ), {"cid": capa_id, "fid": factory_a})

        # Create run in factory_a
        c.execute(text(
            "INSERT INTO capa_d3_import_run (run_id, capa_id, factory_id, is_current, status, "
            "imported_types, analysis_context, imported_by, started_at, completed_at, created_at) "
            "VALUES (:rid, :cid, :fid, true, 'completed', '[]'::jsonb, "
            "'{\"capa_severity\":\"general\",\"risk_mapping_version\":\"v1\"}'::jsonb, "
            ":uid, now(), now(), now())"
        ), {"rid": run_id, "cid": capa_id, "fid": factory_a, "uid": e2e_user_id})

    engine.dispose()
    yield run_id, factory_a, factory_b, e2e_user_id


# ===== Table Existence Tests =====


def test_d3_tables_created(mig_db_url):
    """All 7 D3 containment tables created."""
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name LIKE 'capa_d3_%' ORDER BY table_name"
        )).fetchall()

    engine.dispose()
    assert {r[0] for r in rows} == {
        "capa_d3_import_run",
        "capa_d3_containment_snapshot",
        "capa_d3_impact_report",
        "capa_d3_advice_generation",
        "capa_d3_ai_advice",
        "capa_d3_advice_adoption",
        "capa_d3_execution",
    }


# ===== Import Run Tests =====


def test_import_run_partial_uq_rejects_two_current(mig_db_url, capa_e2e_factory_with_user):
    """Partial UQ(capa_id WHERE is_current=true) rejects second current run."""
    capa_id, factory_id, user_id = capa_e2e_factory_with_user
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))
    with engine.begin() as c:
        # First current run
        c.execute(text(
            "INSERT INTO capa_d3_import_run (run_id, capa_id, factory_id, is_current, status, "
            "imported_types, analysis_context, imported_by, started_at, completed_at, created_at) "
            "VALUES (gen_random_uuid(), :capa, :fac, true, 'completed', '[]'::jsonb, "
            "'{\"capa_severity\":\"general\",\"risk_mapping_version\":\"v1\"}'::jsonb, "
            ":uid, now(), now(), now())"
        ), {"capa": capa_id, "fac": factory_id, "uid": user_id})

    # Second current run should fail
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_import_run (run_id, capa_id, factory_id, is_current, status, "
                "imported_types, analysis_context, imported_by, started_at, completed_at, created_at) "
                "VALUES (gen_random_uuid(), :capa, :fac, true, 'completed', '[]'::jsonb, "
                "'{\"capa_severity\":\"general\",\"risk_mapping_version\":\"v1\"}'::jsonb, "
                ":uid, now(), now(), now())"
            ), {"capa": capa_id, "fac": factory_id, "uid": user_id})

    engine.dispose()


def test_import_run_check_current_requires_completed(mig_db_url, capa_e2e_factory_with_user):
    """CHECK: is_current=true requires status='completed' AND completed_at IS NOT NULL."""
    capa_id, factory_id, user_id = capa_e2e_factory_with_user
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))

    # is_current=true with status='importing' should fail
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_import_run (run_id, capa_id, factory_id, is_current, status, "
                "imported_types, analysis_context, imported_by, started_at, created_at) "
                "VALUES (gen_random_uuid(), :capa, :fac, true, 'importing', '[]'::jsonb, "
                "'{\"capa_severity\":\"general\",\"risk_mapping_version\":\"v1\"}'::jsonb, "
                ":uid, now(), now())"
            ), {"capa": capa_id, "fac": factory_id, "uid": user_id})

    engine.dispose()


# ===== Impact Report Tests =====


def test_report_done_check_requires_risk_explanation_and_llm(mig_db_url, capa_e2e_with_run_and_user):
    """CHECK: status='done' requires risk_explanation NOT NULL AND llm_available=true."""
    run_id, factory_id, user_id = capa_e2e_with_run_and_user
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))

    # risk_explanation NULL should fail
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_impact_report (report_id, run_id, factory_id, is_current, status, "
                "attempt_token, batches, impact_qty, customer_impact, time_window, risk_level, risk_floor, "
                "risk_explanation, llm_available, generated_by, started_at, completed_at, created_at) "
                "VALUES (gen_random_uuid(), :run, :fac, false, 'done', gen_random_uuid(), "
                "'[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, 'high', 'high', NULL, true, "
                ":uid, now(), now(), now())"
            ), {"run": run_id, "fac": factory_id, "uid": user_id})

    # llm_available=false should fail
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_impact_report (report_id, run_id, factory_id, is_current, status, "
                "attempt_token, batches, impact_qty, customer_impact, time_window, risk_level, risk_floor, "
                "risk_explanation, llm_available, generated_by, started_at, completed_at, created_at) "
                "VALUES (gen_random_uuid(), :run, :fac, false, 'done', gen_random_uuid(), "
                "'[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, 'high', 'high', 'explanation', false, "
                ":uid, now(), now(), now())"
            ), {"run": run_id, "fac": factory_id, "uid": user_id})

    engine.dispose()


# ===== Advice Generation Tests =====


def test_advice_generation_done_requires_advice_count_and_llm(mig_db_url, capa_e2e_with_done_report_and_user):
    """CHECK: status='done' requires advice_count>0 AND llm_available=true."""
    report_id, factory_id, user_id = capa_e2e_with_done_report_and_user
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))

    # advice_count=0 should fail
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_advice_generation (generation_id, report_id, factory_id, is_current, "
                "advice_count, rejected_advice_count, stage_runs, status, attempt_token, llm_available, "
                "generated_by, started_at, completed_at, created_at) "
                "VALUES (gen_random_uuid(), :rep, :fac, false, 0, 0, '[]'::jsonb, 'done', "
                "gen_random_uuid(), true, :uid, now(), now(), now())"
            ), {"rep": report_id, "fac": factory_id, "uid": user_id})

    # llm_available=false should fail
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_advice_generation (generation_id, report_id, factory_id, is_current, "
                "advice_count, rejected_advice_count, stage_runs, status, attempt_token, llm_available, "
                "generated_by, started_at, completed_at, created_at) "
                "VALUES (gen_random_uuid(), :rep, :fac, false, 1, 0, '[]'::jsonb, 'done', "
                "gen_random_uuid(), false, :uid, now(), now(), now())"
            ), {"rep": report_id, "fac": factory_id, "uid": user_id})

    engine.dispose()


# ===== Execution Tests =====


def test_execution_check_manual_requires_null_advice(mig_db_url, capa_e2e_with_done_report_and_user):
    """CHECK: source='manual' requires generation_id IS NULL AND advice_id IS NULL."""
    report_id, factory_id, user_id = capa_e2e_with_done_report_and_user
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))

    # source='manual' with advice_id should fail
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_execution (execution_id, report_id, factory_id, advice_id, "
                "generation_id, source, measure_text, result_status, evidence_refs, "
                "executed_by, executed_at, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :rep, :fac, gen_random_uuid(), NULL, 'manual', 't', "
                "'in_progress', '[]'::jsonb, :uid, now(), now(), now())"
            ), {"rep": report_id, "fac": factory_id, "uid": user_id})

    engine.dispose()


def test_execution_composite_fk_rejects_cross_report_generation(mig_db_url, capa_e2e_with_advice_and_user):
    """P0: Composite FK (generation_id, report_id, factory_id) rejects execution whose
    generation belongs to report_A but execution.report_id is report_B (same factory)."""
    advice_id, factory_id, user_id = capa_e2e_with_advice_and_user
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))

    # Fetch the original report_id + run_id from the existing generation
    with engine.connect() as c:
        gen_row = c.execute(text(
            "SELECT g.generation_id, g.report_id, r.run_id "
            "FROM capa_d3_advice_generation g "
            "JOIN capa_d3_impact_report r ON g.report_id = r.report_id LIMIT 1"
        )).fetchone()
    gen_id = gen_row[0]
    orig_report_id = gen_row[1]
    run_id = gen_row[2]

    # Create a SECOND done report in the same run/factory (different report_id)
    second_report_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO capa_d3_impact_report (report_id, run_id, factory_id, is_current, status, "
            "attempt_token, batches, impact_qty, customer_impact, time_window, risk_level, risk_floor, "
            "risk_explanation, llm_available, generated_by, started_at, completed_at, created_at) "
            "VALUES (:rid, :run_id, :fid, false, 'done', gen_random_uuid(), '[]'::jsonb, '[]'::jsonb, "
            "'[]'::jsonb, '{}'::jsonb, 'high', 'high', 'x', true, :uid, now(), now(), now())"
        ), {"rid": second_report_id, "run_id": run_id, "fid": factory_id, "uid": user_id})

    assert orig_report_id != second_report_id

    # Execution with generation from report_A but report_id = report_B → composite FK violation
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_execution (execution_id, report_id, factory_id, advice_id, "
                "generation_id, source, measure_text, result_status, evidence_refs, "
                "executed_by, executed_at, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :second_rep, :fac, :adv, :gen, 'adopted', 't', "
                "'in_progress', '[]'::jsonb, :uid, now(), now(), now())"
            ), {"second_rep": second_report_id, "fac": factory_id, "adv": advice_id,
                "gen": gen_id, "uid": user_id})

    engine.dispose()


def test_execution_composite_fk_rejects_cross_generation_advice(mig_db_url, capa_e2e_with_advice_and_user):
    """P0: Composite FK (advice_id, generation_id, factory_id) rejects execution whose
    advice belongs to generation_A but execution.generation_id is generation_B (same factory)."""
    advice_id, factory_id, user_id = capa_e2e_with_advice_and_user
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))

    # Fetch original report_id + generation_id
    with engine.connect() as c:
        gen_row = c.execute(text(
            "SELECT generation_id, report_id FROM capa_d3_advice_generation LIMIT 1"
        )).fetchone()
    orig_gen_id = gen_row[0]
    orig_report_id = gen_row[1]

    # Create a SECOND advice_generation (same report, different generation_id)
    second_gen_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO capa_d3_advice_generation (generation_id, report_id, factory_id, is_current, "
            "advice_count, rejected_advice_count, stage_runs, status, attempt_token, llm_available, "
            "generated_by, started_at, completed_at, created_at) "
            "VALUES (:gid, :rid, :fid, false, 1, 0, '[]'::jsonb, 'done', gen_random_uuid(), true, "
            ":uid, now(), now(), now())"
        ), {"gid": second_gen_id, "rid": orig_report_id, "fid": factory_id, "uid": user_id})

    # Execution with advice from gen_A but generation_id = gen_B → composite FK violation
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_execution (execution_id, report_id, factory_id, advice_id, "
                "generation_id, source, measure_text, result_status, evidence_refs, "
                "executed_by, executed_at, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :rep, :fac, :adv, :second_gen, 'adopted', 't', "
                "'in_progress', '[]'::jsonb, :uid, now(), now(), now())"
            ), {"rep": orig_report_id, "fac": factory_id, "adv": advice_id,
                "second_gen": second_gen_id, "uid": user_id})

    engine.dispose()


# ===== Adoption Tests =====


def test_adoption_uq_advice_id_single_decision(mig_db_url, capa_e2e_with_advice_and_user):
    """UQ(advice_id) allows only one adoption per advice."""
    advice_id, factory_id, user_id = capa_e2e_with_advice_and_user
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))

    # First adoption
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO capa_d3_advice_adoption (adoption_id, advice_id, factory_id, decision, "
            "adopted_text, advice_type, source_provenance, decided_by, decided_at, created_at) "
            "VALUES (gen_random_uuid(), :adv, :fac, 'adopted', 'adopted text', 'recall', "
            "'[]'::jsonb, :uid, now(), now())"
        ), {"adv": advice_id, "fac": factory_id, "uid": user_id})

    # Second adoption for same advice_id should fail
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_advice_adoption (adoption_id, advice_id, factory_id, decision, "
                "adopted_text, advice_type, source_provenance, decided_by, decided_at, created_at) "
                "VALUES (gen_random_uuid(), :adv, :fac, 'adopted', 'another text', 'recall', "
                "'[]'::jsonb, :uid, now(), now())"
            ), {"adv": advice_id, "fac": factory_id, "uid": user_id})

    engine.dispose()


def test_adoption_check_rejected_requires_null_text(mig_db_url, capa_e2e_with_advice_and_user):
    """CHECK: decision='rejected' requires adopted_text IS NULL."""
    advice_id, factory_id, user_id = capa_e2e_with_advice_and_user
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))

    # rejected with adopted_text should fail
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_advice_adoption (adoption_id, advice_id, factory_id, decision, "
                "adopted_text, advice_type, source_provenance, decided_by, decided_at, created_at) "
                "VALUES (gen_random_uuid(), :adv, :fac, 'rejected', 'should be null', 'recall', "
                "'[]'::jsonb, :uid, now(), now())"
            ), {"adv": advice_id, "fac": factory_id, "uid": user_id})

    engine.dispose()


# ===== Composite FK Tests =====


def test_composite_fk_rejects_cross_factory_snapshot(mig_db_url, capa_e2e_two_factories_with_user):
    """Composite FK(run_id, factory_id) rejects snapshot with different factory_id than run."""
    run_id, factory_a, factory_b, user_id = capa_e2e_two_factories_with_user
    command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(_sync_url(mig_db_url))

    # Snapshot in factory_b but run is in factory_a should fail
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO capa_d3_containment_snapshot (snapshot_id, run_id, factory_id, "
                "snapshot_type, payload, source_query, record_count, imported_by, imported_at, created_at) "
                "VALUES (gen_random_uuid(), :run, :facb, 'inventory', '[]'::jsonb, '{}'::jsonb, 0, "
                ":uid, now(), now())"
            ), {"run": run_id, "facb": factory_b, "uid": user_id})

    engine.dispose()
