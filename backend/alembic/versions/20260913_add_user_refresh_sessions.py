"""Add independent user refresh sessions.

Revision ID: 20260913_user_refresh_sessions
Revises: 20260727_warranty_factory_id
"""
from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID


revision = "20260913_user_refresh_sessions"
down_revision = "20260727_warranty_factory_id"
branch_labels = None
depends_on = None

_TABLE = "user_refresh_sessions"
_SIMPLE_INDEX = "ix_user_refresh_sessions_user_id"
_COMPOSITE_INDEX = "ix_user_refresh_sessions_user_id_expires_at"


def _target_schema() -> str:
    return context.get_x_argument(as_dictionary=True).get("schema") or "public"


def _type_matches(column_type: sa.types.TypeEngine, expected: str) -> bool:
    if expected == "uuid":
        return isinstance(column_type, UUID)
    if expected == "string":
        return isinstance(column_type, sa.String) and column_type.length == 64
    if expected == "timestamp":
        return isinstance(column_type, sa.DateTime) and column_type.timezone is True
    return False


def _validate_existing_table(bind, schema: str) -> None:
    inspector = inspect(bind)
    expected_columns = {
        "session_id": ("uuid", False, False),
        "user_id": ("uuid", False, False),
        "token_hash": ("string", False, False),
        "expires_at": ("timestamp", False, False),
        "created_at": ("timestamp", False, True),
        "rotated_at": ("timestamp", True, False),
        "revoked_at": ("timestamp", True, False),
    }
    columns = {column["name"]: column for column in inspector.get_columns(_TABLE, schema=schema)}
    mismatches: list[str] = []

    missing = sorted(set(expected_columns) - set(columns))
    if missing:
        mismatches.append(f"missing columns {missing}")
    for name, (expected_type, nullable, has_now_default) in expected_columns.items():
        column = columns.get(name)
        if column is None:
            continue
        if not _type_matches(column["type"], expected_type):
            mismatches.append(f"{name} has type {column['type']!s}, expected {expected_type}")
        if column["nullable"] is not nullable:
            mismatches.append(f"{name} nullable={column['nullable']}, expected {nullable}")
        default = "".join(str(column.get("default") or "").lower().split())
        if has_now_default:
            if default not in {"now()", "current_timestamp", "current_timestamp()"}:
                mismatches.append(f"{name} has invalid current-time server default {column['default']!r}")
        elif default:
            mismatches.append(f"{name} has unexpected server default {column['default']!r}")

    primary_key = inspector.get_pk_constraint(_TABLE, schema=schema)
    if primary_key.get("constrained_columns") != ["session_id"]:
        mismatches.append(
            f"primary key is {primary_key.get('constrained_columns')!r}, expected ['session_id']"
        )

    indexes = inspector.get_indexes(_TABLE, schema=schema)
    index_by_name = {index["name"]: index for index in indexes}
    simple = index_by_name.get(_SIMPLE_INDEX)
    if (
        simple is None
        or simple.get("column_names") != ["user_id"]
        or simple.get("unique") is not False
        or (simple.get("dialect_options") or {}).get("postgresql_where") is not None
    ):
        mismatches.append(f"missing or invalid index {_SIMPLE_INDEX}")
    composite = index_by_name.get(_COMPOSITE_INDEX)
    if (
        composite is None
        or composite.get("column_names") != ["user_id", "expires_at"]
        or composite.get("unique") is not False
        or (composite.get("dialect_options") or {}).get("postgresql_where") is not None
    ):
        mismatches.append(f"missing or invalid index {_COMPOSITE_INDEX}")

    unique_token = any(
        constraint.get("column_names") == ["token_hash"]
        for constraint in inspector.get_unique_constraints(_TABLE, schema=schema)
    ) or any(
        index.get("column_names") == ["token_hash"]
        and index.get("unique") is True
        and (index.get("dialect_options") or {}).get("postgresql_where") is None
        for index in indexes
    )
    if not unique_token:
        mismatches.append("token_hash is not uniquely constrained")

    expected_fk = False
    for foreign_key in inspector.get_foreign_keys(_TABLE, schema=schema):
        referred_schema = foreign_key.get("referred_schema") or "public"
        options = foreign_key.get("options") or {}
        if (
            foreign_key.get("constrained_columns") == ["user_id"]
            and referred_schema == schema
            and foreign_key.get("referred_table") == "users"
            and foreign_key.get("referred_columns") == ["user_id"]
            and str(options.get("ondelete", "")).upper() == "CASCADE"
        ):
            expected_fk = True
            break
    if not expected_fk:
        mismatches.append(f"user_id FK does not reference {schema}.users.user_id ON DELETE CASCADE")

    if mismatches:
        raise RuntimeError(
            f"{_TABLE} in schema {schema!r} has incomplete contract: "
            + "; ".join(mismatches)
        )


def upgrade() -> None:
    schema = _target_schema()
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table(_TABLE, schema=schema):
        _validate_existing_table(bind, schema)
        return

    op.create_table(
        _TABLE,
        sa.Column("session_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{schema}.users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        schema=schema,
    )
    op.create_index(
        _SIMPLE_INDEX,
        _TABLE,
        ["user_id"],
        schema=schema,
    )
    op.create_index(
        _COMPOSITE_INDEX,
        _TABLE,
        ["user_id", "expires_at"],
        schema=schema,
    )


def downgrade() -> None:
    schema = _target_schema()
    bind = op.get_bind()
    if not inspect(bind).has_table(_TABLE, schema=schema):
        return
    op.drop_table(_TABLE, schema=schema)
