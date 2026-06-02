import dataclasses

from app.services.recommendation_types import RecommendationCandidate, RecommendationContext


class FusionEngine:
    """Merge candidates from multiple sources, deduplicate and rank."""

    SOURCE_PRIORITY = {
        "fmea_graph": 1.0,
        "historical_capa": 0.9,
        "semantic_search": 0.7,
        "llm": 0.6,
        "rule_engine": 0.5,
    }

    def merge(
        self,
        candidates: list[RecommendationCandidate],
        context: RecommendationContext,
    ) -> list[RecommendationCandidate]:
        """Score, deduplicate and rank recommendation candidates.

        Each candidate is re-scored by source priority and metadata bonuses
        (product line match +0.05, severity match +0.03), capped at 0.95.
        The original candidate objects are not mutated.
        """
        # 1. 来源优先级归一化 + 元数据 bonus
        scored: list[RecommendationCandidate] = []
        for c in candidates:
            priority = self.SOURCE_PRIORITY.get(c.source, 0.5)
            product_bonus = (
                0.05
                if c.metadata.get("product_line_code")
                == context.capa_data.get("product_line_code")
                else 0.0
            )
            severity_bonus = (
                0.03
                if c.metadata.get("severity")
                == context.capa_data.get("severity")
                else 0.0
            )
            new_confidence = min(
                c.confidence * priority + product_bonus + severity_bonus,
                0.95,
            )
            scored.append(dataclasses.replace(c, confidence=new_confidence))

        # 2. 去重（归一化文本匹配）
        seen: set[str] = set()
        deduped: list[RecommendationCandidate] = []
        for c in sorted(scored, key=lambda x: x.confidence, reverse=True):
            normalized = "".join(c.content.lower().split())
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(c)

        # 3. 截断 Top 10
        return deduped[:10]
