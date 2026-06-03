import asyncio
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from unittest.mock import AsyncMock

from app.services.llm_fusion_layer import LLMFusionLayer
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext


class TestLLMFusionLayer:
    @pytest.mark.asyncio
    async def test_timeout_error_fallback(self):
        """TimeoutError should be caught and fall back to original candidates."""
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=asyncio.TimeoutError())

        layer = LLMFusionLayer(mock_llm)
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "original", {})]
        result = await layer.enrich(candidates, None)
        assert len(result) == 1
        assert result[0].match_reason == "original"

    @pytest.mark.asyncio
    async def test_partial_merge_response(self):
        """LLM returns reasons for only some candidates — rest keep original."""
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=[
            {"candidate_id": 0, "match_reason": "updated"}
            # candidate 1 missing
        ])

        layer = LLMFusionLayer(mock_llm)
        candidates = [
            RecommendationCandidate("rule_engine", "A", None, 0.5, "orig A", {}),
            RecommendationCandidate("semantic_search", "B", None, 0.6, "orig B", {}),
        ]
        result = await layer.enrich(candidates, None)
        assert result[0].match_reason == "updated"
        assert result[1].match_reason == "orig B"

    @pytest.mark.asyncio
    async def test_non_list_merge_response(self):
        """LLM returns dict instead of list — should fall back to originals."""
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value={"result": "unexpected"})

        layer = LLMFusionLayer(mock_llm)
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "original", {})]
        result = await layer.enrich(candidates, None)
        assert len(result) == 1
        assert result[0].match_reason == "original"

    @pytest.mark.asyncio
    async def test_no_llm_returns_candidates_unchanged(self):
        layer = LLMFusionLayer(None)
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "reason", {})]
        result = await layer.enrich(candidates, None)
        assert len(result) == 1
        assert result[0].match_reason == "reason"

    @pytest.mark.asyncio
    async def test_llm_fusion_updates_match_reason(self):
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=[
            {"candidate_id": 0, "match_reason": "LLM improved reason"}
        ])

        layer = LLMFusionLayer(mock_llm)
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "original", {})]
        result = await layer.enrich(candidates, None)
        assert result[0].match_reason == "LLM improved reason"

    @pytest.mark.asyncio
    async def test_llm_failure_fallback_to_original(self):
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=Exception("timeout"))

        layer = LLMFusionLayer(mock_llm)
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "original", {})]
        result = await layer.enrich(candidates, None)
        assert result[0].match_reason == "original"

    @pytest.mark.asyncio
    async def test_fallback_generation_when_no_candidates(self):
        mock_llm = AsyncMock()
        # candidates empty -> stage 1 skipped -> _generate_fallback called directly
        mock_llm.complete = AsyncMock(return_value=[
            {"content": "generated", "confidence": 0.4, "match_reason": "LLM fallback"}
        ])

        layer = LLMFusionLayer(mock_llm)
        context = RecommendationContext(
            capa_data={"d2_description": "问题描述", "d4_root_cause": "根因"},
            user_product_lines=None,
            stage="d4",
        )
        candidates = []
        result = await layer.enrich(candidates, context)
        assert len(result) == 1
        assert result[0].content == "generated"

    @pytest.mark.asyncio
    async def test_d5_fallback_prompt_requires_category(self):
        """D5 fallback prompt 必须要求输出 category 字段。"""
        llm = AsyncMock()
        layer = LLMFusionLayer(llm_provider=llm, timeout=1.0)

        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接虚焊", "d4_root_cause": "参数偏移"},
            user_product_lines=None,
            stage="d5",
        )

        # 验证 prompt 包含 category 要求
        llm.complete.return_value = [
            {"content": "加强监控", "confidence": 0.7, "match_reason": "test", "category": "探测措施"}
        ]
        candidates = await layer._generate_fallback(ctx)
        assert len(candidates) == 1
        assert candidates[0].category == "探测措施"

        # 验证 LLM 被传入的 prompt 包含 category 关键字
        prompt = llm.complete.call_args[0][0]
        assert "category" in prompt
        assert "预防措施" in prompt
        assert "探测措施" in prompt
        assert "纠正措施" in prompt

    @pytest.mark.asyncio
    async def test_d4_fallback_prompt_no_category(self):
        """D4 fallback prompt 不应要求 category。"""
        llm = AsyncMock()
        layer = LLMFusionLayer(llm_provider=llm, timeout=1.0)

        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接虚焊", "d4_root_cause": "参数偏移"},
            user_product_lines=None,
            stage="d4",
        )

        llm.complete.return_value = [
            {"content": "检查焊接参数", "confidence": 0.7, "match_reason": "test"}
        ]
        candidates = await layer._generate_fallback(ctx)
        assert len(candidates) == 1
        assert candidates[0].category is None

        prompt = llm.complete.call_args[0][0]
        assert "category" not in prompt
