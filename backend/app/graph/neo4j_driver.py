from neo4j import AsyncGraphDatabase, AsyncDriver
from app.config import settings

_driver: AsyncDriver | None = None


async def get_neo4j_driver() -> AsyncDriver:
    """获取或创建 Neo4j async driver 单例。"""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


async def close_neo4j_driver() -> None:
    """关闭 Neo4j driver 连接池。"""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def ensure_constraints() -> None:
    """创建 Neo4j 唯一性约束和索引（幂等）。"""
    driver = await get_neo4j_driver()
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        await session.run(
            "CREATE CONSTRAINT fmea_doc_id IF NOT EXISTS "
            "FOR (d:FMEDocument) REQUIRE d.fmea_id IS UNIQUE"
        )
        await session.run(
            "CREATE CONSTRAINT graph_node_id IF NOT EXISTS "
            "FOR (n:GraphNode) REQUIRE (n.fmea_id, n.node_id) IS UNIQUE"
        )
        await session.run(
            "CREATE INDEX graph_node_fmea IF NOT EXISTS "
            "FOR (n:GraphNode) ON (n.fmea_id)"
        )
        await session.run(
            "CREATE INDEX graph_node_type IF NOT EXISTS "
            "FOR (n:GraphNode) ON (n.type)"
        )
        await session.run(
            "CREATE INDEX graph_node_product_line IF NOT EXISTS "
            "FOR (n:GraphNode) ON (n.product_line_code)"
        )
