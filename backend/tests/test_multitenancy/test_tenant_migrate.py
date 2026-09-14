"""Pure orchestration and SQL-compilation tests for tenant migration CLI."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.cli import tenant_migrate


class FakeSession:
    def __init__(self, statements: list[object]):
        self.statements = statements
        self.commits = 0

    async def execute(self, statement):
        self.statements.append(statement)

    async def commit(self):
        self.commits += 1


def _session_factory(statements: list[object], sessions: list[FakeSession]):
    @asynccontextmanager
    async def factory():
        session = FakeSession(statements)
        sessions.append(session)
        yield session

    return factory


def _compiled(statement) -> tuple[str, dict[str, object]]:
    compiled = statement.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


@pytest.mark.asyncio
async def test_bookkeeping_rerun_uses_same_race_safe_upsert(monkeypatch):
    tenant_id = uuid.uuid4()
    statements: list[object] = []
    sessions: list[FakeSession] = []
    monkeypatch.setattr(
        tenant_migrate,
        "async_session",
        _session_factory(statements, sessions),
    )

    await tenant_migrate.record_migration_result(tenant_id, success=True)
    await tenant_migrate.record_migration_result(tenant_id, success=True)

    upserts = [statement for statement in statements if not hasattr(statement, "text")]
    assert len(upserts) == 2
    for statement in upserts:
        sql, params = _compiled(statement)
        assert "ON CONFLICT (tenant_id, version) DO UPDATE" in sql
        assert "updated_at" not in sql
        assert params["tenant_id"] == tenant_id
        assert params["version"] == "tenant@head"
        assert params["status"] == "completed"
    assert [session.commits for session in sessions] == [1, 1]


@pytest.mark.asyncio
async def test_main_attempts_later_tenants_records_every_status_then_fails(monkeypatch):
    tenants = [
        SimpleNamespace(id=uuid.uuid4(), slug="first", schema_name="tenant_first"),
        SimpleNamespace(id=uuid.uuid4(), slug="second", schema_name="tenant_second"),
        SimpleNamespace(id=uuid.uuid4(), slug="third", schema_name="tenant_third"),
    ]
    attempted: list[str] = []
    statements: list[object] = []
    sessions: list[FakeSession] = []

    async def active(_slug=None):
        return tenants

    def migrate(schema_name: str) -> bool:
        attempted.append(schema_name)
        return schema_name != "tenant_first"

    monkeypatch.setattr(tenant_migrate, "get_active_tenants", active)
    monkeypatch.setattr(tenant_migrate, "run_alembic_upgrade", migrate)
    monkeypatch.setattr(
        tenant_migrate,
        "async_session",
        _session_factory(statements, sessions),
    )

    with pytest.raises(tenant_migrate.TenantMigrationError, match="1 tenant migration"):
        await tenant_migrate.main(all_tenants=True)

    assert attempted == ["tenant_first", "tenant_second", "tenant_third"]
    upserts = [statement for statement in statements if not hasattr(statement, "text")]
    statuses = [_compiled(statement)[1]["status"] for statement in upserts]
    assert statuses == ["failed", "completed", "completed"]
    assert [session.commits for session in sessions] == [1, 1, 1]


@pytest.mark.asyncio
async def test_alembic_exception_is_sanitized_recorded_and_does_not_stop_later_tenants(
    monkeypatch, caplog
):
    secret = "postgresql://name:password@secret.internal/qms"
    tenants = [
        SimpleNamespace(id=uuid.uuid4(), slug="first", schema_name="tenant_first"),
        SimpleNamespace(id=uuid.uuid4(), slug="second", schema_name="tenant_second"),
    ]
    attempted: list[str] = []
    statements: list[object] = []
    sessions: list[FakeSession] = []

    async def active(_slug=None):
        return tenants

    def migrate(schema_name: str) -> bool:
        attempted.append(schema_name)
        if schema_name == "tenant_first":
            raise RuntimeError(secret)
        return True

    monkeypatch.setattr(tenant_migrate, "get_active_tenants", active)
    monkeypatch.setattr(tenant_migrate, "run_alembic_upgrade", migrate)
    monkeypatch.setattr(
        tenant_migrate,
        "async_session",
        _session_factory(statements, sessions),
    )

    with pytest.raises(tenant_migrate.TenantMigrationError) as exc:
        await tenant_migrate.main(all_tenants=True)

    assert attempted == ["tenant_first", "tenant_second"]
    assert secret not in str(exc.value)
    assert secret not in caplog.text
    upserts = [statement for statement in statements if not hasattr(statement, "text")]
    params = [_compiled(statement)[1] for statement in upserts]
    assert params[0]["status"] == "failed"
    assert params[0]["error_message"] == "tenant migration failed"
    assert secret not in repr(params)


def test_cli_sanitizes_unexpected_orchestration_failure(monkeypatch, caplog):
    secret = "credential-bearing failure detail"

    async def fail_main(**_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(tenant_migrate, "main", fail_main)

    exit_code = tenant_migrate.run_cli(all_tenants=True, slug=None)

    assert exit_code == 1
    assert "tenant migration orchestration failed" in caplog.text
    assert secret not in caplog.text


def test_alembic_failure_log_does_not_include_subprocess_output(monkeypatch, caplog):
    secret = "postgresql://name:password@secret.internal/qms"
    monkeypatch.setattr(
        tenant_migrate.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stderr=secret),
    )

    success = tenant_migrate.run_alembic_upgrade("tenant_safe")

    assert success is False
    assert secret not in caplog.text
