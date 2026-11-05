"""Tenant utility functions — shared between runtime code and Alembic env.py."""
import re
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.tenant_transaction import TenantBinding

# Capture ID and generation at request/worker entry; schema alone is not authority.
current_tenant_binding: ContextVar["TenantBinding | None"] = ContextVar(
    "current_tenant_binding", default=None
)

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


def strict_tenant_search_path_sql(schema_name: str) -> str:
    """Normal transactions never resolve unqualified business tables in public."""
    if not isinstance(schema_name, str) or not _SCHEMA_PATTERN.fullmatch(schema_name):
        raise ValueError(f"Invalid tenant schema name: {schema_name!r}")
    return f'SET LOCAL search_path TO "{schema_name}", pg_catalog'


def set_search_path_sql(schema_name: str) -> str:
    """Validate schema name and generate safe SET search_path SQL."""
    if not _SCHEMA_PATTERN.match(schema_name):
        raise ValueError(f"Invalid schema name: {schema_name!r} (must match tenant_[a-z0-9_]+, max 63 chars)")
    quoted = '"' + schema_name.replace('"', '""') + '"'
    return f'SET search_path TO {quoted}, "public"'