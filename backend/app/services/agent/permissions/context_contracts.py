"""Internal read-only declarations, separate from public capability manifests."""
from dataclasses import dataclass

from app.core.permissions import Module, PermissionLevel


@dataclass(frozen=True, slots=True)
class ContextContract:
    capability_id: str
    data_class: str
    source_projection_id: str


@dataclass(frozen=True, slots=True)
class SourceProjectionContract:
    source_projection_id: str
    owner: Module
    minimum_level: PermissionLevel
    coords: tuple[str, ...]
    version_method: str
