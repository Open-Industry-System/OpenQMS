"""GraphSyncWorker: 异步轮询 outbox 表，投影 FMEA 图数据到 Neo4j。

运行方式:
    python -m app.services.graph_sync_worker
    或 docker compose up graph-worker
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session, get_tenant_aware_session
from app.models.graph_sync_outbox import GraphSyncOutbox
from app.graph.neo4j_driver import get_neo4j_driver, ensure_constraints
from app.services.graph_projection_service import GraphProjectionService

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5
BATCH_SIZE = 10


def backoff_delay(attempt: int) -> int | None:
    """Exponential backoff: 10s → 30s → 90s → 270s。第 5 次返回 None (dead)。"""
    if attempt >= 5:
        return None
    delays = {1: 10, 2: 30, 3: 90, 4: 270}
    return delays.get(attempt, 270)


def deduplicate_tasks(tasks: list[dict]) -> dict[str, list[dict]]:
    """按 aggregate_id 分组，每个 fmea_id 只保留 created_at 最新的一条事件。

    Returns: {"process": [...], "skip": [...]}
    """
    if not tasks:
        return {"process": [], "skip": []}

    latest: dict[str, dict] = {}
    for task in tasks:
        aid = task["aggregate_id"]
        if aid not in latest or task["created_at"] > latest[aid]["created_at"]:
            if aid in latest:
                # 之前的那条要 skip
                pass
            latest[aid] = task

    process = list(latest.values())
    process_ids = {t["id"] for t in process}
    skip = [t for t in tasks if t["id"] not in process_ids]

    return {"process": process, "skip": skip}


async def _poll_and_lock(db: AsyncSession) -> list[GraphSyncOutbox]:
    """使用 PG FOR UPDATE SKIP LOCKED 原子领取一批 pending 任务。

    同时回收超过 10 分钟仍在 processing 的任务（Worker 崩溃残留）。
    """
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(minutes=10)

    # 先回收 stale processing 任务
    await db.execute(
        update(GraphSyncOutbox)
        .where(
            and_(
                GraphSyncOutbox.status == "processing",
                GraphSyncOutbox.locked_at < stale_cutoff,
            )
        )
        .values(status="pending", locked_at=None)
    )
    await db.flush()

    # 领取 pending 任务
    result = await db.execute(
        select(GraphSyncOutbox)
        .where(
            and_(
                GraphSyncOutbox.status == "pending",
                GraphSyncOutbox.next_attempt_at <= now,
            )
        )
        .order_by(GraphSyncOutbox.next_attempt_at)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )
    tasks = list(result.scalars().all())

    if tasks:
        task_ids = [t.id for t in tasks]
        await db.execute(
            update(GraphSyncOutbox)
            .where(GraphSyncOutbox.id.in_(task_ids))
            .values(status="processing", locked_at=now)
        )
        await db.commit()

    return tasks


async def _cleanup_stale_processing() -> int:
    """将 status='processing' 且超过 10 分钟的任务重置为 pending。

    Worker 启动时调用，清理上次崩溃残留。
    """
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with get_tenant_aware_session() as db:
        result = await db.execute(
            update(GraphSyncOutbox)
            .where(
                and_(
                    GraphSyncOutbox.status == "processing",
                    GraphSyncOutbox.locked_at < stale_cutoff,
                )
            )
            .values(status="pending", locked_at=None)
            .returning(GraphSyncOutbox.id)
        )
        reset_ids = list(result.scalars().all())
        await db.commit()
    return len(reset_ids)


async def _mark_completed(db: AsyncSession, task_id: uuid.UUID) -> None:
    await db.execute(
        update(GraphSyncOutbox)
        .where(GraphSyncOutbox.id == task_id)
        .values(status="completed", processed_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def _mark_failed(db: AsyncSession, task: GraphSyncOutbox, error: str) -> None:
    new_attempt = task.attempt_count + 1
    delay = backoff_delay(new_attempt)

    if delay is None:
        # Dead letter
        await db.execute(
            update(GraphSyncOutbox)
            .where(GraphSyncOutbox.id == task.id)
            .values(
                status="dead",
                attempt_count=new_attempt,
                last_error=error,
                processed_at=datetime.now(timezone.utc),
            )
        )
    else:
        await db.execute(
            update(GraphSyncOutbox)
            .where(GraphSyncOutbox.id == task.id)
            .values(
                status="pending",
                attempt_count=new_attempt,
                last_error=error,
                next_attempt_at=datetime.now(timezone.utc) + timedelta(seconds=delay),
            )
        )
    await db.commit()


async def run_worker() -> None:
    """Worker 主入口：无限循环轮询 outbox。"""
    logging.basicConfig(level=logging.INFO)
    logger.info("GraphSyncWorker starting...")

    driver = await get_neo4j_driver()
    await ensure_constraints()
    projection = GraphProjectionService(driver, async_session)

    logger.info("Neo4j connected, constraints ensured. Polling outbox...")

    # 启动时清理上次崩溃残留的 processing 任务
    stale_count = await _cleanup_stale_processing()
    if stale_count:
        logger.info(f"Cleaned up {stale_count} stale processing tasks")

    while True:
        try:
            async with get_tenant_aware_session() as db:
                tasks = await _poll_and_lock(db)

            if not tasks:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # Deduplicate
            task_dicts = [
                {
                    "id": str(t.id),
                    "aggregate_id": str(t.aggregate_id),
                    "event_type": t.event_type,
                    "created_at": t.created_at,
                }
                for t in tasks
            ]
            deduped = deduplicate_tasks(task_dicts)

            # Mark skipped tasks as completed
            process_ids = {t["id"] for t in deduped["process"]}
            for task in tasks:
                if str(task.id) not in process_ids:
                    async with get_tenant_aware_session() as db:
                        await _mark_completed(db, task.id)

            # Process deduplicated tasks
            for task in tasks:
                if str(task.id) not in process_ids:
                    continue
                try:
                    await projection.sync_fmea_to_neo4j(task.aggregate_id)
                    async with get_tenant_aware_session() as db:
                        await _mark_completed(db, task.id)
                    logger.info(f"Synced FMEA {task.aggregate_id} to Neo4j")
                except Exception as e:
                    logger.error(f"Failed to sync FMEA {task.aggregate_id}: {e}")
                    async with get_tenant_aware_session() as db:
                        await _mark_failed(db, task, str(e))

        except Exception as e:
            logger.error(f"Worker poll error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run_worker())
