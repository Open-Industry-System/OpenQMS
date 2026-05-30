import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.graph.repository import FMEAGraphRepository
from app.graph.jsonb_repository import JSONBRepository

router = APIRouter(prefix="/api/graph", tags=["graph"])


async def _repo(db: AsyncSession = Depends(get_db)) -> FMEAGraphRepository:
    """根据 GRAPH_REPOSITORY 配置选择实现。"""
    if settings.GRAPH_REPOSITORY == "neo4j":
        from app.graph.neo4j_driver import get_neo4j_driver
        from app.graph.neo4j_repository import Neo4jRepository
        driver = await get_neo4j_driver()
        return Neo4jRepository(driver)
    return JSONBRepository(db)


@router.get("/fmea/{fmea_id}/impact/{node_id}")
async def impact_chain(
    fmea_id: uuid.UUID,
    node_id: str,
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """下游影响链：从指定节点出发追踪失效效应和控制措施。"""
    return await repo.get_impact_chain(fmea_id, node_id)


@router.get("/fmea/{fmea_id}/cause/{node_id}")
async def cause_chain(
    fmea_id: uuid.UUID,
    node_id: str,
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """上游原因链：从指定节点出发追踪失效原因。"""
    return await repo.get_cause_chain(fmea_id, node_id)


@router.get("/similar")
async def similar_nodes(
    node_type: str = Query(..., description="节点类型，如 FailureMode"),
    name_keyword: str = Query(..., min_length=1, description="名称关键词"),
    product_line_code: str = Query(..., description="产品线代码（必填，租户隔离）"),
    limit: int = Query(20, ge=1, le=100),
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """跨 FMEA 搜索相似节点。product_line_code 必填。"""
    return await repo.find_similar_nodes(node_type, name_keyword, product_line_code, limit)


@router.get("/stats")
async def cross_fmea_stats(
    product_line_code: str = Query(..., description="产品线代码（必填，租户隔离）"),
    repo: FMEAGraphRepository = Depends(_repo),
    _user: User = Depends(get_current_user),
):
    """跨 FMEA 聚合统计。product_line_code 必填。"""
    return await repo.get_cross_fmea_stats(product_line_code)


@router.post("/rebuild")
async def trigger_rebuild(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_admin),
):
    """触发全量重建 (admin only)。异步执行，秒回防超时。"""
    async def _do_rebuild():
        from app.services.graph_projection_service import GraphProjectionService
        from app.graph.neo4j_driver import get_neo4j_driver
        from app.database import async_session

        driver = await get_neo4j_driver()
        projection = GraphProjectionService(driver, async_session)
        await projection.full_rebuild()

    background_tasks.add_task(_do_rebuild)
    return {"message": "Graph rebuild started in background"}
