"""PLM business logic services.

Provides:
- PLMIngestionService: idempotent upsert of parts, BOMs, change orders with
  side-effect creation of SC links and impact tasks.
- PLMSyncService: sync job lifecycle management and connector-driven sync rounds.
- PLMChangeImpactWorker: claim, recover, and process change-impact analysis tasks.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SYSTEM_USER_ID
from app.database import async_session
from app.models.plm import (
    PLMBOM,
    PLMChangeImpactTask,
    PLMChangeOrder,
    PLMConnection,
    PLMPart,
    PLMPartSCLink,
    PLMSyncJob,
)
from app.services.plm_connector import get_plm_connector

logger = logging.getLogger(__name__)

# How long (minutes) before a "running" job/task is considered stale.
STALE_MINUTES = 10


# ---------------------------------------------------------------------------
# PLMIngestionService
# ---------------------------------------------------------------------------


class PLMIngestionService:
    """Idempotent ingestion of PLM data into the database.

    Each call to ``ingest`` processes a single item dict keyed by
    ``data_type`` ("part", "bom", or "change_order").  Upsert semantics
    guarantee idempotency.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest(self, data: dict) -> None:
        """Ingest a single PLM data item.

        ``data`` must contain at least ``data_type``, ``connection_id``
        (UUID or str), and the fields relevant to the type.
        """
        data_type = data["data_type"]
        connection_id = _to_uuid(data["connection_id"])

        # Load connection to get factory_id (background sync has no request context)
        conn_result = await self._db.execute(
            select(PLMConnection).where(PLMConnection.connection_id == connection_id)
        )
        connection = conn_result.scalar_one_or_none()
        factory_id = connection.factory_id if connection else None

        if data_type == "part":
            await self._ingest_part(connection_id, data, factory_id=factory_id)
        elif data_type == "bom":
            await self._ingest_bom(connection_id, data, factory_id=factory_id)
        elif data_type == "change_order":
            await self._ingest_change_order(connection_id, data, factory_id=factory_id)
        else:
            logger.warning("Unknown PLM data_type: %s", data_type)

        await self._db.flush()

    # ------------------------------------------------------------------
    # Parts
    # ------------------------------------------------------------------

    async def _ingest_part(self, connection_id: uuid.UUID, data: dict, factory_id: uuid.UUID | None = None) -> None:
        raw_fields = _extract_raw(data, _PART_COLUMNS)
        values = {
            "part_id": uuid.uuid4(),
            "connection_id": connection_id,
            "external_id": data.get("external_id", ""),
            "part_number": data["part_number"],
            "name": data.get("name", data["part_number"]),
            "revision": data.get("revision", "A"),
            "material": data.get("material"),
            "specification": data.get("specification"),
            "status": data.get("status", "active"),
            "is_safety_related": data.get("is_safety_related", False),
            "is_key_characteristic": data.get("is_key_characteristic", False),
            "source_updated_at": _parse_dt(data.get("source_updated_at")),
            "product_line_code": data.get("product_line_code"),
            "plm_raw_data": raw_fields or None,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id

        update_set = {
            "external_id": data.get("external_id", ""),
            "name": data.get("name", data["part_number"]),
            "material": data.get("material"),
            "specification": data.get("specification"),
            "status": data.get("status", "active"),
            "is_safety_related": data.get("is_safety_related", False),
            "is_key_characteristic": data.get("is_key_characteristic", False),
            "source_updated_at": _parse_dt(data.get("source_updated_at")),
            "product_line_code": data.get("product_line_code"),
            "plm_raw_data": raw_fields or None,
        }
        if factory_id is not None:
            update_set["factory_id"] = factory_id

        stmt = (
            pg_insert(PLMPart)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["connection_id", "part_number", "revision"],
                set_=update_set,
            )
        )
        await self._db.execute(stmt)

        # Side-effect: keep pending SC links aligned with current PLM flags.
        if data.get("is_safety_related"):
            await self._upsert_sc_link(connection_id, data, "safety")
        else:
            await self._delete_pending_sc_link(connection_id, data, "safety")
        if data.get("is_key_characteristic"):
            await self._upsert_sc_link(connection_id, data, "key_characteristic")
        else:
            await self._delete_pending_sc_link(connection_id, data, "key_characteristic")

    async def _upsert_sc_link(
        self,
        connection_id: uuid.UUID,
        data: dict,
        characteristic_type: str,
    ) -> None:
        """Upsert PLMPartSCLink for a safety-related or key-characteristic part."""
        # Resolve the part_id via RETURNING on the part upsert, or fall back to
        # a lookup.  Using a deterministic lookup avoids the race where the
        # INSERT for the part has flushed but the SELECT here sees a stale
        # snapshot in READ COMMITTED.
        part_id = data.get("_resolved_part_id")
        if part_id is None:
            part_result = await self._db.execute(
                select(PLMPart.part_id).where(
                    PLMPart.connection_id == connection_id,
                    PLMPart.part_number == data["part_number"],
                    PLMPart.revision == data.get("revision", "A"),
                )
            )
            part_id = part_result.scalar_one_or_none()
            if part_id is None:
                return  # Part not found after upsert -- should not happen

        product_line_code = data.get("product_line_code")
        if not product_line_code:
            # Resolve from connection
            conn_result = await self._db.execute(
                select(PLMConnection.product_line_code).where(
                    PLMConnection.connection_id == connection_id
                )
            )
            product_line_code = conn_result.scalar_one_or_none()
            if not product_line_code:
                return

        stmt = (
            pg_insert(PLMPartSCLink)
            .values(
                link_id=uuid.uuid4(),
                part_id=part_id,
                sc_id=None,
                characteristic_type=characteristic_type,
                status="pending",
                product_line_code=product_line_code,
            )
            .on_conflict_do_update(
                index_elements=["part_id", "characteristic_type"],
                set_={
                    "status": "pending",
                    "sc_id": None,
                    "confirmed_by": None,
                    "confirmed_at": None,
                },
                where=PLMPartSCLink.status != "confirmed",
            )
        )
        await self._db.execute(stmt)

    async def _delete_pending_sc_link(
        self,
        connection_id: uuid.UUID,
        data: dict,
        characteristic_type: str,
    ) -> None:
        """Remove stale unconfirmed SC requests when PLM flags are turned off."""
        part_id_subquery = (
            select(PLMPart.part_id)
            .where(
                PLMPart.connection_id == connection_id,
                PLMPart.part_number == data["part_number"],
                PLMPart.revision == data.get("revision", "A"),
            )
            .scalar_subquery()
        )
        await self._db.execute(
            delete(PLMPartSCLink).where(
                PLMPartSCLink.part_id == part_id_subquery,
                PLMPartSCLink.characteristic_type == characteristic_type,
                PLMPartSCLink.status == "pending",
            )
        )

    # ------------------------------------------------------------------
    # BOMs
    # ------------------------------------------------------------------

    async def _ingest_bom(self, connection_id: uuid.UUID, data: dict, factory_id: uuid.UUID | None = None) -> None:
        raw_fields = _extract_raw(data, _BOM_COLUMNS)
        values = {
            "bom_id": uuid.uuid4(),
            "connection_id": connection_id,
            "external_id": data.get("external_id", ""),
            "parent_part_number": data["parent_part_number"],
            "parent_revision": data.get("parent_revision", "A"),
            "child_part_number": data["child_part_number"],
            "child_revision": data.get("child_revision", "A"),
            "quantity": data.get("quantity", 1),
            "bom_revision": data.get("bom_revision", "A"),
            "level": data.get("level", 1),
            "source_updated_at": _parse_dt(data.get("source_updated_at")),
            "product_line_code": data.get("product_line_code"),
            "plm_raw_data": raw_fields or None,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id

        update_set = {
            "external_id": data.get("external_id", ""),
            "quantity": data.get("quantity", 1),
            "level": data.get("level", 1),
            "source_updated_at": _parse_dt(data.get("source_updated_at")),
            "product_line_code": data.get("product_line_code"),
            "plm_raw_data": raw_fields or None,
        }
        if factory_id is not None:
            update_set["factory_id"] = factory_id

        stmt = (
            pg_insert(PLMBOM)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[
                    "connection_id",
                    "parent_part_number",
                    "parent_revision",
                    "child_part_number",
                    "child_revision",
                    "bom_revision",
                ],
                set_=update_set,
            )
        )
        await self._db.execute(stmt)

    # ------------------------------------------------------------------
    # Change orders
    # ------------------------------------------------------------------

    async def _ingest_change_order(
        self, connection_id: uuid.UUID, data: dict, factory_id: uuid.UUID | None = None
    ) -> None:
        raw_fields = _extract_raw(data, _CO_COLUMNS)

        new_status = data.get("status", "draft")

        # Determine whether to create/reset impact task: only when the
        # change order is *transitioning* to "approved" -- not when it is
        # already approved (avoids resetting in-progress tasks).
        create_impact_task = False
        if new_status == "approved":
            existing_result = await self._db.execute(
                select(PLMChangeOrder.status).where(
                    PLMChangeOrder.connection_id == connection_id,
                    PLMChangeOrder.change_number == data["change_number"],
                )
            )
            current_status = existing_result.scalar_one_or_none()
            # Create/reset task only when transitioning TO approved
            create_impact_task = current_status != "approved"

        values = {
            "change_id": uuid.uuid4(),
            "connection_id": connection_id,
            "external_id": data.get("external_id", ""),
            "change_number": data["change_number"],
            "title": data.get("title", ""),
            "description": data.get("description"),
            "change_type": data.get("change_type", ""),
            "status": new_status,
            "priority": data.get("priority", "normal"),
            "affected_part_numbers": data.get("affected_part_numbers", []),
            "proposed_changes": data.get("proposed_changes"),
            "requested_by": data.get("requested_by"),
            "approved_by": data.get("approved_by"),
            "planned_implementation_date": _parse_dt(
                data.get("planned_implementation_date")
            ),
            "actual_implementation_date": _parse_dt(
                data.get("actual_implementation_date")
            ),
            "source_updated_at": _parse_dt(data.get("source_updated_at")),
            "product_line_code": data.get("product_line_code"),
            "plm_raw_data": raw_fields or None,
        }
        if factory_id is not None:
            values["factory_id"] = factory_id

        update_set = {
            "external_id": data.get("external_id", ""),
            "title": data.get("title", ""),
            "description": data.get("description"),
            "change_type": data.get("change_type", ""),
            "status": new_status,
            "priority": data.get("priority", "normal"),
            "affected_part_numbers": data.get(
                "affected_part_numbers", []
            ),
            "proposed_changes": data.get("proposed_changes"),
            "requested_by": data.get("requested_by"),
            "approved_by": data.get("approved_by"),
            "planned_implementation_date": _parse_dt(
                data.get("planned_implementation_date")
            ),
            "actual_implementation_date": _parse_dt(
                data.get("actual_implementation_date")
            ),
            "source_updated_at": _parse_dt(
                data.get("source_updated_at")
            ),
            "product_line_code": data.get("product_line_code"),
            "plm_raw_data": raw_fields or None,
        }
        if factory_id is not None:
            update_set["factory_id"] = factory_id

        stmt = (
            pg_insert(PLMChangeOrder)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["connection_id", "change_number"],
                set_=update_set,
            )
        )
        await self._db.execute(stmt)

        # Side-effect: create/reset impact task when transitioning to approved
        if create_impact_task:
            await self._upsert_impact_task(connection_id, data)

    async def _upsert_impact_task(
        self, connection_id: uuid.UUID, data: dict
    ) -> None:
        """Upsert PLMChangeImpactTask for an approved change order."""
        co_result = await self._db.execute(
            select(PLMChangeOrder.change_id).where(
                PLMChangeOrder.connection_id == connection_id,
                PLMChangeOrder.change_number == data["change_number"],
            )
        )
        change_id = co_result.scalar_one_or_none()
        if change_id is None:
            return

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
                started_at=None,
                completed_at=None,
                error_message=None,
                result=None,
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
        await self._db.execute(stmt)


# Known columns for each model to separate user data from raw payload.
_PART_COLUMNS = {
    "external_id", "part_number", "name", "revision", "material",
    "specification", "status", "is_safety_related", "is_key_characteristic",
    "source_updated_at", "product_line_code", "connection_id", "data_type",
    "factory_id",
}
_BOM_COLUMNS = {
    "external_id", "parent_part_number", "parent_revision",
    "child_part_number", "child_revision", "quantity", "bom_revision",
    "level", "source_updated_at", "product_line_code", "connection_id",
    "data_type", "factory_id",
}
_CO_COLUMNS = {
    "external_id", "change_number", "title", "description", "change_type",
    "status", "priority", "affected_part_numbers", "proposed_changes",
    "requested_by", "approved_by", "planned_implementation_date",
    "actual_implementation_date", "source_updated_at", "product_line_code",
    "connection_id", "data_type", "factory_id",
}


def _extract_raw(data: dict, known_columns: set[str]) -> dict:
    """Return keys from *data* that are not in the known-column set."""
    return {k: v for k, v in data.items() if k not in known_columns}


def _to_uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # ISO-8601 string
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            logger.warning("Failed to parse datetime: %s", value)
            return None
    return None


# ---------------------------------------------------------------------------
# PLMSyncService
# ---------------------------------------------------------------------------


class PLMSyncService:
    """Manages sync job lifecycle for PLM connections."""

    @staticmethod
    async def create_sync_jobs_for_connection(
        db: AsyncSession, connection_id: uuid.UUID
    ) -> None:
        """Create sync job rows for each data type if they don't already exist."""
        now = datetime.now(timezone.utc)
        for data_type in ("part", "bom", "change_order"):
            stmt = (
                pg_insert(PLMSyncJob)
                .values(
                    job_id=uuid.uuid4(),
                    connection_id=connection_id,
                    data_type=data_type,
                    status="pending",
                    next_run_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=["connection_id", "data_type"]
                )
            )
            await db.execute(stmt)
        await db.flush()

    @staticmethod
    async def run_sync_round(
        db: AsyncSession,
        connection_id: uuid.UUID | None = None,
    ) -> int:
        """Claim available sync jobs, run them, return count of processed jobs.

        Claims jobs where:
        - status == "pending"
        - OR (status == "running" and started_at older than STALE_MINUTES)
        - OR (status == "failed" and next_run_at <= now)
        """
        now = datetime.now(timezone.utc)
        claim_token = str(uuid.uuid4())
        stale_threshold = now - timedelta(minutes=STALE_MINUTES)

        # Claim eligible jobs
        claim_stmt = (
            select(PLMSyncJob)
            .where(
                (PLMSyncJob.status == "pending")
                | (
                    (PLMSyncJob.status == "running")
                    & (PLMSyncJob.started_at < stale_threshold)
                )
                | (
                    (PLMSyncJob.status == "failed")
                    & (PLMSyncJob.next_run_at <= now)
                )
            )
        )
        if connection_id is not None:
            claim_stmt = claim_stmt.where(PLMSyncJob.connection_id == connection_id)
        claim_stmt = (
            claim_stmt
            .order_by(PLMSyncJob.next_run_at)
            .limit(10)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(claim_stmt)
        jobs = list(result.scalars().all())

        if not jobs:
            return 0

        for job in jobs:
            job.status = "running"
            job.claim_token = claim_token
            job.started_at = now
            job.error_message = None
        await db.flush()

        processed = 0
        for job in jobs:
            try:
                await _run_single_sync_job(db, job, claim_token)
                processed += 1
            except Exception as exc:
                logger.error(
                    "Sync job %s (connection=%s, type=%s) failed: %s",
                    job.job_id, job.connection_id, job.data_type, exc,
                    exc_info=True,
                )
                job.status = "failed"
                job.error_message = str(exc)[:2000]
                job.claim_token = None
                job.consecutive_failures += 1
                # Exponential backoff: 1 min * 2^failures, capped at 1 hour
                backoff = min(60 * (2 ** job.consecutive_failures), 3600)
                job.next_run_at = now + timedelta(seconds=backoff)
                await db.flush()

        # Commit all failure-path status updates so they persist even if the
        # caller does not call db.commit() (e.g. fire-and-forget round).
        await db.commit()

        return processed

    @staticmethod
    async def manual_sync(
        db: AsyncSession, connection_id: uuid.UUID
    ) -> int:
        """Trigger sync for a connection immediately.

        Creates jobs if needed, resets failed/pending, then runs a round.
        """
        # Ensure jobs exist
        await PLMSyncService.create_sync_jobs_for_connection(db, connection_id)

        now = datetime.now(timezone.utc)
        # Reset eligible jobs to pending
        await db.execute(
            update(PLMSyncJob)
            .where(
                PLMSyncJob.connection_id == connection_id,
                PLMSyncJob.status.in_(["failed", "pending", "completed"]),
            )
            .values(
                status="pending",
                claim_token=None,
                error_message=None,
                next_run_at=now,
            )
        )
        await db.flush()

        return await PLMSyncService.run_sync_round(db, connection_id=connection_id)


async def _run_single_sync_job(
    db: AsyncSession, job: PLMSyncJob, claim_token: str
) -> None:
    """Execute a single sync job using a three-phase pattern.

    Phase 1 (short txn): Read connection config and job state, then commit.
    Phase 2 (outside txn): Fetch data from the PLM connector.
    Phase 3 (short txn): Ingest results using PLMIngestionService with
        periodic commits to keep transactions small.
    """
    # --- Phase 1: read connection + job config in short transaction ---
    conn_result = await db.execute(
        select(PLMConnection).where(
            PLMConnection.connection_id == job.connection_id
        )
    )
    connection = conn_result.scalar_one_or_none()
    if connection is None:
        raise ValueError(f"PLM connection not found: {job.connection_id}")

    since = job.checkpoint or datetime(2000, 1, 1, tzinfo=timezone.utc)
    data_type = job.data_type

    await db.commit()

    # --- Phase 2: external fetch outside transaction ---
    connector = get_plm_connector(connection, None)
    try:
        if data_type == "part":
            items = await connector.fetch_parts(since)
        elif data_type == "bom":
            items = await connector.fetch_boms(since)
        elif data_type == "change_order":
            items = await connector.fetch_change_orders(since)
        else:
            items = []
    finally:
        await connector.close()

    # --- Phase 3: ingest results in short transaction(s) ---
    BATCH_SIZE = 50
    now = datetime.now(timezone.utc)

    async with async_session() as ingest_db:
        ingestion = PLMIngestionService(ingest_db)
        for i, item in enumerate(items):
            # Copy to avoid mutating the caller's dict; inject metadata keys.
            row = dict(
                item,
                data_type=data_type,
                connection_id=job.connection_id,
                product_line_code=item.get("product_line_code") or connection.product_line_code,
            )
            await ingestion.ingest(row)
            # Periodic commit to keep transaction size bounded
            if (i + 1) % BATCH_SIZE == 0:
                await ingest_db.commit()

        # Final commit for remaining items
        await ingest_db.commit()

    # Update job status on success (re-fetch in the caller's session)
    async with async_session() as update_db:
        result = await update_db.execute(
            select(PLMSyncJob).where(PLMSyncJob.job_id == job.job_id)
        )
        refreshed_job = result.scalar_one_or_none()
        if refreshed_job is not None:
            refreshed_job.status = "completed"
            refreshed_job.checkpoint = now
            refreshed_job.completed_at = now
            refreshed_job.next_run_at = now + timedelta(minutes=5)
            refreshed_job.claim_token = None
            refreshed_job.error_message = None
            refreshed_job.consecutive_failures = 0
            await update_db.commit()


# ---------------------------------------------------------------------------
# PLMChangeImpactWorker
# ---------------------------------------------------------------------------


class PLMChangeImpactWorker:
    """Processes PLMChangeImpactTask rows via ChangeImpactService.analyze().

    Each analysis runs in its own transaction (independent async_session)
    because ChangeImpactService.analyze() commits internally.
    """

    @staticmethod
    async def claim_tasks(db: AsyncSession) -> list[PLMChangeImpactTask]:
        """Claim pending tasks using SELECT FOR UPDATE SKIP LOCKED.

        Caller must commit the returned session after processing to persist
        the claim state.  Tasks are claimed with status="running" and a
        unique claim_token; the caller should mark them completed/failed
        before or at commit time.
        """
        claim_token = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        stmt = (
            select(PLMChangeImpactTask)
            .where(PLMChangeImpactTask.status == "pending")
            .where(PLMChangeImpactTask.next_retry_at <= now)
            .order_by(PLMChangeImpactTask.next_retry_at)
            .limit(5)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(stmt)
        tasks = list(result.scalars().all())

        for task in tasks:
            task.status = "running"
            task.claim_token = claim_token
            task.started_at = now
            task.error_message = None

        await db.flush()
        return tasks

    @staticmethod
    async def recover_stuck_tasks(
        db: AsyncSession, timeout_minutes: int = STALE_MINUTES
    ) -> int:
        """Reset tasks stuck in 'running' longer than *timeout_minutes* back to pending.

        The update is flushed but NOT committed.  The caller must commit
        the session for the recovery to take effect; this keeps the method
        composable with other transactional work in the same round.
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

        result = await db.execute(
            update(PLMChangeImpactTask)
            .where(
                PLMChangeImpactTask.status == "running",
                PLMChangeImpactTask.started_at < threshold,
            )
            .values(
                status="pending",
                claim_token=None,
                error_message=None,
            )
        )
        await db.flush()
        return result.rowcount

    @staticmethod
    async def process_task(db: AsyncSession, task: PLMChangeImpactTask) -> None:
        """Process a single impact task.

        Fetches the associated change order, resolves affected FMEAs, and
        runs ChangeImpactService.analyze() for each affected node in an
        independent session (because analyze() commits internally).
        """
        # Verify we still own this task
        check_result = await db.execute(
            select(PLMChangeImpactTask).where(
                PLMChangeImpactTask.task_id == task.task_id,
                PLMChangeImpactTask.claim_token == task.claim_token,
                PLMChangeImpactTask.status == "running",
            )
        )
        owned_task = check_result.scalar_one_or_none()
        if owned_task is None:
            logger.warning(
                "Task %s no longer owned by this worker, skipping", task.task_id
            )
            return

        # Fetch change order
        co_result = await db.execute(
            select(PLMChangeOrder).where(
                PLMChangeOrder.change_id == task.change_id
            )
        )
        change_order = co_result.scalar_one_or_none()
        if change_order is None:
            owned_task.status = "failed"
            owned_task.error_message = "Change order not found"
            owned_task.claim_token = None
            owned_task.completed_at = datetime.now(timezone.utc)
            await db.flush()
            return

        warnings: list[str] = []
        analysis_ids: list[str] = []

        try:
            # Resolve affected FMEA documents and nodes via the part numbers
            affected_parts = change_order.affected_part_numbers or []
            if not affected_parts:
                warnings.append("No affected part numbers in change order")
                owned_task.status = "completed"
                owned_task.result = {
                    "warnings": warnings,
                    "analysis_ids": analysis_ids,
                }
                owned_task.claim_token = None
                owned_task.completed_at = datetime.now(timezone.utc)
                await db.flush()
                return

            # Parse "PART_NUMBER|REVISION" entries and build queries
            from app.models.plm import PLMPartFMEALink

            part_filters = []
            for part_ref in affected_parts:
                if "|" in str(part_ref):
                    pn, rev = str(part_ref).split("|", 1)
                    part_filters.append(
                        (PLMPart.part_number == pn, PLMPart.revision == rev)
                    )
                else:
                    part_filters.append(
                        (PLMPart.part_number == str(part_ref),)
                    )

            # Find FMEA links for affected parts
            links: list = []
            for pf in part_filters:
                filter_conditions = [
                    PLMPart.connection_id == change_order.connection_id,
                    *pf,
                ]
                links_result = await db.execute(
                    select(PLMPartFMEALink).join(
                        PLMPart, PLMPartFMEALink.part_id == PLMPart.part_id
                    ).where(*filter_conditions)
                )
                links.extend(links_result.scalars().all())

            if not links:
                warnings.append(
                    f"No FMEA links found for parts: {', '.join(str(p) for p in affected_parts)}"
                )

            for link in links:
                try:
                    # Use an independent session because analyze() commits internally
                    async with async_session() as analysis_db:
                        from app.services.change_impact_service import (
                            ChangeImpactService,
                        )

                        svc = ChangeImpactService(analysis_db)
                        resp = await svc.analyze(
                            fmea_id=link.fmea_id,
                            node_id=link.node_id,
                            node_type="plm_change",
                            node_name=change_order.title,
                            change_type=change_order.change_type,
                            field_name=None,
                            new_value=None,
                            old_value=None,
                            user_id=SYSTEM_USER_ID,
                        )
                        analysis_ids.append(str(resp.id))
                except Exception as analysis_exc:
                    msg = (
                        f"Analysis failed for FMEA {link.fmea_id} "
                        f"node {link.node_id}: {analysis_exc}"
                    )
                    logger.warning(msg)
                    warnings.append(msg)

            # Re-verify ownership before writing result (session may have been
            # away for a while during analysis).
            recheck = await db.execute(
                select(PLMChangeImpactTask).where(
                    PLMChangeImpactTask.task_id == task.task_id,
                    PLMChangeImpactTask.claim_token == task.claim_token,
                )
            )
            still_owned = recheck.scalar_one_or_none()
            if still_owned is None:
                logger.warning(
                    "Task %s claim lost during processing, discarding results",
                    task.task_id,
                )
                return

            still_owned.status = "completed"
            still_owned.result = {
                "warnings": warnings,
                "analysis_ids": analysis_ids,
            }
            still_owned.claim_token = None
            still_owned.completed_at = datetime.now(timezone.utc)
            await db.flush()

        except Exception as exc:
            logger.error(
                "Impact task %s failed: %s", task.task_id, exc, exc_info=True
            )
            # Re-verify ownership
            recheck = await db.execute(
                select(PLMChangeImpactTask).where(
                    PLMChangeImpactTask.task_id == task.task_id,
                    PLMChangeImpactTask.claim_token == task.claim_token,
                )
            )
            still_owned = recheck.scalar_one_or_none()
            if still_owned is not None:
                still_owned.retry_count += 1
                still_owned.error_message = str(exc)[:2000]
                if still_owned.retry_count < still_owned.max_retries:
                    # Re-queue with exponential backoff (1 min * 2^retry_count)
                    still_owned.status = "pending"
                    backoff = min(60 * (2 ** still_owned.retry_count), 3600)
                    still_owned.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                    still_owned.claim_token = None
                else:
                    # Exhausted retries – mark permanently failed
                    still_owned.status = "failed"
                    still_owned.claim_token = None
                    still_owned.completed_at = datetime.now(timezone.utc)
                await db.flush()
