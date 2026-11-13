"""Real PostgreSQL upgrades from both published heads and an empty database."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

MERGE = "20261102_agent_mainline_merge"


def _config(url):
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.mark.parametrize("predecessor", [
    None, "20260929_agent_read_task", "20261009_agent_task_attachments",
], ids=["empty", "main-head", "runtime-head"])
def test_merge_upgrade_preserves_both_agent_table_families(mig_db_url, predecessor):
    config = _config(mig_db_url)
    if predecessor is not None:
        command.upgrade(config, predecessor)
    command.upgrade(config, "head")
    engine = sa.create_engine(mig_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    try:
        with engine.connect() as connection:
            assert connection.scalars(sa.text("SELECT version_num FROM public.alembic_version")).all() == ["20261113_d4_recovery"]
            inspector = sa.inspect(connection)
            tables = set(inspector.get_table_names(schema="public"))
            assert {
                "agent_read_tasks", "agent_tasks", "agent_runs", "agent_task_grants",
                "agent_task_messages", "agent_plugin_installations", "agent_plugin_grants",
                "agent_task_attachments", "tenant_attachment_storage_disposals",
            } <= tables
            assert any(
                fk["constrained_columns"] == ["capa_id", "factory_id"]
                and fk["referred_table"] == "capa_eightd"
                and fk["referred_columns"] == ["report_id", "factory_id"]
                for fk in inspector.get_foreign_keys("agent_read_tasks", schema="public")
            )
            assert {item["name"] for item in inspector.get_indexes("agent_read_tasks", schema="public")} == {
                "ix_agent_read_tasks_initiator_status", "ix_agent_read_tasks_expires_at",
            }
            assert {item["name"] for item in inspector.get_check_constraints("agent_read_tasks", schema="public")} == {
                "ck_agent_read_task_status", "ck_agent_read_task_capability", "ck_agent_read_task_expiry",
            }
    finally:
        engine.dispose()
