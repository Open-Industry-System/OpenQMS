"""ERP API routes."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.erp_deps import require_erp_api_key
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access, resolve_create_factory_id, validate_factory_invariant
from app.core.permissions import Module, PermissionLevel, get_user_permission
from app.database import get_db
from app.models.erp import (
    ERPConnection,
    ERPCostRecord,
    ERPCustomer,
    ERPInventoryBalance,
    ERPLocation,
    ERPMaterial,
    ERPPurchaseOrder,
    ERPSalesOrder,
    ERPShipment,
    ERPSupplier,
    ERPSyncJob,
)
from app.schemas import erp as schemas
from app.services.erp_connector import test_erp_connection
from app.services.erp_crypto import decrypt_credential, encrypt_credential, hash_api_key, sanitize_config
from app.services.erp_service import ERPIngestionService, ERPTraceabilityService

router = APIRouter(prefix="/api/erp", tags=["erp"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_factory_access(entity, scope: RequestScope):
    """Raise 404 if entity's factory_id is not in the user's accessible factories."""
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail="Connection not found")


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


def _process_credentials(config: dict) -> dict:
    auth_config = config.get("auth_config")
    if not auth_config:
        return config
    inbound_key = auth_config.get("inbound_api_key")
    if inbound_key:
        auth_config["api_key_hash"] = hash_api_key(inbound_key)
        auth_config.pop("inbound_api_key", None)
    # NOTE: username is NOT encrypted — needed in plaintext for Basic auth
    for field in ("outbound_api_key", "token", "password", "secret"):
        plaintext = auth_config.get(field)
        if plaintext:
            encrypted_field = f"{field}_encrypted"
            auth_config[encrypted_field] = encrypt_credential(plaintext)
            auth_config.pop(field, None)
    return config


def _mask_entity(entity, permission_level: int):
    """Apply field-level masking for viewer/QE roles on supplier/customer data.

    Mask when permission_level < 4 (APPROVE). Manager/admin or any role with
    level >= 4 sees full values. Uses resolved module-level permission, not
    role_key, so custom roles with ERP level 4/5 are correctly handled.
    """
    from copy import copy

    if permission_level >= 4:  # APPROVE or above
        return entity

    # Only mask ERPSupplier and ERPCustomer
    is_supplier = hasattr(entity, "bank_info")
    is_customer = hasattr(entity, "tax_id") and not is_supplier
    if not is_supplier and not is_customer:
        return entity

    masked = copy(entity)
    if is_supplier:
        if getattr(masked, "bank_info", None):
            masked.bank_info = "***"
        if getattr(masked, "tax_id", None):
            tid = masked.tax_id
            masked.tax_id = tid[:6] + "****" if len(tid) > 6 else "****"
    if is_customer:
        if getattr(masked, "tax_id", None):
            tid = masked.tax_id
            masked.tax_id = tid[:6] + "****" if len(tid) > 6 else "****"
    return masked


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

@router.post("/connections")
async def create_connection(
    data: schemas.ERPConnectionCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="权限不足")

    config = _validate_rest_config(data.connector_type, data.config)
    config = _process_credentials(config)

    factory_id = await resolve_create_factory_id(db, scope, product_line_code=data.product_line_code)
    check_factory_access(factory_id, scope)
    conn = ERPConnection(
        name=data.name,
        connector_type=data.connector_type,
        config=config,
        product_line_code=data.product_line_code,
        created_by=scope.user.user_id,
        factory_id=factory_id,
    )
    db.add(conn)
    await db.flush()

    await validate_factory_invariant(conn, db)

    # Create sync jobs for all 9 data types
    for data_type in ["suppliers", "customers", "materials", "locations",
                      "purchase_orders", "sales_orders", "inventory_balances",
                      "shipments", "cost_records"]:
        db.add(ERPSyncJob(connection_id=conn.connection_id, data_type=data_type, factory_id=conn.factory_id))

    await db.commit()
    out = schemas.ERPConnectionOut.model_validate(conn)
    out.config = sanitize_config(out.config)
    return out


@router.get("/connections")
async def list_connections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")

    query = select(ERPConnection)
    # Factory filtering
    if scope.effective_factory_id:
        query = query.where(ERPConnection.factory_id == scope.effective_factory_id)
    elif scope.factory_scope.accessible_factory_ids is not None:
        if scope.factory_scope.accessible_factory_ids:
            query = query.where(ERPConnection.factory_id.in_(scope.factory_scope.accessible_factory_ids))
        else:
            query = query.where(False)
    # Product line filtering
    if scope.pl_scope.mode == "NONE":
        return schemas.ERPConnectionListResponse(items=[], total=0, page=page, page_size=page_size)
    elif scope.pl_scope.mode == "EXPLICIT" and scope.pl_scope.codes:
        query = query.where(ERPConnection.product_line_code.in_(scope.pl_scope.codes))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = result.scalars().all()

    # Explicitly sanitize config for each item (defense-in-depth: schema
    # validator also runs, but explicit sanitize_config is belt-and-suspenders).
    sanitized_items = []
    for i in items:
        out = schemas.ERPConnectionOut.model_validate(i)
        out.config = sanitize_config(out.config)
        sanitized_items.append(out)

    return schemas.ERPConnectionListResponse(
        items=sanitized_items,
        total=total, page=page, page_size=page_size,
    )


@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")

    conn = await db.get(ERPConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    _check_factory_access(conn, scope)
    out = schemas.ERPConnectionOut.model_validate(conn)
    out.config = sanitize_config(out.config)
    return out


@router.put("/connections/{connection_id}")
async def update_connection(
    connection_id: uuid.UUID,
    data: schemas.ERPConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="权限不足")

    conn = await db.get(ERPConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    _check_factory_access(conn, scope)

    # Validate new product_line_code BEFORE applying changes
    if data.product_line_code is not None and data.product_line_code != conn.product_line_code:
        if scope.pl_scope.mode == "NONE" or scope.pl_scope.mode == "EXPLICIT" and data.product_line_code not in (scope.pl_scope.codes or []):
            raise HTTPException(status_code=403, detail="无权访问该产品线")

    if data.config is not None:
        data.config = _validate_rest_config(data.connector_type or conn.connector_type, data.config)
        data.config = _process_credentials(data.config)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(conn, field, value)

    await db.commit()
    out = schemas.ERPConnectionOut.model_validate(conn)
    out.config = sanitize_config(out.config)
    return out


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.ADMIN:
        raise HTTPException(status_code=403, detail="权限不足")

    conn = await db.get(ERPConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    _check_factory_access(conn, scope)
    await db.delete(conn)
    await db.commit()
    return {"message": "Deleted"}


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="权限不足")

    conn = await db.get(ERPConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    _check_factory_access(conn, scope)

    # Decrypt credentials for testing — use raw config, not sanitize_config
    test_config = dict(conn.config)
    auth_config = test_config.get("auth_config", {})
    if isinstance(auth_config, dict):
        for field in ("outbound_api_key", "token", "password", "secret"):
            encrypted = auth_config.get(f"{field}_encrypted")
            if encrypted:
                auth_config[field] = decrypt_credential(encrypted)

    return await test_erp_connection(conn.connector_type, test_config)


@router.post("/connections/{connection_id}/sync")
async def trigger_sync(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """Schedule a sync for this connection.

    Jobs are picked up by the background sync loop within ~60s.
    For synchronous execution in tests, call ERPSyncService.sync_all() directly.
    """
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="权限不足")

    conn = await db.get(ERPConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    _check_factory_access(conn, scope)
    if not conn.is_active:
        raise HTTPException(status_code=400, detail="Connection is inactive")

    # Reset all jobs to pending
    await db.execute(
        text("UPDATE erp_sync_jobs SET status = 'pending', next_run_at = NOW() WHERE connection_id = :conn_id")
        .bindparams(conn_id=str(connection_id))
    )
    await db.commit()
    return {"message": "Sync scheduled", "connection_id": str(connection_id)}


# ---------------------------------------------------------------------------
# Ingestion (API Key auth)
# ---------------------------------------------------------------------------

@router.post("/ingest")
async def ingest_data(
    data: schemas.ERPIngestRequest,
    db: AsyncSession = Depends(get_db),
    connection: ERPConnection = Depends(require_erp_api_key),
):
    if not connection.is_active:
        raise HTTPException(status_code=401, detail="Connection is inactive")
    try:
        result = await ERPIngestionService.ingest(db, {
            "data_type": data.data_type,
            "connection_id": str(connection.connection_id),
            "items": data.items,
        })
        await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise


# ---------------------------------------------------------------------------
# Data queries
# ---------------------------------------------------------------------------

async def _list_entities(
    db: AsyncSession, scope: RequestScope, model, out_schema,
    page: int, page_size: int,
    filters: dict = None,
):
    query = select(model)
    # Factory filtering
    if scope.effective_factory_id:
        query = query.where(model.factory_id == scope.effective_factory_id)
    elif scope.factory_scope.accessible_factory_ids is not None:
        if scope.factory_scope.accessible_factory_ids:
            query = query.where(model.factory_id.in_(scope.factory_scope.accessible_factory_ids))
        else:
            query = query.where(False)
    # Product line filtering
    if scope.pl_scope.mode == "NONE":
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    elif scope.pl_scope.mode == "EXPLICIT" and scope.pl_scope.codes:
        if hasattr(model, "product_line_code"):
            query = query.where(model.product_line_code.in_(scope.pl_scope.codes))

    if filters:
        for field, value in filters.items():
            if value:
                query = query.where(getattr(model, field) == value)
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = result.scalars().all()
    # Apply masking for supplier/customer responses
    perm_level = await get_user_permission(scope.user, Module.ERP, db)
    masked_items = [_mask_entity(i, perm_level.value) for i in items]
    return {
        "items": [out_schema.model_validate(m) for m in masked_items],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/suppliers")
async def list_suppliers(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    link_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    return await _list_entities(db, scope, ERPSupplier, schemas.SupplierOut, page, page_size,
                                {"link_status": link_status})


@router.get("/suppliers/{supplier_id}")
async def get_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")

    sup = await db.get(ERPSupplier, supplier_id)
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
    _check_factory_access(sup, scope)
    perm = await get_user_permission(scope.user, Module.ERP, db)
    return schemas.SupplierOut.model_validate(_mask_entity(sup, perm.value))


@router.post("/suppliers/{supplier_id}/link")
async def link_supplier(
    supplier_id: uuid.UUID,
    data: schemas.LinkSupplierRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="权限不足")

    sup = await db.get(ERPSupplier, supplier_id)
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
    _check_factory_access(sup, scope)
    sup.openqms_supplier_id = data.supplier_id
    sup.link_status = "linked"
    await db.commit()
    perm = await get_user_permission(scope.user, Module.ERP, db)
    return schemas.SupplierOut.model_validate(_mask_entity(sup, perm.value))


@router.post("/suppliers/{supplier_id}/unlink")
async def unlink_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="权限不足")

    sup = await db.get(ERPSupplier, supplier_id)
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
    _check_factory_access(sup, scope)
    sup.openqms_supplier_id = None
    sup.link_status = "unlinked"
    await db.commit()
    perm = await get_user_permission(scope.user, Module.ERP, db)
    return schemas.SupplierOut.model_validate(_mask_entity(sup, perm.value))


@router.get("/customers")
async def list_customers(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    link_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    return await _list_entities(db, scope, ERPCustomer, schemas.CustomerOut, page, page_size,
                                {"link_status": link_status})


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")

    cust = await db.get(ERPCustomer, customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    _check_factory_access(cust, scope)
    perm = await get_user_permission(scope.user, Module.ERP, db)
    return schemas.CustomerOut.model_validate(_mask_entity(cust, perm.value))


@router.post("/customers/{customer_id}/link")
async def link_customer(
    customer_id: uuid.UUID,
    data: schemas.LinkCustomerRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="权限不足")

    cust = await db.get(ERPCustomer, customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    _check_factory_access(cust, scope)
    cust.openqms_customer_id = data.customer_id
    cust.link_status = "linked"
    await db.commit()
    perm = await get_user_permission(scope.user, Module.ERP, db)
    return schemas.CustomerOut.model_validate(_mask_entity(cust, perm.value))


@router.post("/customers/{customer_id}/unlink")
async def unlink_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="权限不足")

    cust = await db.get(ERPCustomer, customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    _check_factory_access(cust, scope)
    cust.openqms_customer_id = None
    cust.link_status = "unlinked"
    await db.commit()
    perm = await get_user_permission(scope.user, Module.ERP, db)
    return schemas.CustomerOut.model_validate(_mask_entity(cust, perm.value))


@router.get("/materials")
async def list_materials(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    return await _list_entities(db, scope, ERPMaterial, schemas.MaterialOut, page, page_size)


@router.get("/locations")
async def list_locations(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    return await _list_entities(db, scope, ERPLocation, schemas.LocationOut, page, page_size)


@router.get("/purchase-orders")
async def list_purchase_orders(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    return await _list_entities(db, scope, ERPPurchaseOrder, schemas.PurchaseOrderOut, page, page_size)


@router.get("/sales-orders")
async def list_sales_orders(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    return await _list_entities(db, scope, ERPSalesOrder, schemas.SalesOrderOut, page, page_size)


@router.get("/inventory-balances")
async def list_inventory_balances(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    return await _list_entities(db, scope, ERPInventoryBalance, schemas.InventoryBalanceOut, page, page_size)


@router.get("/shipments")
async def list_shipments(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    return await _list_entities(db, scope, ERPShipment, schemas.ShipmentOut, page, page_size)


@router.get("/cost-records")
async def list_cost_records(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    return await _list_entities(db, scope, ERPCostRecord, schemas.CostRecordOut, page, page_size)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")

    kpis: list[schemas.DashboardKPI] = []

    # Build base filter for ERP-scoped queries
    factory_filter = None
    if scope.effective_factory_id:
        factory_filter = scope.effective_factory_id
    elif scope.factory_scope.accessible_factory_ids is not None:
        if not scope.factory_scope.accessible_factory_ids:
            # No factory access → return empty dashboard
            return schemas.ERPDashboardResponse(
                sync_health=[], coq_summary={}, pending_actions=[],
                inventory_alerts=[], shipment_risks=[], kpis=[],
            )

    # Connection count
    conn_query = select(func.count()).select_from(ERPConnection)
    if factory_filter:
        conn_query = conn_query.where(ERPConnection.factory_id == factory_filter)
    elif scope.factory_scope.accessible_factory_ids is not None:
        conn_query = conn_query.where(ERPConnection.factory_id.in_(scope.factory_scope.accessible_factory_ids))
    conn_total_result = await db.execute(conn_query)
    conn_total = conn_total_result.scalar() or 0

    conn_active_query = select(func.count()).select_from(ERPConnection).where(ERPConnection.is_active == True)
    if factory_filter:
        conn_active_query = conn_active_query.where(ERPConnection.factory_id == factory_filter)
    elif scope.factory_scope.accessible_factory_ids is not None:
        conn_active_query = conn_active_query.where(ERPConnection.factory_id.in_(scope.factory_scope.accessible_factory_ids))
    conn_active_result = await db.execute(conn_active_query)
    conn_active = conn_active_result.scalar() or 0
    kpis.append(schemas.DashboardKPI(
        label="活跃连接", value=f"{conn_active}/{conn_total}",
        status="success" if conn_active > 0 else "error",
    ))

    # Sync job status (last success/failure)
    sync_query = select(func.count()).select_from(ERPSyncJob)
    if factory_filter:
        sync_query = sync_query.where(ERPSyncJob.factory_id == factory_filter)
    elif scope.factory_scope.accessible_factory_ids is not None:
        sync_query = sync_query.where(ERPSyncJob.factory_id.in_(scope.factory_scope.accessible_factory_ids))
    sync_total_result = await db.execute(sync_query)
    _sync_total = sync_total_result.scalar() or 0  # noqa: F841

    sync_success_query = select(func.count()).select_from(ERPSyncJob).where(ERPSyncJob.status == "completed")
    if factory_filter:
        sync_success_query = sync_success_query.where(ERPSyncJob.factory_id == factory_filter)
    elif scope.factory_scope.accessible_factory_ids is not None:
        sync_success_query = sync_success_query.where(ERPSyncJob.factory_id.in_(scope.factory_scope.accessible_factory_ids))
    sync_success_result = await db.execute(sync_success_query)
    sync_success = sync_success_result.scalar() or 0

    sync_failed_query = select(func.count()).select_from(ERPSyncJob).where(ERPSyncJob.status == "failed")
    if factory_filter:
        sync_failed_query = sync_failed_query.where(ERPSyncJob.factory_id == factory_filter)
    elif scope.factory_scope.accessible_factory_ids is not None:
        sync_failed_query = sync_failed_query.where(ERPSyncJob.factory_id.in_(scope.factory_scope.accessible_factory_ids))
    sync_failed_result = await db.execute(sync_failed_query)
    sync_failed = sync_failed_result.scalar() or 0
    kpis.append(schemas.DashboardKPI(
        label="同步状态",
        value=f"{sync_success} 成功 / {sync_failed} 失败",
        status="error" if sync_failed > 0 else "success" if sync_success > 0 else "warning",
    ))

    # Supplier/customer link rates
    sup_query_base = select(func.count()).select_from(ERPSupplier)
    if factory_filter:
        sup_query_base = sup_query_base.where(ERPSupplier.factory_id == factory_filter)
    elif scope.factory_scope.accessible_factory_ids is not None:
        sup_query_base = sup_query_base.where(ERPSupplier.factory_id.in_(scope.factory_scope.accessible_factory_ids))

    sup_linked_result = await db.execute(
        sup_query_base.where(ERPSupplier.link_status == "linked")
    )
    sup_linked = sup_linked_result.scalar() or 0
    sup_total_result = await db.execute(sup_query_base)
    sup_total = sup_total_result.scalar() or 0
    kpis.append(schemas.DashboardKPI(
        label="供应商关联率",
        value=f"{sup_linked}/{sup_total}",
        status="success" if sup_total == 0 or sup_linked / sup_total >= 0.5 else "warning",
    ))

    cust_query_base = select(func.count()).select_from(ERPCustomer)
    if factory_filter:
        cust_query_base = cust_query_base.where(ERPCustomer.factory_id == factory_filter)
    elif scope.factory_scope.accessible_factory_ids is not None:
        cust_query_base = cust_query_base.where(ERPCustomer.factory_id.in_(scope.factory_scope.accessible_factory_ids))

    cust_linked_result = await db.execute(
        cust_query_base.where(ERPCustomer.link_status == "linked")
    )
    cust_linked = cust_linked_result.scalar() or 0
    cust_total_result = await db.execute(cust_query_base)
    cust_total = cust_total_result.scalar() or 0
    kpis.append(schemas.DashboardKPI(
        label="客户关联率",
        value=f"{cust_linked}/{cust_total}",
        status="success" if cust_total == 0 or cust_linked / cust_total >= 0.5 else "warning",
    ))

    # COQ total
    coq_query = select(func.coalesce(func.sum(ERPCostRecord.amount), 0))
    if factory_filter:
        coq_query = coq_query.where(ERPCostRecord.factory_id == factory_filter)
    elif scope.factory_scope.accessible_factory_ids is not None:
        coq_query = coq_query.where(ERPCostRecord.factory_id.in_(scope.factory_scope.accessible_factory_ids))
    coq_total_result = await db.execute(coq_query)
    coq_total = float(coq_total_result.scalar() or 0)
    kpis.append(schemas.DashboardKPI(
        label="质量成本总计",
        value=f"¥{coq_total:,.2f}",
        status="warning" if coq_total > 0 else "success",
    ))

    # Sync health (for detailed view)
    sync_health_query = select(ERPSyncJob.data_type, ERPSyncJob.status, ERPSyncJob.completed_at)
    if factory_filter:
        sync_health_query = sync_health_query.where(ERPSyncJob.factory_id == factory_filter)
    elif scope.factory_scope.accessible_factory_ids is not None:
        sync_health_query = sync_health_query.where(ERPSyncJob.factory_id.in_(scope.factory_scope.accessible_factory_ids))
    sync_result = await db.execute(sync_health_query)
    sync_health = [{"data_type": r[0], "status": r[1], "last_sync": r[2]} for r in sync_result.all()]

    # COQ summary
    coq_where = "cost_date >= DATE_TRUNC('month', NOW())"
    coq_params: dict = {}
    if factory_filter:
        coq_where += " AND factory_id = :factory_id"
        coq_params["factory_id"] = str(factory_filter)
    elif scope.factory_scope.accessible_factory_ids is not None and scope.factory_scope.accessible_factory_ids:
        placeholders = ",".join(f":fid{i}" for i in range(len(scope.factory_scope.accessible_factory_ids)))
        for i, fid in enumerate(scope.factory_scope.accessible_factory_ids):
            coq_params[f"fid{i}"] = str(fid)
        coq_where += f" AND factory_id IN ({placeholders})"
    coq_result = await db.execute(
        text(f"SELECT cost_category, SUM(amount) as total FROM erp_cost_records WHERE {coq_where} GROUP BY cost_category"),
        coq_params,
    )
    coq_summary = {r[0]: float(r[1]) for r in coq_result.all()}

    return schemas.ERPDashboardResponse(
        sync_health=sync_health,
        coq_summary=coq_summary,
        pending_actions=[],
        inventory_alerts=[],
        shipment_risks=[],
        kpis=kpis,
    )


# ---------------------------------------------------------------------------
# Traceability
# ---------------------------------------------------------------------------

@router.get("/traceability")
async def query_traceability(
    lot_no: str,
    direction: str = Query("forward", pattern=r"^(forward|backward)$"),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.ERP, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="权限不足")
    return await ERPTraceabilityService.query(db, lot_no, direction)