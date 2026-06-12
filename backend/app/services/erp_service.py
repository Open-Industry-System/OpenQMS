"""
ERP ingestion, sync, and traceability services.

All ingestion methods receive an AsyncSession and do NOT commit.
Caller controls transaction boundaries.
"""
import uuid
from datetime import datetime, date, timezone, timedelta
from typing import Any

from sqlalchemy import select, func, update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SYSTEM_USER_ID
from app.models.erp import (
    ERPConnection, ERPSyncJob, ERPPushOutbox,
    ERPSupplier, ERPCustomer, ERPMaterial, ERPLocation,
    ERPPurchaseOrder, ERPSalesOrder, ERPInventoryBalance,
    ERPShipment, ERPCostRecord,
)
from app.models.supplier import Supplier
from app.models.customer_quality import Customer, ShipmentRecord
from app.services.erp_connector import get_erp_connector


# ---------------------------------------------------------------------------
# Ingestion Service
# ---------------------------------------------------------------------------

class ERPIngestionService:
    @staticmethod
    def _coerce_date(value):
        """Normalize date strings to date objects for DB bind safety."""
        if value is None:
            return None
        if isinstance(value, (date, datetime)):
            return value if isinstance(value, date) else value.date()
        if isinstance(value, str) and value:
            from datetime import datetime as dt
            try:
                return dt.strptime(value[:10], "%Y-%m-%d").date()
            except (ValueError, IndexError):
                return value  # let DB reject bad formats
        return value

    @staticmethod
    def _coerce_datetime(value):
        """Normalize datetime strings to datetime objects for DB bind safety."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            from datetime import datetime as dt
            try:
                return dt.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, IndexError):
                return value
        return value

    @staticmethod
    async def ingest(db: AsyncSession, data: dict) -> dict:
        data_type = data.get("data_type")
        connection_id = data.get("connection_id")
        if not connection_id:
            raise ValueError("connection_id is required")

        # Load connection to get factory_id (background sync has no request context)
        conn_result = await db.execute(
            select(ERPConnection).where(ERPConnection.connection_id == uuid.UUID(connection_id))
        )
        connection = conn_result.scalar_one_or_none()
        factory_id = connection.factory_id if connection else None

        handlers = {
            "suppliers": ERPIngestionService._ingest_suppliers,
            "customers": ERPIngestionService._ingest_customers,
            "materials": ERPIngestionService._ingest_materials,
            "locations": ERPIngestionService._ingest_locations,
            "purchase_orders": ERPIngestionService._ingest_purchase_orders,
            "sales_orders": ERPIngestionService._ingest_sales_orders,
            "inventory_balances": ERPIngestionService._ingest_inventory_balances,
            "shipments": ERPIngestionService._ingest_shipments,
            "cost_records": ERPIngestionService._ingest_cost_records,
        }
        handler = handlers.get(data_type)
        if not handler:
            raise ValueError(f"Unsupported data_type: {data_type}")

        items = data.get("items", [])
        results = []
        for item in items:
            try:
                result = await handler(db, uuid.UUID(connection_id), item, factory_id=factory_id)
                results.append({"status": "success", "external_id": item.get("external_id")})
            except Exception as e:
                results.append({"status": "error", "external_id": item.get("external_id"), "error": str(e)})
        return {"processed": len(items), "results": results}

    @staticmethod
    async def _ingest_suppliers(db: AsyncSession, connection_id: uuid.UUID, item: dict, factory_id: uuid.UUID | None = None) -> dict:
        values = {
            "connection_id": connection_id,
            "external_id": item["external_id"],
            "supplier_code": item["supplier_code"],
            "name": item["name"],
            "status": item.get("status", "active"),
            "payment_terms": item.get("payment_terms"),
            "currency": item.get("currency"),
            "tax_id": item.get("tax_id"),
            "bank_info": item.get("bank_info"),
            "source_updated_at": datetime.now(timezone.utc),
            "erp_raw_data": item,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id
        # Try to auto-link
        supplier_result = await db.execute(
            select(Supplier).where(Supplier.supplier_no == item["supplier_code"])
        )
        supplier = supplier_result.scalar_one_or_none()
        if supplier:
            values["openqms_supplier_id"] = supplier.supplier_id
            values["link_status"] = "linked"
        else:
            values["link_status"] = "pending"

        stmt = pg_insert(ERPSupplier).values(**values).on_conflict_do_update(
            index_elements=["connection_id", "supplier_code"],
            set_={k: v for k, v in values.items() if k not in ("connection_id", "supplier_code")}
        )
        await db.execute(stmt)
        return {"external_id": item["external_id"]}

    @staticmethod
    async def _ingest_customers(db: AsyncSession, connection_id: uuid.UUID, item: dict, factory_id: uuid.UUID | None = None) -> dict:
        values = {
            "connection_id": connection_id,
            "external_id": item["external_id"],
            "customer_code": item["customer_code"],
            "name": item["name"],
            "status": item.get("status", "active"),
            "region": item.get("region"),
            "customer_level": item.get("customer_level"),
            "tax_id": item.get("tax_id"),
            "source_updated_at": datetime.now(timezone.utc),
            "erp_raw_data": item,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id
        customer_result = await db.execute(
            select(Customer).where(Customer.customer_code == item["customer_code"])
        )
        customer = customer_result.scalar_one_or_none()
        if customer:
            values["openqms_customer_id"] = customer.customer_id
            values["link_status"] = "linked"
        else:
            values["link_status"] = "pending"

        stmt = pg_insert(ERPCustomer).values(**values).on_conflict_do_update(
            index_elements=["connection_id", "customer_code"],
            set_={k: v for k, v in values.items() if k not in ("connection_id", "customer_code")}
        )
        await db.execute(stmt)
        return {"external_id": item["external_id"]}

    @staticmethod
    async def _ingest_materials(db: AsyncSession, connection_id: uuid.UUID, item: dict, factory_id: uuid.UUID | None = None) -> dict:
        values = {
            "connection_id": connection_id,
            "external_id": item["external_id"],
            "material_code": item["material_code"],
            "name": item["name"],
            "specification": item.get("specification"),
            "unit": item.get("unit"),
            "material_type": item.get("material_type"),
            "is_purchased": item.get("is_purchased", False),
            "is_manufactured": item.get("is_manufactured", False),
            "default_supplier_code": item.get("default_supplier_code"),
            "status": item.get("status", "active"),
            "source_updated_at": datetime.now(timezone.utc),
            "erp_raw_data": item,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id
        stmt = pg_insert(ERPMaterial).values(**values).on_conflict_do_update(
            index_elements=["connection_id", "material_code"],
            set_={k: v for k, v in values.items() if k not in ("connection_id", "material_code")}
        )
        await db.execute(stmt)
        return {"external_id": item["external_id"]}

    @staticmethod
    async def _ingest_locations(db: AsyncSession, connection_id: uuid.UUID, item: dict, factory_id: uuid.UUID | None = None) -> dict:
        values = {
            "connection_id": connection_id,
            "external_id": item["external_id"],
            "location_code": item["location_code"],
            "warehouse_code": item.get("warehouse_code"),
            "zone_code": item.get("zone_code"),
            "location_type": item.get("location_type", "normal"),
            "is_enabled": item.get("is_enabled", True),
            "source_updated_at": datetime.now(timezone.utc),
            "erp_raw_data": item,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id
        stmt = pg_insert(ERPLocation).values(**values).on_conflict_do_update(
            index_elements=["connection_id", "location_code"],
            set_={k: v for k, v in values.items() if k not in ("connection_id", "location_code")}
        )
        await db.execute(stmt)
        return {"external_id": item["external_id"]}

    @staticmethod
    async def _ingest_purchase_orders(db: AsyncSession, connection_id: uuid.UUID, item: dict, factory_id: uuid.UUID | None = None) -> dict:
        values = {
            "connection_id": connection_id,
            "external_id": item["external_id"],
            "po_number": item["po_number"],
            "line_number": item.get("line_number", "1"),
            "supplier_code": item.get("supplier_code"),
            "material_code": item.get("material_code"),
            "quantity": item.get("quantity"),
            "unit_price": item.get("unit_price"),
            "currency": item.get("currency"),
            "delivery_date": ERPIngestionService._coerce_date(item.get("delivery_date")),
            "received_quantity": item.get("received_quantity"),
            "status": item.get("status", "draft"),
            "lot_no": item.get("lot_no") or "",
            "source_updated_at": datetime.now(timezone.utc),
            "erp_raw_data": item,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id
        # Check reference
        if item.get("supplier_code"):
            sup = await db.execute(select(ERPSupplier).where(
                ERPSupplier.connection_id == connection_id,
                ERPSupplier.supplier_code == item["supplier_code"]
            ))
            if not sup.scalar_one_or_none():
                values.setdefault("erp_raw_data", {})["_reference_errors"] = [
                    {"field": "supplier_code", "value": item["supplier_code"], "reason": "not_found"}
                ]

        stmt = pg_insert(ERPPurchaseOrder).values(**values).on_conflict_do_update(
            index_elements=["connection_id", "po_number", "line_number"],
            set_={k: v for k, v in values.items() if k not in ("connection_id", "po_number", "line_number")}
        )
        await db.execute(stmt)
        return {"external_id": item["external_id"]}

    @staticmethod
    async def _ingest_sales_orders(db: AsyncSession, connection_id: uuid.UUID, item: dict, factory_id: uuid.UUID | None = None) -> dict:
        values = {
            "connection_id": connection_id,
            "external_id": item["external_id"],
            "so_number": item["so_number"],
            "line_number": item.get("line_number", "1"),
            "customer_code": item.get("customer_code"),
            "material_code": item.get("material_code"),
            "quantity": item.get("quantity"),
            "unit_price": item.get("unit_price"),
            "delivery_date": ERPIngestionService._coerce_date(item.get("delivery_date")),
            "status": item.get("status", "draft"),
            "source_updated_at": datetime.now(timezone.utc),
            "erp_raw_data": item,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id
        stmt = pg_insert(ERPSalesOrder).values(**values).on_conflict_do_update(
            index_elements=["connection_id", "so_number", "line_number"],
            set_={k: v for k, v in values.items() if k not in ("connection_id", "so_number", "line_number")}
        )
        await db.execute(stmt)
        return {"external_id": item["external_id"]}

    @staticmethod
    async def _ingest_inventory_balances(db: AsyncSession, connection_id: uuid.UUID, item: dict, factory_id: uuid.UUID | None = None) -> dict:
        values = {
            "connection_id": connection_id,
            "external_id": item["external_id"],
            "material_code": item["material_code"],
            "location_code": item["location_code"],
            "lot_no": item.get("lot_no", ""),
            "supplier_lot_no": item.get("supplier_lot_no"),
            "quantity": item.get("quantity"),
            "unit": item.get("unit"),
            "inventory_status": item.get("inventory_status", "available"),
            "manufacture_date": ERPIngestionService._coerce_date(item.get("manufacture_date")),
            "expiry_date": ERPIngestionService._coerce_date(item.get("expiry_date")),
            "snapshot_at": datetime.now(timezone.utc),
            "erp_raw_data": item,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id
        stmt = pg_insert(ERPInventoryBalance).values(**values).on_conflict_do_update(
            index_elements=["connection_id", "material_code", "location_code", "lot_no"],
            set_={k: v for k, v in values.items() if k not in ("connection_id", "material_code", "location_code", "lot_no")}
        )
        await db.execute(stmt)
        return {"external_id": item["external_id"]}

    @staticmethod
    async def _ingest_shipments(db: AsyncSession, connection_id: uuid.UUID, item: dict, factory_id: uuid.UUID | None = None) -> dict:
        values = {
            "connection_id": connection_id,
            "external_id": item["external_id"],
            "shipment_number": item["shipment_number"],
            "line_number": item.get("line_number", "1"),
            "so_number": item.get("so_number"),
            "customer_code": item.get("customer_code"),
            "material_code": item.get("material_code"),
            "lot_no": item.get("lot_no"),
            "quantity": item.get("quantity"),
            "shipment_date": ERPIngestionService._coerce_date(item.get("shipment_date")),
            "source_updated_at": datetime.now(timezone.utc),
            "link_status": "pending",
            "erp_raw_data": item,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id
        stmt = pg_insert(ERPShipment).values(**values).on_conflict_do_update(
            index_elements=["connection_id", "shipment_number", "line_number"],
            set_={k: v for k, v in values.items() if k not in ("connection_id", "shipment_number", "line_number")}
        )
        await db.execute(stmt)

        # After ingestion, try to link to shipment_records
        await ERPIngestionService._link_shipment(db, connection_id, item)
        return {"external_id": item["external_id"]}

    @staticmethod
    async def _link_shipment(db: AsyncSession, connection_id: uuid.UUID, item: dict) -> None:
        """Link erp_shipments to shipment_records."""
        if not item.get("customer_code"):
            return

        # Find erp_customer
        cust_result = await db.execute(select(ERPCustomer).where(
            ERPCustomer.connection_id == connection_id,
            ERPCustomer.customer_code == item["customer_code"]
        ))
        erp_customer = cust_result.scalar_one_or_none()
        if not erp_customer or not erp_customer.openqms_customer_id:
            return

        customer_id = erp_customer.openqms_customer_id
        lot_no = item.get("lot_no")
        shipment_date = ERPIngestionService._coerce_date(item.get("shipment_date"))

        if not lot_no or not shipment_date:
            return

        # Find existing ShipmentRecord
        record_result = await db.execute(select(ShipmentRecord).where(
            ShipmentRecord.customer_id == customer_id,
            ShipmentRecord.batch_no == lot_no,
            ShipmentRecord.shipment_date == shipment_date,
        ))
        record = record_result.scalar_one_or_none()

        # Find all erp_shipment lines for this customer/lot/date
        lines_result = await db.execute(select(ERPShipment).where(
            ERPShipment.connection_id == connection_id,
            ERPShipment.customer_code == item["customer_code"],
            ERPShipment.lot_no == lot_no,
            ERPShipment.shipment_date == shipment_date,
        ))
        lines = lines_result.scalars().all()
        total_qty = sum(int(line.quantity or 0) for line in lines)
        line_refs = ",".join([f"{line.shipment_number}-{line.line_number}" for line in lines])

        if record:
            record.quantity = total_qty
            record.notes = f"ERP auto-import: {line_refs}"
            for line in lines:
                line.openqms_shipment_id = record.shipment_id
                line.link_status = "linked"
        else:
            # Create new ShipmentRecord
            new_record = ShipmentRecord(
                customer_id=customer_id,
                shipment_date=shipment_date,
                quantity=total_qty,
                batch_no=lot_no,
                product_line_code=lines[0].product_line_code if lines else None,
                notes=f"ERP auto-import: {line_refs}",
                created_by=SYSTEM_USER_ID,
            )
            db.add(new_record)
            await db.flush()
            for line in lines:
                line.openqms_shipment_id = new_record.shipment_id
                line.link_status = "linked"

    @staticmethod
    async def _ingest_cost_records(db: AsyncSession, connection_id: uuid.UUID, item: dict, factory_id: uuid.UUID | None = None) -> dict:
        values = {
            "connection_id": connection_id,
            "external_id": item["external_id"],
            "record_type": item["record_type"],
            "cost_category": item["cost_category"],
            "cost_type": item["cost_type"],
            "amount": item["amount"],
            "currency": item.get("currency"),
            "period_month": item.get("period_month"),
            "source_document_no": item.get("source_document_no"),
            "material_code": item.get("material_code"),
            "supplier_code": item.get("supplier_code"),
            "cost_center": item.get("cost_center"),
            "cost_date": ERPIngestionService._coerce_date(item.get("cost_date")),
            "description": item.get("description"),
            "source_updated_at": datetime.now(timezone.utc),
            "erp_raw_data": item,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id
        stmt = pg_insert(ERPCostRecord).values(**values).on_conflict_do_update(
            index_elements=["connection_id", "external_id"],
            set_={k: v for k, v in values.items() if k not in ("connection_id", "external_id")}
        )
        await db.execute(stmt)
        return {"external_id": item["external_id"]}


# ---------------------------------------------------------------------------
# Sync Service
# ---------------------------------------------------------------------------

class ERPSyncService:
    """4-phase DAG sync with dependency gating."""

    DAG_PHASES = {
        1: ["suppliers", "customers", "materials", "locations"],
        2: ["purchase_orders", "sales_orders"],
        3: ["inventory_balances", "shipments"],
        4: ["cost_records"],
    }

    @staticmethod
    def get_phase(data_type: str) -> int:
        for phase, types in ERPSyncService.DAG_PHASES.items():
            if data_type in types:
                return phase
        return 0

    @staticmethod
    async def sync_all(db: AsyncSession) -> dict:
        """Run sync jobs respecting DAG dependency order."""
        results = []
        for phase in sorted(ERPSyncService.DAG_PHASES.keys()):
            phase_results = await ERPSyncService._sync_phase(db, phase)
            results.extend(phase_results)
        return {"phases": len(ERPSyncService.DAG_PHASES), "results": results}

    @staticmethod
    async def _sync_phase(db: AsyncSession, phase: int) -> list[dict]:
        data_types = ERPSyncService.DAG_PHASES[phase]
        results = []
        for data_type in data_types:
            result = await ERPSyncService._run_single_sync_job(db, data_type)
            results.append(result)
        return results

    @staticmethod
    async def _run_single_sync_job(db: AsyncSession, data_type: str) -> dict:
        """Claim and run a single sync job."""
        from sqlalchemy import text as sa_text

        # Claim job with SKIP LOCKED
        result = await db.execute(sa_text("""
            SELECT job_id, connection_id, checkpoint FROM erp_sync_jobs
            WHERE data_type = :data_type
              AND status IN ('pending', 'failed')
              AND next_run_at <= NOW()
            ORDER BY next_run_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        """).bindparams(data_type=data_type))
        job = result.fetchone()
        if not job:
            return {"data_type": data_type, "status": "no_job"}

        job_id, connection_id, checkpoint = job

        # Check upstream dependencies
        current_phase = ERPSyncService.get_phase(data_type)
        if current_phase > 1:
            upstream_types = []
            for p in range(1, current_phase):
                upstream_types.extend(ERPSyncService.DAG_PHASES[p])
            upstream_result = await db.execute(
                select(func.count()).select_from(ERPSyncJob).where(
                    ERPSyncJob.connection_id == connection_id,
                    ERPSyncJob.data_type.in_(upstream_types),
                    ERPSyncJob.status != "completed",
                )
            )
            pending = upstream_result.scalar()
            if pending > 0:
                # Defer this job
                await db.execute(sa_text("""
                    UPDATE erp_sync_jobs
                    SET next_run_at = NOW() + INTERVAL '30 seconds'
                    WHERE job_id = :job_id
                """).bindparams(job_id=job_id))
                return {"data_type": data_type, "status": "deferred", "reason": "upstream_pending"}

        # Mark as running
        await db.execute(sa_text("""
            UPDATE erp_sync_jobs
            SET status = 'running', started_at = NOW()
            WHERE job_id = :job_id
        """).bindparams(job_id=str(job_id)))
        await db.commit()

        # Execute sync
        try:
            conn_result = await db.execute(select(ERPConnection).where(ERPConnection.connection_id == connection_id))
            connection = conn_result.scalar_one()
            if not connection.is_active:
                raise ValueError("Connection is inactive")

            factory_id = connection.factory_id

            connector = get_erp_connector(connection)
            since = checkpoint or datetime(2000, 1, 1, tzinfo=timezone.utc)

            fetch_method = getattr(connector, f"fetch_{data_type}")
            items = await fetch_method(since)

            # Ingest items
            for item in items:
                await getattr(ERPIngestionService, f"_ingest_{data_type}")(db, connection_id, item, factory_id=factory_id)

            # Mark completed
            await db.execute(sa_text("""
                UPDATE erp_sync_jobs
                SET status = 'completed', checkpoint = NOW(), completed_at = NOW(),
                    next_run_at = NOW() + INTERVAL '5 minutes',
                    consecutive_failures = 0
                WHERE job_id = :job_id
            """).bindparams(job_id=str(job_id)))
            await db.commit()
            return {"data_type": data_type, "status": "completed", "items": len(items)}

        except Exception as e:
            await db.rollback()
            await db.execute(sa_text("""
                UPDATE erp_sync_jobs
                SET status = 'failed', error_message = :error,
                    consecutive_failures = consecutive_failures + 1
                WHERE job_id = :job_id
            """).bindparams(job_id=str(job_id), error=str(e)[:500]))
            await db.commit()

            # Deactivate connection after 3 failures
            fail_result = await db.execute(sa_text("""
                SELECT consecutive_failures FROM erp_sync_jobs WHERE job_id = :job_id
            """).bindparams(job_id=str(job_id)))
            if fail_result.scalar() >= 3:
                await db.execute(sa_text("""
                    UPDATE erp_connections SET is_active = FALSE WHERE connection_id = :conn_id
                """).bindparams(conn_id=str(connection_id)))
                await db.commit()
            return {"data_type": data_type, "status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# Traceability Service
# ---------------------------------------------------------------------------

class ERPTraceabilityService:
    @staticmethod
    async def query(db: AsyncSession, lot_no: str, direction: str = "forward") -> dict:
        """Bidirectional traceability query. Supports multiple PO/shipment lines per lot_no."""
        nodes = []
        edges = []
        gaps = []
        seen_node_ids = set()
        seen_edge_keys = set()

        def _add_node(node_id: str, node_type: str, label: str):
            if node_id not in seen_node_ids:
                nodes.append({"id": node_id, "type": node_type, "label": label})
                seen_node_ids.add(node_id)

        def _add_edge(from_id: str, to_id: str, edge_type: str):
            key = (from_id, to_id, edge_type)
            if key not in seen_edge_keys:
                edges.append({"from": from_id, "to": to_id, "type": edge_type})
                seen_edge_keys.add(key)

        lot_node_id = f"lot:{lot_no}"

        if direction == "forward":
            # 1. Find POs by lot_no (may be multiple lines)
            po_result = await db.execute(select(ERPPurchaseOrder).where(ERPPurchaseOrder.lot_no == lot_no))
            pos = po_result.scalars().all()
            if pos:
                _add_node(lot_node_id, "erp_lot", lot_no)
                for po in pos:
                    _add_node(f"po:{po.po_number}", "po", po.po_number)
                    _add_edge(lot_node_id, f"po:{po.po_number}", "inspected_as")

                    # 2. Find supplier for each PO
                    if po.supplier_code:
                        sup_result = await db.execute(select(ERPSupplier).where(
                            ERPSupplier.connection_id == po.connection_id,
                            ERPSupplier.supplier_code == po.supplier_code
                        ))
                        sup = sup_result.scalar_one_or_none()
                        if sup:
                            _add_node(f"supplier:{po.supplier_code}", "supplier", sup.name)
                            _add_edge(f"supplier:{po.supplier_code}", lot_node_id, "supplied")
            else:
                _add_node(lot_node_id, "erp_lot", lot_no)

            # 3. Find shipments by lot_no (may be multiple lines)
            ship_result = await db.execute(select(ERPShipment).where(ERPShipment.lot_no == lot_no))
            shipments = ship_result.scalars().all()
            for ship in shipments:
                _add_node(f"shipment:{ship.shipment_number}", "shipment", ship.shipment_number)
                _add_edge(lot_node_id, f"shipment:{ship.shipment_number}", "shipped_in")

                # 4. Find customer for each shipment
                if ship.customer_code:
                    cust_result = await db.execute(select(ERPCustomer).where(
                        ERPCustomer.connection_id == ship.connection_id,
                        ERPCustomer.customer_code == ship.customer_code
                    ))
                    cust = cust_result.scalar_one_or_none()
                    if cust:
                        _add_node(f"customer:{ship.customer_code}", "customer", cust.name)
                        _add_edge(f"shipment:{ship.shipment_number}", f"customer:{ship.customer_code}", "delivered_to")

            # MES gap
            gaps.append({"type": "missing_mes_consumption", "message": "MES 工单投料/产出关联尚未建立", "node_id": lot_node_id})

        else:  # backward
            _add_node(lot_node_id, "erp_lot", lot_no)

            # 1. Find shipments by lot_no (may be multiple lines)
            ship_result = await db.execute(select(ERPShipment).where(ERPShipment.lot_no == lot_no))
            ships = ship_result.scalars().all()
            for ship in ships:
                _add_node(f"shipment:{ship.shipment_number}", "shipment", ship.shipment_number)
                _add_edge(f"shipment:{ship.shipment_number}", lot_node_id, "shipped_in")

            # 2. Find POs by lot_no (may be multiple lines)
            po_result = await db.execute(select(ERPPurchaseOrder).where(ERPPurchaseOrder.lot_no == lot_no))
            pos = po_result.scalars().all()
            for po in pos:
                _add_node(f"po:{po.po_number}", "po", po.po_number)
                _add_edge(f"po:{po.po_number}", lot_node_id, "purchased_as")

                if po.supplier_code:
                    sup_result = await db.execute(select(ERPSupplier).where(
                        ERPSupplier.connection_id == po.connection_id,
                        ERPSupplier.supplier_code == po.supplier_code
                    ))
                    sup = sup_result.scalar_one_or_none()
                    if sup:
                        _add_node(f"supplier:{po.supplier_code}", "supplier", sup.name)
                        _add_edge(f"po:{po.po_number}", f"supplier:{po.supplier_code}", "ordered_from")

            # MES gap
            gaps.append({"type": "missing_mes_consumption", "message": "MES 工单投料/产出关联尚未建立", "node_id": lot_node_id})

        return {"nodes": nodes, "edges": edges, "gaps": gaps}
