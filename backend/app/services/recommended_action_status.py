"""Deterministic mapping of legacy RecommendedAction status to canonical 4-state."""
_LEGACY_MAP = {
    "undecided": "open",
    "planned": "in_progress",
    "done": "completed",
    "notExecuted": "not_executed",
    "closed": "completed",
}
_CANONICAL = {"open", "in_progress", "completed", "not_executed"}


def normalize_action_status(value: str | None) -> str | None:
    if not value:
        return None
    if value in _CANONICAL:
        return value
    return _LEGACY_MAP.get(value)
