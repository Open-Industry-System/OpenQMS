"""Blocked-path tests for HybridRecommendationPipeline.recommend."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.user import User
from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_types import RecommendationResult


@pytest.mark.asyncio
async def test_blocked_skips_audit_and_cache(monkeypatch):
    pipe = HybridRecommendationPipeline(db=MagicMock(), pc=None, embedding_provider=None)
    pipe.orchestrator = MagicMock()
    pipe.orchestrator.run = AsyncMock(
        return_value=RecommendationResult(items=[], stages=[], blocked=True)
    )
    pipe._maybe_write_llm_audit = AsyncMock()
    pipe._cache_capa_result = AsyncMock()

    u = MagicMock(spec=User)
    result = await pipe.recommend(
        MagicMock(), user=u, report_id=None, factory_id=None, tenant_schema=None
    )
    assert result.blocked is True
    pipe._maybe_write_llm_audit.assert_not_awaited()
    pipe._cache_capa_result.assert_not_awaited()
