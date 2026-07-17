import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine

REV = "20260716_knowledge_entries"
PARENT = "20260716_capa_scar_ref"  # CAPA/scar chain tip (sibling of doc_gate_waiver_hardening)


def _cfg(mig_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url)
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def _sync_engine(mig_url: str):
    return create_engine(mig_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))


def test_upgrade_raises_when_factories_missing(mig_db_url):
    """Missing factories must raise — never stamp incomplete schema."""
    import pytest

    cfg = _cfg(mig_db_url)
    command.upgrade(cfg, PARENT)
    engine = _sync_engine(mig_db_url)
    with engine.connect() as conn:
        with conn.begin():
            # Drop factories CASCADE may remove FKs; the migration must still fail closed.
            conn.execute(sa.text("DROP TABLE IF EXISTS factories CASCADE"))
    engine.dispose()

    with pytest.raises(RuntimeError, match="factories"):
        command.upgrade(cfg, REV)

    engine = _sync_engine(mig_db_url)
    with engine.connect() as conn:
        rev = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert rev == PARENT
    engine.dispose()


def test_knowledge_entries_table_and_outbox_hash(mig_db_url):
    cfg = _cfg(mig_db_url)
    command.upgrade(cfg, PARENT)
    command.upgrade(cfg, REV)

    engine = _sync_engine(mig_db_url)
    with engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='knowledge_entries'"
                )
            )
        }
        assert "entry_id" in cols and "content_hash" in cols and "embedding_status" in cols
        assert "embedding_id" in cols
        assert "document_no" in cols and "fields" in cols and "llm_status" in cols

        doc_no = conn.execute(
            sa.text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name='knowledge_entries' AND column_name='document_no'"
            )
        ).scalar()
        assert doc_no == 50

        ob = conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='embedding_sync_outbox' AND column_name='content_hash'"
            )
        ).scalar()
        assert ob == "content_hash"

        uq = conn.execute(
            sa.text(
                "SELECT 1 FROM pg_indexes WHERE indexdef ILIKE '%source_type%' "
                "AND indexdef ILIKE '%source_id%' AND tablename='knowledge_entries'"
            )
        ).scalar()
        assert uq == 1

        # CHECK constraints present
        checks = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'knowledge_entries'::regclass AND contype = 'c'"
                )
            )
        }
        assert any("status" in c for c in checks)
        assert any("embedding_status" in c for c in checks)

        # list / recommend indexes
        idx_defs = [
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT indexdef FROM pg_indexes WHERE tablename='knowledge_entries'"
                )
            )
        ]
        assert any(
            "factory_id" in d and "product_line_code" in d and "status" in d for d in idx_defs
        )
        assert any(
            "factory_id" in d
            and "product_line_code" in d
            and "embedding_status" in d
            for d in idx_defs
        )
    engine.dispose()


def test_downgrade_removes_knowledge_entries_and_outbox_hash(mig_db_url):
    cfg = _cfg(mig_db_url)
    command.upgrade(cfg, REV)
    command.downgrade(cfg, PARENT)

    engine = _sync_engine(mig_db_url)
    with engine.connect() as conn:
        table = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name='knowledge_entries'"
            )
        ).scalar()
        assert table is None

        ob = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='embedding_sync_outbox' AND column_name='content_hash'"
            )
        ).scalar()
        assert ob is None
    engine.dispose()
