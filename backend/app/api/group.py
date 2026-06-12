"""Group management API routes — dashboard, comparison, factory CRUD, shared suppliers, cross-factory audits."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import RequestScope, get_request_scope
from app.core.permissions import get_current_user, Module, PermissionLevel, get_user_permission
from app.models.user import User
from app.schemas.factory import FactoryCreate, FactoryUpdate, FactoryResponse, FactoryListResponse
from app.schemas.group import (
    GroupDashboardResponse, FactoryComparisonResponse,
    SharedSupplierResponse, CrossFactoryAuditResponse,
    SupplierMergeRequest, MergedSupplierResponse,
    AuditFactoryAssignment, AuditProgramFactoriesResponse,
)
from app.services.factory_service import (
    list_factories,
    create_factory,
    update_factory,
    deactivate_factory,
)
from app.services import group_service

router = APIRouter(prefix="/api/group", tags=["group"])


async def _require_group_view(user: User, db: AsyncSession):
    """Require GROUP VIEW permission."""
    level = await get_user_permission(user, Module.GROUP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 group 模块的 VIEW 权限")


async def _require_group_admin(user: User, db: AsyncSession):
    """Require GROUP ADMIN permission."""
    level = await get_user_permission(user, Module.GROUP, db)
    if level < PermissionLevel.ADMIN:
        raise HTTPException(status_code=403, detail="需要 group 模块的 ADMIN 权限")


# --- Dashboard & Comparison ---


@router.get("/dashboard", response_model=GroupDashboardResponse)
async def dashboard(
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """Group-level dashboard with KPIs aggregated across accessible factories."""
    await _require_group_view(scope.user, db)
    return await group_service.get_group_dashboard(db, accessible_factory_ids=scope.factory_scope.accessible_factory_ids)


@router.get("/comparison", response_model=FactoryComparisonResponse)
async def comparison(
    metric_names: Optional[str] = Query(None, description="逗号分隔的指标名称"),
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """Compare factories side by side on standardized metrics."""
    await _require_group_view(scope.user, db)
    names = [m.strip() for m in metric_names.split(",") if m.strip()] if metric_names else None
    return await group_service.get_factory_comparison(db, metric_names=names, accessible_factory_ids=scope.factory_scope.accessible_factory_ids)


# --- Shared Suppliers & Cross-Factory Audits ---


@router.get("/suppliers", response_model=list[SharedSupplierResponse])
async def shared_suppliers(
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get suppliers with shared profiles across factories."""
    await _require_group_view(scope.user, db)
    return await group_service.get_shared_suppliers(db)


@router.get("/audits", response_model=list[CrossFactoryAuditResponse])
async def cross_factory_audits(
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get audit programs that span multiple factories."""
    await _require_group_view(scope.user, db)
    return await group_service.get_cross_factory_audits(db)


@router.post("/suppliers/merge", response_model=MergedSupplierResponse)
async def merge_suppliers(
    data: SupplierMergeRequest,
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """Merge supplier records from different factories into a shared profile."""
    await _require_group_admin(scope.user, db)
    try:
        return await group_service.merge_suppliers(db, data.supplier_ids, data.shared_profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/audits/{program_id}/factories", response_model=AuditProgramFactoriesResponse)
async def get_audit_factories(
    program_id: uuid.UUID = Path(...),
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """Get target factories for an audit program."""
    await _require_group_view(scope.user, db)
    try:
        return await group_service.get_audit_program_factories(db, program_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/audits/{program_id}/factories", response_model=AuditProgramFactoriesResponse)
async def add_audit_factory(
    program_id: uuid.UUID = Path(...),
    data: AuditFactoryAssignment = ...,
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """Add a factory to an audit program."""
    await _require_group_admin(scope.user, db)
    try:
        return await group_service.add_factory_to_audit_program(db, program_id, data.factory_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/audits/{program_id}/factories/{fid}", response_model=AuditProgramFactoriesResponse)
async def remove_audit_factory(
    program_id: uuid.UUID = Path(...),
    fid: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a factory from an audit program."""
    level = await get_user_permission(user, Module.GROUP, db)
    if level < PermissionLevel.ADMIN:
        raise HTTPException(status_code=403, detail="需要 group 模块的 ADMIN 权限")
    try:
        return await group_service.remove_factory_from_audit_program(db, program_id, fid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Factory CRUD (group-level) ---


@router.get("/factories", response_model=FactoryListResponse)
async def list_all_factories(
    is_active: Optional[bool] = Query(None),
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """List all factories (group-level view)."""
    await _require_group_view(scope.user, db)
    factories = await list_factories(db, is_active=is_active)
    items = [FactoryResponse.model_validate(f) for f in factories]
    return FactoryListResponse(items=items, total=len(items))


@router.post("/factories", response_model=FactoryResponse, status_code=201)
async def create_new_factory(
    data: FactoryCreate,
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """Create a new factory (group admin only)."""
    await _require_group_admin(scope.user, db)
    try:
        factory = await create_factory(db, data, user_id=scope.user.user_id)
        return FactoryResponse.model_validate(factory)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/factories/{fid}", response_model=FactoryResponse)
async def update_existing_factory(
    fid: uuid.UUID = Path(...),
    data: FactoryUpdate = ...,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a factory (group admin only)."""
    await _require_group_admin(user, db)
    try:
        factory = await update_factory(db, fid, data, user_id=user.user_id)
        return FactoryResponse.model_validate(factory)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/factories/{fid}", response_model=FactoryResponse)
async def deactivate_existing_factory(
    fid: uuid.UUID = Path(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a factory (group admin only)."""
    await _require_group_admin(user, db)
    try:
        factory = await deactivate_factory(db, fid, user_id=user.user_id)
        return FactoryResponse.model_validate(factory)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))