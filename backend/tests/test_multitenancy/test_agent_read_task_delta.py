"""No-DB contract tests for the reviewed tenant read-task delta."""
from unittest.mock import AsyncMock

import pytest

from app.core.tenant_transaction import TenantUnavailable
from app.services import tenant_migrator, tenant_schema_diff

TARGET = "tv006_agent_read_tasks"


def test_read_tasks_are_reviewed_current_target():
    from alembic_tenant import REVIEWED_REVISIONS

    assert tenant_migrator.REVISION == TARGET
    assert tenant_migrator.PREDECESSOR_REVISION == "tv005_agent_task_attachments"
    assert REVIEWED_REVISIONS[-2:] == ("tv005_agent_task_attachments", TARGET)


@pytest.mark.asyncio
@pytest.mark.parametrize("state,predecessor", [
    ("empty", None),
    ("predecessor", "tv005_agent_task_attachments"),
    ("earlier_predecessor", "tv004_agent_readonly_controls"),
    ("earliest_predecessor", "tv003_agent_readonly_delivery"),
    ("core_predecessor", "tv002_agent_task_core"),
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
    maintenance.schema_state.return_value = "predecessor"
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
