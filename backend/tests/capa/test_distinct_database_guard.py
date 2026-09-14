"""Database identity guard tests for the release entrypoint."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
GUARD_PATH = SCRIPTS / "check-distinct-databases.py"
IDENTITY_PATH = SCRIPTS / "database_identity.py"


def _load_module(name: str, path: Path):
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


def _load_guard():
    return _load_module("check_distinct_databases", GUARD_PATH)


def _load_identity():
    return _load_module("database_identity", IDENTITY_PATH)


def test_canonical_identity_normalizes_driver_loopback_and_query_order():
    guard = _load_guard()

    async_url = (
        "postgresql+asyncpg://Qms@localhost/openqms"
        "?sslmode=require&application_name=release"
    )
    sync_url = (
        "postgresql+psycopg://Qms@127.0.0.1:5432/openqms"
        "?application_name=release&sslmode=require"
    )

    assert guard.canonical_database_identity(async_url) == (
        guard.canonical_database_identity(sync_url)
    )


def test_guard_rejects_canonical_match_before_live_connections():
    guard = _load_guard()
    calls: list[str] = []

    def live_identity(dsn: str):
        calls.append(dsn)
        return ("unused",)

    with pytest.raises(guard.DatabaseIdentityError, match="same canonical database"):
        guard.require_distinct_databases(
            "postgresql+asyncpg://qms@localhost/openqms?b=2&a=1",
            "postgresql+psycopg://qms@127.0.0.1:5432/openqms?a=1&b=2",
            identity_resolver=live_identity,
        )

    assert calls == []


def test_guard_rejects_different_urls_that_connect_to_same_live_database():
    identity = _load_identity()
    guard = _load_guard()

    def live_identity(_dsn: str):
        return identity.DatabaseIdentity("cluster-a", "openqms", 16384)

    with pytest.raises(guard.DatabaseIdentityError, match="same live database"):
        guard.require_distinct_databases(
            "postgresql+asyncpg://release@db-a.internal/openqms",
            "postgresql+psycopg://tests@db-alias.internal/openqms",
            identity_resolver=live_identity,
        )


def test_live_identity_uses_psycopg_and_a_read_only_transaction(monkeypatch):
    identity_module = _load_identity()
    created_urls = []
    statements: list[str] = []

    class Result:
        def one(self):
            return ("cluster-a", "openqms", 16384)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def exec_driver_sql(self, statement):
            statements.append(statement)
            return Result()

    class Engine:
        def connect(self):
            return Connection()

        def dispose(self):
            statements.append("DISPOSE")

    def create_engine(url, **_kwargs):
        created_urls.append(url)
        return Engine()

    monkeypatch.setattr(identity_module, "create_engine", create_engine)

    identity = identity_module.resolve_live_identity(
        "postgresql+asyncpg://qms@db.internal/openqms"
    )

    assert created_urls[0].drivername == "postgresql+psycopg"
    assert statements[0] == "SET TRANSACTION READ ONLY"
    assert "(pg_control_system()).system_identifier::text" in statements[1]
    assert "current_database()" in statements[1]
    assert identity == identity_module.DatabaseIdentity("cluster-a", "openqms", 16384)
    assert statements[-1] == "DISPOSE"


def test_guard_cli_rejects_canonical_match_without_connecting():
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql+asyncpg://qms@localhost/openqms?b=2&a=1",
        "TEST_DATABASE_URL": (
            "postgresql+psycopg://qms@127.0.0.1:5432/openqms?a=1&b=2"
        ),
    }
    result = subprocess.run(
        [sys.executable, str(GUARD_PATH)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "same canonical database" in result.stderr


@pytest.mark.parametrize("missing_name", ["DATABASE_URL", "TEST_DATABASE_URL"])
def test_guard_cli_requires_database_environment(missing_name):
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql+asyncpg://qms@target/openqms",
        "TEST_DATABASE_URL": "postgresql+asyncpg://qms@test/openqms",
    }
    env.pop(missing_name, None)

    result = subprocess.run(
        [sys.executable, str(GUARD_PATH)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert f"{missing_name} is required" in result.stderr


def test_guard_cli_sanitizes_invalid_url_errors(monkeypatch, capsys):
    guard = _load_guard()
    secret = "credential-bearing failure detail"
    monkeypatch.setenv("DATABASE_URL", "postgresql://target/openqms")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://test/openqms_test")

    def fail(*_args, **_kwargs):
        raise ValueError(secret)

    monkeypatch.setattr(guard, "require_distinct_databases", fail)

    result = guard.main([])

    captured = capsys.readouterr()
    assert result == 2
    assert captured.err == "database guard: invalid database URL\n"
    assert secret not in captured.err


def test_guard_cli_rejects_positional_database_arguments():
    result = subprocess.run(
        [sys.executable, str(GUARD_PATH), "postgresql://credential-bearing-dsn"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr
