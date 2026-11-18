import hashlib
from types import SimpleNamespace
import json
import uuid as _uuid

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capa import CAPAEightD
from app.models.fmea import FMEADocument
from app.models.recommendation_cache import RecommendationCache
from app.models.user import User
from app.schemas.lessons_learned import LessonCard, LessonCategories, LessonsLearnedResponse
from app.services.lessons_learned.context import LessonsLearnedContext
from app.services.lessons_learned.fusion import LessonsFusionEngine
from app.services.lessons_learned.sources.audit_finding import AuditFindingSource
from app.services.lessons_learned.sources.historical_capa import LessonsCAPASource
from app.services.lessons_learned.sources.historical_fmea import HistoricalFMEASource
from app.services.lessons_learned.sources.rule_engine import LessonsRuleSource
from app.services.lessons_learned.sources.semantic import LessonsSemanticSource
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

    async def _target_version(self):
        from app.services.capa_d4_material import legacy_capa_read_binding
        from app.services.fmea_agent_sources import visible_fmea_source
        kind, doc_id, user = self._release_target
        if kind == 'capa':
            token = await legacy_capa_read_binding(self.db, user, doc_id)
            factory = await self.db.scalar(select(CAPAEightD.factory_id).where(CAPAEightD.report_id == doc_id))
        else:
            source = await visible_fmea_source(self.db, SimpleNamespace(user=user), doc_id)
            factory = source.factory_id
            token = await self.db.scalar(select(FMEADocument.lock_version).where(FMEADocument.fmea_id == doc_id))
        return token, str(factory)

    async def require_current_release(self):
        from app.services.capa_d4_material import require_legacy_candidate_bindings, require_current_egress_statement
        await require_current_egress_statement(self.db)
        if await self._target_version() != self._release_version:
            raise PermissionError('D4_LESSONS_INPUT_CHANGED')
        await require_legacy_candidate_bindings(self.db, self._release_bindings, actor=self._release_target[2])

    async def recommend(
        self,
        doc_id: _uuid.UUID,
        doc_type: str,
        problem_description: str | None,
        user: User,
        skip_fmea_sources: bool = False,
    ) -> LessonsLearnedResponse:
        self._release_target = (doc_type, doc_id, user)
        self._release_bindings = ()
        self._release_version = await self._target_version()
        # 1. Build context
        context = await self._build_context(doc_id, doc_type, problem_description, user)

        context.actor_id = user.user_id
        # 2. Check cache
        context_hash = self._compute_context_hash(context, skip_fmea_sources)
        cached = await self._get_cached(context_hash)
        if cached:
            await self.require_current_release()
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
            await self.require_current_release()
            try:
                from app.services.egress_guard import with_delivery_guard
                candidates = await with_delivery_guard(self.require_current_release, lambda: source.retrieve(context))
                if candidates:
                    from app.services.capa_d4_material import capture_legacy_candidate_bindings
                    captured = await capture_legacy_candidate_bindings(self.db, candidates, actor=user)
                    self._release_bindings = tuple(sorted(set(self._release_bindings + captured)))
                    all_candidates.extend(candidates)
                    active_sources.append(source.name)
            except PermissionError:
                raise
            except Exception:
                # Source failures are non-fatal
                pass

        await self.require_current_release()
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

        await self.require_current_release()
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
        from app.services.capa_legacy_cache import load_cache
        await self.require_current_release()
        cached = await load_cache(self.db, dict(kind='lessons', context_hash=context_hash, target_type=self._release_target[0],
            target_id=str(self._release_target[1]), target_version=list(self._release_version)),
            (RecommendationCache.trigger_type == 'lessons_learned',
             RecommendationCache.context_hash == context_hash,
             RecommendationCache.fmea_id.is_(None), RecommendationCache.report_id.is_(None),
             RecommendationCache.expires_at > func.now()), actor=self._release_target[2])
        if cached is None:
            return None
        cards, self._release_bindings, details = cached
        await self.require_current_release()
        highlights, categories = self._categorize_from_raw(cards)
        return LessonsLearnedResponse(highlights=highlights, categories=categories,
            source=details['source'], cached=True)

    async def _cache_result(
        self,
        context_hash: str,
        context: LessonsLearnedContext,
        response: LessonsLearnedResponse,
    ) -> None:
        await self.require_current_release()
        cards = [c.model_dump() for c in self._flatten(response)]
        from app.services.capa_legacy_cache import seal_cache
        envelope = seal_cache(self.db, dict(kind='lessons', context_hash=context_hash, target_type=self._release_target[0],
            target_id=str(self._release_target[1]), target_version=list(self._release_version)),
            self._release_bindings, cards, dict(source=response.source))
        stmt = (
            pg_insert(RecommendationCache)
            .values(
                trigger_type="lessons_learned",
                factory_id=_uuid.UUID(self._release_version[1]),
                context_hash=context_hash,
                product_line_code=context.product_line_code,
                doc_type=context.doc_type,
                fmea_type=context.fmea_type,
                suggestions=envelope,
                source=response.source,
                llm_available=False,
                expires_at=func.now() + text("INTERVAL '24 hours'"),
            )
            .on_conflict_do_update(
                index_elements=["trigger_type", "context_hash"],
                index_where=text("fmea_id IS NULL AND report_id IS NULL"),
                set_={
                    "suggestions": envelope,
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
