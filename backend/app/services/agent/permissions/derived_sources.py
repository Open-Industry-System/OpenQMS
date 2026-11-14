"""Leaf source identities and safe errors; not an authorization service."""
from dataclasses import dataclass
from uuid import UUID

from app.core.permissions import Module


class SourceUnavailable(PermissionError):
    def __init__(self):
        super().__init__('Source unavailable')


class SourceRevisionConflict(ValueError):
    def __init__(self):
        super().__init__('Source revision conflict')


@dataclass(frozen=True, slots=True)
class DerivedSourceScope:
    target_report_id: UUID
    derived_projection_id: str
    source_module: Module
    source_projection_id: str
    fmea_id: UUID
    cause_node_id: str


def source_intersection_covers(
    current: DerivedSourceScope | None,
    plugin_scope: DerivedSourceScope | None,
    task_scope: DerivedSourceScope | None,
) -> bool:
    """Compare exact declared identities only; None never means ALL."""
    return (current is not None and plugin_scope is not None and task_scope is not None
            and current == plugin_scope == task_scope)
