"""Normal tenant transactions: lock, validate the registry, then bind a strict path."""
import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import settings
from app.core.tenant_utils import strict_tenant_search_path_sql


class TenantUnavailable(Exception):
    """The tenant cannot admit this business transaction."""


def require_single_tenant_global_feature(feature: str) -> None:
    """Prevent process-global providers and graph resets in multi-tenant mode."""
    if settings.TENANT_MODE != "single":
        raise TenantUnavailable(f"{feature} is unavailable in multi-tenant mode")


@dataclass(frozen=True)
class TenantBinding:
    tenant_id: UUID
    schema_name: str
    generation: int
    mode: Literal["business", "maintenance"]


def stable_tenant_lock_key(tenant_id: UUID) -> int:
    return int.from_bytes(hashlib.sha256(tenant_id.bytes).digest()[:8], "big", signed=True)


def bind_business_transaction(connection: Connection, binding: TenantBinding) -> None:
    """Called on every transaction start, before any business statement executes."""
    if not isinstance(binding, TenantBinding) or binding.mode != "business":
        raise TenantUnavailable("business tenant binding required")
    # Validate before acquiring a lock or touching the tenant schema.
    path_sql = strict_tenant_search_path_sql(binding.schema_name)
    acquired = connection.scalar(
        text("SELECT pg_try_advisory_xact_lock_shared(:key)"),
        {"key": stable_tenant_lock_key(binding.tenant_id)},
    )
    if not acquired:
        raise TenantUnavailable("tenant maintenance")
    row = connection.execute(
        text("SELECT status, generation, schema_name FROM public.tenants WHERE id=:tenant_id"),
        {"tenant_id": binding.tenant_id},
    ).one_or_none()
    if (row is None or row.status != "active" or row.generation != binding.generation
            or row.schema_name != binding.schema_name):
        raise TenantUnavailable("tenant generation, status, or schema changed")
    connection.exec_driver_sql(path_sql)
