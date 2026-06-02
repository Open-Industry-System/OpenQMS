import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_sources import SemanticSearchSource, HistoricalCAPAMeasureSource
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


class TestHybridPipelineEndToEnd:
    @pytest.mark.asyncio
    async def test_d4_historical_capa_schema_mapping(self):
        mock_db = MagicMock()
        mock_row = {
            "entity_id": uuid.uuid4(),
            "chunk_text": "温度不稳定",
            "similarity": 0.75,
            "document_no": "8D-2026-001",
            "severity": "严重",
            "source_updated_at": "2026-05-01",
            "d4_root_cause": "温度不稳定",
            "d5_correction": "增加温控",
            "product_line_code": "DC-DC-100",
        }
        mock_mappings = MagicMock()
        mock_mappings.__iter__.return_value = iter([mock_row])
        mock_execute_result = MagicMock()
        mock_execute_result.mappings.return_value = mock_mappings
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        pipeline = HybridRecommendationPipeline(mock_db, None, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接温度问题", "product_line_code": "DC-DC-100"},
            user_product_lines=["DC-DC-100"],
            stage="d4",
        )

        result = await pipeline.recommend(ctx)
        historical = [c for c in result.items if c.source == "historical_capa"]
        assert len(historical) >= 1
        schema = historical[0].to_d4_schema()
        assert schema["source_capa_document_no"] == "8D-2026-001"
        assert schema["match_source"] == "historical_capa"

    @pytest.mark.asyncio
    async def test_d5_category_纠正措施(self):
        candidate = RecommendationCandidate(
            source="historical_capa",
            content="增加温控闭环",
            category="纠正措施",
            confidence=0.8,
            match_reason="历史 CAPA 相似根因",
            metadata={"historical_capa_id": "abc", "document_no": "8D-001"},
        )
        schema = candidate.to_d5_suggestion_schema()
        assert schema["category"] == "纠正措施"
        assert schema["match_source"] == "historical_capa"
        assert schema["source_capa_document_no"] == "8D-001"

    @pytest.mark.asyncio
    async def test_match_source_rule_backward_compat(self):
        candidate = RecommendationCandidate(
            source="rule_engine",
            content="规则建议",
            category=None,
            confidence=0.5,
            match_reason="规则",
            metadata={},
        )
        schema = candidate.to_d4_schema()
        assert schema["match_source"] == "rule"

    @pytest.mark.asyncio
    async def test_cross_product_line_semantic_search_resolved_by_doc_map(self):
        """SemanticSearchSource returns an FMEA node from a non-current but allowed product line;
        doc_map must resolve it because API preloads all allowed PLs."""
        from unittest.mock import MagicMock, AsyncMock, call
        import uuid

        # Mock DB returning a cross-PL FMEA node match
        mock_db = MagicMock()
        fmea_id = uuid.uuid4()
        node_id = str(uuid.uuid4())
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(fmea_id=fmea_id, node_id=node_id, similarity=0.8, product_line_code="OTHER-PL")
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        # Preload FMEA docs from OTHER-PL (simulating API preloading all allowed PLs)
        other_pl_doc = {
            "fmea_id": fmea_id,
            "document_no": "PFMEA-OTHER-001",
            "product_line_code": "OTHER-PL",
            "graph_data": {
                "nodes": [
                    {"id": node_id, "type": "FailureCause", "name": "跨线原因"},
                    {"id": "fm1", "type": "FailureMode", "name": "跨线失效"},
                ],
                "edges": [
                    {"source": node_id, "target": "fm1", "type": "CAUSE_OF"},
                ],
            },
        }

        source = SemanticSearchSource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接问题", "product_line_code": "DC-DC-100"},
            user_product_lines=["DC-DC-100", "OTHER-PL"],  # allowed PLs include OTHER-PL
            stage="d4",
            fmea_docs=[other_pl_doc],
        )

        results = await source.retrieve(ctx)
        assert len(results) == 1
        assert results[0].content == "跨线原因"
        assert results[0].metadata["fmea_document_no"] == "PFMEA-OTHER-001"

    @pytest.mark.asyncio
    async def test_historical_capa_measure_sql_uses_vector_cast(self):
        """HistoricalCAPAMeasureSource._search SQL must contain CAST(:query_vector AS vector)."""
        from unittest.mock import MagicMock, AsyncMock
        import uuid

        mock_db = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.__iter__.return_value = iter([])
        mock_execute_result = MagicMock()
        mock_execute_result.mappings.return_value = mock_mappings
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        source = HistoricalCAPAMeasureSource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d4_root_cause": "参数偏移", "product_line_code": "DC-DC-100"},
            user_product_lines=["DC-DC-100"],
            stage="d5",
        )

        await source.retrieve(ctx)

        # Check the SQL passed to db.execute contains CAST
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "CAST(:query_vector AS vector)" in sql_text
