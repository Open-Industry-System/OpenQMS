"""JSONB 实现：从 PostgreSQL graph_data JSONB 字段执行图查询。

不需要 Neo4j，适合开发/测试环境或 Neo4j 不可用时的 fallback。
"""
import uuid
from collections import deque
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.graph.repository import FMEAGraphRepository
from app.state_machines.fmea_state import compute_ap


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
                node_name = node.get("name") or ""
                if node.get("type") == node_type and name_keyword.lower() in node_name.lower():
                    matches.append({
                        "node_id": node["id"],
                        "name": node_name,
                        "type": node["type"],
                        "fmea_id": str(fmea.fmea_id),
                        "document_no": fmea.document_no,
                    })
                    if len(matches) >= limit:
                        return matches
        return matches

    def _collect_failure_mode_rpn(self, graph_data: dict) -> list[dict]:
        """按链路遍历收集每个 FailureMode 的 S/O/D。

        S 来自 FailureEffect（FailureMode -EFFECT_OF-> FailureEffect）
        O 来自 FailureCause（FailureCause -CAUSE_OF-> FailureMode）
        D 来自 DetectionControl（FailureCause/FailureMode -DETECTED_BY-> DetectionControl）
        """
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        node_map = {n["id"]: n for n in nodes}

        # 构建边索引加速查找
        out_edges: dict[tuple[str, str], list[str]] = {}
        in_edges: dict[tuple[str, str], list[str]] = {}
        for e in edges:
            src = e.get("source", "")
            tgt = e.get("target", "")
            etype = e.get("type", "")
            if src and etype:
                out_edges.setdefault((src, etype), []).append(tgt)
            if tgt and etype:
                in_edges.setdefault((tgt, etype), []).append(src)

        results: list[dict] = []
        for node in nodes:
            if node.get("type") != "FailureMode":
                continue

            fm_id = node["id"]
            fm_name = node.get("name", "")

            # Effect: FailureMode -EFFECT_OF-> FailureEffect
            effect_ids = out_edges.get((fm_id, "EFFECT_OF"), [])
            severities = [
                node_map[eid].get("severity", 0) or 0
                for eid in effect_ids
                if eid in node_map
            ]
            s = max(severities) if severities else 0

            # Cause: FailureCause -CAUSE_OF-> FailureMode
            cause_ids = in_edges.get((fm_id, "CAUSE_OF"), [])
            occurrences = [
                node_map[cid].get("occurrence", 0) or 0
                for cid in cause_ids
                if cid in node_map
            ]
            o = max(occurrences) if occurrences else 0

            # Detection: from causes or directly from FailureMode
            detection_ids: set[str] = set()
            for cid in cause_ids:
                detection_ids.update(out_edges.get((cid, "DETECTED_BY"), []))
            detection_ids.update(out_edges.get((fm_id, "DETECTED_BY"), []))
            detections = [
                node_map[did].get("detection", 0) or 0
                for did in detection_ids
                if did in node_map
            ]
            d_val = max(detections) if detections else 0

            rpn = s * o * d_val
            ap = compute_ap(s, o, d_val) if s > 0 and o > 0 and d_val > 0 else ""

            results.append({
                "node_id": fm_id,
                "name": fm_name,
                "s": s,
                "o": o,
                "d": d_val,
                "rpn": rpn,
                "ap": ap,
            })

        return results

    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        query = select(FMEADocument).where(FMEADocument.product_line_code == product_line_code)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()

        type_counts: dict[str, int] = {}
        total_nodes = 0
        ap_counts = {"H": 0, "M": 0, "L": 0}
        high_ap_nodes: list[dict] = []
        total_rpn = 0
        rpn_count = 0
        top_modes: list[dict] = []

        for fmea in fmeas:
            if not fmea.graph_data:
                continue

            for node in fmea.graph_data.get("nodes", []):
                total_nodes += 1
                t = node.get("type", "Unknown")
                type_counts[t] = type_counts.get(t, 0) + 1

            # 按链路遍历获取正确的 S/O/D（而非直接从 FailureMode 读取）
            for fm in self._collect_failure_mode_rpn(fmea.graph_data):
                rpn = fm["rpn"]
                ap = fm["ap"]

                if rpn > 0:
                    total_rpn += rpn
                    rpn_count += 1
                    top_modes.append({
                        "name": fm["name"],
                        "rpn": rpn,
                        "fmea_id": str(fmea.fmea_id),
                    })

                if ap:
                    ap_counts[ap] = ap_counts.get(ap, 0) + 1
                    if ap == "H":
                        high_ap_nodes.append({
                            "node_id": fm["node_id"],
                            "name": fm["name"],
                            "ap": ap,
                            "rpn": rpn,
                            "fmea_id": str(fmea.fmea_id),
                            "document_no": fmea.document_no,
                        })

        return {
            "total_fmeas": len(fmeas),
            "total_nodes": total_nodes,
            "node_type_distribution": type_counts,
            "ap_distribution": ap_counts,
            "high_ap_nodes": sorted(high_ap_nodes, key=lambda x: x["rpn"], reverse=True)[:20],
            "avg_rpn": round(total_rpn / rpn_count, 1) if rpn_count > 0 else 0,
            "top_failure_modes": sorted(top_modes, key=lambda x: x["rpn"], reverse=True)[:10],
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
        seen_edge_keys = set()
        queue = deque([start_node_id])

        while queue:
            current = queue.popleft()
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

                if direction == "downstream" and src == current and edge_key not in seen_edge_keys:
                    seen_edge_keys.add(edge_key)
                    result_edges.append({"source": src, "target": tgt, "type": edge_type, "_key": edge_key})
                    queue.append(tgt)
                elif direction == "upstream" and tgt == current and edge_key not in seen_edge_keys:
                    seen_edge_keys.add(edge_key)
                    result_edges.append({"source": src, "target": tgt, "type": edge_type, "_key": edge_key})
                    queue.append(src)

        # 去掉内部 _key
        for e in result_edges:
            e.pop("_key", None)

        return {"nodes": result_nodes, "edges": result_edges}
