import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.recommendation import SimilarNodesRequest, SimilarNodesResponse, SimilarNodeMatch
from app.core.permissions import get_user_permission, Module, PermissionLevel
from app.core.deps import RequestScope, get_request_scope
from app.core.factory_scope import check_factory_access
from app.graph.repository import FMEAGraphRepository
from app.graph.deps import get_graph_repository
from app.services import fmea_service


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


class MaskedNodeOut(BaseModel):
    name: str
    ap: str | None = None
    rpn: int


class GlobalStatsOut(BaseModel):
    total_fmeas: int
    total_nodes: int
    node_type_distribution: dict[str, int]
    ap_distribution: dict[str, int]
    avg_rpn: float
    high_ap_nodes: list[MaskedNodeOut]
    top_failure_modes: list[MaskedNodeOut]


def mask_name(name: Any) -> str:
    """安全脱敏：保留前 2 个字符（去除首尾空格后），其余替换为 ***；
    短名称（≤2 字符）仅保留首字符 + ***，防止完整暴露原值。
    非字符串类型直接返回 ***，避免异常类型被意外展示。
    """
    if name is None:
        return "***"
    if not isinstance(name, str):
        return "***"
    name_str = name.strip()
    if not name_str:
        return "***"
    if len(name_str) <= 2:
        return name_str[:1] + "***"
    return name_str[:2] + "***"


def _sanitize_global_stats(raw: dict) -> dict:
    """白名单重建：只保留统计字段，对 name 脱敏，丢弃所有可追溯标识。"""

    def _mask_node(node: dict) -> dict:
        return {
            "name": mask_name(node.get("name", "")),
            "ap": node.get("ap"),
            "rpn": node.get("rpn", 0),
        }

    return {
        "total_fmeas": raw.get("total_fmeas", 0),
        "total_nodes": raw.get("total_nodes", 0),
        "node_type_distribution": raw.get("node_type_distribution", {}),
        "ap_distribution": raw.get("ap_distribution", {}),
        "avg_rpn": raw.get("avg_rpn", 0.0),
        "high_ap_nodes": [_mask_node(n) for n in raw.get("high_ap_nodes", [])],
        "top_failure_modes": [_mask_node(n) for n in raw.get("top_failure_modes", [])],
    }

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/fmea/{fmea_id}/impact/{node_id}")
async def impact_chain(
    fmea_id: uuid.UUID,
    node_id: str,
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """下游影响链：从指定节点出发追踪失效效应和控制措施。"""
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    check_factory_access(fmea.factory_id, scope)
    return await repo.get_impact_chain(fmea_id, node_id)


@router.get("/fmea/{fmea_id}/cause/{node_id}")
async def cause_chain(
    fmea_id: uuid.UUID,
    node_id: str,
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
):
    """上游原因链：从指定节点出发追踪失效原因。"""
    fmea = await fmea_service.get_fmea(db, fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    check_factory_access(fmea.factory_id, scope)
    return await repo.get_cause_chain(fmea_id, node_id)


@router.get("/similar", response_model=list[SimilarNodeOut])
async def similar_nodes(
    node_type: str = Query(..., description="节点类型，如 FailureMode"),
    name_keyword: str = Query(..., min_length=1, description="名称关键词"),
    product_line_code: str = Query(..., min_length=1, description="产品线代码（必填，租户隔离）"),
    limit: int = Query(20, ge=1, le=100),
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    scope: RequestScope = Depends(get_request_scope),
):
    """跨 FMEA 搜索相似节点。product_line_code 必填且不能为空字符串。返回白名单字段。"""
    product_line_code = product_line_code.strip()
    name_keyword = name_keyword.strip()
    if not product_line_code:
        raise HTTPException(status_code=422, detail="product_line_code cannot be empty")
    if not name_keyword:
        raise HTTPException(status_code=422, detail="name_keyword cannot be empty")
    # 产品线访问校验
    if scope.pl_scope.mode == "EXPLICIT" and product_line_code not in (scope.pl_scope.codes or []):
        raise HTTPException(status_code=403, detail="No access to this product line")
    if scope.pl_scope.mode == "NONE":
        raise HTTPException(status_code=403, detail="No product line access")
    return await repo.find_similar_nodes(node_type, name_keyword, product_line_code, limit)


@router.get("/stats", response_model=CrossFmeaStatsOut)
async def cross_fmea_stats(
    product_line_code: str = Query(..., min_length=1, description="产品线代码（必填，租户隔离）"),
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    scope: RequestScope = Depends(get_request_scope),
):
    """跨 FMEA 聚合统计。product_line_code 必填且不能为空字符串。返回白名单字段。"""
    product_line_code = product_line_code.strip()
    if not product_line_code:
        raise HTTPException(status_code=422, detail="product_line_code cannot be empty")
    # 产品线访问校验
    if scope.pl_scope.mode == "EXPLICIT" and product_line_code not in (scope.pl_scope.codes or []):
        raise HTTPException(status_code=403, detail="No access to this product line")
    if scope.pl_scope.mode == "NONE":
        raise HTTPException(status_code=403, detail="No product line access")
    return await repo.get_cross_fmea_stats(product_line_code)


@router.get("/global-stats", response_model=GlobalStatsOut, response_model_exclude_none=True)
async def global_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    scope: RequestScope = Depends(get_request_scope),
):
    """跨产品线全局知识库统计（Admin Only）。返回数据已脱敏。
    不接受 product_line_code 参数，传入则返回 400。
    """
    level = await get_user_permission(scope.user, Module.KNOWLEDGE_GRAPH, db)
    if level < PermissionLevel.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    if "product_line_code" in request.query_params:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="product_line_code is not accepted for global stats",
        )
    raw = await repo.get_global_stats()
    return _sanitize_global_stats(raw)


@router.post("/similar-nodes", response_model=SimilarNodesResponse)
async def similar_nodes_advanced(
    req: SimilarNodesRequest,
    db: AsyncSession = Depends(get_db),
    repo: FMEAGraphRepository = Depends(get_graph_repository),
    scope: RequestScope = Depends(get_request_scope),
):
    """跨 FMEA 相似节点搜索（增强版，用于调试和预览）。
    无 KNOWLEDGE_GRAPH 权限时，global scope 强制降级为 current_product_line。
    """

    # 产品线访问校验
    if scope.pl_scope.mode == "EXPLICIT":
        if req.product_line_code not in (scope.pl_scope.codes or []):
            raise HTTPException(status_code=403, detail="No access to this product line")

    # scope 强制降级
    has_kg = await get_user_permission(scope.user, Module.KNOWLEDGE_GRAPH, db) >= PermissionLevel.VIEW
    effective_scope = "current_product_line" if (not has_kg and req.scope == "global") else req.scope

    matches = await repo.find_similar_nodes_advanced(
        node_type=req.node_type,
        query_text=req.query_text,
        scope=effective_scope,
        product_line_code=req.product_line_code,
        limit=req.limit,
        min_similarity=req.min_similarity,
    )

    # 防御性脱敏：无全局权限用户的跨产品线节点
    current_pl = req.product_line_code
    result_matches = []
    for m in matches:
        name = m["name"]
        if not has_kg and m.get("product_line_code") != current_pl:
            name = mask_name(name)
        result_matches.append(SimilarNodeMatch(
            node_id=m["node_id"],
            name=name,
            node_type=m["type"],
            fmea_id=m["fmea_id"],
            document_no=m["document_no"],
            product_line_code=m.get("product_line_code"),
            product_line_name=m.get("product_line_name"),
            similarity_score=m["similarity_score"],
            match_reason=m["match_reason"],
        ))

    return SimilarNodesResponse(
        matches=result_matches,
        total=len(result_matches),
        effective_scope=effective_scope,
    )


@router.post("/rebuild")
async def trigger_rebuild(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """触发全量重建 (admin only)。异步执行，秒回防超时。"""
    level = await get_user_permission(scope.user, Module.KNOWLEDGE_GRAPH, db)
    if level < PermissionLevel.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    async def _do_rebuild():
        from app.services.graph_projection_service import GraphProjectionService
        from app.graph.neo4j_driver import get_neo4j_driver
        from app.database import async_session

        driver = await get_neo4j_driver()
        projection = GraphProjectionService(driver, async_session)
        await projection.full_rebuild()

    background_tasks.add_task(_do_rebuild)
    return {"message": "Graph rebuild started in background"}
