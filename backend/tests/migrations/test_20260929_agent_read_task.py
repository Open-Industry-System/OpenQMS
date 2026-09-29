"""Tenant migration contract for a single-report Agent read task."""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError


REV = "20260929_agent_read_task"
PARENT = "20260727_warranty_factory_id"
CAPABILITY = "capa.d4.summary.masked.v1"


def _cfg(mig_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url)
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def _engine(mig_url: str):
    return create_engine(mig_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))


def _seed_report(conn):
    factory_id, other_factory_id, user_id, report_id, role_id = (uuid.uuid4() for _ in range(5))
    conn.execute(sa.text(
        "INSERT INTO role_definitions (id, role_key, name_zh, name_en, is_system) "
        "VALUES (:id, 'agent_migration_test', 'test', 'test', true)"
    ), {"id": role_id})
    for fid, code in ((factory_id, "AGENT1"), (other_factory_id, "AGENT2")):
        conn.execute(sa.text("INSERT INTO factories (id, code, name) VALUES (:id, :code, :code)"),
                     {"id": fid, "code": code})
    conn.execute(sa.text(
        "INSERT INTO users (user_id, username, password_hash, is_active, role_id, legacy_role, factory_id) "
        "VALUES (:id, 'agent_migration_user', 'x', true, :role, 'admin', :factory)"
    ), {"id": user_id, "role": role_id, "factory": factory_id})
    conn.execute(sa.text("INSERT INTO product_lines (code, name, factory_id) VALUES ('AGENTPL', 'AGENTPL', :factory)"),
                 {"factory": factory_id})
    conn.execute(sa.text(
        "INSERT INTO capa_eightd "
        "(report_id, document_no, title, product_line_code, factory_id, status, severity, created_by, d1_team) "
        "VALUES (:id, 'AGENT-CAPA-1', 'test', 'AGENTPL', :factory, 'D3_INTERIM', 'serious', :user, '[]')"
    ), {"id": report_id, "factory": factory_id, "user": user_id})
    return user_id, report_id, factory_id, other_factory_id


def _task_values(user_id, report_id, factory_id):
    created_at = datetime.now(timezone.utc)
    return {
        "task_id": uuid.uuid4(), "initiator_user_id": user_id, "tenant_schema": "public",
        "capa_id": report_id, "factory_id": factory_id, "product_line_code": "AGENTPL",
        "capability_id": CAPABILITY, "status": "active",
        "expires_at": created_at + timedelta(hours=24), "created_at": created_at,
    }


INSERT = sa.text(
    "INSERT INTO agent_read_tasks "
    "(task_id, initiator_user_id, tenant_schema, capa_id, factory_id, product_line_code, "
    "capability_id, status, expires_at, created_at) "
    "VALUES (:task_id, :initiator_user_id, :tenant_schema, :capa_id, :factory_id, "
    ":product_line_code, :capability_id, :status, :expires_at, :created_at)"
)


def test_upgrade_creates_tenant_table_with_required_columns_and_indexes(mig_db_url):
    command.upgrade(_cfg(mig_db_url), REV)
    engine = _engine(mig_db_url)
    with engine.connect() as conn:
        columns = {c["name"]: c for c in sa.inspect(conn).get_columns("agent_read_tasks")}
        assert set(columns) == {
            "task_id", "initiator_user_id", "tenant_schema", "capa_id", "factory_id",
            "product_line_code", "capability_id", "status", "expires_at", "created_at", "revoked_at",
        }
        assert all(not col["nullable"] for name, col in columns.items() if name != "revoked_at")
        assert columns["revoked_at"]["nullable"]
        assert columns["task_id"]["type"].__class__.__name__ == "UUID"
        assert columns["tenant_schema"]["default"] is None
        assert {i["name"] for i in sa.inspect(conn).get_indexes("agent_read_tasks")} == {
            "ix_agent_read_tasks_initiator_status", "ix_agent_read_tasks_expires_at",
        }
        assert "agent_read_tasks" in sa.inspect(conn).get_table_names()
    engine.dispose()


def test_constraints_reject_invalid_task_and_cross_factory_report(mig_db_url):
    command.upgrade(_cfg(mig_db_url), REV)
    engine = _engine(mig_db_url)
    with engine.begin() as conn:
        user_id, report_id, factory_id, other_factory_id = _seed_report(conn)
        conn.execute(INSERT, _task_values(user_id, report_id, factory_id))

    bad_values = [
        {"factory_id": other_factory_id},
        {"capa_id": uuid.uuid4()},
        {"initiator_user_id": uuid.uuid4()},
        {"status": "expired"},
        {"capability_id": "capa.d4.full.v1"},
        {"expires_at": datetime(2000, 1, 1, tzinfo=timezone.utc)},
        {"tenant_schema": None},
    ]
    for bad in bad_values:
        values = _task_values(user_id, report_id, factory_id) | bad
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(INSERT, values)
    engine.dispose()


def test_downgrade_removes_only_task_table_and_indexes(mig_db_url):
    command.upgrade(_cfg(mig_db_url), REV)
    command.downgrade(_cfg(mig_db_url), PARENT)
    engine = _engine(mig_db_url)
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        assert "agent_read_tasks" not in inspector.get_table_names()
        assert "capa_eightd" in inspector.get_table_names()
        indexes = {row[0] for row in conn.execute(sa.text(
            "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND "
            "indexname IN ('ix_agent_read_tasks_initiator_status', 'ix_agent_read_tasks_expires_at')"
        ))}
        assert indexes == set()
    engine.dispose()
