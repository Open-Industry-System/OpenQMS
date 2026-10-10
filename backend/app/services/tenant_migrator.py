"""Owner-bound tenant migration, atomic seed and same-tenant recovery."""
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from app.core.tenant_transaction import TenantBinding, TenantUnavailable, stable_tenant_lock_key
from app.core.tenant_utils import slug_to_schema_name, strict_tenant_search_path_sql
from app.database import TenantSession, engine
from app.models.tenant import Tenant
from app.schemas.platform import TenantCreateRequest
from app.services.tenant_schema_diff import load_snapshot_manifest

REVISION = "tv005_agent_task_attachments"
PREDECESSOR_REVISION = "tv004_agent_readonly_controls"
EARLIER_PREDECESSOR_REVISION = "tv003_agent_readonly_delivery"
ANCESTOR_REVISION = "tv001_business_snapshot"
_PREVIOUSLY_ACTIVE_SEED_REASON = "previously active tenant seed unavailable; manual review required"
_SAFE_FAILURE_REASONS = frozenset({
    "partial or unknown tenant schema; manual review required",
    "tenant migration version or DDL incomplete",
    "tenant schema revision is not current",
    "tenant schema does not match reviewed business snapshot",
    "partial tenant seed; manual review required",
    _PREVIOUSLY_ACTIVE_SEED_REASON,
    "matching admin bootstrap credentials required",
    "tenant seed incomplete",
    "tenant has active transactions",
})

_OWNER_KEY = "_tenant_maintenance_owner"
_LOCK_SQL = """
    SELECT EXISTS (SELECT 1 FROM pg_locks
    WHERE locktype='advisory' AND granted AND pid=pg_backend_pid() AND objsubid=1
      AND database=(SELECT oid FROM pg_database WHERE datname=current_database())
      AND classid=((CAST(:key AS bigint) >> 32) & 4294967295)::oid
      AND objid=(CAST(:key AS bigint) & 4294967295)::oid
      AND mode IN ('ExclusiveLock','ShareLock'))
"""


@dataclass
class MaintenanceAttempt:
    tenant_id: UUID
    schema_name: str
    generation: int
    attempt_id: UUID
    backend_pid: int
    lock_key: int
    origin_status: str | None = None


def _claim(attempt: MaintenanceAttempt) -> tuple:
    if not isinstance(attempt, MaintenanceAttempt) or not isinstance(attempt.tenant_id, UUID) or not isinstance(attempt.attempt_id, UUID):
        raise TenantUnavailable("valid maintenance attempt required")
    try:
        strict_tenant_search_path_sql(attempt.schema_name)
    except ValueError as exc:
        raise TenantUnavailable("invalid tenant schema") from exc
    if attempt.lock_key != stable_tenant_lock_key(attempt.tenant_id):
        raise TenantUnavailable("incorrect tenant advisory lock key")
    return (attempt.tenant_id, attempt.schema_name, attempt.generation,
            attempt.attempt_id, attempt.lock_key, attempt.backend_pid)


def _owner_attempt(connection: AsyncConnection, schema_name: str) -> MaintenanceAttempt:
    """Recover the immutable claim captured at lock acquisition, not mutable caller state."""
    owner = connection.info.get(_OWNER_KEY)
    if owner is None or owner[1] != schema_name:
        raise TenantUnavailable("tenant migration requires its maintenance lock owner")
    return MaintenanceAttempt(tenant_id=owner[0], schema_name=owner[1], generation=owner[2],
                              attempt_id=owner[3], lock_key=owner[4], backend_pid=owner[5])


@dataclass(frozen=True)
class SeedResult:
    admin_user_id: UUID
    factory_id: UUID
    product_line_code: str


class MaintenanceContext:
    """Domain operations only; the physical connection and seed session stay private."""

    def __init__(self, connection: AsyncConnection, attempt: MaintenanceAttempt, *, rebuild_authorized: bool = False):
        self.__connection = connection
        self.__attempt = attempt
        self.__rebuild_authorized = rebuild_authorized

    @property
    def backend_pid(self) -> int:
        return self.__attempt.backend_pid

    @property
    def attempt(self) -> MaintenanceAttempt:
        """Copy of the owner claim for phase bookkeeping; mutation cannot affect the guard."""
        return replace(self.__attempt)

    async def run_migration(self, revision: str) -> str:
        from alembic_tenant import upgrade_tenant

        await bind_maintenance_transaction(self.__connection, self.__attempt)
        result = await upgrade_tenant(self.__connection, self.__attempt.schema_name, revision)
        await self.__connection.commit()
        return result

    async def run_downgrade(self, revision: str) -> str:
        """Internal owner-bound delta rollback; never used by provisioning."""
        from alembic_tenant import _downgrade_tenant

        await bind_maintenance_transaction(self.__connection, self.__attempt)
        result = await _downgrade_tenant(self.__connection, self.__attempt.schema_name, revision)
        await self.__connection.commit()
        return result

    async def compare_schema(self, reference_schema: str, manifest: dict, *, baseline_only: bool = False, predecessor: str | None = None):
        from app.services.tenant_schema_diff import compare_business_schema

        await bind_maintenance_transaction(self.__connection, self.__attempt)
        differences = await compare_business_schema(
            self.__connection, reference_schema, self.__attempt.schema_name, manifest, baseline_only=baseline_only, predecessor=predecessor,
        )
        await self.__connection.commit()
        return differences

    async def schema_state(self) -> str:
        """Distinguish absent/empty/current/partial/unknown from actual catalog state."""
        await bind_maintenance_transaction(self.__connection, self.__attempt)
        schema = self.__attempt.schema_name
        exists = await self.__connection.scalar(text("SELECT to_regnamespace(:schema) IS NOT NULL"),
                                                {"schema": schema})
        if not exists:
            await self.__connection.commit()
            return "absent"
        rows = (await self.__connection.execute(text("""
            SELECT relname AS name FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=:schema AND c.relkind IN ('r','p','v','m','S','f')
            UNION ALL SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
            WHERE n.nspname=:schema AND t.typtype IN ('e','d')
            UNION ALL SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname=:schema
            UNION ALL SELECT cfg.cfgname FROM pg_ts_config cfg
            JOIN pg_namespace n ON n.oid=cfg.cfgnamespace WHERE n.nspname=:schema
        """), {"schema": schema})).scalars().all()
        if "tenant_schema_version" not in rows:
            result = "empty" if not rows else "partial"
        else:
            versions = (await self.__connection.execute(text(
                f'SELECT version_num FROM "{schema}".tenant_schema_version'))).scalars().all()
            if versions == [REVISION]:
                result = "current"
            elif versions == [PREDECESSOR_REVISION]:
                result = "predecessor"
            elif versions == [EARLIER_PREDECESSOR_REVISION]:
                result = "earlier_predecessor"
            elif versions == [ANCESTOR_REVISION]:
                result = "ancestor"
            elif not versions and set(rows) == {"tenant_schema_version"}:
                result = "empty"
            else:
                result = "unknown" if versions else "partial"
        await self.__connection.commit()
        return result

    async def create_schema(self) -> None:
        await bind_maintenance_transaction(self.__connection, self.__attempt)
        await self.__connection.execute(text(f'CREATE SCHEMA "{self.__attempt.schema_name}"'))
        await self.__connection.commit()

    async def seed_state(self) -> str:
        """No seed rows means retryable; ANY partial set is not silently overwritten."""
        async with _maintenance_seed_session(self.__connection, self.__attempt) as session:
            return await _read_seed_state(session)

    async def seed_tenant(self, request: TenantCreateRequest, *,
                          before_commit_hook: Callable[[str], None] | None = None) -> SeedResult:
        """One guarded tenant transaction, committing every initial row together."""
        from app.services.tenant_service import (
            _seed_roles_and_permissions, _seed_default_factory_and_product_line, _seed_first_admin,
        )
        async with _maintenance_seed_session(self.__connection, self.__attempt) as session:
            async with session.begin():
                slug = await session.scalar(text("SELECT slug FROM public.tenants WHERE id=:id"),
                                            {"id": self.__attempt.tenant_id})
                if slug != request.slug:
                    raise TenantUnavailable("bootstrap slug does not match tenant")
                await _seed_roles_and_permissions(session)
                factory, line = await _seed_default_factory_and_product_line(session)
                admin = await _seed_first_admin(session, request, factory.id, line.code)
                result = SeedResult(admin.user_id, factory.id, line.code)
                if before_commit_hook:
                    before_commit_hook("seed_precommit")
        return result

    async def verify_isolation(self) -> None:
        await bind_maintenance_transaction(self.__connection, self.__attempt)
        actual = await self.__connection.scalar(text("SELECT current_schema()"))
        if actual != self.__attempt.schema_name:
            raise TenantUnavailable("tenant search path is not isolated")
        await self.__connection.commit()

    async def require_rebuild_quiescence(self) -> None:
        from app.services.tenant_offline import require_no_other_clients, require_test_database
        await bind_maintenance_transaction(self.__connection, self.__attempt)
        await require_test_database(self.__connection)
        await require_no_other_clients(self.__connection)
        await self.__connection.commit()

    async def reset_test_schema(self, *, slug: str, schema_name: str, previous_generation: int,
                                after_drop: Callable[[AsyncConnection], Awaitable[None]] | None = None) -> None:
        """Reset only the exact owner schema after the test-only gates and idle recheck."""
        import os
        from app.config import settings
        from app.services.tenant_offline import require_no_other_clients, require_test_database
        if not self.__rebuild_authorized:
            raise PermissionError("explicit rebuild authorization required")
        if settings.TENANT_MODE == "production" or os.getenv("ALLOW_TEST_TENANT_REBUILD") != "1":
            raise PermissionError("test-only rebuild disabled")
        if (schema_name != self.__attempt.schema_name or schema_name != slug_to_schema_name(slug)
                or previous_generation + 1 != self.__attempt.generation):
            raise TenantUnavailable("rebuild target changed")
        await bind_maintenance_transaction(self.__connection, self.__attempt)
        actual_slug = await self.__connection.scalar(text("SELECT slug FROM public.tenants WHERE id=:id"),
                                                     {"id": self.__attempt.tenant_id})
        if actual_slug != slug:
            raise TenantUnavailable("rebuild target changed")
        await require_test_database(self.__connection)
        await require_no_other_clients(self.__connection)
        await _require_reset_dependency_isolation(self.__connection, schema_name)
        await self.__connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        if after_drop is not None:
            await after_drop(self.__connection)
        await self.__connection.commit()

    async def record_rebuild_phase(self, phase: str, *, active: bool = False) -> None:
        """Coordinator bookkeeping; it verifies revision/parity before activation."""
        if phase not in {"schema_created", "migrated", "seeded", "verified", "active"} or active != (phase == "active"):
            raise ValueError("invalid rebuild phase")
        await bind_maintenance_transaction(self.__connection, self.__attempt)
        if active:
            if await self.seed_state() != "complete":
                raise TenantUnavailable("tenant seed incomplete")
            await self.verify_isolation()
            await bind_maintenance_transaction(self.__connection, self.__attempt)
        await self.__connection.execute(text("""
            UPDATE public.tenants SET provisioning_step=:phase,
                status=CASE WHEN :active THEN 'active' ELSE status END,
                provisioning_error=CASE WHEN :active THEN NULL ELSE provisioning_error END
            WHERE id=:id AND provisioning_attempt_id=:attempt AND generation=:generation
        """), {"id": self.__attempt.tenant_id, "attempt": self.__attempt.attempt_id,
               "generation": self.__attempt.generation, "phase": phase, "active": active})
        await self.__connection.commit()

    async def record_rebuild_failure(self, reason: str) -> None:
        """A failed rebuild can only retry through the explicitly guarded rebuild path."""
        if reason not in {"rebuild_failed", "services_not_offline", "database_not_quiescent", "target_changed", "external_schema_dependency"}:
            reason = "rebuild_failed"
        await self.__connection.rollback()
        await bind_maintenance_transaction(self.__connection, self.__attempt)
        await self.__connection.execute(text("""
            UPDATE public.tenants SET status='failed', provisioning_step=:step, provisioning_error=:error
            WHERE id=:id AND provisioning_attempt_id=:attempt AND generation=:generation
        """), {"id": self.__attempt.tenant_id, "attempt": self.__attempt.attempt_id,
               "generation": self.__attempt.generation, "step": "rebuild_failed:" + reason,
               "error": f"TenantUnavailable: {_PREVIOUSLY_ACTIVE_SEED_REASON}"})
        await self.__connection.commit()


async def _require_reset_dependency_isolation(connection: AsyncConnection, schema_name: str) -> None:
    """CASCADE must not reach public/another tenant or an unidentifiable global object.

    Follow reverse dependencies from the namespace, including indirect view,
    trigger and constraint dependencies. TOAST objects are table internals.
    """
    external = await connection.scalar(text("""
        WITH RECURSIVE dropped(classid,objid) AS (
            SELECT 'pg_catalog.pg_namespace'::pg_catalog.regclass::pg_catalog.oid,n.oid
            FROM pg_catalog.pg_namespace n WHERE n.nspname=:schema
            UNION
            SELECT d.classid,d.objid FROM pg_catalog.pg_depend d
            JOIN dropped o ON d.refclassid=o.classid AND d.refobjid=o.objid
        ), identified AS (
            SELECT o.classid,o.objid,CASE
                WHEN o.classid='pg_catalog.pg_rewrite'::pg_catalog.regclass THEN
                    (SELECT n.nspname FROM pg_catalog.pg_rewrite r
                     JOIN pg_catalog.pg_class c ON c.oid=r.ev_class
                     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE r.oid=o.objid)
                WHEN o.classid='pg_catalog.pg_trigger'::pg_catalog.regclass THEN
                    (SELECT n.nspname FROM pg_catalog.pg_trigger t
                     JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
                     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE t.oid=o.objid)
                WHEN o.classid='pg_catalog.pg_attrdef'::pg_catalog.regclass THEN
                    (SELECT n.nspname FROM pg_catalog.pg_attrdef a
                     JOIN pg_catalog.pg_class c ON c.oid=a.adrelid
                     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE a.oid=o.objid)
                WHEN o.classid='pg_catalog.pg_constraint'::pg_catalog.regclass THEN
                    (SELECT n.nspname FROM pg_catalog.pg_constraint c
                     JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace WHERE c.oid=o.objid)
                WHEN o.classid='pg_catalog.pg_policy'::pg_catalog.regclass THEN
                    (SELECT n.nspname FROM pg_catalog.pg_policy p
                     JOIN pg_catalog.pg_class c ON c.oid=p.polrelid
                     JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE p.oid=o.objid)
                ELSE identity.schema END AS object_schema
            FROM dropped o
            CROSS JOIN LATERAL pg_catalog.pg_identify_object(o.classid,o.objid,0) identity
            WHERE o.classid<>'pg_catalog.pg_namespace'::pg_catalog.regclass
        ) SELECT EXISTS (SELECT 1 FROM identified
            WHERE object_schema IS NULL OR object_schema NOT IN (:schema,'pg_toast'))
    """), {"schema": schema_name})
    if external:
        raise TenantUnavailable("external schema dependency")


@asynccontextmanager
async def maintenance_connection(engine: AsyncEngine, attempt: MaintenanceAttempt | UUID,
                                 *, after_lock_hook: Callable[[str], None] | None = None,
                                 rebuild_precondition: tuple | None = None):
    """Own one session lock across DDL, seed and parity; invalidate uncertain owners.

    UUID entry acquires the lock BEFORE changing attempt ID/generation. The
    legacy explicit-attempt entry is retained for narrowly scoped owner tests.
    """
    tenant_id = attempt if isinstance(attempt, UUID) else attempt.tenant_id
    if rebuild_precondition is not None and not isinstance(attempt, UUID):
        raise PermissionError("rebuild requires a fresh owner attempt")
    if not isinstance(attempt, UUID):
        _claim(attempt)
        if attempt.backend_pid != 0:
            raise TenantUnavailable("maintenance attempt already has an owner")
    lock_key = stable_tenant_lock_key(tenant_id)
    async with engine.connect() as connection:
        # A canceled preflight could otherwise return a previously locked
        # backend to the pool before its contamination can be inspected.
        state = "uncertain"
        info = None
        try:
            # A pooled backend may retain a session lock from another borrower.
            # pg_try_advisory_lock is reentrant on that backend, so checking
            # after acquisition would silently leak one lock count on release.
            if await connection.scalar(text(_LOCK_SQL), {"key": lock_key}):
                await connection.invalidate()
                state = "not_started"
                raise TenantUnavailable("pre-held tenant maintenance lock on pooled connection")
            state = "uncertain"
            held = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"),
                                           {"key": lock_key})
            if not held:
                state = "not_started"
                raise TenantUnavailable("tenant has active transactions")
            state = "held"
            info = connection.info
            if after_lock_hook:
                after_lock_hook("lock_acquired")
            if isinstance(attempt, UUID):
                # The ONLY mutation of an attempt happens under this owner.
                attempt = await begin_new_attempt(connection, tenant_id, rebuild_precondition=rebuild_precondition)
            attempt.backend_pid = await connection.scalar(text("SELECT pg_backend_pid()"))
            info[_OWNER_KEY] = _claim(attempt)
            await connection.commit()  # session lock survives transaction commit
            await bind_maintenance_transaction(connection, attempt)
            await connection.commit()  # no unguarded initial transaction escapes
            yield MaintenanceContext(connection, attempt, rebuild_authorized=rebuild_precondition is not None)
        except BaseException:
            if state == "uncertain":
                # Cancellation may arrive after PostgreSQL acquired the lock
                # but before the await returned. Never check such a backend in.
                await connection.invalidate()
                state = "not_started"
            raise
        finally:
            if info is not None:
                info.pop(_OWNER_KEY, None)
            if state == "held":
                if connection.invalidated:
                    # A severed backend already released its session locks.
                    pass
                else:
                    try:
                        if connection.in_transaction():
                            await connection.rollback()
                        released = await connection.scalar(text("SELECT pg_advisory_unlock(:key)"),
                                                           {"key": lock_key})
                        if not released or await connection.scalar(text(_LOCK_SQL), {"key": lock_key}):
                            raise TenantUnavailable("maintenance lock release failed or remains held")
                        await connection.rollback()
                    except BaseException:
                        # Includes cancellation during release and SQL errors.
                        # Never return a potentially locked backend to the pool.
                        await connection.invalidate()
                        raise


def _bind_maintenance_sync(connection: Connection, attempt: MaintenanceAttempt) -> None:
    """Recheck registry, backend PID and actual session-lock owner before path binding."""
    claim = _claim(attempt)
    if connection.info.get(_OWNER_KEY) != claim:
        raise TenantUnavailable("maintenance connection is not the attempt owner")
    row = connection.execute(text("""
        SELECT status, generation, schema_name, provisioning_attempt_id
        FROM public.tenants WHERE id=:id FOR SHARE
    """), {"id": attempt.tenant_id}).one_or_none()
    if (row is None or row.status not in ("provisioning", "maintenance")
            or row.generation != attempt.generation or row.schema_name != attempt.schema_name
            or row.provisioning_attempt_id != attempt.attempt_id):
        raise TenantUnavailable("maintenance attempt, generation, status, or schema changed")
    pid = connection.scalar(text("SELECT pg_backend_pid()"))
    if pid != attempt.backend_pid:
        raise TenantUnavailable("maintenance backend changed")
    owns_lock = connection.scalar(text("""
        SELECT EXISTS (SELECT 1 FROM pg_locks
        WHERE locktype='advisory' AND mode='ExclusiveLock' AND granted
          AND pid=pg_backend_pid() AND objsubid=1
          AND database=(SELECT oid FROM pg_database WHERE datname=current_database())
          AND classid=((CAST(:key AS bigint) >> 32) & 4294967295)::oid
          AND objid=(CAST(:key AS bigint) & 4294967295)::oid)
    """), {"key": attempt.lock_key})
    if not owns_lock:
        raise TenantUnavailable("maintenance lock ownership lost")
    connection.exec_driver_sql(strict_tenant_search_path_sql(attempt.schema_name))


async def bind_maintenance_transaction(connection: AsyncConnection, attempt: MaintenanceAttempt) -> None:
    """Bind an internal DDL/seed/parity transaction on the original owner."""
    await connection.run_sync(_bind_maintenance_sync, attempt)


class _MaintenanceSeedSession(Session):
    """Task 4's private seed session rechecks owner on each transaction."""

    def __init__(self, *args, attempt: MaintenanceAttempt, **kwargs):
        super().__init__(*args, **kwargs)
        self.info["maintenance_attempt"] = attempt


@event.listens_for(_MaintenanceSeedSession, "after_begin")
def _bind_seed_transaction(session: Session, transaction, connection: Connection) -> None:
    if not transaction.nested:
        _bind_maintenance_sync(connection, session.info["maintenance_attempt"])


def _maintenance_seed_session(connection: AsyncConnection, attempt: MaintenanceAttempt) -> AsyncSession:
    """Task 4 uses only inside seed_tenant; never return this session to callers."""
    return AsyncSession(bind=connection, sync_session_class=_MaintenanceSeedSession,
                        attempt=attempt, expire_on_commit=False)


async def _read_seed_state(session: AsyncSession) -> str:
    """Shared invariants under either a guarded maintenance or active transaction."""
    from app.services.tenant_service import _ROLES, _PERMISSION_MODULES
    counts = (await session.execute(text("""
        SELECT (SELECT count(*) FROM role_definitions),
               (SELECT count(*) FROM role_permissions),
               (SELECT count(*) FROM factories),
               (SELECT count(*) FROM product_lines),
               (SELECT count(*) FROM users),
               (SELECT count(*) FROM user_factories),
               (SELECT count(*) FROM user_product_lines)
    """))).one()
    if all(count == 0 for count in counts):
        return "empty"
    # Initial records are a minimum, not a census. Active tenants can add users,
    # factories, lines and roles, and authorized permissions may change levels.
    # A nonempty but missing bootstrap relationship remains a partial seed.
    consistent = await session.scalar(text("""
        SELECT EXISTS (SELECT 1 FROM users u
            JOIN role_definitions r ON r.id=u.role_id AND r.role_key='admin'
            JOIN factories f ON f.id=u.factory_id AND f.code='DEFAULT' AND f.is_active
            JOIN user_factories uf ON uf.user_id=u.user_id AND uf.factory_id=f.id
            JOIN product_lines pl ON pl.factory_id=f.id AND pl.code='DC-DC-100' AND pl.is_active
            JOIN user_product_lines upl ON upl.user_id=u.user_id AND upl.product_line_code=pl.code
            WHERE u.is_active AND u.password_hash IS NOT NULL AND u.password_hash <> '')
    """))
    roles = (await session.execute(text("SELECT role_key FROM role_definitions"))).scalars().all()
    permissions = (await session.execute(text("""
        SELECT r.role_key, p.module FROM role_permissions p
        JOIN role_definitions r ON r.id=p.role_id
    """))).all()
    present = set(permissions)
    required = {(role[0], module) for role in _ROLES for module in _PERMISSION_MODULES}
    return ("complete" if consistent and {role[0] for role in _ROLES} <= set(roles)
            and required <= present else "partial")


async def lock_platform_tenant_row(connection: AsyncConnection, tenant_id: UUID, *, rebuild_precondition: tuple | None = None):
    """Lock the registry row only after the caller owns its exclusive session lock."""
    row = (await connection.execute(text("""
        SELECT id, slug, schema_name, status, generation, provisioning_attempt_id,
               provisioning_error
        FROM public.tenants WHERE id=:id FOR UPDATE
    """), {"id": tenant_id})).one_or_none()
    if row is None or row.schema_name != slug_to_schema_name(row.slug):
        raise TenantUnavailable("tenant registry or canonical schema unavailable")
    if row.status not in {"pending", "provisioning", "failed", "active", "maintenance"}:
        raise TenantUnavailable("tenant status does not permit migration")
    if rebuild_precondition is not None:
        # Validate captured state BEFORE changing generation, including a rival's
        # attempt identity. A test reset is the only explicit manual-review bypass.
        import os
        from app.config import settings
        from app.services.tenant_offline import require_test_database
        if settings.TENANT_MODE == "production" or os.getenv("ALLOW_TEST_TENANT_REBUILD") != "1":
            raise PermissionError("test-only rebuild disabled")
        await require_test_database(connection)
        if (row.id, row.slug, row.schema_name, row.generation, row.status, row.provisioning_attempt_id) != rebuild_precondition:
            raise TenantUnavailable("rebuild target changed")
        return row
    if row.provisioning_error == f"TenantUnavailable: {_PREVIOUSLY_ACTIVE_SEED_REASON}":
        raise TenantUnavailable(_PREVIOUSLY_ACTIVE_SEED_REASON)
    return row


async def begin_new_attempt(connection: AsyncConnection, tenant_id: UUID, *, rebuild_precondition: tuple | None = None) -> MaintenanceAttempt:
    """Persist a fresh attempt under the session-lock owner's FOR UPDATE row lock."""
    row = await lock_platform_tenant_row(connection, tenant_id, rebuild_precondition=rebuild_precondition)
    new_id = uuid4()
    generation = row.generation + 1
    await connection.execute(text("""
        UPDATE public.tenants SET status=:status, generation=:generation,
            provisioning_attempt_id=:attempt, provisioning_step=:step,
            provisioning_error=:error WHERE id=:id
    """), {"status": "maintenance" if row.status == "active" or rebuild_precondition is not None else "provisioning",
           "generation": generation, "attempt": new_id, "id": tenant_id,
           "step": "rebuild_claimed" if rebuild_precondition is not None else "registered",
           "error": (f"TenantUnavailable: {_PREVIOUSLY_ACTIVE_SEED_REASON}"
                     if rebuild_precondition is not None else None)})
    await connection.commit()
    return MaintenanceAttempt(tenant_id, row.schema_name, generation, new_id, 0,
                              stable_tenant_lock_key(tenant_id), row.status)


async def _platform_step(attempt: MaintenanceAttempt, phase: str, *, status: str | None = None):
    values = {"id": attempt.tenant_id, "attempt": attempt.attempt_id,
              "generation": attempt.generation, "phase": phase}
    sql = "UPDATE public.tenants SET provisioning_step=:phase"
    if status:
        sql += ", status=:status"
        values["status"] = status
    sql += (" WHERE id=:id AND provisioning_attempt_id=:attempt "
            "AND generation=:generation AND status IN ('provisioning','maintenance')")
    async with engine.begin() as connection:
        result = await connection.execute(text(sql), values)
        if result.rowcount != 1:
            raise TenantUnavailable("tenant attempt changed before phase update")


async def _record_failure(attempt: MaintenanceAttempt, exc: Exception):
    # Never persist arbitrary str(exc): database diagnostics and application
    # exceptions can contain the bootstrap password. Only vetted reasons pass.
    reason = str(exc) if type(exc) is TenantUnavailable and str(exc) in _SAFE_FAILURE_REASONS else None
    async with engine.begin() as connection:
        await connection.execute(text("""
            UPDATE public.tenants SET status='failed', provisioning_error=:error
            WHERE id=:id AND generation=:generation AND provisioning_attempt_id=:attempt
        """), {"error": f"TenantUnavailable: {reason}" if reason else type(exc).__name__,
               "id": attempt.tenant_id,
               "generation": attempt.generation, "attempt": attempt.attempt_id})


async def _load_tenant(tenant_id: UUID) -> Tenant:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await session.execute(text("SET LOCAL search_path TO public, pg_catalog"))
        tenant = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
        if tenant is None:
            raise TenantUnavailable("tenant not found")
        return tenant


async def _active_current(tenant: Tenant) -> bool:
    """Read-only active fast path behind the normal shared lock and strict path.

    A stale captured generation, maintenance lock, or status change raises;
    pending/failed tenants never enter this ordinary business transaction.
    """
    if tenant.status != "active":
        return False
    from app.services.tenant_schema_diff import compare_business_schema

    binding = TenantBinding(tenant.id, tenant.schema_name, tenant.generation, "business")
    async with AsyncSession(bind=engine, sync_session_class=TenantSession,
                            binding=binding, expire_on_commit=False) as session:
        # TenantSession.after_begin enforces shared lock, active status and
        # generation before the first catalog or tenant-business query.
        schema = await session.scalar(text("SELECT current_schema()"))
        if schema != tenant.schema_name:
            raise TenantUnavailable("tenant active read was not isolated")
        version_table = f"{schema}.tenant_schema_version"
        if not await session.scalar(text("SELECT to_regclass(:name) IS NOT NULL"),
                                    {"name": version_table}):
            return False
        versions = (await session.execute(text(
            f'SELECT version_num FROM "{schema}".tenant_schema_version'))).scalars().all()
        if versions != [REVISION]:
            return False
        connection = await session.connection()  # private, never returned to caller
        if await compare_business_schema(connection, "public", schema, load_snapshot_manifest()):
            return False
        if await _read_seed_state(session) != "complete":
            return False
        # Check the registry again at the linearization point. A later update
        # cannot invalidate an already-running shared-locked read transaction.
        current = (await session.execute(text("""
            SELECT status,generation,schema_name FROM public.tenants WHERE id=:id FOR SHARE
        """), {"id": tenant.id})).one_or_none()
        if (current is None or current.status != "active"
                or current.generation != tenant.generation
                or current.schema_name != tenant.schema_name):
            raise TenantUnavailable("tenant changed during active verification")
        return True


async def schema_is_current(maintenance: MaintenanceContext) -> bool:
    return await maintenance.schema_state() == "current"


async def create_schema_if_absent(maintenance: MaintenanceContext, attempt: MaintenanceAttempt):
    state = await maintenance.schema_state()
    if state == "absent":
        await maintenance.create_schema()
    elif state not in {"empty", "current", "ancestor", "predecessor", "earlier_predecessor"}:
        raise TenantUnavailable("partial or unknown tenant schema; manual review required")


async def migrate_if_needed(maintenance: MaintenanceContext, attempt: MaintenanceAttempt):
    state = await maintenance.schema_state()
    if state == "ancestor":
        if await maintenance.compare_schema("public", load_snapshot_manifest(), baseline_only=True):
            raise TenantUnavailable("partial or unknown tenant schema; manual review required")
        await maintenance.run_migration(REVISION)
    elif state in {"predecessor", "earlier_predecessor"}:
        predecessor = PREDECESSOR_REVISION if state == "predecessor" else EARLIER_PREDECESSOR_REVISION
        if await maintenance.compare_schema("public", load_snapshot_manifest(), predecessor=predecessor):
            raise TenantUnavailable("partial or unknown tenant schema; manual review required")
        await maintenance.run_migration(REVISION)
    elif state == "empty":
        await maintenance.run_migration(REVISION)
    elif state != "current":
        raise TenantUnavailable("tenant migration version or DDL incomplete")


async def require_schema_parity(maintenance: MaintenanceContext, attempt: MaintenanceAttempt):
    if not await schema_is_current(maintenance):
        raise TenantUnavailable("tenant schema revision is not current")
    differences = await maintenance.compare_schema("public", load_snapshot_manifest())
    if differences:
        raise TenantUnavailable("tenant schema does not match reviewed business snapshot")


async def seed_invariants_complete(maintenance: MaintenanceContext, attempt: MaintenanceAttempt) -> bool:
    state = await maintenance.seed_state()
    if state == "partial":
        raise TenantUnavailable("partial tenant seed; manual review required")
    return state == "complete"


async def seed_all_in_one_transaction(maintenance: MaintenanceContext, attempt: MaintenanceAttempt,
                                      bootstrap_request: TenantCreateRequest | None,
                                      before_commit_hook: Callable[[str], None] | None = None) -> None:
    tenant = await _load_tenant(attempt.tenant_id)
    if bootstrap_request is None or bootstrap_request.slug != tenant.slug:
        raise TenantUnavailable("matching admin bootstrap credentials required")
    await maintenance.seed_tenant(bootstrap_request, before_commit_hook=before_commit_hook)


async def verify_seed_and_isolation(maintenance: MaintenanceContext, attempt: MaintenanceAttempt):
    if not await seed_invariants_complete(maintenance, attempt):
        raise TenantUnavailable("tenant seed incomplete")
    await maintenance.verify_isolation()


async def mark_active(maintenance: MaintenanceContext, attempt: MaintenanceAttempt):
    # Recheck the owner before final platform write, then release its row lock.
    await maintenance.verify_isolation()
    await _platform_step(attempt, "active", status="active")


async def provision_new(request: TenantCreateRequest, *,
                        after_stage_hook: Callable[[str], None] | None = None) -> Tenant:
    """Register the stable tenant ID once; password remains only in request memory."""
    from sqlalchemy.exc import IntegrityError
    schema_name = slug_to_schema_name(request.slug)
    tenant_id = uuid4()
    async with engine.begin() as connection:
        try:
            await connection.execute(text("""
                INSERT INTO public.tenants (id,name,slug,subdomain,schema_name,plan,status,generation,
                                            provisioning_step)
                VALUES (:id,:name,:slug,:subdomain,:schema,:plan,'pending',0,'registered')
            """), {"id": tenant_id, "name": request.name, "slug": request.slug,
                   "subdomain": request.subdomain or request.slug, "schema": schema_name,
                   "plan": request.plan or "free"})
        except IntegrityError as exc:
            raise ValueError("Tenant slug, schema, or subdomain already exists") from exc
    if after_stage_hook:
        after_stage_hook("registration")
    return await resume_tenant(tenant_id, bootstrap_request=request, after_stage_hook=after_stage_hook)


async def resume_tenant(tenant_id: UUID, *, bootstrap_request: TenantCreateRequest | None = None,
                        after_stage_hook: Callable[[str], None] | None = None) -> Tenant:
    """Recover only the registered tenant, reconciling committed schema and seed."""
    tenant = await _load_tenant(tenant_id)
    if await _active_current(tenant):
        return tenant
    attempt = None
    try:
        async with maintenance_connection(engine, tenant_id, after_lock_hook=after_stage_hook) as maintenance:
            attempt = maintenance.attempt
            await create_schema_if_absent(maintenance, attempt)
            await _platform_step(attempt, "schema_created")
            if after_stage_hook:
                after_stage_hook("schema_created")
            await migrate_if_needed(maintenance, attempt)
            if after_stage_hook:
                after_stage_hook("migration_commit")
            await _platform_step(attempt, "migrated")
            await require_schema_parity(maintenance, attempt)
            await _platform_step(attempt, "verified")
            if not await seed_invariants_complete(maintenance, attempt):
                if attempt.origin_status in {"active", "maintenance"}:
                    failure = TenantUnavailable(_PREVIOUSLY_ACTIVE_SEED_REASON)
                    # Persist the manual-review barrier before the exclusive
                    # owner unlocks. Otherwise another resume may see the
                    # transient maintenance status and reseed an old tenant.
                    await _record_failure(attempt, failure)
                    raise failure
                await seed_all_in_one_transaction(maintenance, attempt, bootstrap_request,
                                                  before_commit_hook=after_stage_hook)
                if after_stage_hook:
                    after_stage_hook("seed_commit")
            await _platform_step(attempt, "seeded")
            await verify_seed_and_isolation(maintenance, attempt)
            if after_stage_hook:
                after_stage_hook("final_platform_update")
            await mark_active(maintenance, attempt)
        return await _load_tenant(tenant_id)
    except Exception as exc:
        if attempt is not None:
            await _record_failure(attempt, exc)
        raise
