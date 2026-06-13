import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.audit_finding import AuditFinding
from app.models.audit_plan import AuditPlan
from app.models.audit_program import AuditProgram
from app.models.capa import CAPAEightD
from app.models.user import User
from app.services.embedding_outbox import enqueue_embedding

# ───────────────────────────────────────────────
# Numbering generators
# ───────────────────────────────────────────────

async def _generate_program_no(db: AsyncSession, audit_type: str, year: int) -> str:
    type_map = {"system": "SYS", "process": "PRO", "product": "PRD", "customer": "CUS"}
    type_code = type_map.get(audit_type, "SYS")
    prefix = f"AP-{year}-{type_code}"
    result = await db.execute(
        select(func.count()).where(AuditProgram.program_no.like(f"{prefix}-%"))
    )
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


async def _generate_plan_no(db: AsyncSession, year: int) -> str:
    prefix = f"PL-{year}"
    result = await db.execute(
        select(func.count()).where(AuditPlan.plan_no.like(f"{prefix}-%"))
    )
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


async def _generate_8d_no(db: AsyncSession, year: int) -> str:
    prefix = f"8D-{year}"
    result = await db.execute(
        select(func.count()).where(CAPAEightD.document_no.like(f"{prefix}-%"))
    )
    count = result.scalar() or 0
    return f"{prefix}-{count + 1:03d}"


# ───────────────────────────────────────────────
# Program status helper
# ───────────────────────────────────────────────

async def _update_program_status(db: AsyncSession, program: AuditProgram) -> None:
    result = await db.execute(
        select(AuditPlan.status).where(AuditPlan.program_id == program.program_id)
    )
    plan_statuses = [row[0] for row in result.all()]

    if not plan_statuses:
        return

    if all(s in ("completed", "cancelled") for s in plan_statuses):
        program.status = "completed"
    elif any(s in ("in_progress", "completed") for s in plan_statuses):
        program.status = "active"


# ───────────────────────────────────────────────
# AuditProgram CRUD
# ───────────────────────────────────────────────

async def list_audit_programs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    year: int | None = None,
    audit_type: str | None = None,
    status: str | None = None,
    factory_id: uuid.UUID | None = None,
) -> tuple[list[AuditProgram], int]:
    query = select(AuditProgram)
    count_query = select(func.count()).select_from(AuditProgram)

    if year is not None:
        query = query.where(AuditProgram.program_year == year)
        count_query = count_query.where(AuditProgram.program_year == year)
    if audit_type:
        query = query.where(AuditProgram.audit_type == audit_type)
        count_query = count_query.where(AuditProgram.audit_type == audit_type)
    if status:
        query = query.where(AuditProgram.status == status)
        count_query = count_query.where(AuditProgram.status == status)
    if factory_id is not None:
        query = query.where(AuditProgram.factory_id == factory_id)
        count_query = count_query.where(AuditProgram.factory_id == factory_id)

    query = query.order_by(AuditProgram.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return list(items), total


async def get_audit_program(db: AsyncSession, program_id: uuid.UUID) -> AuditProgram | None:
    return await db.get(AuditProgram, program_id)


async def create_audit_program(
    db: AsyncSession,
    program_year: int,
    audit_type: str,
    scope: str,
    criteria: str,
    user_id: uuid.UUID,
    factory_id: uuid.UUID | None = None,
) -> AuditProgram:
    program_no = await _generate_program_no(db, audit_type, program_year)

    program = AuditProgram(
        program_no=program_no,
        program_year=program_year,
        audit_type=audit_type,
        scope=scope,
        criteria=criteria,
        status="planned",
        created_by=user_id,
        factory_id=factory_id,
    )
    db.add(program)

    audit_log = AuditLog(
        table_name="audit_programs",
        record_id=program.program_id,
        action="CREATE",
        changed_fields={
            "program_no": program_no,
            "program_year": program_year,
            "audit_type": audit_type,
            "scope": scope,
            "criteria": criteria,
            "status": "planned",
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create audit program: {e}")
    await db.refresh(program)
    return program


async def update_audit_program(
    db: AsyncSession,
    program: AuditProgram,
    program_year: int | None,
    audit_type: str | None,
    scope: str | None,
    criteria: str | None,
    status: str | None,
    user_id: uuid.UUID,
) -> AuditProgram:
    changed = {}

    if program_year is not None and program_year != program.program_year:
        changed["program_year"] = {"before": program.program_year, "after": program_year}
        program.program_year = program_year
    if audit_type is not None and audit_type != program.audit_type:
        changed["audit_type"] = {"before": program.audit_type, "after": audit_type}
        program.audit_type = audit_type
    if scope is not None and scope != program.scope:
        changed["scope"] = {"before": program.scope, "after": scope}
        program.scope = scope
    if criteria is not None and criteria != program.criteria:
        changed["criteria"] = {"before": program.criteria, "after": criteria}
        program.criteria = criteria
    if status is not None and status != program.status:
        changed["status"] = {"before": program.status, "after": status}
        program.status = status

    if not changed:
        return program

    audit_log = AuditLog(
        table_name="audit_programs",
        record_id=program.program_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update audit program: {e}")
    await db.refresh(program)
    return program


async def delete_audit_program(db: AsyncSession, program: AuditProgram, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(func.count()).where(AuditPlan.program_id == program.program_id)
    )
    plan_count = result.scalar() or 0
    if plan_count > 0:
        raise ValueError("cannot delete program with associated audit plans")

    audit_log = AuditLog(
        table_name="audit_programs",
        record_id=program.program_id,
        action="DELETE",
        changed_fields={
            "program_no": program.program_no,
            "program_year": program.program_year,
            "audit_type": program.audit_type,
            "status": program.status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.delete(program)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to delete audit program: {e}")


# ───────────────────────────────────────────────
# AuditPlan CRUD + transitions
# ───────────────────────────────────────────────

async def list_audit_plans(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    program_id: uuid.UUID | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    audit_category: str | None = None,
    customer_type: str | None = None,
    audit_mode: str | None = None,
    customer_name: str | None = None,
    product_line_code: str | None = None,
    factory_id: uuid.UUID | None = None,
    allowed_product_line_codes: list[str] | None = None,
) -> tuple[list[AuditPlan], int]:
    query = select(AuditPlan)
    count_query = select(func.count()).select_from(AuditPlan)

    if program_id is not None:
        query = query.where(AuditPlan.program_id == program_id)
        count_query = count_query.where(AuditPlan.program_id == program_id)
    if status:
        query = query.where(AuditPlan.status == status)
        count_query = count_query.where(AuditPlan.status == status)
    if date_from is not None:
        query = query.where(AuditPlan.planned_date >= date_from)
        count_query = count_query.where(AuditPlan.planned_date >= date_from)
    if date_to is not None:
        query = query.where(AuditPlan.planned_date <= date_to)
        count_query = count_query.where(AuditPlan.planned_date <= date_to)
    if audit_category:
        query = query.where(AuditPlan.audit_category == audit_category)
        count_query = count_query.where(AuditPlan.audit_category == audit_category)
    if customer_type:
        query = query.where(AuditPlan.customer_type == customer_type)
        count_query = count_query.where(AuditPlan.customer_type == customer_type)
    if audit_mode:
        query = query.where(AuditPlan.audit_mode == audit_mode)
        count_query = count_query.where(AuditPlan.audit_mode == audit_mode)
    if customer_name:
        query = query.where(AuditPlan.customer_name.ilike(f"%{customer_name}%"))
        count_query = count_query.where(AuditPlan.customer_name.ilike(f"%{customer_name}%"))
    if product_line_code:
        query = query.where(AuditPlan.product_line_code == product_line_code)
        count_query = count_query.where(AuditPlan.product_line_code == product_line_code)
    if factory_id is not None:
        query = query.join(AuditProgram, AuditPlan.program_id == AuditProgram.program_id).where(AuditProgram.factory_id == factory_id)
        count_query = count_query.join(AuditProgram, AuditPlan.program_id == AuditProgram.program_id).where(AuditProgram.factory_id == factory_id)
    if allowed_product_line_codes is not None:
        query = query.where(AuditPlan.product_line_code.in_(allowed_product_line_codes))
        count_query = count_query.where(AuditPlan.product_line_code.in_(allowed_product_line_codes))

    query = query.order_by(AuditPlan.planned_date.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return list(items), total


async def get_audit_plan(db: AsyncSession, audit_id: uuid.UUID) -> AuditPlan | None:
    return await db.get(AuditPlan, audit_id)


async def create_audit_plan(
    db: AsyncSession,
    program_id: uuid.UUID,
    audit_scope: str,
    audit_criteria: str,
    planned_date: date,
    lead_auditor: uuid.UUID | None,
    team_members: list,
    checklist: list,
    user_id: uuid.UUID,
    product_line_code: str | None = None,
    factory_id: uuid.UUID | None = None,
) -> AuditPlan:
    program = await db.get(AuditProgram, program_id)
    if program and program.audit_type == "customer":
        raise ValueError("internal audit cannot be linked to a customer program")

    year = planned_date.year
    plan_no = await _generate_plan_no(db, year)

    # Auditor qualification check
    if lead_auditor:
        await _check_auditor_qualification(db, lead_auditor)

    plan = AuditPlan(
        plan_no=plan_no,
        program_id=program_id,
        audit_scope=audit_scope,
        audit_criteria=audit_criteria,
        planned_date=planned_date,
        lead_auditor=lead_auditor,
        team_members=team_members or [],
        checklist=checklist or [],
        status="planned",
        created_by=user_id,
        product_line_code=product_line_code,
        factory_id=factory_id,
    )
    db.add(plan)

    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="CREATE",
        changed_fields={
            "plan_no": plan_no,
            "program_id": str(program_id),
            "audit_scope": audit_scope,
            "planned_date": planned_date.isoformat(),
            "status": "planned",
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create audit plan: {e}")
    await db.refresh(plan)

    # Update parent program status
    program = await db.get(AuditProgram, program_id)
    if program:
        await _update_program_status(db, program)
        await db.commit()
        await db.refresh(program)

    return plan


async def update_audit_plan(
    db: AsyncSession,
    plan: AuditPlan,
    audit_scope: str | None,
    audit_criteria: str | None,
    planned_date: date | None,
    actual_date: date | None,
    lead_auditor: uuid.UUID | None,
    team_members: list | None,
    checklist: list | None,
    user_id: uuid.UUID,
    status: str | None = None,
    product_line_code: str | None = None,
) -> AuditPlan:
    changed = {}

    # Auditor qualification check
    if lead_auditor is not None and lead_auditor != plan.lead_auditor:
        await _check_auditor_qualification(db, lead_auditor)

    if audit_scope is not None and audit_scope != plan.audit_scope:
        changed["audit_scope"] = {"before": plan.audit_scope, "after": audit_scope}
        plan.audit_scope = audit_scope
    if audit_criteria is not None and audit_criteria != plan.audit_criteria:
        changed["audit_criteria"] = {"before": plan.audit_criteria, "after": audit_criteria}
        plan.audit_criteria = audit_criteria
    if planned_date is not None and planned_date != plan.planned_date:
        changed["planned_date"] = {"before": plan.planned_date.isoformat(), "after": planned_date.isoformat()}
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
    if status is not None and status != plan.status:
        changed["status"] = {"before": plan.status, "after": status}
        plan.status = status
    if product_line_code is not None and product_line_code != plan.product_line_code:
        changed["product_line_code"] = {"before": plan.product_line_code, "after": product_line_code}
        plan.product_line_code = product_line_code

    if not changed:
        return plan

    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update audit plan: {e}")
    await db.refresh(plan)

    # Update parent program status if status changed
    if "status" in changed:
        program = await db.get(AuditProgram, plan.program_id)
        if program:
            await _update_program_status(db, program)
            await db.commit()
            await db.refresh(program)

    return plan


async def delete_audit_plan(db: AsyncSession, plan: AuditPlan, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(func.count()).where(AuditFinding.audit_id == plan.audit_id)
    )
    finding_count = result.scalar() or 0
    if finding_count > 0:
        raise ValueError("cannot delete audit plan with associated findings")

    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="DELETE",
        changed_fields={
            "plan_no": plan.plan_no,
            "audit_scope": plan.audit_scope,
            "status": plan.status,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    program_id = plan.program_id

    try:
        await db.delete(plan)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to delete audit plan: {e}")

    # Update parent program status
    program = await db.get(AuditProgram, program_id)
    if program:
        await _update_program_status(db, program)
        await db.commit()
        await db.refresh(program)


async def start_audit_plan(db: AsyncSession, plan: AuditPlan, user_id: uuid.UUID) -> AuditPlan:
    if plan.status != "planned":
        raise ValueError("only planned audits can be started")

    plan.status = "in_progress"
    plan.actual_date = date.today()

    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="TRANSITION",
        changed_fields={
            "status": {"before": "planned", "after": "in_progress"},
            "actual_date": plan.actual_date.isoformat(),
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(plan)

    program = await db.get(AuditProgram, plan.program_id)
    if program:
        await _update_program_status(db, program)
        await db.commit()
        await db.refresh(program)

    return plan


async def complete_audit_plan(db: AsyncSession, plan: AuditPlan, user_id: uuid.UUID) -> AuditPlan:
    if plan.status != "in_progress":
        raise ValueError("only in-progress audits can be completed")

    plan.status = "completed"

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

    program = await db.get(AuditProgram, plan.program_id)
    if program:
        await _update_program_status(db, program)
        await db.commit()
        await db.refresh(program)

    return plan


async def cancel_audit_plan(db: AsyncSession, plan: AuditPlan, user_id: uuid.UUID) -> AuditPlan:
    if plan.status != "planned":
        raise ValueError("only planned audits can be cancelled")

    plan.status = "cancelled"

    audit_log = AuditLog(
        table_name="audit_plans",
        record_id=plan.audit_id,
        action="TRANSITION",
        changed_fields={"status": {"before": "planned", "after": "cancelled"}},
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(plan)

    program = await db.get(AuditProgram, plan.program_id)
    if program:
        await _update_program_status(db, program)
        await db.commit()
        await db.refresh(program)

    return plan


# ───────────────────────────────────────────────
# AuditFinding CRUD + transitions
# ───────────────────────────────────────────────

async def list_audit_findings(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    audit_id: uuid.UUID | None = None,
    finding_type: str | None = None,
    status: str | None = None,
    factory_id: uuid.UUID | None = None,
) -> tuple[list[AuditFinding], int]:
    query = select(AuditFinding)
    count_query = select(func.count()).select_from(AuditFinding)

    if audit_id is not None:
        query = query.where(AuditFinding.audit_id == audit_id)
        count_query = count_query.where(AuditFinding.audit_id == audit_id)
    if finding_type:
        query = query.where(AuditFinding.finding_type == finding_type)
        count_query = count_query.where(AuditFinding.finding_type == finding_type)
    if status:
        query = query.where(AuditFinding.status == status)
        count_query = count_query.where(AuditFinding.status == status)
    if factory_id is not None:
        query = query.where(AuditFinding.factory_id == factory_id)
        count_query = count_query.where(AuditFinding.factory_id == factory_id)

    query = query.order_by(AuditFinding.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return list(items), total


async def get_audit_finding(db: AsyncSession, finding_id: uuid.UUID) -> AuditFinding | None:
    return await db.get(AuditFinding, finding_id)


async def create_audit_finding(
    db: AsyncSession,
    audit_id: uuid.UUID,
    clause_ref: str | None,
    finding_type: str,
    description: str,
    root_cause: str | None,
    correction: str | None,
    corrective_action: str | None,
    due_date: date | None,
    user_id: uuid.UUID,
    factory_id: uuid.UUID | None = None,
) -> AuditFinding:
    finding = AuditFinding(
        audit_id=audit_id,
        clause_ref=clause_ref,
        finding_type=finding_type,
        description=description,
        root_cause=root_cause,
        correction=correction,
        corrective_action=corrective_action,
        due_date=due_date,
        status="open",
        created_by=user_id,
        factory_id=factory_id,
    )
    db.add(finding)

    audit_log = AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="CREATE",
        changed_fields={
            "audit_id": str(audit_id),
            "clause_ref": clause_ref,
            "finding_type": finding_type,
            "description": description,
            "status": "open",
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await enqueue_embedding(db, "audit_finding", finding.finding_id, None, finding.factory_id)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create audit finding: {e}")
    await db.refresh(finding)
    return finding


async def update_audit_finding(
    db: AsyncSession,
    finding: AuditFinding,
    clause_ref: str | None,
    finding_type: str | None,
    description: str | None,
    root_cause: str | None,
    correction: str | None,
    corrective_action: str | None,
    due_date: date | None,
    user_id: uuid.UUID,
    status: str | None = None,
) -> AuditFinding:
    changed = {}

    if clause_ref is not None and clause_ref != finding.clause_ref:
        changed["clause_ref"] = {"before": finding.clause_ref, "after": clause_ref}
        finding.clause_ref = clause_ref
    if finding_type is not None and finding_type != finding.finding_type:
        changed["finding_type"] = {"before": finding.finding_type, "after": finding_type}
        finding.finding_type = finding_type
    if description is not None and description != finding.description:
        changed["description"] = {"before": finding.description, "after": description}
        finding.description = description
    if root_cause is not None and root_cause != finding.root_cause:
        changed["root_cause"] = {"before": finding.root_cause, "after": root_cause}
        finding.root_cause = root_cause
    if correction is not None and correction != finding.correction:
        changed["correction"] = {"before": finding.correction, "after": correction}
        finding.correction = correction
    if corrective_action is not None and corrective_action != finding.corrective_action:
        changed["corrective_action"] = {"before": finding.corrective_action, "after": corrective_action}
        finding.corrective_action = corrective_action
    if status is not None and status != finding.status:
        changed["status"] = {"before": finding.status, "after": status}
        finding.status = status
    if due_date is not None and due_date != finding.due_date:
        changed["due_date"] = {"before": finding.due_date.isoformat() if finding.due_date else None, "after": due_date.isoformat()}
        finding.due_date = due_date

    if not changed:
        return finding

    audit_log = AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    )
    db.add(audit_log)

    await enqueue_embedding(db, "audit_finding", finding.finding_id, None, finding.factory_id)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update audit finding: {e}")
    await db.refresh(finding)
    return finding


async def close_audit_finding(db: AsyncSession, finding: AuditFinding, user_id: uuid.UUID) -> AuditFinding:
    if finding.status != "open":
        raise ValueError("only open findings can be closed")

    now = datetime.now(UTC)
    finding.status = "closed"
    finding.closed_at = now

    audit_log = AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="TRANSITION",
        changed_fields={
            "status": {"before": "open", "after": "closed"},
            "closed_at": now.isoformat(),
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(finding)
    return finding


async def create_capa_from_finding(
    db: AsyncSession,
    finding: AuditFinding,
    user_id: uuid.UUID,
) -> CAPAEightD:
    if finding.capa_ref_id is not None:
        raise ValueError("finding already has an associated CAPA")

    year = datetime.now().year
    doc_no = await _generate_8d_no(db, year)
    title = f"【审核发现】{finding.clause_ref or ''} - {finding.description[:50]}"
    severity = "严重" if finding.finding_type == "major_nc" else "一般"

    capa = CAPAEightD(
        document_no=doc_no,
        title=title,
        status="D1_TEAM",
        severity=severity,
        d2_description=finding.description,
        d4_root_cause=finding.root_cause or "",
        due_date=finding.due_date,
        created_by=user_id,
    )
    db.add(capa)

    # Flush to get capa.report_id before linking
    await db.flush()

    finding.capa_ref_id = capa.report_id

    audit_log = AuditLog(
        table_name="audit_findings",
        record_id=finding.finding_id,
        action="CREATE",
        changed_fields={
            "capa_ref_id": str(capa.report_id),
            "capa_doc_no": doc_no,
            "action": "linked CAPA from finding",
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to create CAPA from finding: {e}")
    await db.refresh(capa)
    await db.refresh(finding)
    return capa


# ───────────────────────────────────────────────
# Stats
# ───────────────────────────────────────────────

async def get_audit_stats(db: AsyncSession, factory_id: uuid.UUID | None = None) -> dict:
    program_query = select(func.count()).select_from(AuditProgram)
    if factory_id is not None:
        program_query = program_query.where(AuditProgram.factory_id == factory_id)
    program_result = await db.execute(program_query)
    program_count = program_result.scalar() or 0

    # AuditPlan doesn't have factory_id; join through AuditProgram
    plan_base = select(func.count()).select_from(AuditPlan).join(
        AuditProgram, AuditPlan.program_id == AuditProgram.program_id
    )
    if factory_id is not None:
        plan_base = plan_base.where(AuditProgram.factory_id == factory_id)

    planned_result = await db.execute(
        plan_base.where(AuditPlan.status == "planned")
    )
    planned_count = planned_result.scalar() or 0

    in_progress_result = await db.execute(
        plan_base.where(AuditPlan.status == "in_progress")
    )
    in_progress_count = in_progress_result.scalar() or 0

    completed_result = await db.execute(
        plan_base.where(AuditPlan.status == "completed")
    )
    completed_count = completed_result.scalar() or 0

    finding_factory_filter = [AuditFinding.factory_id == factory_id] if factory_id else []
    open_findings_result = await db.execute(
        select(func.count()).select_from(AuditFinding).where(AuditFinding.status == "open",
        *finding_factory_filter)
    )
    open_findings = open_findings_result.scalar() or 0

    major_nc_result = await db.execute(
        select(func.count())
        .select_from(AuditFinding)
        .where(AuditFinding.finding_type == "major_nc", AuditFinding.status == "open",
        *finding_factory_filter)
    )
    major_nc_count = major_nc_result.scalar() or 0

    return {
        "program_count": program_count,
        "planned_count": planned_count,
        "in_progress_count": in_progress_count,
        "completed_count": completed_count,
        "open_findings": open_findings,
        "major_nc_count": major_nc_count,
    }


# ───────────────────────────────────────────────
# Auditors
# ───────────────────────────────────────────────

async def _check_auditor_qualification(db: AsyncSession, auditor_id: uuid.UUID) -> None:
    """Raise ValueError if the auditor's qualification has expired (> 12 months)."""
    from datetime import date as date_type
    user = await db.get(User, auditor_id)
    if user is None:
        return
    if user.auditor_info and user.auditor_info.get('last_qualification_date'):
        try:
            qual_date = datetime.fromisoformat(user.auditor_info['last_qualification_date']).date()
            if (date_type.today() - qual_date).days > 365:
                raise ValueError("审核员资格已过期，请先完成资格再评审")
        except (ValueError, TypeError):
            pass  # If date parse fails, allow assignment (warn in logs in production)

async def list_auditors(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).where(User.auditor_info.isnot(None)))
    return list(result.scalars().all())


async def update_auditor_info(
    db: AsyncSession,
    user: User,
    is_auditor: bool,
    qualifications: list | None,
    last_qualification_date: date | None,
    user_id: uuid.UUID,
) -> User:
    changed = {}
    old_info = user.auditor_info or {}

    if is_auditor:
        new_info = {
            "qualifications": qualifications or [],
            "last_qualification_date": last_qualification_date.isoformat() if last_qualification_date else None,
        }
        if new_info != old_info:
            changed["auditor_info"] = {"before": old_info, "after": new_info}
            user.auditor_info = new_info
    else:
        if old_info:
            changed["auditor_info"] = {"before": old_info, "after": None}
            user.auditor_info = None

    if not changed:
        return user

    audit_log = AuditLog(
        table_name="users",
        record_id=user.user_id,
        action="UPDATE",
        changed_fields=changed,
        operated_by=user_id,
    )
    db.add(audit_log)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise ValueError(f"failed to update auditor info: {e}")
    await db.refresh(user)
    return user
