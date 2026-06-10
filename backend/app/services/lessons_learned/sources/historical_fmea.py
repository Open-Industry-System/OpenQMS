import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.services.lessons_learned.context import LessonsLearnedContext
from app.services.lessons_learned.sources.base import LessonsSource
from app.services.recommendation_types import RecommendationCandidate


class HistoricalFMEASource(LessonsSource):
    """历史 FMEA 失效模式召回源 — 关键词匹配 approved FMEA 的 FailureMode 节点。"""

    name = "historical_fmea"

    def __init__(self, db: AsyncSession):
        self.db = db

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        keywords = self._extract_keywords(context.query_text)
        if not keywords:
            return []

        # Step 1: Keyword-match via document_embeddings to find candidate FMEA IDs
        ilike_clauses = " OR ".join(
            f"(de.chunk_text ILIKE :kw{i} OR de.chunk_text ILIKE :kw_desc{i})"
            for i in range(len(keywords))
        )
        params = {}
        for i, kw in enumerate(keywords):
            params[f"kw{i}"] = f"%{kw}%"
            params[f"kw_desc{i}"] = f"%{kw}%"

        pl_filter = ""
        if context.user_product_lines is not None:
            placeholders = ", ".join(f":pl{i}" for i in range(len(context.user_product_lines)))
            pl_filter = f"AND de.product_line_code IN ({placeholders})"
            for i, pl in enumerate(context.user_product_lines):
                params[f"pl{i}"] = pl

        params["limit"] = 50

        embed_stmt = text(f"""
            SELECT DISTINCT de.entity_id
            FROM document_embeddings de
            WHERE de.entity_type = 'fmea_node'
              AND (de.metadata->>'node_type' = 'FailureMode'
                   OR de.metadata->>'node_type' = 'FailureCause')
              AND ({ilike_clauses})
              {pl_filter}
            LIMIT :limit
        """)
        embed_result = await self.db.execute(embed_stmt, params)
        matched_fmea_ids = [row[0] for row in embed_result.fetchall()]

        if not matched_fmea_ids:
            return []

        # Step 2: Load only the matched FMEA documents
        query = (
            select(FMEADocument)
            .where(FMEADocument.fmea_id.in_(matched_fmea_ids))
            .where(FMEADocument.status == "approved")
            .where(FMEADocument.fmea_id != context.doc_id)
        )
        if context.user_product_lines is not None:
            query = query.where(FMEADocument.product_line_code.in_(context.user_product_lines))

        result = await self.db.execute(query)
        fmeas = result.scalars().all()

        candidates: list[RecommendationCandidate] = []
        for fmea in fmeas:
            graph = fmea.graph_data or {}
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])
            node_map = {n["id"]: n for n in nodes}

            # Build edge lookups
            forward_edges: dict[str, list[tuple[str, str]]] = {}
            reverse_edges: dict[str, list[tuple[str, str]]] = {}
            for e in edges:
                forward_edges.setdefault(e["source"], []).append((e["target"], e["type"]))
                reverse_edges.setdefault(e["target"], []).append((e["source"], e["type"]))

            for node in nodes:
                if node.get("type") != "FailureMode":
                    continue
                fm_name = node.get("name", "")
                fm_desc = node.get("description", "")
                if not any(kw in fm_name or kw in fm_desc for kw in keywords):
                    continue

                # Determine confidence based on product line match
                same_pl = fmea.product_line_code == context.product_line_code
                confidence = 0.7 if same_pl else 0.5

                # Extract associated causes
                cause_names: list[str] = []
                for src_id, etype in reverse_edges.get(node["id"], []):
                    if etype == "CAUSE_OF":
                        cause_node = node_map.get(src_id)
                        if cause_node and cause_node.get("type") == "FailureCause":
                            cause_names.append(cause_node.get("name", ""))

                # Extract controls
                prevention: list[str] = []
                detection: list[str] = []
                for tgt_id, etype in forward_edges.get(node["id"], []):
                    if etype == "PREVENTED_BY":
                        ctrl = node_map.get(tgt_id)
                        if ctrl and ctrl.get("type") == "PreventionControl":
                            prevention.append(ctrl.get("name", ""))
                    elif etype == "DETECTED_BY":
                        ctrl = node_map.get(tgt_id)
                        if ctrl and ctrl.get("type") == "DetectionControl":
                            detection.append(ctrl.get("name", ""))

                controls_str = ""
                if prevention:
                    controls_str += f"预防措施: {', '.join(prevention)}; "
                if detection:
                    controls_str += f"探测措施: {', '.join(detection)}"

                summary = f"失效模式: {fm_name}"
                if cause_names:
                    summary += f" | 根因: {', '.join(cause_names)}"
                if controls_str:
                    summary += f" | {controls_str}"

                candidates.append(
                    RecommendationCandidate(
                        source=self.name,
                        content=fm_name,
                        category=None,
                        confidence=confidence,
                        match_reason="相似失效模式" if same_pl else "关键词匹配",
                        metadata={
                            "fmea_id": str(fmea.fmea_id),
                            "document_no": fmea.document_no,
                            "product_line_code": fmea.product_line_code,
                            "same_product_line": same_pl,
                            "root_cause": ", ".join(cause_names) if cause_names else None,
                            "action": controls_str.strip() or None,
                            "severity": node.get("severity"),
                            "source_type": "fmea",
                        },
                    )
                )

        # Sort by confidence desc
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[:10]

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from query text."""
        if not text:
            return []
        # Simple heuristic: split by common delimiters, filter short words
        import re
        words = re.split(r"[,，;；\s]+", text)
        return [w.strip() for w in words if len(w.strip()) >= 2][:5]
