"""Database identity guard tests for the release entrypoint."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
GUARD_PATH = ROOT / "scripts" / "check-distinct-databases.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location(
        "check_distinct_databases", GUARD_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    guard = _load_guard()

    def live_identity(_dsn: str):
        return ("10.0.0.8", 5432, "openqms", 16384)

    with pytest.raises(guard.DatabaseIdentityError, match="same live database"):
        guard.require_distinct_databases(
            "postgresql+asyncpg://release@db-a.internal/openqms",
            "postgresql+psycopg://tests@db-alias.internal/openqms",
            identity_resolver=live_identity,
        )


def test_live_identity_uses_psycopg_and_a_read_only_transaction(monkeypatch):
    guard = _load_guard()
    created_urls = []
    statements: list[str] = []

    class Result:
        def one(self):
            return ("openqms", "10.0.0.8", 5432, 16384)

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

    monkeypatch.setattr(guard, "create_engine", create_engine)

    identity = guard.resolve_live_identity(
        "postgresql+asyncpg://qms@db.internal/openqms"
    )

    assert created_urls[0].drivername == "postgresql+psycopg"
    assert statements[0] == "SET TRANSACTION READ ONLY"
    assert "current_database()" in statements[1]
    assert identity == ("10.0.0.8", 5432, "openqms", 16384)
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


def test_guard_cli_rejects_positional_database_arguments():
    result = subprocess.run(
        [sys.executable, str(GUARD_PATH), "postgresql://credential-bearing-dsn"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr
