from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func

from app.core.deps import require_platform_admin
from app.database import get_platform_db
from app.models.tenant import Tenant
from app.schemas.platform import TenantCreateRequest, TenantResponse, TenantListResponse
from app.services.tenant_service import TenantService

router = APIRouter()


@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    _admin=Depends(require_platform_admin),
    db=Depends(get_platform_db),
):
    """List all tenants (platform admin only)."""
    query = select(Tenant)
    if status:
        query = query.where(Tenant.status == status)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    tenants = result.scalars().all()
    return TenantListResponse(items=tenants, total=total, page=page, page_size=page_size)


@router.post("/tenants", response_model=TenantResponse, status_code=201)
async def create_tenant(
    request: TenantCreateRequest,
    _admin=Depends(require_platform_admin),
    db=Depends(get_platform_db),
):
    """Provision a new tenant (platform admin only)."""
    try:
        tenant = await TenantService.provision(db, request)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return tenant