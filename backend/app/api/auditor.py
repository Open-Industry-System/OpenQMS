import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app import schemas
from app.services import audit_service

router = APIRouter(prefix="/api/auditors", tags=["auditors"])


@router.get("")
async def list_auditors(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    auditors = await audit_service.list_auditors(db)
    return [
        {
            "user_id": str(u.user_id),
            "username": u.username,
            "display_name": u.display_name,
            "auditor_info": u.auditor_info,
        }
        for u in auditors
    ]


@router.put("/{user_id}/auditor-info")
async def update_auditor_info(
    user_id: uuid.UUID,
    req: schemas.audit.AuditorInfoUpdate,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    last_date = None
    if req.last_qualification_date:
        try:
            last_date = date.fromisoformat(req.last_qualification_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid last_qualification_date format, expected ISO date")

    try:
        user = await audit_service.update_auditor_info(
            db,
            user=user,
            is_auditor=req.is_auditor,
            qualifications=req.qualifications,
            last_qualification_date=last_date,
            user_id=admin_user.user_id,
        )
        return {
            "user_id": str(user.user_id),
            "username": user.username,
            "display_name": user.display_name,
            "auditor_info": user.auditor_info,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
