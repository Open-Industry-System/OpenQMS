import os
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from unittest.mock import AsyncMock

from app.services.llm_fusion_layer import LLMFusionLayer
from app.services.recommendation_types import RecommendationContext


@pytest.mark.asyncio
async def test_d5_fallback_prompt_requires_category():
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
async def test_d4_fallback_prompt_no_category():
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
