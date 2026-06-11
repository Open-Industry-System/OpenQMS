import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import (
    get_current_user, require_permission,
    PermissionLevel, Module,
)
from app.models.user import User
from app.models.cp_validation import (
    CPValidationRun, CPValidationFinding, CPValidationOccurrence,
)
from app.schemas.cp_validation import (
    ValidationRunResponse,
    ValidationResultItem,
    ValidationSummaryResponse,
    ValidationResultsListResponse,
)
from app.services.cp_validation import CPValidationEngine, ValidationAlreadyRunning

router = APIRouter(prefix="/api", tags=["cp-validation"])


class ValidationSummariesRequest(BaseModel):
    cp_ids: list[uuid.UUID]


class ValidationSummariesResponse(BaseModel):
    summaries: dict[str, ValidationSummaryResponse]


@router.post("/control-plans/validation-summaries", response_model=ValidationSummariesResponse)
async def batch_validation_summaries(
    req: ValidationSummariesRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.VIEW)),
):
    """Batch fetch validation summaries for multiple control plans (list page N+1 fix)."""
    from sqlalchemy import func as sql_func

    # Latest run per cp_id
    subq = (
        select(
            CPValidationRun.cp_id,
            sql_func.max(CPValidationRun.started_at).label("max_started"),
        )
        .where(CPValidationRun.cp_id.in_(req.cp_ids))
        .group_by(CPValidationRun.cp_id)
        .subquery("latest_runs")
    )

    latest = (
        select(CPValidationRun)
        .join(
            subq,
            and_(
                CPValidationRun.cp_id == subq.c.cp_id,
                CPValidationRun.started_at == subq.c.max_started,
            ),
        )
        .subquery("latest")
    )

    # Status counts per cp
    # Join latest subquery to scope occurrences to the most recent run only
    counts_result = await db.execute(
        select(
            CPValidationFinding.cp_id,
            CPValidationFinding.status,
            sql_func.count(),
        )
        .join(
            latest,
            latest.c.cp_id == CPValidationFinding.cp_id,
        )
        .join(
            CPValidationOccurrence,
            and_(
                CPValidationOccurrence.finding_id == CPValidationFinding.finding_id,
                CPValidationOccurrence.present == True,
                CPValidationOccurrence.run_id == latest.c.run_id,
            ),
        )
        .where(CPValidationFinding.cp_id.in_(req.cp_ids))
        .group_by(CPValidationFinding.cp_id, CPValidationFinding.status)
    )

    # Organize: cp_id -> {status -> count}
    status_map: dict[str, dict[str, int]] = {}
    for cp_id_val, status_val, cnt in counts_result.all():
        cp_key = str(cp_id_val)
        if cp_key not in status_map:
            status_map[cp_key] = {}
        status_map[cp_key][status_val] = cnt

    # Fetch latest run rows via the subquery (already joined above)
    run_result = await db.execute(
        select(CPValidationRun).join(
            subq,
            and_(
                CPValidationRun.cp_id == subq.c.cp_id,
                CPValidationRun.started_at == subq.c.max_started,
            ),
        )
    )
    run_rows = run_result.scalars().all()

    latest_by_cp: dict[str, CPValidationRun] = {}
    for r in run_rows:
        latest_by_cp[str(r.cp_id)] = r

    summaries: dict[str, ValidationSummaryResponse] = {}
    for cp_key, run in latest_by_cp.items():
        sc = status_map.get(cp_key, {})
        summaries[cp_key] = ValidationSummaryResponse(
            run_id=run.run_id,
            status=run.status,
            total=run.rule_count,
            error_count=run.error_count,
            warning_count=run.warning_count,
            info_count=run.info_count,
            open_count=sc.get("open", 0),
            resolved_count=sc.get("resolved", 0),
            rejected_count=sc.get("rejected", 0),
        )

    return ValidationSummariesResponse(summaries=summaries)


def _row_to_result_item(occ: CPValidationOccurrence, finding: CPValidationFinding) -> ValidationResultItem:
    return ValidationResultItem(
        occurrence_id=occ.occurrence_id,
        run_id=occ.run_id,
        finding_id=finding.finding_id,
        cp_id=occ.cp_id,
        validation_type=occ.validation_type,
        rule_id=finding.rule_id,
        severity=finding.severity,
        category=finding.category,
        title=occ.title,
        description=occ.description,
        affected_items=occ.affected_items or [],
        fmea_node_ids=occ.fmea_node_ids or [],
        suggestion=occ.suggestion,
        suggestion_data=occ.suggestion_data,
        status=finding.status,
        resolved_by=finding.resolved_by,
        resolved_at=finding.resolved_at,
        present=occ.present,
        created_at=occ.created_at,
    )


async def _get_latest_run(db: AsyncSession, cp_id: uuid.UUID) -> CPValidationRun | None:
    result = await db.execute(
        select(CPValidationRun)
        .where(CPValidationRun.cp_id == cp_id)
        .order_by(desc(CPValidationRun.started_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/control-plans/{cp_id}/validation-results", response_model=ValidationResultsListResponse)
async def list_validation_results(
    cp_id: uuid.UUID,
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.VIEW)),
):
    """List validation results for latest run (join occurrences + findings)."""
    latest_run = await _get_latest_run(db, cp_id)
    if latest_run is None:
        return ValidationResultsListResponse(items=[], total=0)

    query = select(CPValidationOccurrence, CPValidationFinding).join(
        CPValidationFinding,
        CPValidationOccurrence.finding_id == CPValidationFinding.finding_id,
    ).where(
        CPValidationOccurrence.run_id == latest_run.run_id,
        CPValidationOccurrence.present == True,
    )
    if status_filter:
        query = query.where(CPValidationFinding.status == status_filter)
    if severity:
        query = query.where(CPValidationFinding.severity == severity)

    result = await db.execute(query)
    rows = result.all()

    items = [_row_to_result_item(occ, finding) for occ, finding in rows]
    return ValidationResultsListResponse(items=items, total=len(items))


@router.post("/control-plans/{cp_id}/validate", response_model=ValidationRunResponse)
async def trigger_validation(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    """Manually trigger a validation run. Synchronous — waits for completion."""
    engine = CPValidationEngine()
    try:
        run = await engine.validate(db, cp_id, user.user_id, trigger="manual")
    except ValidationAlreadyRunning:
        raise HTTPException(status_code=409, detail="该控制计划的校验正在运行中")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="校验执行失败")

    return ValidationRunResponse.model_validate(run)


@router.get("/control-plans/{cp_id}/validation-runs", response_model=list[ValidationRunResponse])
async def list_validation_runs(
    cp_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.VIEW)),
):
    """List validation run history for a control plan."""
    result = await db.execute(
        select(CPValidationRun)
        .where(CPValidationRun.cp_id == cp_id)
        .order_by(desc(CPValidationRun.started_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [ValidationRunResponse.model_validate(r) for r in rows]


@router.get("/control-plans/{cp_id}/validation-summary", response_model=ValidationSummaryResponse)
async def get_validation_summary(
    cp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.VIEW)),
):
    """Get summary of the latest validation run."""
    latest_run = await _get_latest_run(db, cp_id)
    if latest_run is None:
        return ValidationSummaryResponse()

    # Severity counts from present occurrences joined to findings
    counts_result = await db.execute(
        select(CPValidationFinding.status, func.count())
        .join(
            CPValidationOccurrence,
            and_(
                CPValidationOccurrence.finding_id == CPValidationFinding.finding_id,
                CPValidationOccurrence.run_id == latest_run.run_id,
                CPValidationOccurrence.present == True,
            ),
        )
        .where(CPValidationFinding.cp_id == cp_id)
        .group_by(CPValidationFinding.status)
    )
    status_counts = {status: count for status, count in counts_result.all()}

    return ValidationSummaryResponse(
        run_id=latest_run.run_id,
        status=latest_run.status,
        total=latest_run.rule_count,
        error_count=latest_run.error_count,
        warning_count=latest_run.warning_count,
        info_count=latest_run.info_count,
        open_count=status_counts.get("open", 0),
        resolved_count=status_counts.get("resolved", 0),
        rejected_count=status_counts.get("rejected", 0),
    )


async def _get_finding(db: AsyncSession, finding_id: uuid.UUID) -> CPValidationFinding:
    result = await db.execute(
        select(CPValidationFinding).where(CPValidationFinding.finding_id == finding_id)
    )
    finding = result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=404, detail="校验结果不存在")
    return finding


async def _get_latest_occurrence(db: AsyncSession, finding_id: uuid.UUID) -> CPValidationOccurrence:
    result = await db.execute(
        select(CPValidationOccurrence)
        .where(CPValidationOccurrence.finding_id == finding_id)
        .order_by(desc(CPValidationOccurrence.created_at))
        .limit(1)
    )
    return result.scalar_one()


async def _find_and_respond(db: AsyncSession, finding_id: uuid.UUID) -> ValidationResultItem:
    finding = await _get_finding(db, finding_id)
    occ = await _get_latest_occurrence(db, finding_id)
    return _row_to_result_item(occ, finding)


@router.post("/validation-results/{finding_id}/reject", response_model=ValidationResultItem)
async def reject_validation_result(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    """Reject a validation finding."""
    finding = await _get_finding(db, finding_id)
    finding.status = "rejected"
    finding.resolved_by = user.user_id
    finding.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return await _find_and_respond(db, finding_id)


@router.post("/validation-results/{finding_id}/resolve", response_model=ValidationResultItem)
async def resolve_validation_result(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    """Mark a validation finding as resolved."""
    finding = await _get_finding(db, finding_id)
    finding.status = "resolved"
    finding.resolved_by = user.user_id
    finding.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return await _find_and_respond(db, finding_id)


@router.post("/validation-results/{finding_id}/reopen", response_model=ValidationResultItem)
async def reopen_validation_result(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLANNING, PermissionLevel.EDIT)),
):
    """Reopen a rejected or resolved validation finding."""
    finding = await _get_finding(db, finding_id)
    if finding.status not in ("rejected", "resolved"):
        raise HTTPException(status_code=400, detail="只能重新打开已拒绝或已解决的项目")
    finding.status = "open"
    finding.resolved_by = None
    finding.resolved_at = None
    await db.commit()
    return await _find_and_respond(db, finding_id)
