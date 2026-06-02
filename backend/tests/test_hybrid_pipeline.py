import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_types import RecommendationContext, RecommendationCandidate


class TestHybridRecommendationPipeline:
    @pytest.mark.asyncio
    async def test_d4_pipeline_runs_all_sources(self):
        mock_db = MagicMock()
        mock_llm = AsyncMock()
        mock_embedding = AsyncMock()

        pipeline = HybridRecommendationPipeline(mock_db, mock_llm, mock_embedding)

        # Verify D4 sources are configured
        assert len(pipeline.d4_sources) == 4
        source_names = [s.name for s in pipeline.d4_sources]
        assert "fmea_graph" in source_names
        assert "semantic_search" in source_names
        assert "historical_capa" in source_names
        assert "rule_engine" in source_names

    @pytest.mark.asyncio
    async def test_d5_pipeline_runs_all_sources(self):
        mock_db = MagicMock()
        mock_llm = AsyncMock()
        mock_embedding = AsyncMock()

        pipeline = HybridRecommendationPipeline(mock_db, mock_llm, mock_embedding)

        # Verify D5 sources are configured
        assert len(pipeline.d5_sources) == 3
        source_names = [s.name for s in pipeline.d5_sources]
        assert "semantic_search" in source_names
        assert "historical_capa_measure" in source_names
        assert "rule_engine_measure" in source_names

        # Verify D5 Stage 2 expander exists
        assert pipeline.d5_control_expander is not None

    @pytest.mark.asyncio
    async def test_recommend_returns_recommendation_result(self):
        mock_db = MagicMock()
        mock_llm = AsyncMock()
        mock_embedding = AsyncMock()

        pipeline = HybridRecommendationPipeline(mock_db, mock_llm, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接问题", "d4_root_cause": ""},
            user_product_lines=["DC-DC-100"],
            stage="d4",
            linked_fmea=None,
            fmea_docs=[],
        )

        result = await pipeline.recommend(ctx)
        assert hasattr(result, "items")
        assert isinstance(result.items, list)

    @pytest.mark.asyncio
    async def test_d5_with_cause_candidates_triggers_expansion(self):
        """D5 pipeline with FailureCause candidates should trigger FMEAControlExpander."""
        mock_db = MagicMock()
        mock_llm = AsyncMock()
        mock_embedding = AsyncMock()

        pipeline = HybridRecommendationPipeline(mock_db, mock_llm, mock_embedding)

        # Create a candidate with failure_cause_node_id
        cause_candidate = RecommendationCandidate(
            source="semantic_search",
            content="焊接参数偏移",
            category=None,
            confidence=0.7,
            match_reason="语义匹配",
            metadata={
                "failure_cause_node_id": "cause-123",
                "failure_mode_node_id": "fm-123",
                "fmea_id": "fmea-123",
            },
        )

        # Mock Stage 1 to return our cause candidate
        with patch.object(pipeline.d5_sources[0], 'retrieve', return_value=[cause_candidate]):
            with patch.object(pipeline.d5_control_expander, 'expand', return_value=[]) as mock_expand:
                ctx = RecommendationContext(
                    capa_data={"d2_description": "焊接问题", "d4_root_cause": "参数偏移"},
                    user_product_lines=["DC-DC-100"],
                    stage="d5",
                    linked_fmea=None,
                    fmea_docs=[{"fmea_id": "fmea-123", "graph_data": {"nodes": [], "edges": []}}],
                )

                result = await pipeline.recommend(ctx)
                # Expander should have been called because we have cause candidates
                mock_expand.assert_called_once()
