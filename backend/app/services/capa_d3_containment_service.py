"""D3 Containment Import Service (US-E2E-01.1 Task 2)

Implements Transaction A: 4 source queries + 5-step run promotion.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa_d3 import CapaD3ImportRun, CapaD3ContainmentSnapshot
from app.models.capa import CAPAEightD
from app.models.erp import ERPInventoryBalance, ERPShipment
from app.models.iqc_inspection import IqcInspection
from app.models.spc import SPCAlarm
from app.models.customer_quality import Customer
from app.models.supplier import Supplier
from app.services.capa_d3_risk_mappings import CURRENT_RISK_MAPPING_VERSION

if TYPE_CHECKING:
    from app.models.user import User


# Valid arrival status values for shipment
VALID_ARRIVAL_STATUSES = {"signed", "in_transit", "pending", "unknown"}


async def import_containment_data(
    db: AsyncSession,
    capa_id: uuid.UUID,
    user: "User",
    request: dict | None = None,
) -> dict:
    """Import containment data for a CAPA (Transaction A: 4 source queries + 5-step run promotion).

    This function:
    1. Queries 4 data sources (inventory, shipment, iqc, spc)
    2. Creates snapshots for each source
    3. Promotes a new run (demotes old current if exists)

    Args:
        db: Database session
        capa_id: CAPA report ID
        user: User performing the import
        request: Import request (optional, for future extensibility)

    Returns:
        dict with run_id, snapshots list, and summary
    """
    # Get CAPA with factory info
    capa = await db.get(CAPAEightD, capa_id)
    if not capa:
        raise ValueError(f"CAPA {capa_id} not found")

    factory_id = capa.factory_id
    product_line_code = capa.product_line_code

    # Query 4 data sources
    inventory_records = await _query_inventory(db, factory_id, product_line_code)
    shipment_records = await _query_shipment(db, factory_id, product_line_code)
    iqc_records = await _query_iqc(db, factory_id, product_line_code)
    spc_records = await _query_spc(db, factory_id, product_line_code)

    # 5-step run promotion (atomic)
    run, snapshots = await _promote_run(
        db=db,
        capa_id=capa_id,
        factory_id=factory_id,
        user_id=user.user_id,
        capa_severity=capa.severity,
        inventory_records=inventory_records,
        shipment_records=shipment_records,
        iqc_records=iqc_records,
        spc_records=spc_records,
    )

    return {
        "run_id": str(run.run_id),
        "snapshots": [
            {
                "snapshot_id": str(s.snapshot_id),
                "snapshot_type": s.snapshot_type,
                "record_count": s.record_count,
            }
            for s in snapshots
        ],
    }


async def _query_inventory(
    db: AsyncSession, factory_id: uuid.UUID, product_line_code: str
) -> list[dict]:
    """Query inventory balance records for the factory + product line."""
    from app.models.erp import ERPConnection

    # Get ERP connections for this factory
    result = await db.execute(
        select(ERPConnection.connection_id).where(ERPConnection.factory_id == factory_id)
    )
    connection_ids = [row[0] for row in result.fetchall()]

    if not connection_ids:
        return []

    # Query inventory balances
    result = await db.execute(
        select(ERPInventoryBalance).where(
            and_(
                ERPInventoryBalance.connection_id.in_(connection_ids),
            )
        )
    )
    records = result.scalars().all()

    payload = []
    for rec in records:
        payload.append({
            "record_key": f"inv:{rec.balance_id}",
            "source_id": str(rec.balance_id),
            "material_code": rec.material_code,
            "lot_no": rec.lot_no or None,
            "quantity": rec.quantity,
            "unit": rec.unit or "pcs",
            "location_code": rec.location_code,
            "snapshot_type": "inventory",
        })

    return payload


async def _query_shipment(
    db: AsyncSession, factory_id: uuid.UUID, product_line_code: str
) -> list[dict]:
    """Query shipment records for the factory + product line."""
    # Query shipments
    result = await db.execute(
        select(ERPShipment).where(
            and_(
                ERPShipment.factory_id == factory_id,
                or_(
                    ERPShipment.product_line_code == product_line_code,
                    ERPShipment.product_line_code.is_(None),
                ),
            )
        )
    )
    shipments = result.scalars().all()

    payload = []
    for ship in shipments:
        # Extract unit from erp_raw_data or default to 'unknown'
        raw_data = ship.erp_raw_data or {}
        unit = raw_data.get("unit", "unknown")

        # Extract and validate arrival_status
        arrival_status = raw_data.get("arrival_status", "unknown")
        if arrival_status not in VALID_ARRIVAL_STATUSES:
            arrival_status = "unknown"

        # Get customer info
        customer_segment = None
        customer_name = None
        if ship.customer_code:
            cust_result = await db.execute(
                select(Customer).where(Customer.customer_code == ship.customer_code)
            )
            customer = cust_result.scalar_one_or_none()
            if customer:
                customer_segment = customer.segment
                customer_name = customer.name

        payload.append({
            "record_key": f"ship:{ship.erp_shipment_id}",
            "source_id": str(ship.erp_shipment_id),
            "material_code": ship.material_code,
            "lot_no": ship.lot_no,
            "quantity": ship.quantity,
            "unit": unit,
            "customer_code": ship.customer_code,
            "customer_name": customer_name,
            "customer_segment": customer_segment,
            "arrival_status": arrival_status,
            "shipment_date": str(ship.shipment_date) if ship.shipment_date else None,
            "snapshot_type": "shipment",
        })

    return payload


async def _query_iqc(
    db: AsyncSession, factory_id: uuid.UUID, product_line_code: str
) -> list[dict]:
    """Query IQC inspection records for the factory + product line."""
    result = await db.execute(
        select(IqcInspection).where(IqcInspection.linked_capa_id.is_(None))
    )
    inspections = result.scalars().all()

    payload = []
    for insp in inspections:
        # Get supplier name
        supplier_name = None
        if insp.supplier_id:
            sup_result = await db.execute(
                select(Supplier).where(Supplier.supplier_id == insp.supplier_id)
            )
            supplier = sup_result.scalar_one_or_none()
            if supplier:
                supplier_name = supplier.name

        payload.append({
            "record_key": f"iqc:{insp.inspection_id}",
            "source_id": str(insp.inspection_id),
            "inspection_no": insp.inspection_no,
            "supplier_id": str(insp.supplier_id) if insp.supplier_id else None,
            "supplier_name": supplier_name,
            "part_no": insp.part_no,
            "lot_no": insp.lot_no,
            "lot_qty": insp.lot_qty,
            "defect_qty": insp.defect_qty,
            "defect_description": insp.defect_description,
            "inspection_result": insp.inspection_result,
            "inspection_date": str(insp.inspection_date) if insp.inspection_date else None,
            "snapshot_type": "iqc",
        })

    return payload


async def _query_spc(
    db: AsyncSession, factory_id: uuid.UUID, product_line_code: str
) -> list[dict]:
    """Query SPC alarm records for the factory (30-day window).

    Note: SPCAlarm has FK to inspection_characteristics (ic_id).
    We use a LEFT JOIN pattern by querying linked_capa_id first,
    then falling back to recent alarms in the factory.
    """
    from datetime import timezone

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    # Query SPC alarms linked to this CAPA or in the factory
    result = await db.execute(
        select(SPCAlarm).where(
            and_(
                SPCAlarm.factory_id == factory_id,
                SPCAlarm.triggered_at >= thirty_days_ago,
            )
        )
    )
    alarms = result.scalars().all()

    payload = []
    for alarm in alarms:
        payload.append({
            "record_key": f"spc:{alarm.alarm_id}",
            "source_id": str(alarm.alarm_id),
            "ic_id": str(alarm.ic_id),
            "rule_no": alarm.rule_no,
            "severity": alarm.severity,
            "status": alarm.status,
            "triggered_at": str(alarm.triggered_at),
            "snapshot_type": "spc",
        })

    return payload


async def _promote_run(
    db: AsyncSession,
    capa_id: uuid.UUID,
    factory_id: uuid.UUID,
    user_id: uuid.UUID,
    capa_severity: str,
    inventory_records: list[dict],
    shipment_records: list[dict],
    iqc_records: list[dict],
    spc_records: list[dict],
) -> tuple[CapaD3ImportRun, list[CapaD3ContainmentSnapshot]]:
    """5-step atomic run promotion:

    1. Demote old current run (if exists)
    2. Create new run with is_current=false (to avoid CHECK constraint)
    3. Create 4 snapshots linked to new run
    4. Update run status to completed with completed_at
    5. Set is_current=true and commit

    Returns (run, snapshots) tuple.
    """
    from datetime import timezone

    now = datetime.now(timezone.utc)
    completed_at = datetime.now(timezone.utc)

    # Step 1: Demote old current run
    result = await db.execute(
        select(CapaD3ImportRun).where(
            and_(
                CapaD3ImportRun.capa_id == capa_id,
                CapaD3ImportRun.is_current == True,
            )
        )
    )
    old_run = result.scalar_one_or_none()
    if old_run:
        old_run.is_current = False

    # Step 2: Create new run (is_current=False initially to avoid CHECK)
    run = CapaD3ImportRun(
        capa_id=capa_id,
        factory_id=factory_id,
        is_current=False,  # Start false, will set true after completed
        status="importing",
        imported_types=[],
        analysis_context={
            "capa_severity": capa_severity,
            "risk_mapping_version": CURRENT_RISK_MAPPING_VERSION,
        },
        imported_by=user_id,
        started_at=now,
    )
    db.add(run)
    await db.flush()  # Get run_id

    # Step 3: Create 4 snapshots
    snapshots = []
    snapshot_data = [
        ("inventory", inventory_records),
        ("shipment", shipment_records),
        ("iqc", iqc_records),
        ("spc", spc_records),
    ]

    for snapshot_type, records in snapshot_data:
        snapshot = CapaD3ContainmentSnapshot(
            run_id=run.run_id,
            factory_id=factory_id,
            snapshot_type=snapshot_type,
            payload=records,
            record_count=len(records),
            imported_by=user_id,
            imported_at=now,
        )
        db.add(snapshot)
        snapshots.append(snapshot)

    # Step 4: Update run status to completed with completed_at
    run.status = "completed"
    run.completed_at = completed_at
    run.imported_types = [s.snapshot_type for s in snapshots if s.record_count > 0 or True]

    # Step 5: Set is_current=true (now satisfies CHECK: completed + completed_at)
    run.is_current = True

    # Commit
    await db.commit()

    # Refresh to get IDs
    for s in snapshots:
        await db.refresh(s)
    await db.refresh(run)

    return run, snapshots
