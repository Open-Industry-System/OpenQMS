"""R7 bindings are not input to the generic CAPA task or run surface."""

from uuid import uuid4

import pytest

from app.models.agent_pfmea_impact import AgentPfmeaImpactBinding
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_task import AgentTask
from app.services.agent_runtime import runtime_access, task_service
from tests.services.agent_runtime.test_task_reads import scope_for


@pytest.mark.requires_db
@pytest.mark.asyncio
async def test_legacy_list_control_activity_and_run_authority_do_not_accept_r7_binding(committed_runtime):
    owned = committed_runtime
    async with owned.factory(binding=owned.binding) as db:
        scope = await scope_for(db, owned)
        old = await db.get(AgentTask, owned.task_id)
        impact = AgentTask(
            task_id=uuid4(), initiator_id=old.initiator_id, executor_user_id=old.executor_user_id,
            preferred_installation_id=old.preferred_installation_id,
            target_capa_id=old.target_capa_id, factory_id=old.factory_id,
            request_key=uuid4().hex, status="ready",
        )
        db.add(impact)
        await db.flush()
        db.add(AgentPfmeaImpactBinding(
            task_id=impact.task_id, actor_id=impact.initiator_id, request_key=impact.request_key,
            binding={"contract_version": 1}, binding_digest="0" * 64,
        ))
        await db.commit()

        visible = await task_service.list_for_initiator(db, scope, 1, 20)
        assert visible["total"] == 1
        assert [task.task_id for task in visible["items"]] == [old.task_id]

        with pytest.raises(LookupError):
            await task_service.get_task_for_control(db, scope, impact.task_id)
        with pytest.raises(LookupError):
            await task_service.get_task_for_view(db, scope, impact.task_id)
        plugin = await db.get(AgentPluginInstallation, old.preferred_installation_id)
        with pytest.raises(PermissionError):
            await runtime_access.authorize_task(db, impact, plugin)
