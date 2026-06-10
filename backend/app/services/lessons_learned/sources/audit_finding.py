import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_finding import AuditFinding
from app.models.audit_plan import AuditPlan
from app.services.lessons_learned.context import LessonsLearnedContext
from app.services.lessons_learned.sources.base import LessonsSource
from app.services.recommendation_types import RecommendationCandidate


class AuditFindingSource(LessonsSource):
    """审核发现项召回源 — pgvector 语义搜索 + audit_plans JOIN。"""

    name = "audit_finding"

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

        # Query via pgvector on document_embeddings
        pl_filter = ""
        params: dict = {"embedding": embedding_vec, "limit": 20}
        if context.user_product_lines is not None:
            placeholders = ", ".join(f":pl{i}" for i in range(len(context.user_product_lines)))
            pl_filter = f"AND ap.product_line_code IN ({placeholders})"
            for i, pl in enumerate(context.user_product_lines):
                params[f"pl{i}"] = pl

        stmt = text(f"""
            SELECT
                de.entity_id,
                de.chunk_text,
                ap.plan_no,
                ap.product_line_code,
                ap.audit_category,
                1 - (de.embedding <=> :embedding) AS similarity
            FROM document_embeddings de
            JOIN audit_findings af ON af.finding_id = de.entity_id
            JOIN audit_plans ap ON ap.audit_id = af.audit_id
            WHERE de.entity_type = 'audit_finding'
              AND af.corrective_action IS NOT NULL
              AND af.status = 'closed'
              {pl_filter}
            ORDER BY de.embedding <=> :embedding
            LIMIT :limit
        """)

        result = await self.db.execute(stmt, params)
        rows = result.fetchall()

        candidates: list[RecommendationCandidate] = []
        for row in rows:
            finding_id, chunk_text, plan_no, pl_code, audit_category, similarity = row
            same_pl = pl_code == context.product_line_code
            confidence = min(similarity + (0.1 if same_pl else 0.0), 0.85)

            candidates.append(
                RecommendationCandidate(
                    source=self.name,
                    content=chunk_text[:100],
                    category=None,
                    confidence=round(confidence, 2),
                    match_reason="语义搜索" if similarity > 0.5 else "审核发现匹配",
                    metadata={
                        "finding_id": str(finding_id),
                        "document_no": plan_no,
                        "product_line_code": pl_code,
                        "same_product_line": same_pl,
                        "action": None,
                        "severity": None,
                        "source_type": "audit",
                        "audit_id": str(finding_id),
                        "audit_category": audit_category,
                    },
                )
            )

        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[:10]
