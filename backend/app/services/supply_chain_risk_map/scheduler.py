"""Background scheduler for supply chain risk map snapshots.

Uses pg_try_advisory_xact_lock (transaction-level) for concurrency control
so only one instance generates snapshots at a time. Transaction-level locks
are automatically released on commit/rollback, preventing lock leaks across
connection pool reuse.
"""
import asyncio
import logging

from sqlalchemy import text

from app.database import run_for_each_tenant
from app.services.supply_chain_risk_map.service import current_period, generate_snapshot

logger = logging.getLogger(__name__)

LOCK_ID = 20260611  # Unique advisory lock ID for risk map scheduler
SLEEP_SECONDS = 3600  # Run hourly


async def _try_acquire_xact_lock(db) -> bool:
    """Try to acquire a transaction-level advisory lock.

    Unlike session-level pg_try_advisory_lock, pg_try_advisory_xact_lock
    is automatically released at transaction end (commit/rollback), so we
    don't need to manually release it. This prevents lock leaks when
    connections are returned to the pool.
    """
    result = await db.execute(text(f"SELECT pg_try_advisory_xact_lock({LOCK_ID})"))
    return result.scalar()


async def snapshot_loop():
    """Main loop: acquire lock, generate snapshot, release session, sleep.

    Each iteration opens a fresh session per tenant via run_for_each_tenant()
    so connections are not held during the sleep interval. The sleep always
    happens outside the session context.
    """
    while True:
        try:
            async for tenant, db in run_for_each_tenant():
                acquired = await _try_acquire_xact_lock(db)
                if acquired:
                    try:
                        period = current_period()
                        count = await generate_snapshot(db, None, period)
                        logger.info(f"Generated {count} snapshots for tenant %s, period {period}", tenant.slug)
                    except Exception:
                        logger.exception("Error generating snapshot for tenant %s", tenant.slug)
                        # Transaction-level lock is released on rollback
                else:
                    logger.debug("Snapshot lock not acquired for tenant %s, skipping", tenant.slug)
        except Exception:
            logger.exception("Error in snapshot loop")
        await asyncio.sleep(SLEEP_SECONDS)