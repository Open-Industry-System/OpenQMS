"""Focused PostgreSQL tests for the user refresh-session migration contract."""
from argparse import Namespace
from pathlib import Path
import re
import uuid

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from tests.conftest import _test_db_url


REV = "20260913_user_refresh_sessions"
DOWN_REV = "20260727_warranty_factory_id"
TABLE = "user_refresh_sessions"
OLD_FILENAME = "20260913_user_refresh_sessions.py"
NEW_FILENAME = "20260913_add_user_refresh_sessions.py"


def _cfg(mig_url: str, schema: str | None = None) -> Config:
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", mig_url)
    cfg.set_main_option("script_location", str(root / "alembic"))
    if schema is not None:
        cfg.cmd_opts = Namespace(x=[f"schema={schema}"])
    return cfg


def _sync_engine(mig_url: str):
    return create_engine(mig_url.replace("postgresql+asyncpg://", "postgresql+psycopg://"))


def _q(schema: str, table: str) -> str:
    return f'"{schema}"."{table}"'


@pytest.fixture
def migration_db_url(monkeypatch):
    """Use the explicitly configured test DB; do not create/drop a database."""
    monkeypatch.setenv("DATABASE_URL", _test_db_url)
    return _test_db_url


@pytest.fixture
def tenant_schema(migration_db_url):
    schema = f"tenant_refresh_{uuid.uuid4().hex[:12]}"
    engine = _sync_engine(migration_db_url)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield schema
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _prepare_base(engine, schema: str, version: str = DOWN_REV) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            f"CREATE TABLE {_q(schema, 'alembic_version')} "
            "(version_num VARCHAR(64) PRIMARY KEY)"
        ))
        conn.execute(text(
            f"INSERT INTO {_q(schema, 'alembic_version')} (version_num) "
            f"VALUES ('{version}')"
        ))
        conn.execute(text(
            f"CREATE TABLE {_q(schema, 'users')} "
            "(user_id UUID PRIMARY KEY)"
        ))


def _create_refresh_table(engine, schema: str, *, token_unique: bool = True) -> None:
    token_unique_sql = " UNIQUE" if token_unique else ""
    with engine.begin() as conn:
        conn.execute(text(
            f"CREATE TABLE {_q(schema, TABLE)} ("
            "session_id UUID PRIMARY KEY, "
            f"user_id UUID NOT NULL REFERENCES {_q(schema, 'users')}(user_id) ON DELETE CASCADE, "
            f"token_hash VARCHAR(64) NOT NULL{token_unique_sql}, "
            "expires_at TIMESTAMPTZ NOT NULL, "
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "rotated_at TIMESTAMPTZ, "
            "revoked_at TIMESTAMPTZ"
            ")"
        ))
        conn.execute(text(
            f"CREATE INDEX ix_user_refresh_sessions_user_id ON {_q(schema, TABLE)} (user_id)"
        ))
        conn.execute(text(
            "CREATE INDEX ix_user_refresh_sessions_user_id_expires_at "
            f"ON {_q(schema, TABLE)} (user_id, expires_at)"
        ))


def _create_incomplete_refresh_table(engine, schema: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            f"CREATE TABLE {_q(schema, TABLE)} (session_id UUID PRIMARY KEY)"
        ))


def _create_partial_index_variant(engine, schema: str, defect: str) -> None:
    _create_refresh_table(engine, schema, token_unique=defect != "partial_token_hash_unique")
    with engine.begin() as conn:
        if defect == "partial_token_hash_unique":
            conn.execute(text(
                "CREATE UNIQUE INDEX uq_user_refresh_sessions_token_hash_partial "
                f"ON {_q(schema, TABLE)} (token_hash) WHERE revoked_at IS NULL"
            ))
        elif defect == "partial_user_id_index":
            conn.execute(text(
                f"DROP INDEX {_q(schema, 'ix_user_refresh_sessions_user_id')}"
            ))
            conn.execute(text(
                f"CREATE INDEX ix_user_refresh_sessions_user_id ON {_q(schema, TABLE)} "
                "(user_id) WHERE revoked_at IS NULL"
            ))
        elif defect == "partial_composite_index":
            conn.execute(text(
                f"DROP INDEX {_q(schema, 'ix_user_refresh_sessions_user_id_expires_at')}"
            ))
            conn.execute(text(
                "CREATE INDEX ix_user_refresh_sessions_user_id_expires_at "
                f"ON {_q(schema, TABLE)} (user_id, expires_at) WHERE revoked_at IS NULL"
            ))
        else:
            raise AssertionError(f"unknown partial-index defect {defect}")


def _version(engine, schema: str) -> str | None:
    with engine.connect() as conn:
        return conn.execute(text(
            f"SELECT version_num FROM {_q(schema, 'alembic_version')}"
        )).scalar_one_or_none()


def _table_oid(engine, schema: str) -> int | None:
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT cls.oid "
            "FROM pg_class cls "
            "JOIN pg_namespace ns ON ns.oid=cls.relnamespace "
            "WHERE ns.nspname=:schema AND cls.relname=:table AND cls.relkind='r'"
        ), {"schema": schema, "table": TABLE}).scalar_one_or_none()


def _assert_complete_contract(engine, schema: str) -> None:
    with engine.connect() as conn:
        columns = {
            row["column_name"]: (
                row["data_type"],
                row["is_nullable"],
                row["character_maximum_length"],
                row["column_default"],
            )
            for row in conn.execute(text(
                "SELECT column_name, data_type, is_nullable, character_maximum_length, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema=:schema AND table_name=:table"
            ), {"schema": schema, "table": TABLE}).mappings()
        }
        expected_columns = {
            "session_id": ("uuid", "NO", None, None),
            "user_id": ("uuid", "NO", None, None),
            "token_hash": ("character varying", "NO", 64, None),
            "expires_at": ("timestamp with time zone", "NO", None, None),
            "created_at": ("timestamp with time zone", "NO", None, "current_time"),
            "rotated_at": ("timestamp with time zone", "YES", None, None),
            "revoked_at": ("timestamp with time zone", "YES", None, None),
        }
        for name, expected in expected_columns.items():
            actual = columns.get(name)
            assert actual is not None, f"missing required column {name}"
            assert actual[:3] == expected[:3], f"{name}: {actual!r} != {expected!r}"
            if name == "created_at":
                normalized_default = re.sub(r"\\s+", "", str(actual[3] or "").lower())
                assert normalized_default in {"now()", "current_timestamp", "current_timestamp()"}, (
                    f"created_at has non-current default {actual[3]!r}"
                )
            else:
                assert actual[3] is None, f"{name} has unexpected default {actual[3]!r}"

        primary_key = conn.execute(text(
            "SELECT array_agg(att.attname ORDER BY key.ord) "
            "FROM pg_index idx "
            "JOIN pg_class tbl ON tbl.oid=idx.indrelid "
            "JOIN pg_namespace ns ON ns.oid=tbl.relnamespace "
            "JOIN LATERAL unnest(idx.indkey) WITH ORDINALITY AS key(attnum, ord) ON true "
            "JOIN pg_attribute att ON att.attrelid=tbl.oid AND att.attnum=key.attnum "
            "WHERE ns.nspname=:schema AND tbl.relname=:table AND idx.indisprimary"
        ), {"schema": schema, "table": TABLE}).scalar_one()
        assert primary_key == ["session_id"]

        indexes = conn.execute(text(
            "SELECT idx.relname AS index_name, idx_data.indisunique AS is_unique, "
            "array_agg(att.attname ORDER BY key.ord) AS columns, "
            "pg_get_expr(idx_data.indpred, idx_data.indrelid) AS predicate "
            "FROM pg_index idx_data "
            "JOIN pg_class tbl ON tbl.oid=idx_data.indrelid "
            "JOIN pg_namespace ns ON ns.oid=tbl.relnamespace "
            "JOIN pg_class idx ON idx.oid=idx_data.indexrelid "
            "JOIN LATERAL unnest(idx_data.indkey) WITH ORDINALITY AS key(attnum, ord) ON true "
            "JOIN pg_attribute att ON att.attrelid=tbl.oid AND att.attnum=key.attnum "
            "WHERE ns.nspname=:schema AND tbl.relname=:table "
            "GROUP BY idx.relname, idx_data.indisunique, idx_data.indpred, idx_data.indrelid"
        ), {"schema": schema, "table": TABLE}).mappings().all()
        expected_indexes = {
            "ix_user_refresh_sessions_user_id": (("user_id",), False),
            "ix_user_refresh_sessions_user_id_expires_at": (("user_id", "expires_at"), False),
        }
        indexes_by_name = {index["index_name"]: index for index in indexes}
        for name, (expected_columns, expected_unique) in expected_indexes.items():
            index = indexes_by_name.get(name)
            assert index is not None, f"missing required index {name}"
            assert tuple(index["columns"]) == expected_columns
            assert index["is_unique"] is expected_unique
            assert index["predicate"] is None, f"{name} must not be partial"
        assert any(
            tuple(index["columns"]) == ("token_hash",)
            and index["is_unique"] is True
            and index["predicate"] is None
            for index in indexes
        ), "token_hash must have global uniqueness"

        foreign_keys = conn.execute(text(
            "SELECT remote_ns.nspname AS remote_schema, remote_tbl.relname AS remote_table, "
            "array_agg(local_att.attname ORDER BY local_key.ord) AS local_columns, "
            "array_agg(remote_att.attname ORDER BY local_key.ord) AS remote_columns, "
            "constraint_data.confdeltype "
            "FROM pg_constraint constraint_data "
            "JOIN pg_class local_tbl ON local_tbl.oid=constraint_data.conrelid "
            "JOIN pg_namespace local_ns ON local_ns.oid=local_tbl.relnamespace "
            "JOIN pg_class remote_tbl ON remote_tbl.oid=constraint_data.confrelid "
            "JOIN pg_namespace remote_ns ON remote_ns.oid=remote_tbl.relnamespace "
            "JOIN LATERAL unnest(constraint_data.conkey) WITH ORDINALITY AS local_key(attnum, ord) ON true "
            "JOIN pg_attribute local_att ON local_att.attrelid=local_tbl.oid AND local_att.attnum=local_key.attnum "
            "JOIN LATERAL unnest(constraint_data.confkey) WITH ORDINALITY AS remote_key(attnum, ord) "
            "  ON remote_key.ord=local_key.ord "
            "JOIN pg_attribute remote_att ON remote_att.attrelid=remote_tbl.oid AND remote_att.attnum=remote_key.attnum "
            "WHERE constraint_data.contype='f' AND local_ns.nspname=:schema "
            "AND local_tbl.relname=:table "
            "GROUP BY constraint_data.oid, remote_ns.nspname, remote_tbl.relname, constraint_data.confdeltype"
        ), {"schema": schema, "table": TABLE}).mappings().all()
        assert {
            (row["remote_schema"], row["remote_table"], tuple(row["local_columns"]), tuple(row["remote_columns"]), row["confdeltype"])
            for row in foreign_keys
        } >= {(schema, "users", ("user_id",), ("user_id",), "c")}


@pytest.mark.requires_db
def test_public_table_does_not_hide_tenant_upgrade(migration_db_url, tenant_schema):
    """A visible public table must not make a tenant migration skip its table."""
    engine = _sync_engine(migration_db_url)
    public_oid = _table_oid(engine, "public")
    public_version = _version(engine, "public")
    assert public_version == REV
    _prepare_base(engine, tenant_schema)
    engine.dispose()

    command.upgrade(_cfg(migration_db_url, tenant_schema), REV)

    engine = _sync_engine(migration_db_url)
    assert _version(engine, tenant_schema) == REV
    assert _version(engine, "public") == public_version
    assert _table_oid(engine, "public") == public_oid
    _assert_complete_contract(engine, tenant_schema)
    engine.dispose()


@pytest.mark.requires_db
def test_incomplete_squash_table_fails_and_is_not_stamped(migration_db_url, tenant_schema):
    """An incomplete squash-created table must fail validation before stamping."""
    engine = _sync_engine(migration_db_url)
    _prepare_base(engine, tenant_schema)
    _create_incomplete_refresh_table(engine, tenant_schema)
    engine.dispose()

    with pytest.raises(RuntimeError, match="user_refresh_sessions"):
        command.upgrade(_cfg(migration_db_url, tenant_schema), REV)

    engine = _sync_engine(migration_db_url)
    assert _version(engine, tenant_schema) == DOWN_REV
    engine.dispose()


@pytest.mark.requires_db
@pytest.mark.parametrize(
    "defect",
    ["partial_token_hash_unique", "partial_user_id_index", "partial_composite_index"],
)
def test_partial_required_indexes_are_rejected(migration_db_url, tenant_schema, defect):
    """Partial indexes must never satisfy the historical global contract."""
    engine = _sync_engine(migration_db_url)
    _prepare_base(engine, tenant_schema)
    _create_partial_index_variant(engine, tenant_schema, defect)
    engine.dispose()

    with pytest.raises(RuntimeError, match="user_refresh_sessions"):
        command.upgrade(_cfg(migration_db_url, tenant_schema), REV)

    engine = _sync_engine(migration_db_url)
    assert _version(engine, tenant_schema) == DOWN_REV
    engine.dispose()


@pytest.mark.requires_db
def test_offset_created_at_default_is_rejected(migration_db_url, tenant_schema):
    """A future created_at default must not pass as a current-time default."""
    engine = _sync_engine(migration_db_url)
    _prepare_base(engine, tenant_schema)
    _create_refresh_table(engine, tenant_schema)
    with engine.begin() as conn:
        conn.execute(text(
            f"ALTER TABLE {_q(tenant_schema, TABLE)} "
            "ALTER COLUMN created_at SET DEFAULT now() + interval '7 days'"
        ))
    engine.dispose()

    with pytest.raises(RuntimeError, match="user_refresh_sessions"):
        command.upgrade(_cfg(migration_db_url, tenant_schema), REV)

    engine = _sync_engine(migration_db_url)
    assert _version(engine, tenant_schema) == DOWN_REV
    engine.dispose()


@pytest.mark.requires_db
def test_complete_squash_table_is_validated_without_recreation(migration_db_url, tenant_schema):
    """A complete pre-existing table is preserved while the revision is stamped."""
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    engine = _sync_engine(migration_db_url)
    _prepare_base(engine, tenant_schema)
    _create_refresh_table(engine, tenant_schema)
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {_q(tenant_schema, 'users')} (user_id) VALUES (:user_id)"
        ), {"user_id": user_id})
        conn.execute(text(
            f"INSERT INTO {_q(tenant_schema, TABLE)} "
            "(session_id, user_id, token_hash, expires_at) "
            "VALUES (:session_id, :user_id, :token_hash, now() + interval '1 day')"
        ), {"session_id": session_id, "user_id": user_id, "token_hash": "squash-marker"})
        conn.execute(text(
            f"ALTER TABLE {_q(tenant_schema, TABLE)} ADD COLUMN last_used_at TIMESTAMPTZ"
        ))
    engine.dispose()

    command.upgrade(_cfg(migration_db_url, tenant_schema), REV)

    engine = _sync_engine(migration_db_url)
    assert _version(engine, tenant_schema) == REV
    _assert_complete_contract(engine, tenant_schema)
    with engine.connect() as conn:
        assert conn.execute(text(
            f"SELECT session_id FROM {_q(tenant_schema, TABLE)} WHERE session_id=:session_id"
        ), {"session_id": session_id}).scalar_one() == session_id
        extra_column = conn.execute(text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema=:schema AND table_name=:table AND column_name='last_used_at'"
        ), {"schema": tenant_schema, "table": TABLE}).one()
        assert extra_column == ("timestamp with time zone", "YES")
    engine.dispose()


@pytest.mark.requires_db
def test_existing_public_table_has_complete_contract(migration_db_url):
    """The existing public table must satisfy the same migration contract."""
    engine = _sync_engine(migration_db_url)
    public_version = _version(engine, "public")
    assert public_version == REV
    _assert_complete_contract(engine, "public")
    engine.dispose()

    command.upgrade(_cfg(migration_db_url), REV)

    engine = _sync_engine(migration_db_url)
    assert _version(engine, "public") == public_version
    _assert_complete_contract(engine, "public")
    engine.dispose()


@pytest.mark.requires_db
def test_downgrade_targets_schema_and_is_safe_when_absent(migration_db_url, tenant_schema):
    """Downgrade must not touch public or fail when the tenant table is absent."""
    engine = _sync_engine(migration_db_url)
    public_oid = _table_oid(engine, "public")
    public_version = _version(engine, "public")
    assert public_version == REV
    _prepare_base(engine, tenant_schema, REV)
    engine.dispose()

    command.downgrade(_cfg(migration_db_url, tenant_schema), DOWN_REV)

    engine = _sync_engine(migration_db_url)
    assert _version(engine, tenant_schema) == DOWN_REV
    assert _version(engine, "public") == public_version
    assert _table_oid(engine, "public") == public_oid
    engine.dispose()


@pytest.mark.requires_db
def test_downgrade_drops_present_tenant_table_only(migration_db_url, tenant_schema):
    """Present-table downgrade removes only the exact tenant table."""
    engine = _sync_engine(migration_db_url)
    public_oid = _table_oid(engine, "public")
    public_version = _version(engine, "public")
    assert public_version == REV
    _prepare_base(engine, tenant_schema, REV)
    _create_refresh_table(engine, tenant_schema)
    engine.dispose()

    command.downgrade(_cfg(migration_db_url, tenant_schema), DOWN_REV)

    engine = _sync_engine(migration_db_url)
    assert _version(engine, tenant_schema) == DOWN_REV
    assert _table_oid(engine, tenant_schema) is None
    assert _version(engine, "public") == public_version
    assert _table_oid(engine, "public") == public_oid
    engine.dispose()


def test_filename_convention_and_single_head():
    """The revision follows ADR-0013 naming and remains the sole Alembic head."""
    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    assert (versions_dir / NEW_FILENAME).exists()
    assert not (versions_dir / OLD_FILENAME).exists()

    script = ScriptDirectory.from_config(_cfg("postgresql+psycopg://unused"))
    assert script.get_heads() == [REV]
