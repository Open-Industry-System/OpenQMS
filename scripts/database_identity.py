#!/usr/bin/env python3
"""Resolve a PostgreSQL database's stable runtime identity."""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


_IDENTITY_SQL = """
SELECT
    (pg_control_system()).system_identifier::text,
    current_database(),
    (SELECT oid FROM pg_database WHERE datname = current_database())::bigint
"""


class DatabaseIdentityError(RuntimeError):
    """A runtime database identity is invalid or does not match."""


@dataclass(frozen=True)
class DatabaseIdentity:
    system_identifier: str
    database: str
    database_oid: int

    @classmethod
    def from_json(cls, value: str) -> "DatabaseIdentity":
        """Parse an exact database identity JSON object."""
        try:
            data = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise DatabaseIdentityError("invalid database identity JSON") from exc

        expected_fields = {"system_identifier", "database", "database_oid"}
        if not isinstance(data, dict) or set(data) != expected_fields:
            raise DatabaseIdentityError("invalid database identity fields")
        if type(data["system_identifier"]) is not str or not data["system_identifier"]:
            raise DatabaseIdentityError("invalid system identifier")
        if type(data["database"]) is not str or not data["database"]:
            raise DatabaseIdentityError("invalid database name")
        if type(data["database_oid"]) is not int:
            raise DatabaseIdentityError("invalid database OID")
        return cls(
            system_identifier=data["system_identifier"],
            database=data["database"],
            database_oid=data["database_oid"],
        )


def resolve_live_identity(dsn: str) -> DatabaseIdentity:
    """Read the identity through a psycopg, read-only transaction."""
    url = make_url(dsn)
    if url.get_backend_name().lower() != "postgresql":
        raise ValueError("only PostgreSQL database URLs are supported")
    engine = create_engine(url.set(drivername="postgresql+psycopg"))
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            system_identifier, database, database_oid = connection.exec_driver_sql(
                _IDENTITY_SQL
            ).one()
            return DatabaseIdentity(
                system_identifier=system_identifier,
                database=database,
                database_oid=database_oid,
            )
    finally:
        engine.dispose()
