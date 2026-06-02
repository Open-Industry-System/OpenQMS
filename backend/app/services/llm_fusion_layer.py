import asyncio
import dataclasses
import json
import logging
from typing import Any

from app.services.recommendation_types import RecommendationCandidate, RecommendationContext

logger = logging.getLogger(__name__)


class LLMFusionLayer:
    """LLM 融合层：为候选生成推荐理由 + 候选不足时回退生成。"""

    def __init__(self, llm_provider, timeout: float = 2.0):
        self.llm = llm_provider
        self.timeout = timeout

    async def enrich(
        self,
        candidates: list[RecommendationCandidate],
        context: RecommendationContext | None,
    ) -> list[RecommendationCandidate]:
        if not self.llm:
            return candidates

        # 阶段 1：为候选生成推荐理由
        enriched: list[RecommendationCandidate] = []
        if candidates:
            try:
                prompt = self._build_fusion_prompt(candidates, context)
                result = await asyncio.wait_for(
                    self.llm.complete(prompt, {}),
                    timeout=self.timeout,
                )
                enriched = self._merge_explanations(candidates, result)
            except Exception as e:
                logger.warning(f"LLM fusion failed: {e}")
                enriched = candidates
        else:
            enriched = []

        # 阶段 2：候选不足时独立生成
        if len(enriched) < 3:
            try:
                generated = await self._generate_fallback(context)
                enriched.extend(generated)
            except Exception as e:
                logger.warning(f"LLM fallback generation failed: {e}")

        return enriched

    def _build_fusion_prompt(
        self,
        candidates: list[RecommendationCandidate],
        context: RecommendationContext | None,
    ) -> str:
        d2 = context.capa_data.get("d2_description", "") if context else ""
        d4 = context.capa_data.get("d4_root_cause", "") if context else ""
        stage = context.stage if context else "d4"

        items = []
        for i, c in enumerate(candidates):
            items.append({
                "candidate_id": i,
                "source": c.source,
                "content": c.content,
                "confidence": c.confidence,
                "match_reason": c.match_reason,
            })

        system = (
            "你是一名资深质量工程师，擅长 AIAG-VDA 8D 问题解决方法。"
            "请根据提供的候选列表，为每条推荐写一句中文推荐理由。\n\n"
            "规则：\n"
            "1. 你只能改写 match_reason 字段，不允许生成新的 content、node_id 等主键字段\n"
            "2. 输出必须保留每条候选的 candidate_id\n"
            "3. 不增减候选数量，只优化理由\n"
            "4. 输出 JSON 数组"
        )

        user = f"""
当前 8D 阶段: {stage}
D2 问题描述: {d2}
D4 根因: {d4}

候选列表:
{json.dumps(items, ensure_ascii=False)}

请输出 JSON 数组: [{{"candidate_id": 0, "match_reason": "..."}}, ...]
"""
        return f"{system}\n\n{user}"

    def _merge_explanations(
        self,
        candidates: list[RecommendationCandidate],
        result: Any,
    ) -> list[RecommendationCandidate]:
        if not isinstance(result, list):
            logger.warning(f"LLM fusion returned non-list result: {type(result)}")
            return list(candidates)

        reason_map = {}
        for item in result:
            if isinstance(item, dict) and "candidate_id" in item:
                reason_map[item["candidate_id"]] = item.get("match_reason", "")

        merged = []
        for i, c in enumerate(candidates):
            if i in reason_map and reason_map[i]:
                merged.append(dataclasses.replace(c, match_reason=reason_map[i]))
            else:
                merged.append(c)
        return merged

    async def _generate_fallback(
        self,
        context: RecommendationContext | None,
    ) -> list[RecommendationCandidate]:
        if not context:
            return []
        d2 = context.capa_data.get("d2_description", "")
        d4 = context.capa_data.get("d4_root_cause", "")
        stage = context.stage

        prompt = f"""
你是一名质量工程师。请基于以下信息生成 8D {stage.upper()} 阶段的建议：

D2 问题描述: {d2}
D4 根因: {d4}

请输出 JSON 数组，每条包含 content、confidence(0.0-1.0)、match_reason：
[{{"content": "...", "confidence": 0.5, "match_reason": "..."}}]
"""

        result = await asyncio.wait_for(
            self.llm.complete(prompt, {}),
            timeout=self.timeout,
        )

        candidates: list[RecommendationCandidate] = []
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and item.get("content"):
                    candidates.append(RecommendationCandidate(
                        source="llm",
                        content=item["content"],
                        category=item.get("category") if stage == "d5" else None,
                        confidence=float(item.get("confidence", 0.5)),
                        match_reason=item.get("match_reason", "LLM 生成建议"),
                        metadata={},
                    ))
                else:
                    logger.warning(f"LLM fallback returned invalid item: {item}")
        return candidates
