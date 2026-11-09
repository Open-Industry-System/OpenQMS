import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration_session import CollaborationSession
from app.models.fmea import FMEADocument
from app.models.control_plan import ControlPlan

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


async def resolve_document_scope(
    db: AsyncSession, document_type: str, document_id: uuid.UUID
) -> tuple[uuid.UUID, str | None]:
    """Resolve only owning factory/line metadata, never document or item bodies."""
    if document_type == "fmea":
        model, key = FMEADocument, FMEADocument.fmea_id
    elif document_type == "control_plan":
        model, key = ControlPlan, ControlPlan.cp_id
    else:
        raise ValueError("unsupported_document_type")
    row = (await db.execute(select(model.factory_id, model.product_line_code)
                            .where(key == document_id))).one_or_none()
    if row is None or row[0] is None:
        raise ValueError("document_not_found")
    return row[0], row[1]


async def resolve_document_factory_id(
    db: AsyncSession, document_type: str, document_id: uuid.UUID
) -> uuid.UUID:
    """Keep the existing factory-only resolver contract for FMEA admission."""
    return (await resolve_document_scope(db, document_type, document_id))[0]


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
