"""Tenant utility functions — shared between runtime code and Alembic env.py."""
import re
from contextvars import ContextVar

# Context variable: current request/task's tenant schema name
current_tenant_schema: ContextVar[str | None] = ContextVar("current_tenant_schema", default=None)

# Regex patterns
_SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_SCHEMA_PATTERN = re.compile(r"^tenant_[a-z0-9_]{1,56}$")


def slug_to_schema_name(slug: str) -> str:
    """Convert a URL slug to a PostgreSQL schema name."""
    if not slug or not _SLUG_PATTERN.match(slug):
        raise ValueError(f"Invalid slug: {slug!r} (must match [a-z0-9-]+)")
    schema_name = "tenant_" + slug.replace("-", "_")
    if not _SCHEMA_PATTERN.match(schema_name):
        raise ValueError(f"Invalid schema name derived from slug: {slug!r} -> {schema_name!r}")
    return schema_name


def set_search_path_sql(schema_name: str) -> str:
    """Validate schema name and generate safe SET search_path SQL."""
    if not _SCHEMA_PATTERN.match(schema_name):
        raise ValueError(f"Invalid schema name: {schema_name!r} (must match tenant_[a-z0-9_]+, max 63 chars)")
    quoted = '"' + schema_name.replace('"', '""') + '"'
    return f'SET search_path TO {quoted}, "public"'