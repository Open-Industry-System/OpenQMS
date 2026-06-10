"""Unit tests for lessons learned smart push.

Covers: LessonsFusionEngine, LessonsLearnedService (cache hash, skip_fmea_sources),
source adapters (HistoricalFMEASource embedding two-step query, LessonsCAPASource,
AuditFindingSource audit_id), and _infer_source_type.
"""
import uuid

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.lessons_learned.context import LessonsLearnedContext
from app.services.lessons_learned.fusion import LessonsFusionEngine
from app.services.lessons_learned.service import LessonsLearnedService
from app.services.recommendation_types import RecommendationCandidate


# ---------------------------------------------------------------------------
# FusionEngine
# ---------------------------------------------------------------------------

class TestLessonsFusionEngine:
    def test_deduplicate_by_content(self):
        engine = LessonsFusionEngine()
        candidates = [
            RecommendationCandidate("historical_fmea", "焊接虚焊", None, 0.7, "", {}),
            RecommendationCandidate("historical_capa", "焊接虚焊", None, 0.8, "", {}),
        ]
        result = engine.merge(candidates, "DC-DC-100")
        assert len(result) == 1
        assert result[0].source == "historical_capa"  # higher after priority

    def test_pl_boost(self):
        engine = LessonsFusionEngine()
        candidates = [
            RecommendationCandidate("semantic_search", "A", None, 0.7, "", {"product_line_code": "DC-DC-100"}),
            RecommendationCandidate("semantic_search", "B", None, 0.7, "", {"product_line_code": "OTHER"}),
        ]
        result = engine.merge(candidates, "DC-DC-100")
        # A: 0.7 * 0.7 + 0.10 = 0.59; B: 0.7 * 0.7 + 0 = 0.49
        assert result[0].content == "A"

    def test_cap_at_10(self):
        engine = LessonsFusionEngine()
        candidates = [
            RecommendationCandidate("rule_engine", f"item_{i}", None, 0.5, "", {})
            for i in range(20)
        ]
        result = engine.merge(candidates, "DC-DC-100")
        assert len(result) == 10


# ---------------------------------------------------------------------------
# Cache hash includes skip_fmea_sources
# ---------------------------------------------------------------------------

class TestCacheHashFmeaPermission:
    def test_different_hash_when_skip_fmea_sources(self):
        service = LessonsLearnedService(db=None, embedding=None)
        ctx = LessonsLearnedContext(
            doc_type="capa",
            doc_id=uuid.uuid4(),
            query_text="焊接不良",
            fmea_type=None,
            severity="严重",
            product_line_code="DC-DC-100",
            user_product_lines=["DC-DC-100"],
        )
        hash_with_fmea = service._compute_context_hash(ctx, skip_fmea_sources=False)
        hash_without_fmea = service._compute_context_hash(ctx, skip_fmea_sources=True)
        assert hash_with_fmea != hash_without_fmea

    def test_same_hash_for_same_skip_flag(self):
        service = LessonsLearnedService(db=None, embedding=None)
        ctx = LessonsLearnedContext(
            doc_type="capa",
            doc_id=uuid.uuid4(),
            query_text="焊接不良",
            fmea_type=None,
            severity="严重",
            product_line_code="DC-DC-100",
            user_product_lines=["DC-DC-100"],
        )
        h1 = service._compute_context_hash(ctx, skip_fmea_sources=False)
        h2 = service._compute_context_hash(ctx, skip_fmea_sources=False)
        assert h1 == h2


# ---------------------------------------------------------------------------
# _infer_source_type
# ---------------------------------------------------------------------------

class TestInferSourceType:
    def test_metadata_takes_priority(self):
        service = LessonsLearnedService(db=None, embedding=None)
        c = RecommendationCandidate("semantic_search", "test", None, 0.5, "", {"source_type": "capa"})
        assert service._infer_source_type(c) == "capa"

    def test_fallback_by_source_name(self):
        service = LessonsLearnedService(db=None, embedding=None)
        c = RecommendationCandidate("audit_finding", "test", None, 0.5, "", {})
        assert service._infer_source_type(c) == "audit"

    def test_semantic_search_defaults_to_fmea(self):
        service = LessonsLearnedService(db=None, embedding=None)
        c = RecommendationCandidate("semantic_search", "test", None, 0.5, "", {})
        assert service._infer_source_type(c) == "fmea"


# ---------------------------------------------------------------------------
# HistoricalFMEASource: two-step query mock
# ---------------------------------------------------------------------------

class TestHistoricalFMEASource:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_keywords(self):
        from app.services.lessons_learned.sources.historical_fmea import HistoricalFMEASource

        db = AsyncMock()
        source = HistoricalFMEASource(db)
        ctx = LessonsLearnedContext(
            doc_type="fmea", doc_id=uuid.uuid4(), query_text="",
            fmea_type="PFMEA", severity=None,
            product_line_code="DC-DC-100", user_product_lines=["DC-DC-100"],
        )
        result = await source.retrieve(ctx)
        assert result == []

    @pytest.mark.asyncio
    async def test_matches_failure_mode_by_keyword(self):
        from app.services.lessons_learned.sources.historical_fmea import HistoricalFMEASource

        db = AsyncMock()
        fmea = MagicMock()
        fmea.fmea_id = uuid.uuid4()
        fmea.document_no = "PFMEA-001"
        fmea.product_line_code = "DC-DC-100"
        fmea.graph_data = {
            "nodes": [
                {"id": "fm1", "type": "FailureMode", "name": "焊接虚焊"},
                {"id": "cause1", "type": "FailureCause", "name": "温度不足"},
            ],
            "edges": [
                {"source": "cause1", "target": "fm1", "type": "CAUSE_OF"},
            ],
        }
        # Two-step execute: first embeddings, then FMEA documents
        embed_result = MagicMock(fetchall=MagicMock(return_value=[(fmea.fmea_id,)]))
        fmea_result = MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[fmea]))))
        db.execute.side_effect = [embed_result, fmea_result]

        source = HistoricalFMEASource(db)
        ctx = LessonsLearnedContext(
            doc_type="fmea", doc_id=uuid.uuid4(), query_text="焊接不良",
            fmea_type="PFMEA", severity=None,
            product_line_code="DC-DC-100", user_product_lines=["DC-DC-100"],
        )
        result = await source.retrieve(ctx)
        assert len(result) == 1
        assert result[0].content == "焊接虚焊"
        assert result[0].metadata["same_product_line"] is True


# ---------------------------------------------------------------------------
# AuditFindingSource: audit_id in metadata
# ---------------------------------------------------------------------------

class TestAuditFindingSource:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_embedding(self):
        from app.services.lessons_learned.sources.audit_finding import AuditFindingSource

        db = AsyncMock()
        source = AuditFindingSource(db, embedding=None)
        ctx = LessonsLearnedContext(
            doc_type="fmea", doc_id=uuid.uuid4(), query_text="test",
            fmea_type="PFMEA", severity=None,
            product_line_code="DC-DC-100", user_product_lines=["DC-DC-100"],
        )
        result = await source.retrieve(ctx)
        assert result == []


# ---------------------------------------------------------------------------
# LessonsCAPASource: embedding protocol
# ---------------------------------------------------------------------------

class TestLessonsCAPASource:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_embedding(self):
        from app.services.lessons_learned.sources.historical_capa import LessonsCAPASource

        db = AsyncMock()
        source = LessonsCAPASource(db, embedding=None)
        ctx = LessonsLearnedContext(
            doc_type="capa", doc_id=uuid.uuid4(), query_text="test",
            fmea_type=None, severity="严重",
            product_line_code="DC-DC-100", user_product_lines=["DC-DC-100"],
        )
        result = await source.retrieve(ctx)
        assert result == []
