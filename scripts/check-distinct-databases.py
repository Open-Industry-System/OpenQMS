#!/usr/bin/env python3
"""Reject release configurations whose target and test DSNs name one database."""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class DatabaseIdentityError(RuntimeError):
    """The target and test URLs do not identify distinct databases."""


_IDENTITY_SQL = """
SELECT
    current_database(),
    inet_server_addr()::text,
    COALESCE(inet_server_port(), current_setting('port')::integer),
    (SELECT oid FROM pg_database WHERE datname = current_database())
"""


def canonical_database_identity(dsn: str) -> tuple[object, ...]:
    """Return the connection identity encoded by a PostgreSQL DSN."""
    url = make_url(dsn)
    backend = url.get_backend_name().lower()
    if backend != "postgresql":
        raise ValueError("only PostgreSQL database URLs are supported")

    host = (url.host or "").lower()
    if host in _LOOPBACK_HOSTS:
        host = "loopback"
    query = tuple(
        sorted(
            (str(key), tuple(value) if isinstance(value, tuple) else str(value))
            for key, value in url.query.items()
        )
    )
    return (
        backend,
        host,
        url.port or 5432,
        url.database or "",
        url.username or "",
        query,
    )


def resolve_live_identity(dsn: str) -> tuple[object, ...]:
    """Read the database identity through a psycopg, read-only connection."""
    url = make_url(dsn)
    if url.get_backend_name().lower() != "postgresql":
        raise ValueError("only PostgreSQL database URLs are supported")
    sync_url = url.set(drivername="postgresql+psycopg")
    engine = create_engine(sync_url)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            database, address, port, database_oid = connection.exec_driver_sql(
                _IDENTITY_SQL
            ).one()
            return (address, port, database, database_oid)
    finally:
        engine.dispose()


def require_distinct_databases(
    target_dsn: str,
    test_dsn: str,
    *,
    identity_resolver: Callable[[str], tuple[object, ...]] | None = None,
) -> None:
    """Reject DSNs that are canonically identical before opening connections."""
    if canonical_database_identity(target_dsn) == canonical_database_identity(
        test_dsn
    ):
        raise DatabaseIdentityError(
            "target and test URLs resolve to the same canonical database"
        )

    if identity_resolver is None:
        identity_resolver = resolve_live_identity
    target_identity = identity_resolver(target_dsn)
    test_identity = identity_resolver(test_dsn)
    if target_identity == test_identity:
        raise DatabaseIdentityError(
            "target and test URLs connect to the same live database"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify that release target and test PostgreSQL URLs are distinct."
    )
    parser.parse_args(argv)

    target_url = os.environ.get("DATABASE_URL")
    if not target_url:
        print("database guard: DATABASE_URL is required", file=sys.stderr)
        return 2
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        print("database guard: TEST_DATABASE_URL is required", file=sys.stderr)
        return 2

    try:
        require_distinct_databases(target_url, test_url)
    except DatabaseIdentityError as exc:
        print(f"database guard: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"database guard: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # Connection/driver failure must fail closed.
        print(
            "database guard: could not verify live database identities "
            f"({type(exc).__name__})",
            file=sys.stderr,
        )
        return 2

    print("database guard OK — target and test databases are distinct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
