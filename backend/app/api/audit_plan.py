import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_engineer_or_admin
from app.models.user import User
from app import schemas
from app.services import audit_service

router = APIRouter(prefix="/api/audit-plans", tags=["audit-plans"])


CHECKLIST_TEMPLATES = [
    {
        "audit_type": "system",
        "name": "体系审核检查表",
        "items": [
            {"item_no": "4.1", "clause": "4.1 理解组织及其环境", "question": "组织是否识别了与其宗旨相关的内外部议题？", "result": "", "evidence": "", "note": ""},
            {"item_no": "4.2", "clause": "4.2 理解相关方需求", "question": "相关方及其要求是否被识别并监视？", "result": "", "evidence": "", "note": ""},
            {"item_no": "5.1", "clause": "5.1 领导作用和承诺", "question": "最高管理者是否对质量管理体系的有效性承担责任？", "result": "", "evidence": "", "note": ""},
            {"item_no": "6.1", "clause": "6.1 应对风险和机遇的措施", "question": "风险和机遇是否被识别并策划应对措施？", "result": "", "evidence": "", "note": ""},
            {"item_no": "7.1", "clause": "7.1 资源", "question": "组织是否确定和提供了所需的资源？", "result": "", "evidence": "", "note": ""},
            {"item_no": "8.1", "clause": "8.1 运行的策划和控制", "question": "过程是否被策划、实施、监视和改进？", "result": "", "evidence": "", "note": ""},
            {"item_no": "9.1", "clause": "9.1 监视、测量、分析和评价", "question": "是否策划并实施了所需的监视和测量活动？", "result": "", "evidence": "", "note": ""},
            {"item_no": "10.2", "clause": "10.2 不合格和纠正措施", "question": "是否对不合格做出应对并在必要时采取纠正措施？", "result": "", "evidence": "", "note": ""},
        ],
    },
    {
        "audit_type": "process",
        "name": "过程审核检查表",
        "items": [
            {"item_no": "P1", "clause": "过程输入", "question": "输入要求是否完整、明确并被验证？", "result": "", "evidence": "", "note": ""},
            {"item_no": "P2", "clause": "过程资源", "question": "人员、设备、环境是否满足过程要求？", "result": "", "evidence": "", "note": ""},
            {"item_no": "P3", "clause": "过程方法", "question": "作业指导书/控制计划是否被有效执行？", "result": "", "evidence": "", "note": ""},
            {"item_no": "P4", "clause": "过程监视", "question": "关键过程参数是否被监视并记录？", "result": "", "evidence": "", "note": ""},
            {"item_no": "P5", "clause": "过程输出", "question": "输出是否满足规定的接收准则？", "result": "", "evidence": "", "note": ""},
            {"item_no": "P6", "clause": "过程改进", "question": "是否利用过程数据推动持续改进？", "result": "", "evidence": "", "note": ""},
        ],
    },
    {
        "audit_type": "product",
        "name": "产品审核检查表",
        "items": [
            {"item_no": "D1", "clause": "外观", "question": "产品外观是否符合图纸/规范要求？", "result": "", "evidence": "", "note": ""},
            {"item_no": "D2", "clause": "尺寸", "question": "关键尺寸是否在公差范围内？", "result": "", "evidence": "", "note": ""},
            {"item_no": "D3", "clause": "功能", "question": "产品功能测试结果是否满足规范？", "result": "", "evidence": "", "note": ""},
            {"item_no": "D4", "clause": "标识", "question": "产品标识、追溯信息是否完整正确？", "result": "", "evidence": "", "note": ""},
            {"item_no": "D5", "clause": "包装", "question": "包装方式和防护是否符合要求？", "result": "", "evidence": "", "note": ""},
        ],
    },
]


@router.get("", response_model=schemas.audit.AuditPlanListResponse)
async def list_audit_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    program_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await audit_service.list_audit_plans(
        db, page, page_size, program_id, status, date_from, date_to
    )
    return schemas.audit.AuditPlanListResponse(
        items=[schemas.audit.AuditPlanResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=schemas.audit.AuditPlanResponse)
async def create_audit_plan(
    req: schemas.audit.AuditPlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    try:
        plan = await audit_service.create_audit_plan(
            db,
            program_id=req.program_id,
            audit_scope=req.audit_scope,
            audit_criteria=req.audit_criteria,
            planned_date=req.planned_date,
            lead_auditor=req.lead_auditor,
            team_members=req.team_members,
            checklist=req.checklist,
            user_id=user.user_id,
        )
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{audit_id}", response_model=schemas.audit.AuditPlanResponse)
async def get_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    return schemas.audit.AuditPlanResponse.model_validate(plan)


@router.put("/{audit_id}", response_model=schemas.audit.AuditPlanResponse)
async def update_audit_plan(
    audit_id: uuid.UUID,
    req: schemas.audit.AuditPlanUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.update_audit_plan(
            db,
            plan=plan,
            audit_scope=req.audit_scope,
            audit_criteria=req.audit_criteria,
            planned_date=req.planned_date,
            actual_date=req.actual_date,
            lead_auditor=req.lead_auditor,
            team_members=req.team_members,
            checklist=req.checklist,
            status=req.status,
            user_id=user.user_id,
        )
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{audit_id}")
async def delete_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        await audit_service.delete_audit_plan(db, plan, user.user_id)
        return {"message": "audit plan deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{audit_id}/start", response_model=schemas.audit.AuditPlanResponse)
async def start_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.start_audit_plan(db, plan, user.user_id)
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{audit_id}/complete", response_model=schemas.audit.AuditPlanResponse)
async def complete_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.complete_audit_plan(db, plan, user.user_id)
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{audit_id}/cancel", response_model=schemas.audit.AuditPlanResponse)
async def cancel_audit_plan(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_engineer_or_admin),
):
    plan = await audit_service.get_audit_plan(db, audit_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="audit plan not found")
    try:
        plan = await audit_service.cancel_audit_plan(db, plan, user.user_id)
        return schemas.audit.AuditPlanResponse.model_validate(plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{audit_id}/findings", response_model=schemas.audit.AuditFindingListResponse)
async def get_plan_findings(
    audit_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await audit_service.list_audit_findings(
        db, page, page_size, audit_id=audit_id
    )
    return schemas.audit.AuditFindingListResponse(
        items=[schemas.audit.AuditFindingResponse.model_validate(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/checklist-templates")
async def get_checklist_templates(
    _user: User = Depends(get_current_user),
):
    return CHECKLIST_TEMPLATES
