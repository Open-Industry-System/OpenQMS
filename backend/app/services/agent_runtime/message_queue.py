"""Durable initiator-only instructions; R1 never claims or delivers messages."""
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.models.agent_task import AgentTask, AgentTaskMessage
from app.models.audit import AuditLog
from app.schemas.agent_task import TaskMessageCreate
from app.services.agent_runtime import task_updates
from app.services.agent_runtime.task_service import get_task_for_view, require_current_capa_view


async def append_task_message(db: AsyncSession, task: AgentTask, scope: RequestScope,
                              text: str, idempotency_key: str) -> AgentTaskMessage:
    request = TaskMessageCreate(content=text, idempotency_key=idempotency_key)
    if not request.content.strip():
        raise ValueError("message empty")
    task_id = task.task_id
    # Shared admission validates the namespace before any business lock query,
    # and hides foreign tasks without locking them or exposing message content.
    await get_task_for_view(db, scope, task_id)
    with db.no_autoflush:
        locked = await db.scalar(select(AgentTask).where(AgentTask.task_id == task_id,
            AgentTask.initiator_id == scope.user.user_id,
            AgentTask.executor_user_id == scope.user.user_id).with_for_update()
            .execution_options(populate_existing=True))
    if locked is None:
        raise LookupError("Task not found")
    # Both target and status may have changed while the row lock was awaited.
    capa = await require_current_capa_view(db, scope, locked.target_capa_id)
    if locked.factory_id != capa.factory_id:
        raise LookupError("Task not found")
    if locked.status in {"completed", "failed", "cancelled"}:
        raise ValueError("task closed")
    with db.no_autoflush:
        previous = await db.scalar(select(AgentTaskMessage).where(
            AgentTaskMessage.task_id == task_id,
            AgentTaskMessage.author_id == scope.user.user_id,
            AgentTaskMessage.idempotency_key == request.idempotency_key)
            .execution_options(populate_existing=True))
        if previous is not None:
            if previous.content != request.content:
                raise ValueError("idempotency key reused with different content")
            return previous
        next_sequence = (await db.scalar(select(func.coalesce(func.max(AgentTaskMessage.sequence), 0))
            .where(AgentTaskMessage.task_id == task_id))) + 1
    message = AgentTaskMessage(message_id=uuid4(), task_id=task_id,
        author_id=scope.user.user_id, sequence=next_sequence, content=request.content,
        sensitivity="restricted", state="queued", idempotency_key=request.idempotency_key)
    db.add(message)
    db.add(AuditLog(table_name="agent_task_messages", record_id=message.message_id,
        action="APPEND_AGENT_TASK_MESSAGE", operated_by=scope.user.user_id,
        factory_id=locked.factory_id, changed_fields={"task_id": str(task_id),
            "message_id": str(message.message_id), "sequence": next_sequence,
            "target_capa_id": str(locked.target_capa_id)}))
    await task_updates.append_update(db, task_id=task_id, kind="message", object_id=message.message_id)
    await db.commit()
    return message
