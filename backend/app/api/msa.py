import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.permissions import get_current_user, require_permission, PermissionLevel, Module
from app.models.spc import InspectionCharacteristic
from app.models.gauge import Gauge
from app import schemas
from app.services import (
    grr_service,
    grr_engine,
    bias_service,
    bias_engine,
    linearity_service,
    linearity_engine,
    stability_service,
    stability_engine,
    attribute_service,
    attribute_engine,
)

grr_router = APIRouter(prefix="/api/msa/grr", tags=["msa-grr"])
bias_router = APIRouter(prefix="/api/msa/bias", tags=["msa-bias"])
linearity_router = APIRouter(prefix="/api/msa/linearity", tags=["msa-linearity"])
stability_router = APIRouter(prefix="/api/msa/stability", tags=["msa-stability"])
attribute_router = APIRouter(prefix="/api/msa/attribute", tags=["msa-attribute"])
overview_router = APIRouter(prefix="/api/msa", tags=["msa-overview"])


# ─── GRR routes ───

@grr_router.get("", response_model=schemas.grr.GrrStudyListResponse)
async def list_grr(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    gauge_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await grr_service.list_studies(db, page, page_size, status, gauge_id)
    return schemas.grr.GrrStudyListResponse(
        items=[schemas.grr.GrrStudyResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@grr_router.post("", response_model=schemas.grr.GrrStudyResponse)
async def create_grr(
    req: schemas.grr.GrrStudyCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    try:
        study = await grr_service.create_study(
            db,
            title=req.title,
            method=req.method,
            gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            unit=req.unit,
            tolerance_upper=req.tolerance_upper,
            tolerance_lower=req.tolerance_lower,
            reference_value=req.reference_value,
            appraiser_count=req.appraiser_count,
            part_count=req.part_count,
            trial_count=req.trial_count,
            study_date=req.study_date,
            user_id=user.user_id,
        )
        return schemas.grr.GrrStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@grr_router.get("/{study_id}", response_model=schemas.grr.GrrStudyResponse)
async def get_grr(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    study = await grr_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="GRR study not found")
    return schemas.grr.GrrStudyResponse.model_validate(study)


@grr_router.put("/{study_id}", response_model=schemas.grr.GrrStudyResponse)
async def update_grr(
    study_id: uuid.UUID,
    req: schemas.grr.GrrStudyUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await grr_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="GRR study not found")
    try:
        study = await grr_service.update_study(
            db,
            study,
            user.user_id,
            title=req.title,
            method=req.method,
            gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            unit=req.unit,
            tolerance_upper=req.tolerance_upper,
            tolerance_lower=req.tolerance_lower,
            reference_value=req.reference_value,
            appraiser_count=req.appraiser_count,
            part_count=req.part_count,
            trial_count=req.trial_count,
            study_date=req.study_date,
        )
        return schemas.grr.GrrStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@grr_router.delete("/{study_id}")
async def delete_grr(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await grr_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="GRR study not found")
    try:
        await grr_service.delete_study(db, study, user.user_id)
        return {"message": "GRR study deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@grr_router.post("/{study_id}/measurements")
async def upsert_grr_measurements(
    study_id: uuid.UUID,
    req: schemas.grr.GrrMeasurementBulkUpsert,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    try:
        await grr_service.upsert_measurements(
            db, study_id, [m.model_dump() for m in req.measurements]
        )
        return {"message": "measurements saved", "count": len(req.measurements)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@grr_router.get("/{study_id}/measurements")
async def get_grr_measurements(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    measurements = await grr_service.get_measurements(db, study_id)
    return [
        {
            "measurement_id": str(m.measurement_id),
            "study_id": str(m.study_id),
            "appraiser_name": m.appraiser_name,
            "part_no": m.part_no,
            "trial_no": m.trial_no,
            "value": m.value,
        }
        for m in measurements
    ]


@grr_router.post("/{study_id}/compute", response_model=schemas.grr.GrrResultResponse)
async def compute_grr(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await grr_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="GRR study not found")
    try:
        measurements = await grr_service.get_measurements(db, study_id)
        if not measurements:
            raise ValueError("请先录入测量数据")
        result = grr_engine.compute_grr(study, measurements)
        result = await grr_service.save_result(db, result)
        return schemas.grr.GrrResultResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@grr_router.get("/{study_id}/result", response_model=schemas.grr.GrrResultResponse)
async def get_grr_result(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await grr_service.get_result(db, study_id)
    if not result:
        raise HTTPException(status_code=404, detail="result not computed yet")
    return schemas.grr.GrrResultResponse.model_validate(result)


@grr_router.post("/{study_id}/complete", response_model=schemas.grr.GrrStudyResponse)
async def complete_grr(
    study_id: uuid.UUID,
    accepted: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await grr_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="GRR study not found")
    try:
        study = await grr_service.complete_study(db, study, user.user_id, accepted)
        return schemas.grr.GrrStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Bias routes ───

@bias_router.get("", response_model=schemas.bias.BiasStudyListResponse)
async def list_bias(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    gauge_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await bias_service.list_studies(db, page, page_size, status, gauge_id)
    return schemas.bias.BiasStudyListResponse(
        items=[schemas.bias.BiasStudyResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@bias_router.post("", response_model=schemas.bias.BiasStudyResponse)
async def create_bias(
    req: schemas.bias.BiasStudyCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    try:
        study = await bias_service.create_study(
            db,
            title=req.title,
            gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            unit=req.unit,
            reference_value=req.reference_value,
            sample_size=req.sample_size,
            study_date=req.study_date,
            user_id=user.user_id,
        )
        return schemas.bias.BiasStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@bias_router.get("/{study_id}", response_model=schemas.bias.BiasStudyResponse)
async def get_bias(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    study = await bias_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="bias study not found")
    return schemas.bias.BiasStudyResponse.model_validate(study)


@bias_router.put("/{study_id}", response_model=schemas.bias.BiasStudyResponse)
async def update_bias(
    study_id: uuid.UUID,
    req: schemas.bias.BiasStudyUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await bias_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="bias study not found")
    try:
        study = await bias_service.update_study(
            db,
            study,
            user.user_id,
            title=req.title,
            gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            unit=req.unit,
            reference_value=req.reference_value,
            sample_size=req.sample_size,
            study_date=req.study_date,
        )
        return schemas.bias.BiasStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@bias_router.delete("/{study_id}")
async def delete_bias(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await bias_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="bias study not found")
    try:
        await bias_service.delete_study(db, study, user.user_id)
        return {"message": "bias study deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@bias_router.post("/{study_id}/measurements")
async def upsert_bias_measurements(
    study_id: uuid.UUID,
    req: schemas.bias.BiasMeasurementBulkUpsert,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    try:
        await bias_service.upsert_measurements(
            db, study_id, [m.model_dump() for m in req.measurements]
        )
        return {"message": "measurements saved", "count": len(req.measurements)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@bias_router.get("/{study_id}/measurements")
async def get_bias_measurements(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    measurements = await bias_service.get_measurements(db, study_id)
    return [
        {
            "measurement_id": str(m.measurement_id),
            "study_id": str(m.study_id),
            "value": m.value,
            "sequence_no": m.sequence_no,
        }
        for m in measurements
    ]


@bias_router.post("/{study_id}/compute", response_model=schemas.bias.BiasResultResponse)
async def compute_bias(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await bias_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="bias study not found")
    try:
        measurements = await bias_service.get_measurements(db, study_id)
        if not measurements:
            raise ValueError("请先录入测量数据")
        result = bias_engine.compute_bias(study, measurements)
        result = await bias_service.save_result(db, result)
        return schemas.bias.BiasResultResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@bias_router.get("/{study_id}/result", response_model=schemas.bias.BiasResultResponse)
async def get_bias_result(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await bias_service.get_result(db, study_id)
    if not result:
        raise HTTPException(status_code=404, detail="result not computed yet")
    return schemas.bias.BiasResultResponse.model_validate(result)


@bias_router.post("/{study_id}/complete", response_model=schemas.bias.BiasStudyResponse)
async def complete_bias(
    study_id: uuid.UUID,
    accepted: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await bias_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="bias study not found")
    try:
        study = await bias_service.complete_study(db, study, user.user_id, accepted)
        return schemas.bias.BiasStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Linearity routes ───

@linearity_router.get("", response_model=schemas.linearity.LinearityStudyListResponse)
async def list_linearity(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    gauge_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await linearity_service.list_studies(db, page, page_size, status, gauge_id)
    return schemas.linearity.LinearityStudyListResponse(
        items=[schemas.linearity.LinearityStudyResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@linearity_router.post("", response_model=schemas.linearity.LinearityStudyResponse)
async def create_linearity(
    req: schemas.linearity.LinearityStudyCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    try:
        study = await linearity_service.create_study(
            db,
            title=req.title,
            gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            unit=req.unit,
            tolerance_upper=req.tolerance_upper,
            tolerance_lower=req.tolerance_lower,
            sample_size_per_reference=req.sample_size_per_reference,
            study_date=req.study_date,
            user_id=user.user_id,
        )
        return schemas.linearity.LinearityStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@linearity_router.get("/{study_id}", response_model=schemas.linearity.LinearityStudyResponse)
async def get_linearity(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    study = await linearity_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="linearity study not found")
    return schemas.linearity.LinearityStudyResponse.model_validate(study)


@linearity_router.put("/{study_id}", response_model=schemas.linearity.LinearityStudyResponse)
async def update_linearity(
    study_id: uuid.UUID,
    req: schemas.linearity.LinearityStudyUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await linearity_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="linearity study not found")
    try:
        study = await linearity_service.update_study(
            db,
            study,
            user.user_id,
            title=req.title,
            gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            unit=req.unit,
            tolerance_upper=req.tolerance_upper,
            tolerance_lower=req.tolerance_lower,
            sample_size_per_reference=req.sample_size_per_reference,
            study_date=req.study_date,
        )
        return schemas.linearity.LinearityStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@linearity_router.delete("/{study_id}")
async def delete_linearity(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await linearity_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="linearity study not found")
    try:
        await linearity_service.delete_study(db, study, user.user_id)
        return {"message": "linearity study deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@linearity_router.post("/{study_id}/measurements")
async def upsert_linearity_measurements(
    study_id: uuid.UUID,
    req: schemas.linearity.LinearityMeasurementBulkUpsert,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    try:
        await linearity_service.upsert_measurements(
            db, study_id, [m.model_dump() for m in req.measurements]
        )
        return {"message": "measurements saved", "count": len(req.measurements)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@linearity_router.get("/{study_id}/measurements")
async def get_linearity_measurements(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    measurements = await linearity_service.get_measurements(db, study_id)
    return [
        {
            "measurement_id": str(m.measurement_id),
            "study_id": str(m.study_id),
            "reference_value": m.reference_value,
            "measured_value": m.measured_value,
            "sequence_no": m.sequence_no,
        }
        for m in measurements
    ]


@linearity_router.post("/{study_id}/compute", response_model=schemas.linearity.LinearityResultResponse)
async def compute_linearity(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await linearity_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="linearity study not found")
    try:
        measurements = await linearity_service.get_measurements(db, study_id)
        if not measurements:
            raise ValueError("请先录入测量数据")
        result = linearity_engine.compute_linearity(study, measurements)
        result = await linearity_service.save_result(db, result)
        return schemas.linearity.LinearityResultResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@linearity_router.get("/{study_id}/result", response_model=schemas.linearity.LinearityResultResponse)
async def get_linearity_result(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await linearity_service.get_result(db, study_id)
    if not result:
        raise HTTPException(status_code=404, detail="result not computed yet")
    return schemas.linearity.LinearityResultResponse.model_validate(result)


@linearity_router.post("/{study_id}/complete", response_model=schemas.linearity.LinearityStudyResponse)
async def complete_linearity(
    study_id: uuid.UUID,
    accepted: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await linearity_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="linearity study not found")
    try:
        study = await linearity_service.complete_study(db, study, user.user_id, accepted)
        return schemas.linearity.LinearityStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Stability routes ───

@stability_router.get("", response_model=schemas.stability.StabilityStudyListResponse)
async def list_stability(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    gauge_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await stability_service.list_studies(db, page, page_size, status, gauge_id)
    return schemas.stability.StabilityStudyListResponse(
        items=[schemas.stability.StabilityStudyResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@stability_router.post("", response_model=schemas.stability.StabilityStudyResponse)
async def create_stability(
    req: schemas.stability.StabilityStudyCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    try:
        study = await stability_service.create_study(
            db,
            title=req.title,
            gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            unit=req.unit,
            reference_value=req.reference_value,
            subgroup_size=req.subgroup_size,
            study_date=req.study_date,
            user_id=user.user_id,
        )
        return schemas.stability.StabilityStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@stability_router.get("/{study_id}", response_model=schemas.stability.StabilityStudyResponse)
async def get_stability(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    study = await stability_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="stability study not found")
    return schemas.stability.StabilityStudyResponse.model_validate(study)


@stability_router.put("/{study_id}", response_model=schemas.stability.StabilityStudyResponse)
async def update_stability(
    study_id: uuid.UUID,
    req: schemas.stability.StabilityStudyUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await stability_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="stability study not found")
    try:
        study = await stability_service.update_study(
            db,
            study,
            user.user_id,
            title=req.title,
            gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            unit=req.unit,
            reference_value=req.reference_value,
            subgroup_size=req.subgroup_size,
            study_date=req.study_date,
        )
        return schemas.stability.StabilityStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@stability_router.delete("/{study_id}")
async def delete_stability(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await stability_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="stability study not found")
    try:
        await stability_service.delete_study(db, study, user.user_id)
        return {"message": "stability study deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@stability_router.post("/{study_id}/measurements")
async def upsert_stability_measurements(
    study_id: uuid.UUID,
    req: schemas.stability.StabilityMeasurementBulkUpsert,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    try:
        await stability_service.upsert_measurements(
            db, study_id, [m.model_dump() for m in req.measurements]
        )
        return {"message": "measurements saved", "count": len(req.measurements)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@stability_router.get("/{study_id}/measurements")
async def get_stability_measurements(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    measurements = await stability_service.get_measurements(db, study_id)
    return [
        {
            "measurement_id": str(m.measurement_id),
            "study_id": str(m.study_id),
            "measurement_date": m.measurement_date.isoformat(),
            "sample_mean": m.sample_mean,
            "sample_range": m.sample_range,
            "sequence_no": m.sequence_no,
        }
        for m in measurements
    ]


@stability_router.post("/{study_id}/compute", response_model=schemas.stability.StabilityResultResponse)
async def compute_stability(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await stability_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="stability study not found")
    try:
        measurements = await stability_service.get_measurements(db, study_id)
        if not measurements:
            raise ValueError("请先录入测量数据")
        result = stability_engine.compute_stability(study, measurements)
        result = await stability_service.save_result(db, result)
        return schemas.stability.StabilityResultResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@stability_router.get("/{study_id}/result", response_model=schemas.stability.StabilityResultResponse)
async def get_stability_result(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await stability_service.get_result(db, study_id)
    if not result:
        raise HTTPException(status_code=404, detail="result not computed yet")
    return schemas.stability.StabilityResultResponse.model_validate(result)


@stability_router.post("/{study_id}/complete", response_model=schemas.stability.StabilityStudyResponse)
async def complete_stability(
    study_id: uuid.UUID,
    accepted: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await stability_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="stability study not found")
    try:
        study = await stability_service.complete_study(db, study, user.user_id, accepted)
        return schemas.stability.StabilityStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Attribute routes ───

@attribute_router.get("", response_model=schemas.attribute.AttributeStudyListResponse)
async def list_attribute(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    gauge_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    items, total = await attribute_service.list_studies(db, page, page_size, status, gauge_id)
    return schemas.attribute.AttributeStudyListResponse(
        items=[schemas.attribute.AttributeStudyResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@attribute_router.post("", response_model=schemas.attribute.AttributeStudyResponse)
async def create_attribute(
    req: schemas.attribute.AttributeStudyCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    try:
        study = await attribute_service.create_study(
            db,
            title=req.title,
            gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            method=req.method,
            sample_size=req.sample_size,
            known_standard_count=req.known_standard_count,
            study_date=req.study_date,
            user_id=user.user_id,
        )
        return schemas.attribute.AttributeStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@attribute_router.get("/{study_id}", response_model=schemas.attribute.AttributeStudyResponse)
async def get_attribute(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    study = await attribute_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="attribute study not found")
    return schemas.attribute.AttributeStudyResponse.model_validate(study)


@attribute_router.put("/{study_id}", response_model=schemas.attribute.AttributeStudyResponse)
async def update_attribute(
    study_id: uuid.UUID,
    req: schemas.attribute.AttributeStudyUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await attribute_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="attribute study not found")
    try:
        study = await attribute_service.update_study(
            db,
            study,
            user.user_id,
            title=req.title,
            gauge_id=req.gauge_id,
            characteristic_name=req.characteristic_name,
            spc_characteristic_id=req.spc_characteristic_id,
            method=req.method,
            sample_size=req.sample_size,
            known_standard_count=req.known_standard_count,
            study_date=req.study_date,
        )
        return schemas.attribute.AttributeStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@attribute_router.delete("/{study_id}")
async def delete_attribute(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await attribute_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="attribute study not found")
    try:
        await attribute_service.delete_study(db, study, user.user_id)
        return {"message": "attribute study deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@attribute_router.post("/{study_id}/measurements")
async def upsert_attribute_measurements(
    study_id: uuid.UUID,
    req: schemas.attribute.AttributeMeasurementBulkUpsert,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    try:
        await attribute_service.upsert_measurements(
            db, study_id, [m.model_dump() for m in req.measurements]
        )
        return {"message": "measurements saved", "count": len(req.measurements)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@attribute_router.get("/{study_id}/measurements")
async def get_attribute_measurements(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    measurements = await attribute_service.get_measurements(db, study_id)
    return [
        {
            "measurement_id": str(m.measurement_id),
            "study_id": str(m.study_id),
            "appraiser_name": m.appraiser_name,
            "part_no": m.part_no,
            "known_standard": m.known_standard,
            "appraiser_decision": m.appraiser_decision,
            "trial_no": m.trial_no,
        }
        for m in measurements
    ]


@attribute_router.post("/{study_id}/compute", response_model=schemas.attribute.AttributeResultResponse)
async def compute_attribute(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await attribute_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="attribute study not found")
    try:
        measurements = await attribute_service.get_measurements(db, study_id)
        if not measurements:
            raise ValueError("请先录入测量数据")
        result = attribute_engine.compute_attribute(study, measurements)
        result = await attribute_service.save_result(db, result)
        return schemas.attribute.AttributeResultResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@attribute_router.get("/{study_id}/result", response_model=schemas.attribute.AttributeResultResponse)
async def get_attribute_result(
    study_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await attribute_service.get_result(db, study_id)
    if not result:
        raise HTTPException(status_code=404, detail="result not computed yet")
    return schemas.attribute.AttributeResultResponse.model_validate(result)


@attribute_router.post("/{study_id}/complete", response_model=schemas.attribute.AttributeStudyResponse)
async def complete_attribute(
    study_id: uuid.UUID,
    accepted: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.MSA, PermissionLevel.CREATE)),
):
    study = await attribute_service.get_study(db, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="attribute study not found")
    try:
        study = await attribute_service.complete_study(db, study, user.user_id, accepted)
        return schemas.attribute.AttributeStudyResponse.model_validate(study)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Overview routes ───

@overview_router.get("/studies", response_model=schemas.msa.MsaStudyOverviewListResponse)
async def list_all_msa_studies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: str | None = Query(None),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    from app.models.grr import GrrStudy
    from app.models.bias import BiasStudy
    from app.models.linearity import LinearityStudy
    from app.models.stability import StabilityStudy
    from app.models.attribute import AttributeStudy

    results = []
    type_map = {
        "grr": (GrrStudy, "GRR"),
        "bias": (BiasStudy, "偏倚"),
        "linearity": (LinearityStudy, "线性"),
        "stability": (StabilityStudy, "稳定性"),
        "attribute": (AttributeStudy, "计数型"),
    }

    for study_type, (model, type_label) in type_map.items():
        if type and type != study_type:
            continue
        query = select(model)
        if status:
            query = query.where(model.status == status)
        items = (await db.execute(query)).scalars().all()
        for s in items:
            gauge_name = None
            if hasattr(s, "gauge_id") and s.gauge_id:
                g = await db.get(Gauge, s.gauge_id)
                gauge_name = g.name if g else None
            results.append(
                schemas.msa.MsaStudyOverview(
                    study_id=s.study_id,
                    study_no=s.study_no,
                    type=type_label,
                    title=s.title,
                    gauge_name=gauge_name,
                    status=s.status,
                    study_date=s.study_date,
                    created_at=s.created_at,
                )
            )

    results.sort(key=lambda x: x.created_at, reverse=True)
    total = len(results)
    start = (page - 1) * page_size
    return schemas.msa.MsaStudyOverviewListResponse(
        items=results[start : start + page_size],
        total=total,
        page=page,
        page_size=page_size,
    )


@overview_router.get("/spc-characteristics", response_model=list[schemas.msa.MsaSpcCharacteristic])
async def list_spc_characteristics(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    result = await db.execute(select(InspectionCharacteristic))
    chars = result.scalars().all()
    return [
        schemas.msa.MsaSpcCharacteristic(
            ic_id=c.ic_id,
            ic_code=c.ic_code,
            process_name=c.process_name,
            characteristic_name=c.characteristic_name,
            unit=None,
            spec_upper=float(c.spec_upper) if c.spec_upper is not None else None,
            spec_lower=float(c.spec_lower) if c.spec_lower is not None else None,
        )
        for c in chars
    ]
