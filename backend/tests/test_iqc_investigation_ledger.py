from uuid import uuid4

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.agent_iqc_investigation import IqcInvestigationBinding, IqcInvestigationReceipt
from app.models.agent_plugin import AgentPluginInstallation
from app.models.agent_runtime_event import AgentResult
from app.models.agent_task import AgentRun, AgentTask
from tests.test_iqc_investigation_optional import sources  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.requires_db]


async def test_ledger_is_run_bound_and_published_evidence_stays_immutable(db, sources):
    inspection, scope, *_ = sources
    actor = scope.user.user_id
    plugin = AgentPluginInstallation(
        installation_id=uuid4(), plugin_key="iqc-ledger-test", plugin_version="1",
        manifest={}, secret_hash="unused", created_by=actor,
    )
    db.add(plugin)
    await db.flush()
    task = AgentTask(
        initiator_id=actor, executor_user_id=actor, task_type="iqc_investigation_advice.v1",
        preferred_installation_id=plugin.installation_id, request_key="ledger",
        status="ready", factory_id=inspection.factory_id, target_iqc_inspection_id=inspection.inspection_id,
    )
    db.add(task)
    await db.flush()
    run = AgentRun(
        task_id=task.task_id, installation_id=plugin.installation_id,
        plugin_version="1", status="active", lease_epoch=1,
    )
    db.add(run)
    await db.flush()
    binding = IqcInvestigationBinding(
        task_id=task.task_id, binding_digest="a" * 64, binding={
            "inspection_id": str(inspection.inspection_id), "factory_id": str(inspection.factory_id),
        },
    )
    db.add(binding)
    await db.flush()
    with pytest.raises(IntegrityError, match="run mismatch"):
        async with db.begin_nested():
            db.add(IqcInvestigationReceipt(
                task_id=task.task_id, run_id=run.run_id, lease_epoch=0, kind="source", payload={},
            ))
            await db.flush()
    receipt = IqcInvestigationReceipt(
        task_id=task.task_id, run_id=run.run_id, lease_epoch=1, kind="source", payload={},
    )
    result = AgentResult(
        task_id=task.task_id, run_id=run.run_id, idempotency_key="publish",
        payload={"contract": "iqc_investigation_result.v1", "binding_digest": binding.binding_digest},
    )
    db.add_all([receipt, result])
    await db.flush()
    statements = (
        update(IqcInvestigationBinding).where(IqcInvestigationBinding.task_id == task.task_id)
        .values(binding_digest="b" * 64),
        delete(IqcInvestigationReceipt).where(IqcInvestigationReceipt.receipt_id == receipt.receipt_id),
        delete(AgentResult).where(AgentResult.result_id == result.result_id),
    )
    for statement in statements:
        with pytest.raises(IntegrityError, match="immutable"):
            async with db.begin_nested():
                await db.execute(statement)


@pytest.mark.parametrize("statement", [
    "UPDATE public.capa_eightd SET title = title WHERE false",
    "UPDATE public.supplier_scars SET source_id = source_id WHERE false",
    "INSERT INTO public.iqc_inspections (inspection_id) SELECT gen_random_uuid() WHERE false",
])
async def test_exclusive_publication_fence_blocks_relation_statements(sessionmaker, statement):
    async with sessionmaker() as publisher, sessionmaker() as business:
        await publisher.execute(text(
            "SELECT pg_advisory_xact_lock(hashtextextended('openqms.iqc-associations.v1:public', 0))"
        ))
        await business.execute(text("SET LOCAL lock_timeout = '150ms'"))
        with pytest.raises(DBAPIError) as blocked:
            await business.execute(text(statement))
        assert blocked.value.orig.sqlstate == "55P03"
        await business.rollback()
        await publisher.rollback()
        await business.execute(text("SET LOCAL lock_timeout = '150ms'"))
        await business.execute(text(statement))
        await business.rollback()


async def test_legacy_capa_and_scar_writers_share_association_fence(sessionmaker):
    async with sessionmaker() as capa, sessionmaker() as scar, sessionmaker() as publisher:
        await capa.execute(text("UPDATE public.capa_eightd SET title = title WHERE false"))
        await scar.execute(text("SET LOCAL lock_timeout = '150ms'"))
        await scar.execute(text("UPDATE public.supplier_scars SET status = status WHERE false"))
        claim_publication = text(
            "SELECT pg_try_advisory_xact_lock(hashtextextended('openqms.iqc-associations.v1:public', 0))"
        )
        assert await publisher.scalar(claim_publication) is False
        await capa.rollback()
        assert await publisher.scalar(claim_publication) is False
        await scar.rollback()
        assert await publisher.scalar(claim_publication) is True
