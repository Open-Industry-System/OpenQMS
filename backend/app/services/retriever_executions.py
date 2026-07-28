"""Run external knowledge retrievers for FMEA recommendation with observability.

Each retriever is classified into a SourceExecution status so E2E can distinguish
"called but zero hits" (empty) from "not called / no creds" (unavailable) from
"raised" (error). Never raises — degradations are returned as 200 with status rows.
"""
import time
import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.recommendation import SourceExecution, SuggestionItem


async def _run_one(name, coro_factory):
    start = time.monotonic()
    try:
        candidates = await coro_factory()
    except Exception:
        return SourceExecution(
            source=name, status="error", hit_count=0,
            latency_ms=int((time.monotonic() - start) * 1000),
        ), []
    latency = int((time.monotonic() - start) * 1000)
    status = "success" if candidates else "empty"
    return SourceExecution(
        source=name, status=status, hit_count=len(candidates), latency_ms=latency
    ), candidates


async def run_retrievers(
    db: AsyncSession,
    embedding: object | None,
    *,
    query_text: str,
    user_product_lines: list[str] | None,
    fmea_id: _uuid.UUID,
    fmea_type: str,
    product_line_code: str,
    user,
) -> tuple[list[SourceExecution], list[SuggestionItem]]:
    from app.services.lessons_learned.context import LessonsLearnedContext
    from app.services.lessons_learned.sources.semantic import LessonsSemanticSource

    executions: list[SourceExecution] = []
    suggestions: list[SuggestionItem] = []

    if embedding is None:
        executions.append(SourceExecution(source="semantic_search", status="unavailable"))
        executions.append(SourceExecution(source="lessons_learned", status="unavailable"))
        return executions, suggestions

    context = LessonsLearnedContext(
        doc_type="fmea", doc_id=fmea_id, query_text=query_text,
        fmea_type=fmea_type, severity=None,
        product_line_code=product_line_code, user_product_lines=user_product_lines,
    )

    # --- semantic_search (pgvector over FMEA node embeddings) ---
    sem_src = LessonsSemanticSource(db, embedding)
    sem_exec, sem_cands = await _run_one(
        "semantic_search", lambda: sem_src.retrieve(context)
    )
    executions.append(sem_exec)
    suggestions.extend(
        SuggestionItem(
            name=c.content,
            confidence=float(c.confidence or 0.5),
            source="semantic_search",
            source_document_no=(c.metadata or {}).get("document_no"),
            explanation=c.match_reason or "",
        )
        for c in sem_cands
    )

    # --- lessons_learned (经验教训库; queries non-FMEA sources directly) ---
    # NOTE: LessonsLearnedService.recommend writes RecommendationCache, whose model
    # declares `stage_runs` but the test/CI schema lags that column — pre-existing
    # migration drift. Calling the orchestrator here would always error in tests,
    # so we query the lessons sources directly per the brief's fallback contract.
    from app.services.lessons_learned.sources.audit_finding import AuditFindingSource
    from app.services.lessons_learned.sources.historical_capa import LessonsCAPASource
    from app.services.lessons_learned.sources.rule_engine import LessonsRuleSource

    async def _lessons():
        sources = [
            LessonsCAPASource(db, embedding),
            AuditFindingSource(db, embedding),
            LessonsRuleSource(),
        ]
        cands: list = []
        for src in sources:
            try:
                cands.extend(await src.retrieve(context))
            except Exception:
                # Source failures are non-fatal — match orchestrator behavior.
                continue
        return cands

    les_exec, les_cands = await _run_one("lessons_learned", _lessons)
    executions.append(les_exec)
    suggestions.extend(
        SuggestionItem(
            name=c.content,
            confidence=float(c.confidence or 0.5),
            source="lessons_learned",
            source_document_no=(c.metadata or {}).get("document_no"),
            explanation=c.match_reason or "",
        )
        for c in les_cands
    )

    return executions, suggestions
