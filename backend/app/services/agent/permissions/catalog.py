from types import MappingProxyType

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec


CAPA_CAPABILITIES = MappingProxyType({
    spec.id: spec for spec in (
        CapabilitySpec(
            "capa.d4.summary.masked.v1", Module.CAPA, "context",
            PermissionLevel.VIEW, ApprovalFloor.DENY, "masked",
        ),
        CapabilitySpec(
            "capa.d4.candidate.propose.v1", Module.CAPA, "command",
            PermissionLevel.EDIT, ApprovalFloor.DENY, "none",
        ),
    )
})


def get_capability(id: str) -> CapabilitySpec | None:
    return CAPA_CAPABILITIES.get(id)
