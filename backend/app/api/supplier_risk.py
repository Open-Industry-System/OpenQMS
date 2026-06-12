"""API routes for supplier risk alert module."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import validate_factory_invariant, resolve_create_factory_id, check_factory_access
from app.core.permissions import Module, PermissionLevel, get_user_permission
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
from app.services.supplier_risk.notifier import send_notifications, sanitize_channel_config


router = APIRouter(prefix="/api/supplier-risk", tags=["supplier-risk"])


def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="预警不存在")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="预警不存在")


def _apply_factory_filter(query, model, scope: RequestScope):
    """Apply factory_id filter to a query based on scope."""
    if hasattr(model, "factory_id"):
        if scope.effective_factory_id:
            query = query.where(model.factory_id == scope.effective_factory_id)
        elif scope.factory_scope.accessible_factory_ids is not None:
            if scope.factory_scope.accessible_factory_ids:
                query = query.where(model.factory_id.in_(scope.factory_scope.accessible_factory_ids))
            else:
                query = query.where(False)
    return query


def _apply_pl_scope_filter(query, model, scope: RequestScope, product_line_code: str | None = None):
    """Apply product line scope filter, intersecting with user-supplied product_line_code if present."""
    if not hasattr(model, "product_line_code"):
        return query
    if scope.pl_scope.mode == "NONE":
        query = query.where(False)
    elif scope.pl_scope.mode == "EXPLICIT" and scope.pl_scope.codes:
        if product_line_code:
            if product_line_code in scope.pl_scope.codes:
                query = query.where(model.product_line_code == product_line_code)
            else:
                query = query.where(False)
        else:
            query = query.where(model.product_line_code.in_(scope.pl_scope.codes))
    elif product_line_code:
        query = query.where(model.product_line_code == product_line_code)
    return query


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
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 VIEW 权限")

    query = select(SupplierRiskAlert)
    count_query = select(func.count()).select_from(SupplierRiskAlert)

    # Apply factory + product line scope
    query = _apply_factory_filter(query, SupplierRiskAlert, scope)
    count_query = _apply_factory_filter(count_query, SupplierRiskAlert, scope)
    query = _apply_pl_scope_filter(query, SupplierRiskAlert, scope, product_line_code)
    count_query = _apply_pl_scope_filter(count_query, SupplierRiskAlert, scope, product_line_code)

    if risk_level:
        query = query.where(SupplierRiskAlert.risk_level == risk_level)
        count_query = count_query.where(SupplierRiskAlert.risk_level == risk_level)
    if status:
        query = query.where(SupplierRiskAlert.status == status)
        count_query = count_query.where(SupplierRiskAlert.status == status)
    if supplier_id:
        query = query.where(SupplierRiskAlert.supplier_id == supplier_id)
        count_query = count_query.where(SupplierRiskAlert.supplier_id == supplier_id)

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
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 VIEW 权限")

    alert = await db.get(SupplierRiskAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="预警不存在")
    _check_factory_access(alert, scope)

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
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 EDIT 权限")

    # close requires APPROVE level (manager or admin)
    if req.action == "close":
        if perm_level < PermissionLevel.APPROVE:
            raise HTTPException(status_code=403, detail="关闭预警需要审批权限")

    # Factory access check
    alert = await db.get(SupplierRiskAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="预警不存在")
    _check_factory_access(alert, scope)

    try:
        alert = await handle_alert(db, alert_id, req.action, req.note, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return alert


@router.post("/alerts/{alert_id}/scar", response_model=dict)
async def create_scar_from_alert_route(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 EDIT 权限")

    # Factory access check
    alert = await db.get(SupplierRiskAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="预警不存在")
    _check_factory_access(alert, scope)

    try:
        scar = await create_scar_from_alert(db, alert_id, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"scar_id": str(scar.scar_id)}


@router.post("/alerts/{alert_id}/capa", response_model=dict)
async def create_capa_from_alert_route(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 EDIT 权限")

    # Factory access check
    alert = await db.get(SupplierRiskAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="预警不存在")
    _check_factory_access(alert, scope)

    try:
        capa = await create_capa_from_alert(db, alert_id, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"capa_id": str(capa.report_id)}


# ─── Evaluation ────────────────────────────────────────────────────────────────

@router.post("/evaluate/{supplier_id}", response_model=EvaluationResponse)
async def evaluate_one(
    supplier_id: uuid.UUID,
    product_line_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 EDIT 权限")

    # If user specified a product_line_code, check it's within scope
    if product_line_code and scope.pl_scope.mode == "EXPLICIT":
        if scope.pl_scope.codes and product_line_code not in scope.pl_scope.codes:
            raise HTTPException(status_code=403, detail="无权访问该产品线")

    try:
        result = await evaluate_supplier_risk(db, supplier_id, product_line_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return EvaluationResponse(**result)


@router.post("/evaluate", response_model=list[EvaluationResponse])
async def evaluate_all(
    product_line_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 APPROVE 权限")

    # If user specified a product_line_code, check it's within scope
    if product_line_code and scope.pl_scope.mode == "EXPLICIT":
        if scope.pl_scope.codes and product_line_code not in scope.pl_scope.codes:
            raise HTTPException(status_code=403, detail="无权访问该产品线")

    results = await evaluate_all_suppliers(db, product_line_code)
    return [EvaluationResponse(**r) for r in results]


# ─── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=RiskDashboardResponse)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 VIEW 权限")

    # Build base alert query with factory + pl scope filters
    base_alert = select(SupplierRiskAlert)
    base_alert = _apply_factory_filter(base_alert, SupplierRiskAlert, scope)
    base_alert = _apply_pl_scope_filter(base_alert, SupplierRiskAlert, scope)

    # Count queries with scope filters applied
    high_q = select(func.count()).select_from(SupplierRiskAlert).where(SupplierRiskAlert.risk_level == "high")
    high_q = _apply_factory_filter(high_q, SupplierRiskAlert, scope)
    high_q = _apply_pl_scope_filter(high_q, SupplierRiskAlert, scope)
    high = (await db.execute(high_q)).scalar() or 0

    critical_q = select(func.count()).select_from(SupplierRiskAlert).where(SupplierRiskAlert.risk_level == "critical")
    critical_q = _apply_factory_filter(critical_q, SupplierRiskAlert, scope)
    critical_q = _apply_pl_scope_filter(critical_q, SupplierRiskAlert, scope)
    critical = (await db.execute(critical_q)).scalar() or 0

    open_q = select(func.count()).select_from(SupplierRiskAlert).where(SupplierRiskAlert.status == "open")
    open_q = _apply_factory_filter(open_q, SupplierRiskAlert, scope)
    open_q = _apply_pl_scope_filter(open_q, SupplierRiskAlert, scope)
    open_count = (await db.execute(open_q)).scalar() or 0

    avg_q = select(func.avg(SupplierRiskAlert.risk_score)).select_from(SupplierRiskAlert)
    avg_q = _apply_factory_filter(avg_q, SupplierRiskAlert, scope)
    avg_q = _apply_pl_scope_filter(avg_q, SupplierRiskAlert, scope)
    avg_score = (await db.execute(avg_q)).scalar() or 0.0

    distribution = {}
    for level in ("low", "medium"):
        level_q = select(func.count()).select_from(SupplierRiskAlert).where(SupplierRiskAlert.risk_level == level)
        level_q = _apply_factory_filter(level_q, SupplierRiskAlert, scope)
        level_q = _apply_pl_scope_filter(level_q, SupplierRiskAlert, scope)
        distribution[level] = (await db.execute(level_q)).scalar() or 0
    distribution["high"] = high
    distribution["critical"] = critical

    # Risk points for scatter plot
    points_q = select(SupplierRiskAlert, Supplier).join(Supplier, SupplierRiskAlert.supplier_id == Supplier.supplier_id)
    points_q = _apply_factory_filter(points_q, SupplierRiskAlert, scope)
    points_q = _apply_pl_scope_filter(points_q, SupplierRiskAlert, scope)
    result = await db.execute(points_q)
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
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 VIEW 权限")

    # If user specified a product_line_code, check it's within scope
    if product_line_code and scope.pl_scope.mode == "EXPLICIT":
        if scope.pl_scope.codes and product_line_code not in scope.pl_scope.codes:
            return []

    configs = await list_configs(db, product_line_code, supplier_id)
    return configs


@router.put("/configs/{config_id}", response_model=RuleConfigResponse)
async def update_rule_config(
    config_id: uuid.UUID,
    req: RuleConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 APPROVE 权限")

    # Factory access check on the config
    config = await db.get(SupplierRiskConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    _check_factory_access(config, scope)

    try:
        config = await update_config(db, config_id, req.model_dump(exclude_unset=True), scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return config


# ─── Notification Channels ─────────────────────────────────────────────────────

@router.get("/channels")
async def list_channels(
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 VIEW 权限")

    query = select(SupplierRiskNotificationChannel).order_by(SupplierRiskNotificationChannel.created_at.desc())
    query = _apply_factory_filter(query, SupplierRiskNotificationChannel, scope)
    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        {
            "channel_id": str(c.channel_id),
            "channel_type": c.channel_type,
            "config": sanitize_channel_config(c.config),
            "min_risk_level": c.min_risk_level,
            "enabled": c.enabled,
            "supplier_id": str(c.supplier_id) if c.supplier_id else None,
            "product_line_code": c.product_line_code,
            "created_by": str(c.created_by),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.post("/channels", response_model=ChannelResponse)
async def create_channel(
    req: ChannelCreateRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 APPROVE 权限")

    from app.services.supplier_risk.notifier import encrypt_secret
    config = req.config.copy()
    if req.channel_type == "webhook" and "secret" in config:
        try:
            config["secret_encrypted"] = encrypt_secret(config.pop("secret"))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

    factory_id = await resolve_create_factory_id(db, scope, product_line_code=req.product_line_code)
    check_factory_access(factory_id, scope)
    channel = SupplierRiskNotificationChannel(
        channel_type=req.channel_type,
        config=config,
        min_risk_level=req.min_risk_level,
        enabled=req.enabled,
        supplier_id=req.supplier_id,
        product_line_code=req.product_line_code,
        created_by=scope.user.user_id,
        factory_id=factory_id,
    )
    db.add(channel)
    await validate_factory_invariant(channel, db)
    await db.commit()
    await db.refresh(channel)
    # Sanitize before returning so secret_encrypted is redacted
    channel.config = sanitize_channel_config(channel.config)
    return channel


@router.put("/channels/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: uuid.UUID,
    req: ChannelUpdateRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 APPROVE 权限")

    channel = await db.get(SupplierRiskNotificationChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="通知渠道不存在")
    _check_factory_access(channel, scope)

    from app.services.supplier_risk.notifier import encrypt_secret
    updates = req.model_dump(exclude_unset=True)
    if "config" in updates:
        new_config = updates["config"].copy()
        if channel.channel_type == "webhook" and "secret" in new_config:
            try:
                new_config["secret_encrypted"] = encrypt_secret(new_config.pop("secret"))
            except RuntimeError as e:
                raise HTTPException(status_code=503, detail=str(e))
        channel.config = new_config

    if "min_risk_level" in updates:
        channel.min_risk_level = updates["min_risk_level"]
    if "enabled" in updates:
        channel.enabled = updates["enabled"]

    await db.commit()
    await db.refresh(channel)
    channel.config = sanitize_channel_config(channel.config)
    return channel


@router.delete("/channels/{channel_id}")
async def delete_channel(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # Permission check
    perm_level = await get_user_permission(scope.user, Module.SUPPLIER_RISK, db)
    if perm_level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="需要 supplier_risk 模块的 APPROVE 权限")

    channel = await db.get(SupplierRiskNotificationChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="通知渠道不存在")
    _check_factory_access(channel, scope)
    await db.delete(channel)
    await db.commit()
    return {"ok": True}