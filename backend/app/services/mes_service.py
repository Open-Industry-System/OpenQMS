"""MES ingestion service — atomic, caller-controls-transaction.

All methods receive an AsyncSession and do NOT commit or rollback.
The caller is responsible for transaction boundaries.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mes import (
    MESConnection,
    MESMeasurementIngestion,
    MESProductionOrder,
    MESEquipmentStatus,
    MESScrapRecord,
    MESPushOutbox,
)
from app.models.spc import InspectionCharacteristic, SampleBatch
from app.services.spc_service import _create_sample_batch_inner, _reevaluate_alarms_no_commit


class MESIngestionService:
    """Dispatch MES raw data into OpenQMS tables atomically."""

    @staticmethod
    async def ingest(db: AsyncSession, data: dict) -> dict:
        """Route ingestion payload by data_type."""
        data_type = data.get("data_type")
        connection_id = data.get("connection_id")
        if not connection_id:
            raise ValueError("connection_id is required")

        if data_type == "measurement":
            return await MESIngestionService._ingest_measurement(db, data)
        if data_type == "production_order":
            return await MESIngestionService._ingest_production_order(db, data)
        if data_type == "equipment_status":
            return await MESIngestionService._ingest_equipment_status(db, data)
        if data_type == "scrap_record":
            return await MESIngestionService._ingest_scrap_record(db, data)

        raise ValueError(f"Unsupported data_type: {data_type}")

    # ------------------------------------------------------------------
    # Measurement -> SPC SampleBatch (atomic)
    # ------------------------------------------------------------------

    @staticmethod
    async def _ingest_measurement(db: AsyncSession, data: dict) -> dict:
        """Atomic measurement ingestion:
        1. INSERT mes_measurement_ingestions ON CONFLICT DO NOTHING
        2. If duplicate -> skip
        3. Find IC by ic_code, verify product_line
        4. Create SampleBatch (flush only)
        5. Re-evaluate SPC alarms
        6. If new alarms, write MES outbox events for push_enabled connections
        7. Backfill batch_id into ingestion record
        """
        connection_id = uuid.UUID(data["connection_id"]) if isinstance(data["connection_id"], str) else data["connection_id"]
        external_id = data["external_id"]
        ic_code = data["ic_code"]
        product_line_code = data.get("product_line_code")

        # 1. Deduplication insert
        ingest_stmt = (
            pg_insert(MESMeasurementIngestion)
            .values(
                connection_id=connection_id,
                external_id=external_id,
                order_no=data.get("order_no"),
                ic_code=ic_code,
                mes_raw_data=data.get("raw_data"),
                source_sampled_at=data["sampled_at"],
                source_updated_at=data.get("source_updated_at"),
                product_line_code=product_line_code,
            )
            .on_conflict_do_nothing(
                index_elements=["connection_id", "external_id"]
            )
            .returning(MESMeasurementIngestion.ingestion_id)
        )
        result = await db.execute(ingest_stmt)
        ingestion_id = result.scalar()

        # 2. Duplicate check
        if ingestion_id is None:
            return {"status": "skipped", "reason": "duplicate"}

        # 3. Find InspectionCharacteristic
        ic_result = await db.execute(
            select(InspectionCharacteristic).where(InspectionCharacteristic.ic_code == ic_code)
        )
        ic = ic_result.scalar_one_or_none()
        if ic is None:
            return {"status": "skipped", "reason": f"ic_code not found: {ic_code}"}

        # Verify product_line matches connection
        if product_line_code and ic.product_line != product_line_code:
            return {
                "status": "skipped",
                "reason": f"product_line mismatch: IC={ic.product_line}, data={product_line_code}",
            }

        # 4. Create SampleBatch (flush only, no commit)
        batch_data = {
            "batch_no": data.get("batch_no") or external_id,
            "sampled_at": data["sampled_at"],
            "values": data.get("values", []),
            "inspected_count": data.get("inspected_count"),
            "defect_count": data.get("defect_count"),
        }
        batch = await _create_sample_batch_inner(db, ic.created_by_id, ic.ic_id, batch_data)

        # 5. Re-evaluate SPC alarms (flush only)
        new_alarms = await _reevaluate_alarms_no_commit(db, ic)

        # 6. Write MES outbox events for new alarms
        if new_alarms:
            await MESIngestionService._write_alarm_outbox_events(
                db, connection_id, ic, batch, new_alarms
            )

        # 7. Backfill batch_id into ingestion record
        await db.execute(
            select(MESMeasurementIngestion)
            .where(MESMeasurementIngestion.ingestion_id == ingestion_id)
        )
        # Use UPDATE to set batch_id
        await db.execute(
            select(MESMeasurementIngestion)
            .where(MESMeasurementIngestion.ingestion_id == ingestion_id)
        )
        # Actually update
        from sqlalchemy import update as sa_update
        await db.execute(
            sa_update(MESMeasurementIngestion)
            .where(MESMeasurementIngestion.ingestion_id == ingestion_id)
            .values(batch_id=batch.batch_id)
        )

        return {"status": "success", "batch_id": str(batch.batch_id), "alarm_count": len(new_alarms)}

    @staticmethod
    async def _write_alarm_outbox_events(
        db: AsyncSession,
        source_connection_id: uuid.UUID,
        ic: InspectionCharacteristic,
        batch: SampleBatch,
        alarms: list[Any],
    ) -> None:
        """Write MESPushOutbox records for all active connections with push_enabled."""
        conn_result = await db.execute(
            select(MESConnection).where(
                MESConnection.is_active == True,  # noqa: E712
            )
        )
        connections = conn_result.scalars().all()

        for conn in connections:
            config = conn.config or {}
            if not config.get("push_enabled"):
                continue

            for alarm in alarms:
                payload = {
                    "event_type": "spc_alarm",
                    "ic_code": ic.ic_code,
                    "batch_no": batch.batch_no,
                    "rule_no": alarm.rule_no,
                    "severity": alarm.severity,
                    "alarm_id": str(alarm.alarm_id) if alarm.alarm_id else None,
                    "source_connection_id": str(source_connection_id),
                }
                outbox = MESPushOutbox(
                    event_type="spc_alarm",
                    connection_id=conn.connection_id,
                    payload=payload,
                )
                db.add(outbox)

        await db.flush()

    # ------------------------------------------------------------------
    # Production Order (UPSERT)
    # ------------------------------------------------------------------

    @staticmethod
    async def _ingest_production_order(db: AsyncSession, data: dict) -> dict:
        """UPSERT production order with ON CONFLICT (connection_id, order_no) DO UPDATE.
        Backfills scrap records' order_id via (connection_id, order_no)."""
        connection_id = uuid.UUID(data["connection_id"]) if isinstance(data["connection_id"], str) else data["connection_id"]
        order_no = data["order_no"]

        values = {
            "connection_id": connection_id,
            "order_no": order_no,
            "product_model": data.get("product_model"),
            "process_route": data.get("process_route"),
            "planned_qty": data.get("planned_qty"),
            "actual_qty": data.get("actual_qty"),
            "status": data.get("status", "planned"),
            "started_at": data.get("started_at"),
            "completed_at": data.get("completed_at"),
            "source_updated_at": data.get("source_updated_at"),
            "product_line_code": data.get("product_line_code"),
            "mes_raw_data": data.get("raw_data"),
        }

        stmt = (
            pg_insert(MESProductionOrder)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["connection_id", "order_no"],
                set_={
                    "product_model": pg_insert(MESProductionOrder).excluded.product_model,
                    "process_route": pg_insert(MESProductionOrder).excluded.process_route,
                    "planned_qty": pg_insert(MESProductionOrder).excluded.planned_qty,
                    "actual_qty": pg_insert(MESProductionOrder).excluded.actual_qty,
                    "status": pg_insert(MESProductionOrder).excluded.status,
                    "started_at": pg_insert(MESProductionOrder).excluded.started_at,
                    "completed_at": pg_insert(MESProductionOrder).excluded.completed_at,
                    "source_updated_at": pg_insert(MESProductionOrder).excluded.source_updated_at,
                    "product_line_code": pg_insert(MESProductionOrder).excluded.product_line_code,
                    "mes_raw_data": pg_insert(MESProductionOrder).excluded.mes_raw_data,
                },
            )
            .returning(MESProductionOrder.order_id)
        )
        result = await db.execute(stmt)
        order_id = result.scalar()

        # Backfill scrap records' order_id
        await db.execute(
            select(MESScrapRecord).where(
                MESScrapRecord.connection_id == connection_id,
                MESScrapRecord.order_no == order_no,
                MESScrapRecord.order_id.is_(None),
            )
        )
        from sqlalchemy import update as sa_update
        await db.execute(
            sa_update(MESScrapRecord)
            .where(
                MESScrapRecord.connection_id == connection_id,
                MESScrapRecord.order_no == order_no,
                MESScrapRecord.order_id.is_(None),
            )
            .values(order_id=order_id)
        )

        return {"status": "success", "order_id": str(order_id)}

    # ------------------------------------------------------------------
    # Equipment Status (INSERT ON CONFLICT DO NOTHING)
    # ------------------------------------------------------------------

    @staticmethod
    async def _ingest_equipment_status(db: AsyncSession, data: dict) -> dict:
        """INSERT equipment status ON CONFLICT DO NOTHING."""
        connection_id = uuid.UUID(data["connection_id"]) if isinstance(data["connection_id"], str) else data["connection_id"]
        external_id = data["external_id"]

        stmt = (
            pg_insert(MESEquipmentStatus)
            .values(
                connection_id=connection_id,
                external_id=external_id,
                equipment_code=data["equipment_code"],
                equipment_name=data.get("equipment_name"),
                status=data["status"],
                availability=data.get("availability"),
                performance=data.get("performance"),
                quality=data.get("quality"),
                oee=data.get("oee"),
                downtime_reason=data.get("downtime_reason"),
                recorded_at=data["recorded_at"],
                product_line_code=data.get("product_line_code"),
                mes_raw_data=data.get("raw_data"),
            )
            .on_conflict_do_nothing(
                index_elements=["connection_id", "external_id"]
            )
            .returning(MESEquipmentStatus.record_id)
        )
        result = await db.execute(stmt)
        record_id = result.scalar()

        if record_id is None:
            return {"status": "skipped", "reason": "duplicate"}

        return {"status": "success", "record_id": str(record_id)}

    # ------------------------------------------------------------------
    # Scrap Record (UPSERT with COALESCE backfill)
    # ------------------------------------------------------------------

    @staticmethod
    async def _ingest_scrap_record(db: AsyncSession, data: dict) -> dict:
        """UPSERT scrap record. Resolves order_no -> order_id if possible.
        ON CONFLICT only backfills order_id/order_no via COALESCE."""
        connection_id = uuid.UUID(data["connection_id"]) if isinstance(data["connection_id"], str) else data["connection_id"]
        external_id = data["external_id"]
        order_no = data.get("order_no")

        # Resolve order_no -> order_id if possible
        order_id = None
        if order_no:
            order_result = await db.execute(
                select(MESProductionOrder.order_id).where(
                    MESProductionOrder.connection_id == connection_id,
                    MESProductionOrder.order_no == order_no,
                )
            )
            order_id = order_result.scalar_one_or_none()

        stmt = (
            pg_insert(MESScrapRecord)
            .values(
                connection_id=connection_id,
                external_id=external_id,
                order_no=order_no,
                order_id=order_id,
                equipment_code=data.get("equipment_code"),
                defect_type=data["defect_type"],
                defect_category=data.get("defect_category"),
                defect_qty=data["defect_qty"],
                total_qty=data["total_qty"],
                defect_description=data.get("defect_description"),
                recorded_at=data["recorded_at"],
                source_updated_at=data.get("source_updated_at"),
                product_line_code=data.get("product_line_code"),
                mes_raw_data=data.get("raw_data"),
            )
            .on_conflict_do_update(
                index_elements=["connection_id", "external_id"],
                set_={
                    "order_id": func.coalesce(
                        MESScrapRecord.order_id,
                        pg_insert(MESScrapRecord).excluded.order_id,
                    ),
                    "order_no": func.coalesce(
                        MESScrapRecord.order_no,
                        pg_insert(MESScrapRecord).excluded.order_no,
                    ),
                },
            )
            .returning(MESScrapRecord.scrap_id)
        )
        result = await db.execute(stmt)
        scrap_id = result.scalar()

        return {"status": "success", "scrap_id": str(scrap_id), "order_id": str(order_id) if order_id else None}
