import hashlib
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_types import RecommendationResult, StageRun


@pytest.mark.asyncio
async def test_thin_shell_delegates_and_audits_structured(monkeypatch):
    pipe = HybridRecommendationPipeline(MagicMock(), MagicMock(), None)
    pipe._cache_capa_result = AsyncMock()
    stage11 = StageRun(11, "LLM", "llm", "done", llm_attempted=2, llm_succeeded=1, llm_failed=1)
    pipe.orchestrator.run = AsyncMock(return_value=RecommendationResult(items=[], stages=[stage11]))
    audit = AsyncMock()
    monkeypatch.setattr("app.services.agent.audit.write_audit_raw", audit)
    await pipe.recommend(
        MagicMock(stage="d4", capa_data={"d2_description": "x"}),
        user=MagicMock(user_id=uuid.uuid4()),
        report_id=uuid.uuid4(),
        factory_id=uuid.uuid4(),
        tenant_schema="t",
    )
    # 审计被调用，new_values 含结构化计数
    assert audit.await_args.kwargs["action"] == "llm_recommend"
    assert audit.await_args.kwargs["new_values"]["attempted"] == 2


@pytest.mark.asyncio
async def test_no_audit_when_attempted_zero(monkeypatch):
    pipe = HybridRecommendationPipeline(MagicMock(), MagicMock(), None)
    pipe._cache_capa_result = AsyncMock()
    stage11 = StageRun(11, "LLM", "llm", "error", llm_attempted=0)
    pipe.orchestrator.run = AsyncMock(return_value=RecommendationResult(items=[], stages=[stage11]))
    audit = AsyncMock()
    monkeypatch.setattr("app.services.agent.audit.write_audit_raw", audit)
    await pipe.recommend(
        MagicMock(stage="d4", capa_data={}),
        user=MagicMock(user_id=uuid.uuid4()),
        report_id=uuid.uuid4(),
        factory_id=uuid.uuid4(),
        tenant_schema="t",
    )
    audit.assert_not_called()
