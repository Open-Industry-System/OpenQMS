import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.apqp import APQPProject
from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.models.control_plan import ControlPlan
from app.models.supplier import SupplierPPAPSubmission
from app.models.product_line import ProductLine


PHASE_NAMES = {
    1: "策划与定义",
    2: "产品设计与开发",
    3: "过程设计与开发",
    4: "产品与过程确认",
    5: "量产启动与反馈",
}

DELIVERABLE_CHECKS = {
    2: [{"field": "dfmea_id", "label": "DFMEA"}],
    3: [{"field": "pfmea_id", "label": "PFMEA"}, {"field": "control_plan_id", "label": "控制计划"}],
    4: [{"field": "ppap_submission_id", "label": "PPAP"}],
}


async def _next_project_code(db: AsyncSession) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"APQP-{year}-"
    result = await db.execute(
        select(APQPProject.project_code)
        .where(APQPProject.project_code.like(f"{prefix}%"))
        .order_by(APQPProject.project_code.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    seq = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{seq:03d}"


def _append_gate_history(project: APQPProject, action: str, user_id: uuid.UUID, user_name: str, comments: str | None):
    entry = {
        "phase": project.current_phase,
        "action": action,
        "user_id": str(user_id),
        "user_name": user_name,
        "comments": comments,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if project.gate_history is None:
        project.gate_history = [entry]
    else:
        project.gate_history = project.gate_history + [entry]


async def list_projects(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    project_status: str | None = None,
    current_phase: int | None = None,
) -> tuple[list[APQPProject], int]:
    query = select(APQPProject).options(
        selectinload(APQPProject.creator),
        selectinload(APQPProject.gate_approver),
        selectinload(APQPProject.dfmea),
        selectinload(APQPProject.pfmea),
        selectinload(APQPProject.control_plan),
        selectinload(APQPProject.ppap_submission),
    )
    count_query = select(func.count()).select_from(APQPProject)

    if project_status:
        query = query.where(APQPProject.project_status == project_status)
        count_query = count_query.where(APQPProject.project_status == project_status)
    if current_phase is not None:
        query = query.where(APQPProject.current_phase == current_phase)
        count_query = count_query.where(APQPProject.current_phase == current_phase)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(APQPProject.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())
    return items, total


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> APQPProject | None:
    result = await db.execute(
        select(APQPProject)
        .options(
            selectinload(APQPProject.creator),
            selectinload(APQPProject.gate_approver),
            selectinload(APQPProject.dfmea),
            selectinload(APQPProject.pfmea),
            selectinload(APQPProject.control_plan),
            selectinload(APQPProject.ppap_submission),
        )
        .where(APQPProject.project_id == project_id)
    )
    return result.scalar_one_or_none()


async def create_project(
    db: AsyncSession,
    *,
    project_name: str,
    product_name: str,
    product_line_code: str,
    user_id: uuid.UUID,
    customer_name: str | None = None,
    description: str | None = None,
    target_sop_date: date | None = None,
    team_members: list | None = None,
    dfmea_id: uuid.UUID | None = None,
    pfmea_id: uuid.UUID | None = None,
    control_plan_id: uuid.UUID | None = None,
    ppap_submission_id: uuid.UUID | None = None,
) -> APQPProject:
    # Validate linked IDs if provided
    if product_line_code:
        if not await db.get(ProductLine, product_line_code):
            raise ValueError("产品线记录不存在")
    if dfmea_id:
        if not await db.get(FMEADocument, dfmea_id):
            raise ValueError("DFMEA 记录不存在")
    if pfmea_id:
        if not await db.get(FMEADocument, pfmea_id):
            raise ValueError("PFMEA 记录不存在")
    if control_plan_id:
        if not await db.get(ControlPlan, control_plan_id):
            raise ValueError("控制计划记录不存在")
    if ppap_submission_id:
        if not await db.get(SupplierPPAPSubmission, ppap_submission_id):
            raise ValueError("PPAP 提交记录不存在")

    for attempt in range(3):
        project_code = await _next_project_code(db)
        project = APQPProject(
            project_code=project_code,
            project_name=project_name,
            product_name=product_name,
            product_line_code=product_line_code,
            customer_name=customer_name,
            description=description,
            target_sop_date=target_sop_date,
            team_members=team_members,
            dfmea_id=dfmea_id,
            pfmea_id=pfmea_id,
            control_plan_id=control_plan_id,
            ppap_submission_id=ppap_submission_id,
            created_by=user_id,
        )
        db.add(project)
        try:
            await db.flush()
            break
        except IntegrityError as e:
            if "apqp_projects_project_code" not in str(e.orig):
                raise
            await db.rollback()
            if attempt == 2:
                raise ValueError("项目编号生成冲突，请重试")
            continue

    db.add(AuditLog(
        table_name="apqp_projects",
        record_id=project.project_id,
        action="CREATE",
        changed_fields={"project_code": project.project_code, "project_name": project_name, "product_name": product_name},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_project(db, project.project_id)


async def update_project(
    db: AsyncSession,
    project: APQPProject,
    *,
    user_id: uuid.UUID,
    **kwargs,
) -> APQPProject:
    # Validate linked IDs if being updated
    fk_fields = {
        "product_line_code": (ProductLine, "产品线"),
        "dfmea_id": (FMEADocument, "DFMEA"),
        "pfmea_id": (FMEADocument, "PFMEA"),
        "control_plan_id": (ControlPlan, "控制计划"),
        "ppap_submission_id": (SupplierPPAPSubmission, "PPAP"),
    }
    for key, (model, label) in fk_fields.items():
        val = kwargs.get(key)
        if val is not None and not await db.get(model, val):
            raise ValueError(f"{label} 记录不存在")

    changed = {}
    field_map = {
        "project_name": "project_name",
        "product_name": "product_name",
        "product_line_code": "product_line_code",
        "customer_name": "customer_name",
        "description": "description",
        "target_sop_date": "target_sop_date",
        "team_members": "team_members",
        "dfmea_id": "dfmea_id",
        "pfmea_id": "pfmea_id",
        "control_plan_id": "control_plan_id",
        "ppap_submission_id": "ppap_submission_id",
    }
    for key, attr in field_map.items():
        if key in kwargs:
            val = kwargs[key]
            setattr(project, attr, val)
            if attr in ("target_sop_date", "dfmea_id", "pfmea_id", "control_plan_id", "ppap_submission_id"):
                changed[key] = str(val) if val is not None else None
            elif attr == "team_members":
                changed[key] = str(val) if val is not None else None
            else:
                changed[key] = val

    if changed:
        db.add(AuditLog(
            table_name="apqp_projects",
            record_id=project.project_id,
            action="UPDATE",
            changed_fields=changed,
            operated_by=user_id,
        ))
    await db.commit()
    return await get_project(db, project.project_id)


async def get_stats(db: AsyncSession) -> dict:
    today = date.today()

    total = (await db.execute(select(func.count()).select_from(APQPProject))).scalar() or 0
    active = (await db.execute(select(func.count()).where(APQPProject.project_status == "active"))).scalar() or 0
    pending = (await db.execute(
        select(func.count()).where(
            APQPProject.phase_status == "pending_approval",
            APQPProject.project_status == "active",
        )
    )).scalar() or 0
    completed = (await db.execute(select(func.count()).where(APQPProject.project_status == "completed"))).scalar() or 0
    cancelled = (await db.execute(select(func.count()).where(APQPProject.project_status == "cancelled"))).scalar() or 0
    overdue = (await db.execute(
        select(func.count()).where(
            APQPProject.target_sop_date < today,
            APQPProject.project_status == "active",
        )
    )).scalar() or 0

    phase_rows = (await db.execute(
        select(APQPProject.current_phase, func.count())
        .where(APQPProject.project_status == "active")
        .group_by(APQPProject.current_phase)
    )).all()
    phase_dist = {row[0]: row[1] for row in phase_rows}

    return {
        "total_projects": total,
        "active_count": active,
        "pending_approval_count": pending,
        "completed_count": completed,
        "cancelled_count": cancelled,
        "overdue_count": overdue,
        "phase_distribution": phase_dist,
    }


async def transition_project(
    db: AsyncSession,
    project: APQPProject,
    action: str,
    user_id: uuid.UUID,
    user_name: str,
    comments: str | None = None,
) -> APQPProject:
    if project.project_status != "active":
        raise ValueError("项目不在进行中，无法操作")

    if action == "submit_gate":
        if project.phase_status != "in_progress":
            raise ValueError("当前阶段不在进行中")
        project.phase_status = "pending_approval"
        _append_gate_history(project, "submit", user_id, user_name, comments)

    elif action == "approve_gate":
        if project.phase_status != "pending_approval":
            raise ValueError("当前阶段未提交审批")
        checks = DELIVERABLE_CHECKS.get(project.current_phase, [])
        for check in checks:
            if not getattr(project, check["field"]):
                raise ValueError(f"Phase {project.current_phase} 需关联 {check['label']} 后方可审批通过")
        now = datetime.now(timezone.utc)
        project.gate_approved_by = user_id
        project.gate_approved_at = now
        project.gate_comments = comments
        setattr(project, f"phase_{project.current_phase}_completed_at", now)
        _append_gate_history(project, "approve", user_id, user_name, comments)
        if project.current_phase < 5:
            project.current_phase += 1
            project.phase_status = "in_progress"
        else:
            project.project_status = "completed"
            project.phase_status = "completed"

    elif action == "reject_gate":
        if project.phase_status != "pending_approval":
            raise ValueError("当前阶段未提交审批")
        project.phase_status = "in_progress"
        project.gate_comments = comments
        _append_gate_history(project, "reject", user_id, user_name, comments)

    elif action == "cancel":
        project.project_status = "cancelled"

    else:
        raise ValueError(f"无效动作: {action}")

    db.add(AuditLog(
        table_name="apqp_projects",
        record_id=project.project_id,
        action="TRANSITION",
        changed_fields={"action": action, "comments": comments},
        operated_by=user_id,
    ))
    await db.commit()
    return await get_project(db, project.project_id)
