#!/usr/bin/env python3
"""Reject release configurations whose target and test DSNs name one database."""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable

from sqlalchemy.engine import make_url

from database_identity import (
    DatabaseIdentity,
    DatabaseIdentityError,
    resolve_live_identity,
)


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


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


def require_distinct_databases(
    target_dsn: str,
    test_dsn: str,
    *,
    identity_resolver: Callable[[str], DatabaseIdentity] | None = None,
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
    except ValueError:
        print("database guard: invalid database URL", file=sys.stderr)
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
