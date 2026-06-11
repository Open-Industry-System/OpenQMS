"""API routes for supplier risk alert module."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import Module, PermissionLevel, require_permission
from app.models.supplier import Supplier
from app.models.supplier_risk import SupplierRiskAlert, SupplierRiskConfig, SupplierRiskNotificationChannel
from app.schemas.supplier_risk import (
    AlertListParams,
    AlertListResponse,
    AlertResponse,
    HandleAlertRequest,
    RiskDashboardResponse,
    RuleConfigResponse,
    RuleConfigUpdateRequest,
    ChannelCreateRequest,
    ChannelUpdateRequest,
    ChannelResponse,
    EvaluationResponse,
)
from app.services.supplier_risk.service import (
    evaluate_supplier_risk,
    evaluate_all_suppliers,
    handle_alert,
    create_scar_from_alert,
    create_capa_from_alert,
)
from app.services.supplier_risk.config import list_configs, update_config
from app.services.supplier_risk.notifier import send_notifications


router = APIRouter(prefix="/api/supplier-risk", tags=["supplier-risk"])


# ─── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    risk_level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
    product_line_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.VIEW)),
):
    query = select(SupplierRiskAlert)
    if risk_level:
        query = query.where(SupplierRiskAlert.risk_level == risk_level)
    if status:
        query = query.where(SupplierRiskAlert.status == status)
    if supplier_id:
        query = query.where(SupplierRiskAlert.supplier_id == supplier_id)
    if product_line_code:
        query = query.where(SupplierRiskAlert.product_line_code == product_line_code)

    count_query = select(func.count()).select_from(SupplierRiskAlert)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    query = query.order_by(SupplierRiskAlert.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.scalars().all()

    # Resolve supplier names
    supplier_ids = {r.supplier_id for r in rows}
    suppliers = {}
    if supplier_ids:
        sup_result = await db.execute(select(Supplier).where(Supplier.supplier_id.in_(supplier_ids)))
        suppliers = {s.supplier_id: s for s in sup_result.scalars().all()}

    items = []
    for alert in rows:
        ar = AlertResponse.model_validate(alert)
        sup = suppliers.get(alert.supplier_id)
        ar.supplier_name = sup.name if sup else ""
        ar.supplier_no = sup.supplier_no if sup else ""
        items.append(ar)

    return AlertListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.VIEW)),
):
    alert = await db.get(SupplierRiskAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="预警不存在")

    ar = AlertResponse.model_validate(alert)
    supplier = await db.get(Supplier, alert.supplier_id)
    ar.supplier_name = supplier.name if supplier else ""
    ar.supplier_no = supplier.supplier_no if supplier else ""
    return ar


@router.post("/alerts/{alert_id}/handle", response_model=AlertResponse)
async def handle_alert_route(
    alert_id: uuid.UUID,
    req: HandleAlertRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.EDIT)),
):
    try:
        alert = await handle_alert(db, alert_id, req.action, req.note, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return alert


@router.post("/alerts/{alert_id}/scar", response_model=dict)
async def create_scar_from_alert_route(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.EDIT)),
):
    try:
        scar = await create_scar_from_alert(db, alert_id, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"scar_id": str(scar.scar_id)}


@router.post("/alerts/{alert_id}/capa", response_model=dict)
async def create_capa_from_alert_route(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.EDIT)),
):
    try:
        capa = await create_capa_from_alert(db, alert_id, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"capa_id": str(capa.report_id)}


# ─── Evaluation ────────────────────────────────────────────────────────────────

@router.post("/evaluate/{supplier_id}", response_model=EvaluationResponse)
async def evaluate_one(
    supplier_id: uuid.UUID,
    product_line_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.EDIT)),
):
    try:
        result = await evaluate_supplier_risk(db, supplier_id, product_line_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return EvaluationResponse(**result)


@router.post("/evaluate", response_model=list[EvaluationResponse])
async def evaluate_all(
    product_line_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.APPROVE)),
):
    results = await evaluate_all_suppliers(db, product_line_code)
    return [EvaluationResponse(**r) for r in results]


# ─── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=RiskDashboardResponse)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.VIEW)),
):
    # Count queries
    high = (await db.execute(select(func.count()).select_from(SupplierRiskAlert).where(SupplierRiskAlert.risk_level == "high"))).scalar() or 0
    critical = (await db.execute(select(func.count()).select_from(SupplierRiskAlert).where(SupplierRiskAlert.risk_level == "critical"))).scalar() or 0
    open_count = (await db.execute(select(func.count()).select_from(SupplierRiskAlert).where(SupplierRiskAlert.status == "open"))).scalar() or 0
    avg_score = (await db.execute(select(func.avg(SupplierRiskAlert.risk_score)).select_from(SupplierRiskAlert))).scalar() or 0.0

    distribution = {
        "low": (await db.execute(select(func.count()).select_from(SupplierRiskAlert).where(SupplierRiskAlert.risk_level == "low"))).scalar() or 0,
        "medium": (await db.execute(select(func.count()).select_from(SupplierRiskAlert).where(SupplierRiskAlert.risk_level == "medium"))).scalar() or 0,
        "high": high,
        "critical": critical,
    }

    # Risk points for scatter plot
    result = await db.execute(
        select(SupplierRiskAlert, Supplier)
        .join(Supplier, SupplierRiskAlert.supplier_id == Supplier.supplier_id)
    )
    points = []
    for alert, supplier in result.all():
        points.append({
            "supplier_id": str(alert.supplier_id),
            "supplier_name": supplier.name,
            "supplier_no": supplier.supplier_no,
            "quality_score": alert.quality_score,
            "delivery_score": alert.delivery_score,
            "compliance_score": alert.compliance_score,
            "risk_level": alert.risk_level,
            "risk_score": alert.risk_score,
        })

    return RiskDashboardResponse(
        high_risk_count=high,
        critical_risk_count=critical,
        open_alert_count=open_count,
        avg_risk_score=round(float(avg_score), 2),
        risk_distribution=distribution,
        supplier_risk_points=points,
    )


# ─── Configs ───────────────────────────────────────────────────────────────────

@router.get("/configs", response_model=list[RuleConfigResponse])
async def list_rule_configs(
    product_line_code: Optional[str] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.VIEW)),
):
    configs = await list_configs(db, product_line_code, supplier_id)
    return configs


@router.put("/configs/{config_id}", response_model=RuleConfigResponse)
async def update_rule_config(
    config_id: uuid.UUID,
    req: RuleConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.APPROVE)),
):
    try:
        config = await update_config(db, config_id, req.model_dump(exclude_unset=True), user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return config


# ─── Notification Channels ─────────────────────────────────────────────────────

@router.get("/channels", response_model=list[ChannelResponse])
async def list_channels(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.VIEW)),
):
    result = await db.execute(select(SupplierRiskNotificationChannel).order_by(SupplierRiskNotificationChannel.created_at.desc()))
    return result.scalars().all()


@router.post("/channels", response_model=ChannelResponse)
async def create_channel(
    req: ChannelCreateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.APPROVE)),
):
    from app.services.supplier_risk.notifier import encrypt_secret
    config = req.config.copy()
    if req.channel_type == "webhook" and "secret" in config:
        config["secret_encrypted"] = encrypt_secret(config.pop("secret"))

    channel = SupplierRiskNotificationChannel(
        channel_type=req.channel_type,
        config=config,
        min_risk_level=req.min_risk_level,
        enabled=req.enabled,
        supplier_id=req.supplier_id,
        product_line_code=req.product_line_code,
        created_by=user.user_id,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


@router.put("/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: uuid.UUID,
    req: ChannelUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.APPROVE)),
):
    channel = await db.get(SupplierRiskNotificationChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="通知渠道不存在")

    from app.services.supplier_risk.notifier import encrypt_secret
    updates = req.model_dump(exclude_unset=True)
    if "config" in updates:
        new_config = updates["config"].copy()
        if channel.channel_type == "webhook" and "secret" in new_config:
            new_config["secret_encrypted"] = encrypt_secret(new_config.pop("secret"))
        channel.config = new_config

    if "min_risk_level" in updates:
        channel.min_risk_level = updates["min_risk_level"]
    if "enabled" in updates:
        channel.enabled = updates["enabled"]

    await db.commit()
    await db.refresh(channel)
    return channel


@router.delete("/channels/{channel_id}")
async def delete_channel(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_permission(Module.SUPPLIER_RISK, PermissionLevel.APPROVE)),
):
    channel = await db.get(SupplierRiskNotificationChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="通知渠道不存在")
    await db.delete(channel)
    await db.commit()
    return {"ok": True}
