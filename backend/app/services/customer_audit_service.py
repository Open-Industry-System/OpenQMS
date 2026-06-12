import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.audit import AuditLog
from app.models.audit_finding import AuditFinding
from app.models.audit_plan import AuditPlan
from app.models.audit_program import AuditProgram
from app.models.capa import CAPAEightD

VALID_CUSTOMER_TYPES = {"OEM", "Tier 1", "Tier 2", "其他"}
VALID_AUDIT_MODES = {"on_site", "remote"}


async def _get_or_create_customer_program(
    db: AsyncSession, year: int, user_id: uuid.UUID
) -> AuditProgram:
    """Return the default customer audit program for a year, creating if needed.
    Uses deterministic program_no so concurrent requests collide on uniqueness."""
    result = await db.execute(
        select(AuditProgram).where(
            AuditProgram.audit_type == "customer",
            AuditProgram.program_year == year,
        )
    )
    program = result.scalar_one_or_none()
    if program:
        return program

    program = AuditProgram(
        program_no=f"AP-{year}-CUS-001",
        program_year=year,
        audit_type="customer",
        scope="客户审核方案",
        criteria="客户审核标准",
        status="active",
        created_by=user_id,
    )
    db.add(program)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(AuditProgram).where(
                AuditProgram.audit_type == "customer",
                AuditProgram.program_year == year,
            )
        )
        program = result.scalar_one()
    return program


async def _generate_customer_audit_no(db: AsyncSession, year: int) -> str:
    prefix = f"CA-{year}"
    result = await db.execute(
        select(func.count()).where(AuditPlan.plan_no.like(f"{prefix}-%"))
    )
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


async def create_customer_audit(
    db: AsyncSession,
    *,
    audit_scope: str,
    audit_criteria: str,
    planned_date: date,
    customer_name: str,
    customer_type: str,
    audit_mode: str | None,
    lead_auditor: uuid.UUID | None,
    team_members: list | None,
    checklist: list | None,
    product_line_code: str | None,
    user_id: uuid.UUID,
) -> AuditPlan:
    if not customer_name or not customer_name.strip():
        raise ValueError("customer_name is required")
    if customer_type not in VALID_CUSTOMER_TYPES:
        raise ValueError(f"invalid customer_type: {customer_type}")
    if audit_mode and audit_mode not in VALID_AUDIT_MODES:
        raise ValueError(f"invalid audit_mode: {audit_mode}")

    program = await _get_or_create_customer_program(db, planned_date.year, user_id)
    plan_no = await _generate_customer_audit_no(db, planned_date.year)

    plan = AuditPlan(
        plan_no=plan_no,
        program_id=program.program_id,
        audit_scope=audit_scope,
        audit_criteria=audit_criteria,
        planned_date=planned_date,
        lead_auditor=lead_auditor,
        team_members=team_members or [],
        checklist=checklist or [],
        status="planned",
        audit_category="customer",
        customer_name=customer_name,
        customer_type=customer_type,
        audit_mode=audit_mode,
        created_by=user_id,
        product_line_code=product_line_code,
    )
    db.add(plan)
    await db.flush()  # populate plan.audit_id

    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="CREATE",
        changed_fields={"audit_category": "customer", "customer_name": customer_name},
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(plan)
    return plan


async def list_customer_audits(
    db: AsyncSession,
    page: int,
    page_size: int,
    customer_type: str | None = None,
    audit_mode: str | None = None,
    customer_name: str | None = None,
    status: str | None = None,
    product_line_code: str | None = None,
) -> tuple[list[AuditPlan], int]:
    query = select(AuditPlan).where(AuditPlan.audit_category == "customer")
    count_query = select(func.count()).select_from(AuditPlan).where(AuditPlan.audit_category == "customer")

    if customer_type:
        query = query.where(AuditPlan.customer_type == customer_type)
        count_query = count_query.where(AuditPlan.customer_type == customer_type)
    if audit_mode:
        query = query.where(AuditPlan.audit_mode == audit_mode)
        count_query = count_query.where(AuditPlan.audit_mode == audit_mode)
    if customer_name:
        query = query.where(AuditPlan.customer_name.ilike(f"%{customer_name}%"))
        count_query = count_query.where(AuditPlan.customer_name.ilike(f"%{customer_name}%"))
    if status:
        query = query.where(AuditPlan.status == status)
        count_query = count_query.where(AuditPlan.status == status)
    if product_line_code:
        query = query.where(AuditPlan.product_line_code == product_line_code)
        count_query = count_query.where(AuditPlan.product_line_code == product_line_code)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(AuditPlan.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_customer_audit(
    db: AsyncSession,
    plan: AuditPlan,
    *,
    user_id: uuid.UUID,
    customer_name: str | None = None,
    customer_type: str | None = None,
    audit_mode: str | None = None,
    audit_scope: str | None = None,
    audit_criteria: str | None = None,
    planned_date: date | None = None,
    actual_date: date | None = None,
    lead_auditor: uuid.UUID | None = None,
    team_members: list | None = None,
    checklist: list | None = None,
    product_line_code: str | None = None,
) -> AuditPlan:
    changed: dict = {}
    if customer_name is not None and customer_name != plan.customer_name:
        changed["customer_name"] = {"before": plan.customer_name, "after": customer_name}
        plan.customer_name = customer_name
    if customer_type is not None and customer_type != plan.customer_type:
        if customer_type not in VALID_CUSTOMER_TYPES:
            raise ValueError(f"invalid customer_type: {customer_type}")
        changed["customer_type"] = {"before": plan.customer_type, "after": customer_type}
        plan.customer_type = customer_type
    if audit_mode is not None and audit_mode != plan.audit_mode:
        if audit_mode not in VALID_AUDIT_MODES:
            raise ValueError(f"invalid audit_mode: {audit_mode}")
        changed["audit_mode"] = {"before": plan.audit_mode, "after": audit_mode}
        plan.audit_mode = audit_mode
    if audit_scope is not None and audit_scope != plan.audit_scope:
        changed["audit_scope"] = {"before": plan.audit_scope, "after": audit_scope}
        plan.audit_scope = audit_scope
    if audit_criteria is not None and audit_criteria != plan.audit_criteria:
        changed["audit_criteria"] = {"before": plan.audit_criteria, "after": audit_criteria}
        plan.audit_criteria = audit_criteria
    if planned_date is not None and planned_date != plan.planned_date:
        changed["planned_date"] = {"before": plan.planned_date.isoformat() if plan.planned_date else None, "after": planned_date.isoformat()}
        plan.planned_date = planned_date
    if actual_date is not None and actual_date != plan.actual_date:
        changed["actual_date"] = {"before": plan.actual_date.isoformat() if plan.actual_date else None, "after": actual_date.isoformat()}
        plan.actual_date = actual_date
    if lead_auditor is not None and lead_auditor != plan.lead_auditor:
        changed["lead_auditor"] = {"before": str(plan.lead_auditor), "after": str(lead_auditor)}
        plan.lead_auditor = lead_auditor
    if team_members is not None and team_members != plan.team_members:
        changed["team_members"] = {"before": plan.team_members, "after": team_members}
        plan.team_members = team_members
    if checklist is not None and checklist != plan.checklist:
        changed["checklist"] = {"before": plan.checklist, "after": checklist}
        plan.checklist = checklist
    if product_line_code is not None and product_line_code != plan.product_line_code:
        changed["product_line_code"] = {"before": plan.product_line_code, "after": product_line_code}
        plan.product_line_code = product_line_code

    if changed:
        audit_log = AuditLog(
            table_name="audit_plans",
            record_id=plan.audit_id,
            action="UPDATE",
            changed_fields=changed,
            operated_by=user_id,
        )
        db.add(audit_log)

    await db.commit()
    await db.refresh(plan)
    return plan


async def complete_customer_audit(db: AsyncSession, plan: AuditPlan, user_id: uuid.UUID) -> AuditPlan:
    if plan.status != "in_progress":
        raise ValueError("only in-progress audits can be completed")

    result = await db.execute(
        select(AuditFinding.finding_id, AuditFinding.status, AuditFinding.customer_confirmed)
        .where(AuditFinding.audit_id == plan.audit_id, AuditFinding.status != "closed")
    )
    unclosed = result.all()
    if unclosed:
        raise ValueError(f"cannot complete: {len(unclosed)} finding(s) not closed")

    result = await db.execute(
        select(AuditFinding.finding_id)
        .where(
            AuditFinding.audit_id == plan.audit_id,
            AuditFinding.status == "closed",
            AuditFinding.customer_confirmed == False,
        )
    )
    unconfirmed = result.all()
    if unconfirmed:
        raise ValueError(f"cannot complete: {len(unconfirmed)} finding(s) not customer-confirmed")

    plan.status = "completed"
    plan.actual_date = datetime.now(timezone.utc).date()

    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "in_progress", "after": "completed"}},
        operated_by=user_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(plan)
    return plan


async def transition_finding(
    db: AsyncSession,
    finding: AuditFinding,
    *,
    action: str,
    user_id: uuid.UUID,
    customer_confirmed: bool | None = None,
    customer_confirmation_date: date | None = None,
    customer_confirmation_attachments: list | None = None,
) -> AuditFinding:
    old_status = finding.status

    # Stage new values locally; do not write to ORM until all validation passes
    new_customer_confirmed = customer_confirmed if customer_confirmed is not None else finding.customer_confirmed
    new_customer_confirmation_date = customer_confirmation_date if customer_confirmation_date is not None else finding.customer_confirmation_date
    new_customer_confirmation_attachments = (
        customer_confirmation_attachments if customer_confirmation_attachments is not None else finding.customer_confirmation_attachments
    )
    new_status = finding.status

    if action == "start_progress":
        if finding.status != "open":
            raise ValueError("only open findings can start progress")
        new_status = "in_progress"

    elif action == "close":
        if finding.status not in ("open", "in_progress"):
            raise ValueError("only open or in_progress findings can be closed")
        if not finding.root_cause:
            raise ValueError("root_cause is required before closing")
        if not finding.corrective_action:
            raise ValueError("corrective_action is required before closing")

        if finding.capa_ref_id:
            capa_result = await db.execute(
                select(CAPAEightD.status).where(CAPAEightD.report_id == finding.capa_ref_id)
            )
            capa_status = capa_result.scalar_one_or_none()
            if capa_status != "D8_CLOSURE":
                raise ValueError(f"linked CAPA status is '{capa_status}', must be 'D8_CLOSURE'")

        plan_result = await db.execute(
            select(AuditPlan.audit_category).where(AuditPlan.audit_id == finding.audit_id)
        )
        audit_category = plan_result.scalar_one_or_none()
        if audit_category == "customer" and not new_customer_confirmed:
            raise ValueError("customer confirmation is required before closing customer audit finding")

        new_status = "closed"

    else:
        raise ValueError(f"invalid action: {action}")

    # All validations passed — apply staged values
    finding.customer_confirmed = new_customer_confirmed
    finding.customer_confirmation_date = new_customer_confirmation_date
    finding.customer_confirmation_attachments = new_customer_confirmation_attachments
    finding.status = new_status
    if new_status == "closed":
        finding.closed_at = datetime.now(timezone.utc)

    audit_log = AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="TRANSITION",
        changed_fields={
            "status": {"before": old_status, "after": finding.status},
            "action": action,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(finding)
    return finding


async def customer_confirm_finding(
    db: AsyncSession,
    finding: AuditFinding,
    *,
    confirmation_date: date,
    attachments: list,
    user_id: uuid.UUID,
) -> AuditFinding:
    """Mark a finding as customer-confirmed without changing its workflow status."""
    plan_result = await db.execute(
        select(AuditPlan.audit_category).where(AuditPlan.audit_id == finding.audit_id)
    )
    audit_category = plan_result.scalar_one_or_none()
    if audit_category != "customer":
        raise ValueError("finding does not belong to a customer audit")

    finding.customer_confirmed = True
    finding.customer_confirmation_date = confirmation_date
    finding.customer_confirmation_attachments = attachments

    audit_log = AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="CUSTOMER_CONFIRM",
        changed_fields={
            "customer_confirmed": {"before": False, "after": True},
            "customer_confirmation_date": confirmation_date.isoformat(),
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(finding)
    return finding


async def get_customer_audit_stats(
    db: AsyncSession,
    product_line_code: str | None = None,
    factory_id: uuid.UUID | None = None,
) -> dict:
    plan_conditions = [AuditPlan.audit_category == "customer"]
    finding_join_conditions = [AuditPlan.audit_category == "customer"]
    if product_line_code:
        plan_conditions.append(AuditPlan.product_line_code == product_line_code)
        finding_join_conditions.append(AuditPlan.product_line_code == product_line_code)
    if factory_id is not None:
        plan_conditions.append(AuditPlan.factory_id == factory_id)
        finding_join_conditions.append(AuditPlan.factory_id == factory_id)

    total_result = await db.execute(
        select(func.count()).select_from(AuditPlan).where(*plan_conditions)
    )
    total = total_result.scalar() or 0

    planned_result = await db.execute(
        select(func.count()).select_from(AuditPlan).where(
            *plan_conditions, AuditPlan.status == "planned"
        )
    )
    planned = planned_result.scalar() or 0

    in_progress_result = await db.execute(
        select(func.count()).select_from(AuditPlan).where(
            *plan_conditions, AuditPlan.status == "in_progress"
        )
    )
    in_progress = in_progress_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count()).select_from(AuditPlan).where(
            *plan_conditions, AuditPlan.status == "completed"
        )
    )
    completed = completed_result.scalar() or 0

    open_findings_result = await db.execute(
        select(func.count())
        .select_from(AuditFinding)
        .join(AuditPlan, AuditFinding.audit_id == AuditPlan.audit_id)
        .where(
            *finding_join_conditions,
            AuditFinding.status.in_(["open", "in_progress"]),
        )
    )
    open_findings = open_findings_result.scalar() or 0

    major_nc_result = await db.execute(
        select(func.count())
        .select_from(AuditFinding)
        .join(AuditPlan, AuditFinding.audit_id == AuditPlan.audit_id)
        .where(
            *finding_join_conditions,
            AuditFinding.finding_type == "major_nc",
            AuditFinding.status.in_(["open", "in_progress"]),
        )
    )
    major_nc = major_nc_result.scalar() or 0

    confirmed_result = await db.execute(
        select(func.count())
        .select_from(AuditFinding)
        .join(AuditPlan, AuditFinding.audit_id == AuditPlan.audit_id)
        .where(
            *finding_join_conditions,
            AuditFinding.customer_confirmed == True,
        )
    )
    confirmed = confirmed_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count())
        .select_from(AuditFinding)
        .join(AuditPlan, AuditFinding.audit_id == AuditPlan.audit_id)
        .where(
            *finding_join_conditions,
            AuditFinding.customer_confirmed == False,
            AuditFinding.status.in_(["open", "in_progress"]),
        )
    )
    pending = pending_result.scalar() or 0

    return {
        "total_customer_audits": total,
        "planned": planned,
        "in_progress": in_progress,
        "completed": completed,
        "open_findings": open_findings,
        "major_nc_count": major_nc,
        "customer_confirmed_count": confirmed,
        "pending_confirmation_count": pending,
    }
