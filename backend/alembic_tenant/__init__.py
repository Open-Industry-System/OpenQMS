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


async def upgrade_tenant(connection: AsyncConnection, schema_name: str, target_revision: str) -> str:
    strict_tenant_search_path_sql(schema_name)
    # No unowned migration entry: even internal/test callers must carry the
    # original exclusive owner through the same injected physical connection.
    attempt = _owner_attempt(connection, schema_name)
    await bind_maintenance_transaction(connection, attempt)
    if target_revision != "tv001_business_snapshot":
        raise ValueError(f"Unknown tenant revision: {target_revision}")
    verify_snapshot_checksum(load_snapshot_manifest())
    if not await connection.scalar(text("SELECT to_regnamespace(:schema)"), {"schema": schema_name}):
        raise ValueError(f"Tenant schema does not exist: {schema_name}")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic_tenant.ini"))
    config.attributes["schema_name"] = schema_name
    config.attributes["maintenance_attempt"] = attempt
    def run(sync_connection):
        config.attributes["connection"] = sync_connection
        command.upgrade(config, target_revision)

    await connection.run_sync(run)
    return target_revision
