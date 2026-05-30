"""Neo4j 实现：使用 Cypher 查询图投影。

需要 worker 同步完成后数据才可用。
"""
import uuid
from typing import Any

from neo4j import AsyncDriver

from app.graph.repository import FMEAGraphRepository
from app.config import settings


class Neo4jRepository(FMEAGraphRepository):
    def __init__(self, driver: AsyncDriver):
        self._driver = driver

    async def get_impact_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                "MATCH path = (start:GraphNode {fmea_id: $fmea_id, node_id: $node_id})"
                "-[*1..3]->(end:GraphNode) "
                "RETURN nodes(path) AS ns, relationships(path) AS rs",
                fmea_id=str(fmea_id), node_id=node_id,
            )
            return await self._path_result_to_dict(result)

    async def get_cause_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                "MATCH path = (start:GraphNode {fmea_id: $fmea_id, node_id: $node_id})"
                "<-[*1..3]-(end:GraphNode) "
                "RETURN nodes(path) AS ns, relationships(path) AS rs",
                fmea_id=str(fmea_id), node_id=node_id,
            )
            return await self._path_result_to_dict(result)

    async def find_similar_nodes(
        self, node_type: str, name_keyword: str, product_line_code: str, limit: int = 20
    ) -> list[dict]:
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                "MATCH (n:GraphNode) "
                "WHERE n.type = $node_type AND n.product_line_code = $product_line_code "
                "AND toLower(n.name) CONTAINS toLower($keyword) "
                "RETURN n.node_id AS node_id, n.name AS name, n.type AS type, "
                "n.fmea_id AS fmea_id "
                "LIMIT $limit",
                node_type=node_type, product_line_code=product_line_code,
                keyword=name_keyword, limit=limit,
            )
            records = await result.data()
            return records

    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            # 节点类型分布
            type_result = await session.run(
                "MATCH (n:GraphNode) WHERE n.product_line_code = $pl "
                "RETURN n.type AS type, count(*) AS cnt "
                "ORDER BY cnt DESC",
                pl=product_line_code,
            )
            type_records = await type_result.data()
            type_dist = {r["type"]: r["cnt"] for r in type_records}

            # 高风险失效模式
            risk_result = await session.run(
                "MATCH (n:GraphNode:FailureMode) WHERE n.product_line_code = $pl "
                "AND n.severity * n.occurrence * n.detection >= 100 "
                "RETURN n.name AS name, n.severity * n.occurrence * n.detection AS rpn, "
                "n.fmea_id AS fmea_id "
                "ORDER BY rpn DESC LIMIT 10",
                pl=product_line_code,
            )
            risk_records = await risk_result.data()

            # FMEA 文档数
            doc_result = await session.run(
                "MATCH (d:FMEDocument) WHERE d.product_line_code = $pl RETURN count(*) AS cnt",
                pl=product_line_code,
            )
            doc_records = await doc_result.data()

            total_nodes = sum(type_dist.values())

            return {
                "total_fmeas": doc_records[0]["cnt"] if doc_records else 0,
                "total_nodes": total_nodes,
                "node_type_distribution": type_dist,
                "high_risk_failure_modes": risk_records,
            }

    async def _path_result_to_dict(self, result) -> dict:
        """将 Neo4j path 查询结果转为 {nodes, edges} dict。"""
        nodes = []
        edges = []
        seen_node_ids = set()
        seen_edge_ids = set()

        records = await result.data()
        for record in records:
            ns = record.get("ns", [])
            rs = record.get("rs", [])
            for node in ns:
                nid = dict(node).get("node_id")
                if nid and nid not in seen_node_ids:
                    seen_node_ids.add(nid)
                    nodes.append(dict(node))
            for rel in rs:
                edge_key = (rel.start_node.id, rel.end_node.id, rel.type)
                if edge_key not in seen_edge_ids:
                    seen_edge_ids.add(edge_key)
                    edges.append({
                        "source": dict(rel.start_node).get("node_id", ""),
                        "target": dict(rel.end_node).get("node_id", ""),
                        "type": rel.type,
                    })

        return {"nodes": nodes, "edges": edges}
