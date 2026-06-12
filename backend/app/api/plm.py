"""PLM API routes — connections, parts, BOMs, change orders, dashboard."""

import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.core.permissions import (
    Module,
    PermissionLevel,
    get_user_permission,
)
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import populate_factory_id, validate_factory_invariant
from app.models.fmea import FMEADocument
from app.models.plm import (
    PLMBOM,
    PLMChangeImpactTask,
    PLMChangeOrder,
    PLMConnection,
    PLMPart,
    PLMPartFMEALink,
    PLMPartSCLink,
)
from app.schemas import plm as schemas
from app.schemas import special_characteristic as schemas_special_characteristic
from app.services.fmea_service import get_fmea
from app.services.plm_service import PLMSyncService
from app.services.plm_connector import test_plm_connection
from app.services.special_characteristic_service import (
    SafetyApprovalStatus,
    prepare_special_characteristic,
)

router = APIRouter(prefix="/api/plm", tags=["plm"])


IMPLEMENTED_CONNECTOR_TYPES = {"mock"}


def _ensure_connector_type_implemented(connector_type: str) -> None:
    if connector_type not in IMPLEMENTED_CONNECTOR_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"PLM connector type '{connector_type}' is not implemented",
        )


async def _resolve_change_order_product_line(
    db: AsyncSession,
    change_order: PLMChangeOrder,
) -> str | None:
    if change_order.product_line_code is not None:
        return change_order.product_line_code
    conn_result = await db.execute(
        select(PLMConnection.product_line_code).where(
            PLMConnection.connection_id == change_order.connection_id
        )
    )
    return conn_result.scalar_one_or_none()


def _check_factory_access(entity, scope: RequestScope, detail: str = "PLM connection not found"):
    if not hasattr(entity, "factory_id") or entity.factory_id is None:
        return
    if scope.effective_factory_id and entity.factory_id != scope.effective_factory_id:
        raise HTTPException(status_code=404, detail=detail)
    if scope.factory_scope.accessible_factory_ids is not None:
        if entity.factory_id not in scope.factory_scope.accessible_factory_ids:
            raise HTTPException(status_code=404, detail=detail)


def _apply_scope_filter(query, scope: RequestScope, model, pl_column: str = "product_line_code"):
    """Apply factory + product line filtering to a query based on scope."""
    if scope.pl_scope.mode == "NONE":
        return query.where(False)
    if scope.effective_factory_id:
        query = query.where(model.factory_id == scope.effective_factory_id)
    elif scope.factory_scope.accessible_factory_ids is not None:
        if scope.factory_scope.accessible_factory_ids:
            query = query.where(model.factory_id.in_(scope.factory_scope.accessible_factory_ids))
        else:
            query = query.where(False)
    if scope.pl_scope.mode == "EXPLICIT":
        query = query.where(getattr(model, pl_column).in_(scope.pl_scope.codes))
    return query


def _plm_part_response(
    part: PLMPart,
    sc_links: list[PLMPartSCLink],
) -> schemas.PLMPartResponse:
    return schemas.PLMPartResponse.model_validate(
        {
            "part_id": part.part_id,
            "connection_id": part.connection_id,
            "external_id": part.external_id,
            "part_number": part.part_number,
            "name": part.name,
            "revision": part.revision,
            "material": part.material,
            "specification": part.specification,
            "status": part.status,
            "is_safety_related": part.is_safety_related,
            "is_key_characteristic": part.is_key_characteristic,
            "source_updated_at": part.source_updated_at,
            "product_line_code": part.product_line_code,
            "plm_raw_data": part.plm_raw_data,
            "sc_links": [
                schemas.PLMPartSCLinkResponse.model_validate(link)
                for link in sc_links
            ],
        }
    )


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


@router.post("/connections", response_model=schemas.PLMConnectionResponse, status_code=201)
async def create_connection(
    req: schemas.PLMConnectionCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """Create a PLM connection. User must have access to the target product line."""
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 CREATE 权限")
    _ensure_connector_type_implemented(req.connector_type)
    # Enforce product line access
    if scope.pl_scope.mode == "NONE":
        raise HTTPException(status_code=403, detail="无权访问该产品线")
    if scope.pl_scope.mode == "EXPLICIT" and req.product_line_code not in scope.pl_scope.codes:
        raise HTTPException(status_code=403, detail="无权访问该产品线")

    conn = PLMConnection(
        name=req.name,
        connector_type=req.connector_type,
        config=req.config,
        product_line_code=req.product_line_code,
        created_by=scope.user.user_id,
    )
    db.add(conn)
    await db.flush()
    await populate_factory_id(conn, PLMConnection, db, scope=scope)
    await validate_factory_invariant(conn, db)
    await PLMSyncService.create_sync_jobs_for_connection(db, conn.connection_id)
    await db.commit()
    await db.refresh(conn)
    return schemas.PLMConnectionResponse.model_validate(conn)


@router.get("/connections", response_model=schemas.PLMConnectionListResponse)
async def list_connections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 VIEW 权限")

    query = select(PLMConnection)
    query = _apply_scope_filter(query, scope, PLMConnection)

    count_query = select(func.count()).select_from(PLMConnection)
    count_query = _apply_scope_filter(count_query, scope, PLMConnection)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(PLMConnection.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()

    return schemas.PLMConnectionListResponse(
        items=[schemas.PLMConnectionResponse.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/connections/{connection_id}", response_model=schemas.PLMConnectionResponse)
async def get_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 VIEW 权限")
    result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    _check_factory_access(conn, scope, detail="PLM connection not found")
    return schemas.PLMConnectionResponse.model_validate(conn)


@router.put("/connections/{connection_id}", response_model=schemas.PLMConnectionResponse)
async def update_connection(
    connection_id: uuid.UUID,
    req: schemas.PLMConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 EDIT 权限")
    result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    _check_factory_access(conn, scope, detail="PLM connection not found")

    data = req.model_dump(exclude_unset=True)
    if "connector_type" in data:
        _ensure_connector_type_implemented(data["connector_type"])

    # If changing product_line_code, verify access to new value
    new_plc = data.get("product_line_code")
    if new_plc and new_plc != conn.product_line_code:
        if scope.pl_scope.mode == "NONE":
            raise HTTPException(status_code=403, detail="无权访问该产品线")
        if scope.pl_scope.mode == "EXPLICIT" and new_plc not in scope.pl_scope.codes:
            raise HTTPException(status_code=403, detail="无权访问该产品线")

    for field, value in data.items():
        setattr(conn, field, value)

    await db.commit()
    await db.refresh(conn)
    return schemas.PLMConnectionResponse.model_validate(conn)


@router.delete("/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.ADMIN:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 ADMIN 权限")
    result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    _check_factory_access(conn, scope, detail="PLM connection not found")

    await db.delete(conn)
    await db.commit()


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 EDIT 权限")
    result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    _check_factory_access(conn, scope, detail="PLM connection not found")

    return await test_plm_connection(conn, db)


@router.post("/connections/{connection_id}/sync")
async def manual_sync(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 EDIT 权限")
    result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    _check_factory_access(conn, scope, detail="PLM connection not found")

    count = await PLMSyncService.manual_sync(db, connection_id)
    return {"synced_jobs": count}


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------


@router.get("/parts")
async def list_parts(
    connection_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 VIEW 权限")

    if scope.pl_scope.mode == "NONE":
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
        }

    query = select(PLMPart)
    if connection_id:
        query = query.where(PLMPart.connection_id == connection_id)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            PLMPart.part_number.ilike(pattern) | PLMPart.name.ilike(pattern)
        )

    query = _apply_scope_filter(query, scope, PLMPart)

    count_query = select(func.count()).select_from(PLMPart)
    if connection_id:
        count_query = count_query.where(PLMPart.connection_id == connection_id)
    if search:
        pattern = f"%{search}%"
        count_query = count_query.where(
            PLMPart.part_number.ilike(pattern) | PLMPart.name.ilike(pattern)
        )
    count_query = _apply_scope_filter(count_query, scope, PLMPart)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(PLMPart.part_number).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()

    part_list = list(items)
    if not part_list:
        return {
            "items": [],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    part_ids = [part.part_id for part in part_list]
    links_result = await db.execute(
        select(PLMPartSCLink)
        .where(PLMPartSCLink.part_id.in_(part_ids))
        .order_by(PLMPartSCLink.created_at.asc())
    )
    links = links_result.scalars().all()
    links_by_part: dict[uuid.UUID, list[PLMPartSCLink]] = defaultdict(list)
    for link in links:
        links_by_part[link.part_id].append(link)

    return {
        "items": [
            _plm_part_response(part, links_by_part.get(part.part_id, []))
            for part in part_list
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/parts/{part_id}", response_model=schemas.PLMPartResponse)
async def get_part(
    part_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 VIEW 权限")
    result = await db.execute(select(PLMPart).where(PLMPart.part_id == part_id))
    part = result.scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")
    _check_factory_access(part, scope, detail="Part not found")
    links_result = await db.execute(
        select(PLMPartSCLink).where(PLMPartSCLink.part_id == part.part_id)
    )
    links = links_result.scalars().all()
    return _plm_part_response(part, list(links))


# ---------------------------------------------------------------------------
# BOMs
# ---------------------------------------------------------------------------


@router.get("/boms")
async def list_boms(
    connection_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 VIEW 权限")

    if scope.pl_scope.mode == "NONE":
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
        }

    query = select(PLMBOM)
    if connection_id:
        query = query.where(PLMBOM.connection_id == connection_id)

    query = _apply_scope_filter(query, scope, PLMBOM)

    count_query = select(func.count()).select_from(PLMBOM)
    if connection_id:
        count_query = count_query.where(PLMBOM.connection_id == connection_id)
    count_query = _apply_scope_filter(count_query, scope, PLMBOM)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()

    return {
        "items": [schemas.PLMBOMResponse.model_validate(b) for b in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/connections/{connection_id}/boms/tree/{part_number}")
async def get_bom_tree(
    connection_id: uuid.UUID,
    part_number: str,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    revision: str = Query("A"),
    bom_revision: str = Query("A"),
):
    """Multi-level BOM tree via BFS starting from part_number."""
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 VIEW 权限")

    # Verify connection exists and user has access
    conn_result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    _check_factory_access(conn, scope, detail="PLM connection not found")

    # Fetch all BOM rows for this connection
    bom_result = await db.execute(
        select(PLMBOM).where(
            PLMBOM.connection_id == connection_id,
            PLMBOM.bom_revision == bom_revision,
        )
    )
    all_boms = [
        bom for bom in bom_result.scalars().all()
        if bom.bom_revision == bom_revision
    ]

    # Build adjacency: (parent_part_number, parent_revision) -> children
    children_map: dict[tuple[str, str], list[PLMBOM]] = defaultdict(list)
    all_part_keys: set[tuple[str, str]] = set()
    for bom in all_boms:
        parent_key = (bom.parent_part_number, bom.parent_revision)
        child_key = (bom.child_part_number, bom.child_revision)
        children_map[parent_key].append(bom)
        all_part_keys.add(parent_key)
        all_part_keys.add(child_key)

    # Validate root part exists in BOM tree
    root_key = (part_number, revision)
    if root_key not in all_part_keys:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Part '{part_number}' revision '{revision}' not found in "
                f"BOM revision '{bom_revision}' for this connection"
            ),
        )

    # Multi-level BFS
    visited: set[tuple[str, str]] = set()
    queue: deque[tuple[str, str]] = deque([root_key])
    tree: list[dict] = []

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        for bom in children_map.get(current, []):
            child_key = (bom.child_part_number, bom.child_revision)
            tree.append({
                "parent_part_number": bom.parent_part_number,
                "parent_revision": bom.parent_revision,
                "child_part_number": bom.child_part_number,
                "child_revision": bom.child_revision,
                "quantity": float(bom.quantity),
                "level": bom.level,
                "bom_revision": bom.bom_revision,
            })
            if child_key not in visited:
                queue.append(child_key)

    return {
        "root": part_number,
        "revision": revision,
        "bom_revision": bom_revision,
        "items": tree,
        "total": len(tree),
    }


# ---------------------------------------------------------------------------
# Change orders
# ---------------------------------------------------------------------------


@router.get("/change-orders")
async def list_change_orders(
    connection_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 VIEW 权限")

    if scope.pl_scope.mode == "NONE":
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
        }

    query = select(PLMChangeOrder)
    if connection_id:
        query = query.where(PLMChangeOrder.connection_id == connection_id)

    query = _apply_scope_filter(query, scope, PLMChangeOrder)

    count_query = select(func.count()).select_from(PLMChangeOrder)
    if connection_id:
        count_query = count_query.where(PLMChangeOrder.connection_id == connection_id)
    count_query = _apply_scope_filter(count_query, scope, PLMChangeOrder)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(PLMChangeOrder.change_number.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()

    return {
        "items": [schemas.PLMChangeOrderResponse.model_validate(c) for c in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/change-orders/{change_id}", response_model=schemas.PLMChangeOrderResponse)
async def get_change_order(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 VIEW 权限")
    result = await db.execute(
        select(PLMChangeOrder).where(PLMChangeOrder.change_id == change_id)
    )
    co = result.scalar_one_or_none()
    if co is None:
        raise HTTPException(status_code=404, detail="Change order not found")
    _check_factory_access(co, scope, detail="Change order not found")
    return schemas.PLMChangeOrderResponse.model_validate(co)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=schemas.PLMDashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """Dashboard with factory + product-line-filtered counts."""
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 VIEW 权限")

    if scope.pl_scope.mode == "NONE":
        return schemas.PLMDashboardResponse(
            part_count=0,
            bom_count=0,
            pending_ecn_count=0,
            pending_sc_count=0,
            recent_changes=[],
        )

    # Parts count
    parts_q = select(func.count()).select_from(PLMPart)
    parts_q = _apply_scope_filter(parts_q, scope, PLMPart)
    part_count = (await db.execute(parts_q)).scalar() or 0

    # BOM count
    boms_q = select(func.count()).select_from(PLMBOM)
    boms_q = _apply_scope_filter(boms_q, scope, PLMBOM)
    bom_count = (await db.execute(boms_q)).scalar() or 0

    # Pending ECN count
    ecn_q = select(func.count()).select_from(PLMChangeOrder).where(
        PLMChangeOrder.status.in_(["draft", "pending", "approved"])
    )
    ecn_q = _apply_scope_filter(ecn_q, scope, PLMChangeOrder)
    pending_ecn_count = (await db.execute(ecn_q)).scalar() or 0

    # Pending SC count (from PLMPartSCLink)
    sc_q = select(func.count()).select_from(PLMPartSCLink).where(
        PLMPartSCLink.status == "pending"
    )
    # Factory filter on SC links
    if scope.effective_factory_id:
        sc_q = sc_q.where(PLMPartSCLink.factory_id == scope.effective_factory_id)
    elif scope.factory_scope.accessible_factory_ids is not None:
        if scope.factory_scope.accessible_factory_ids:
            sc_q = sc_q.where(PLMPartSCLink.factory_id.in_(scope.factory_scope.accessible_factory_ids))
        else:
            sc_q = sc_q.where(False)
    # Product line filter on SC links
    if scope.pl_scope.mode == "EXPLICIT":
        sc_q = sc_q.where(PLMPartSCLink.product_line_code.in_(scope.pl_scope.codes))
    pending_sc_count = (await db.execute(sc_q)).scalar() or 0

    # Recent changes (last 10)
    recent_q = select(PLMChangeOrder).order_by(
        PLMChangeOrder.change_number.desc()
    ).limit(10)
    recent_q = _apply_scope_filter(recent_q, scope, PLMChangeOrder)
    recent_items = (await db.execute(recent_q)).scalars().all()

    return schemas.PLMDashboardResponse(
        part_count=part_count,
        bom_count=bom_count,
        pending_ecn_count=pending_ecn_count,
        pending_sc_count=pending_sc_count,
        recent_changes=[schemas.PLMChangeOrderResponse.model_validate(c) for c in recent_items],
    )


# ---------------------------------------------------------------------------
# Link part to FMEA
# ---------------------------------------------------------------------------


@router.post("/parts/{part_id}/link-fmea")
async def link_part_to_fmea(
    part_id: uuid.UUID,
    req: schemas.PLMPartLinkFMEARequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """Link a PLM part to an FMEA node. Both must share the same product line."""
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 EDIT 权限")

    if len(req.node_id) > _MAX_NODE_ID_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"node_id 长度不能超过 {_MAX_NODE_ID_LENGTH}",
        )

    # Fetch part
    part_result = await db.execute(select(PLMPart).where(PLMPart.part_id == part_id))
    part = part_result.scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")
    _check_factory_access(part, scope, detail="Part not found")

    # Resolve part product line
    part_plc = part.product_line_code
    if part_plc is None:
        conn_r = await db.execute(
            select(PLMConnection.product_line_code).where(
                PLMConnection.connection_id == part.connection_id
            )
        )
        part_plc = conn_r.scalar_one_or_none()
    # Enforce PL access on part
    if scope.pl_scope.mode == "NONE":
        raise HTTPException(status_code=403, detail="无权访问该产品线")
    if scope.pl_scope.mode == "EXPLICIT" and part_plc and part_plc not in scope.pl_scope.codes:
        raise HTTPException(status_code=403, detail="无权访问该产品线")

    # Fetch FMEA
    fmea = await get_fmea(db, req.fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    _check_factory_access(fmea, scope, detail="FMEA not found")

    # Enforce PL access on FMEA
    if scope.pl_scope.mode == "EXPLICIT" and fmea.product_line_code and fmea.product_line_code not in scope.pl_scope.codes:
        raise HTTPException(status_code=403, detail="无权访问该产品线")

    # Product line match check
    if part_plc and fmea.product_line_code and part_plc != fmea.product_line_code:
        raise HTTPException(
            status_code=400,
            detail=f"Product line mismatch: part '{part_plc}' vs FMEA '{fmea.product_line_code}'",
        )

    graph = fmea.graph_data if isinstance(fmea.graph_data, dict) else {}
    graph_nodes = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
    if not any(isinstance(node, dict) and node.get("id") == req.node_id for node in graph_nodes):
        raise HTTPException(status_code=400, detail="目标 FMEA 节点不存在")

    stmt = (
        pg_insert(PLMPartFMEALink)
        .values(
            link_id=uuid.uuid4(),
            part_id=part.part_id,
            fmea_id=req.fmea_id,
            node_id=req.node_id,
            link_type="manual",
        )
        .on_conflict_do_update(
            index_elements=["part_id", "fmea_id", "node_id"],
            set_={"link_type": "manual"},
        )
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "linked"}


_MAX_NODE_ID_LENGTH = 128
_VALID_FMEA_TYPES = {"DFMEA", "PFMEA"}


@router.post(
    "/parts/{part_id}/confirm-sc",
    response_model=schemas.PLMPartConfirmSCResponse,
)
async def confirm_part_sc(
    part_id: uuid.UUID,
    req: schemas.PLMPartConfirmSCRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 EDIT 权限")
    sc_level = await get_user_permission(scope.user, Module.SPECIAL_CHARACTERISTIC, db)
    if sc_level < PermissionLevel.CREATE:
        raise HTTPException(status_code=403, detail="需要 special_characteristic 模块的 CREATE 权限")

    if len(req.node_id) > _MAX_NODE_ID_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"node_id 长度不能超过 {_MAX_NODE_ID_LENGTH}",
        )

    part_result = await db.execute(select(PLMPart).where(PLMPart.part_id == part_id))
    part = part_result.scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")
    _check_factory_access(part, scope, detail="Part not found")

    part_plc = part.product_line_code
    if part_plc is None:
        conn_result = await db.execute(
            select(PLMConnection.product_line_code).where(
                PLMConnection.connection_id == part.connection_id
            )
        )
        part_plc = conn_result.scalar_one_or_none()
    # Enforce PL access on part
    if scope.pl_scope.mode == "NONE":
        raise HTTPException(status_code=403, detail="无权访问该产品线")
    if scope.pl_scope.mode == "EXPLICIT" and part_plc and part_plc not in scope.pl_scope.codes:
        raise HTTPException(status_code=403, detail="无权访问该产品线")

    fmea = await get_fmea(db, req.fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    _check_factory_access(fmea, scope, detail="FMEA not found")

    # Enforce PL access on FMEA
    if scope.pl_scope.mode == "EXPLICIT" and fmea.product_line_code and fmea.product_line_code not in scope.pl_scope.codes:
        raise HTTPException(status_code=403, detail="无权访问该产品线")

    if fmea.fmea_type not in _VALID_FMEA_TYPES:
        raise HTTPException(status_code=400, detail="FMEA 类型必须是 DFMEA 或 PFMEA")

    if part_plc and fmea.product_line_code and part_plc != fmea.product_line_code:
        raise HTTPException(
            status_code=400,
            detail=f"Product line mismatch: part '{part_plc}' vs FMEA '{fmea.product_line_code}'",
        )

    if req.characteristic_type == "safety" and not part.is_safety_related:
        raise HTTPException(status_code=400, detail="该零件不是安全件，无法确认安全特性")
    if req.characteristic_type == "key_characteristic" and not part.is_key_characteristic:
        raise HTTPException(status_code=400, detail="该零件不是关键特性，无法确认关键特性")

    link_result = await db.execute(
        select(PLMPartSCLink)
        .where(
            PLMPartSCLink.part_id == part.part_id,
            PLMPartSCLink.characteristic_type == req.characteristic_type,
        )
        .with_for_update()
    )
    link = link_result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=400, detail="该零件没有对应的待确认请求")
    if link.status != "pending":
        raise HTTPException(status_code=400, detail="该请求已处理，无法重复确认")

    graph = fmea.graph_data if isinstance(fmea.graph_data, dict) else {}
    graph_nodes = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
    if not any(isinstance(node, dict) and node.get("id") == req.node_id for node in graph_nodes):
        raise HTTPException(status_code=400, detail="目标 FMEA 节点不存在")

    fmea_link_result = await db.execute(
        select(PLMPartFMEALink).where(
            PLMPartFMEALink.part_id == part.part_id,
            PLMPartFMEALink.fmea_id == req.fmea_id,
            PLMPartFMEALink.node_id == req.node_id,
        )
    )
    if fmea_link_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="目标 FMEA 节点未关联该 PLM 零件")

    product_line_code = fmea.product_line_code or part_plc
    if not product_line_code:
        raise HTTPException(status_code=400, detail="无法确定特殊特性的产品线")

    sc_type_by_characteristic_type = {
        "safety": "CC",
        "key_characteristic": "SC",
    }
    sc_create = schemas_special_characteristic.SCCreate(
        sc_name=part.name or part.part_number,
        sc_type=sc_type_by_characteristic_type[req.characteristic_type],
        source_fmea_id=req.fmea_id,
        source_node_id=req.node_id,
        source_type=fmea.fmea_type,
        product_line_code=product_line_code,
    )

    sc = await prepare_special_characteristic(db, sc_create, scope.user.user_id)
    if req.characteristic_type == "safety":
        sc.is_safety_related = True
        sc.safety_approval_status = SafetyApprovalStatus.PENDING.value

    link.sc_id = sc.sc_id
    link.status = "confirmed"
    link.confirmed_by = scope.user.user_id
    link.confirmed_at = datetime.now(timezone.utc)

    await db.commit()

    return schemas.PLMPartConfirmSCResponse(
        status="confirmed",
        sc_id=sc.sc_id,
        link_id=link.link_id,
    )


# ---------------------------------------------------------------------------
# Trigger impact analysis
# ---------------------------------------------------------------------------


@router.post("/change-orders/{change_id}/impact-analysis", response_model=schemas.PLMChangeImpactTaskResponse)
async def trigger_impact_analysis(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """Upsert an impact analysis task for a change order."""
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 EDIT 权限")

    # Fetch change order
    co_result = await db.execute(
        select(PLMChangeOrder).where(PLMChangeOrder.change_id == change_id)
    )
    co = co_result.scalar_one_or_none()
    if co is None:
        raise HTTPException(status_code=404, detail="Change order not found")
    _check_factory_access(co, scope, detail="Change order not found")

    # Upsert impact task
    from datetime import datetime, timezone

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(PLMChangeImpactTask)
        .values(
            task_id=uuid.uuid4(),
            change_id=change_id,
            status="pending",
            claim_token=None,
            retry_count=0,
            next_retry_at=now,
        )
        .on_conflict_do_update(
            index_elements=["change_id"],
            set_={
                "status": "pending",
                "claim_token": None,
                "retry_count": 0,
                "next_retry_at": now,
                "started_at": None,
                "completed_at": None,
                "error_message": None,
                "result": None,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()

    # Re-fetch to return
    task_result = await db.execute(
        select(PLMChangeImpactTask).where(PLMChangeImpactTask.change_id == change_id)
    )
    task = task_result.scalar_one()
    return schemas.PLMChangeImpactTaskResponse.model_validate(task)


# ---------------------------------------------------------------------------
# Import BOM to FMEA
# ---------------------------------------------------------------------------


@router.post("/connections/{connection_id}/boms/{part_number}/import-to-fmea")
async def import_bom_to_fmea(
    connection_id: uuid.UUID,
    part_number: str,
    req: schemas.BOMImportRequest,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    revision: str = Query("A"),
    bom_revision: str = Query("A"),
):
    """Import a multi-level BOM tree into an FMEA graph.

    Validates that the connection's product line matches the FMEA's product line,
    verifies the root part exists in the BOM tree, then performs multi-level BFS
    to build real parent-child HAS_CHILD edges in the FMEA graph.
    """
    level = await get_user_permission(scope.user, Module.PLM, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 plm 模块的 EDIT 权限")

    # Verify connection
    conn_result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    _check_factory_access(conn, scope, detail="PLM connection not found")

    # Verify FMEA
    fmea = await get_fmea(db, req.fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    _check_factory_access(fmea, scope, detail="FMEA not found")

    # Product line match: connection vs FMEA
    if conn.product_line_code != fmea.product_line_code:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Product line mismatch: connection '{conn.product_line_code}' "
                f"vs FMEA '{fmea.product_line_code}'"
            ),
        )

    # Fetch all BOM rows for this connection
    bom_result = await db.execute(
        select(PLMBOM).where(
            PLMBOM.connection_id == connection_id,
            PLMBOM.bom_revision == bom_revision,
        )
    )
    all_boms = [
        bom for bom in bom_result.scalars().all()
        if bom.bom_revision == bom_revision
    ]

    # Build adjacency: parent -> list of child BOM rows
    children_map: dict[tuple[str, str], list[PLMBOM]] = defaultdict(list)
    all_part_keys: set[tuple[str, str]] = set()
    for bom in all_boms:
        parent_key = (bom.parent_part_number, bom.parent_revision)
        child_key = (bom.child_part_number, bom.child_revision)
        children_map[parent_key].append(bom)
        all_part_keys.add(parent_key)
        all_part_keys.add(child_key)

    # Validate root part exists in BOM tree
    root_key = (part_number, revision)
    if root_key not in all_part_keys:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Part '{part_number}' revision '{revision}' not found in "
                f"BOM revision '{bom_revision}' for this connection"
            ),
        )

    # Multi-level BFS to collect BOM edges
    visited: set[tuple[str, str]] = set()
    queue: deque[tuple[str, str]] = deque([root_key])
    bom_edges: list[PLMBOM] = []

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        for bom in children_map.get(current, []):
            child_key = (bom.child_part_number, bom.child_revision)
            bom_edges.append(bom)
            if child_key not in visited:
                queue.append(child_key)

    existing_graph = fmea.graph_data or {"nodes": [], "edges": []}
    existing_nodes = existing_graph.get("nodes", [])
    existing_edges = existing_graph.get("edges", [])
    has_existing_graph = len(existing_nodes) > 1 or len(existing_edges) > 0
    if has_existing_graph and not req.overwrite:
        raise HTTPException(
            status_code=400,
            detail="FMEA already has graph data; use overwrite=true to replace",
        )

    # Build FMEA graph nodes and edges from BOM tree
    graph = {"nodes": [], "edges": []} if req.overwrite else existing_graph
    existing_node_ids: set[str] = {n["id"] for n in graph.get("nodes", [])}
    existing_edge_ids: set[str] = {e["id"] for e in graph.get("edges", []) if e.get("id")}
    new_nodes: list[dict] = []
    new_edges: list[dict] = []

    # Collect all unique parts from the BOM tree for node creation and links.
    tree_parts: dict[tuple[str, str], int] = {}
    for bom in bom_edges:
        parent_key = (bom.parent_part_number, bom.parent_revision)
        child_key = (bom.child_part_number, bom.child_revision)
        tree_parts[parent_key] = min(tree_parts.get(parent_key, bom.level - 1), bom.level - 1)
        tree_parts[child_key] = min(tree_parts.get(child_key, bom.level), bom.level)

    # Create nodes for parts not yet in the graph
    node_meta: list[tuple[str, str, str]] = []
    for (pn, rev), level in sorted(tree_parts.items(), key=lambda item: (item[1], item[0][0], item[0][1])):
        node_id = f"plm:{pn}:{rev}"
        node_meta.append((node_id, pn, rev))
        if node_id not in existing_node_ids:
            node_type = "System" if level <= 0 else "Subsystem" if level == 1 else "Component"
            new_nodes.append({
                "id": node_id,
                "type": node_type,
                "name": pn,
                "revision": rev,
                "source": "plm_import",
            })

    # Create HAS_CHILD edges for each BOM relationship
    for bom in bom_edges:
        edge_id = (
            f"has_child:{bom.parent_part_number}:{bom.parent_revision}:"
            f"{bom.child_part_number}:{bom.child_revision}:{bom.bom_revision}"
        )
        if edge_id not in existing_edge_ids:
            new_edges.append({
                "id": edge_id,
                "source": f"plm:{bom.parent_part_number}:{bom.parent_revision}",
                "target": f"plm:{bom.child_part_number}:{bom.child_revision}",
                "type": "HAS_CHILD",
                "quantity": float(bom.quantity),
            })

    # Merge into graph
    graph.setdefault("nodes", []).extend(new_nodes)
    graph.setdefault("edges", []).extend(new_edges)
    fmea.graph_data = graph
    flag_modified(fmea, "graph_data")

    # Keep PLM -> FMEA traceability in sync for ECN impact analysis.
    await db.execute(
        delete(PLMPartFMEALink).where(
            PLMPartFMEALink.fmea_id == req.fmea_id,
            PLMPartFMEALink.link_type == "auto_import",
        )
    )
    for node_id, pn, rev in node_meta:
        part_result = await db.execute(
            select(PLMPart).where(
                PLMPart.connection_id == connection_id,
                PLMPart.part_number == pn,
                PLMPart.revision == rev,
            )
        )
        part = part_result.scalar_one_or_none()
        if part is not None:
            await db.execute(
                pg_insert(PLMPartFMEALink)
                .values(
                    link_id=uuid.uuid4(),
                    part_id=part.part_id,
                    fmea_id=req.fmea_id,
                    node_id=node_id,
                    link_type="auto_import",
                )
                .on_conflict_do_update(
                    index_elements=["part_id", "fmea_id", "node_id"],
                    set_={"link_type": "auto_import"},
                )
            )
    await db.commit()

    return {
        "imported_nodes": len(new_nodes),
        "imported_edges": len(new_edges),
        "root": part_number,
        "revision": revision,
        "bom_revision": bom_revision,
        "fmea_id": str(req.fmea_id),
    }
