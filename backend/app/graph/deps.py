from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.graph.repository import FMEAGraphRepository


async def get_graph_repository(
    db: AsyncSession = Depends(get_db),
) -> FMEAGraphRepository:
    """根据 GRAPH_REPOSITORY 配置选择 Neo4j 或 JSONB 实现。"""
    if settings.GRAPH_REPOSITORY == "neo4j":
        from app.graph.neo4j_driver import get_neo4j_driver
        from app.graph.neo4j_repository import Neo4jRepository
        driver = await get_neo4j_driver()
        return Neo4jRepository(driver)
    from app.graph.jsonb_repository import JSONBRepository
    return JSONBRepository(db)
