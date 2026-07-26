"""CPSyncWorker: durable outbox consumer for FMEA-approval -> CP sync_pending.

Run: python -m app.services.cp_sync_worker
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.cp_sync_outbox import CPSyncOutbox
from app.services.control_plan_service import apply_cp_sync_pending

logger = logging.getLogger(__name__)
POLL_INTERVAL = 5
BATCH_SIZE = 10
_BACKOFF = {1: 10, 2: 30, 3: 90, 4: 270}


async def process_cp_sync_outbox_batch(db: AsyncSession, batch_size: int = BATCH_SIZE) -> int:
    now = datetime.now(UTC)
    rows = (await db.execute(
        select(CPSyncOutbox)
        .where(CPSyncOutbox.status == "pending", CPSyncOutbox.next_attempt_at <= now)
        .order_by(CPSyncOutbox.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )).scalars().all()
    processed = 0
    for row in rows:
        try:
            user_id = uuid.UUID(row.payload["user_id"]) if row.payload.get("user_id") else None
            await apply_cp_sync_pending(db, row, user_id)
            row.status = "completed"
            row.processed_at = datetime.now(UTC)
            processed += 1
        except Exception as e:  # noqa: BLE001
            row.attempt_count += 1
            row.last_error = f"{type(e).__name__}: {e}"
            if row.attempt_count >= row.max_attempts:
                row.status = "dead"
            else:
                row.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=_BACKOFF.get(row.attempt_count, 270)
                )
        await db.commit()
    return processed


async def _loop() -> None:
    while True:
        async with async_session() as db:
            try:
                await process_cp_sync_outbox_batch(db)
            except Exception:  # noqa: BLE001
                logger.exception("cp_sync batch failed")
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(_loop())
