"""Database enforcement of durable task identity, scope, and execution history."""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError


def _models():
    import app.models as models
    names = ("AgentTask", "AgentRun", "AgentTaskGrant", "AgentTaskMessage")
    assert all(hasattr(models, name) for name in names), "durable task models must be exported"
    return tuple(getattr(models, name) for name in names)


async def _task(db, user, capa, plugin, **overrides):
    AgentTask, *_ = _models()
    values = dict(initiator_id=user.user_id, executor_user_id=user.user_id,
        preferred_installation_id=plugin.installation_id, target_capa_id=capa.report_id,
        factory_id=capa.factory_id, request_key=uuid.uuid4().hex, status="ready")
    values.update(overrides)
    task = AgentTask(**values)
    db.add(task)
    await db.flush()
    return task


@pytest.mark.asyncio
async def test_task_and_message_persist_defaults(db, admin_user, sample_capa, enabled_plugin):
    _, _, AgentTaskGrant, AgentTaskMessage = _models()
    task = await _task(db, admin_user, sample_capa, enabled_plugin)
    grant = AgentTaskGrant(task_id=task.task_id, capability_id="capa.d4.summary.masked.v1",
        factory_ids=[str(sample_capa.factory_id)], access_kind="read")
    message = AgentTaskMessage(task_id=task.task_id, sequence=1, author_id=admin_user.user_id,
        content="Task instructions", idempotency_key="first")
    db.add_all([grant, message])
    await db.flush()
    await db.refresh(task)
    await db.refresh(message)
    assert task.task_id and grant.grant_id and message.message_id
    assert task.created_at.tzinfo and task.updated_at.tzinfo and message.created_at.tzinfo
    assert message.state == "queued" and message.sensitivity == "restricted"


@pytest.mark.asyncio
async def test_task_rejects_cross_factory_capa(db, admin_user, sample_capa, enabled_plugin):
    with pytest.raises(IntegrityError, match="fk_agent_task_capa_factory"):
        await _task(db, admin_user, sample_capa, enabled_plugin, factory_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_task_request_key_is_unique_for_initiator(db, admin_user, sample_capa, enabled_plugin):
    await _task(db, admin_user, sample_capa, enabled_plugin, request_key="retry")
    with pytest.raises(IntegrityError, match="uq_agent_task_initiator_request"):
        await _task(db, admin_user, sample_capa, enabled_plugin, request_key="retry")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "active", "paused"])
async def test_only_one_nonterminal_run_per_task(db, admin_user, sample_capa, enabled_plugin, status):
    _, AgentRun, *_ = _models()
    task = await _task(db, admin_user, sample_capa, enabled_plugin)
    for terminal in ("completed", "failed", "stopped", "completed"):
        db.add(AgentRun(task_id=task.task_id, installation_id=enabled_plugin.installation_id,
            plugin_version="1.0.0", status=terminal))
    first = AgentRun(task_id=task.task_id, installation_id=enabled_plugin.installation_id,
        plugin_version="1.0.0", status=status)
    db.add(first)
    await db.flush()
    assert first.lease_epoch == first.accepted_message_seq == 0
    db.add(AgentRun(task_id=task.task_id, installation_id=enabled_plugin.installation_id,
        plugin_version="1.0.0", status="pending"))
    with pytest.raises(IntegrityError, match="uq_agent_run_nonterminal_task"):
        await db.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize("values", [dict(sequence=1, idempotency_key="different"),
    dict(sequence=2, idempotency_key="same")])
async def test_message_sequence_and_idempotency_are_unique(db, admin_user, sample_capa, enabled_plugin, values):
    *_, AgentTaskMessage = _models()
    task = await _task(db, admin_user, sample_capa, enabled_plugin)
    db.add(AgentTaskMessage(task_id=task.task_id, sequence=1, author_id=admin_user.user_id,
        content="first", idempotency_key="same"))
    await db.flush()
    db.add(AgentTaskMessage(task_id=task.task_id, author_id=admin_user.user_id, content="retry", **values))
    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,values", [
    ("task", dict(status="unknown")), ("run", dict(status="unknown")),
    ("run", dict(lease_epoch=-1)), ("run", dict(accepted_message_seq=-1)),
    ("grant", dict(factory_ids=[])), ("grant", dict(factory_ids={})),
    ("grant", dict(access_kind="write")), ("message", dict(sequence=0)),
    ("message", dict(state="unknown")), ("message", dict(sensitivity="public")),
])
async def test_task_contract_checks_reject_invalid_values(db, admin_user, sample_capa, enabled_plugin, kind, values):
    AgentTask, AgentRun, AgentTaskGrant, AgentTaskMessage = _models()
    if kind == "task":
        with pytest.raises(IntegrityError):
            await _task(db, admin_user, sample_capa, enabled_plugin, **values)
        return
    task = await _task(db, admin_user, sample_capa, enabled_plugin)
    if kind == "run":
        base = dict(task_id=task.task_id, installation_id=enabled_plugin.installation_id,
            plugin_version="1.0.0", status="pending")
        model = AgentRun
    elif kind == "grant":
        base = dict(task_id=task.task_id, capability_id="read", factory_ids=[str(sample_capa.factory_id)], access_kind="read")
        model = AgentTaskGrant
    else:
        base = dict(task_id=task.task_id, sequence=1, author_id=admin_user.user_id, content="message", idempotency_key="test")
        model = AgentTaskMessage
    base.update(values)
    db.add(model(**base))
    with pytest.raises(IntegrityError):
        await db.flush()
