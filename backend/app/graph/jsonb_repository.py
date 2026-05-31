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
        """按 FMEARow 语义逐行计算每个 FailureMode 的 RPN/AP。

        口径与前端 FMEA 编辑器表格一致：
        - S 取第一个 FailureEffect 的 severity（edges 顺序中的第一个）
        - O 取每个 FailureCause 的 occurrence
        - D 优先取该 Cause 的第一个 DetectionControl，否则取 FailureMode 的第一个
        每行 = effect.severity × cause.occurrence × detection.detection
        取该 FailureMode 下所有真实行的最大 RPN 作为代表值。
        """
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        node_map = {n["id"]: n for n in nodes}

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

        def _first_detection(source_id: str) -> int:
            """取 source 的第一个 DetectionControl 的 detection 值（与前端 detectionControlIds[0] 一致）。"""
            det_ids = out_edges.get((source_id, "DETECTED_BY"), [])
            first_id = det_ids[0] if det_ids else None
            node = node_map.get(first_id) if first_id else None
            return node.get("detection", 0) or 0 if node else 0

        results: list[dict] = []
        for node in nodes:
            if node.get("type") != "FailureMode":
                continue

            fm_id = node["id"]
            fm_name = node.get("name", "")

            # S: 取第一个 FailureEffect 的 severity（与前端 effectEdges[0] 一致）
            effect_ids = out_edges.get((fm_id, "EFFECT_OF"), [])
            first_effect = node_map.get(effect_ids[0]) if effect_ids else None
            s = first_effect.get("severity", 0) or 0 if first_effect else 0

            # Causes
            cause_ids = in_edges.get((fm_id, "CAUSE_OF"), [])

            # 按 (effect, cause, detection) 逐行计算 RPN，取最大真实行
            rows: list[tuple[int, int, int]] = []  # (o, d, rpn)

            if not cause_ids:
                # 无 cause：O=0，D 取 fm 的第一个 detection
                d = _first_detection(fm_id)
                rows.append((0, d, 0))
            else:
                for cause_id in cause_ids:
                    cause = node_map.get(cause_id)
                    o = cause.get("occurrence", 0) or 0 if cause else 0
                    # D：优先取 cause 的第一个 detection，否则取 fm 的第一个
                    # 与前端 findDetectionControls(causeId=xx) → [0] 一致
                    cause_dets = out_edges.get((cause_id, "DETECTED_BY"), [])
                    if cause_dets:
                        d = _first_detection(cause_id)
                    else:
                        d = _first_detection(fm_id)
                    rows.append((o, d, s * o * d))

            # 取最大 RPN 的真实行
            best = max(rows, key=lambda x: x[2]) if rows else (0, 0, 0)
            o_best, d_best, max_rpn = best

            ap = compute_ap(s, o_best, d_best) if s > 0 and o_best > 0 and d_best > 0 else ""

            results.append({
                "node_id": fm_id,
                "name": fm_name,
                "s": s,
                "o": o_best,
                "d": d_best,
                "rpn": max_rpn,
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
