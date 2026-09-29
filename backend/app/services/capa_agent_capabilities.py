"""CAPA-owned Agent capability declarations, disabled until approved."""

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec


CAPA_CAPABILITIES = {
    spec.id: spec for spec in (
        CapabilitySpec("capa.d4.summary.masked.v1", Module.CAPA, "context", PermissionLevel.VIEW, ApprovalFloor.DENY, "masked"),
        CapabilitySpec("capa.d4.candidate.propose.v1", Module.CAPA, "command", PermissionLevel.EDIT, ApprovalFloor.DENY, "none"),
    )
}
