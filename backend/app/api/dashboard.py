from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await dashboard_service.get_dashboard(db)


@router.get("/kpi")
async def get_kpi(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await dashboard_service.get_dashboard(db)
    return data["kpi"]


@router.get("/trends")
async def get_trends(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await dashboard_service.get_dashboard(db)
    return data["trends"]


@router.get("/alerts")
async def get_alerts(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await dashboard_service.get_dashboard(db)
    return data["alerts"]
