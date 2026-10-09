"""Committed, lease-fenced batches of restricted original task instructions."""
from uuid import UUID, uuid5

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_task import AgentTaskMessage
from app.models.audit import AuditLog
from app.schemas.agent_runtime import MessageAck, MessageAckOut, MessageBatch, MessageClaim, RuntimeMessage
from app.services.agent_runtime import runtime_access, task_updates
from app.services.agent_runtime.runtime_access import RuntimeIdentity


def _delivery(identity: RuntimeIdentity) -> None:
    # Original user text is restricted/raw, never a masked projection. Egress
    # authority comes exclusively from the current server deployment tuple.
    runtime_access.require_delivery(identity, "restricted", "raw", controlled_egress=True)


def _contiguous(rows, start: int) -> None:
    if len(rows) > 20 or [row.sequence for row in rows] != list(range(start, start + len(rows))):
        raise ValueError("Message sequence conflicts")


def _batch_id(identity: RuntimeIdentity, first_sequence: int) -> UUID:
    # Epochs are local to a Run. Bind the batch to that Run as well, so a later
    # Run for this Task cannot reuse an earlier Run's epoch-1 markers. This ID
    # alone grants nothing: claims and ACKs also require actual persisted rows.
    return uuid5(identity.run.run_id, f"agent-message-batch:{identity.run.lease_epoch}:{first_sequence}")


async def _final_authority(db: AsyncSession, identity: RuntimeIdentity) -> RuntimeIdentity:
    # Role, memberships and grants do not share the business row locks. Recheck
    # after the message read, before any dirty ORM values could be overwritten
    # by populate_existing, and before any restricted material leaves the service.
    current = await runtime_access.refresh_runtime_identity(db, identity)
    _delivery(current)
    return current


async def claim_messages(db: AsyncSession, identity: RuntimeIdentity, limit: int = 20) -> MessageBatch:
    request = MessageClaim(limit=limit)
    current = await runtime_access.lock_runtime_identity(db, identity)
    _delivery(current)
    task_id, epoch, accepted = current.task.task_id, current.run.lease_epoch, current.run.accepted_message_seq
    with db.no_autoflush:
        # Existing current-epoch markers define an immutable bounded batch,
        # independently of a retry's new limit or messages appended later.
        pending = list((await db.scalars(select(AgentTaskMessage).where(
            AgentTaskMessage.task_id == task_id, AgentTaskMessage.sequence > accepted,
            AgentTaskMessage.delivery_batch_id.is_not(None), AgentTaskMessage.delivery_epoch == epoch)
            .order_by(AgentTaskMessage.sequence).limit(21).execution_options(populate_existing=True))).all())
        if pending:
            _contiguous(pending, accepted + 1)
            batch_id = pending[0].delivery_batch_id
            if any(row.delivery_batch_id != batch_id or row.state == "accepted" for row in pending):
                raise ValueError("Message batch conflicts")
            # Include the accepted part of a partially acknowledged batch when
            # finding its original boundary. A different Run may have the same
            # epoch, but its old unaccepted markers are not this Run's batch.
            first_sequence = await db.scalar(select(func.min(AgentTaskMessage.sequence)).where(
                AgentTaskMessage.task_id == task_id, AgentTaskMessage.delivery_batch_id == batch_id))
            if batch_id != _batch_id(current, first_sequence):
                pending = []
        if pending:
            rows = pending
        else:
            rows = list((await db.scalars(select(AgentTaskMessage).where(
                AgentTaskMessage.task_id == task_id, AgentTaskMessage.sequence > accepted)
                .order_by(AgentTaskMessage.sequence).limit(request.limit)
                .execution_options(populate_existing=True))).all())
            _contiguous(rows, accepted + 1)
            if any(row.state == "accepted" for row in rows):
                raise ValueError("Message state conflicts")
            batch_id = _batch_id(current, rows[0].sequence) if rows else None
    current = await _final_authority(db, current)
    if not pending:
        # A newly verified lease may reclaim only unaccepted old markers. History
        # retains both its accepted watermark and the original batch/epoch proof.
        await db.execute(update(AgentTaskMessage).where(
            AgentTaskMessage.task_id == task_id, AgentTaskMessage.sequence > accepted,
            AgentTaskMessage.delivery_batch_id.is_not(None), AgentTaskMessage.state != "accepted")
            .values(delivery_batch_id=None, delivery_epoch=None, state="queued"))
        for row in rows:
            row.delivery_batch_id = batch_id
            row.delivery_epoch = epoch
            row.state = "claimed"
        if rows:
            db.add(AuditLog(table_name="agent_task_messages", record_id=batch_id,
                action="CLAIM_AGENT_TASK_MESSAGES", operated_by=current.task.executor_user_id,
                factory_id=current.task.factory_id, changed_fields={
                    "batch_id": str(batch_id), "task_id": str(task_id), "run_id": str(current.run.run_id),
                    "from_sequence": rows[0].sequence, "through_sequence": rows[-1].sequence,
                    "lease_epoch": epoch, "executor_user_id": str(current.task.executor_user_id)}))
    result = MessageBatch(batch_id=batch_id, accepted_sequence=accepted,
        messages=[RuntimeMessage(message_id=row.message_id, sequence=row.sequence, content=row.content) for row in rows])
    await db.commit()
    return result


async def ack_messages(db: AsyncSession, identity: RuntimeIdentity,
                       batch_id: UUID, through_sequence: int) -> MessageAckOut:
    request = MessageAck(batch_id=batch_id, through_sequence=through_sequence)
    current = await runtime_access.lock_runtime_identity(db, identity)
    _delivery(current)
    task_id, epoch, accepted = current.task.task_id, current.run.lease_epoch, current.run.accepted_message_seq
    with db.no_autoflush:
        rows = list((await db.scalars(select(AgentTaskMessage).where(
            AgentTaskMessage.task_id == task_id, AgentTaskMessage.delivery_batch_id == request.batch_id)
            .order_by(AgentTaskMessage.sequence).limit(21).execution_options(populate_existing=True))).all())
    if not rows or any(row.delivery_epoch != epoch for row in rows):
        raise ValueError("Message batch unavailable")
    _contiguous(rows, rows[0].sequence)
    if request.batch_id != _batch_id(current, rows[0].sequence):
        raise ValueError("Message batch unavailable")
    if not rows[0].sequence <= request.through_sequence <= rows[-1].sequence:
        raise ValueError("Message acknowledgement conflicts")
    if any((row.sequence <= accepted) != (row.state == "accepted") for row in rows):
        raise ValueError("Message state conflicts")
    advancing = [row for row in rows if accepted < row.sequence <= request.through_sequence]
    if request.through_sequence > accepted:
        _contiguous(advancing, accepted + 1)
        if not advancing or advancing[-1].sequence != request.through_sequence:
            raise ValueError("Message acknowledgement conflicts")
    current = await _final_authority(db, current)
    if advancing:
        for row in advancing:
            row.state = "accepted"
        current.run.accepted_message_seq = request.through_sequence
        db.add(AuditLog(table_name="agent_task_messages", record_id=request.batch_id,
            action="ACK_AGENT_TASK_MESSAGES", operated_by=current.task.executor_user_id,
            factory_id=current.task.factory_id, changed_fields={
                "batch_id": str(request.batch_id), "task_id": str(task_id),
                "run_id": str(current.run.run_id), "through_sequence": request.through_sequence,
                "lease_epoch": epoch, "executor_user_id": str(current.task.executor_user_id)}))
    # Durable batch rows are the retry proof; audit retention cannot change ACK
    # authority. A previously covered prefix of this actual batch is a no-op.
    result = MessageAckOut(accepted_sequence=current.run.accepted_message_seq)
    if advancing:
        await task_updates.append_update(db, task_id=task_id, kind="ack", object_id=request.batch_id)
    await db.commit()
    return result


async def require_accepted_prefix(db: AsyncSession, task_id: UUID, accepted: int,
                                  *, no_claimed: bool = False) -> None:
    """Prove the entire actual accepted prefix; queued future input is allowed."""
    with db.no_autoflush:
        count, first, last, claimed = (await db.execute(select(
            func.count().filter(AgentTaskMessage.state == "accepted"),
            func.min(AgentTaskMessage.sequence).filter(AgentTaskMessage.state == "accepted"),
            func.max(AgentTaskMessage.sequence).filter(AgentTaskMessage.state == "accepted"),
            func.count().filter(AgentTaskMessage.state == "claimed"))
            .where(AgentTaskMessage.task_id == task_id))).one()
    if (type(accepted) is not int or accepted < 0 or count != accepted
            or (count and (first != 1 or last != accepted)) or (no_claimed and claimed)):
        raise ValueError("Message prefix conflicts")


async def get_message_history(db: AsyncSession, identity: RuntimeIdentity,
                               after_sequence: int = 0, limit: int = 20):
    """Read original accepted input without ACK, audit, update or watermark writes.

    A cursor at or beyond the watermark returns an empty complete page whose
    next_sequence is that watermark. New pending/claimed input is never history.
    """
    from app.schemas.agent_runtime import MessageHistoryQuery, MessageHistoryOut
    request = MessageHistoryQuery(after_sequence=after_sequence, limit=limit)
    current = await runtime_access.lock_runtime_identity(db, identity)
    _delivery(current)
    accepted = current.run.accepted_message_seq
    await require_accepted_prefix(db, current.task.task_id, accepted)
    with db.no_autoflush:
        rows = [] if request.after_sequence >= accepted else list((await db.scalars(
            select(AgentTaskMessage).where(AgentTaskMessage.task_id == current.task.task_id,
                AgentTaskMessage.state == "accepted", AgentTaskMessage.sequence > request.after_sequence,
                AgentTaskMessage.sequence <= accepted).order_by(AgentTaskMessage.sequence)
                .limit(request.limit).execution_options(populate_existing=True))).all())
    if rows:
        _contiguous(rows, request.after_sequence + 1)
    current = await _final_authority(db, current)
    return MessageHistoryOut(messages=[RuntimeMessage(message_id=row.message_id,
        sequence=row.sequence, content=row.content) for row in rows],
        next_sequence=rows[-1].sequence if rows else accepted,
        complete=not rows or rows[-1].sequence == accepted)
