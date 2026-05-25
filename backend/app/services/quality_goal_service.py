import uuid
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models.quality_goal import QualityGoal
from app.models.audit import AuditLog


async def _generate_doc_no(db: AsyncSession) -> str:
    year = datetime.now().year
    prefix = f"QG-{year}"
    result = await db.execute(
        select(func.count()).where(QualityGoal.doc_no.like(f"{prefix}-%"))
    )
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


async def _validate_hierarchy(db: AsyncSession, parent_id: uuid.UUID | None, level: int) -> None:
    if level == 1 and parent_id is not None:
        raise ValueError("company-level goal must not have a parent")
    if level > 1 and parent_id is None:
        raise ValueError(f"level {level} goal must have a parent")
    if parent_id is not None:
        parent = await db.get(QualityGoal, parent_id)
        if parent is None:
            raise ValueError("parent goal not found")
        if parent.level != level - 1:
            raise ValueError(f"parent must be level {level - 1}, got level {parent.level}")


async def list_quality_goals(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    level: int | None = None,
    product_line_code: str | None = None,
    status: str | None = None,
    period: str | None = None,
) -> tuple[list[QualityGoal], int]:
    query = select(QualityGoal)
    count_query = select(func.count()).select_from(QualityGoal)

    if level is not None:
        query = query.where(QualityGoal.level == level)
        count_query = count_query.where(QualityGoal.level == level)
    if product_line_code:
        query = query.where(QualityGoal.product_line_code == product_line_code)
        count_query = count_query.where(QualityGoal.product_line_code == product_line_code)
    if status:
        query = query.where(QualityGoal.status == status)
        count_query = count_query.where(QualityGoal.status == status)
    if period:
        query = query.where(QualityGoal.period == period)
        count_query = count_query.where(QualityGoal.period == period)

    query = query.order_by(QualityGoal.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return list(items), total


async def get_quality_goal(db: AsyncSession, goal_id: uuid.UUID) -> QualityGoal | None:
    return await db.get(QualityGoal, goal_id)


async def create_quality_goal(
    db: AsyncSession,
    parent_id: uuid.UUID | None,
    level: int,
    product_line: str | None,
    name: str,
    target_value: str,
    unit: str,
    period: str,
    owner_id: uuid.UUID,
    description: str | None,
    user_id: uuid.UUID,
) -> QualityGoal:
    await _validate_hierarchy(db, parent_id, level)
    doc_no = await _generate_doc_no(db)

    goal = QualityGoal(
        doc_no=doc_no,
        parent_id=parent_id,
        level=level,
        product_line_code=product_line_code,
        name=name,
        target_value=target_value,
        unit=unit,
        period=period,
        owner_id=owner_id,
        description=description,
        status="draft",
    )
    db.add(goal)

    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="CREATE",
        changed_fields={
            "doc_no": doc_no,
            "name": name,
            "level": level,
            "target_value": target_value,
            "status": "draft",
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create quality goal: {e}")
    await db.refresh(goal)
    return goal


async def update_quality_goal(
    db: AsyncSession,
    goal: QualityGoal,
    name: str | None,
    target_value: str | None,
    actual_value: str | None,
    unit: str | None,
    period: str | None,
    owner_id: uuid.UUID | None,
    description: str | None,
    user_id: uuid.UUID,
) -> QualityGoal:
    if goal.status != "draft":
        raise ValueError("only draft goals can be edited")
    if actual_value is not None and goal.status != "active":
        raise ValueError("actual_value can only be updated on active goals")

    changed = {}
    if name is not None and name != goal.name:
        changed["name"] = {"before": goal.name, "after": name}
        goal.name = name
    if target_value is not None and target_value != goal.target_value:
        changed["target_value"] = {"before": goal.target_value, "after": target_value}
        goal.target_value = target_value
    if actual_value is not None and actual_value != goal.actual_value:
        changed["actual_value"] = {"before": goal.actual_value, "after": actual_value}
        goal.actual_value = actual_value
    if unit is not None and unit != goal.unit:
        changed["unit"] = {"before": goal.unit, "after": unit}
        goal.unit = unit
    if period is not None and period != goal.period:
        changed["period"] = {"before": goal.period, "after": period}
        goal.period = period
    if owner_id is not None and owner_id != goal.owner_id:
        changed["owner_id"] = {"before": str(goal.owner_id), "after": str(owner_id)}
        goal.owner_id = owner_id
    if description is not None and description != goal.description:
        changed["description"] = {"before": goal.description, "after": description}
        goal.description = description

    if not changed:
        return goal

    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update quality goal: {e}")
    await db.refresh(goal)
    return goal


async def delete_quality_goal(db: AsyncSession, goal: QualityGoal, user_id: uuid.UUID) -> None:
    if goal.status != "draft":
        raise ValueError("only draft goals can be deleted")

    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="DELETE",
        changed_fields={
            "doc_no": goal.doc_no,
            "name": goal.name,
            "status": goal.status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)
    try:
        await db.delete(goal)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError("cannot delete goal with child goals")


async def submit_for_approval(db: AsyncSession, goal: QualityGoal, user_id: uuid.UUID) -> QualityGoal:
    if goal.status != "draft":
        raise ValueError("only draft goals can be submitted for approval")

    goal.status = "pending"
    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "draft", "after": "pending"}},
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def withdraw_submission(db: AsyncSession, goal: QualityGoal, user_id: uuid.UUID) -> QualityGoal:
    if goal.status != "pending":
        raise ValueError("only pending goals can be withdrawn")

    goal.status = "draft"
    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "pending", "after": "draft"}},
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def approve_goal(db: AsyncSession, goal: QualityGoal, approver_id: uuid.UUID) -> QualityGoal:
    if goal.status != "pending":
        raise ValueError("only pending goals can be approved")

    now = datetime.now(timezone.utc)
    goal.status = "active"
    goal.approved_by = approver_id
    goal.approved_at = now
    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="TRANSITION",
        changed_fields={
            "status": {"before": "pending", "after": "active"},
            "approved_by": str(approver_id),
            "approved_at": now.isoformat(),
        },
        operated_by=approver_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def reject_goal(db: AsyncSession, goal: QualityGoal, reject_reason: str, approver_id: uuid.UUID) -> QualityGoal:
    if goal.status != "pending":
        raise ValueError("only pending goals can be rejected")
    if not reject_reason or not reject_reason.strip():
        raise ValueError("reject reason is required")

    goal.status = "draft"
    goal.reject_reason = reject_reason
    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="TRANSITION",
        changed_fields={
            "status": {"before": "pending", "after": "draft"},
            "reject_reason": reject_reason,
        },
        operated_by=approver_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def archive_goal(db: AsyncSession, goal: QualityGoal, user_id: uuid.UUID) -> QualityGoal:
    if goal.status != "active":
        raise ValueError("only active goals can be archived")

    goal.status = "archived"
    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "active", "after": "archived"}},
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def update_actual_value(
    db: AsyncSession, goal: QualityGoal, actual_value: str, user_id: uuid.UUID
) -> QualityGoal:
    if goal.status != "active":
        raise ValueError("only active goals can have actual value updated")

    changed = {
        "actual_value": {"before": goal.actual_value, "after": actual_value}
    }
    goal.actual_value = actual_value

    audit_log = AuditLog(
        table_name="quality_goals",
        record_id=goal.goal_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(goal)
    return goal


async def get_quality_goal_stats(db: AsyncSession) -> dict:
    total_result = await db.execute(select(func.count()).select_from(QualityGoal))
    total = total_result.scalar() or 0

    active_result = await db.execute(
        select(func.count()).select_from(QualityGoal).where(QualityGoal.status == "active")
    )
    active = active_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count()).select_from(QualityGoal).where(QualityGoal.status == "pending")
    )
    pending = pending_result.scalar() or 0

    active_goals_result = await db.execute(
        select(QualityGoal).where(QualityGoal.status == "active")
    )
    active_goals = active_goals_result.scalars().all()

    achieved = 0
    for g in active_goals:
        if not g.actual_value:
            continue
        tv = g.target_value.strip()
        av = g.actual_value.strip()
        try:
            if tv.startswith("≤") or tv.startswith("<="):
                threshold = float(tv.lstrip("≤<=").replace("%", ""))
                actual = float(av.replace("%", ""))
                if actual <= threshold:
                    achieved += 1
            elif tv.startswith("≥") or tv.startswith(">="):
                threshold = float(tv.lstrip("≥>=").replace("%", ""))
                actual = float(av.replace("%", ""))
                if actual >= threshold:
                    achieved += 1
            else:
                threshold = float(tv.replace("%", ""))
                actual = float(av.replace("%", ""))
                if actual <= threshold:
                    achieved += 1
        except (ValueError, TypeError):
            continue

    return {"total": total, "active": active, "pending": pending, "achieved": achieved}
