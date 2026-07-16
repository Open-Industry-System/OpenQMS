import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine

REV = "20260716_capa_scar_ref"
PARENT = "20260715_waiver_items"  # confirmed head on CAPA/doc-gate chain


def _cfg(mig_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url)
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def _indexes(conn) -> set[str]:
    rows = conn.execute(sa.text(
        "SELECT indexname FROM pg_indexes WHERE schemaname='public' "
        "AND indexname IN ('uq_capa_eightd_scar_ref_id','uq_supplier_scars_capa_ref_id')"
    )).fetchall()
    return {r[0] for r in rows}


import uuid

def _setup_legacy_data(conn):
    fid1 = str(uuid.uuid4())
    fid2 = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    role_id = conn.execute(sa.text("SELECT id FROM role_definitions LIMIT 1")).scalar()
    if role_id is None:
        role_id = str(uuid.uuid4())
        conn.execute(sa.text(f"INSERT INTO role_definitions (id, role_key, name_zh, name_en, is_system) VALUES ('{role_id}', 'test', 'test', 'test', true)"))

    conn.execute(sa.text(f"INSERT INTO factories (id, code, name) VALUES ('{fid1}', 'F1', 'F1'), ('{fid2}', 'F2', 'F2')"))
    conn.execute(sa.text(f"INSERT INTO users (user_id, username, password_hash, is_active, role_id, legacy_role, factory_id) VALUES ('{uid}', 'u1', 'x', true, '{role_id}', 'admin', '{fid1}')"))
    conn.execute(sa.text(f"INSERT INTO product_lines (code, name, factory_id) VALUES ('PL1', 'PL1', '{fid1}'), ('PL2', 'PL2', '{fid1}')"))
    conn.execute(sa.text(f"INSERT INTO suppliers (supplier_id, supplier_no, factory_id, name, short_name, created_by) VALUES ('{uid}', 'SUP1', '{fid1}', 'SUP1', 'S1', '{uid}')"))

    capa_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO capa_eightd (report_id, document_no, title, product_line_code, factory_id, status, severity, created_by, d1_team) "
        f"VALUES ('{capa_id}', 'C1', 'C1', 'PL1', '{fid1}', 'D3_INTERIM', 'serious', '{uid}', '[]')"
    ))

    scar_id = str(uuid.uuid4())
    conn.execute(sa.text(
        "INSERT INTO supplier_scars (scar_id, scar_no, factory_id, supplier_id, source_type, status, issued_by, product_line_code, capa_ref_id, description) "
        f"VALUES ('{scar_id}', 'S1', '{fid1}', '{uid}', 'manual', 'open', '{uid}', 'PL1', '{capa_id}', 'desc')"
    ))
    return capa_id, scar_id, fid1, fid2, uid

def test_upgrade_adds_column_indexes_and_backfills(mig_db_url):
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    command.upgrade(_cfg(mig_db_url), PARENT)
    with engine.connect() as conn:
        with conn.begin():
            capa_id, scar_id, _, _, _ = _setup_legacy_data(conn)
    engine.dispose()

    command.upgrade(_cfg(mig_db_url), REV)
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        col = conn.execute(sa.text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name='capa_eightd' AND column_name='scar_ref_id'"
        )).one_or_none()
        assert col is not None
        assert col[0] == "uuid" and col[1] == "YES"
        assert _indexes(conn) == {
            "uq_capa_eightd_scar_ref_id",
            "uq_supplier_scars_capa_ref_id",
        }
        backfill = conn.execute(sa.text(f"SELECT scar_ref_id FROM capa_eightd WHERE report_id='{capa_id}'")).scalar()
        assert str(backfill) == scar_id
    engine.dispose()


def test_downgrade_removes_column_and_indexes(mig_db_url):
    command.upgrade(_cfg(mig_db_url), REV)
    command.downgrade(_cfg(mig_db_url), PARENT)
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        col = conn.execute(sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='capa_eightd' AND column_name='scar_ref_id'"
        )).scalar()
        assert col is None
        assert _indexes(conn) == set()
    engine.dispose()


def test_upgrade_aborts_on_cross_factory_dirty_link(mig_db_url):
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    command.upgrade(_cfg(mig_db_url), PARENT)
    with engine.connect() as conn:
        with conn.begin():
            capa_id, scar_id, fid1, fid2, uid = _setup_legacy_data(conn)
            # Update SCAR to be in a different factory
            conn.execute(sa.text(f"UPDATE supplier_scars SET factory_id='{fid2}' WHERE scar_id='{scar_id}'"))
    engine.dispose()

    with pytest.raises(RuntimeError, match="cross-factory capa_ref_id"):
        command.upgrade(_cfg(mig_db_url), REV)


def test_upgrade_aborts_on_cross_pl_dirty_link(mig_db_url):
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    command.upgrade(_cfg(mig_db_url), PARENT)
    with engine.connect() as conn:
        with conn.begin():
            capa_id, scar_id, fid1, fid2, uid = _setup_legacy_data(conn)
            # Update SCAR to be in a different PL
            conn.execute(sa.text(f"UPDATE supplier_scars SET product_line_code='PL2' WHERE scar_id='{scar_id}'"))
    engine.dispose()

    with pytest.raises(RuntimeError, match="cross-PL capa_ref_id"):
        command.upgrade(_cfg(mig_db_url), REV)


def test_upgrade_aborts_on_duplicate_capa_ref_id(mig_db_url):
    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    command.upgrade(_cfg(mig_db_url), PARENT)
    with engine.connect() as conn:
        with conn.begin():
            capa_id, scar_id, fid1, fid2, uid = _setup_legacy_data(conn)
            scar2_id = str(uuid.uuid4())
            conn.execute(sa.text(
                "INSERT INTO supplier_scars (scar_id, scar_no, factory_id, supplier_id, source_type, status, issued_by, product_line_code, capa_ref_id, description) "
                f"VALUES ('{scar2_id}', 'S2', '{fid1}', '{uid}', 'manual', 'open', '{uid}', 'PL1', '{capa_id}', 'desc2')"
            ))
    engine.dispose()

    with pytest.raises(RuntimeError, match="duplicate capa_ref_id"):
        command.upgrade(_cfg(mig_db_url), REV)
