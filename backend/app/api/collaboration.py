import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access
from app.database import get_db
from app.schemas.collaboration import ActiveUser, ActiveUsersResponse, HeartbeatRequest
from app.services import collaboration_service

router = APIRouter(prefix="/api/collaboration", tags=["collaboration"])


async def _require_document_access(
    db: AsyncSession,
    scope: RequestScope,
    document_type: str,
    document_id: uuid.UUID,
) -> uuid.UUID:
    try:
        factory_id = await collaboration_service.resolve_document_factory_id(
            db, document_type, document_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        check_factory_access(factory_id, scope)
    except HTTPException as exc:
        raise HTTPException(status_code=404, detail="document_not_found") from exc
    return factory_id


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat(
    req: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    factory_id = await _require_document_access(
        db, scope, req.document_type, req.document_id
    )
    user = scope.user
    await collaboration_service.upsert_session(
        db,
        document_type=req.document_type,
        document_id=req.document_id,
        user_id=user.user_id,
        user_name=user.display_name or user.username,
        action=req.action,
        editing_area=req.editing_area.model_dump() if req.editing_area else None,
        factory_id=factory_id,
    )


@router.delete("/leave/{document_type}/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave(
    document_type: str,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    await _require_document_access(db, scope, document_type, document_id)
    await collaboration_service.delete_session(
        db,
        document_type=document_type,
        document_id=document_id,
        user_id=scope.user.user_id,
    )


@router.get("/{document_type}/{document_id}/active-users", response_model=ActiveUsersResponse)
async def active_users(
    document_type: str,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    await _require_document_access(db, scope, document_type, document_id)
    sessions = await collaboration_service.get_active_users(
        db,
        document_type=document_type,
        document_id=document_id,
        exclude_user_id=scope.user.user_id,
    )
    return ActiveUsersResponse(
        users=[
            ActiveUser(
                user_id=str(session.user_id),
                user_name=session.user_name or "未知用户",
                action=session.action,  # type: ignore[arg-type]
                editing_area=session.editing_area,
            )
            for session in sessions
        ],
        total=len(sessions),
    )
