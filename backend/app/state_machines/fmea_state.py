from enum import Enum


class FMEAState(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REWORK = "rework"
    ARCHIVED = "archived"


class FMEAType(str, Enum):
    DFMEA = "DFMEA"
    PFMEA = "PFMEA"


FMEA_TRANSITIONS: dict[FMEAState, list[FMEAState]] = {
    FMEAState.DRAFT: [FMEAState.IN_REVIEW, FMEAState.ARCHIVED],
    FMEAState.IN_REVIEW: [FMEAState.APPROVED, FMEAState.REWORK],
    FMEAState.APPROVED: [FMEAState.REWORK, FMEAState.ARCHIVED],
    FMEAState.REWORK: [FMEAState.IN_REVIEW],
    FMEAState.ARCHIVED: [],
}


def can_transition(current: FMEAState, target: FMEAState) -> bool:
    return target in FMEA_TRANSITIONS.get(current, [])


def compute_rpn(severity: int, occurrence: int, detection: int) -> int:
    return severity * occurrence * detection


def compute_ap(rpn: int) -> str:
    if rpn >= 100:
        return "HIGH"
    elif rpn >= 50:
        return "MEDIUM"
    return "LOW"
