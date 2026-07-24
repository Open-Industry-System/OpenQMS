import asyncio
import dataclasses
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.services.agent import provider_adapter
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext

logger = logging.getLogger(__name__)


@dataclass
class LLMOutcome:
    """Result of an enrich() call: fused candidates + per-stage LLM counts."""
    candidates: list[RecommendationCandidate]
    attempted: int = 0   # stage-1 fusion + stage-2 fallback (max 2)
    succeeded: int = 0
    failed: int = 0


class LLMFusionLayer:
    """LLM 融合层：为候选生成推荐理由 + 候选不足时回退生成。"""

    def __init__(self, pc, timeout: float | None = None):
        # Default to configured LLM_TIMEOUT (not a hardcoded 2s). Stage-11 fusion
        # with local models routinely exceeds 2s; US-E2E-01.2 saw attempted=2/failed=2.
        from app.config import settings

        self.pc = pc
        self.timeout = float(timeout if timeout is not None else settings.LLM_TIMEOUT)

    async def enrich(
        self,
        candidates: list[RecommendationCandidate],
        context: RecommendationContext | None,
    ) -> LLMOutcome:
        if self.pc is None:
            return LLMOutcome(candidates=list(candidates) if candidates else [], attempted=0)

        attempted = 0
        succeeded = 0
        failed = 0
        enriched: list[RecommendationCandidate] = []

        try:
            # 阶段 1：为候选生成推荐理由（一次批量 fusion 调用）
            if candidates:
                attempted += 1
                try:
                    prompt = self._build_fusion_prompt(candidates, context)
                    result = await asyncio.wait_for(
                        provider_adapter.complete_json(self.pc, prompt, {}),
                        timeout=self.timeout,
                    )
                    enriched = self._merge_explanations(candidates, result)
                    succeeded += 1
                except Exception as e:
                    logger.warning(f"LLM fusion failed: {e}")
                    enriched = list(candidates)
                    failed += 1
            else:
                enriched = []

            # 阶段 2：候选不足时独立生成（一次 fallback 调用）
            if len(enriched) < 3 and context is not None:
                attempted += 1
                try:
                    generated = await self._generate_fallback(context)
                    enriched.extend(generated)
                    succeeded += 1
                except Exception as e:
                    logger.warning(f"LLM fallback generation failed: {e}")
                    failed += 1
        except Exception as e:
            # R4-修复：enrich 硬化为 catch-all，任何未预期异常都不抛，返回带计数的 LLMOutcome
            logger.warning(f"LLM enrich unexpected error (catch-all): {e}")
            return LLMOutcome(
                candidates=list(candidates),
                attempted=attempted,
                succeeded=succeeded,
                failed=attempted - succeeded,
            )

        return LLMOutcome(candidates=enriched, attempted=attempted,
                          succeeded=succeeded, failed=failed)

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

请输出 JSON 数组，每条包含 content、confidence(0.0-1.0)、match_reason{"、category（仅 D5 阶段必填，值为：预防措施 / 探测措施 / 纠正措施）" if stage == "d5" else ""}：
[{{"content": "...", "confidence": 0.5, "match_reason": "..."{', "category": "预防措施"' if stage == "d5" else ""}}}]
"""

        result = await asyncio.wait_for(
            provider_adapter.complete_json(self.pc, prompt, {}),
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
