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


def compute_ap(s: int, o: int, d: int) -> str:
    """
    Calculates Action Priority (AP) based on Severity (S), Occurrence (O), Detection (D).
    Ref: AIAG-VDA FMEA Handbook (2019) Appendix C1.5
    Returns "H" | "M" | "L" | ""
    """
    if s < 1 or s > 10 or o < 1 or o > 10 or d < 1 or d > 10:
        return ""

    # Severity 9-10
    if s >= 9:
        if o >= 4:
            return "H"
        if o in (3, 2):
            return "H" if d >= 7 else "M" if d >= 5 else "L"
        return "L"  # o == 1

    # Severity 7-8
    if s >= 7:
        if o >= 8:
            return "H"
        if o in (6, 7):
            return "H" if d >= 2 else "M"
        if o in (4, 5):
            return "H" if d >= 7 else "M"
        if o in (2, 3):
            return "M" if d >= 5 else "L"
        return "L"  # o == 1

    # Severity 4-6
    if s >= 4:
        if o >= 8:
            return "H" if d >= 5 else "M"
        if o in (6, 7):
            return "M" if d >= 2 else "L"
        if o in (4, 5):
            return "M" if d >= 7 else "L"
        return "L"  # o <= 3

    # Severity 1-3
    if o >= 8:
        return "M" if d >= 5 else "L"
    return "L"
