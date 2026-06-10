"""ERP API routes."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select, func, and_, text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_current_user, require_permission, get_user_permission, Module, PermissionLevel
from app.core.product_line_filter import (
    apply_product_line_filter,
    enforce_product_line_access,
    get_user_product_line_codes,
)
from app.models.user import User
from app.models.erp import (
    ERPConnection, ERPSyncJob, ERPSupplier, ERPCustomer,
    ERPMaterial, ERPLocation, ERPPurchaseOrder, ERPSalesOrder,
    ERPInventoryBalance, ERPShipment, ERPCostRecord,
)
from app.schemas import erp as schemas
from app.services.erp_service import ERPIngestionService, ERPSyncService, ERPTraceabilityService
from app.services.erp_connector import test_erp_connection, get_erp_connector, get_erp_connector_by_config
from app.services.erp_crypto import hash_api_key, encrypt_credential, sanitize_config
from app.api.erp_deps import require_erp_api_key

router = APIRouter(prefix="/api/erp", tags=["erp"])


# ---------------------------------------------------------------------------
# Helpers
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


def _process_credentials(config: dict) -> dict:
    auth_config = config.get("auth_config")
    if not auth_config:
        return config
    inbound_key = auth_config.get("inbound_api_key")
    if inbound_key:
        auth_config["api_key_hash"] = hash_api_key(inbound_key)
        auth_config.pop("inbound_api_key", None)
    for field in ("outbound_api_key", "token", "password", "secret", "username"):
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
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.APPROVE)),
):
    config = _validate_rest_config(data.connector_type, data.config)
    config = _process_credentials(config)

    conn = ERPConnection(
        name=data.name,
        connector_type=data.connector_type,
        config=config,
        product_line_code=data.product_line_code,
        created_by=user.user_id,
    )
    db.add(conn)
    await db.flush()

    # Create sync jobs for all 9 data types
    for data_type in ["suppliers", "customers", "materials", "locations",
                      "purchase_orders", "sales_orders", "inventory_balances",
                      "shipments", "cost_records"]:
        db.add(ERPSyncJob(connection_id=conn.connection_id, data_type=data_type))

    await db.commit()
    return schemas.ERPConnectionOut.model_validate(conn)


@router.get("/connections")
async def list_connections(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    query = await apply_product_line_filter(select(ERPConnection), user, ERPConnection, "erp", db, request)
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = result.scalars().all()

    return schemas.ERPConnectionListResponse(
        items=[schemas.ERPConnectionOut.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    conn = await db.get(ERPConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await enforce_product_line_access(user, conn.product_line_code, db)
    out = schemas.ERPConnectionOut.model_validate(conn)
    out.config = sanitize_config(out.config)
    return out


@router.put("/connections/{connection_id}")
async def update_connection(
    connection_id: uuid.UUID,
    data: schemas.ERPConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.APPROVE)),
):
    conn = await db.get(ERPConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if data.config is not None:
        data.config = _validate_rest_config(data.connector_type or conn.connector_type, data.config)
        data.config = _process_credentials(data.config)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(conn, field, value)
    await db.commit()
    return schemas.ERPConnectionOut.model_validate(conn)


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.ADMIN)),
):
    conn = await db.get(ERPConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)
    await db.commit()
    return {"message": "Deleted"}


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.APPROVE)),
):
    conn = await db.get(ERPConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return test_erp_connection(conn.connector_type, sanitize_config(conn.config))


@router.post("/connections/{connection_id}/sync")
async def trigger_sync(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.APPROVE)),
):
    """Schedule a sync for this connection.

    Jobs are picked up by the background sync loop within ~60s.
    For synchronous execution in tests, call ERPSyncService.sync_all() directly.
    """
    conn = await db.get(ERPConnection, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
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
    db: AsyncSession, user: User, request: Request, model, out_schema,
    page: int, page_size: int,
    filters: dict = None,
):
    query = select(model)
    query = await apply_product_line_filter(query, user, model, "erp", db, request)
    if filters:
        for field, value in filters.items():
            if value:
                query = query.where(getattr(model, field) == value)
    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar()
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = result.scalars().all()
    # Apply masking for supplier/customer responses
    perm_level = await get_user_permission(user, Module.ERP, db)
    masked_items = [_mask_entity(i, perm_level.value) for i in items]
    return {
        "items": [out_schema.model_validate(m) for m in masked_items],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/suppliers")
async def list_suppliers(
    request: Request,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    link_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    return await _list_entities(db, user, request, ERPSupplier, schemas.SupplierOut, page, page_size,
                                {"link_status": link_status})


@router.get("/suppliers/{supplier_id}")
async def get_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    sup = await db.get(ERPSupplier, supplier_id)
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
    await enforce_product_line_access(user, sup.product_line_code, db)
    perm = await get_user_permission(user, Module.ERP, db)
    return schemas.SupplierOut.model_validate(_mask_entity(sup, perm.value))


@router.post("/suppliers/{supplier_id}/link")
async def link_supplier(
    supplier_id: uuid.UUID,
    data: schemas.LinkSupplierRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.EDIT)),
):
    sup = await db.get(ERPSupplier, supplier_id)
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
    sup.openqms_supplier_id = data.supplier_id
    sup.link_status = "linked"
    await db.commit()
    perm = await get_user_permission(user, Module.ERP, db)
    return schemas.SupplierOut.model_validate(_mask_entity(sup, perm.value))


@router.post("/suppliers/{supplier_id}/unlink")
async def unlink_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.EDIT)),
):
    sup = await db.get(ERPSupplier, supplier_id)
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")
    sup.openqms_supplier_id = None
    sup.link_status = "unlinked"
    await db.commit()
    perm = await get_user_permission(user, Module.ERP, db)
    return schemas.SupplierOut.model_validate(_mask_entity(sup, perm.value))


@router.get("/customers")
async def list_customers(
    request: Request,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    link_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    return await _list_entities(db, user, request, ERPCustomer, schemas.CustomerOut, page, page_size,
                                {"link_status": link_status})


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    cust = await db.get(ERPCustomer, customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    await enforce_product_line_access(user, cust.product_line_code, db)
    perm = await get_user_permission(user, Module.ERP, db)
    return schemas.CustomerOut.model_validate(_mask_entity(cust, perm.value))


@router.post("/customers/{customer_id}/link")
async def link_customer(
    customer_id: uuid.UUID,
    data: schemas.LinkCustomerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.EDIT)),
):
    cust = await db.get(ERPCustomer, customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    cust.openqms_customer_id = data.customer_id
    cust.link_status = "linked"
    await db.commit()
    perm = await get_user_permission(user, Module.ERP, db)
    return schemas.CustomerOut.model_validate(_mask_entity(cust, perm.value))


@router.post("/customers/{customer_id}/unlink")
async def unlink_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.EDIT)),
):
    cust = await db.get(ERPCustomer, customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    cust.openqms_customer_id = None
    cust.link_status = "unlinked"
    await db.commit()
    perm = await get_user_permission(user, Module.ERP, db)
    return schemas.CustomerOut.model_validate(_mask_entity(cust, perm.value))


@router.get("/materials")
async def list_materials(
    request: Request,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    return await _list_entities(db, user, request, ERPMaterial, schemas.MaterialOut, page, page_size)


@router.get("/locations")
async def list_locations(
    request: Request,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    return await _list_entities(db, user, request, ERPLocation, schemas.LocationOut, page, page_size)


@router.get("/purchase-orders")
async def list_purchase_orders(
    request: Request,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    return await _list_entities(db, user, request, ERPPurchaseOrder, schemas.PurchaseOrderOut, page, page_size)


@router.get("/sales-orders")
async def list_sales_orders(
    request: Request,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    return await _list_entities(db, user, request, ERPSalesOrder, schemas.SalesOrderOut, page, page_size)


@router.get("/inventory-balances")
async def list_inventory_balances(
    request: Request,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    return await _list_entities(db, user, request, ERPInventoryBalance, schemas.InventoryBalanceOut, page, page_size)


@router.get("/shipments")
async def list_shipments(
    request: Request,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    return await _list_entities(db, user, request, ERPShipment, schemas.ShipmentOut, page, page_size)


@router.get("/cost-records")
async def list_cost_records(
    request: Request,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    return await _list_entities(db, user, request, ERPCostRecord, schemas.CostRecordOut, page, page_size)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    # Sync health
    sync_result = await db.execute(select(ERPSyncJob.data_type, ERPSyncJob.status, ERPSyncJob.completed_at))
    sync_health = [{"data_type": r[0], "status": r[1], "last_sync": r[2]} for r in sync_result.all()]

    # COQ summary
    coq_result = await db.execute(
        text("""
            SELECT cost_category, SUM(amount) as total
            FROM erp_cost_records
            WHERE cost_date >= DATE_TRUNC('month', NOW())
            GROUP BY cost_category
        """)
    )
    coq_summary = {r[0]: float(r[1]) for r in coq_result.all()}

    return schemas.ERPDashboardResponse(
        sync_health=sync_health,
        coq_summary=coq_summary,
        pending_actions=[],
        inventory_alerts=[],
        shipment_risks=[],
        kpis=[],
    )


# ---------------------------------------------------------------------------
# Traceability
# ---------------------------------------------------------------------------

@router.get("/traceability")
async def query_traceability(
    lot_no: str,
    direction: str = Query("forward", pattern=r"^(forward|backward)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.ERP, PermissionLevel.VIEW)),
):
    return await ERPTraceabilityService.query(db, lot_no, direction)