from dataclasses import replace
from types import MappingProxyType

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec


CAPA_CAPABILITIES = MappingProxyType({
    spec.id: spec for spec in (
        CapabilitySpec(
            "capa.d4.summary.masked.v1", Module.CAPA, "context",
            PermissionLevel.VIEW, ApprovalFloor.DENY, "masked", target_required=True,
        ),
        CapabilitySpec(
            "capa.d4.candidate.propose.v1", Module.CAPA, "command",
            PermissionLevel.EDIT, ApprovalFloor.DENY, "none",
        ),
    )
})


_LOCAL_METADATA_CAPABILITIES = MappingProxyType({
    **CAPA_CAPABILITIES,
    "capa.d4.summary.masked.v1": replace(CAPA_CAPABILITIES["capa.d4.summary.masked.v1"],
        approval_floor=ApprovalFloor.DIRECT),
})


def get_capability(id: str, *, profile: str = "baseline") -> CapabilitySpec | None:
    if profile == "baseline":
        return CAPA_CAPABILITIES.get(id)
    if profile == "local_metadata_v1":
        return _LOCAL_METADATA_CAPABILITIES.get(id)
    return None
