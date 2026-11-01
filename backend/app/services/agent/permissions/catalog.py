"""Lookup for module-owned Agent capability declarations."""

from app.services.capa_agent_capabilities import CAPA_CAPABILITIES

from .types import CapabilitySpec


def get_capability(id: str) -> CapabilitySpec | None:
    return CAPA_CAPABILITIES.get(id)
