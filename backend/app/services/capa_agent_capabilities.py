"""CAPA-owned Agent capability declarations, disabled until approved."""

from types import MappingProxyType

from app.core.permissions import Module, PermissionLevel
from app.services.agent.permissions.types import ApprovalFloor, CapabilitySpec
from app.services.agent.permissions.context_contracts import ContextContract


CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT = ContextContract(
    'capa.d4.root_cause_candidate.masked.v1', 'restricted',
    'fmea.failure_cause.reference.v1',
)


D4_FMEA_INPUT_CONTRACT = ContextContract(
    'capa.d4.fmea_input.masked.v1', 'restricted', 'fmea.failure_cause.reference.v1')

D5_SAVE_CAPABILITY = "capa.d5.proposal.save.v1"
D5_REPLACE_CAPABILITY = "capa.d5.proposal.replace.v1"


CAPA_CAPABILITIES = MappingProxyType({
    spec.id: spec for spec in (
        CapabilitySpec(D4_FMEA_INPUT_CONTRACT.capability_id, Module.CAPA, 'context', PermissionLevel.VIEW, ApprovalFloor.DENY, 'masked', target_required=True),
        CapabilitySpec('capa.d2.snapshot.v1', Module.CAPA, 'context', PermissionLevel.VIEW, ApprovalFloor.DENY, 'masked', target_required=True),
        CapabilitySpec('capa.d3.snapshot.v1', Module.CAPA, 'context', PermissionLevel.VIEW, ApprovalFloor.DENY, 'masked', target_required=True),
        CapabilitySpec(D5_SAVE_CAPABILITY, Module.CAPA, "command", PermissionLevel.EDIT, ApprovalFloor.DENY, "none", target_required=True),
        CapabilitySpec(D5_REPLACE_CAPABILITY, Module.CAPA, "command", PermissionLevel.EDIT, ApprovalFloor.DENY, "none", target_required=True),
        CapabilitySpec("capa.d4.summary.masked.v1", Module.CAPA, "context", PermissionLevel.VIEW, ApprovalFloor.DENY, "masked", target_required=True),
        CapabilitySpec("capa.d4.candidate.propose.v1", Module.CAPA, "command", PermissionLevel.EDIT, ApprovalFloor.DENY, "none", target_required=True),
        CapabilitySpec(CAPA_D4_ROOT_CAUSE_TEXT_CONTRACT.capability_id, Module.CAPA, "context", PermissionLevel.VIEW, ApprovalFloor.DENY, "masked", target_required=True),
    )
})
