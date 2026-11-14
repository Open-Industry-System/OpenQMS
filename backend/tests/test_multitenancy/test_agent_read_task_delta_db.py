"""Owned PostgreSQL acceptance for fresh and tv005 tenant read-task upgrades.

These require mig_db_url; never run them in the no-DB pure lane.
"""
import asyncio
from pathlib import Path
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.schemas.platform import TenantCreateRequest
from app.services import tenant_migrator
from app.services.tenant_schema_diff import load_snapshot_manifest


@pytest.mark.asyncio
@pytest.mark.parametrize("predecessor", [None, "tv005_agent_task_attachments", "tv009_r4b_main_merge"], ids=["fresh", "tv005-existing", "tv009-existing"])
async def test_read_task_delta_owned_tenant_paths(mig_db_url, monkeypatch, predecessor):
    existing = predecessor is not None
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", mig_db_url)
    await asyncio.to_thread(command.upgrade, config,
                            ({"tv005_agent_task_attachments": "20261009_agent_task_attachments",
                              "tv009_r4b_main_merge": "20261114_r4b_main_merge"}.get(predecessor, "head")))
    engine = create_async_engine(mig_db_url, poolclass=NullPool)
    monkeypatch.setattr(tenant_migrator, "engine", engine)
    target = tenant_migrator.REVISION
    if existing:
        monkeypatch.setattr(tenant_migrator, "REVISION", predecessor)
    try:
        tenant = await tenant_migrator.provision_new(TenantCreateRequest(
            name="Read task delta", slug="read-delta-" + uuid.uuid4().hex[:12],
            admin_email="delta@example.test", admin_password="DeltaTestPassword123",
        ))
        schema = tenant.schema_name
        async with engine.connect() as connection:
            original = (await connection.execute(text(
                f'SELECT to_jsonb(u) FROM "{schema}".users u ORDER BY user_id'
            ))).scalars().all()
            assert bool(await connection.scalar(text("SELECT to_regclass(:name)"),
                                               {"name": f"{schema}.user_refresh_sessions"})) is not existing
        if existing:
            generation = tenant.generation
            await asyncio.to_thread(command.upgrade, config, "head")
            monkeypatch.setattr(tenant_migrator, "REVISION", target)
            tenant = await tenant_migrator.resume_tenant(tenant.id)
            assert tenant.generation == generation + 1
        assert tenant.status == "active"
        async with engine.connect() as connection:
            assert (await connection.execute(text(
                f'SELECT to_jsonb(u) FROM "{schema}".users u ORDER BY user_id'
            ))).scalars().all() == original
            assert await connection.scalar(text(
                f'SELECT version_num FROM "{schema}".tenant_schema_version'
            )) == "tv010_refresh_sessions"
        # The same owner-bound connection performs full parity and the reviewed
        # rollback/reapply; no legacy public-chain tenant runner is involved.
        async with tenant_migrator.maintenance_connection(engine, tenant.id) as maintenance:
            assert await maintenance.compare_schema("public", load_snapshot_manifest()) == []
            await maintenance.run_downgrade("tv005_agent_task_attachments")
            assert await maintenance.schema_state() == "latest_predecessor"
            assert await maintenance.compare_schema(
                "public", load_snapshot_manifest(), predecessor="tv005_agent_task_attachments",
            ) == []
            await maintenance.run_migration("tv006_agent_read_tasks")
            assert await maintenance.schema_state() == "delivery_predecessor"
            assert await maintenance.compare_schema(
                "public", load_snapshot_manifest(), predecessor="tv006_agent_read_tasks",
            ) == []
            await maintenance.run_migration("tv007_d4_text_delivery")
            assert await maintenance.schema_state() == "recovery_predecessor"
            assert await maintenance.compare_schema("public", load_snapshot_manifest(), predecessor="tv007_d4_text_delivery") == []
            await maintenance.run_migration("tv008_d4_recovery")
            assert await maintenance.schema_state() == "recovery_head"
            assert await maintenance.compare_schema("public", load_snapshot_manifest(), predecessor="tv008_d4_recovery") == []
            await maintenance.run_migration("tv009_r4b_main_merge")
            assert await maintenance.schema_state() == "refresh_predecessor"
            assert await maintenance.compare_schema("public", load_snapshot_manifest(), predecessor="tv009_r4b_main_merge") == []
            await maintenance.run_migration("tv010_refresh_sessions")
            assert await maintenance.schema_state() == "current"
            assert await maintenance.compare_schema("public", load_snapshot_manifest()) == []
    finally:
        await engine.dispose()
