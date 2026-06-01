import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.permissions import get_current_user, require_permission, PermissionLevel, Module
from app.models.user import User
from app import schemas
from app.services import audit_service

router = APIRouter(prefix="/api/audit-programs", tags=["audit-programs"])


@router.get("", response_model=schemas.audit.AuditStatsResponse)
async def get_audit_stats(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stats = await audit_service.get_audit_stats(db)
    return schemas.audit.AuditStatsResponse(**stats)


@router.get("/list", response_model=schemas.audit.AuditProgramListResponse)
async def list_audit_programs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    year: int | None = Query(None),
    audit_type: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await audit_service.list_audit_programs(
        db, page, page_size, year, audit_type, status
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
    user: User = Depends(require_permission(Module.AUDIT, PermissionLevel.CREATE)),
):
    try:
        program = await audit_service.create_audit_program(
            db,
            program_year=req.program_year,
            audit_type=req.audit_type,
            scope=req.scope,
            criteria=req.criteria,
            user_id=user.user_id,
        )
        return schemas.audit.AuditProgramResponse.model_validate(program)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{program_id}", response_model=schemas.audit.AuditProgramResponse)
async def get_audit_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    program = await audit_service.get_audit_program(db, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="audit program not found")
    return schemas.audit.AuditProgramResponse.model_validate(program)


@router.put("/{program_id}", response_model=schemas.audit.AuditProgramResponse)
async def update_audit_program(
    program_id: uuid.UUID,
    req: schemas.audit.AuditProgramUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.AUDIT, PermissionLevel.CREATE)),
):
    program = await audit_service.get_audit_program(db, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="audit program not found")
    try:
        program = await audit_service.update_audit_program(
            db,
            program=program,
            program_year=req.program_year,
            audit_type=req.audit_type,
            scope=req.scope,
            criteria=req.criteria,
            status=req.status,
            user_id=user.user_id,
        )
        return schemas.audit.AuditProgramResponse.model_validate(program)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{program_id}")
async def delete_audit_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.AUDIT, PermissionLevel.CREATE)),
):
    program = await audit_service.get_audit_program(db, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="audit program not found")
    try:
        await audit_service.delete_audit_program(db, program, user.user_id)
        return {"message": "audit program deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
