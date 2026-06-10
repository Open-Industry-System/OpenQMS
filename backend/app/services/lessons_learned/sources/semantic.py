from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.lessons_learned.context import LessonsLearnedContext
from app.services.lessons_learned.sources.base import LessonsSource
from app.services.recommendation_types import RecommendationCandidate


class LessonsSemanticSource(LessonsSource):
    """Lessons 专用语义搜索 adapter — 复用 pgvector 基础设施，搜索 FMEA nodes。"""

    name = "semantic_search"

    def __init__(self, db: AsyncSession, embedding: object | None):
        self.db = db
        self.embedding = embedding

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        if self.embedding is None:
            return []

        try:
            embedding_vec = await self.embedding.embed(context.query_text)
        except Exception:
            return []

        pl_filter = ""
        params: dict = {"embedding": embedding_vec, "limit": 20}
        if context.user_product_lines is not None:
            placeholders = ", ".join(f":pl{i}" for i in range(len(context.user_product_lines)))
            pl_filter = f"AND de.product_line_code IN ({placeholders})"
            for i, pl in enumerate(context.user_product_lines):
                params[f"pl{i}"] = pl

        stmt = text(f"""
            SELECT
                de.entity_id,
                de.entity_type,
                de.node_id,
                de.chunk_text,
                de.product_line_code,
                de.metadata,
                1 - (de.embedding <=> :embedding) AS similarity
            FROM document_embeddings de
            WHERE de.entity_type = 'fmea_node'
              {pl_filter}
            ORDER BY de.embedding <=> :embedding
            LIMIT :limit
        """)

        result = await self.db.execute(stmt, params)
        rows = result.fetchall()

        candidates: list[RecommendationCandidate] = []
        for row in rows:
            entity_id, entity_type, node_id, chunk_text, pl_code, meta, similarity = row
            same_pl = pl_code == context.product_line_code
            confidence = min(similarity + (0.1 if same_pl else 0.0), 0.85)

            candidates.append(
                RecommendationCandidate(
                    source=self.name,
                    content=chunk_text[:100],
                    category=None,
                    confidence=round(confidence, 2),
                    match_reason="语义搜索",
                    metadata={
                        "fmea_id": str(entity_id),
                        "document_no": meta.get("document_no", "") if isinstance(meta, dict) else "",
                        "product_line_code": pl_code,
                        "same_product_line": same_pl,
                        "node_id": node_id,
                        "source_type": "fmea",
                    },
                )
            )

        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[:10]
