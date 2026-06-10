import re

from app.services.recommendation_types import RecommendationCandidate


class LessonsFusionEngine:
    """Lessons 专用去重排序引擎。"""

    SOURCE_PRIORITY = {
        "historical_fmea": 1.0,
        "historical_capa": 0.9,
        "semantic_search": 0.7,
        "audit_finding": 0.6,
        "rule_engine": 0.5,
    }

    PL_BOOST = 0.10  # 同产品线加成（lessons 专用）

    def merge(
        self,
        candidates: list[RecommendationCandidate],
        product_line_code: str,
    ) -> list[RecommendationCandidate]:
        # 1. Score normalization + source priority + PL boost
        scored: list[tuple[float, RecommendationCandidate]] = []
        for c in candidates:
            base = c.confidence
            priority = self.SOURCE_PRIORITY.get(c.source, 0.5)
            same_pl = c.metadata.get("product_line_code") == product_line_code
            pl_bonus = self.PL_BOOST if same_pl else 0.0
            final_score = min(base * priority + pl_bonus, 1.0)
            scored.append((final_score, c))

        # 2. Deduplicate by normalized content
        seen: set[str] = set()
        unique: list[tuple[float, RecommendationCandidate]] = []
        for score, c in sorted(scored, key=lambda x: x[0], reverse=True):
            key = self._normalize(c.content)
            if key not in seen:
                seen.add(key)
                # Update confidence to fused score
                c.confidence = round(score, 2)
                unique.append((score, c))

        # 3. Truncate top 10
        return [c for _, c in unique[:10]]

    def _normalize(self, text: str) -> str:
        """Normalize text for deduplication."""
        text = text.lower().strip()
        text = re.sub(r"[\s,，;；]+", "", text)
        return text[:50]
