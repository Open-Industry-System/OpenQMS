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


from sqlalchemy import text

from app.services.embedding_provider import EmbeddingProvider


class SemanticSearchSource:
    """FMEA 节点语义搜索。通过 pgvector 检索 + 图结构回溯。"""

    name = "semantic_search"

    def __init__(self, db, embedding_provider: EmbeddingProvider | None):
        self.db = db
        self.embedding = embedding_provider

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        if not self.embedding:
            return []

        # NEW: Explicit guard for no permission
        if context.user_product_lines == []:
            return []

        capa_data = context.capa_data
        if context.stage == "d4":
            query_text = capa_data.get("d2_description", "")
        else:
            query_text = capa_data.get("d4_root_cause", "")
            if not query_text:
                query_text = capa_data.get("d2_description", "")

        if not query_text or not query_text.strip():
            return []

        query_vector = await self.embedding.embed([query_text])
        if not query_vector:
            return []

        vec_str = "[" + ",".join(str(v) for v in query_vector[0]) + "]"
        user_pls = context.user_product_lines

        params: dict[str, Any] = {
            "query_vector": vec_str,
            "limit": 10,
        }
        pl_filter = ""
        if user_pls is not None:
            pl_filter = "AND de.product_line_code = ANY(:product_line_codes)"
            params["product_line_codes"] = user_pls

        stmt = text(f"""
            SELECT de.entity_id AS fmea_id, de.node_id,
                   1 - (de.embedding <=> CAST(:query_vector AS vector)) AS similarity,
                   de.product_line_code
            FROM document_embeddings de
            WHERE de.entity_type = 'fmea_node'
              {pl_filter}
            ORDER BY de.embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """)

        rows = await self.db.execute(stmt, params)
        raw_matches = rows.fetchall()

        # 将预加载的 fmea_docs 转为映射，方便 O(1) 回溯
        doc_map = {str(d["fmea_id"]): d for d in (context.fmea_docs or []) if d.get("graph_data")}

        candidates: list[RecommendationCandidate] = []
        for row in raw_matches:
            fmea_id = str(row.fmea_id)
            node_id = row.node_id
            similarity = float(row.similarity)

            doc = doc_map.get(fmea_id)
            if not doc or not node_id:
                continue

            graph = doc["graph_data"]
            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            node = node_map.get(node_id)
            if not node:
                continue

            node_type = node.get("type")
            edges = graph.get("edges", [])

            # D4: 召回 FailureCause 或 FailureMode
            if context.stage == "d4":
                if node_type == "FailureCause":
                    fm_id = None
                    fm_name = None
                    for e in edges:
                        if e["source"] == node_id and e["type"] == "CAUSE_OF":
                            parent = node_map.get(e["target"])
                            if parent and parent.get("type") == "FailureMode":
                                fm_id = parent["id"]
                                fm_name = parent.get("name")
                                break
                    candidates.append(RecommendationCandidate(
                        source="semantic_search",
                        content=node.get("name", ""),
                        category=None,
                        confidence=similarity * 0.7,
                        match_reason="语义相关失效原因",
                        metadata={
                            "failure_cause_node_id": node_id,
                            "failure_cause_desc": node.get("description"),
                            "failure_mode_node_id": fm_id,
                            "failure_mode_name": fm_name,
                            "fmea_id": fmea_id,
                            "fmea_document_no": doc.get("document_no"),
                            "product_line_code": doc.get("product_line_code"),
                        },
                    ))
                elif node_type == "FailureMode":
                    candidates.append(RecommendationCandidate(
                        source="semantic_search",
                        content=node.get("name", ""),
                        category=None,
                        confidence=similarity * 0.5,
                        match_reason="语义相关失效模式",
                        metadata={
                            "failure_mode_node_id": node_id,
                            "failure_mode_name": node.get("name"),
                            "fmea_id": fmea_id,
                            "fmea_document_no": doc.get("document_no"),
                            "product_line_code": doc.get("product_line_code"),
                        },
                    ))

            # D5: 只召回 FailureCause（后续交给 FMEAControlExpander）
            elif context.stage == "d5" and node_type == "FailureCause":
                fm_id = None
                fm_name = None
                for e in edges:
                    if e["source"] == node_id and e["type"] == "CAUSE_OF":
                        parent = node_map.get(e["target"])
                        if parent and parent.get("type") == "FailureMode":
                            fm_id = parent["id"]
                            fm_name = parent.get("name")
                            break
                candidates.append(RecommendationCandidate(
                    source="semantic_search",
                    content=node.get("name", ""),
                    category=None,
                    confidence=similarity * 0.8,
                    match_reason="语义相关失效原因",
                    metadata={
                        "failure_cause_node_id": node_id,
                        "failure_cause_desc": node.get("description"),
                        "failure_mode_node_id": fm_id,
                        "failure_mode_name": fm_name,
                        "fmea_id": fmea_id,
                        "fmea_document_no": doc.get("document_no"),
                        "product_line_code": doc.get("product_line_code"),
                    },
                ))

        return candidates


class HistoricalCAPASource:
    """历史 CAPA D2→D2 语义匹配。只搜索 D8_CLOSURE。"""

    name = "historical_capa"

    def __init__(self, db, embedding_provider: EmbeddingProvider | None):
        self.db = db
        self.embedding = embedding_provider

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        if not self.embedding:
            return []

        # NEW: Explicit guard for no permission
        if context.user_product_lines == []:
            return []

        d2 = context.capa_data.get("d2_description", "")
        if not d2 or not d2.strip():
            return []

        query_vector = await self.embedding.embed([d2])
        if not query_vector:
            return []

        vec_str = "[" + ",".join(str(v) for v in query_vector[0]) + "]"
        user_pls = context.user_product_lines

        # 先尝试同产品线（或用户允许的产品线）
        # 注意：user_pls 为 None 时表示 admin（无限制），不应放宽
        # user_pls 为 [] 时表示无权限，应返回空
        # user_pls 为 ["xxx"] 时优先搜索这些产品线的 CAPA
        capa_pl = context.capa_data.get("product_line_code")
        search_pls = user_pls
        if user_pls is not None and capa_pl and capa_pl in user_pls:
            # 优先搜索当前 CAPA 的产品线
            search_pls = [capa_pl]

        results = await self._search(vec_str, search_pls, "d2_description", limit=5)
        if not results and user_pls is not None and len(user_pls) > 1 and capa_pl in user_pls:
            # 当前产品线无结果，放宽到用户允许的所有产品线
            results = await self._search(vec_str, user_pls, "d2_description", limit=5)

        return results

    async def _search(
        self,
        vec_str: str,
        product_line_codes: list[str] | None,
        target_field: str,
        limit: int,
    ) -> list[RecommendationCandidate]:
        params: dict[str, Any] = {
            "query_vector": vec_str,
            "target_field": target_field,
            "limit": limit,
        }
        pl_filter = ""
        if product_line_codes is not None:
            pl_filter = "AND de.product_line_code = ANY(:product_line_codes)"
            params["product_line_codes"] = product_line_codes

        stmt = text(f"""
            SELECT de.entity_id, de.chunk_text,
                   1 - (de.embedding <=> CAST(:query_vector AS vector)) AS similarity,
                   capa.document_no, capa.severity, capa.updated_at AS source_updated_at,
                   capa.d4_root_cause, capa.d5_correction, de.product_line_code
            FROM document_embeddings de
            JOIN capa_eightd capa ON de.entity_id = capa.report_id
            WHERE de.entity_type = 'capa'
              AND de.entity_field = :target_field
              AND capa.status = 'D8_CLOSURE'
              {pl_filter}
            ORDER BY de.embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """)

        rows = await self.db.execute(stmt, params)
        candidates: list[RecommendationCandidate] = []
        for row in rows.mappings():
            sim = row["similarity"]
            capa_id = str(row["entity_id"])
            candidates.append(RecommendationCandidate(
                source="historical_capa",
                content=row["d4_root_cause"] or row["chunk_text"],
                category=None,
                confidence=min(float(sim) * 0.8, 0.8),
                match_reason=f"历史 CAPA [{row['document_no']}] 相似问题",
                metadata={
                    "historical_capa_id": capa_id,
                    "document_no": row["document_no"],
                    "d5_correction": row["d5_correction"],
                    "product_line_code": row["product_line_code"],
                    "severity": row["severity"],
                    "source_updated_at": row["source_updated_at"],
                },
            ))
        return candidates


class RuleEngineSource:
    """规则引擎兜底 — D4 根因建议。"""

    name = "rule_engine"

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        from app.services.recommendation_service import RuleEngine

        engine = RuleEngine()
        d2 = context.capa_data.get("d2_description", "")
        result = engine.evaluate("failure_cause", {"input_text": d2, "failure_mode": d2})

        candidates: list[RecommendationCandidate] = []
        for s in result.suggestions:
            candidates.append(RecommendationCandidate(
                source="rule_engine",
                content=s.name,
                category=None,
                confidence=s.confidence * 0.5,
                match_reason="规则引擎推断",
                metadata={"explanation": s.explanation},
            ))
        return candidates


class RuleEngineMeasureSource:
    """规则引擎兜底 — D5 通用措施建议。"""

    name = "rule_engine"

    async def retrieve(self, context: RecommendationContext) -> list[RecommendationCandidate]:
        from app.services.recommendation_service import RuleEngine

        engine = RuleEngine()

        # Try to get AP level from linked FMEA
        ap_level = None
        linked_fmea = context.linked_fmea
        target_node_id = context.capa_data.get("fmea_node_id")
        if linked_fmea and linked_fmea.get("graph_data"):
            graph = linked_fmea["graph_data"]
            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            edges = graph.get("edges", [])

            target_fm_id = None
            if target_node_id:
                target_node = node_map.get(target_node_id)
                if target_node:
                    if target_node["type"] == "FailureMode":
                        target_fm_id = target_node_id
                    elif target_node["type"] == "FailureCause":
                        for e in edges:
                            if e["source"] == target_node_id and e["type"] == "CAUSE_OF":
                                parent = node_map.get(e["target"])
                                if parent and parent.get("type") == "FailureMode":
                                    target_fm_id = e["target"]
                                    break

            if target_fm_id and node_map.get(target_fm_id, {}).get("ap"):
                ap_level = node_map[target_fm_id]["ap"]
            else:
                for node in graph.get("nodes", []):
                    if node.get("type") == "FailureMode" and node.get("ap"):
                        ap_level = node["ap"]
                        break

        failure_mode_text = context.capa_data.get("d2_description", "")
        ctx = {"failure_mode": failure_mode_text, "ap": ap_level or "M"}
        result = engine.evaluate("measure", ctx)

        candidates: list[RecommendationCandidate] = []
        for s in result.suggestions:
            cat = s.explanation or "预防措施"
            if cat == "检测措施":
                cat = "探测措施"
            candidates.append(RecommendationCandidate(
                source="rule_engine",
                content=s.name,
                category=cat,
                confidence=s.confidence,
                match_reason=f"AP={ap_level or 'M'} 规则建议",
                metadata={"basis": f"AP={ap_level or 'M'}"},
            ))
        return candidates


class FMEAControlExpander:
    """D5 Stage 2: 基于召回的 FailureCause 做图遍历扩展 Controls。"""

    name = "fmea_graph"

    async def expand(
        self,
        cause_candidates: list[RecommendationCandidate],
        fmea_docs: list[dict[str, Any]],
    ) -> list[RecommendationCandidate]:
        """接收 Stage 1 召回的 FailureCause 候选，扩展出 Control 候选。"""
        controls: list[RecommendationCandidate] = []
        seen: set[tuple[str, str]] = set()

        # Build fmea_id -> doc map
        doc_map = {str(doc["fmea_id"]): doc for doc in fmea_docs if doc.get("graph_data")}

        for cause_candidate in cause_candidates:
            cause_id = cause_candidate.metadata.get("failure_cause_node_id")
            fmea_id = cause_candidate.metadata.get("fmea_id")
            if not cause_id or not fmea_id:
                continue

            doc = doc_map.get(fmea_id)
            if not doc:
                continue

            graph = doc["graph_data"]
            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            edges = graph.get("edges", [])

            forward_edges: dict[str, list[tuple[str, str]]] = {}
            for e in edges:
                forward_edges.setdefault(e["source"], []).append((e["target"], e["type"]))

            fm_id = cause_candidate.metadata.get("failure_mode_node_id")
            fm_name = cause_candidate.metadata.get("failure_mode_name")
            cause_name = cause_candidate.content

            # Path 1: Cause -> PREVENTED_BY -> PreventionControl
            for tgt, etype in forward_edges.get(cause_id, []):
                if etype == "PREVENTED_BY":
                    ctrl = node_map.get(tgt)
                    if ctrl and ctrl.get("type") == "PreventionControl":
                        key = (tgt, "prevention")
                        if key not in seen:
                            seen.add(key)
                            controls.append(RecommendationCandidate(
                                source="fmea_graph",
                                content=ctrl.get("name", ""),
                                category="prevention",
                                confidence=0.6,
                                match_reason="FMEA 预防措施",
                                metadata={
                                    "failure_mode_node_id": fm_id,
                                    "failure_mode_name": fm_name,
                                    "failure_cause_node_id": cause_id,
                                    "failure_cause_name": cause_name,
                                    "control_node_id": tgt,
                                    "control_type": "prevention",
                                    "fmea_id": fmea_id,
                                    "fmea_document_no": doc.get("document_no"),
                                },
                            ))

            # Path 2: Cause -> DETECTED_BY -> DetectionControl
            for tgt, etype in forward_edges.get(cause_id, []):
                if etype == "DETECTED_BY":
                    ctrl = node_map.get(tgt)
                    if ctrl and ctrl.get("type") == "DetectionControl":
                        key = (tgt, "detection")
                        if key not in seen:
                            seen.add(key)
                            controls.append(RecommendationCandidate(
                                source="fmea_graph",
                                content=ctrl.get("name", ""),
                                category="detection",
                                confidence=0.55,
                                match_reason="FMEA 探测措施（原因级）",
                                metadata={
                                    "failure_mode_node_id": fm_id,
                                    "failure_mode_name": fm_name,
                                    "failure_cause_node_id": cause_id,
                                    "failure_cause_name": cause_name,
                                    "control_node_id": tgt,
                                    "control_type": "detection",
                                    "fmea_id": fmea_id,
                                    "fmea_document_no": doc.get("document_no"),
                                },
                            ))

            # Path 3: FailureMode -> DETECTED_BY -> DetectionControl
            if fm_id:
                for tgt, etype in forward_edges.get(fm_id, []):
                    if etype == "DETECTED_BY":
                        ctrl = node_map.get(tgt)
                        if ctrl and ctrl.get("type") == "DetectionControl":
                            key = (tgt, "detection")
                            if key not in seen:
                                seen.add(key)
                                controls.append(RecommendationCandidate(
                                    source="fmea_graph",
                                    content=ctrl.get("name", ""),
                                    category="detection",
                                    confidence=0.5,
                                    match_reason="FMEA 探测措施（失效模式级）",
                                    metadata={
                                        "failure_mode_node_id": fm_id,
                                        "failure_mode_name": fm_name,
                                        "failure_cause_node_id": cause_id,
                                        "failure_cause_name": cause_name,
                                        "control_node_id": tgt,
                                        "control_type": "detection",
                                        "fmea_id": fmea_id,
                                    "fmea_document_no": doc.get("document_no"),
                                    },
                                ))

        return controls
