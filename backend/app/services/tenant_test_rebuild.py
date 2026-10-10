"""Explicit, offline-only rebuild of an exact test tenant inventory."""
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.config import settings
from app.core.tenant_transaction import TenantUnavailable
from app.core.tenant_utils import slug_to_schema_name, strict_tenant_search_path_sql
from app.database import engine as default_engine
from app.schemas.platform import TenantCreateRequest
from app.services.tenant_migrator import REVISION, _PREVIOUSLY_ACTIVE_SEED_REASON, maintenance_connection
from app.services.tenant_offline import (
    ComposeOfflineObserver, TenantBusy, require_no_other_clients, require_test_database,
)
from app.services.tenant_schema_diff import load_snapshot_manifest


@dataclass(frozen=True)
class RebuildTarget:
    tenant_id: UUID
    slug: str
    schema_name: str
    generation: int
    status: str

    def __post_init__(self):
        if (not isinstance(self.tenant_id, UUID) or not isinstance(self.slug, str)
                or self.schema_name != slug_to_schema_name(self.slug)
                or type(self.generation) is not int or self.generation < 0
                or self.status not in {"active", "failed", "maintenance", "provisioning", "pending"}):
            raise ValueError("invalid exact rebuild target")
        strict_tenant_search_path_sql(self.schema_name)


@dataclass(frozen=True)
class RebuildResult:
    tenant_id: UUID
    status: str
    error: str | None = None


@dataclass(frozen=True)
class RebuildInventory:
    test_only: bool
    targets: tuple[RebuildTarget, ...]

    def __post_init__(self):
        if self.test_only is not True or not isinstance(self.targets, tuple):
            raise PermissionError("explicit test-only inventory required")
        _validate_targets(self.targets)

    @classmethod
    def from_json(cls, raw: str) -> "RebuildInventory":
        """Reject extra fields rather than allowing credentials into inventories."""
        try:
            body = json.loads(raw)
            if not isinstance(body, dict) or set(body) != {"test_only", "targets"} or not isinstance(body["targets"], list):
                raise ValueError()
            targets = []
            for entry in body["targets"]:
                if not isinstance(entry, dict) or set(entry) != {"tenant_id", "slug", "schema_name", "generation", "status"}:
                    raise ValueError()
                targets.append(RebuildTarget(**dict(entry, tenant_id=UUID(entry["tenant_id"]))))
            return cls(body["test_only"], tuple(targets))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ValueError("invalid credential-free exact test inventory") from exc


def _validate_targets(targets) -> None:
    if (not targets or any(not isinstance(t, RebuildTarget) for t in targets)
            or len({t.tenant_id for t in targets}) != len(targets)
            or len({t.schema_name for t in targets}) != len(targets)):
        raise ValueError("nonempty unique exact targets required")


_REGISTRY_SQL = """
    SELECT id,slug,schema_name,generation,status,provisioning_attempt_id
    FROM public.tenants WHERE id=:id
"""


def _matches(row, target: RebuildTarget) -> bool:
    return row is not None and tuple(row[:5]) == (
        target.tenant_id, target.slug, target.schema_name, target.generation, target.status,
    )


async def preview_rebuild(tenant_ids: list[UUID], *, engine: AsyncEngine = default_engine) -> list[RebuildTarget]:
    """Read-only preview. No broad enumeration or string/wildcard IDs."""
    if not tenant_ids or any(not isinstance(item, UUID) for item in tenant_ids) or len(set(tenant_ids)) != len(tenant_ids):
        raise ValueError("nonempty unique UUID allowlist required")
    targets = []
    async with engine.connect() as connection:
        for tenant_id in tenant_ids:
            row = (await connection.execute(text(_REGISTRY_SQL), {"id": tenant_id})).one_or_none()
            if row is None:
                raise PermissionError("unknown test inventory target")
            targets.append(RebuildTarget(*row[:5]))
    _validate_targets(targets)
    return targets


def require_execute_flags(confirmation: str) -> None:
    if settings.TENANT_MODE == "production" or os.getenv("ALLOW_TEST_TENANT_REBUILD") != "1":
        raise PermissionError("test-only rebuild disabled")
    if confirmation != "discard-test-data":
        raise PermissionError("explicit discard confirmation required")


async def record_test_rebuild_disposal(connection: AsyncConnection, target: RebuildTarget) -> None:
    """Record only an exact old generation in the transaction that dropped it."""
    from app.models.tenant_attachment_disposal import TenantAttachmentStorageDisposal

    if not isinstance(target, RebuildTarget):
        raise ValueError("exact rebuild target required")
    # reset_test_schema has a strict path for the just-dropped tenant schema;
    # disposal authority is platform state and must be written to public in the
    # same open destructive transaction.
    await connection.execute(text("SET LOCAL search_path TO public, pg_catalog"))
    await connection.execute(
        insert(TenantAttachmentStorageDisposal).values(
            tenant_id=target.tenant_id,
            origin_generation=target.generation,
            storage_namespace=f"tenant_{target.tenant_id.hex}_{target.generation}",
            reason="test_rebuild",
        ).on_conflict_do_nothing(
            index_elements=["tenant_id", "origin_generation", "storage_namespace"],
        )
    )


async def _mark_maintenance(engine: AsyncEngine, target: RebuildTarget) -> tuple:
    """Deny new work without changing the attempt or generation before owning the lock."""
    async with engine.begin() as connection:
        await require_test_database(connection)
        await require_no_other_clients(connection)
        row = (await connection.execute(text(_REGISTRY_SQL + " FOR UPDATE"), {"id": target.tenant_id})).one_or_none()
        if not _matches(row, target):
            raise TenantUnavailable("rebuild target changed")
        await connection.execute(text("""
            UPDATE public.tenants SET status='maintenance', provisioning_step='rebuild_requested',
                provisioning_error=:error WHERE id=:id
        """), {"id": target.tenant_id,
               "error": f"TenantUnavailable: {_PREVIOUSLY_ACTIVE_SEED_REASON}"})
        return (row.id, row.slug, row.schema_name, row.generation, "maintenance", row.provisioning_attempt_id)


def _safe_reason(exc: BaseException) -> str:
    if type(exc) is TenantBusy and str(exc) in {"services_not_offline", "database_not_quiescent"}:
        return str(exc)
    if type(exc) is TenantUnavailable:
        if str(exc) == "external schema dependency":
            return "external_schema_dependency"
        if str(exc) == "rebuild target changed":
            return "target_changed"
        if str(exc) == "tenant has active transactions":
            return "tenant_busy"
    return "rebuild_failed"


async def rebuild_test_tenants(
    targets: list[RebuildTarget], confirmation: str, bootstrap_requests: dict[UUID, TenantCreateRequest],
    *, inventory: RebuildInventory, compose_project: str,
    engine: AsyncEngine = default_engine, offline: ComposeOfflineObserver | None = None,
    after_stage_hook: Callable[[str], None] | None = None,
) -> list[RebuildResult]:
    require_execute_flags(confirmation)
    _validate_targets(targets)
    if (not isinstance(inventory, RebuildInventory) or inventory.test_only is not True
            or any(t not in inventory.targets for t in targets)):
        raise PermissionError("target not in explicit test inventory")
    for target in targets:
        request = bootstrap_requests.get(target.tenant_id)
        if not isinstance(request, TenantCreateRequest) or request.slug != target.slug:
            raise PermissionError("matching test admin bootstrap credentials required")
    # Global validation is read-only: one malformed target cannot partially reset another.
    async with engine.connect() as connection:
        await require_test_database(connection)
        for target in targets:
            row = (await connection.execute(text(_REGISTRY_SQL), {"id": target.tenant_id})).one_or_none()
            if not _matches(row, target):
                raise PermissionError("test inventory drift; refresh exact inventory")
    observer = offline or ComposeOfflineObserver()
    results = []
    for target in targets:
        try:
            await observer.require_stopped(compose_project)
            precondition = await _mark_maintenance(engine, target)
            if after_stage_hook:
                after_stage_hook("maintenance_marked")
            async with maintenance_connection(engine, target.tenant_id, rebuild_precondition=precondition) as maintenance:
                try:
                    # Only the lock owner incremented generation. Recheck all live proof before DROP.
                    await observer.require_stopped(compose_project)
                    await maintenance.require_rebuild_quiescence()
                    await maintenance.reset_test_schema(
                        slug=target.slug,
                        schema_name=target.schema_name,
                        previous_generation=target.generation,
                        after_drop=lambda connection: record_test_rebuild_disposal(connection, target),
                    )
                    if after_stage_hook:
                        after_stage_hook("reset_commit")
                    await maintenance.create_schema()
                    await maintenance.record_rebuild_phase("schema_created")
                    await maintenance.run_migration(REVISION)
                    await maintenance.record_rebuild_phase("migrated")
                    if after_stage_hook:
                        after_stage_hook("migration_commit")
                    await maintenance.seed_tenant(bootstrap_requests[target.tenant_id], before_commit_hook=after_stage_hook)
                    await maintenance.record_rebuild_phase("seeded")
                    if after_stage_hook:
                        after_stage_hook("seed_commit")
                    if await maintenance.compare_schema("public", load_snapshot_manifest()):
                        raise TenantUnavailable("tenant schema does not match reviewed business snapshot")
                    await maintenance.verify_isolation()
                    await maintenance.record_rebuild_phase("verified")
                    if after_stage_hook:
                        after_stage_hook("final_platform_update")
                    await maintenance.record_rebuild_phase("active", active=True)
                except BaseException as exc:
                    reason = _safe_reason(exc)
                    await maintenance.record_rebuild_failure(reason)
                    if not isinstance(exc, Exception):
                        raise
                    result = RebuildResult(target.tenant_id, "failed", reason)
                else:
                    result = RebuildResult(target.tenant_id, "active")
            results.append(result)
        except Exception as exc:
            # No captured owner claim: never overwrite a winner's attempt/status.
            results.append(RebuildResult(target.tenant_id, "refused", _safe_reason(exc)))
    return results
