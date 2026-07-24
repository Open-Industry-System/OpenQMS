import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine


A3_HEAD = "20260709_capa_cache_stage_runs"
B1_REV = "20260709_conclusion_retrycount"


def _cfg(mig_url: str) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    return cfg


def test_migration_aborts_on_dirty_method_data(mig_db_url):
    """非法 method 行存在时 upgrade 抛 RuntimeError 且 method CHECK / conclusion 列 / d4_retry_count 列均未残留。"""
    command.upgrade(_cfg(mig_db_url), A3_HEAD)

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        conn.execute(sa.text(
            "INSERT INTO factories (id, code, name, is_active, created_at, updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000001', 'TEST', 'Test', true, now(), now())"))
        conn.execute(sa.text(
            "INSERT INTO capa_eightd (report_id, document_no, title, product_line_code, status, severity, "
            " factory_id, d1_team, d2_description, d3_interim, d4_root_cause, d5_correction, d6_verification, "
            " d7_prevention, d8_closure, due_date, created_at, updated_at) "
            "VALUES (gen_random_uuid(), '8D-TEST-001', 't', 'PL', 'D4_ROOT_CAUSE', '一般', "
            " '00000000-0000-0000-0000-000000000001', '[]'::jsonb, '', '', '', '', '', '', '', NULL, now(), now())"))
        conn.execute(sa.text(
            "INSERT INTO capa_root_cause_verification "
            "(verification_id, capa_id, factory_id, root_cause_text, is_verified, "
            " method, result, evidence_attachments, source_ref, created_at, updated_at) "
            "SELECT gen_random_uuid(), report_id, factory_id, 'rc', false, 'guess', NULL, '[]'::jsonb, NULL, now(), now() "
            "FROM capa_eightd WHERE document_no='8D-TEST-001'"
        ))
        conn.commit()
    engine.dispose()

    import pytest
    with pytest.raises(RuntimeError, match="non-enum method"):
        command.upgrade(_cfg(mig_db_url), "head")

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        cols_v = [r[0] for r in conn.execute(sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='capa_root_cause_verification'"))]
        assert "conclusion" not in cols_v
        cols_e = [r[0] for r in conn.execute(sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='capa_eightd'"))]
        assert "d4_retry_count" not in cols_e
        cons = [r[0] for r in conn.execute(sa.text(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'capa_root_cause_verification'::regclass"))]
        assert "chk_verification_method" not in cons
        assert "chk_verification_conclusion" not in cons
    engine.dispose()


def test_backfill_passed_to_conclusion(mig_db_url):
    """CASE-WHEN IS_VERIFIED THEN 'passed' ELSE 'pending' — 映射结果正确。"""
    # 1) 升到 A3_HEAD：有 is_verified，无 conclusion
    command.upgrade(_cfg(mig_db_url), A3_HEAD)

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        conn.execute(sa.text(
            "INSERT INTO factories (id, code, name, is_active, created_at, updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000001', 'TEST', 'Test', true, now(), now())"))
        conn.execute(sa.text(
            "INSERT INTO capa_eightd (report_id, document_no, title, product_line_code, status, severity, "
            " factory_id, d1_team, d2_description, d3_interim, d4_root_cause, d5_correction, d6_verification, "
            " d7_prevention, d8_closure, due_date, created_at, updated_at) "
            "VALUES (gen_random_uuid(), '8D-BF-001', 't', 'PL', 'D4_ROOT_CAUSE', '一般', "
            " '00000000-0000-0000-0000-000000000001', '[]'::jsonb, '', '', '', '', '', '', '', NULL, now(), now())"))
        conn.execute(sa.text(
            "INSERT INTO capa_root_cause_verification "
            "(verification_id, capa_id, factory_id, root_cause_text, is_verified, "
            " method, result, evidence_attachments, source_ref, created_at, updated_at) "
            "SELECT gen_random_uuid(), report_id, factory_id, 'passed-row', true, NULL, "
            " 'data ok', '[]'::jsonb, NULL, now(), now() "
            "FROM capa_eightd WHERE document_no='8D-BF-001'"))
        conn.execute(sa.text(
            "INSERT INTO capa_root_cause_verification "
            "(verification_id, capa_id, factory_id, root_cause_text, is_verified, "
            " method, result, evidence_attachments, source_ref, created_at, updated_at) "
            "SELECT gen_random_uuid(), report_id, factory_id, 'failed-row', false, NULL, "
            " NULL, '[]'::jsonb, NULL, now(), now() "
            "FROM capa_eightd WHERE document_no='8D-BF-001'"))
        conn.commit()
    engine.dispose()

    # 2) 升到 B1_REV — 执行 backfill
    command.upgrade(_cfg(mig_db_url), B1_REV)

    # 3) 断言映射结果
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        row = conn.execute(sa.text(
            "SELECT conclusion FROM capa_root_cause_verification "
            "WHERE root_cause_text='passed-row'")).one()
        assert row[0] == "passed", f"expected 'passed' for is_verified=true, got {row[0]!r}"

        row = conn.execute(sa.text(
            "SELECT conclusion FROM capa_root_cause_verification "
            "WHERE root_cause_text='failed-row'")).one()
        assert row[0] == "pending", f"expected 'pending' for is_verified=false, got {row[0]!r}"
    engine.dispose()


def test_migration_clean_upgrade_downgrade(mig_db_url):
    """无脏数据时 upgrade B1 新增结论列、method/conclusion CHECK、d4_retry_count；downgrade 回 A3 全部移除。"""
    command.upgrade(_cfg(mig_db_url), B1_REV)

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        cols_v = [r[0] for r in conn.execute(sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='capa_root_cause_verification'"))]
        assert "conclusion" in cols_v
        cols_e = [r[0] for r in conn.execute(sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='capa_eightd'"))]
        assert "d4_retry_count" in cols_e
        cons = [r[0] for r in conn.execute(sa.text(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'capa_root_cause_verification'::regclass"))]
        assert "chk_verification_method" in cons
        assert "chk_verification_conclusion" in cons
    engine.dispose()

    command.downgrade(_cfg(mig_db_url), A3_HEAD)

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        cols_v = [r[0] for r in conn.execute(sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='capa_root_cause_verification'"))]
        assert "conclusion" not in cols_v
        cols_e = [r[0] for r in conn.execute(sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='capa_eightd'"))]
        assert "d4_retry_count" not in cols_e
        cons = [r[0] for r in conn.execute(sa.text(
            "SELECT conname FROM pg_constraint WHERE conrelid = 'capa_root_cause_verification'::regclass"))]
        assert "chk_verification_method" not in cons
        assert "chk_verification_conclusion" not in cons
    engine.dispose()
