"""GraphProjectionService: 将 FMEA JSONB graph_data 映射为 Neo4j Cypher 语句。

核心逻辑是 build_cypher_sync()：给定一个 FMEA 文档的完整数据，生成一组
(Cypher, params) 元组，worker 逐条执行实现幂等投影。
"""
import uuid
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# ── 白名单：防止用户输入直接进入 Cypher ──

ALLOWED_NODE_TYPES: set[str] = {
    "ProcessItem", "System", "ProcessStep", "Subsystem",
    "ProcessWorkElement", "Component",
    "ProcessItemFunction", "ProcessStepFunction", "ProcessWorkElementFunction",
    "Function",
    "FailureMode", "FailureEffect", "FailureCause",
    "PreventionControl", "DetectionControl",
    "RecommendedAction",
}

NODE_TYPE_LABEL_MAP: dict[str, str] = {
    "PreventionControl": "Control",
    "DetectionControl": "Control",
    # 其他类型保持原名
}

ALLOWED_EDGE_TYPES: set[str] = {
    "HAS_PROCESS_STEP", "HAS_WORK_ELEMENT", "HAS_FUNCTION",
    "FUNCTION_MAPPED_TO", "HAS_FAILURE_MODE",
    "EFFECT_OF", "CAUSE_OF",
    "PREVENTED_BY", "DETECTED_BY", "OPTIMIZED_BY",
    "HAS_NODE",
}


def _node_properties(node: dict) -> dict[str, Any]:
    """从 GraphNode JSONB 提取 Neo4j 节点属性。"""
    props: dict[str, Any] = {
        "node_id": node["id"],
        "name": node.get("name", ""),
        "type": node["type"],
    }
    for key in ("process_number", "classification", "requirement", "specification",
                "severity", "occurrence", "detection", "ap",
                "revised_severity", "revised_occurrence", "revised_detection", "revised_ap",
                "severity_plant", "severity_customer", "severity_user",
                "responsible", "due_date", "status", "action_taken", "completion_date"):
        val = node.get(key)
        if val is not None and val != 0 and val != "":
            props[key] = val

    if node["type"] in ("PreventionControl", "DetectionControl"):
        props["control_type"] = "prevention" if node["type"] == "PreventionControl" else "detection"

    return props


def build_cypher_sync(
    fmea_id: str,
    document_no: str,
    title: str,
    fmea_type: str,
    product_line_code: str,
    product_line_name: str,
    status: str,
    version: int,
    graph_data: dict,
) -> list[tuple[str, dict]]:
    """为单个 FMEA 文档生成完整的 Neo4j 投影 Cypher 语句序列。

    策略：逐条生成简单、参数化的 Cypher（不用动态字符串拼接标签/关系类型）。
    每个 (cypher, params) 对应一条独立语句，在同一个 Neo4j transaction 中顺序执行。

    Returns: [(cypher, params), ...] — 按顺序在同一个 Neo4j write transaction 中执行即为幂等同步。
    """
    statements: list[tuple[str, dict]] = []

    # Step 1: DELETE existing projection for this fmea_id
    statements.append((
        "MATCH (n) WHERE n.fmea_id = $fmea_id DETACH DELETE n",
        {"fmea_id": fmea_id},
    ))

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    if not nodes:
        return statements

    # Step 2: CREATE FMEDocument node
    statements.append((
        "CREATE (d:FMEDocument {fmea_id: $fmea_id, document_no: $document_no, "
        "title: $title, fmea_type: $fmea_type, product_line_code: $product_line_code, "
        "product_line_name: $product_line_name, "
        "status: $status, version: $version})",
        {
            "fmea_id": fmea_id,
            "document_no": document_no,
            "title": title,
            "fmea_type": fmea_type,
            "product_line_code": product_line_code,
            "product_line_name": product_line_name,
            "status": status,
            "version": version,
        },
    ))

    # Step 3: CREATE each GraphNode (逐条，标签在白名单内直接拼接)
    for node in nodes:
        raw_type = node.get("type", "")
        if raw_type not in ALLOWED_NODE_TYPES:
            logger.warning(f"Skipping unknown node type: {raw_type}")
            continue

        label = NODE_TYPE_LABEL_MAP.get(raw_type, raw_type)
        props = _node_properties(node)
        props["fmea_id"] = fmea_id
        props["product_line_code"] = product_line_code

        statements.append((
            f"CREATE (n:GraphNode:{label}) SET n += $props",
            {"props": props},
        ))

        # Step 3b: CREATE (:FMEDocument)-[:HAS_NODE]->(:GraphNode)
        statements.append((
            "MATCH (d:FMEDocument {fmea_id: $fmea_id}), "
            f"(n:GraphNode {{fmea_id: $fmea_id, node_id: $node_id}}) "
            "CREATE (d)-[:HAS_NODE]->(n)",
            {"fmea_id": fmea_id, "node_id": node["id"]},
        ))

    # Step 4: CREATE edges — MATCH by (fmea_id, node_id) for exact binding
    # edge_index 保持原始顺序，Neo4j 查询 ORDER BY rel.edge_index 可稳定取第一条
    node_ids = {n["id"] for n in nodes if n.get("type") in ALLOWED_NODE_TYPES}
    for edge_idx, edge in enumerate(edges):
        edge_type = edge.get("type", "")
        source = edge.get("source", "")
        target = edge.get("target", "")

        if edge_type not in ALLOWED_EDGE_TYPES:
            logger.warning(f"Skipping unknown edge type: {edge_type}")
            continue
        if source not in node_ids or target not in node_ids:
            continue

        statements.append((
            f"MATCH (s:GraphNode {{fmea_id: $fmea_id, node_id: $source}}), "
            f"(t:GraphNode {{fmea_id: $fmea_id, node_id: $target}}) "
            f"CREATE (s)-[:{edge_type} {{edge_index: $edge_index}}]->(t)",
            {"fmea_id": fmea_id, "source": source, "target": target, "edge_index": edge_idx},
        ))

    return statements


class GraphProjectionService:
    """JSONB → Neo4j 投影服务。"""

    def __init__(self, neo4j_driver, db_session_factory):
        self._driver = neo4j_driver
        self._session_factory = db_session_factory

    async def sync_fmea_to_neo4j(self, fmea_id: uuid.UUID) -> None:
        """从 PG 读取 FMEA → 生成 Cypher → 执行到 Neo4j。"""
        from app.models.fmea import FMEADocument
        from app.models.product_line import ProductLine
        from sqlalchemy import select

        async with self._session_factory() as db:
            result = await db.execute(
                select(FMEADocument).where(FMEADocument.fmea_id == fmea_id)
            )
            fmea = result.scalar_one_or_none()
            if fmea is None:
                return

            # 获取产品线名称
            pl_result = await db.execute(
                select(ProductLine.name).where(ProductLine.code == fmea.product_line_code)
            )
            product_line_name = pl_result.scalar_one_or_none() or fmea.product_line_code

        statements = build_cypher_sync(
            fmea_id=str(fmea.fmea_id),
            document_no=fmea.document_no,
            title=fmea.title,
            fmea_type=fmea.fmea_type,
            product_line_code=fmea.product_line_code,
            product_line_name=product_line_name,
            status=fmea.status,
            version=fmea.version,
            graph_data=fmea.graph_data or {"nodes": [], "edges": []},
        )

        async def _tx(tx):
            for cypher, params in statements:
                result = await tx.run(cypher, params)
                await result.consume()  # 确保每条语句执行完成并检查错误

        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            await session.execute_write(_tx)

    async def full_rebuild(self) -> dict:
        """全量重建：清空 Neo4j + 遍历所有 FMEA 逐个同步。"""
        from app.models.fmea import FMEADocument
        from sqlalchemy import select, func

        total = 0
        synced = 0
        failed = 0

        # 清空 Neo4j
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            await session.run("MATCH (n) DETACH DELETE n")

        # 重新创建约束
        from app.graph.neo4j_driver import ensure_constraints
        await ensure_constraints()

        # 遍历所有 FMEA
        async with self._session_factory() as db:
            count_result = await db.execute(select(func.count(FMEADocument.fmea_id)))
            total = count_result.scalar() or 0

            result = await db.execute(select(FMEADocument))
            fmeas = result.scalars().all()

        for fmea in fmeas:
            try:
                await self.sync_fmea_to_neo4j(fmea.fmea_id)
                synced += 1
            except Exception:
                failed += 1

        return {"total": total, "synced": synced, "failed": failed}
