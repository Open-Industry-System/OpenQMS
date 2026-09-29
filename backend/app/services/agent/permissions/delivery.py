"""Conservative lineage and explicit target-delivery guards."""

from dataclasses import dataclass
from uuid import UUID

from app.core.permissions import Module


@dataclass(frozen=True)
class SourceLabel:
    owner: Module
    object_id: UUID
    sensitivity: str
    capability_id: str
    projection: str


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
    if any(source.sensitivity not in {"internal", "restricted"}
           or source.projection not in {"masked", "raw"}
           or not source.capability_id for source in sources):
        raise ValueError("unknown source authorization")
    level = "restricted" if any(source.sensitivity == "restricted" for source in sources) else "internal"
    return DerivedLabel(sources, level)


def can_view_derived(label: DerivedLabel, target_authorized: bool,
                     authorized_sources: frozenset[tuple[Module, UUID, str, str]]) -> bool:
    try:
        valid_label = derive_label(label.sources)
    except ValueError:
        return False
    return (target_authorized and label.sensitivity == valid_label.sensitivity
            and all((source.owner, source.object_id, source.capability_id, source.projection)
                    in authorized_sources for source in label.sources))


def can_deliver(attempt: DeliveryAttempt) -> bool:
    explicit = (attempt.sensitivity, attempt.projection, attempt.target_kind, attempt.target_id)
    return (attempt.sensitivity in {"internal", "restricted"}
            and attempt.projection in {"masked", "raw"}
            and attempt.target_kind in {"plugin", "model"}
            and explicit in attempt.allowed
            and (attempt.sensitivity != "restricted" or attempt.controlled_egress))
