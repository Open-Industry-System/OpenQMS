from app.services.lessons_learned.context import LessonsLearnedContext
from app.services.lessons_learned.sources.base import LessonsSource
from app.services.recommendation_types import RecommendationCandidate
from app.services.recommendation_service import RuleEngine


class LessonsRuleSource(LessonsSource):
    """Lessons 专用规则引擎 fallback — 复用 RuleEngine，适配 LessonsLearnedContext。"""

    name = "rule_engine"

    def __init__(self):
        self.engine = RuleEngine()

    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        result = self.engine.evaluate("failure_mode", {"input_text": context.query_text})
        candidates: list[RecommendationCandidate] = []
        for s in result.suggestions:
            candidates.append(
                RecommendationCandidate(
                    source=self.name,
                    content=s.name,
                    category=None,
                    confidence=s.confidence,
                    match_reason=s.explanation or "规则引擎匹配",
                    metadata={
                        "source_type": "fmea",
                    },
                )
            )
        return candidates
