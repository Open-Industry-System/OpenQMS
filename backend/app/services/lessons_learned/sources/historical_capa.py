import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa import CAPAEightD
from app.services.lessons_learned.context import LessonsLearnedContext
from app.services.lessons_learned.sources.base import LessonsSource
from app.services.recommendation_types import RecommendationCandidate


class LessonsCAPASource(LessonsSource):
    """历史 CAPA 召回源 — pgvector 语义搜索已关闭 CAPA 的 d2_description。"""

    name = "historical_capa"

    def __init__(self, db: AsyncSession, embedding: object | None):
        self.db = db
        self.embedding = embedding

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        if self.embedding is None:
            return []

        if not context.query_text or not context.query_text.strip():
            return []

        try:
            query_vector = await self.embedding.embed([context.query_text])
            if not query_vector:
                return []
            vec_str = "[" + ",".join(str(v) for v in query_vector[0]) + "]"
        except Exception:
            return []

        # pgvector semantic search on capa d2_description embeddings
        pl_filter = ""
        params: dict = {"query_vector": vec_str, "limit": 20}
        if context.user_product_lines is not None:
            placeholders = ", ".join(f":pl{i}" for i in range(len(context.user_product_lines)))
            pl_filter = f"AND de.product_line_code IN ({placeholders})"
            for i, pl in enumerate(context.user_product_lines):
                params[f"pl{i}"] = pl

        stmt = text(f"""
            SELECT
                de.entity_id,
                de.chunk_text,
                de.product_line_code,
                1 - (de.embedding <=> CAST(:query_vector AS vector)) AS similarity
            FROM document_embeddings de
            WHERE de.entity_type = 'capa'
              AND de.entity_field = 'd2_description'
              {pl_filter}
            ORDER BY de.embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        """)

        result = await self.db.execute(stmt, params)
        rows = result.fetchall()
        if not rows:
            return []

        capa_ids = [row[0] for row in rows]
        capa_query = (
            select(CAPAEightD)
            .where(CAPAEightD.report_id.in_(capa_ids))
            .where(CAPAEightD.status.in_(["D8_CLOSURE", "ARCHIVED"]))
            .where(CAPAEightD.report_id != context.doc_id)
        )
        capa_result = await self.db.execute(capa_query)
        capa_map = {c.report_id: c for c in capa_result.scalars().all()}

        candidates: list[RecommendationCandidate] = []
        for row in rows:
            capa_id, chunk_text, pl_code, similarity = row
            capa = capa_map.get(capa_id)
            if not capa:
                continue

            same_pl = pl_code == context.product_line_code
            confidence = min(similarity + (0.1 if same_pl else 0.0), 0.85)

            candidates.append(
                RecommendationCandidate(
                    source=self.name,
                    content=capa.d4_root_cause or chunk_text[:100],
                    category=None,
                    confidence=round(confidence, 2),
                    match_reason="语义搜索" if similarity > 0.5 else "历史CAPA匹配",
                    metadata={
                        "capa_id": str(capa.report_id),
                        "document_no": capa.document_no,
                        "product_line_code": pl_code or capa.product_line_code,
                        "same_product_line": same_pl,
                        "root_cause": capa.d4_root_cause,
                        "action": capa.d5_correction,
                        "severity": capa.severity,
                        "source_type": "capa",
                    },
                )
            )

        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[:10]
