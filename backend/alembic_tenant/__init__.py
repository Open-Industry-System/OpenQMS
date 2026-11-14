"""Internal tenant-only Alembic runner; caller owns the physical connection and lock.

This is not a provisioning route or a maintenance authorization mechanism.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.tenant_utils import strict_tenant_search_path_sql
from app.services.tenant_migrator import _owner_attempt, bind_maintenance_transaction
from app.services.tenant_schema_diff import load_snapshot_manifest, verify_snapshot_checksum


REVIEWED_REVISIONS = (
    "tv001_business_snapshot", "tv002_agent_task_core", "tv003_agent_readonly_delivery",
    "tv004_agent_readonly_controls", "tv005_agent_task_attachments", "tv006_agent_read_tasks",
    "tv007_characteristic_refs", "tv007_d4_text_delivery", "tv008_d4_recovery", "tv009_r4b_main_merge",
)


async def upgrade_tenant(connection: AsyncConnection, schema_name: str, target_revision: str) -> str:
    return await _run_tenant_revision(connection, schema_name, target_revision, downgrade=False)


async def _downgrade_tenant(connection: AsyncConnection, schema_name: str, target_revision: str) -> str:
    """Internal owned delta rollback; the irreversible baseline cannot be removed."""
    return await _run_tenant_revision(connection, schema_name, target_revision, downgrade=True)


def _is_strict_ancestor(scripts: ScriptDirectory, current: str, target: str) -> bool:
    """Only a reachable reviewed parent can be a downgrade target."""
    if current == target or current not in REVIEWED_REVISIONS or target not in REVIEWED_REVISIONS:
        return False
    pending = [current]
    seen = set()
    while pending:
        revision = pending.pop()
        if revision in seen:
            continue
        seen.add(revision)
        node = scripts.get_revision(revision)
        if node is None:
            return False
        parents = node.down_revision
        if isinstance(parents, str):
            parents = (parents,)
        for parent in parents or ():
            if parent not in REVIEWED_REVISIONS:
                return False
            if parent == target:
                return True
            pending.append(parent)
    return False


def _has_single_downgrade_target(scripts: ScriptDirectory, current: str, target: str) -> bool:
    """Every path below current must reach target before reaching the base."""
    if not _is_strict_ancestor(scripts, current, target):
        return False
    memo = {}

    def reaches(revision, active):
        if revision == target:
            return True
        if revision not in REVIEWED_REVISIONS or revision in active:
            return False
        if revision in memo:
            return memo[revision]
        node = scripts.get_revision(revision)
        if node is None:
            return False
        parents = node.down_revision
        if isinstance(parents, str):
            parents = (parents,)
        result = bool(parents) and all(reaches(parent, active | {revision}) for parent in parents)
        memo[revision] = result
        return result

    return reaches(current, set())


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
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic_tenant.ini"))
    if downgrade:
        versions = (await connection.execute(text(
            f'SELECT version_num FROM "{schema_name}".tenant_schema_version'))).scalars().all()
        if (len(versions) != 1 or not _is_strict_ancestor(
                ScriptDirectory.from_config(config), versions[0], target_revision)):
            raise ValueError("Only the reviewed tenant delta can be downgraded")
        if not _has_single_downgrade_target(ScriptDirectory.from_config(config), versions[0], target_revision):
            raise ValueError("Downgrade must end at a single reviewed tenant revision")
    config.attributes["schema_name"] = schema_name
    config.attributes["maintenance_attempt"] = attempt
    def run(sync_connection):
        config.attributes["connection"] = sync_connection
        (command.downgrade if downgrade else command.upgrade)(config, target_revision)

    await connection.run_sync(run)
    if downgrade:
        versions = (await connection.execute(text(
            f'SELECT version_num FROM "{schema_name}".tenant_schema_version'))).scalars().all()
        if versions != [target_revision]:
            raise RuntimeError("Tenant downgrade did not end at the requested revision")
    return target_revision
