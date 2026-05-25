import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_admin, require_engineer_or_admin, require_manager_or_admin
from app.models.user import User
from app import schemas
from app.services import management_review_service

router = APIRouter(prefix="/api/management-reviews", tags=["management-reviews"])


@router.get("", response_model=schemas.management_review.ManagementReviewListResponse)
async def list_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    product_line_code: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await management_review_service.list_reviews(
        db, page, page_size, status, product_line_code
    )
    return schemas.management_review.ManagementReviewListResponse(
        items=[schemas.management_review.ManagementReviewResponse.model_validate(r) for r in items],
        total=total, page=page, page_size=page_size,
    )


@router.post("", response_model=schemas.management_review.ManagementReviewResponse)
async def create_review(
    req: schemas.management_review.ManagementReviewCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        review = await management_review_service.create_review(
            db,
            title=req.title,
            review_date=req.review_date,
            product_line_code=req.product_line_code,
            location=req.location,
            chair_person_id=req.chair_person_id,
            participants=req.participants,
            user_id=user.user_id,
        )
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{review_id}", response_model=schemas.management_review.ManagementReviewResponse)
async def get_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    return schemas.management_review.ManagementReviewResponse.model_validate(review)


@router.put("/{review_id}", response_model=schemas.management_review.ManagementReviewResponse)
async def update_review(
    review_id: uuid.UUID,
    req: schemas.management_review.ManagementReviewUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        fields = req.model_dump(exclude_unset=True)
        review = await management_review_service.update_review(
            db, review, user_id=user.user_id, **fields,
        )
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{review_id}")
async def delete_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        await management_review_service.delete_review(db, review, user.user_id)
        return {"message": "review deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/collect-data", response_model=schemas.management_review.ManagementReviewResponse)
async def collect_data(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        review = await management_review_service.collect_data(db, review, user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/refresh-data", response_model=schemas.management_review.ManagementReviewResponse)
async def refresh_data(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        review = await management_review_service.refresh_data(db, review, user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/back-to-draft", response_model=schemas.management_review.ManagementReviewResponse)
async def back_to_draft(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        review = await management_review_service.back_to_draft(db, review, user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/start-review", response_model=schemas.management_review.ManagementReviewResponse)
async def start_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        review = await management_review_service.start_review(db, review, user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/close", response_model=schemas.management_review.ManagementReviewResponse)
async def close_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        review = await management_review_service.close_review(db, review, user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/reopen", response_model=schemas.management_review.ManagementReviewResponse)
async def reopen_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    try:
        review = await management_review_service.reopen_review(db, review, user.user_id)
        return schemas.management_review.ManagementReviewResponse.model_validate(review)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{review_id}/outputs", response_model=list[schemas.management_review.ReviewOutputResponse])
async def list_outputs(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    outputs = await management_review_service.list_outputs(db, review_id)
    return [schemas.management_review.ReviewOutputResponse.model_validate(o) for o in outputs]


@router.post("/{review_id}/outputs", response_model=schemas.management_review.ReviewOutputResponse)
async def create_output(
    review_id: uuid.UUID,
    req: schemas.management_review.ReviewOutputCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        output = await management_review_service.create_output(
            db, review_id,
            category=req.category,
            description=req.description,
            responsible_id=req.responsible_id,
            due_date=req.due_date,
            user_id=user.user_id,
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
    user: User = Depends(require_engineer_or_admin),
):
    review = await management_review_service.get_review(db, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    outputs = await management_review_service.list_outputs(db, review_id)
    output = next((o for o in outputs if o.output_id == output_id), None)
    if output is None:
        raise HTTPException(status_code=404, detail="output not found")
    try:
        fields = req.model_dump(exclude_unset=True)
        output = await management_review_service.update_output(
            db, output,
            review_is_closed=(review.status == "closed"),
            user_id=user.user_id,
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
    user: User = Depends(require_admin),
):
    outputs = await management_review_service.list_outputs(db, review_id)
    output = next((o for o in outputs if o.output_id == output_id), None)
    if output is None:
        raise HTTPException(status_code=404, detail="output not found")
    try:
        await management_review_service.delete_output(db, output, user.user_id)
        return {"message": "output deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{review_id}/outputs/{output_id}/verify", response_model=schemas.management_review.ReviewOutputResponse)
async def verify_output(
    review_id: uuid.UUID,
    output_id: uuid.UUID,
    req: schemas.management_review.ReviewOutputVerify,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    outputs = await management_review_service.list_outputs(db, review_id)
    output = next((o for o in outputs if o.output_id == output_id), None)
    if output is None:
        raise HTTPException(status_code=404, detail="output not found")
    try:
        output = await management_review_service.verify_output(
            db, output,
            verification_notes=req.verification_notes,
            user_id=user.user_id,
        )
        return schemas.management_review.ReviewOutputResponse.model_validate(output)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))