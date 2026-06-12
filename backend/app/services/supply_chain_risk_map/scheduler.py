"""Background scheduler for supply chain risk map snapshots.

Uses pg_try_advisory_lock for concurrency control so only one instance
generates snapshots at a time. Sessions are released before sleep to
avoid holding connections idle.
"""
import asyncio
import logging
from sqlalchemy import text
from app.database import async_session
from app.services.supply_chain_risk_map.service import generate_snapshot, current_period

logger = logging.getLogger(__name__)

LOCK_ID = 20260611  # Unique advisory lock ID for risk map scheduler
SLEEP_SECONDS = 3600  # Run hourly


async def _acquire_snapshot_lock(db) -> bool:
    """Try to acquire the advisory lock. Returns True if acquired."""
    result = await db.execute(text(f"SELECT pg_try_advisory_lock({LOCK_ID})"))
    return result.scalar()


async def _release_snapshot_lock(db) -> bool:
    """Release the advisory lock. Returns True if released."""
    result = await db.execute(text(f"SELECT pg_advisory_unlock({LOCK_ID})"))
    return result.scalar()


async def snapshot_loop():
    """Main loop: acquire lock, generate snapshot, release session, sleep.

    Each iteration opens a fresh session so connections are not held
    during the sleep interval. The sleep always happens outside the
    session context.
    """
    while True:
        try:
            acquired = False
            async with async_session() as db:
                acquired = await _acquire_snapshot_lock(db)
                if acquired:
                    try:
                        period = current_period()
                        count = await generate_snapshot(db, None, period)
                        logger.info(f"Generated {count} snapshots for {period}")
                    finally:
                        await _release_snapshot_lock(db)
                else:
                    logger.debug("Snapshot lock not acquired, skipping")
            # Session is released before sleep — connections not held idle
        except Exception:
            logger.exception("Error in snapshot loop")
        await asyncio.sleep(SLEEP_SECONDS)