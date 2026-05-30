"""JSONB 实现：从 PostgreSQL graph_data JSONB 字段执行图查询。

不需要 Neo4j，适合开发/测试环境或 Neo4j 不可用时的 fallback。
"""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.graph.repository import FMEAGraphRepository


class JSONBRepository(FMEAGraphRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_impact_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        fmea = await self._get_fmea(fmea_id)
        if not fmea or not fmea.graph_data:
            return {"nodes": [], "edges": []}
        return self._trace_chain(fmea.graph_data, node_id, direction="downstream")

    async def get_cause_chain(self, fmea_id: uuid.UUID, node_id: str) -> dict:
        fmea = await self._get_fmea(fmea_id)
        if not fmea or not fmea.graph_data:
            return {"nodes": [], "edges": []}
        return self._trace_chain(fmea.graph_data, node_id, direction="upstream")

    async def find_similar_nodes(
        self, node_type: str, name_keyword: str, product_line_code: str, limit: int = 20
    ) -> list[dict]:
        query = select(FMEADocument).where(FMEADocument.product_line_code == product_line_code)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()

        matches = []
        for fmea in fmeas:
            if not fmea.graph_data:
                continue
            for node in fmea.graph_data.get("nodes", []):
                if node.get("type") == node_type and name_keyword.lower() in node.get("name", "").lower():
                    matches.append({
                        "node_id": node["id"],
                        "name": node["name"],
                        "type": node["type"],
                        "fmea_id": str(fmea.fmea_id),
                        "document_no": fmea.document_no,
                    })
                    if len(matches) >= limit:
                        return matches
        return matches

    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        query = select(FMEADocument).where(FMEADocument.product_line_code == product_line_code)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()

        type_counts: dict[str, int] = {}
        high_risk_modes: list[dict] = []
        total_nodes = 0

        for fmea in fmeas:
            if not fmea.graph_data:
                continue
            for node in fmea.graph_data.get("nodes", []):
                total_nodes += 1
                t = node.get("type", "Unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
                if node.get("type") == "FailureMode":
                    s = node.get("severity", 0)
                    o = node.get("occurrence", 0)
                    d = node.get("detection", 0)
                    if s * o * d >= 100:
                        high_risk_modes.append({
                            "name": node.get("name", ""),
                            "rpn": s * o * d,
                            "fmea_id": str(fmea.fmea_id),
                            "document_no": fmea.document_no,
                        })

        return {
            "total_fmeas": len(fmeas),
            "total_nodes": total_nodes,
            "node_type_distribution": type_counts,
            "high_risk_failure_modes": sorted(high_risk_modes, key=lambda x: x["rpn"], reverse=True)[:10],
        }

    async def _get_fmea(self, fmea_id: uuid.UUID) -> FMEADocument | None:
        result = await self._db.execute(
            select(FMEADocument).where(FMEADocument.fmea_id == fmea_id)
        )
        return result.scalar_one_or_none()

    def _trace_chain(self, graph_data: dict, start_node_id: str, direction: str) -> dict:
        """BFS 遍历图，收集影响链或原因链。"""
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        node_map = {n["id"]: n for n in nodes}

        visited_nodes = set()
        result_nodes = []
        result_edges = []
        queue = [start_node_id]

        while queue:
            current = queue.pop(0)
            if current in visited_nodes:
                continue
            visited_nodes.add(current)
            if current in node_map:
                result_nodes.append(node_map[current])

            for idx, edge in enumerate(edges):
                src = edge.get("source", "")
                tgt = edge.get("target", "")
                edge_type = edge.get("type", "")
                # 用 (source, target, type, index) 做唯一标识，因为 edge 没有 id 字段
                edge_key = (src, tgt, edge_type, idx)

                if direction == "downstream" and src == current and edge_key not in {e["_key"] for e in result_edges}:
                    result_edges.append({"source": src, "target": tgt, "type": edge_type, "_key": edge_key})
                    queue.append(tgt)
                elif direction == "upstream" and tgt == current and edge_key not in {e["_key"] for e in result_edges}:
                    result_edges.append({"source": src, "target": tgt, "type": edge_type, "_key": edge_key})
                    queue.append(src)

        # 去掉内部 _key
        for e in result_edges:
            e.pop("_key", None)

        return {"nodes": result_nodes, "edges": result_edges}
