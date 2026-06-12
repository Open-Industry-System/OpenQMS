import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import populate_factory_id, validate_factory_invariant
from app.core.permissions import get_user_permission, PermissionLevel, Module
from app.models.supplier import SupplierSCAR
from app.schemas import scar as scar_schemas
from app.services import scar_service

router = APIRouter(prefix="/api/scars", tags=["scars"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="SCAR not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="SCAR not found")


def _resolve_allowed_pls(scope: RequestScope) -> list[str] | None:
    """Resolve allowed product line codes from scope. Returns None for ALL mode, empty list for NONE."""
    if scope.pl_scope.mode == "NONE":
        return []
    elif scope.pl_scope.mode == "EXPLICIT":
        return scope.pl_scope.codes
    return None  # ALL


def _to_response(s) -> dict:
    """Convert SupplierSCAR ORM object with loaded supplier to SCARResponse dict."""
    return scar_schemas.SCARResponse(
        scar_id=s.scar_id,
        scar_no=s.scar_no,
        supplier_id=s.supplier_id,
        supplier_name=s.supplier.name if s.supplier else None,
        supplier_no=s.supplier.supplier_no if s.supplier else None,
        source_type=s.source_type,
        source_id=s.source_id,
        description=s.description,
        product_line_code=s.product_line_code,
        requested_action=s.requested_action,
        supplier_response=s.supplier_response,
        status=s.status,
        capa_ref_id=s.capa_ref_id,
        resolution_summary=s.resolution_summary,
        issued_by=s.issued_by,
        issued_date=s.issued_date,
        due_date=s.due_date,
        closed_date=s.closed_date,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("", response_model=scar_schemas.SCARListResponse)
async def list_scars(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Comma-separated statuses"),
    supplier_id: uuid.UUID | None = Query(None),
    source_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SCAR, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 scar 模块的 VIEW 权限")

    statuses = status.split(",") if status else None
    allowed_pls = _resolve_allowed_pls(scope)
    if allowed_pls is not None and not allowed_pls:
        return scar_schemas.SCARListResponse(items=[], total=0, page=page, page_size=page_size)

    items, total = await scar_service.list_scars(
        db, page, page_size, statuses, supplier_id, source_type,
        factory_id=scope.effective_factory_id,
        allowed_product_line_codes=allowed_pls,
    )
    return scar_schemas.SCARListResponse(
        items=[_to_response(s) for s in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{scar_id}", response_model=scar_schemas.SCARResponse)
async def get_scar(
    scar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SCAR, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 scar 模块的 VIEW 权限")

    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    _check_factory_access(scar, scope)
    return _to_response(scar)


@router.post("", response_model=scar_schemas.SCARResponse)
async def create_scar(
    req: scar_schemas.SCARCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SCAR, db)
    if perm_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 scar 模块的 CREATE 权限")

    try:
        scar = await scar_service.create_scar(
            db,
            supplier_id=req.supplier_id,
            source_type=req.source_type,
            source_id=req.source_id,
            description=req.description,
            product_line_code=req.product_line_code,
            requested_action=req.requested_action,
            due_date=req.due_date,
            user_id=scope.user.user_id,
        )
        await populate_factory_id(scar, SupplierSCAR, db, scope=scope)
        await validate_factory_invariant(scar, db)
        await db.commit()
        await db.refresh(scar)
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{scar_id}", response_model=scar_schemas.SCARResponse)
async def update_scar(
    scar_id: uuid.UUID,
    req: scar_schemas.SCARUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SCAR, db)
    if perm_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 scar 模块的 CREATE 权限")

    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    _check_factory_access(scar, scope)
    try:
        scar = await scar_service.update_scar(
            db, scar,
            user_id=scope.user.user_id,
            description=req.description,
            requested_action=req.requested_action,
            due_date=req.due_date,
        )
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{scar_id}/transition", response_model=scar_schemas.SCARResponse)
async def transition_scar(
    scar_id: uuid.UUID,
    req: scar_schemas.SCARTransitionRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SCAR, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 scar 模块的 VIEW 权限")

    if req.action in ("verify", "reject", "close", "reopen"):
        if perm_level < PermissionLevel.APPROVE:
            raise HTTPException(403, "需要 manager 或 admin 权限")
    elif req.action in ("start", "respond"):
        if perm_level < PermissionLevel.CREATE:
            raise HTTPException(403, "需要 engineer 或更高权限")

    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    _check_factory_access(scar, scope)
    try:
        scar = await scar_service.transition_scar(
            db, scar, req.action, user_id=scope.user.user_id,
            supplier_response=req.supplier_response,
            resolution_summary=req.resolution_summary,
        )
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{scar_id}/link-capa", response_model=scar_schemas.SCARResponse)
async def link_capa(
    scar_id: uuid.UUID,
    req: scar_schemas.SCARLinkCAPARequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SCAR, db)
    if perm_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 scar 模块的 CREATE 权限")

    scar = await scar_service.get_scar(db, scar_id)
    if not scar:
        raise HTTPException(404, "SCAR not found")
    _check_factory_access(scar, scope)
    try:
        scar = await scar_service.link_capa(db, scar, req.capa_ref_id, scope.user.user_id)
        return _to_response(scar)
    except ValueError as e:
        raise HTTPException(400, str(e))