"""Internal tenant-only Alembic runner; caller owns the physical connection and lock.

This is not a provisioning route or a maintenance authorization mechanism.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.tenant_utils import strict_tenant_search_path_sql
from app.services.tenant_migrator import _owner_attempt, bind_maintenance_transaction
from app.services.tenant_schema_diff import load_snapshot_manifest, verify_snapshot_checksum


REVIEWED_REVISIONS = ("tv001_business_snapshot", "tv002_agent_task_core", "tv003_agent_readonly_delivery", "tv004_agent_readonly_controls")


async def upgrade_tenant(connection: AsyncConnection, schema_name: str, target_revision: str) -> str:
    return await _run_tenant_revision(connection, schema_name, target_revision, downgrade=False)


async def _downgrade_tenant(connection: AsyncConnection, schema_name: str, target_revision: str) -> str:
    """Internal owned delta rollback; the irreversible baseline cannot be removed."""
    return await _run_tenant_revision(connection, schema_name, target_revision, downgrade=True)


async def _run_tenant_revision(connection: AsyncConnection, schema_name: str, target_revision: str, *, downgrade: bool) -> str:
    strict_tenant_search_path_sql(schema_name)
    # No unowned migration entry: even internal/test callers must carry the
    # original exclusive owner through the same injected physical connection.
    attempt = _owner_attempt(connection, schema_name)
    await bind_maintenance_transaction(connection, attempt)
    if target_revision not in REVIEWED_REVISIONS:
        raise ValueError(f"Unknown tenant revision: {target_revision}")
    verify_snapshot_checksum(load_snapshot_manifest())
    if not await connection.scalar(text("SELECT to_regnamespace(:schema)"), {"schema": schema_name}):
        raise ValueError(f"Tenant schema does not exist: {schema_name}")
    if downgrade:
        versions = (await connection.execute(text(
            f'SELECT version_num FROM "{schema_name}".tenant_schema_version'))).scalars().all()
        if (len(versions) != 1 or versions[0] not in REVIEWED_REVISIONS
                or REVIEWED_REVISIONS.index(target_revision) >= REVIEWED_REVISIONS.index(versions[0])):
            raise ValueError("Only the reviewed tenant delta can be downgraded")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic_tenant.ini"))
    config.attributes["schema_name"] = schema_name
    config.attributes["maintenance_attempt"] = attempt
    def run(sync_connection):
        config.attributes["connection"] = sync_connection
        (command.downgrade if downgrade else command.upgrade)(config, target_revision)

    await connection.run_sync(run)
    return target_revision
