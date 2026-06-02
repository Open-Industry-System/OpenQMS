from __future__ import annotations

from typing import Any

from app.services.recommendation_types import RecommendationCandidate, RecommendationContext


class FMEAGraphSource:
    """关联 FMEA 结构性图匹配。纯结构解析，不做文本匹配。"""

    name = "fmea_graph"

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        linked_fmea = context.linked_fmea
        if not linked_fmea or not linked_fmea.get("graph_data"):
            return []

        capa_data = context.capa_data
        target_node_id = capa_data.get("fmea_node_id")
        if not target_node_id:
            return []

        graph = linked_fmea["graph_data"]
        node_map = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])

        forward_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            forward_edges.setdefault(e["source"], []).append((e["target"], e["type"]))

        reverse_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            reverse_edges.setdefault(e["target"], []).append((e["source"], e["type"]))

        target_node = node_map.get(target_node_id)
        if not target_node:
            return []

        # Resolve to FailureMode IDs
        failure_mode_ids: list[str] = []
        ntype = target_node["type"]
        if ntype == "FailureCause":
            for tgt, etype in forward_edges.get(target_node_id, []):
                if etype == "CAUSE_OF" and node_map.get(tgt, {}).get("type") == "FailureMode":
                    failure_mode_ids.append(tgt)
        elif ntype == "FailureMode":
            failure_mode_ids.append(target_node_id)
        elif ntype in ("Function", "ProcessStepFunction", "ProcessItemFunction", "ProcessWorkElementFunction"):
            for tgt, etype in forward_edges.get(target_node_id, []):
                if etype == "HAS_FAILURE_MODE" and node_map.get(tgt, {}).get("type") == "FailureMode":
                    failure_mode_ids.append(tgt)

        # For each FailureMode, find FailureCauses
        results: list[RecommendationCandidate] = []
        for fm_id in failure_mode_ids:
            fm_node = node_map.get(fm_id, {})
            cause_ids = [
                src
                for src, etype in reverse_edges.get(fm_id, [])
                if etype == "CAUSE_OF" and node_map.get(src, {}).get("type") == "FailureCause"
            ]
            for cause_id in cause_ids:
                cause_node = node_map.get(cause_id, {})
                results.append(RecommendationCandidate(
                    source="fmea_graph",
                    content=cause_node.get("name", ""),
                    category=None,
                    confidence=0.6,
                    match_reason="关联 FMEA 失效原因",
                    metadata={
                        "failure_cause_node_id": cause_id,
                        "failure_cause_desc": cause_node.get("description"),
                        "failure_mode_node_id": fm_id,
                        "failure_mode_name": fm_node.get("name"),
                        "fmea_document_no": linked_fmea.get("document_no"),
                        "fmea_id": str(linked_fmea["fmea_id"]),
                        "product_line_code": linked_fmea.get("product_line_code"),
                    },
                ))

            # If no FailureCause matched but FM was found, return FM-level match
            if not cause_ids:
                results.append(RecommendationCandidate(
                    source="fmea_graph",
                    content=fm_node.get("name", ""),
                    category=None,
                    confidence=0.4,
                    match_reason="关联 FMEA 失效模式",
                    metadata={
                        "failure_mode_node_id": fm_id,
                        "failure_mode_name": fm_node.get("name"),
                        "fmea_document_no": linked_fmea.get("document_no"),
                        "fmea_id": str(linked_fmea["fmea_id"]),
                        "product_line_code": linked_fmea.get("product_line_code"),
                    },
                ))

        return results
