import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access, resolve_create_factory_id, validate_factory_invariant
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.database import get_db
from app.services import audit_service

router = APIRouter(prefix="/api/audit-programs", tags=["audit-programs"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="audit program not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="audit program not found")


@router.get("", response_model=schemas.audit.AuditStatsResponse)
async def get_audit_stats(
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 VIEW 权限")
    stats = await audit_service.get_audit_stats(db, factory_id=scope.effective_factory_id)
    return schemas.audit.AuditStatsResponse(**stats)


@router.get("/list", response_model=schemas.audit.AuditProgramListResponse)
async def list_audit_programs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    year: int | None = Query(None),
    audit_type: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 VIEW 权限")
    items, total = await audit_service.list_audit_programs(
        db, page, page_size, year, audit_type, status,
        factory_id=scope.effective_factory_id,
    )
    return schemas.audit.AuditProgramListResponse(
        items=[schemas.audit.AuditProgramResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=schemas.audit.AuditProgramResponse)
async def create_audit_program(
    req: schemas.audit.AuditProgramCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    try:
        factory_id = await resolve_create_factory_id(db, scope)
        check_factory_access(factory_id, scope)
        program = await audit_service.create_audit_program(
            db,
            program_year=req.program_year,
            audit_type=req.audit_type,
            scope=req.scope,
            criteria=req.criteria,
            user_id=scope.user.user_id,
            factory_id=factory_id,
        )
        await validate_factory_invariant(program, db)
        return schemas.audit.AuditProgramResponse.model_validate(program)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{program_id}", response_model=schemas.audit.AuditProgramResponse)
async def get_audit_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 VIEW 权限")
    program = await audit_service.get_audit_program(db, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="audit program not found")
    _check_factory_access(program, scope)
    return schemas.audit.AuditProgramResponse.model_validate(program)


@router.put("/{program_id}", response_model=schemas.audit.AuditProgramResponse)
async def update_audit_program(
    program_id: uuid.UUID,
    req: schemas.audit.AuditProgramUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    program = await audit_service.get_audit_program(db, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="audit program not found")
    _check_factory_access(program, scope)
    try:
        program = await audit_service.update_audit_program(
            db,
            program=program,
            program_year=req.program_year,
            audit_type=req.audit_type,
            scope=req.scope,
            criteria=req.criteria,
            status=req.status,
            user_id=scope.user.user_id,
        )
        return schemas.audit.AuditProgramResponse.model_validate(program)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{program_id}")
async def delete_audit_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.AUDIT, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 audit 模块的 CREATE 权限")
    program = await audit_service.get_audit_program(db, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="audit program not found")
    _check_factory_access(program, scope)
    try:
        await audit_service.delete_audit_program(db, program, scope.user.user_id)
        return {"message": "audit program deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))