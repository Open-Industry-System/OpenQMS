"""Internal, owner-bound tenant maintenance on one physical PostgreSQL connection.

Not a production entry point: Task 4 will move provisioning/CLI to this primitive.
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


@asynccontextmanager
async def maintenance_connection(engine: AsyncEngine, attempt: MaintenanceAttempt):
    """Hold the exclusive session lock on this connection across every commit."""
    _claim(attempt)
    if attempt.backend_pid != 0:
        raise TenantUnavailable("maintenance attempt already has an owner")
    async with engine.connect() as connection:
        held = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": attempt.lock_key})
        if not held:
            raise TenantUnavailable("tenant has active transactions")
        info = connection.info
        try:
            attempt.backend_pid = await connection.scalar(text("SELECT pg_backend_pid()"))
            info[_OWNER_KEY] = _claim(attempt)
            await connection.commit()  # acquisition query's implicit transaction is finished; session lock persists
            await bind_maintenance_transaction(connection, attempt)
            yield connection
        finally:
            info.pop(_OWNER_KEY, None)
            # A failed statement can leave the transaction aborted. Roll it back
            # before unlocking; dropping the physical connection is also fail-closed.
            if connection.in_transaction():
                await connection.rollback()
            if not connection.invalidated:
                try:
                    await connection.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": attempt.lock_key})
                finally:
                    if connection.in_transaction():
                        await connection.rollback()


def _bind_maintenance_sync(connection: Connection, attempt: MaintenanceAttempt) -> None:
    """Recheck the registry AND actual session-lock owner before setting a tenant path."""
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
    """Begin/rebind each DDL, seed, or parity transaction on the original owner."""
    await connection.run_sync(_bind_maintenance_sync, attempt)


class MaintenanceSeedSession(Session):
    """Bound-only seed session: recheck owner on each transaction after commits."""

    def __init__(self, *args, attempt: MaintenanceAttempt, **kwargs):
        super().__init__(*args, **kwargs)
        self.info["maintenance_attempt"] = attempt


@event.listens_for(MaintenanceSeedSession, "after_begin")
def _bind_seed_transaction(session: Session, transaction, connection: Connection) -> None:
    if not transaction.nested:
        _bind_maintenance_sync(connection, session.info["maintenance_attempt"])


def maintenance_seed_session(connection: AsyncConnection, attempt: MaintenanceAttempt) -> AsyncSession:
    """Session pinned to the owner connection, never to the engine's pool."""
    return AsyncSession(bind=connection, sync_session_class=MaintenanceSeedSession,
                        attempt=attempt, expire_on_commit=False)
