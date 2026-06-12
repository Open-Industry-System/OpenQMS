import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_user_permission, Module, PermissionLevel
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import populate_factory_id, validate_factory_invariant
from app.models.change_impact import ChangeImpactAnalysis
from app.schemas.change_impact import ChangeImpactAnalyzeRequest, ChangeImpactAnalysisResponse
from app.services.fmea_service import get_fmea
from app.services.change_impact_service import ChangeImpactService
from app.graph.deps import get_graph_repository
from app.graph.repository import FMEAGraphRepository

router = APIRouter(prefix="/api/change-impact", tags=["change-impact"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="Analysis not found")


@router.post("/analyze", response_model=ChangeImpactAnalysisResponse)
async def analyze_change_impact(
    req: ChangeImpactAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    repo: FMEAGraphRepository = Depends(get_graph_repository),
):
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 EDIT 权限")

    fmea = await get_fmea(db, req.fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    _check_factory_access(fmea, scope)

    # 从 FMEA 图中提取旧值（如果变更的是属性且有字段名）
    old_value = None
    if req.field_name and fmea.graph_data:
        for node in fmea.graph_data.get("nodes", []):
            if node.get("id") == req.node_id:
                old_value = node.get(req.field_name)
                if old_value is not None:
                    old_value = str(old_value)
                break

    service = ChangeImpactService(db, repo)
    try:
        result = await service.analyze(
            fmea_id=req.fmea_id,
            node_id=req.node_id,
            node_type=req.node_type,
            node_name=req.node_name,
            change_type=req.change_type,
            field_name=req.field_name,
            new_value=req.new_value,
            old_value=old_value,
            user_id=scope.user.user_id,
        )
        # Populate and validate factory_id on the new record
        record = await db.execute(
            select(ChangeImpactAnalysis).where(ChangeImpactAnalysis.id == result.id)
        )
        analysis_record = record.scalar_one_or_none()
        if analysis_record:
            await populate_factory_id(analysis_record, ChangeImpactAnalysis, db, scope=scope)
            await validate_factory_invariant(analysis_record, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("", response_model=dict)
async def list_change_impact_analyses(
    product_line_code: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    # Product line filtering via RequestScope
    if scope.pl_scope.mode == "NONE":
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    allowed_pls = scope.pl_scope.codes if scope.pl_scope.mode == "EXPLICIT" else None

    if product_line_code:
        if allowed_pls is not None and product_line_code not in allowed_pls:
            raise HTTPException(status_code=403, detail=f"无权访问产品线 '{product_line_code}'")
        filter_codes = [product_line_code]
    else:
        filter_codes = allowed_pls

    service = ChangeImpactService(db)
    items, total = await service.list_all(
        product_line_codes=filter_codes,
        page=page,
        page_size=page_size,
        factory_id=scope.effective_factory_id,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/fmea/{fmea_id}", response_model=dict)
async def list_change_impact_by_fmea(
    fmea_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    fmea = await get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    _check_factory_access(fmea, scope)

    service = ChangeImpactService(db)
    items, total = await service.list_by_fmea(fmea_id, page=page, page_size=page_size)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{analysis_id}", response_model=ChangeImpactAnalysisResponse)
async def get_change_impact_analysis(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    # Fetch ORM model for factory access check
    result = await db.execute(
        select(ChangeImpactAnalysis).where(ChangeImpactAnalysis.id == analysis_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    _check_factory_access(record, scope)

    # Use service for the response schema
    service = ChangeImpactService(db)
    analysis = await service.get_by_id(analysis_id)
    return analysis