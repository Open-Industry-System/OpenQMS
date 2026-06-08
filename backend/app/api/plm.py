"""PLM API routes — connections, parts, BOMs, change orders, dashboard."""

import uuid
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import (
    Module,
    PermissionLevel,
    get_current_user,
    require_permission,
)
from app.core.product_line_filter import (
    apply_product_line_filter,
    enforce_product_line_access,
)
from app.models.fmea import FMEADocument
from app.models.plm import (
    PLMBOM,
    PLMChangeImpactTask,
    PLMChangeOrder,
    PLMConnection,
    PLMPart,
    PLMPartFMEALink,
)
from app.models.user import User
from app.schemas import plm as schemas
from app.services.fmea_service import get_fmea
from app.services.plm_service import PLMSyncService

router = APIRouter(prefix="/api/plm", tags=["plm"])


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


@router.post("/connections", response_model=schemas.PLMConnectionResponse, status_code=201)
async def create_connection(
    req: schemas.PLMConnectionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.CREATE)),
):
    """Create a PLM connection. User must have access to the target product line."""
    await enforce_product_line_access(user, req.product_line_code, db)

    conn = PLMConnection(
        name=req.name,
        connector_type=req.connector_type,
        config=req.config,
        product_line_code=req.product_line_code,
        created_by=user.user_id,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return schemas.PLMConnectionResponse.model_validate(conn)


@router.get("/connections", response_model=schemas.PLMConnectionListResponse)
async def list_connections(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(PLMConnection)
    query = await apply_product_line_filter(query, user, PLMConnection, "plm", db, request)

    count_query = select(func.count()).select_from(PLMConnection)
    count_query = await apply_product_line_filter(count_query, user, PLMConnection, "plm", db, request)

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
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    await enforce_product_line_access(user, conn.product_line_code, db)
    return schemas.PLMConnectionResponse.model_validate(conn)


@router.put("/connections/{connection_id}", response_model=schemas.PLMConnectionResponse)
async def update_connection(
    connection_id: uuid.UUID,
    req: schemas.PLMConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    await enforce_product_line_access(user, conn.product_line_code, db)

    data = req.model_dump(exclude_unset=True)
    # If changing product_line_code, verify access to new value
    new_plc = data.get("product_line_code")
    if new_plc and new_plc != conn.product_line_code:
        await enforce_product_line_access(user, new_plc, db)

    for field, value in data.items():
        setattr(conn, field, value)

    await db.commit()
    await db.refresh(conn)
    return schemas.PLMConnectionResponse.model_validate(conn)


@router.delete("/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.ADMIN)),
):
    result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    await enforce_product_line_access(user, conn.product_line_code, db)

    await db.delete(conn)
    await db.commit()


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    await enforce_product_line_access(user, conn.product_line_code, db)

    from app.services.plm_connector import get_plm_connector

    connector = get_plm_connector(conn, None)
    try:
        ok = await connector.test_connection()
    finally:
        await connector.close()
    return {"success": ok}


@router.post("/connections/{connection_id}/sync")
async def manual_sync(
    connection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    await enforce_product_line_access(user, conn.product_line_code, db)

    count = await PLMSyncService.manual_sync(db, connection_id)
    return {"synced_jobs": count}


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------


@router.get("/parts")
async def list_parts(
    request: Request,
    connection_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(PLMPart)
    if connection_id:
        query = query.where(PLMPart.connection_id == connection_id)

    query = await apply_product_line_filter(query, user, PLMPart, "plm", db, request)

    count_query = select(func.count()).select_from(PLMPart)
    if connection_id:
        count_query = count_query.where(PLMPart.connection_id == connection_id)
    count_query = await apply_product_line_filter(count_query, user, PLMPart, "plm", db, request)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(PLMPart.part_number).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()

    return {
        "items": [schemas.PLMPartResponse.model_validate(p) for p in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/parts/{part_id}", response_model=schemas.PLMPartResponse)
async def get_part(
    part_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(PLMPart).where(PLMPart.part_id == part_id))
    part = result.scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")
    # Part product_line_code may be null; fall back to connection's
    plc = part.product_line_code
    if plc is None:
        conn_result = await db.execute(
            select(PLMConnection.product_line_code).where(
                PLMConnection.connection_id == part.connection_id
            )
        )
        plc = conn_result.scalar_one_or_none()
    await enforce_product_line_access(user, plc, db)
    return schemas.PLMPartResponse.model_validate(part)


# ---------------------------------------------------------------------------
# BOMs
# ---------------------------------------------------------------------------


@router.get("/boms")
async def list_boms(
    request: Request,
    connection_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(PLMBOM)
    if connection_id:
        query = query.where(PLMBOM.connection_id == connection_id)

    query = await apply_product_line_filter(query, user, PLMBOM, "plm", db, request)

    count_query = select(func.count()).select_from(PLMBOM)
    if connection_id:
        count_query = count_query.where(PLMBOM.connection_id == connection_id)
    count_query = await apply_product_line_filter(count_query, user, PLMBOM, "plm", db, request)

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
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Multi-level BOM tree via BFS starting from part_number."""
    # Verify connection exists and user has access
    conn_result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    await enforce_product_line_access(user, conn.product_line_code, db)

    # Fetch all BOM rows for this connection
    bom_result = await db.execute(
        select(PLMBOM).where(PLMBOM.connection_id == connection_id)
    )
    all_boms = bom_result.scalars().all()

    # Build adjacency: parent_part_number -> list of children
    children_map: dict[str, list[PLMBOM]] = defaultdict(list)
    all_part_numbers: set[str] = set()
    for bom in all_boms:
        children_map[bom.parent_part_number].append(bom)
        all_part_numbers.add(bom.parent_part_number)
        all_part_numbers.add(bom.child_part_number)

    # Validate root part exists in BOM tree
    if part_number not in all_part_numbers:
        raise HTTPException(
            status_code=404,
            detail=f"Part '{part_number}' not found in BOM tree for this connection",
        )

    # Multi-level BFS
    visited: set[str] = set()
    queue: deque[str] = deque([part_number])
    tree: list[dict] = []

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        for bom in children_map.get(current, []):
            tree.append({
                "parent_part_number": bom.parent_part_number,
                "parent_revision": bom.parent_revision,
                "child_part_number": bom.child_part_number,
                "child_revision": bom.child_revision,
                "quantity": float(bom.quantity),
                "level": bom.level,
                "bom_revision": bom.bom_revision,
            })
            if bom.child_part_number not in visited:
                queue.append(bom.child_part_number)

    return {"root": part_number, "items": tree, "total": len(tree)}


# ---------------------------------------------------------------------------
# Change orders
# ---------------------------------------------------------------------------


@router.get("/change-orders")
async def list_change_orders(
    request: Request,
    connection_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(PLMChangeOrder)
    if connection_id:
        query = query.where(PLMChangeOrder.connection_id == connection_id)

    query = await apply_product_line_filter(query, user, PLMChangeOrder, "plm", db, request)

    count_query = select(func.count()).select_from(PLMChangeOrder)
    if connection_id:
        count_query = count_query.where(PLMChangeOrder.connection_id == connection_id)
    count_query = await apply_product_line_filter(count_query, user, PLMChangeOrder, "plm", db, request)

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
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PLMChangeOrder).where(PLMChangeOrder.change_id == change_id)
    )
    co = result.scalar_one_or_none()
    if co is None:
        raise HTTPException(status_code=404, detail="Change order not found")
    await enforce_product_line_access(user, co.product_line_code, db)
    return schemas.PLMChangeOrderResponse.model_validate(co)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=schemas.PLMDashboardResponse)
async def get_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dashboard with product-line-filtered counts."""
    # Parts count
    parts_q = select(func.count()).select_from(PLMPart)
    parts_q = await apply_product_line_filter(parts_q, user, PLMPart, "plm", db, request)
    part_count = (await db.execute(parts_q)).scalar() or 0

    # BOM count
    boms_q = select(func.count()).select_from(PLMBOM)
    boms_q = await apply_product_line_filter(boms_q, user, PLMBOM, "plm", db, request)
    bom_count = (await db.execute(boms_q)).scalar() or 0

    # Pending ECN count
    ecn_q = select(func.count()).select_from(PLMChangeOrder).where(
        PLMChangeOrder.status.in_(["draft", "pending", "approved"])
    )
    ecn_q = await apply_product_line_filter(ecn_q, user, PLMChangeOrder, "plm", db, request)
    pending_ecn_count = (await db.execute(ecn_q)).scalar() or 0

    # Pending SC count (from PLMPartSCLink)
    from app.models.plm import PLMPartSCLink

    sc_q = select(func.count()).select_from(PLMPartSCLink).where(
        PLMPartSCLink.status == "pending"
    )
    if not user.role_definition.bypass_row_level_security:
        from app.models.role import UserProductLine

        user_plc_result = await db.execute(
            select(UserProductLine.product_line_code).where(
                UserProductLine.user_id == user.user_id
            )
        )
        user_codes = [r[0] for r in user_plc_result.all()]
        if not user_codes:
            pending_sc_count = 0
        else:
            sc_q = sc_q.where(PLMPartSCLink.product_line_code.in_(user_codes))
            pending_sc_count = (await db.execute(sc_q)).scalar() or 0
    else:
        pending_sc_count = (await db.execute(sc_q)).scalar() or 0

    # Recent changes (last 10)
    recent_q = select(PLMChangeOrder).order_by(
        PLMChangeOrder.change_number.desc()
    ).limit(10)
    recent_q = await apply_product_line_filter(recent_q, user, PLMChangeOrder, "plm", db, request)
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
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    """Link a PLM part to an FMEA node. Both must share the same product line."""
    # Fetch part
    part_result = await db.execute(select(PLMPart).where(PLMPart.part_id == part_id))
    part = part_result.scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")

    # Resolve part product line
    part_plc = part.product_line_code
    if part_plc is None:
        conn_r = await db.execute(
            select(PLMConnection.product_line_code).where(
                PLMConnection.connection_id == part.connection_id
            )
        )
        part_plc = conn_r.scalar_one_or_none()
    await enforce_product_line_access(user, part_plc, db)

    # Fetch FMEA
    fmea = await get_fmea(db, req.fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)

    # Product line match check
    if part_plc and fmea.product_line_code and part_plc != fmea.product_line_code:
        raise HTTPException(
            status_code=400,
            detail=f"Product line mismatch: part '{part_plc}' vs FMEA '{fmea.product_line_code}'",
        )

    # Upsert link
    from sqlalchemy.dialects.postgresql import insert as pg_insert

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


# ---------------------------------------------------------------------------
# Trigger impact analysis
# ---------------------------------------------------------------------------


@router.post("/change-orders/{change_id}/impact-analysis", response_model=schemas.PLMChangeImpactTaskResponse)
async def trigger_impact_analysis(
    change_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    """Upsert an impact analysis task for a change order."""
    # Fetch change order
    co_result = await db.execute(
        select(PLMChangeOrder).where(PLMChangeOrder.change_id == change_id)
    )
    co = co_result.scalar_one_or_none()
    if co is None:
        raise HTTPException(status_code=404, detail="Change order not found")
    await enforce_product_line_access(user, co.product_line_code, db)

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
    user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT)),
):
    """Import a multi-level BOM tree into an FMEA graph.

    Validates that the connection's product line matches the FMEA's product line,
    verifies the root part exists in the BOM tree, then performs multi-level BFS
    to build real parent-child HAS_CHILD edges in the FMEA graph.
    """
    # Verify connection
    conn_result = await db.execute(
        select(PLMConnection).where(PLMConnection.connection_id == connection_id)
    )
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="PLM connection not found")
    await enforce_product_line_access(user, conn.product_line_code, db)

    # Verify FMEA
    fmea = await get_fmea(db, req.fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)

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
        select(PLMBOM).where(PLMBOM.connection_id == connection_id)
    )
    all_boms = bom_result.scalars().all()

    # Build adjacency: parent -> list of child BOM rows
    children_map: dict[str, list[PLMBOM]] = defaultdict(list)
    all_part_numbers: set[str] = set()
    for bom in all_boms:
        children_map[bom.parent_part_number].append(bom)
        all_part_numbers.add(bom.parent_part_number)
        all_part_numbers.add(bom.child_part_number)

    # Validate root part exists in BOM tree
    if part_number not in all_part_numbers:
        raise HTTPException(
            status_code=404,
            detail=f"Part '{part_number}' not found in BOM tree for this connection",
        )

    # Multi-level BFS to collect BOM edges
    visited: set[str] = set()
    queue: deque[str] = deque([part_number])
    bom_edges: list[PLMBOM] = []

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        for bom in children_map.get(current, []):
            bom_edges.append(bom)
            if bom.child_part_number not in visited:
                queue.append(bom.child_part_number)

    # Build FMEA graph nodes and edges from BOM tree
    graph = fmea.graph_data or {"nodes": [], "edges": []}
    existing_node_ids: set[str] = {n["id"] for n in graph.get("nodes", [])}
    new_nodes: list[dict] = []
    new_edges: list[dict] = []

    # Collect all unique part numbers from the BOM tree for node creation
    tree_parts: set[str] = set()
    for bom in bom_edges:
        tree_parts.add(bom.parent_part_number)
        tree_parts.add(bom.child_part_number)

    # Create nodes for parts not yet in the graph
    for pn in tree_parts:
        node_id = f"plm:{pn}"
        if node_id not in existing_node_ids:
            new_nodes.append({
                "id": node_id,
                "type": "process_item",
                "label": pn,
                "source": "plm_import",
            })

    # Create HAS_CHILD edges for each BOM relationship
    for bom in bom_edges:
        edge_id = f"has_child:{bom.parent_part_number}:{bom.child_part_number}"
        new_edges.append({
            "id": edge_id,
            "source": f"plm:{bom.parent_part_number}",
            "target": f"plm:{bom.child_part_number}",
            "type": "HAS_CHILD",
            "quantity": float(bom.quantity),
        })

    # Merge into graph
    graph.setdefault("nodes", []).extend(new_nodes)
    graph.setdefault("edges", []).extend(new_edges)
    fmea.graph_data = graph
    await db.commit()

    return {
        "imported_nodes": len(new_nodes),
        "imported_edges": len(new_edges),
        "root": part_number,
        "fmea_id": str(req.fmea_id),
    }
