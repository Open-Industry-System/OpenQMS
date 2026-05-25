"""Version management API routes for FMEA and Control Plan documents."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin, require_manager_or_admin
from app.models.user import User
from app.services import fmea_service, control_plan_service
from app.services.version_service import (
    list_fmea_versions,
    get_fmea_version,
    create_fmea_version,
    verify_fmea_version,
    rollback_fmea,
    list_cp_versions,
    get_cp_version,
    create_cp_version,
    verify_cp_version,
    rollback_control_plan,
    get_fmea_version_by_id,
    build_sync_preview,
    apply_sync_preview,
)
from app.services.diff_engine import diff_fmea_graphs, diff_cp_items, diff_cp_headers
from app.schemas.version import (
    FMEAVersionListItem,
    FMEAVersionDetail,
    ControlPlanVersionListItem,
    ControlPlanVersionDetail,
    VersionListResponse,
    ManualVersionCreate,
    RollbackRequest,
    RollbackResponse,
    FMEADiffResult,
    ModifiedNode,
    CPDiffResult,
    CPItemDiff,
    DiffSummary,
    FMEACompareResponse,
    CPCompareResponse,
    VerifyResponse,
    SyncPreviewItem,
    SyncPreviewResponse,
)

router = APIRouter(prefix="/api/versions", tags=["versions"])


# ---------------------------------------------------------------------------
# FMEA version endpoints
# ---------------------------------------------------------------------------

@router.get("/fmea/{fmea_id}", response_model=VersionListResponse)
async def list_fmea_version_list(
    fmea_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    major_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    items, total = await list_fmea_versions(db, fmea_id, page, page_size, major_only)
    return VersionListResponse(
        items=[FMEAVersionListItem.model_validate(v) for v in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/fmea/{fmea_id}/{major}/{minor}", response_model=FMEAVersionDetail)
async def get_fmea_version_detail(
    fmea_id: uuid.UUID,
    major: int,
    minor: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    version = await get_fmea_version(db, fmea_id, major, minor)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return FMEAVersionDetail.model_validate(version)


@router.post("/fmea/{fmea_id}", response_model=FMEAVersionDetail, status_code=201)
async def manual_create_fmea_version(
    fmea_id: uuid.UUID,
    req: ManualVersionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    version = await create_fmea_version(
        db, fmea, "manual", req.change_summary, user.user_id,
    )
    return FMEAVersionDetail.model_validate(version)


@router.post("/fmea/{fmea_id}/rollback", response_model=RollbackResponse)
async def rollback_fmea_version(
    fmea_id: uuid.UUID,
    req: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    try:
        version = await rollback_fmea(
            db, fmea, req.target_major, req.target_minor, req.reason, user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RollbackResponse.model_validate(version)


@router.get("/fmea/{fmea_id}/compare", response_model=FMEACompareResponse)
async def compare_fmea_versions(
    fmea_id: uuid.UUID,
    v1_major: int = Query(..., description="Source version major"),
    v1_minor: int = Query(..., description="Source version minor"),
    v2_major: int = Query(..., description="Target version major"),
    v2_minor: int = Query(..., description="Target version minor"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    v1 = await get_fmea_version(db, fmea_id, v1_major, v1_minor)
    v2 = await get_fmea_version(db, fmea_id, v2_major, v2_minor)
    if v1 is None or v2 is None:
        raise HTTPException(status_code=404, detail="One or both versions not found")
    raw_diff = diff_fmea_graphs(v1.snapshot, v2.snapshot)
    diff = FMEADiffResult(
        added_nodes=raw_diff["added_nodes"],
        deleted_nodes=raw_diff["deleted_nodes"],
        modified_nodes=[ModifiedNode(**n) for n in raw_diff["modified_nodes"]],
    )
    return FMEACompareResponse(
        v1_major=v1_major,
        v1_minor=v1_minor,
        v2_major=v2_major,
        v2_minor=v2_minor,
        diff=diff,
        summary=DiffSummary(
            total_added=len(diff.added_nodes),
            total_deleted=len(diff.deleted_nodes),
            total_modified=len(diff.modified_nodes),
        ),
    )


@router.get("/fmea/{fmea_id}/verify/{version_id}", response_model=VerifyResponse)
async def verify_fmea_version_integrity(
    fmea_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        valid = await verify_fmea_version(db, version_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    # Fetch hash for response
    version = await get_fmea_version_by_id(db, version_id)
    return VerifyResponse(version_id=version_id, valid=valid, sha256_hash=version.sha256_hash)


# ---------------------------------------------------------------------------
# Control Plan version endpoints
# ---------------------------------------------------------------------------

@router.get("/cp/{cp_id}", response_model=VersionListResponse)
async def list_cp_version_list(
    cp_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    major_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    items, total = await list_cp_versions(db, cp_id, page, page_size, major_only)
    return VersionListResponse(
        items=[ControlPlanVersionListItem.model_validate(v) for v in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/cp/{cp_id}/{major}/{minor}", response_model=ControlPlanVersionDetail)
async def get_cp_version_detail(
    cp_id: uuid.UUID,
    major: int,
    minor: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    version = await get_cp_version(db, cp_id, major, minor)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return ControlPlanVersionDetail.model_validate(version)


@router.post("/cp/{cp_id}", response_model=ControlPlanVersionDetail, status_code=201)
async def manual_create_cp_version(
    cp_id: uuid.UUID,
    req: ManualVersionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    version = await create_cp_version(
        db, cp, "manual", req.change_summary, user.user_id,
    )
    return ControlPlanVersionDetail.model_validate(version)


@router.post("/cp/{cp_id}/rollback", response_model=RollbackResponse)
async def rollback_cp_version(
    cp_id: uuid.UUID,
    req: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    try:
        version = await rollback_control_plan(
            db, cp, req.target_major, req.target_minor, req.reason, user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RollbackResponse.model_validate(version)


@router.get("/cp/{cp_id}/compare", response_model=CPCompareResponse)
async def compare_cp_versions(
    cp_id: uuid.UUID,
    v1_major: int = Query(..., description="Source version major"),
    v1_minor: int = Query(..., description="Source version minor"),
    v2_major: int = Query(..., description="Target version major"),
    v2_minor: int = Query(..., description="Target version minor"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    v1 = await get_cp_version(db, cp_id, v1_major, v1_minor)
    v2 = await get_cp_version(db, cp_id, v2_major, v2_minor)
    if v1 is None or v2 is None:
        raise HTTPException(status_code=404, detail="One or both versions not found")

    header_diffs = diff_cp_headers(v1.header_snapshot, v2.header_snapshot)
    items_diff = diff_cp_items(v1.items_snapshot, v2.items_snapshot)

    diff = CPDiffResult(
        header_changes=header_diffs,
        added_items=items_diff["added_items"],
        deleted_items=items_diff["deleted_items"],
        modified_items=[CPItemDiff(**i) for i in items_diff["modified_items"]],
    )
    return CPCompareResponse(
        v1_major=v1_major,
        v1_minor=v1_minor,
        v2_major=v2_major,
        v2_minor=v2_minor,
        diff=diff,
        summary=DiffSummary(
            total_added=len(diff.added_items),
            total_deleted=len(diff.deleted_items),
            total_modified=len(diff.modified_items) + len(diff.header_changes),
        ),
    )


@router.get("/cp/{cp_id}/verify/{version_id}", response_model=VerifyResponse)
async def verify_cp_version_integrity(
    cp_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        valid = await verify_cp_version(db, version_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    from app.services.version_service import get_latest_cp_version
    # Fetch version for hash - use get_cp_version which needs cp_id + major/minor
    # Instead, query directly
    from sqlalchemy import select
    from app.models.control_plan_version import ControlPlanVersion
    result = await db.execute(
        select(ControlPlanVersion).where(ControlPlanVersion.version_id == version_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return VerifyResponse(version_id=version_id, valid=valid, sha256_hash=version.sha256_hash)


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------

@router.get("/cp/{cp_id}/sync-preview", response_model=SyncPreviewResponse)
async def get_sync_preview(
    cp_id: uuid.UUID,
    fmea_version_id: uuid.UUID = Query(..., description="FMEA version ID to sync from"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    fmea_version = await get_fmea_version_by_id(db, fmea_version_id)
    if fmea_version is None:
        raise HTTPException(status_code=404, detail="FMEA version not found")
    preview = await build_sync_preview(db, cp, fmea_version)
    return SyncPreviewResponse(
        fmea_version_id=fmea_version.version_id,
        fmea_version_label=f"v{fmea_version.major_no}.{fmea_version.minor_no}",
        cp_id=cp_id,
        items=[SyncPreviewItem(**p) for p in preview],
    )


@router.post("/cp/{cp_id}/sync-from-fmea", response_model=ControlPlanVersionDetail)
async def sync_from_fmea(
    cp_id: uuid.UUID,
    fmea_version_id: uuid.UUID = Query(..., description="FMEA version ID to sync from"),
    accepted_item_ids: list[str] = [],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    cp = await control_plan_service.get_control_plan(db, cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="控制计划不存在")
    fmea_version = await get_fmea_version_by_id(db, fmea_version_id)
    if fmea_version is None:
        raise HTTPException(status_code=404, detail="FMEA version not found")
    if not accepted_item_ids:
        raise HTTPException(status_code=400, detail="No items selected for sync")
    try:
        version = await apply_sync_preview(
            db, cp, fmea_version, accepted_item_ids, user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ControlPlanVersionDetail.model_validate(version)
