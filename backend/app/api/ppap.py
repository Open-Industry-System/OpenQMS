import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access, resolve_create_factory_id, validate_factory_invariant
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.database import get_db
from app.models.supplier import SupplierPPAPElement
from app.schemas import ppap as ppap_schemas
from app.services import ppap_service

router = APIRouter(prefix="/api/ppap", tags=["ppap"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="PPAP not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="PPAP not found")


def _to_response(ppap) -> ppap_schemas.PPAPResponse:
    """Convert SupplierPPAPSubmission ORM object with loaded supplier and elements to PPAPResponse."""
    return ppap_schemas.PPAPResponse(
        submission_id=ppap.submission_id,
        ppap_no=ppap.ppap_no,
        supplier_id=ppap.supplier_id,
        supplier_name=ppap.supplier.name if ppap.supplier else None,
        supplier_no=ppap.supplier.supplier_no if ppap.supplier else None,
        part_no=ppap.part_no,
        part_name=ppap.part_name,
        submission_level=ppap.submission_level,
        submission_date=ppap.submission_date,
        customer_name=ppap.customer_name,
        product_line_code=ppap.product_line_code,
        status=ppap.status,
        revision=ppap.revision,
        rejection_reason=ppap.rejection_reason,
        approved_by=ppap.approved_by,
        approved_at=ppap.approved_at,
        notes=ppap.notes,
        created_by=ppap.created_by,
        created_at=ppap.created_at,
        updated_at=ppap.updated_at,
        elements=[
            ppap_schemas.PPAPElementResponse(
                element_id=el.element_id,
                submission_id=el.submission_id,
                element_no=el.element_no,
                element_name=el.element_name,
                required=el.required,
                status=el.status,
                reviewed_by=el.reviewed_by,
                reviewed_at=el.reviewed_at,
                file_url=el.file_url,
                notes=el.notes,
                sort_order=el.sort_order,
            )
            for el in (ppap.elements or [])
        ],
    )


@router.get("", response_model=ppap_schemas.PPAPListResponse)
async def list_ppaps(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Comma-separated statuses"),
    supplier_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PPAP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 PPAP 模块的 VIEW 权限")

    # Product line filtering via RequestScope
    if scope.pl_scope.mode == "NONE":
        return ppap_schemas.PPAPListResponse(items=[], total=0, page=page, page_size=page_size)
    allowed_pls = scope.pl_scope.codes if scope.pl_scope.mode == "EXPLICIT" else None

    statuses = status.split(",") if status else None
    items, total = await ppap_service.list_ppaps(
        db, page, page_size, statuses, supplier_id,
        factory_id=scope.effective_factory_id,
        allowed_product_line_codes=allowed_pls,
    )
    return ppap_schemas.PPAPListResponse(
        items=[_to_response(s) for s in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{ppap_id}", response_model=ppap_schemas.PPAPResponse)
async def get_ppap(
    ppap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PPAP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 PPAP 模块的 VIEW 权限")

    ppap = await ppap_service.get_ppap(db, ppap_id)
    if not ppap:
        raise HTTPException(404, "PPAP not found")
    _check_factory_access(ppap, scope)
    return _to_response(ppap)


@router.post("", response_model=ppap_schemas.PPAPResponse)
async def create_ppap(
    req: ppap_schemas.PPAPCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PPAP, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 PPAP 模块的 CREATE 权限")

    try:
        factory_id = await resolve_create_factory_id(db, scope, product_line_code=req.product_line_code)
        check_factory_access(factory_id, scope)
        ppap = await ppap_service.create_ppap(
            db,
            supplier_id=req.supplier_id,
            part_no=req.part_no,
            part_name=req.part_name,
            submission_level=req.submission_level,
            submission_date=req.submission_date,
            customer_name=req.customer_name,
            product_line_code=req.product_line_code,
            notes=req.notes,
            user_id=scope.user.user_id,
            factory_id=factory_id,
        )
        await validate_factory_invariant(ppap, db)
        return _to_response(ppap)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{ppap_id}", response_model=ppap_schemas.PPAPResponse)
async def update_ppap(
    ppap_id: uuid.UUID,
    req: ppap_schemas.PPAPUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PPAP, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 PPAP 模块的 CREATE 权限")

    ppap = await ppap_service.get_ppap(db, ppap_id)
    if not ppap:
        raise HTTPException(404, "PPAP not found")
    _check_factory_access(ppap, scope)
    try:
        ppap = await ppap_service.update_ppap(
            db, ppap,
            user_id=scope.user.user_id,
            **req.model_dump(exclude_unset=True),
        )
        return _to_response(ppap)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{ppap_id}/elements/{element_id}", response_model=ppap_schemas.PPAPElementResponse)
async def update_ppap_element(
    ppap_id: uuid.UUID,
    element_id: uuid.UUID,
    req: ppap_schemas.PPAPElementUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PPAP, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 PPAP 模块的 CREATE 权限")

    # Check parent PPAP factory access
    ppap = await ppap_service.get_ppap(db, ppap_id)
    if not ppap:
        raise HTTPException(404, "PPAP not found")
    _check_factory_access(ppap, scope)

    from sqlalchemy import select as sa_select
    result = await db.execute(
        sa_select(SupplierPPAPElement).where(
            SupplierPPAPElement.element_id == element_id,
            SupplierPPAPElement.submission_id == ppap_id,
        )
    )
    element = result.scalar_one_or_none()
    if not element:
        raise HTTPException(404, "PPAP element not found")
    try:
        element = await ppap_service.update_element(
            db, element,
            user_id=scope.user.user_id,
            **req.model_dump(exclude_unset=True),
        )
        return ppap_schemas.PPAPElementResponse(
            element_id=element.element_id,
            submission_id=element.submission_id,
            element_no=element.element_no,
            element_name=element.element_name,
            required=element.required,
            status=element.status,
            reviewed_by=element.reviewed_by,
            reviewed_at=element.reviewed_at,
            file_url=element.file_url,
            notes=element.notes,
            sort_order=element.sort_order,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{ppap_id}/transition", response_model=ppap_schemas.PPAPResponse)
async def transition_ppap(
    ppap_id: uuid.UUID,
    req: ppap_schemas.PPAPTransitionRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    perm_level = await get_user_permission(scope.user, Module.PPAP, db)
    if req.action in ("approve", "reject"):
        if perm_level < PermissionLevel.APPROVE:
            raise HTTPException(403, "需要 manager 或 admin 权限")
    elif req.action in ("submit", "resubmit"):
        if perm_level < PermissionLevel.CREATE:
            raise HTTPException(403, "需要 engineer 或更高权限")

    ppap = await ppap_service.get_ppap(db, ppap_id)
    if not ppap:
        raise HTTPException(404, "PPAP not found")
    _check_factory_access(ppap, scope)
    try:
        ppap = await ppap_service.transition_ppap(
            db, ppap, req.action, user_id=scope.user.user_id,
            rejection_reason=req.rejection_reason,
        )
        return _to_response(ppap)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{ppap_id}")
async def delete_ppap(
    ppap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PPAP, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 PPAP 模块的 CREATE 权限")

    ppap = await ppap_service.get_ppap(db, ppap_id)
    if not ppap:
        raise HTTPException(404, "PPAP not found")
    _check_factory_access(ppap, scope)
    try:
        await ppap_service.delete_ppap(db, ppap, scope.user.user_id)
        return {"message": "PPAP 已删除"}
    except ValueError as e:
        raise HTTPException(400, str(e))