import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access, resolve_create_factory_id, validate_factory_invariant
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.database import get_db
from app.services import management_review_report_service as report_service
from app.services import management_review_service

router = APIRouter(prefix="/api/management-reviews", tags=["management-reviews"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="review not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="review not found")


def _resolve_allowed_pls(scope: RequestScope) -> list[str] | None:
    """Resolve allowed product line codes from scope. Returns None for ALL mode, empty list for NONE."""
    if scope.pl_scope.mode == "NONE":
        return []
    elif scope.pl_scope.mode == "EXPLICIT":
        return scope.pl_scope.codes
    return None  # ALL mode — no restriction


@router.get("", response_model=schemas.management_review.ManagementReviewListResponse)
async def list_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    product_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 VIEW 权限")

    allowed_pls = _resolve_allowed_pls(scope)
    if allowed_pls is not None and not allowed_pls:
        return schemas.management_review.ManagementReviewListResponse(
            items=[], total=0, page=page, page_size=page_size,
        )

    items, total = await management_review_service.list_reviews(
        db, page, page_size, status, product_line_code,
        allowed_product_line_codes=allowed_pls,
        factory_id=scope.effective_factory_id,
    )
    return schemas.management_review.ManagementReviewListResponse(
        items=[schemas.management_review.ManagementReviewResponse.model_validate(r) for r in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", response_model=schemas.management_review.ManagementReviewResponse)
async def create_review(
    req: schemas.management_review.ManagementReviewCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 CREATE 权限")
    try:
        factory_id = await resolve_create_factory_id(db, scope, product_line_code=req.product_line_code)
        check_factory_access(factory_id, scope)
        review = await management_review_service.create_review(
            db,
            title=req.title,
            review_date=req.review_date,
            product_line_code=req.product_line_code,
            location=req.location,
            chair_person_id=req.chair_person_id,
            participants=req.participants,
            user_id=scope.user.user_id,
            factory_id=factory_id,
        )
        await validate_factory_invariant(review, db)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{review_id}", response_model=schemas.management_review.ManagementReviewResponse)
async def get_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 VIEW 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    return schemas.management_review.ManagementReviewResponse.model_validate(review)


@router.put("/{review_id}", response_model=schemas.management_review.ManagementReviewResponse)
async def update_review(
    review_id: uuid.UUID,
    req: schemas.management_review.ManagementReviewUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 CREATE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        fields = req.model_dump(exclude_unset=True)
        review = await management_review_service.update_review(
            db, review, user_id=scope.user.user_id, **fields,
        )
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{review_id}")
async def delete_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.ADMIN:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 ADMIN 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        await management_review_service.delete_review(db, review, scope.user.user_id)
        return {"message": "review deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/collect-data", response_model=schemas.management_review.ManagementReviewResponse)
async def collect_data(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 CREATE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        review = await management_review_service.collect_data(db, review, scope.user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/refresh-data", response_model=schemas.management_review.ManagementReviewResponse)
async def refresh_data(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 CREATE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        review = await management_review_service.refresh_data(db, review, scope.user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/back-to-draft", response_model=schemas.management_review.ManagementReviewResponse)
async def back_to_draft(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 CREATE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        review = await management_review_service.back_to_draft(db, review, scope.user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/start-review", response_model=schemas.management_review.ManagementReviewResponse)
async def start_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 CREATE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        review = await management_review_service.start_review(db, review, scope.user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/close", response_model=schemas.management_review.ManagementReviewResponse)
async def close_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 APPROVE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        review = await management_review_service.close_review(db, review, scope.user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/reopen", response_model=schemas.management_review.ManagementReviewResponse)
async def reopen_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 APPROVE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        review = await management_review_service.reopen_review(db, review, scope.user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{review_id}/outputs", response_model=list[schemas.management_review.ReviewOutputResponse])
async def list_outputs(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 VIEW 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    outputs = await management_review_service.list_outputs(db, review_id)
    return [schemas.management_review.ReviewOutputResponse.model_validate(o) for o in outputs]


@router.post("/{review_id}/outputs", response_model=schemas.management_review.ReviewOutputResponse)
async def create_output(
    review_id: uuid.UUID,
    req: schemas.management_review.ReviewOutputCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 CREATE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        output = await management_review_service.create_output(
            db, review_id,
            category=req.category,
            description=req.description,
            responsible_id=req.responsible_id,
            due_date=req.due_date,
            user_id=scope.user.user_id,
        )
        return schemas.management_review.ReviewOutputResponse.model_validate(output)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{review_id}/outputs/{output_id}", response_model=schemas.management_review.ReviewOutputResponse)
async def update_output(
    review_id: uuid.UUID,
    output_id: uuid.UUID,
    req: schemas.management_review.ReviewOutputUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 CREATE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    outputs = await management_review_service.list_outputs(db, review_id)
    output = next((o for o in outputs if o.output_id == output_id), None)
    if output is None:
        raise HTTPException(status_code=404, detail="output not found")
    try:
        fields = req.model_dump(exclude_unset=True)
        output = await management_review_service.update_output(
            db, output,
            review_is_closed=(review.status == "closed"),
            user_id=scope.user.user_id,
            **fields,
        )
        return schemas.management_review.ReviewOutputResponse.model_validate(output)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{review_id}/outputs/{output_id}")
async def delete_output(
    review_id: uuid.UUID,
    output_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.ADMIN:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 ADMIN 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    outputs = await management_review_service.list_outputs(db, review_id)
    output = next((o for o in outputs if o.output_id == output_id), None)
    if output is None:
        raise HTTPException(status_code=404, detail="output not found")
    try:
        await management_review_service.delete_output(db, output, scope.user.user_id)
        return {"message": "output deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/outputs/{output_id}/verify", response_model=schemas.management_review.ReviewOutputResponse)
async def verify_output(
    review_id: uuid.UUID,
    output_id: uuid.UUID,
    req: schemas.management_review.ReviewOutputVerify,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 APPROVE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    outputs = await management_review_service.list_outputs(db, review_id)
    output = next((o for o in outputs if o.output_id == output_id), None)
    if output is None:
        raise HTTPException(status_code=404, detail="output not found")
    try:
        output = await management_review_service.verify_output(
            db, output,
            verification_notes=req.verification_notes,
            user_id=scope.user.user_id,
        )
        return schemas.management_review.ReviewOutputResponse.model_validate(output)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Report endpoints

@router.post("/{review_id}/report/generate", response_model=schemas.management_review.ReportGenerateResponse)
async def generate_report(
    review_id: uuid.UUID,
    req: schemas.management_review.ReportGenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 CREATE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        llm_provider = getattr(request.app.state, "llm_provider", None)
        report_llm_timeout = getattr(request.app.state, "report_llm_timeout", None)
        content = await report_service.generate_report(
            db, review, scope.user,
            llm_provider=llm_provider, use_llm=req.use_llm,
            report_llm_timeout=report_llm_timeout,
        )
        return schemas.management_review.ReportGenerateResponse(
            report_status=review.report_status,
            generated_report=schemas.management_review.ReportContent.model_validate(content),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/report/save-draft", response_model=schemas.management_review.ReportGenerateResponse)
async def save_report_draft(
    review_id: uuid.UUID,
    req: schemas.management_review.ReportSaveDraftRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 CREATE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        content = await report_service.save_report_draft(
            db, review, req.generated_report.model_dump(), scope.user,
        )
        return schemas.management_review.ReportGenerateResponse(
            report_status=review.report_status,
            generated_report=schemas.management_review.ReportContent.model_validate(content),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/report/finalize", response_model=schemas.management_review.ReportVersionResponse)
async def finalize_report(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 APPROVE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        snapshot = await report_service.finalize_report(db, review, scope.user)
        return schemas.management_review.ReportVersionResponse.model_validate(snapshot)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/report/reopen", response_model=schemas.management_review.ManagementReviewResponse)
async def reopen_report(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 APPROVE 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    try:
        review = await report_service.reopen_report_to_draft(db, review, scope.user)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{review_id}/report/versions", response_model=list[schemas.management_review.ReportVersionResponse])
async def list_report_versions(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 VIEW 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    versions = await report_service.list_report_versions(db, review_id)
    return [schemas.management_review.ReportVersionResponse.model_validate(v) for v in versions]


@router.get("/{review_id}/report/versions/{report_id}", response_model=schemas.management_review.ReportVersionResponse)
async def get_report_version(
    review_id: uuid.UUID,
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 VIEW 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    version = await report_service.get_report_version(db, report_id)
    if version is None or version.review_id != review_id:
        raise HTTPException(status_code=404, detail="report version not found")
    return schemas.management_review.ReportVersionResponse.model_validate(version)


@router.get("/{review_id}/report/export", response_model=schemas.management_review.ReportExportResponse)
async def export_report(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.MANAGEMENT_REVIEW, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 management_review 模块的 VIEW 权限")
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    _check_factory_access(review, scope)
    await db.refresh(review, ["generated_report"])
    if not review.generated_report:
        raise HTTPException(status_code=404, detail="report not generated")
    markdown = report_service.export_report_markdown(review.generated_report)
    return schemas.management_review.ReportExportResponse(markdown=markdown)