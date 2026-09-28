"""Internal owner-bound tenant maintenance on one private physical PostgreSQL connection.

Not a provisioning route: Task 4 will move production callers to this coordinator.
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from app.core.tenant_transaction import TenantUnavailable, stable_tenant_lock_key
from app.core.tenant_utils import strict_tenant_search_path_sql

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


class MaintenanceContext:
    """Guarded DDL and catalog operations; Task 4 adds private domain seeding."""

    def __init__(self, connection: AsyncConnection, attempt: MaintenanceAttempt):
        self.__connection = connection
        self.__attempt = attempt

    @property
    def backend_pid(self) -> int:
        return self.__attempt.backend_pid

    async def run_migration(self, revision: str) -> str:
        from alembic_tenant import upgrade_tenant

        await bind_maintenance_transaction(self.__connection, self.__attempt)
        result = await upgrade_tenant(self.__connection, self.__attempt.schema_name, revision)
        await self.__connection.commit()
        return result

    async def compare_schema(self, reference_schema: str, manifest: dict):
        from app.services.tenant_schema_diff import compare_business_schema

        await bind_maintenance_transaction(self.__connection, self.__attempt)
        return await compare_business_schema(
            self.__connection, reference_schema, self.__attempt.schema_name, manifest,
        )


@asynccontextmanager
async def maintenance_connection(engine: AsyncEngine, attempt: MaintenanceAttempt):
    """Own one session lock across DDL, seed and parity; invalidate uncertain owners."""
    _claim(attempt)
    if attempt.backend_pid != 0:
        raise TenantUnavailable("maintenance attempt already has an owner")
    async with engine.connect() as connection:
        # A canceled preflight could otherwise return a previously locked
        # backend to the pool before its contamination can be inspected.
        state = "uncertain"
        info = None
        try:
            # A pooled backend may retain a session lock from another borrower.
            # pg_try_advisory_lock is reentrant on that backend, so checking
            # after acquisition would silently leak one lock count on release.
            if await connection.scalar(text(_LOCK_SQL), {"key": attempt.lock_key}):
                await connection.invalidate()
                state = "not_started"
                raise TenantUnavailable("pre-held tenant maintenance lock on pooled connection")
            state = "uncertain"
            held = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"),
                                           {"key": attempt.lock_key})
            if not held:
                state = "not_started"
                raise TenantUnavailable("tenant has active transactions")
            state = "held"
            info = connection.info
            attempt.backend_pid = await connection.scalar(text("SELECT pg_backend_pid()"))
            info[_OWNER_KEY] = _claim(attempt)
            await connection.commit()  # session lock survives transaction commit
            await bind_maintenance_transaction(connection, attempt)
            await connection.commit()  # no unguarded initial transaction escapes
            yield MaintenanceContext(connection, attempt)
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
                                                           {"key": attempt.lock_key})
                        if not released or await connection.scalar(text(_LOCK_SQL), {"key": attempt.lock_key}):
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
