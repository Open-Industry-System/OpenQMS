import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.graph.repository import FMEAGraphRepository
from app.graph.deps import get_graph_repository


class SimilarNodeOut(BaseModel):
    node_id: str
    name: str
    type: str
    fmea_id: str
    document_no: str


class HighAPNodeOut(BaseModel):
    node_id: str
    name: str
    ap: str
    rpn: int
    fmea_id: str
    document_no: str


class TopFailureModeOut(BaseModel):
    name: str
    rpn: int
    fmea_id: str
    document_no: str


class CrossFmeaStatsOut(BaseModel):
    total_fmeas: int
    total_nodes: int
    node_type_distribution: dict[str, int]
    ap_distribution: dict[str, int]
    high_ap_nodes: list[HighAPNodeOut]
    avg_rpn: float
    top_failure_modes: list[TopFailureModeOut]

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/fmea/{fmea_id}/impact/{node_id}")
async def impact_chain(
    fmea_id: uuid.UUID,
    node_id: str,
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    _user: User = Depends(get_current_user),
):
    """下游影响链：从指定节点出发追踪失效效应和控制措施。"""
    return await repo.get_impact_chain(fmea_id, node_id)


@router.get("/fmea/{fmea_id}/cause/{node_id}")
async def cause_chain(
    fmea_id: uuid.UUID,
    node_id: str,
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    _user: User = Depends(get_current_user),
):
    """上游原因链：从指定节点出发追踪失效原因。"""
    return await repo.get_cause_chain(fmea_id, node_id)


@router.get("/similar", response_model=list[SimilarNodeOut])
async def similar_nodes(
    node_type: str = Query(..., description="节点类型，如 FailureMode"),
    name_keyword: str = Query(..., min_length=1, description="名称关键词"),
    product_line_code: str = Query(..., min_length=1, description="产品线代码（必填，租户隔离）"),
    limit: int = Query(20, ge=1, le=100),
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    _user: User = Depends(get_current_user),
):
    """跨 FMEA 搜索相似节点。product_line_code 必填且不能为空字符串。返回白名单字段。"""
    product_line_code = product_line_code.strip()
    name_keyword = name_keyword.strip()
    if not product_line_code:
        raise HTTPException(status_code=422, detail="product_line_code cannot be empty")
    if not name_keyword:
        raise HTTPException(status_code=422, detail="name_keyword cannot be empty")
    return await repo.find_similar_nodes(node_type, name_keyword, product_line_code, limit)


@router.get("/stats", response_model=CrossFmeaStatsOut)
async def cross_fmea_stats(
    product_line_code: str = Query(..., min_length=1, description="产品线代码（必填，租户隔离）"),
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    _user: User = Depends(get_current_user),
):
    """跨 FMEA 聚合统计。product_line_code 必填且不能为空字符串。返回白名单字段。"""
    product_line_code = product_line_code.strip()
    if not product_line_code:
        raise HTTPException(status_code=422, detail="product_line_code cannot be empty")
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
