"""CAPA-owned Agent capability declarations, disabled until approved."""

from types import MappingProxyType

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec
from app.services.agent.permissions.context_contracts import ContextContract


CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT = ContextContract(
    'capa.d4.root_cause_candidate.masked.v1', 'restricted',
    'fmea.failure_cause.reference.v1',
)


CAPA_CAPABILITIES = MappingProxyType({
    spec.id: spec for spec in (
        CapabilitySpec("capa.d4.summary.masked.v1", Module.CAPA, "context", PermissionLevel.VIEW, ApprovalFloor.DENY, "masked", target_required=True),
        CapabilitySpec("capa.d4.candidate.propose.v1", Module.CAPA, "command", PermissionLevel.EDIT, ApprovalFloor.DENY, "none"),
        CapabilitySpec(CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT.capability_id, Module.CAPA, "context", PermissionLevel.VIEW, ApprovalFloor.DENY, "masked", target_required=True),
    )
})
