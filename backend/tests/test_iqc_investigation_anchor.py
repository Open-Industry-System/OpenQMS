from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_task import AgentTask
from app.schemas.agent_task import IqcInvestigationCreate
from app.services.agent_runtime import runtime_access, task_service
from tests.test_iqc_investigation_optional import sources  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.requires_db]


async def test_iqc_anchor_does_not_require_capa_and_is_inaccessible_to_legacy_runtime(db, sources):
    inspection, scope, *_ = sources
    actor = scope.user.user_id
    plugin = AgentPluginInstallation(
        installation_id=uuid4(), plugin_key="iqc-anchor-test", plugin_version="1",
        manifest={}, secret_hash="unused", created_by=actor,
    )
    db.add(plugin)
    await db.flush()
    task = AgentTask(
        initiator_id=actor, executor_user_id=actor,
        preferred_installation_id=plugin.installation_id, request_key="iqc-anchor",
        status="ready", task_type="iqc_investigation_advice.v1", factory_id=inspection.factory_id,
        target_iqc_inspection_id=inspection.inspection_id,
    )
    db.add(task)
    await db.flush()
    assert task.target_capa_id is None
    with pytest.raises(PermissionError):
        await runtime_access.authorize_task(db, task, plugin)
    with pytest.raises(LookupError):
        await task_service.get_task_for_control(db, scope, task.task_id)


@pytest.mark.parametrize("invalid", ["both", "missing", "wrong_factory", "wrong_type"])
async def test_iqc_anchor_rejects_invalid_target_shapes(db, sources, invalid):
    inspection, scope, _, _, _, other_factory, _ = sources
    actor = scope.user.user_id
    plugin = AgentPluginInstallation(
        installation_id=uuid4(), plugin_key="iqc-anchor-test", plugin_version="1",
        manifest={}, secret_hash="unused", created_by=actor,
    )
    db.add(plugin)
    await db.flush()
    fields = {
        "initiator_id": actor, "executor_user_id": actor,
        "preferred_installation_id": plugin.installation_id, "request_key": "iqc-anchor",
        "status": "ready", "task_type": "iqc_investigation_advice.v1",
        "factory_id": inspection.factory_id, "target_iqc_inspection_id": inspection.inspection_id,
    }
    expected = "ck_agent_task_typed_anchor"
    if invalid == "both":
        fields["target_capa_id"] = uuid4()
    elif invalid == "missing":
        fields["target_iqc_inspection_id"] = None
    elif invalid == "wrong_factory":
        fields["factory_id"] = other_factory.id
        expected = "fk_agent_task_iqc_factory"
    else:
        fields["task_type"] = "capa"
    with pytest.raises(IntegrityError, match=expected), db.no_autoflush:
        async with db.begin_nested():
            db.add(AgentTask(**fields))
            await db.flush()


async def test_iqc_create_input_rejects_unbound_or_free_text_fields():
    params = {"expected_version": "a" * 64, "request_key": "prepare", "model_deployment_id": uuid4()}
    assert IqcInvestigationCreate.model_validate(params).request_key == "prepare"
    for field in ("initial_text", "report_id", "factory_id", "executor_user_id", "profile"):
        with pytest.raises(ValidationError, match="Extra inputs"):
            IqcInvestigationCreate.model_validate({**params, field: "untrusted"})
