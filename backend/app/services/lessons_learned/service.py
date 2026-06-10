import hashlib
import json
import uuid as _uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD
from app.models.recommendation_cache import RecommendationCache
from app.models.user import User
from app.schemas.lessons_learned import LessonsLearnedResponse, LessonCard, LessonCategories
from app.services.lessons_learned.context import LessonsLearnedContext
from app.services.lessons_learned.sources.historical_fmea import HistoricalFMEASource
from app.services.lessons_learned.sources.historical_capa import LessonsCAPASource
from app.services.lessons_learned.sources.audit_finding import AuditFindingSource
from app.services.lessons_learned.sources.semantic import LessonsSemanticSource
from app.services.lessons_learned.sources.rule_engine import LessonsRuleSource
from app.services.lessons_learned.fusion import LessonsFusionEngine
from app.services.recommendation_types import RecommendationCandidate


class LessonsLearnedService:
    """Orchestrate lessons learned retrieval for new FMEA/CAPA documents."""

    def __init__(
        self,
        db: AsyncSession,
        embedding: object | None,
    ):
        self.db = db
        self.embedding = embedding
        self.fusion = LessonsFusionEngine()

    async def recommend(
        self,
        doc_id: _uuid.UUID,
        doc_type: str,
        problem_description: str | None,
        user: User,
        skip_fmea_sources: bool = False,
    ) -> LessonsLearnedResponse:
        # 1. Build context
        context = await self._build_context(doc_id, doc_type, problem_description, user)

        # 2. Check cache
        context_hash = self._compute_context_hash(context, skip_fmea_sources)
        cached = await self._get_cached(context_hash)
        if cached:
            return cached

        # 3. Retrieve from all sources
        sources: list = [
            LessonsCAPASource(self.db, self.embedding),
            AuditFindingSource(self.db, self.embedding),
            LessonsRuleSource(),
        ]
        if not skip_fmea_sources:
            sources.insert(0, HistoricalFMEASource(self.db))
            sources.insert(3, LessonsSemanticSource(self.db, self.embedding))

        all_candidates = []
        active_sources = []
        for source in sources:
            try:
                candidates = await source.retrieve(context)
                if candidates:
                    all_candidates.extend(candidates)
                    active_sources.append(source.name)
            except Exception:
                # Source failures are non-fatal
                pass

        # 4. Fusion
        fused = self.fusion.merge(all_candidates, context.product_line_code)

        # 5. Categorize
        highlights, categories = self._categorize(fused, context.product_line_code)

        # 6. Build response
        response = LessonsLearnedResponse(
            highlights=highlights,
            categories=categories,
            source=" + ".join(active_sources) if active_sources else "rule_engine",
            cached=False,
        )

        # 7. Cache
        await self._cache_result(context_hash, context, response)

        return response

    async def _build_context(
        self,
        doc_id: _uuid.UUID,
        doc_type: str,
        problem_description: str | None,
        user: User,
    ) -> LessonsLearnedContext:
        from app.core.product_line_filter import get_user_product_line_codes

        # Load document
        if doc_type == "fmea":
            result = await self.db.execute(select(FMEADocument).where(FMEADocument.fmea_id == doc_id))
            doc = result.scalar_one()
            query_text = problem_description or doc.title
            user_pls = (
                await get_user_product_line_codes(user, self.db)
                if not user.role_definition.bypass_row_level_security
                else None
            )
            return LessonsLearnedContext(
                doc_type="fmea",
                doc_id=doc_id,
                query_text=query_text,
                fmea_type=doc.fmea_type,
                severity=None,
                product_line_code=doc.product_line_code,
                user_product_lines=user_pls,
            )
        else:
            result = await self.db.execute(select(CAPAEightD).where(CAPAEightD.report_id == doc_id))
            doc = result.scalar_one()
            query_text = problem_description or doc.title
            user_pls = (
                await get_user_product_line_codes(user, self.db)
                if not user.role_definition.bypass_row_level_security
                else None
            )
            return LessonsLearnedContext(
                doc_type="capa",
                doc_id=doc_id,
                query_text=query_text,
                fmea_type=None,
                severity=doc.severity,
                product_line_code=doc.product_line_code,
                user_product_lines=user_pls,
                fmea_ref_id=doc.fmea_ref_id,
            )

    def _compute_context_hash(self, context: LessonsLearnedContext, skip_fmea_sources: bool = False) -> str:
        raw = json.dumps({
            "query_text": context.query_text,
            "product_line_code": context.product_line_code,
            "doc_type": context.doc_type,
            "fmea_type": context.fmea_type,
            "severity": context.severity,
            "pl_hash": context.pl_hash_for_cache(),
            "fmea_sources": not skip_fmea_sources,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    async def _get_cached(self, context_hash: str) -> LessonsLearnedResponse | None:
        stmt = (
            select(RecommendationCache)
            .where(RecommendationCache.trigger_type == "lessons_learned")
            .where(RecommendationCache.context_hash == context_hash)
            .where(RecommendationCache.fmea_id.is_(None))
            .where(RecommendationCache.report_id.is_(None))
            .where(RecommendationCache.expires_at > func.now())
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            suggestions = row.suggestions
            highlights, categories = self._categorize_from_raw(suggestions)
            return LessonsLearnedResponse(
                highlights=highlights,
                categories=categories,
                source=row.source,
                cached=True,
            )
        return None

    async def _cache_result(
        self,
        context_hash: str,
        context: LessonsLearnedContext,
        response: LessonsLearnedResponse,
    ) -> None:
        stmt = (
            pg_insert(RecommendationCache)
            .values(
                trigger_type="lessons_learned",
                context_hash=context_hash,
                product_line_code=context.product_line_code,
                doc_type=context.doc_type,
                fmea_type=context.fmea_type,
                suggestions=[c.model_dump() for c in self._flatten(response)],
                source=response.source,
                llm_available=False,
                expires_at=func.now() + text("INTERVAL '24 hours'"),
            )
            .on_conflict_do_update(
                index_elements=["trigger_type", "context_hash"],
                index_where=text("fmea_id IS NULL AND report_id IS NULL"),
                set_={
                    "suggestions": [c.model_dump() for c in self._flatten(response)],
                    "source": response.source,
                    "llm_available": False,
                    "product_line_code": context.product_line_code,
                    "doc_type": context.doc_type,
                    "fmea_type": context.fmea_type,
                    "created_at": func.now(),
                    "expires_at": func.now() + text("INTERVAL '24 hours'"),
                },
            )
        )
        await self.db.execute(stmt)

    def _categorize(
        self,
        candidates: list[RecommendationCandidate],
        current_pl: str,
    ) -> tuple[list[LessonCard], LessonCategories]:
        fmea_cards: list[LessonCard] = []
        capa_cards: list[LessonCard] = []
        audit_cards: list[LessonCard] = []

        for c in candidates:
            source_type = self._infer_source_type(c)
            same_pl = c.metadata.get("product_line_code") == current_pl
            card = LessonCard(
                id=f"{c.source}:{c.metadata.get('document_no', '')}:{c.content[:20]}",
                title=c.content[:100],
                summary=c.match_reason,
                source_type=source_type,
                source_document_no=c.metadata.get("document_no", ""),
                source_id=c.metadata.get("fmea_id") or c.metadata.get("capa_id") or c.metadata.get("finding_id", ""),
                source_product_line=c.metadata.get("product_line_code", ""),
                same_product_line=same_pl,
                confidence=c.confidence,
                match_reason=c.match_reason,
                root_cause=c.metadata.get("root_cause"),
                action=c.metadata.get("action"),
                severity=c.metadata.get("severity"),
                metadata={k: v for k, v in c.metadata.items() if k not in {
                    "fmea_id", "capa_id", "finding_id", "document_no", "product_line_code",
                    "root_cause", "action", "severity", "source_type",
                }},
            )
            if source_type == "fmea":
                fmea_cards.append(card)
            elif source_type == "capa":
                capa_cards.append(card)
            else:
                audit_cards.append(card)

        all_cards = fmea_cards + capa_cards + audit_cards
        highlights = [c for c in all_cards if c.confidence >= 0.7][:2]

        return highlights, LessonCategories(fmea=fmea_cards, capa=capa_cards, audit=audit_cards)

    def _categorize_from_raw(self, suggestions: list[dict]) -> tuple[list[LessonCard], LessonCategories]:
        """Reconstruct LessonCards from cached raw dicts."""
        fmea_cards: list[LessonCard] = []
        capa_cards: list[LessonCard] = []
        audit_cards: list[LessonCard] = []

        for s in suggestions:
            source_type = s.get("source_type", "audit")
            card = LessonCard.model_validate(s)
            if source_type == "fmea":
                fmea_cards.append(card)
            elif source_type == "capa":
                capa_cards.append(card)
            else:
                audit_cards.append(card)

        all_cards = fmea_cards + capa_cards + audit_cards
        highlights = [c for c in all_cards if c.confidence >= 0.7][:2]
        return highlights, LessonCategories(fmea=fmea_cards, capa=capa_cards, audit=audit_cards)

    def _infer_source_type(self, candidate: RecommendationCandidate) -> str:
        # Metadata takes priority; fallback by source name
        explicit = candidate.metadata.get("source_type")
        if explicit in ("fmea", "capa", "audit"):
            return explicit
        name = candidate.source
        if name == "historical_fmea":
            return "fmea"
        elif name == "historical_capa":
            return "capa"
        elif name == "audit_finding":
            return "audit"
        elif name == "semantic_search":
            return candidate.metadata.get("source_type", "fmea")
        else:
            return candidate.metadata.get("source_type", "fmea")

    def _flatten(self, response: LessonsLearnedResponse) -> list[LessonCard]:
        """Flatten all cards back to LessonCard dicts for caching."""
        all_cards = (
            response.highlights
            + response.categories.fmea
            + response.categories.capa
            + response.categories.audit
        )
        # Deduplicate by id
        seen: set[str] = set()
        unique: list[LessonCard] = []
        for c in all_cards:
            if c.id not in seen:
                seen.add(c.id)
                unique.append(c)
        return unique
