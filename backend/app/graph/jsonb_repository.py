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
from app.schemas.change_impact import ChangeImpactResult, AffectedNode, ImpactSummary
from app.state_machines.fmea_state import compute_ap
from app.utils.similarity import compute_similarity


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

    def _aggregate_stats(self, fmeas) -> dict:
        """从 FMEADocument 列表聚合统计，供 get_cross_fmea_stats / get_global_stats 复用。"""
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
                        "document_no": fmea.document_no,
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

    async def get_cross_fmea_stats(self, product_line_code: str) -> dict:
        query = select(FMEADocument).where(FMEADocument.product_line_code == product_line_code)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()
        return self._aggregate_stats(fmeas)

    async def get_global_stats(self) -> dict:
        query = select(FMEADocument)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()
        return self._aggregate_stats(fmeas)

    async def _load_product_line_names(self, codes: set[str]) -> dict[str, str]:
        """批量加载产品线名称，避免 N+1。"""
        if not codes:
            return {}
        from app.models.product_line import ProductLine
        from sqlalchemy import select as sa_select
        result = await self._db.execute(
            sa_select(ProductLine.code, ProductLine.name).where(ProductLine.code.in_(codes))
        )
        return {row.code: row.name for row in result.all()}

    async def find_similar_nodes_advanced(
        self,
        node_type: str,
        query_text: str,
        scope: str,
        product_line_code: str | None,
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict]:
        from sqlalchemy import select as sa_select

        query = sa_select(FMEADocument).where(
            FMEADocument.status == "approved",
            FMEADocument.graph_data.isnot(None),
        )
        if scope == "current_product_line" and product_line_code:
            query = query.where(FMEADocument.product_line_code == product_line_code)
        result = await self._db.execute(query)
        fmeas = result.scalars().all()

        pl_codes = {fmea.product_line_code for fmea in fmeas if fmea.product_line_code}
        pl_name_map = await self._load_product_line_names(pl_codes)

        matches = []
        for fmea in fmeas:
            for node in fmea.graph_data.get("nodes", []):
                if node.get("type") != node_type:
                    continue
                node_name = node.get("name") or ""
                score, reason = compute_similarity(query_text, node_name)
                if score >= min_similarity:
                    pl_code = fmea.product_line_code
                    matches.append({
                        "node_id": node.get("id", ""),
                        "name": node_name,
                        "type": node_type,
                        "fmea_id": str(fmea.fmea_id),
                        "document_no": fmea.document_no,
                        "product_line_code": pl_code,
                        "product_line_name": pl_name_map.get(pl_code, pl_code),
                        "similarity_score": round(score, 3),
                        "match_reason": reason,
                    })

        matches.sort(key=lambda x: x["similarity_score"], reverse=True)
        return matches[:limit]

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

    async def analyze_change_impact(
        self,
        fmea_id: uuid.UUID,
        node_id: str,
        change_type: str,
        field_name: str | None,
        new_value: str | None,
    ) -> ChangeImpactResult:
        fmea = await self._get_fmea(fmea_id)
        if not fmea or not fmea.graph_data:
            return ChangeImpactResult(affected_nodes=[], summary=ImpactSummary(
                total_affected=0, failure_modes_affected=0, controls_affected=0,
                ap_upgraded_count=0, max_hop_distance=0,
            ))

        nodes = fmea.graph_data.get("nodes", [])
        edges = fmea.graph_data.get("edges", [])
        node_map = {n["id"]: n for n in nodes}
        start_node = node_map.get(node_id)
        if not start_node:
            return ChangeImpactResult(affected_nodes=[], summary=ImpactSummary(
                total_affected=0, failure_modes_affected=0, controls_affected=0,
                ap_upgraded_count=0, max_hop_distance=0,
            ))

        # 方向控制逻辑
        if change_type == "attribute" and field_name in ("name", "description"):
            return ChangeImpactResult(affected_nodes=[], summary=ImpactSummary(
                total_affected=0, failure_modes_affected=0, controls_affected=0,
                ap_upgraded_count=0, max_hop_distance=0,
            ))

        if change_type == "attribute" and field_name in ("severity", "occurrence", "detection"):
            directions = ["downstream", "upstream"]
        else:
            directions = ["downstream"]

        downstream_edges = {"HAS_FUNCTION", "FUNCTION_MAPPED_TO", "HAS_FAILURE_MODE", "EFFECT_OF", "HAS_PROCESS_STEP"}
        upstream_edges = {"CAUSE_OF", "PREVENTED_BY", "DETECTED_BY", "OPTIMIZED_BY"}

        affected: list[AffectedNode] = []
        seen_node_ids: set[str] = set()

        for direction in directions:
            edge_filter = downstream_edges if direction == "downstream" else upstream_edges
            paths = self._bfs_with_path(fmea.graph_data, node_id, edge_filter, max_depth=5, direction=direction)
            for path_info in paths:
                nid = path_info["node_id"]
                if nid == node_id or nid in seen_node_ids:
                    continue
                seen_node_ids.add(nid)
                n = node_map.get(nid)
                if not n:
                    continue

                risk_change = self._compute_risk_change(
                    start_node, n, field_name, new_value, node_map, edges, direction,
                )
                affected.append(AffectedNode(
                    node_id=nid,
                    node_type=n.get("type", ""),
                    name=n.get("name", ""),
                    path=path_info["path"],
                    impact_type=direction,
                    hop_distance=path_info["hop_distance"],
                    risk_change=risk_change,
                ))

        # 统计摘要
        fm_count = sum(1 for a in affected if a.node_type == "FailureMode")
        ctrl_count = sum(1 for a in affected if a.node_type in ("PreventionControl", "DetectionControl"))
        ap_upgraded = sum(
            1 for a in affected
            if a.risk_change and a.risk_change.get("old_ap") and a.risk_change.get("new_ap")
            and self._ap_rank(a.risk_change["new_ap"]) > self._ap_rank(a.risk_change["old_ap"])
        )
        max_hop = max((a.hop_distance for a in affected), default=0)

        summary = ImpactSummary(
            total_affected=len(affected),
            failure_modes_affected=fm_count,
            controls_affected=ctrl_count,
            ap_upgraded_count=ap_upgraded,
            max_hop_distance=max_hop,
        )
        return ChangeImpactResult(affected_nodes=affected, summary=summary)

    def _bfs_with_path(
        self, graph_data: dict, start_node_id: str, edge_filter: set[str], max_depth: int, direction: str,
    ) -> list[dict]:
        """BFS 遍历图，返回每个可达节点的路径信息。

        结果项: {"node_id": str, "path": list[str], "hop_distance": int}
        """
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        node_map = {n["id"]: n for n in nodes}

        # 构建邻接表
        adj: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            src = e.get("source", "")
            tgt = e.get("target", "")
            etype = e.get("type", "")
            if not src or not tgt or not etype:
                continue
            if direction == "downstream":
                adj.setdefault(src, []).append((tgt, etype))
            else:
                adj.setdefault(tgt, []).append((src, etype))

        results: list[dict] = []
        visited: set[str] = set()
        queue: deque[tuple[str, list[str], int]] = deque([(start_node_id, [node_map.get(start_node_id, {}).get("name", start_node_id)], 0)])

        while queue:
            current, path, dist = queue.popleft()
            if current in visited or dist > max_depth:
                continue
            visited.add(current)
            if current != start_node_id:
                results.append({"node_id": current, "path": path, "hop_distance": dist})
            for nxt, etype in adj.get(current, []):
                if etype not in edge_filter:
                    continue
                if nxt not in visited and dist < max_depth:
                    nxt_name = node_map.get(nxt, {}).get("name", nxt)
                    queue.append((nxt, path + [nxt_name], dist + 1))
        return results

    def _compute_risk_change(
        self,
        start_node: dict,
        affected_node: dict,
        field_name: str | None,
        new_value: str | None,
        node_map: dict[str, dict],
        edges: list[dict],
        direction: str,
    ) -> dict | None:
        """计算风险变化。仅对 FailureMode 和 FailureCause 有意义。"""
        start_type = start_node.get("type", "")
        affected_type = affected_node.get("type", "")

        # 辅助：从 edges 构建 out/in 映射
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
            det_ids = out_edges.get((source_id, "DETECTED_BY"), [])
            first_id = det_ids[0] if det_ids else None
            node = node_map.get(first_id) if first_id else None
            return node.get("detection", 0) or 0 if node else 0

        def _get_fm_sod(fm_id: str) -> tuple[int, int, int, str]:
            """返回 (s, o, d, ap)"""
            effect_ids = out_edges.get((fm_id, "EFFECT_OF"), [])
            first_effect = node_map.get(effect_ids[0]) if effect_ids else None
            s = first_effect.get("severity", 0) or 0 if first_effect else 0
            cause_ids = in_edges.get((fm_id, "CAUSE_OF"), [])
            if not cause_ids:
                d = _first_detection(fm_id)
                o = 0
            else:
                # 取最大 RPN 的 cause 的 O/D（与 _collect_failure_mode_rpn 一致）
                best_rpn = -1
                o = 0
                d = 0
                for cause_id in cause_ids:
                    cause = node_map.get(cause_id)
                    oc = cause.get("occurrence", 0) or 0 if cause else 0
                    cause_dets = out_edges.get((cause_id, "DETECTED_BY"), [])
                    if cause_dets:
                        dc = _first_detection(cause_id)
                    else:
                        dc = _first_detection(fm_id)
                    rpn = s * oc * dc
                    if rpn > best_rpn:
                        best_rpn = rpn
                        o = oc
                        d = dc
            ap = compute_ap(s, o, d) if s > 0 and o > 0 and d > 0 else ""
            return s, o, d, ap

        # Case 1: FailureMode 自身 S/O/D 变更
        if start_type == "FailureMode" and affected_node["id"] == start_node["id"]:
            if field_name in ("severity", "occurrence", "detection"):
                old_val = start_node.get(field_name, 0) or 0
                try:
                    new_val_int = int(new_value) if new_value is not None else old_val
                except (ValueError, TypeError):
                    new_val_int = old_val
                s, o, d, old_ap = _get_fm_sod(start_node["id"])
                if field_name == "severity":
                    s = new_val_int
                elif field_name == "occurrence":
                    o = new_val_int
                elif field_name == "detection":
                    d = new_val_int
                new_ap = compute_ap(s, o, d) if s > 0 and o > 0 and d > 0 else ""
                return {
                    "old_ap": old_ap,
                    "new_ap": new_ap,
                    "old_value": old_val,
                    "new_value": new_val_int,
                    "field": field_name,
                }
            return None

        # Case 2: FailureCause 的 O/D 变更 → 影响关联 FailureMode
        if start_type == "FailureCause" and affected_type == "FailureMode":
            if field_name in ("occurrence", "detection"):
                # 找到该 cause 关联的 FailureMode（通过 CAUSE_OF）
                fm_ids = out_edges.get((start_node["id"], "CAUSE_OF"), [])
                if not fm_ids:
                    return None
                fm_id = fm_ids[0]
                s, o, d, old_ap = _get_fm_sod(fm_id)
                try:
                    new_val_int = int(new_value) if new_value is not None else (start_node.get(field_name, 0) or 0)
                except (ValueError, TypeError):
                    new_val_int = start_node.get(field_name, 0) or 0
                # 重新计算：替换该 cause 的值后重新选最佳行
                effect_ids = out_edges.get((fm_id, "EFFECT_OF"), [])
                first_effect = node_map.get(effect_ids[0]) if effect_ids else None
                s = first_effect.get("severity", 0) or 0 if first_effect else 0
                cause_ids = in_edges.get((fm_id, "CAUSE_OF"), [])
                best_rpn = -1
                new_o = o
                new_d = d
                for cause_id in cause_ids:
                    cause = node_map.get(cause_id)
                    if cause_id == start_node["id"]:
                        oc = new_val_int
                    else:
                        oc = cause.get("occurrence", 0) or 0 if cause else 0
                    cause_dets = out_edges.get((cause_id, "DETECTED_BY"), [])
                    if cause_id == start_node["id"] and field_name == "detection":
                        # 该 cause 的 detection 变了，重新取第一个 detection
                        dc = _first_detection(cause_id) if not cause_dets else new_val_int
                        if cause_dets:
                            first_det = node_map.get(cause_dets[0])
                            dc = new_val_int if first_det and first_det["id"] == start_node["id"] else _first_detection(cause_id)
                        else:
                            dc = _first_detection(fm_id)
                    else:
                        if cause_dets:
                            dc = _first_detection(cause_id)
                        else:
                            dc = _first_detection(fm_id)
                    rpn = s * oc * dc
                    if rpn > best_rpn:
                        best_rpn = rpn
                        new_o = oc
                        new_d = dc
                new_ap = compute_ap(s, new_o, new_d) if s > 0 and new_o > 0 and new_d > 0 else ""
                return {
                    "old_ap": old_ap,
                    "new_ap": new_ap,
                    "old_value": start_node.get(field_name, 0) or 0,
                    "new_value": new_val_int,
                    "field": field_name,
                }
            return None

        # Case 3: Component/ProcessStep 的 design_parameter 变更
        if start_type in ("Component", "ProcessStep") and field_name == "design_parameter":
            if affected_type == "FailureMode":
                return {"needs_reassessment": True, "reason": f"{start_type} design_parameter changed"}
            return None

        return None

    @staticmethod
    def _ap_rank(ap: str) -> int:
        return {"H": 3, "M": 2, "L": 1}.get(ap, 0)
