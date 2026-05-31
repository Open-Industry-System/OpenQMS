"""Neo4j 实现：使用 Cypher 查询图投影。

需要 worker 同步完成后数据才可用。
"""
import uuid
from typing import Any

from neo4j import AsyncDriver

from app.graph.repository import FMEAGraphRepository
from app.config import settings
from app.state_machines.fmea_state import compute_ap


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
                "MATCH (d:FMEDocument) WHERE d.fmea_id = n.fmea_id "
                "RETURN n.node_id AS node_id, n.name AS name, n.type AS type, "
                "n.fmea_id AS fmea_id, d.document_no AS document_no "
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
                "RETURN n.type AS type, count(*) AS cnt ORDER BY cnt DESC",
                pl=product_line_code,
            )
            type_records = await type_result.data()
            type_dist = {r["type"]: r["cnt"] for r in type_records}

            # 获取所有 FailureMode 的 S/O/D：按 FMEARow 语义逐行计算真实 RPN
            # 口径与前端 FMEA 编辑器表格一致：
            # - S 取第一个 FailureEffect 的 severity
            # - O 取每个 FailureCause 的 occurrence
            # - D 优先取该 Cause 的第一个 DetectionControl，否则取 FailureMode 的第一个
            # 每行 = effect.severity × cause.occurrence × detection.detection
            fm_result = await session.run(
                """
                MATCH (fm:GraphNode {type: 'FailureMode'}) WHERE fm.product_line_code = $pl
                MATCH (d:FMEDocument) WHERE d.fmea_id = fm.fmea_id
                OPTIONAL MATCH (fm)-[re:EFFECT_OF]->(effect:GraphNode)
                WITH fm, d, effect, re
                   ORDER BY re.edge_index ASC
                WITH fm, d, coalesce(head(collect(effect.severity)), 0) as s
                OPTIONAL MATCH (cause:GraphNode)-[rc:CAUSE_OF]->(fm)
                WITH fm, d, s, cause, rc
                   ORDER BY rc.edge_index ASC
                WITH fm, d, s, collect(cause) as causes
                UNWIND CASE WHEN size(causes) = 0 THEN [null] ELSE causes END as cause
                WITH fm, d, s,
                     coalesce(cause.occurrence, 0) as o
                OPTIONAL MATCH (cause)-[rdc:DETECTED_BY]->(det_c:GraphNode)
                WITH fm, d, s, o, det_c, rdc
                   ORDER BY rdc.edge_index ASC
                WITH fm, d, s, o,
                     coalesce(head(collect(det_c.detection)), 0) as first_d_cause,
                     count(det_c) > 0 as has_cause_det
                OPTIONAL MATCH (fm)-[rdf:DETECTED_BY]->(det_f:GraphNode)
                WITH fm, d, s, o, first_d_cause, has_cause_det, det_f, rdf
                   ORDER BY rdf.edge_index ASC
                WITH fm, d, s, o, first_d_cause, has_cause_det,
                     coalesce(head(collect(det_f.detection)), 0) as first_d_fm
                WITH fm, d, s, o,
                     CASE WHEN has_cause_det THEN first_d_cause ELSE first_d_fm END as d_val,
                     s * o * CASE WHEN has_cause_det THEN first_d_cause ELSE first_d_fm END as rpn
                ORDER BY rpn DESC
                WITH fm, d, s,
                     head(collect(o)) as o_best,
                     head(collect(d_val)) as d_best,
                     head(collect(rpn)) as max_rpn
                RETURN fm.node_id AS node_id, fm.name AS name,
                       s AS severity, o_best AS occurrence, d_best AS detection, max_rpn AS rpn,
                       fm.fmea_id AS fmea_id, d.document_no AS document_no
                """,
                pl=product_line_code,
            )
            fm_records = await fm_result.data()

            ap_counts = {"H": 0, "M": 0, "L": 0}
            high_ap_nodes: list[dict] = []
            total_rpn = 0
            rpn_count = 0
            top_modes: list[dict] = []

            for r in fm_records:
                s = r.get("severity", 0) or 0
                o = r.get("occurrence", 0) or 0
                d = r.get("detection", 0) or 0
                rpn = s * o * d
                ap = compute_ap(s, o, d) if s > 0 and o > 0 and d > 0 else ""

                if rpn > 0:
                    total_rpn += rpn
                    rpn_count += 1
                    top_modes.append({
                        "name": r.get("name", ""),
                        "rpn": rpn,
                        "fmea_id": r.get("fmea_id", ""),
                        "document_no": r.get("document_no"),
                    })

                if ap:
                    ap_counts[ap] = ap_counts.get(ap, 0) + 1
                    if ap == "H":
                        high_ap_nodes.append({
                            "node_id": r.get("node_id", ""),
                            "name": r.get("name", ""),
                            "ap": ap,
                            "rpn": rpn,
                            "fmea_id": r.get("fmea_id", ""),
                            "document_no": r.get("document_no"),
                        })

            # 平均 RPN：用 Python 累加结果计算（与 JSONB 实现一致）
            avg_rpn = round(total_rpn / rpn_count, 1) if rpn_count > 0 else 0

            # FMEA 文档数
            doc_result = await session.run(
                "MATCH (d:FMEDocument) WHERE d.product_line_code = $pl RETURN count(*) AS cnt",
                pl=product_line_code,
            )
            doc_records = await doc_result.data()

            return {
                "total_fmeas": doc_records[0]["cnt"] if doc_records else 0,
                "total_nodes": sum(type_dist.values()),
                "node_type_distribution": type_dist,
                "ap_distribution": ap_counts,
                "high_ap_nodes": sorted(high_ap_nodes, key=lambda x: x["rpn"], reverse=True)[:20],
                "avg_rpn": avg_rpn,
                "top_failure_modes": sorted(top_modes, key=lambda x: x["rpn"], reverse=True)[:10],
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
