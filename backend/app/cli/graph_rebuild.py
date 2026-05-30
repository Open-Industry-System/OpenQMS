"""全量重建 Neo4j 图投影。

用法:
    python -m app.cli.graph_rebuild              # 全量重建
    python -m app.cli.graph_rebuild --retry-failed  # 重置 dead 任务
"""
import asyncio
import argparse
import sys

from app.database import async_session
from app.graph.neo4j_driver import get_neo4j_driver, ensure_constraints
from app.services.graph_projection_service import GraphProjectionService
from app.models.graph_sync_outbox import GraphSyncOutbox

from sqlalchemy import select, update, func


async def retry_failed() -> int:
    """将 outbox 中 dead 状态的任务重置为 pending。"""
    async with async_session() as db:
        result = await db.execute(
            update(GraphSyncOutbox)
            .where(GraphSyncOutbox.status == "dead")
            .values(status="pending", attempt_count=0, next_attempt_at=func.now())
            .returning(GraphSyncOutbox.id)
        )
        reset_ids = result.scalars().all()
        await db.commit()
    return len(reset_ids)


async def full_rebuild() -> dict:
    """清空 Neo4j 并从 PG 全量重建。"""
    driver = await get_neo4j_driver()
    await ensure_constraints()
    projection = GraphProjectionService(driver, async_session)
    return await projection.full_rebuild()


def main():
    parser = argparse.ArgumentParser(description="Neo4j graph projection rebuild")
    parser.add_argument("--retry-failed", action="store_true", help="Reset dead outbox tasks to pending")
    args = parser.parse_args()

    if args.retry_failed:
        count = asyncio.run(retry_failed())
        print(f"Reset {count} dead tasks to pending.")
    else:
        result = asyncio.run(full_rebuild())
        print(f"Full rebuild complete: {result}")


if __name__ == "__main__":
    main()
