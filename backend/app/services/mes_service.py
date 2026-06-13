"""MES ingestion service — atomic, caller-controls-transaction.

All methods receive an AsyncSession and do NOT commit or rollback.
The caller is responsible for transaction boundaries.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_tenant_aware_session
from app.models.audit import AuditLog
from app.models.mes import (
    MESConnection,
    MESEquipmentStatus,
    MESMeasurementIngestion,
    MESProductionOrder,
    MESPushOutbox,
    MESScrapRecord,
    MESSyncJob,
)
from app.models.spc import InspectionCharacteristic, SampleBatch
from app.services.mes_connector import get_mes_connector_by_config
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

        # Load connection to get factory_id (background sync has no request context)
        conn_result = await db.execute(
            select(MESConnection).where(MESConnection.connection_id == uuid.UUID(connection_id))
        )
        connection = conn_result.scalar_one_or_none()
        factory_id = connection.factory_id if connection else None

        if data_type == "measurement":
            return await MESIngestionService._ingest_measurement(db, data, factory_id=factory_id)
        if data_type == "production_order":
            return await MESIngestionService._ingest_production_order(db, data, factory_id=factory_id)
        if data_type == "equipment_status":
            return await MESIngestionService._ingest_equipment_status(db, data, factory_id=factory_id)
        if data_type == "scrap_record":
            return await MESIngestionService._ingest_scrap_record(db, data, factory_id=factory_id)

        raise ValueError(f"Unsupported data_type: {data_type}")

    # ------------------------------------------------------------------
    # Measurement -> SPC SampleBatch (atomic)
    # ------------------------------------------------------------------

    @staticmethod
    async def _ingest_measurement(db: AsyncSession, data: dict, factory_id: uuid.UUID | None = None) -> dict:
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

        # 1. Validate IC exists BEFORE dedupe insert (so bad data never marks external_id as processed)
        ic_result = await db.execute(
            select(InspectionCharacteristic).where(InspectionCharacteristic.ic_code == ic_code)
        )
        ic = ic_result.scalar_one_or_none()
        if ic is None:
            raise ValueError(f"Inspection characteristic not found: {ic_code}")

        # Verify product_line matches connection
        if product_line_code and ic.product_line != product_line_code:
            raise ValueError(
                f"Product line mismatch: IC={ic.product_line}, connection={product_line_code}"
            )

        # 2. Deduplication insert
        ingest_values = {
                "connection_id": connection_id,
                "external_id": external_id,
                "order_no": data.get("order_no"),
                "ic_code": ic_code,
                "mes_raw_data": data.get("raw_data"),
                "source_sampled_at": data["sampled_at"],
                "source_updated_at": data.get("source_updated_at"),
                "product_line_code": product_line_code,
        }
        if factory_id is not None:
            ingest_values["factory_id"] = factory_id

        ingest_stmt = (
            pg_insert(MESMeasurementIngestion)
            .values(**ingest_values)
            .on_conflict_do_nothing(
                index_elements=["connection_id", "external_id"]
            )
            .returning(MESMeasurementIngestion.ingestion_id)
        )
        result = await db.execute(ingest_stmt)
        ingestion_id = result.scalar()

        # 3. Duplicate check
        if ingestion_id is None:
            return {"status": "skipped", "reason": "duplicate"}

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
        """Write MESPushOutbox records for active connections matching IC product line.
        Skips the source connection to avoid echoing back to the originating MES."""
        conn_result = await db.execute(
            select(MESConnection).where(
                MESConnection.is_active == True,  # noqa: E712
                MESConnection.product_line_code == ic.product_line,
                MESConnection.connection_id != source_connection_id,
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
    async def _ingest_production_order(db: AsyncSession, data: dict, factory_id: uuid.UUID | None = None) -> dict:
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
        if factory_id is not None:
            values["factory_id"] = factory_id

        # Build set_ from values excluding index elements
        update_set = {
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
        }
        if factory_id is not None:
            update_set["factory_id"] = pg_insert(MESProductionOrder).excluded.factory_id

        stmt = (
            pg_insert(MESProductionOrder)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["connection_id", "order_no"],
                set_=update_set,
            )
            .returning(MESProductionOrder.order_id)
        )
        result = await db.execute(stmt)
        order_id = result.scalar()

        # Backfill scrap records' order_id
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
    async def _ingest_equipment_status(db: AsyncSession, data: dict, factory_id: uuid.UUID | None = None) -> dict:
        """INSERT equipment status ON CONFLICT DO NOTHING."""
        connection_id = uuid.UUID(data["connection_id"]) if isinstance(data["connection_id"], str) else data["connection_id"]
        external_id = data["external_id"]

        values = {
            "connection_id": connection_id,
            "external_id": external_id,
            "equipment_code": data["equipment_code"],
            "equipment_name": data.get("equipment_name"),
            "status": data["status"],
            "availability": data.get("availability"),
            "performance": data.get("performance"),
            "quality": data.get("quality"),
            "oee": data.get("oee"),
            "downtime_reason": data.get("downtime_reason"),
            "recorded_at": data["recorded_at"],
            "product_line_code": data.get("product_line_code"),
            "mes_raw_data": data.get("raw_data"),
        }
        if factory_id is not None:
            values["factory_id"] = factory_id

        stmt = (
            pg_insert(MESEquipmentStatus)
            .values(**values)
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
    async def _ingest_scrap_record(db: AsyncSession, data: dict, factory_id: uuid.UUID | None = None) -> dict:
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

        values = {
            "connection_id": connection_id,
            "external_id": external_id,
            "order_no": order_no,
            "order_id": order_id,
            "equipment_code": data.get("equipment_code"),
            "defect_type": data["defect_type"],
            "defect_category": data.get("defect_category"),
            "defect_qty": data["defect_qty"],
            "total_qty": data["total_qty"],
            "defect_description": data.get("defect_description"),
            "recorded_at": data["recorded_at"],
            "source_updated_at": data.get("source_updated_at"),
            "product_line_code": data.get("product_line_code"),
            "mes_raw_data": data.get("raw_data"),
        }
        if factory_id is not None:
            values["factory_id"] = factory_id

        update_set = {
            "order_id": func.coalesce(
                MESScrapRecord.order_id,
                pg_insert(MESScrapRecord).excluded.order_id,
            ),
            "order_no": func.coalesce(
                MESScrapRecord.order_no,
                pg_insert(MESScrapRecord).excluded.order_no,
            ),
        }
        if factory_id is not None:
            update_set["factory_id"] = pg_insert(MESScrapRecord).excluded.factory_id

        stmt = (
            pg_insert(MESScrapRecord)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["connection_id", "external_id"],
                set_=update_set,
            )
            .returning(MESScrapRecord.scrap_id)
        )
        result = await db.execute(stmt)
        scrap_id = result.scalar()

        return {"status": "success", "scrap_id": str(scrap_id), "order_id": str(order_id) if order_id else None}


class MESSyncService:
    """MES sync service. 3-phase short transactions to avoid long locks."""

    SYNC_INTERVAL_MINUTES = 5
    OVERLAP_WINDOW_SECONDS = 300
    TIMEOUT_MINUTES = 10
    MAX_FAILURES = 3
    BATCH_SIZE = 100

    CHECKPOINT_FIELDS = {
        "production_orders": ["source_updated_at"],
        "equipment_status": [],  # Full snapshot, no checkpoint
        "scrap_records": ["source_updated_at"],
        "measurements": ["source_updated_at"],
    }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_checkpoint_value(data_type: str, item: dict) -> datetime | None:
        """Extract checkpoint timestamp from item using CHECKPOINT_FIELDS."""
        fields = MESSyncService.CHECKPOINT_FIELDS.get(data_type, [])
        for field in fields:
            value = item.get(field)
            if value is not None:
                if isinstance(value, datetime):
                    return value
                if isinstance(value, str):
                    try:
                        # Handle ISO format with or without timezone
                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        continue
        return None

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    async def create_sync_jobs_for_connection(
        db: AsyncSession, connection_id: uuid.UUID
    ) -> None:
        """Create 4 pending sync jobs for a connection. Caller commits."""
        data_types = ["production_orders", "equipment_status", "scrap_records", "measurements"]
        for dt in data_types:
            job = MESSyncJob(
                connection_id=connection_id,
                data_type=dt,
                status="pending",
                next_run_at=datetime.now(UTC),
            )
            db.add(job)
        await db.flush()

    @staticmethod
    async def claim_jobs(
        db: AsyncSession, connection_id: uuid.UUID | None = None
    ) -> list[MESSyncJob]:
        """Phase 1: SELECT FOR UPDATE SKIP LOCKED.

        - Join mes_connections, filter is_active=True
        - Filter: status in (pending, failed) OR (status=completed AND next_run_at <= now())
        - Optional connection_id filter (for testing/manual sync)
        - Limit BATCH_SIZE
        - Set status=running, started_at=now(), claim_token=str(uuid.uuid4())
        - Return jobs (caller must commit)
        """
        now = datetime.now(UTC)

        # Build the subquery for eligible jobs with FOR UPDATE SKIP LOCKED

        stmt = (
            select(MESSyncJob)
            .join(MESConnection, MESSyncJob.connection_id == MESConnection.connection_id)
            .where(
                MESConnection.is_active == True,  # noqa: E712
                (
                    (MESSyncJob.status.in_(["pending", "failed"]))
                    | (
                        (MESSyncJob.status == "completed")
                        & (MESSyncJob.next_run_at <= now)
                    )
                ),
            )
            .order_by(MESSyncJob.next_run_at)
            .limit(MESSyncService.BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )

        if connection_id is not None:
            stmt = stmt.where(MESSyncJob.connection_id == connection_id)

        result = await db.execute(stmt)
        jobs = result.scalars().all()

        claim_token = str(uuid.uuid4())
        for job in jobs:
            job.status = "running"
            job.started_at = now
            job.claim_token = claim_token

        await db.flush()
        return list(jobs)

    @staticmethod
    async def recover_stuck_jobs(
        db: AsyncSession, connection_id: uuid.UUID | None = None
    ) -> int:
        """Find running jobs with started_at < now() - 10 minutes.

        Reset to failed, clear claim_token.
        Return count (caller must commit).
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=MESSyncService.TIMEOUT_MINUTES)

        stmt = (
            select(MESSyncJob)
            .where(
                MESSyncJob.status == "running",
                MESSyncJob.started_at < cutoff,
            )
            .with_for_update()
        )

        if connection_id is not None:
            stmt = stmt.where(MESSyncJob.connection_id == connection_id)

        result = await db.execute(stmt)
        jobs = result.scalars().all()

        for job in jobs:
            job.status = "failed"
            job.claim_token = None
            job.error_message = f"Job timed out after {MESSyncService.TIMEOUT_MINUTES} minutes"
            job.consecutive_failures += 1

        await db.flush()
        return len(jobs)

    # ------------------------------------------------------------------
    # Single job sync (3-phase)
    # ------------------------------------------------------------------

    @staticmethod
    async def _sync_single_job(db: AsyncSession, job: MESSyncJob) -> None:
        """Phase 2a: Read connection config in short read-only tx.
        Phase 2b: External fetch (NO transaction).
        Phase 3: Write results in short tx.
        """
        # Phase 2a: Read connection config in short read-only session
        connection_id = job.connection_id
        async with get_tenant_aware_session() as read_session:
            result = await read_session.execute(
                select(MESConnection).where(MESConnection.connection_id == connection_id)
            )
            connection = result.scalar_one()
            connector_type = connection.connector_type
            config = connection.config
            product_line_code = connection.product_line_code
            factory_id = connection.factory_id

        # Phase 2b: External fetch (NO transaction)
        connector = get_mes_connector_by_config(connector_type, config)
        checkpoint = job.checkpoint

        if job.data_type == "production_orders":
            items = await connector.fetch_production_orders(checkpoint)
        elif job.data_type == "equipment_status":
            items = await connector.fetch_equipment_status()
        elif job.data_type == "scrap_records":
            items = await connector.fetch_scrap_records(checkpoint)
        elif job.data_type == "measurements":
            items = await connector.fetch_measurements(checkpoint)
        else:
            raise ValueError(f"Unsupported data_type: {job.data_type}")

        if hasattr(connector, "close"):
            await connector.close()

        # Phase 3: Write results in short tx (using provided db session)
        # Refresh job AND verify claim_token ownership
        result = await db.execute(
            select(MESSyncJob)
            .where(MESSyncJob.job_id == job.job_id)
            .with_for_update()
        )
        refreshed_job = result.scalar_one()

        if refreshed_job.claim_token != job.claim_token:
            raise ValueError("Job claim token mismatch — job was stolen by another worker")

        max_ts: datetime | None = None
        for item in items:
            item["connection_id"] = connection_id
            item["product_line_code"] = product_line_code

            # Route to appropriate ingestion method
            if job.data_type == "production_orders":
                await MESIngestionService._ingest_production_order(db, item, factory_id=factory_id)
            elif job.data_type == "equipment_status":
                await MESIngestionService._ingest_equipment_status(db, item, factory_id=factory_id)
            elif job.data_type == "scrap_records":
                await MESIngestionService._ingest_scrap_record(db, item, factory_id=factory_id)
            elif job.data_type == "measurements":
                await MESIngestionService._ingest_measurement(db, item, factory_id=factory_id)

            # Track max timestamp for checkpoint
            ts = MESSyncService._get_checkpoint_value(job.data_type, item)
            if ts is not None:
                if max_ts is None or ts > max_ts:
                    max_ts = ts

        # Update job status
        now = datetime.now(UTC)
        refreshed_job.status = "completed"
        refreshed_job.claim_token = None
        refreshed_job.checkpoint = max_ts if max_ts is not None else refreshed_job.checkpoint
        refreshed_job.next_run_at = now + timedelta(minutes=MESSyncService.SYNC_INTERVAL_MINUTES)
        refreshed_job.completed_at = now
        refreshed_job.consecutive_failures = 0
        refreshed_job.error_message = None

        await db.flush()

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    @staticmethod
    async def run_sync_round(
        db: AsyncSession, connection_id: uuid.UUID | None = None
    ) -> None:
        """Recover stuck jobs, claim jobs, and sync each one."""
        # Recover stuck jobs + commit
        recovered = await MESSyncService.recover_stuck_jobs(db, connection_id)
        if recovered:
            await db.commit()

        # Claim jobs + commit
        jobs = await MESSyncService.claim_jobs(db, connection_id)
        if jobs:
            await db.commit()

        # For each job: try/except, call _sync_single_job
        for job in jobs:
            try:
                # Each job gets its own short write session
                async with get_tenant_aware_session() as job_session:
                    await MESSyncService._sync_single_job(job_session, job)
                    await job_session.commit()
            except Exception as e:
                # On exception: update job to failed in separate session, verify claim_token
                async with get_tenant_aware_session() as fail_session:
                    result = await fail_session.execute(
                        select(MESSyncJob)
                        .where(MESSyncJob.job_id == job.job_id)
                        .with_for_update()
                    )
                    failed_job = result.scalar_one()

                    if failed_job.claim_token != job.claim_token:
                        # Job was stolen, skip
                        await fail_session.rollback()
                        continue

                    failed_job.status = "failed"
                    failed_job.error_message = str(e)
                    failed_job.claim_token = None
                    failed_job.consecutive_failures += 1

                    if failed_job.consecutive_failures >= MESSyncService.MAX_FAILURES:
                        # Deactivate connection
                        conn_result = await fail_session.execute(
                            select(MESConnection).where(
                                MESConnection.connection_id == job.connection_id
                            )
                        )
                        connection = conn_result.scalar_one()
                        connection.is_active = False

                        # Create AuditLog
                        audit = AuditLog(
                            table_name="mes_connections",
                            record_id=job.connection_id,
                            action="mes_deactivated",
                            new_values={
                                "reason": "consecutive_failures_exceeded",
                                "last_error": str(e),
                                "job_id": str(job.job_id),
                            },
                            operated_by=None,
                        )
                        fail_session.add(audit)

                    await fail_session.commit()

    @staticmethod
    async def manual_sync(
        db: AsyncSession, connection_id: uuid.UUID
    ) -> dict:
        """Check if any running job for connection — if so, raise ValueError.

        Set all completed/failed jobs to pending with next_run_at=now().
        Commit. Return 202 (async — background worker picks up).
        """
        # Check if any running job for connection
        result = await db.execute(
            select(MESSyncJob).where(
                MESSyncJob.connection_id == connection_id,
                MESSyncJob.status == "running",
            )
        )
        running = result.scalar_one_or_none()
        if running is not None:
            raise ValueError("Sync already in progress")

        # Set all completed/failed jobs to pending with next_run_at=now()
        now = datetime.now(UTC)
        await db.execute(
            sa_update(MESSyncJob)
            .where(
                MESSyncJob.connection_id == connection_id,
                MESSyncJob.status.in_(["completed", "failed"]),
            )
            .values(status="pending", next_run_at=now)
        )

        await db.commit()
        return {"status": "accepted"}


class MESPushService:
    """MES reverse push service (outbox pattern). 3-phase short transactions."""

    OUTBOX_TIMEOUT_MINUTES = 10
    BATCH_SIZE = 100

    @staticmethod
    async def push_event(
        db: AsyncSession, event_type: str, connection_id: uuid.UUID, payload: dict
    ) -> MESPushOutbox:
        """Create outbox record with status='pending'. Caller commits."""
        outbox = MESPushOutbox(
            event_type=event_type,
            connection_id=connection_id,
            payload=payload,
            status="pending",
        )
        db.add(outbox)
        await db.flush()
        return outbox

    @staticmethod
    async def recover_stuck_outbox(
        db: AsyncSession, connection_id: uuid.UUID | None = None
    ) -> int:
        """Find processing items with started_at < now() - 10 minutes.

        Reset to pending, clear started_at and claim_token.
        Return count (caller must commit).
        """
        cutoff = datetime.now(UTC) - timedelta(
            minutes=MESPushService.OUTBOX_TIMEOUT_MINUTES
        )

        stmt = (
            select(MESPushOutbox)
            .where(
                MESPushOutbox.status == "processing",
                MESPushOutbox.started_at < cutoff,
            )
            .with_for_update()
        )

        if connection_id is not None:
            stmt = stmt.where(MESPushOutbox.connection_id == connection_id)

        result = await db.execute(stmt)
        items = result.scalars().all()

        for item in items:
            item.status = "pending"
            item.started_at = None
            item.claim_token = None

        await db.flush()
        return len(items)

    @staticmethod
    async def claim_items(db: AsyncSession) -> list[MESPushOutbox]:
        """Phase 2: SELECT FOR UPDATE SKIP LOCKED.

        - Join mes_connections, filter is_active=True
        - Filter: status=pending AND next_retry_at <= now()
        - Limit BATCH_SIZE
        - Set status=processing, started_at=now(), claim_token=str(uuid.uuid4())
        - Return items (caller must commit to release locks)
        """
        now = datetime.now(UTC)

        stmt = (
            select(MESPushOutbox)
            .join(MESConnection, MESPushOutbox.connection_id == MESConnection.connection_id)
            .where(
                MESConnection.is_active == True,  # noqa: E712
                MESPushOutbox.status == "pending",
                MESPushOutbox.next_retry_at <= now,
            )
            .order_by(MESPushOutbox.next_retry_at)
            .limit(MESPushService.BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )

        result = await db.execute(stmt)
        items = result.scalars().all()

        for item in items:
            item.status = "processing"
            item.started_at = now
            item.claim_token = str(uuid.uuid4())

        await db.flush()
        return list(items)

    @staticmethod
    async def process_outbox(db: AsyncSession) -> None:
        """3-phase outbox processing.

        Step 1: recover_stuck_outbox + commit
        Step 2: claim items + commit (release locks)
        Step 3: For each item: read config, HTTP push, write result.
        """
        # Step 1: recover stuck items + commit
        recovered = await MESPushService.recover_stuck_outbox(db)
        if recovered:
            await db.commit()

        # Step 2: claim items + commit
        items = await MESPushService.claim_items(db)
        if not items:
            return
        await db.commit()

        # Step 3: process each item independently
        for item in items:
            try:
                await MESPushService._process_single_item(item)
            except Exception as e:
                # On exception: mark as failed in separate session, verify claim_token
                async with get_tenant_aware_session() as fail_session:
                    result = await fail_session.execute(
                        select(MESPushOutbox)
                        .where(MESPushOutbox.outbox_id == item.outbox_id)
                        .with_for_update()
                    )
                    failed_item = result.scalar_one_or_none()

                    if failed_item is None or failed_item.claim_token != item.claim_token:
                        # Item was stolen or deleted, skip
                        await fail_session.rollback()
                        continue

                    failed_item.retry_count += 1
                    failed_item.last_error = str(e)

                    if failed_item.retry_count >= failed_item.max_retries:
                        failed_item.status = "failed"
                        failed_item.claim_token = None
                    else:
                        failed_item.status = "pending"
                        backoff_minutes = 2 ** min(failed_item.retry_count, 5)
                        failed_item.next_retry_at = datetime.now(UTC) + timedelta(
                            minutes=backoff_minutes
                        )
                        failed_item.claim_token = None

                    await fail_session.commit()

    @staticmethod
    async def _process_single_item(item: MESPushOutbox) -> None:
        """3a: Read config. 3b: HTTP push. 3c: Write result."""
        # 3a: Copy data to memory (short read tx)
        async with get_tenant_aware_session() as read_session:
            result = await read_session.execute(
                select(MESPushOutbox).where(
                    MESPushOutbox.outbox_id == item.outbox_id,
                    MESPushOutbox.claim_token == item.claim_token,
                    MESPushOutbox.status == "processing",
                )
            )
            verified = result.scalar_one_or_none()
            if verified is None:
                # Item no longer ours or no longer processing
                return

            result = await read_session.execute(
                select(MESConnection).where(
                    MESConnection.connection_id == item.connection_id
                )
            )
            connection = result.scalar_one()
            connector_type = connection.connector_type
            config = connection.config

        # 3b: HTTP push (NO transaction)
        connector = get_mes_connector_by_config(connector_type, config)
        try:
            await connector.push_quality_event(
                item.event_type,
                item.payload,
                event_id=str(item.outbox_id),
            )
            push_success = True
            error_msg = None
        except Exception as e:
            push_success = False
            error_msg = str(e)
        finally:
            if hasattr(connector, "close"):
                await connector.close()

        # 3c: Write result (short tx)
        async with get_tenant_aware_session() as write_session:
            result = await write_session.execute(
                select(MESPushOutbox)
                .where(MESPushOutbox.outbox_id == item.outbox_id)
                .with_for_update()
            )
            refreshed = result.scalar_one()

            if refreshed.claim_token != item.claim_token:
                raise ValueError("Outbox claim token mismatch — item was stolen by another worker")

            if push_success:
                refreshed.status = "sent"
                refreshed.sent_at = datetime.now(UTC)
                refreshed.claim_token = None
                refreshed.last_error = None
            else:
                refreshed.retry_count += 1
                refreshed.last_error = error_msg

                if refreshed.retry_count >= refreshed.max_retries:
                    refreshed.status = "failed"
                    refreshed.claim_token = None
                else:
                    refreshed.status = "pending"
                    backoff_minutes = 2 ** min(refreshed.retry_count, 5)
                    refreshed.next_retry_at = datetime.now(UTC) + timedelta(
                        minutes=backoff_minutes
                    )
                    refreshed.claim_token = None

            await write_session.commit()


class MESLifecycleService:
    """MES data lifecycle management.
    - Equipment status: 90-day retention
    - Scrap records: 1-year retention, aggregate to monthly summary before delete
    - Closed orders: 2-year archive to mes_production_orders_archive
    """

    DEFAULT_EQUIPMENT_DAYS = 90
    DEFAULT_SCRAP_DAYS = 365
    DEFAULT_CLOSED_ORDER_DAYS = 730

    @staticmethod
    def _get_retention_days(connection_config: dict) -> dict:
        ret = connection_config.get("retention", {})
        if not isinstance(ret, dict):
            ret = {}
        return {
            "equipment_status_days": ret.get("equipment_status_days", MESLifecycleService.DEFAULT_EQUIPMENT_DAYS),
            "scrap_days": ret.get("scrap_days", MESLifecycleService.DEFAULT_SCRAP_DAYS),
            "closed_order_days": ret.get("closed_order_days", MESLifecycleService.DEFAULT_CLOSED_ORDER_DAYS),
        }

    @staticmethod
    async def cleanup(db: AsyncSession) -> dict:
        from sqlalchemy import delete, text
        now = datetime.now(UTC)

        # Transaction-level advisory lock (auto-released on commit/rollback)
        lock_result = await db.execute(text("SELECT pg_try_advisory_xact_lock(42)"))
        has_lock = lock_result.scalar()
        if not has_lock:
            return {"deleted_equipment_status": 0, "deleted_scrap_records": 0, "aggregated_scrap_rows": 0, "archived_orders": 0}

        # Load ALL connections (active + inactive)
        result = await db.execute(select(MESConnection))
        connections = result.scalars().all()

        total_deleted_equipment = 0
        total_deleted_scrap = 0
        total_aggregated = 0
        total_archived = 0

        for conn in connections:
            retention = MESLifecycleService._get_retention_days(conn.config)

            # 1. Clean old equipment status
            cutoff_equipment = now - timedelta(days=retention["equipment_status_days"])
            eq_result = await db.execute(
                delete(MESEquipmentStatus)
                .where(MESEquipmentStatus.connection_id == conn.connection_id)
                .where(MESEquipmentStatus.recorded_at < cutoff_equipment)
            )
            total_deleted_equipment += eq_result.rowcount

            # 2. Aggregate and clean old scrap records
            cutoff_scrap = now - timedelta(days=retention["scrap_days"])
            agg_result = await db.execute(text("""
                INSERT INTO mes_scrap_monthly_summary
                    (connection_id, product_line_code, year_month, defect_category,
                     total_defect_qty, total_total_qty, record_count, created_at)
                SELECT
                    connection_id,
                    COALESCE(product_line_code, '__none__'),
                    TO_CHAR(recorded_at, 'YYYY-MM'),
                    COALESCE(defect_category, '未知'),
                    SUM(defect_qty),
                    SUM(total_qty),
                    COUNT(*),
                    NOW()
                FROM mes_scrap_records
                WHERE connection_id = :cid AND recorded_at < :cutoff
                GROUP BY connection_id, COALESCE(product_line_code, '__none__'),
                         TO_CHAR(recorded_at, 'YYYY-MM'),
                         COALESCE(defect_category, '未知')
                ON CONFLICT (connection_id, product_line_code, year_month, defect_category)
                DO UPDATE SET
                    total_defect_qty = mes_scrap_monthly_summary.total_defect_qty + EXCLUDED.total_defect_qty,
                    total_total_qty = mes_scrap_monthly_summary.total_total_qty + EXCLUDED.total_total_qty,
                    record_count = mes_scrap_monthly_summary.record_count + EXCLUDED.record_count
            """), {"cid": conn.connection_id, "cutoff": cutoff_scrap})
            total_aggregated += agg_result.rowcount

            sc_result = await db.execute(
                delete(MESScrapRecord)
                .where(MESScrapRecord.connection_id == conn.connection_id)
                .where(MESScrapRecord.recorded_at < cutoff_scrap)
            )
            total_deleted_scrap += sc_result.rowcount

            # 3. Archive closed orders
            cutoff_order = now - timedelta(days=retention["closed_order_days"])
            await db.execute(text("""
                INSERT INTO mes_production_orders_archive
                    (order_id, connection_id, order_no, product_model, process_route,
                     planned_qty, actual_qty, status, started_at, completed_at,
                     source_updated_at, product_line_code, archived_at)
                SELECT
                    order_id, connection_id, order_no, product_model, process_route,
                    planned_qty, actual_qty, status, started_at, completed_at,
                    source_updated_at, product_line_code, NOW()
                FROM mes_production_orders
                WHERE connection_id = :cid AND status = 'closed' AND completed_at < :cutoff
                ON CONFLICT (order_id) DO NOTHING
            """), {"cid": conn.connection_id, "cutoff": cutoff_order})

            arc_result = await db.execute(
                delete(MESProductionOrder)
                .where(MESProductionOrder.connection_id == conn.connection_id)
                .where(MESProductionOrder.status == "closed")
                .where(MESProductionOrder.completed_at < cutoff_order)
            )
            total_archived += arc_result.rowcount

        await db.commit()

        return {
            "deleted_equipment_status": total_deleted_equipment,
            "deleted_scrap_records": total_deleted_scrap,
            "aggregated_scrap_rows": total_aggregated,
            "archived_orders": total_archived,
        }
