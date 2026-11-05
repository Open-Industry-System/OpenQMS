"""R2 persistence required before readonly delivery can acquire authority."""
import pytest

from app.database import Base


def test_readonly_delivery_persistence_has_fences_and_server_receipt_links():
    tables = Base.metadata.tables
    assert {"agent_projection_receipts", "agent_run_events", "agent_results"} <= tables.keys()
    assert {"claim_key", "lease_expires_at"} <= set(tables["agent_runs"].columns.keys())
    assert {"delivery_batch_id", "delivery_epoch"} <= set(tables["agent_task_messages"].columns.keys())
    for name in ("agent_run_events", "agent_results"):
        table = tables[name]
        assert any(set(c.columns.keys()) == {"run_id", "idempotency_key"}
                   for c in table.constraints)
    for name, owner in (("agent_event_receipts", "event_id"), ("agent_result_receipts", "result_id")):
        table = tables[name]
        assert set(table.primary_key.columns.keys()) == {owner, "receipt_id"}
        assert any(f.target_fullname == "agent_projection_receipts.receipt_id"
                   for f in table.columns.receipt_id.foreign_keys)
    assert "source_capa_id" in tables["agent_projection_receipts"].columns


async def _receipt(db, run, task):
    from app.models.agent_runtime_event import AgentProjectionReceipt
    receipt = AgentProjectionReceipt(task_id=task.task_id, run_id=run.run_id, lease_epoch=1,
        tenant_generation=0, source_capa_id=task.target_capa_id, projection_id="capa.d4.summary.masked.v1",
        projection_digest="a"*64, data_class="internal")
    db.add(receipt)
    await db.flush()
    return receipt


@pytest.mark.asyncio
async def test_receipt_result_associations_allow_both_query_sources(db, active_run):
    from app.models.agent_runtime_event import AgentResult, AgentResultReceipt
    run, task, *_ = active_run
    receipts = [await _receipt(db, run, task), await _receipt(db, run, task)]
    result = AgentResult(task_id=task.task_id, run_id=run.run_id, idempotency_key="result", payload={"summary": "readonly"})
    db.add(result)
    await db.flush()
    db.add_all([AgentResultReceipt(result_id=result.result_id, receipt_id=receipt.receipt_id) for receipt in receipts])
    await db.flush()
    assert result.data_class == "restricted"
    assert len(receipts) == 2 and receipts[0].receipt_id != receipts[1].receipt_id


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["claim", "event", "result", "receipt", "classification"])
async def test_readonly_persistence_database_fences_invalid_output(db, active_run, violation):
    import uuid
    from sqlalchemy.exc import IntegrityError
    from app.models.agent_task import AgentRun, AgentTask
    from app.models.agent_runtime_event import AgentEventReceipt, AgentResult, AgentRunEvent
    run, task, plugin, user = active_run
    if violation == "claim":
        run.claim_key = "same-claim"
        other = AgentTask(initiator_id=user.user_id, executor_user_id=user.user_id,
            preferred_installation_id=plugin.installation_id, target_capa_id=task.target_capa_id,
            factory_id=task.factory_id, request_key="another-task", status="ready")
        db.add(other)
        await db.flush()
        invalid = AgentRun(task_id=other.task_id, installation_id=plugin.installation_id,
            plugin_version=plugin.plugin_version, status="pending", claim_key="same-claim")
    elif violation == "receipt":
        event = AgentRunEvent(task_id=task.task_id, run_id=run.run_id, idempotency_key="progress", event_type="progress", payload={})
        db.add(event)
        await db.flush()
        invalid = AgentEventReceipt(event_id=event.event_id, receipt_id=uuid.uuid4())
    else:
        cls = AgentRunEvent if violation == "event" else AgentResult
        fields = dict(task_id=task.task_id, run_id=run.run_id, idempotency_key="same", payload={})
        if violation == "event":
            fields["event_type"] = "progress"
        db.add(cls(**fields))
        await db.flush()
        invalid = cls(**{**fields, **({"data_class": "internal", "idempotency_key": "classified"} if violation == "classification" else {})})
    db.add(invalid)
    with pytest.raises(IntegrityError):
        await db.flush()
