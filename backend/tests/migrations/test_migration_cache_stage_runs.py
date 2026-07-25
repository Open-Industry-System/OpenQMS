import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pathlib import Path
from sqlalchemy import create_engine


def _cfg(mig_url: str) -> Config:
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    # env.py:50 优先读 DATABASE_URL env；mig_db_url fixture 已 monkeypatch setenv。
    return cfg


def test_stage_runs_column_added_and_removed(mig_db_url):
    """A3：upgrade 到 A3 rev → stage_runs 列存在；downgrade 到 A3 parent → 移除。"""
    command.upgrade(_cfg(mig_db_url), "20260709_capa_cache_stage_runs")

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        cols = [
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='recommendation_cache' AND column_name='stage_runs'"
                )
            )
        ]
        assert "stage_runs" in cols
    engine.dispose()

    command.downgrade(_cfg(mig_db_url), "20260708_capa_ppt_review_sk")

    engine = create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    with engine.connect() as conn:
        cols = [
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='recommendation_cache' AND column_name='stage_runs'"
                )
            )
        ]
        assert "stage_runs" not in cols
    engine.dispose()
