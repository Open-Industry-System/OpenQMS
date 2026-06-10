import uuid
from dataclasses import dataclass
from typing import Literal


@dataclass
class LessonsLearnedContext:
    """Context for lessons learned recommendation — independent from RecommendationContext."""

    doc_type: Literal["fmea", "capa"]
    doc_id: uuid.UUID
    query_text: str  # problem_description or title fallback
    fmea_type: str | None  # only for FMEA
    severity: str | None  # only for CAPA
    product_line_code: str
    user_product_lines: list[str] | None  # None = admin (all PLs)
    fmea_ref_id: uuid.UUID | None = None

    def pl_hash_for_cache(self) -> str:
        """Return a stable string for cache key hashing.
        Admin (None) uses sentinel '__ALL_PRODUCT_LINES__'."""
        if self.user_product_lines is None:
            return "__ALL_PRODUCT_LINES__"
        return ",".join(sorted(self.user_product_lines))
