"""Activity pointers appended within the business mutation's transaction."""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_readonly_control import AgentTaskUpdate


async def append_update(db: AsyncSession, *, task_id: UUID, kind: str,
                        object_id: UUID) -> AgentTaskUpdate:
    """Caller must own Task FOR UPDATE, or its new uncommitted Task insert.

    This internal helper grants no authority and takes no additional locks.
    Runtime callers retain INSTALL→TASK→RUN ordering; task-only writers never
    acquire INSTALL later. The caller commits object, audit and pointer together.
    """
    sequence = (await db.scalar(select(func.coalesce(func.max(AgentTaskUpdate.sequence), 0))
        .where(AgentTaskUpdate.task_id == task_id))) + 1
    row = AgentTaskUpdate(task_id=task_id, sequence=sequence, kind=kind, object_id=object_id)
    db.add(row)
    await db.flush()
    return row
