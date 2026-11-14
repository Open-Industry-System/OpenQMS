"""No-DB contract tests for the reviewed tenant read-task delta."""
from unittest.mock import AsyncMock

import pytest

from app.core.tenant_transaction import TenantUnavailable
from app.services import tenant_migrator, tenant_schema_diff

TARGET = "tv010_refresh_sessions"


def test_read_tasks_are_reviewed_current_target():
    from alembic_tenant import REVIEWED_REVISIONS

    assert tenant_migrator.REVISION == TARGET
    assert tenant_migrator.LATEST_PREDECESSOR_REVISION == "tv005_agent_task_attachments"
    assert tenant_migrator.PREDECESSOR_REVISION == "tv004_agent_readonly_controls"
    assert tenant_migrator.DELIVERY_PREDECESSOR_REVISION == "tv006_agent_read_tasks"
    assert tenant_migrator.RECOVERY_PREDECESSOR_REVISION == "tv007_d4_text_delivery"
    assert REVIEWED_REVISIONS[-5:] == ("tv007_characteristic_refs", "tv007_d4_text_delivery", "tv008_d4_recovery", "tv009_r4b_main_merge", TARGET)


@pytest.mark.asyncio
@pytest.mark.parametrize("state,predecessor", [
    ("empty", None),
    ("refresh_predecessor", "tv009_r4b_main_merge"),
    ("characteristic_predecessor", "tv007_characteristic_refs"),
    ("recovery_head", "tv008_d4_recovery"),
    ("recovery_predecessor", "tv007_d4_text_delivery"),
    ("delivery_predecessor", "tv006_agent_read_tasks"),
    ("latest_predecessor", "tv005_agent_task_attachments"),
    ("predecessor", "tv004_agent_readonly_controls"),
    ("earlier_predecessor", "tv003_agent_readonly_delivery"),
    ("earliest_predecessor", "tv002_agent_task_core"),
    ("ancestor", None),
])
async def test_fresh_and_reviewed_existing_tenants_upgrade_to_read_tasks(state, predecessor):
    maintenance = AsyncMock()
    maintenance.schema_state.return_value = state
    maintenance.compare_schema.return_value = []
    await tenant_migrator.create_schema_if_absent(maintenance, None)
    await tenant_migrator.migrate_if_needed(maintenance, None)
    maintenance.run_migration.assert_awaited_once_with(TARGET)
    if state == "empty":
        maintenance.compare_schema.assert_not_awaited()
    elif state == "ancestor":
        assert maintenance.compare_schema.await_args.kwargs == {"baseline_only": True}
    else:
        assert maintenance.compare_schema.await_args.kwargs == {"predecessor": predecessor}


@pytest.mark.asyncio
async def test_tv005_parity_failure_does_not_migrate():
    maintenance = AsyncMock()
    maintenance.schema_state.return_value = "latest_predecessor"
    maintenance.compare_schema.return_value = ["unexpected object"]
    with pytest.raises(TenantUnavailable, match="partial or unknown"):
        await tenant_migrator.migrate_if_needed(maintenance, None)
    maintenance.run_migration.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("predecessor", [
    "tv002_agent_task_core", "tv003_agent_readonly_delivery",
    "tv004_agent_readonly_controls", "tv005_agent_task_attachments",
])
async def test_predecessor_parity_filters_read_tasks_only_on_reference(monkeypatch, predecessor):
    objects = {("table", "agent_read_tasks"): "r",
               ("column", "agent_read_tasks.task_id"): "uuid",
               ("constraint", "agent_read_tasks.ck_agent_read_task_status"): "check",
               ("index", "agent_read_tasks.ix_agent_read_tasks_expires_at"): "index"}
    read = AsyncMock(side_effect=[objects, {}])
    monkeypatch.setattr(tenant_schema_diff, "_objects", read)
    assert await tenant_schema_diff.compare_business_schema(
        None, "public", "tenant_delta", tenant_schema_diff.load_snapshot_manifest(),
        predecessor=predecessor,
    ) == []
    # An unreviewed tenant-side object is never hidden by predecessor filtering.
    read.side_effect = [objects, objects]
    differences = await tenant_schema_diff.compare_business_schema(
        None, "public", "tenant_delta", tenant_schema_diff.load_snapshot_manifest(),
        predecessor=predecessor,
    )
    assert len(differences) == len(objects)


@pytest.mark.asyncio
async def test_tv005_parity_keeps_existing_attachment_objects(monkeypatch):
    objects = {("table", "agent_task_attachments"): "r"}
    monkeypatch.setattr(tenant_schema_diff, "_objects", AsyncMock(side_effect=[objects, {}]))
    differences = await tenant_schema_diff.compare_business_schema(
        None, "public", "tenant_delta", tenant_schema_diff.load_snapshot_manifest(),
        predecessor="tv005_agent_task_attachments",
    )
    assert [(diff.object_type, diff.object_key) for diff in differences] == [
        ("table", "agent_task_attachments")]


@pytest.mark.asyncio
async def test_refresh_predecessor_only_filters_new_public_table(monkeypatch):
    existing = ("column", "control_plan_items.source_characteristic_ref")
    added = {("table", "user_refresh_sessions"): "table",
             ("column", "user_refresh_sessions.token_hash"): "varchar64",
             ("constraint", "user_refresh_sessions.user_refresh_sessions_user_id_fkey"): "tenant fk",
             ("index", "user_refresh_sessions.ix_user_refresh_sessions_user_id"): "index"}
    objects = {"public": {existing: "jsonb", **added}, "tenant_delta": {existing: "jsonb"}}
    async def load(connection, schema):
        return objects[schema]
    monkeypatch.setattr(tenant_schema_diff, "_objects", load)
    compare = tenant_schema_diff.compare_business_schema
    manifest = tenant_schema_diff.load_snapshot_manifest()
    assert await compare(None, "public", "tenant_delta", manifest, predecessor="tv009_r4b_main_merge") == []
    assert await compare(None, "public", "tenant_delta", manifest)
    objects["tenant_delta"][("table", "user_refresh_sessions")] = "partial"
    assert await compare(None, "public", "tenant_delta", manifest, predecessor="tv009_r4b_main_merge")
