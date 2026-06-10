from abc import ABC, abstractmethod

from app.services.lessons_learned.context import LessonsLearnedContext
from app.services.recommendation_types import RecommendationCandidate


class LessonsSource(ABC):
    """经验教训召回源基类。"""

    name: str

    @abstractmethod
    async def retrieve(self, context: LessonsLearnedContext) -> list[RecommendationCandidate]:
        """Retrieve lesson candidates for the given context."""
        ...
