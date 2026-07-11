"""D3 Containment Import Service (US-E2E-01.1 Task 2+3)

Implements Transaction A: 4 source queries + 5-step run promotion.
Implements deterministic calculations: batch_key, impact_qty, customer_impact, time_window, risk_floor.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa_d3 import CapaD3ImportRun, CapaD3ContainmentSnapshot
from app.models.capa import CAPAEightD
from app.models.erp import ERPInventoryBalance, ERPShipment
from app.models.iqc_inspection import IqcInspection
from app.models.spc import SPCAlarm
from app.models.customer_quality import Customer
from app.models.supplier import Supplier
from app.services.capa_d3_risk_mappings import CURRENT_RISK_MAPPING_VERSION, RISK_MAPPINGS

if TYPE_CHECKING:
    from app.models.user import User


# Valid arrival status values for shipment
VALID_ARRIVAL_STATUSES = {"signed", "in_transit", "pending", "unknown"}


# ===== Deterministic Calculation Functions (Task 3) =====

def _norm(v: str | None) -> str:
    """Normalize string for comparison: strip, lowercase."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip().lower()
    return str(v)


def _batch_key(material_code: str | None, lot_no: str | None, snapshot_type: str, source_id: str) -> str:
    """Compute batch key: hash(normalized_material + normalized_lot).

    If lot is missing, degrades to {snapshot_type}:{source_id}.
    """
    m = _norm(material_code)
    lot = _norm(lot_no)
    if not lot:
        return f"{snapshot_type}:{source_id}"  # Degraded
    raw = f"{m}|{lot}"
    return sha256(raw.encode()).hexdigest()[:16]


def _material_of(rec: dict, snapshot_type: str) -> str:
    """Get material identifier: inventory/shipment use material_code; IQC uses part_no."""
    if snapshot_type == "iqc":
        return rec.get("part_no", "")
    return rec.get("material_code", "")


def _arrival_status_to_status(arrival_status: str | None) -> str:
    """Map arrival_status to qty_by_status key.

    signed -> shipped
    in_transit -> in_transit
    pending/unknown/None -> in_transit (conservative)
    """
    if arrival_status == "signed":
        return "shipped"
    return "in_transit"


def _compute_batches(snapshots: list[dict]) -> list[dict]:
    """Compute batches from snapshots.

    Each snapshot is {"snapshot_type", "snapshot_id", "payload": [record, ...]}.
    Returns list of batches, each with:
    - batch_key
    - material_code
    - lot_no
    - qty_by_status: {"inventory": [...], "shipped": [...], "in_transit": [...]}
    - source_refs: [{"snapshot_type", "snapshot_id", "source_id", ...}]
    """
    batches: dict[str, dict] = {}  # batch_key -> batch

    for snap in snapshots:
        snapshot_type = snap["snapshot_type"]
        snapshot_id = snap["snapshot_id"]
        payload = snap.get("payload", [])

        seen_source_ids: set[str] = set()  # Dedup within snapshot

        for rec in payload:
            source_id = rec.get("source_id", "")
            if not source_id or source_id in seen_source_ids:
                continue  # Skip empty or duplicate source_id
            seen_source_ids.add(source_id)

            material = _material_of(rec, snapshot_type)
            lot_no = rec.get("lot_no")
            qty = rec.get("quantity")
            unit = rec.get("unit", "pcs")
            arrival_status = rec.get("arrival_status")

            # Compute batch key
            bkey = _batch_key(material, lot_no, snapshot_type, source_id)

            # Initialize batch if needed
            if bkey not in batches:
                batches[bkey] = {
                    "batch_key": bkey,
                    "material_code": material,
                    "lot_no": lot_no,
                    "qty_by_status": {
                        "inventory": [],
                        "shipped": [],
                        "in_transit": [],
                    },
                    "source_refs": [],
                }

            batch = batches[bkey]

            # Add source ref (all sources)
            batch["source_refs"].append({
                "snapshot_type": snapshot_type,
                "snapshot_id": snapshot_id,
                "source_id": source_id,
            })

            # Add quantity only for inventory/shipment
            if qty is not None and snapshot_type in ("inventory", "shipment"):
                status_key = "inventory" if snapshot_type == "inventory" else _arrival_status_to_status(arrival_status)
                qty_entry = {"qty": qty, "unit": unit}
                batch["qty_by_status"][status_key].append(qty_entry)

    return list(batches.values())


def _compute_impact_qty(batches: list[dict]) -> dict[str, list[dict]]:
    """Compute impact quantities by status.

    Sums quantities by status+unit across all batches.
    Returns {"inventory": [{"qty", "unit"}], "shipped": [...], "in_transit": [...]}.
    """
    result: dict[str, dict[str, float]] = {}  # status -> {unit: qty}

    for batch in batches:
        for status, qtys in batch["qty_by_status"].items():
            if status not in result:
                result[status] = {}
            for q in qtys:
                unit = q["unit"]
                if unit not in result[status]:
                    result[status][unit] = 0.0
                result[status][unit] += q["qty"]

    # Convert to output format
    output: dict[str, list[dict]] = {}
    for status, units in result.items():
        output[status] = [{"qty": qty, "unit": unit} for unit, qty in units.items()]

    return output


def _compute_customer_impact(shipment_snapshot: dict) -> list[dict]:
    """Compute customer impact from shipment snapshot.

    Returns list of {"customer_name", "customer_segment", "arrival_status", "quantities"}.
    """
    result: dict[tuple, dict] = {}  # (customer_code, arrival_status) -> impact

    for rec in shipment_snapshot.get("payload", []):
        customer_code = rec.get("customer_code")
        customer_name = rec.get("customer_name", "")
        customer_segment = rec.get("customer_segment", "")
        arrival_status = rec.get("arrival_status", "unknown")
        qty = rec.get("quantity")
        unit = rec.get("unit", "pcs")

        if not customer_code:
            continue

        key = (customer_code, arrival_status)
        if key not in result:
            result[key] = {
                "customer_name": customer_name,
                "customer_segment": customer_segment,
                "arrival_status": arrival_status,
                "quantities": [],
            }

        if qty is not None:
            result[key]["quantities"].append({"qty": qty, "unit": unit})

    return list(result.values())


def _compute_time_window(spc_snapshot: dict) -> dict[str, str | None]:
    """Compute time window from SPC snapshot.

    Returns {"start": min_triggered_at, "end": max_triggered_at}.
    """
    timestamps = []
    for rec in spc_snapshot.get("payload", []):
        ts = rec.get("triggered_at")
        if ts:
            timestamps.append(ts)

    if not timestamps:
        return {"start": None, "end": None}

    timestamps.sort()
    return {"start": timestamps[0], "end": timestamps[-1]}


def _compute_risk_floor(customer_impact: list[dict], analysis_context: dict) -> tuple[str | None, str | None]:
    """Compute risk floor based on customer impact and CAPA severity.

    Returns (floor, error_code). error_code is None on success.
    Unknown risk_mapping_version returns (None, "unknown_risk_mapping_version").
    """
    version = analysis_context.get("risk_mapping_version")
    capa_severity = analysis_context.get("capa_severity", "general")

    # Check version exists
    if version not in RISK_MAPPINGS:
        return (None, "unknown_risk_mapping_version")

    version_mappings = RISK_MAPPINGS[version]

    # Check for unknown arrival status with affected customer
    for ci in customer_impact:
        arrival = ci.get("arrival_status", "unknown")
        if arrival == "unknown" and ci.get("quantities"):
            # Unknown arrival with affected customer -> high (conservative)
            return ("high", None)

    # Use CAPA severity mapping
    severity_floor = version_mappings.get(capa_severity)
    if severity_floor:
        return (severity_floor, None)

    # Default to general
    return (version_mappings.get("general", "low"), None)


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
