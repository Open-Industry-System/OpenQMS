import asyncio
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from unittest.mock import AsyncMock

from app.services.llm_fusion_layer import LLMFusionLayer, LLMOutcome
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext
from app.services.agent import provider_adapter


def _ctx(stage="d4"):
    return RecommendationContext(
        capa_data={"d2_description": "虚焊", "d4_root_cause": "温度不足"},
        user_product_lines=None, stage=stage, fmea_docs=[], linked_fmea=None,
    )


def _cands(n=3):
    return [RecommendationCandidate(source="rule", content=f"c{i}", category=None,
            confidence=0.5, match_reason="r", metadata={}) for i in range(n)]


class _PC:
    model = "test-model"


@pytest.mark.asyncio
async def test_enrich_pc_none_no_attempt(monkeypatch):
    layer = LLMFusionLayer(pc=None)
    out = await layer.enrich(_cands(), _ctx())
    assert isinstance(out, LLMOutcome)
    assert out.attempted == 0 and out.succeeded == 0 and out.failed == 0
    assert out.candidates == _cands()


@pytest.mark.asyncio
async def test_enrich_success_counts_fusion(monkeypatch):
    async def _ok(pc, prompt, schema):
        return [{"candidate_id": 0, "match_reason": "x"},
                {"candidate_id": 1, "match_reason": "y"},
                {"candidate_id": 2, "match_reason": "z"}]
    monkeypatch.setattr(provider_adapter, "complete_json", _ok)
    layer = LLMFusionLayer(pc=_PC())
    out = await layer.enrich(_cands(3), _ctx())
    assert out.attempted >= 1 and out.failed == 0 and out.succeeded >= 1
    assert len(out.candidates) == 3  # 3 candidates, no fallback (<3 is false)


@pytest.mark.asyncio
async def test_enrich_partial_fusion_ok_fallback_fail(monkeypatch):
    # fusion returns 3 reasons (no fallback needed by count) — to exercise fallback
    # failure path, force enriched<3 by returning a non-list from fusion.
    calls = {"n": 0}
    async def _fusion_ok_fallback_boom(pc, prompt, schema):
        calls["n"] += 1
        if calls["n"] == 1:
            return "not-a-list"  # _merge_explanations returns candidates unchanged → still 3
        raise RuntimeError("fallback boom")
    monkeypatch.setattr(provider_adapter, "complete_json", _fusion_ok_fallback_boom)
    layer = LLMFusionLayer(pc=_PC())
    out = await layer.enrich(_cands(2), _ctx())  # 2 candidates → len<3 → fallback attempted
    assert out.attempted == 2
    assert out.succeeded == 1 and out.failed == 1  # fusion ok, fallback failed


class TestLLMFusionLayer:
    @pytest.mark.asyncio
    async def test_timeout_error_fallback(self, monkeypatch):
        """TimeoutError should be caught and fall back to original candidates."""
        async def _boom(pc, prompt, schema):
            raise asyncio.TimeoutError()
        monkeypatch.setattr(provider_adapter, "complete_json", _boom)

        layer = LLMFusionLayer(pc=_PC())
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "original", {})]
        result = await layer.enrich(candidates, None)
        assert len(result.candidates) == 1
        assert result.candidates[0].match_reason == "original"

    @pytest.mark.asyncio
    async def test_partial_merge_response(self, monkeypatch):
        """LLM returns reasons for only some candidates — rest keep original."""
        async def _ok(pc, prompt, schema):
            return [{"candidate_id": 0, "match_reason": "updated"}]
        monkeypatch.setattr(provider_adapter, "complete_json", _ok)

        layer = LLMFusionLayer(pc=_PC())
        candidates = [
            RecommendationCandidate("rule_engine", "A", None, 0.5, "orig A", {}),
            RecommendationCandidate("semantic_search", "B", None, 0.6, "orig B", {}),
        ]
        result = await layer.enrich(candidates, None)
        assert result.candidates[0].match_reason == "updated"
        assert result.candidates[1].match_reason == "orig B"

    @pytest.mark.asyncio
    async def test_non_list_merge_response(self, monkeypatch):
        """LLM returns dict instead of list — should fall back to originals."""
        async def _bad(pc, prompt, schema):
            return {"result": "unexpected"}
        monkeypatch.setattr(provider_adapter, "complete_json", _bad)

        layer = LLMFusionLayer(pc=_PC())
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "original", {})]
        result = await layer.enrich(candidates, None)
        assert len(result.candidates) == 1
        assert result.candidates[0].match_reason == "original"

    @pytest.mark.asyncio
    async def test_no_llm_returns_candidates_unchanged(self):
        layer = LLMFusionLayer(pc=None)
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "reason", {})]
        result = await layer.enrich(candidates, None)
        assert len(result.candidates) == 1
        assert result.candidates[0].match_reason == "reason"

    @pytest.mark.asyncio
    async def test_llm_fusion_updates_match_reason(self, monkeypatch):
        async def _ok(pc, prompt, schema):
            return [{"candidate_id": 0, "match_reason": "LLM improved reason"}]
        monkeypatch.setattr(provider_adapter, "complete_json", _ok)

        layer = LLMFusionLayer(pc=_PC())
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "original", {})]
        result = await layer.enrich(candidates, None)
        assert result.candidates[0].match_reason == "LLM improved reason"

    @pytest.mark.asyncio
    async def test_llm_failure_fallback_to_original(self, monkeypatch):
        async def _boom(pc, prompt, schema):
            raise Exception("timeout")
        monkeypatch.setattr(provider_adapter, "complete_json", _boom)

        layer = LLMFusionLayer(pc=_PC())
        candidates = [RecommendationCandidate("rule_engine", "test", None, 0.5, "original", {})]
        result = await layer.enrich(candidates, None)
        assert result.candidates[0].match_reason == "original"

    @pytest.mark.asyncio
    async def test_fallback_generation_when_no_candidates(self, monkeypatch):
        # candidates empty -> stage 1 skipped -> _generate_fallback called directly
        async def _ok(pc, prompt, schema):
            return [{"content": "generated", "confidence": 0.4, "match_reason": "LLM fallback"}]
        monkeypatch.setattr(provider_adapter, "complete_json", _ok)

        layer = LLMFusionLayer(pc=_PC())
        context = RecommendationContext(
            capa_data={"d2_description": "问题描述", "d4_root_cause": "根因"},
            user_product_lines=None,
            stage="d4",
        )
        candidates = []
        result = await layer.enrich(candidates, context)
        assert len(result.candidates) == 1
        assert result.candidates[0].content == "generated"

    @pytest.mark.asyncio
    async def test_d5_fallback_prompt_requires_category(self, monkeypatch):
        """D5 fallback prompt 必须要求输出 category 字段。"""
        captured = {}
        async def _capture(pc, prompt, schema):
            captured["prompt"] = prompt
            return [{"content": "加强监控", "confidence": 0.7, "match_reason": "test", "category": "探测措施"}]
        monkeypatch.setattr(provider_adapter, "complete_json", _capture)

        layer = LLMFusionLayer(pc=_PC(), timeout=1.0)

        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接虚焊", "d4_root_cause": "参数偏移"},
            user_product_lines=None,
            stage="d5",
        )

        candidates = await layer._generate_fallback(ctx)
        assert len(candidates) == 1
        assert candidates[0].category == "探测措施"

        prompt = captured["prompt"]
        assert "category" in prompt
        assert "预防措施" in prompt
        assert "探测措施" in prompt
        assert "纠正措施" in prompt

    @pytest.mark.asyncio
    async def test_d4_fallback_prompt_no_category(self, monkeypatch):
        """D4 fallback prompt 不应要求 category。"""
        captured = {}
        async def _capture(pc, prompt, schema):
            captured["prompt"] = prompt
            return [{"content": "检查焊接参数", "confidence": 0.7, "match_reason": "test"}]
        monkeypatch.setattr(provider_adapter, "complete_json", _capture)

        layer = LLMFusionLayer(pc=_PC(), timeout=1.0)

        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接虚焊", "d4_root_cause": "参数偏移"},
            user_product_lines=None,
            stage="d4",
        )

        candidates = await layer._generate_fallback(ctx)
        assert len(candidates) == 1
        assert candidates[0].category is None

        prompt = captured["prompt"]
        assert "category" not in prompt
