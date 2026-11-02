from dataclasses import replace
from types import MappingProxyType

from app.services.capa_agent_capabilities import CAPA_CAPABILITIES
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec


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
