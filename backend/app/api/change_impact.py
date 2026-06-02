import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_current_user, require_permission, Module, PermissionLevel
from app.core.product_line_filter import enforce_product_line_access, get_user_product_line_codes
from app.models.user import User
from app.schemas.change_impact import ChangeImpactAnalyzeRequest, ChangeImpactAnalysisResponse
from app.services.fmea_service import get_fmea
from app.services.change_impact_service import ChangeImpactService
from app.graph.deps import get_graph_repository
from app.graph.repository import FMEAGraphRepository

router = APIRouter(prefix="/api/change-impact", tags=["change-impact"])


@router.post("/analyze", response_model=ChangeImpactAnalysisResponse)
async def analyze_change_impact(
    req: ChangeImpactAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.FMEA, PermissionLevel.EDIT)),
    repo: FMEAGraphRepository = Depends(get_graph_repository),
):
    fmea = await get_fmea(db, req.fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)

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
            user_id=user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.get("", response_model=dict)
async def list_change_impact_analyses(
    product_line_code: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role_definition.bypass_row_level_security:
        filter_codes = [product_line_code] if product_line_code else None
    else:
        user_codes = await get_user_product_line_codes(user, db)
        if not user_codes:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        if product_line_code:
            if product_line_code not in user_codes:
                raise HTTPException(403, f"无权访问产品线 '{product_line_code}'")
            filter_codes = [product_line_code]
        else:
            filter_codes = user_codes

    service = ChangeImpactService(db)
    items, total = await service.list_all(
        product_line_codes=filter_codes, page=page, page_size=page_size
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
    user: User = Depends(get_current_user),
):
    fmea = await get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)

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
    user: User = Depends(get_current_user),
):
    service = ChangeImpactService(db)
    record = await service.get_by_id(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    await enforce_product_line_access(user, record.product_line_code, db)
    return record
