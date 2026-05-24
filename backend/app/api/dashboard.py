from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await dashboard_service.get_dashboard(db, product_line)


@router.get("/kpi")
async def get_kpi(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await dashboard_service.get_dashboard(db, product_line)
    return data["kpi"]


@router.get("/trends")
async def get_trends(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await dashboard_service.get_dashboard(db, product_line)
    return data["trends"]


@router.get("/alerts")
async def get_alerts(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await dashboard_service.get_dashboard(db, product_line)
    return data["alerts"]
