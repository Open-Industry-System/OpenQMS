import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine

REV = "20260721_capa_lateral_diffusion"
# Merge parent of both prior heads (knowledge/doc_gate + supplier_risk seed).
PARENT = "20260717_merge_knowledge_and_doc_gate"


def _cfg(mig_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url)
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def _sync_engine(mig_url: str):
    return create_engine(mig_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))


def test_lateral_diffusion_tables_created(mig_db_url):
    cfg = _cfg(mig_db_url)
    command.upgrade(cfg, PARENT)
    command.upgrade(cfg, REV)

    engine = _sync_engine(mig_db_url)
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
            )
        }
        assert "capa_lateral_diffusion_checks" in tables
        assert "capa_lateral_notifications" in tables
    engine.dispose()


def test_lateral_check_unique_capa(mig_db_url):
    import pytest

    cfg = _cfg(mig_db_url)
    command.upgrade(cfg, REV)

    engine = _sync_engine(mig_db_url)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                sa.text(
                    "INSERT INTO factories (id, code, name, is_active) "
                    "VALUES ('11111111-1111-1111-1111-111111111111', 'F-LAT', 'Lat Factory', true)"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO capa_eightd "
                    "(report_id, document_no, title, status, factory_id, product_line_code, severity, d1_team) "
                    "VALUES ('11111111-2222-3333-4444-555555555555', '8D-X', 't', 'D8_CLOSURE',"
                    "'11111111-1111-1111-1111-111111111111', 'PL', 'general', '[]'::jsonb)"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO capa_lateral_diffusion_checks "
                    "(check_id,capa_id,factory_id,source_product_line_code,"
                    "source_product_type_code,similar_products,status,llm_status,truncated) "
                    "VALUES ('00000000-0000-0000-0000-000000000001',"
                    "'11111111-2222-3333-4444-555555555555',"
                    "'11111111-1111-1111-1111-111111111111','PL','T','[]','done','done',false)"
                )
            )
    engine.dispose()

    engine = _sync_engine(mig_db_url)
    with pytest.raises(Exception):
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    sa.text(
                        "INSERT INTO capa_lateral_diffusion_checks "
                        "(check_id,capa_id,factory_id,source_product_line_code,"
                        "source_product_type_code,similar_products,status,llm_status,truncated) "
                        "VALUES ('00000000-0000-0000-0000-000000000002',"
                        "'11111111-2222-3333-4444-555555555555',"
                        "'11111111-1111-1111-1111-111111111111','PL','T','[]','done','done',false)"
                    )
                )
    engine.dispose()


def test_downgrade_removes_lateral_tables(mig_db_url):
    cfg = _cfg(mig_db_url)
    command.upgrade(cfg, REV)
    command.downgrade(cfg, PARENT)

    engine = _sync_engine(mig_db_url)
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
            )
        }
        assert "capa_lateral_diffusion_checks" not in tables
        assert "capa_lateral_notifications" not in tables
    engine.dispose()
