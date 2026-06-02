import uuid
import pytest
from unittest.mock import AsyncMock

from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_types import RecommendationContext


class TestHybridRecommendationPipeline:
    @pytest.mark.asyncio
    async def test_d4_pipeline_with_mock_sources(self):
        mock_db = AsyncMock()
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
        assert isinstance(result.items, list)

    @pytest.mark.asyncio
    async def test_d5_pipeline_with_mock_sources(self):
        mock_db = AsyncMock()
        mock_llm = AsyncMock()
        mock_embedding = AsyncMock()

        pipeline = HybridRecommendationPipeline(mock_db, mock_llm, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接问题", "d4_root_cause": "参数偏移"},
            user_product_lines=["DC-DC-100"],
            stage="d5",
            linked_fmea=None,
            fmea_docs=[],
        )

        result = await pipeline.recommend(ctx)
        assert isinstance(result.items, list)
