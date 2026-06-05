import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select, func, and_, text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_current_user, require_permission, Module, PermissionLevel
from app.core.product_line_filter import (
    apply_product_line_filter,
    enforce_product_line_access,
    get_user_product_line_codes,
)
from app.models.user import User
from app.models.mes import (
    MESConnection,
    MESSyncJob,
    MESProductionOrder,
    MESEquipmentStatus,
    MESScrapRecord,
    MESPushOutbox,
)
from app.models.audit import AuditLog
from app.schemas import mes as schemas
from app.services.mes_service import MESIngestionService, MESSyncService, MESPushService
from app.services.mes_connector import test_mes_connection, get_mes_connector, get_mes_connector_by_config
from app.services.mes_crypto import hash_api_key, encrypt_credential, sanitize_config
from app.api.mes_deps import require_mes_api_key

router = APIRouter(prefix="/api/mes", tags=["mes"])


# ---------------------------------------------------------------------------
# Helper: validate REST config
# ---------------------------------------------------------------------------

def _validate_rest_config(connector_type: str, config: dict) -> dict:
    if connector_type != "rest":
        return config
    try:
        validated = schemas.RESTConfig.model_validate(config)
    except ValidationError as e:
        errors = e.errors()
        detail = errors[0]["msg"] if len(errors) == 1 else errors
        raise HTTPException(status_code=400, detail=detail)
    return validated.model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# Helper: process credentials in config
# ---------------------------------------------------------------------------

def _process_credentials(config: dict) -> dict:
    """Hash inbound API key, encrypt outbound credentials. Mutates config in place."""
    auth_config = config.get("auth_config")
    if not auth_config:
        return config

    # Hash inbound API key
    inbound_key = auth_config.get("inbound_api_key")
    if inbound_key:
        auth_config["api_key_hash"] = hash_api_key(inbound_key)
        auth_config.pop("inbound_api_key", None)

    # Encrypt outbound credentials
    for field in ("outbound_api_key", "token", "password", "secret", "username"):
        plaintext = auth_config.get(field)
        if plaintext:
            encrypted_field = f"{field}_encrypted"
            auth_config[encrypted_field] = encrypt_credential(plaintext)
            auth_config.pop(field, None)

    return config


# ---------------------------------------------------------------------------
# Helper: strip "***" placeholders from auth_config
# ---------------------------------------------------------------------------

def _strip_placeholder_credentials(config: dict) -> dict:
    """Remove fields with '***' placeholder values from auth_config."""
    auth_config = config.get("auth_config")
    if not auth_config:
        return config

    keys_to_remove = [k for k, v in auth_config.items() if v == "***"]
    for k in keys_to_remove:
        auth_config.pop(k, None)

    return config


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

@router.get("/connections", response_model=schemas.MESConnectionListResponse)
async def list_connections(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    query = select(MESConnection).where(MESConnection.is_active == True)
    query = await apply_product_line_filter(query, user, MESConnection, "mes", db, request)

    count_query = select(func.count()).select_from(MESConnection).where(MESConnection.is_active == True)
    count_query = await apply_product_line_filter(count_query, user, MESConnection, "mes", db, request)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return schemas.MESConnectionListResponse(
        items=[
            schemas.MESConnectionResponse.model_validate({
                **{k: getattr(c, k) for k in c.__mapper__.columns.keys()},
                "config": sanitize_config(c.config),
            })
            for c in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/connections", response_model=schemas.MESConnectionResponse, status_code=201)
async def create_connection(
    req: schemas.MESConnectionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    # Validate REST config first
    config = _validate_rest_config(req.connector_type, req.config)

    # Process credentials
    config = _process_credentials(config)

    # Enforce product line access
    await enforce_product_line_access(user, req.product_line_code, db)

    connection = MESConnection(
        name=req.name,
        connector_type=req.connector_type,
        config=config,
        product_line_code=req.product_line_code,
        created_by=user.user_id,
        is_active=True,
    )
    db.add(connection)
    await db.flush()

    # Create 4 sync jobs
    await MESSyncService.create_sync_jobs_for_connection(db, connection.connection_id)

    await db.commit()
    await db.refresh(connection)

    return schemas.MESConnectionResponse.model_validate({
        **{k: getattr(connection, k) for k in connection.__mapper__.columns.keys()},
        "config": sanitize_config(connection.config),
    })


@router.get("/connections/{connection_id}", response_model=schemas.MESConnectionResponse)
async def get_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    conn = await db.get(MESConnection, connection_id)
    if not conn or not conn.is_active:
        raise HTTPException(status_code=404, detail="Connection not found")

    await enforce_product_line_access(user, conn.product_line_code, db)

    return schemas.MESConnectionResponse.model_validate({
        **{k: getattr(conn, k) for k in conn.__mapper__.columns.keys()},
        "config": sanitize_config(conn.config),
    })


@router.put("/connections/{connection_id}", response_model=schemas.MESConnectionResponse)
async def update_connection(
    connection_id: uuid.UUID,
    req: schemas.MESConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    conn = await db.get(MESConnection, connection_id)
    if not conn or not conn.is_active:
        raise HTTPException(status_code=404, detail="Connection not found")

    await enforce_product_line_access(user, conn.product_line_code, db)

    # Merge config
    if req.config is not None:
        merged_config = {**(conn.config or {}), **req.config}
        merged_config = _strip_placeholder_credentials(merged_config)

        # Validate merged config
        connector_type = req.connector_type or conn.connector_type
        merged_config = _validate_rest_config(connector_type, merged_config)

        # Process credentials
        merged_config = _process_credentials(merged_config)

        # Final guard: validate resulting connector_type + config
        get_mes_connector_by_config(connector_type, merged_config)

        conn.config = merged_config

    if req.connector_type is not None:
        conn.connector_type = req.connector_type

    if req.name is not None:
        conn.name = req.name

    if req.is_active is not None:
        conn.is_active = req.is_active

    if req.product_line_code is not None:
        await enforce_product_line_access(user, req.product_line_code, db)
        conn.product_line_code = req.product_line_code

    await db.commit()
    await db.refresh(conn)

    return schemas.MESConnectionResponse.model_validate({
        **{k: getattr(conn, k) for k in conn.__mapper__.columns.keys()},
        "config": sanitize_config(conn.config),
    })


@router.delete("/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    conn = await db.get(MESConnection, connection_id)
    if not conn or not conn.is_active:
        raise HTTPException(status_code=404, detail="Connection not found")

    await enforce_product_line_access(user, conn.product_line_code, db)

    # Soft delete
    conn.is_active = False

    # Cancel running/pending sync jobs
    await db.execute(
        select(MESSyncJob)
        .where(MESSyncJob.connection_id == connection_id)
        .where(MESSyncJob.status.in_(["pending", "running"]))
    )
    # Update sync jobs to cancelled
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(MESSyncJob)
        .where(MESSyncJob.connection_id == connection_id)
        .where(MESSyncJob.status.in_(["pending", "running"]))
        .values(status="cancelled")
    )

    # Cancel pending/processing outbox
    await db.execute(
        sa_update(MESPushOutbox)
        .where(MESPushOutbox.connection_id == connection_id)
        .where(MESPushOutbox.status.in_(["pending", "processing"]))
        .values(status="cancelled")
    )

    await db.commit()
    return None


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    conn = await db.get(MESConnection, connection_id)
    if not conn or not conn.is_active:
        raise HTTPException(status_code=404, detail="Connection not found")

    await enforce_product_line_access(user, conn.product_line_code, db)

    # Validate config completeness
    config = conn.config or {}
    if conn.connector_type == "rest":
        if not config.get("base_url"):
            return {"ok": False, "error": "Missing base_url in config"}
        if not config.get("endpoints"):
            return {"ok": False, "error": "Missing endpoints in config"}

    # Lightweight HTTP probe
    result = await test_mes_connection(conn, db)
    return result


# ---------------------------------------------------------------------------
# Ingest (API Key auth, no JWT)
# ---------------------------------------------------------------------------

@router.post("/ingest")
async def ingest_data(
    request: Request,
    db: AsyncSession = Depends(get_db),
    conn: MESConnection = Depends(require_mes_api_key),
):
    body = await request.json()

    # Pre-check data_type
    data_type = body.get("data_type")
    if not data_type:
        raise HTTPException(status_code=400, detail="Missing data_type")

    # Enforce product_line_code from connection
    body["connection_id"] = str(conn.connection_id)
    if conn.product_line_code:
        body["product_line_code"] = conn.product_line_code

    # Manual validation with TypeAdapter
    adapter = TypeAdapter(schemas.MESIngestRequest)
    try:
        validated = adapter.validate_python(body)
    except ValidationError as e:
        errors = e.errors()
        detail = errors[0]["msg"] if len(errors) == 1 else errors
        raise HTTPException(status_code=400, detail=detail)

    # Call ingestion service
    try:
        result = await MESIngestionService.ingest(db, validated.model_dump(mode="json"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    return result


# ---------------------------------------------------------------------------
# Manual sync
# ---------------------------------------------------------------------------

@router.post("/connections/{connection_id}/sync", status_code=202)
async def manual_sync(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.APPROVE)),
):
    conn = await db.get(MESConnection, connection_id)
    if not conn or not conn.is_active:
        raise HTTPException(status_code=404, detail="Connection not found")

    await enforce_product_line_access(user, conn.product_line_code, db)

    try:
        result = await MESSyncService.manual_sync(db, connection_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return result


# ---------------------------------------------------------------------------
# Production Orders
# ---------------------------------------------------------------------------

@router.get("/production-orders", response_model=schemas.MESProductionOrderListResponse)
async def list_production_orders(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.VIEW)),
):
    query = select(MESProductionOrder)
    if status:
        query = query.where(MESProductionOrder.status == status)
    query = await apply_product_line_filter(query, user, MESProductionOrder, "mes", db, request)
    query = query.order_by(MESProductionOrder.created_at.desc())

    # Count query
    count_query = select(func.count()).select_from(query.subquery())
    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return schemas.MESProductionOrderListResponse(
        items=[schemas.MESProductionOrderResponse.model_validate(o) for o in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/production-orders/{order_id}", response_model=schemas.MESProductionOrderResponse)
async def get_production_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.VIEW)),
):
    order = await db.get(MESProductionOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Production order not found")

    await enforce_product_line_access(user, order.product_line_code, db)
    return schemas.MESProductionOrderResponse.model_validate(order)


# ---------------------------------------------------------------------------
# Equipment Status
# ---------------------------------------------------------------------------

@router.get("/equipment-status", response_model=list[schemas.MESEquipmentStatusResponse])
async def list_equipment_status(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.VIEW)),
):
    query = select(MESEquipmentStatus)
    query = await apply_product_line_filter(query, user, MESEquipmentStatus, "mes", db, request)
    query = query.order_by(MESEquipmentStatus.recorded_at.desc())

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return [schemas.MESEquipmentStatusResponse.model_validate(e) for e in items]


# ---------------------------------------------------------------------------
# Scrap Records
# ---------------------------------------------------------------------------

@router.get("/scrap-records", response_model=schemas.MESScrapRecordListResponse)
async def list_scrap_records(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    defect_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.VIEW)),
):
    query = select(MESScrapRecord)
    if defect_type:
        query = query.where(MESScrapRecord.defect_type == defect_type)
    query = await apply_product_line_filter(query, user, MESScrapRecord, "mes", db, request)
    query = query.order_by(MESScrapRecord.recorded_at.desc())

    # Count query
    count_query = select(func.count()).select_from(query.subquery())
    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return schemas.MESScrapRecordListResponse(
        items=[schemas.MESScrapRecordResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Dashboard (DB aggregation only)
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=schemas.MESDashboardResponse)
async def get_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.MES, PermissionLevel.VIEW)),
):
    # Product line isolation
    user_codes: list[str] | None = None
    if not user.role_definition.bypass_row_level_security:
        user_codes = await get_user_product_line_codes(user, db)
        if not user_codes:
            return schemas.MESDashboardResponse(
                equipment_summary=[],
                running_count=0,
                down_count=0,
                total_planned=0,
                total_actual=0,
                scrap_by_category={},
                scrap_trend_7d=[],
            )

    # Equipment summary: latest per equipment via ROW_NUMBER
    from sqlalchemy.orm import aliased
    from sqlalchemy import desc

    eq_sub = (
        select(
            MESEquipmentStatus,
            func.row_number().over(
                partition_by=MESEquipmentStatus.equipment_code,
                order_by=desc(MESEquipmentStatus.recorded_at),
            ).label("rn"),
        )
    )
    if user_codes:
        eq_sub = eq_sub.where(MESEquipmentStatus.product_line_code.in_(user_codes))
    eq_alias = aliased(MESEquipmentStatus, eq_sub.subquery())
    eq_query = select(eq_alias).where(eq_sub.c.rn == 1)
    eq_result = await db.execute(eq_query)
    equipment_rows = eq_result.scalars().all()

    equipment_summary = []
    running_count = 0
    down_count = 0
    for row in equipment_rows:
        equipment_summary.append(schemas.MESEquipmentSummary(
            equipment_code=row.equipment_code,
            equipment_name=row.equipment_name,
            status=row.status,
            availability=float(row.availability) if row.availability is not None else None,
            performance=float(row.performance) if row.performance is not None else None,
            quality=float(row.quality) if row.quality is not None else None,
            oee=float(row.oee) if row.oee is not None else None,
        ))
        if row.status == "running":
            running_count += 1
        elif row.status == "down":
            down_count += 1

    # Today's production aggregate
    today = datetime.now(timezone.utc).date()
    prod_query = select(
        func.coalesce(func.sum(MESProductionOrder.planned_qty), 0).label("total_planned"),
        func.coalesce(func.sum(MESProductionOrder.actual_qty), 0).label("total_actual"),
    ).where(func.date(MESProductionOrder.started_at) == today)
    if user_codes:
        prod_query = prod_query.where(MESProductionOrder.product_line_code.in_(user_codes))
    prod_result = await db.execute(prod_query)
    prod_row = prod_result.one_or_none()
    total_planned = int(prod_row.total_planned) if prod_row else 0
    total_actual = int(prod_row.total_actual) if prod_row else 0

    # Scrap by category (today)
    scrap_cat_query = (
        select(
            MESScrapRecord.defect_category,
            func.sum(MESScrapRecord.defect_qty).label("total_defect_qty"),
        )
        .where(func.date(MESScrapRecord.recorded_at) == today)
        .group_by(MESScrapRecord.defect_category)
    )
    if user_codes:
        scrap_cat_query = scrap_cat_query.where(MESScrapRecord.product_line_code.in_(user_codes))
    scrap_cat_result = await db.execute(scrap_cat_query)
    scrap_by_category = {
        row.defect_category or "未分类": int(row.total_defect_qty)
        for row in scrap_cat_result.all()
    }

    # 7-day scrap trend
    seven_days_ago = today - timedelta(days=6)
    trend_query = (
        select(
            func.date(MESScrapRecord.recorded_at).label("day"),
            func.sum(MESScrapRecord.defect_qty).label("total_defect_qty"),
        )
        .where(func.date(MESScrapRecord.recorded_at).between(seven_days_ago, today))
        .group_by(func.date(MESScrapRecord.recorded_at))
        .order_by(func.date(MESScrapRecord.recorded_at))
    )
    if user_codes:
        trend_query = trend_query.where(MESScrapRecord.product_line_code.in_(user_codes))
    trend_result = await db.execute(trend_query)
    scrap_trend_7d = [
        {"date": str(row.day), "defect_qty": int(row.total_defect_qty)}
        for row in trend_result.all()
    ]

    return schemas.MESDashboardResponse(
        equipment_summary=equipment_summary,
        running_count=running_count,
        down_count=down_count,
        total_planned=total_planned,
        total_actual=total_actual,
        scrap_by_category=scrap_by_category,
        scrap_trend_7d=scrap_trend_7d,
    )
