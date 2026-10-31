from dataclasses import dataclass
from uuid import UUID

from app.core.permissions import Module


@dataclass(frozen=True)
class SourceLabel:
    owner: Module
    object_id: UUID
    source_version: str
    sensitivity: str


@dataclass(frozen=True)
class DerivedLabel:
    sources: tuple[SourceLabel, ...]
    sensitivity: str


@dataclass(frozen=True)
class DeliveryAttempt:
    sensitivity: str
    projection: str
    target_id: str
    target_kind: str
    allowed: frozenset[tuple[str, str, str, str]]
    controlled_egress: bool


def derive_label(sources: tuple[SourceLabel, ...]) -> DerivedLabel:
    if not sources:
        raise ValueError("derived content requires server-attached sources")
    if any(not source.source_version.strip() for source in sources):
        raise ValueError("source version required")
    if any(source.sensitivity not in {"internal", "restricted"} for source in sources):
        raise ValueError("unknown sensitivity")
    level = "restricted" if any(source.sensitivity == "restricted" for source in sources) else "internal"
    return DerivedLabel(sources, level)


def _valid_label(label: DerivedLabel) -> bool:
    try:
        return derive_label(label.sources) == label
    except ValueError:
        return False


def can_view_derived(
    label: DerivedLabel,
    target_authorized: bool,
    authorized_sources: frozenset[tuple[Module, UUID, str]],
) -> bool:
    return _valid_label(label) and target_authorized and all(
        (source.owner, source.object_id, source.sensitivity) in authorized_sources
        for source in label.sources
    )


def can_deliver(attempt: DeliveryAttempt) -> bool:
    explicit = (attempt.sensitivity, attempt.projection, attempt.target_kind, attempt.target_id)
    return (
        attempt.sensitivity in {"internal", "restricted"}
        and attempt.projection in {"masked", "raw"}
        and attempt.target_kind in {"plugin", "model"}
        and bool(attempt.target_id.strip())
        and explicit in attempt.allowed
        and (attempt.sensitivity != "restricted" or attempt.controlled_egress)
    )


def can_deliver_derived(label: DerivedLabel, attempt: DeliveryAttempt) -> bool:
    return _valid_label(label) and label.sensitivity == attempt.sensitivity and can_deliver(attempt)
