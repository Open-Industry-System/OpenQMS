import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_current_user
from app.models.user import User
from app.schemas.collaboration import HeartbeatRequest, ActiveUsersResponse, ActiveUser
from app.services import collaboration_service

router = APIRouter(prefix="/api/collaboration", tags=["collaboration"])


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat(
    req: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await collaboration_service.upsert_session(
        db,
        document_type=req.document_type,
        document_id=req.document_id,
        user_id=user.user_id,
        user_name=user.display_name or user.username,
        action=req.action,
        editing_area=req.editing_area.model_dump() if req.editing_area else None,
    )


@router.delete("/leave/{document_type}/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave(
    document_type: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await collaboration_service.delete_session(
        db,
        document_type=document_type,
        document_id=document_id,
        user_id=user.user_id,
    )


@router.get("/{document_type}/{document_id}/active-users", response_model=ActiveUsersResponse)
async def active_users(
    document_type: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sessions = await collaboration_service.get_active_users(
        db,
        document_type=document_type,
        document_id=document_id,
        exclude_user_id=user.user_id,
    )
    return ActiveUsersResponse(
        users=[
            ActiveUser(
                user_id=str(s.user_id),
                user_name=s.user_name or "未知用户",
                action=s.action,  # type: ignore[arg-type]
                editing_area=s.editing_area,
            )
            for s in sessions
        ],
        total=len(sessions),
    )
