"""Admin log query endpoints — tenant-scoped (get_db), admin-only."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.permissions import require_admin
from app.models.user import User
from app.services import log_service

router = APIRouter(prefix="/api/admin/logs", tags=["admin-logs"])


def _filters(**kw: Any) -> dict[str, Any]:
    return {k: v for k, v in kw.items() if v is not None}


@router.get("/audit")
async def list_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    table_name: str | None = None,
    action: str | None = None,
    operated_by: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    items, total = await log_service.list_audit_logs(
        db, _filters(table_name=table_name, action=action, operated_by=operated_by, start=start, end=end),
        page, page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/login")
async def list_login(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    username: str | None = None,
    success: bool | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    items, total = await log_service.list_login_logs(
        db, _filters(username=username, success=success, start=start, end=end),
        page, page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/system")
async def list_system(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    level: str | None = None,
    logger_name: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    items, total = await log_service.list_system_logs(
        db, _filters(level=level, logger_name=logger_name, start=start, end=end),
        page, page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}
