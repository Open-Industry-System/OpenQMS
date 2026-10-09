"""Immutable server-derived readonly checkpoint coordinates and user history."""
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_readonly_control import AgentReadonlyCheckpoint, AgentCheckpointReceipt, AgentTaskUpdate
from app.models.agent_task import AgentRun
from app.models.audit import AuditLog
from app.schemas.agent_runtime import ReadonlyCheckpointCreate, ReadonlyCheckpointOut, ReadonlyCheckpointView
from app.services.agent_runtime import readonly_delivery, runtime_access, runtime_messages, task_service, task_updates


def _admit(identity):
    readonly_delivery._admit(identity)
    runtime_messages._delivery(identity)


def _metadata(row, receipts):
    return ReadonlyCheckpointOut(checkpoint_id=row.checkpoint_id, task_id=row.task_id,
        run_id=row.run_id, lease_epoch=row.lease_epoch, tenant_generation=row.tenant_generation,
        accepted_message_seq=row.accepted_message_seq, update_sequence=row.update_sequence,
        created_at=row.created_at, sources=readonly_delivery._source_metadata(receipts)).model_dump(mode="json")


async def _latest(db, task_id, run_id):
    with db.no_autoflush:
        rows = list((await db.scalars(select(AgentReadonlyCheckpoint).where(
            AgentReadonlyCheckpoint.task_id == task_id, AgentReadonlyCheckpoint.run_id == run_id)
            .order_by(AgentReadonlyCheckpoint.update_sequence.desc()).limit(2)
            .execution_options(populate_existing=True))).all())
    if len(rows) == 2 and rows[0].update_sequence == rows[1].update_sequence:
        raise PermissionError("Checkpoint position unavailable")
    return rows[0] if rows else None


async def save_checkpoint(db: AsyncSession, identity, body) -> dict:
    request = ReadonlyCheckpointCreate.model_validate(body)
    current = await runtime_access.lock_runtime_identity(db, identity)
    _admit(current)
    generation = 0 if current.binding is None else current.binding.generation
    task_id, run_id = current.task.task_id, current.run.run_id
    receipts = await readonly_delivery._sources(db, request.receipt_ids, task_id, run_id,
        current.task.target_capa_id, generation, current.run.lease_epoch)
    identifiers = sorted({row.receipt_id for row in receipts}, key=str)
    with db.no_autoflush:
        previous = await db.scalar(select(AgentReadonlyCheckpoint).where(
            AgentReadonlyCheckpoint.run_id == run_id, AgentReadonlyCheckpoint.key == request.idempotency_key)
            .execution_options(populate_existing=True))
    stored_ids = [] if previous is None else await readonly_delivery._stored_sources(
        db, AgentCheckpointReceipt, AgentCheckpointReceipt.checkpoint_id, previous.checkpoint_id)
    await runtime_messages.require_accepted_prefix(db, task_id, current.run.accepted_message_seq, no_claimed=True)
    # All reads precede full final identity and source-coordinate admission. No
    # checkpoint, pointer or audit exists yet, including on an idempotent retry.
    current = await runtime_access.refresh_runtime_identity(db, current)
    _admit(current)
    for receipt in receipts:
        readonly_delivery._recognized_source(receipt, current.task.task_id, current.run.run_id,
            current.task.target_capa_id, generation, current.run.lease_epoch)
    if previous is not None:
        if (previous.task_id != current.task.task_id or previous.lease_epoch != current.run.lease_epoch
                or previous.tenant_generation != generation or stored_ids != identifiers
                or previous.accepted_message_seq != current.run.accepted_message_seq):
            raise ValueError("Checkpoint key reused with different sources or position")
        result = _metadata(previous, receipts)
        await db.commit()
        return result
    checkpoint_id = uuid4()
    try:
        # Allocate the real pointer first; object_id is a content-free UUID and
        # both pointer and checkpoint remain invisible until the same commit.
        pointer = await task_updates.append_update(db, task_id=task_id, kind="checkpoint", object_id=checkpoint_id)
        row = AgentReadonlyCheckpoint(checkpoint_id=checkpoint_id, task_id=task_id, run_id=run_id,
            key=request.idempotency_key, lease_epoch=current.run.lease_epoch, tenant_generation=generation,
            accepted_message_seq=current.run.accepted_message_seq, update_sequence=pointer.sequence)
        db.add(row)
        await db.flush()
        db.add_all([AgentCheckpointReceipt(checkpoint_id=checkpoint_id, receipt_id=value) for value in identifiers])
        db.add(AuditLog(table_name="agent_readonly_checkpoints", record_id=checkpoint_id,
            action="SAVE_AGENT_READONLY_CHECKPOINT", operated_by=current.task.executor_user_id,
            factory_id=current.task.factory_id, correlation_id=run_id, changed_fields={
                "checkpoint_id": str(checkpoint_id), "task_id": str(task_id), "run_id": str(run_id),
                "lease_epoch": row.lease_epoch, "tenant_generation": generation,
                "accepted_message_seq": row.accepted_message_seq, "update_sequence": row.update_sequence,
                "sources": readonly_delivery._source_metadata(receipts)}))
        result = _metadata(row, receipts)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return result


async def _historical_sources(db, scope, task, row):
    with db.no_autoflush:
        run_task = await db.scalar(select(AgentRun.task_id).where(AgentRun.run_id == row.run_id))
        pointers = list((await db.scalars(select(AgentTaskUpdate).where(
            AgentTaskUpdate.task_id == row.task_id, AgentTaskUpdate.sequence == row.update_sequence,
            AgentTaskUpdate.kind == "checkpoint", AgentTaskUpdate.object_id == row.checkpoint_id))).all())
    if row.task_id != task.task_id or run_task != task.task_id or len(pointers) != 1:
        raise PermissionError("Checkpoint association unavailable")
    identifiers = await readonly_delivery._stored_sources(db, AgentCheckpointReceipt,
        AgentCheckpointReceipt.checkpoint_id, row.checkpoint_id)
    if not 1 <= len(identifiers) <= 20:
        raise PermissionError("Source unavailable")
    receipts = await readonly_delivery._sources(db, identifiers, task.task_id, row.run_id,
        task.target_capa_id, row.tenant_generation, row.lease_epoch)
    for receipt in receipts:
        try:
            source = await task_service.require_current_capa_view(db, scope, receipt.source_capa_id)
        except LookupError:
            raise PermissionError("Source unavailable") from None
        if source.factory_id != task.factory_id:
            raise PermissionError("Source unavailable")
    return receipts


async def get_checkpoint_for_view(db: AsyncSession, scope, task_id: UUID, checkpoint_id: UUID) -> dict:
    """Current own-user/source ACL, independent of plugin, lease and saved generation."""
    from app.services.agent_runtime.task_controls import _current_run, _task_binding
    task = await task_service.get_task_for_view(db, scope, task_id)
    binding = _task_binding(task)
    with db.no_autoflush:
        row = await db.scalar(select(AgentReadonlyCheckpoint).where(
            AgentReadonlyCheckpoint.checkpoint_id == checkpoint_id,
            AgentReadonlyCheckpoint.task_id == task_id).execution_options(populate_existing=True))
    if row is None:
        raise LookupError("Checkpoint not found")
    receipts = await _historical_sources(db, scope, task, row)
    latest = await _latest(db, task_id, row.run_id)
    run = await _current_run(db, task_id)
    eligible = latest is not None and latest.checkpoint_id == checkpoint_id and run is not None and run.run_id == row.run_id and run.accepted_message_seq == row.accepted_message_seq
    if eligible:
        try:
            await runtime_messages.require_accepted_prefix(db, task_id, row.accepted_message_seq, no_claimed=True)
        except ValueError:
            eligible = False
    # Source/role/target changes committed during materialization deny the whole
    # metadata response. Saved epoch/generation are references, never admission.
    task = await task_service.get_task_for_view(db, scope, task_id)
    if _task_binding(task) != binding:
        raise PermissionError("Checkpoint association unavailable")
    receipts = await _historical_sources(db, scope, task, row)
    task = await task_service.get_task_for_view(db, scope, task_id)
    if _task_binding(task) != binding:
        raise PermissionError("Checkpoint association unavailable")
    for receipt in receipts:
        readonly_delivery._recognized_source(receipt, task_id, row.run_id,
            task.target_capa_id, row.tenant_generation, row.lease_epoch)
    return ReadonlyCheckpointView.model_validate({**_metadata(row, receipts),
        "is_latest": latest is not None and latest.checkpoint_id == checkpoint_id,
        "prefix_eligible": eligible}).model_dump(mode="json")


async def require_restart_checkpoint(db, scope, task, run, checkpoint_id):
    metadata = await get_checkpoint_for_view(db, scope, task.task_id, checkpoint_id)
    if (metadata["run_id"] != str(run.run_id) or not metadata["is_latest"]
            or not metadata["prefix_eligible"] or metadata["accepted_message_seq"] != run.accepted_message_seq):
        raise ValueError("Checkpoint is not the latest safe position")
    return metadata
