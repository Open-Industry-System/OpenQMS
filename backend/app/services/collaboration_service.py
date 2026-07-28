import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration_session import CollaborationSession
from app.models.fmea import FMEADocument

SESSION_TTL_SECONDS = 60


async def upsert_session(
    db: AsyncSession,
    document_type: str,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    user_name: str,
    action: str,
    editing_area: dict | None,
    factory_id: uuid.UUID,
) -> None:
    """Upsert collaboration session on heartbeat."""
    stmt = (
        insert(CollaborationSession)
        .values(
            document_type=document_type,
            document_id=document_id,
            user_id=user_id,
            user_name=user_name,
            action=action,
            editing_area=editing_area,
            last_activity=datetime.now(UTC),
            factory_id=factory_id,
        )
        .on_conflict_do_update(
            index_elements=["document_type", "document_id", "user_id"],
            set_={
                "user_name": user_name,
                "action": action,
                "editing_area": editing_area,
                "last_activity": datetime.now(UTC),
                "factory_id": factory_id,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()


async def resolve_document_factory_id(
    db: AsyncSession, document_type: str, document_id: uuid.UUID
) -> uuid.UUID:
    """Resolve the owning factory for a collaboration document.

    Raises ValueError("document_not_found") when the document does not exist
    and ValueError("unsupported_document_type") for unknown types; the API
    layer converts these to HTTPException.
    """
    if document_type == "fmea":
        factory_id = await db.scalar(
            select(FMEADocument.factory_id).where(FMEADocument.fmea_id == document_id)
        )
        if factory_id is None:
            raise ValueError("document_not_found")
        return factory_id
    raise ValueError("unsupported_document_type")


async def delete_session(
    db: AsyncSession,
    document_type: str,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Delete session on page unload."""
    stmt = delete(CollaborationSession).where(
        CollaborationSession.document_type == document_type,
        CollaborationSession.document_id == document_id,
        CollaborationSession.user_id == user_id,
    )
    await db.execute(stmt)
    await db.commit()


async def get_active_users(
    db: AsyncSession,
    document_type: str,
    document_id: uuid.UUID,
    exclude_user_id: uuid.UUID | None = None,
) -> list[CollaborationSession]:
    """Get active users for a document, filtering expired sessions."""
    cutoff = datetime.now(UTC) - timedelta(seconds=SESSION_TTL_SECONDS)
    stmt = (
        select(CollaborationSession)
        .where(
            CollaborationSession.document_type == document_type,
            CollaborationSession.document_id == document_id,
            CollaborationSession.last_activity >= cutoff,
        )
        .order_by(CollaborationSession.last_activity.desc())
    )
    if exclude_user_id:
        stmt = stmt.where(CollaborationSession.user_id != exclude_user_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_expired_sessions(db: AsyncSession) -> int:
    """Delete expired sessions. Returns count deleted."""
    cutoff = datetime.now(UTC) - timedelta(seconds=SESSION_TTL_SECONDS)
    stmt = delete(CollaborationSession).where(
        CollaborationSession.last_activity < cutoff
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0
