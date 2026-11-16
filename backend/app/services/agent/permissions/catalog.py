"""Lookup for module-owned Agent capabilities and controlled read profiles."""
from dataclasses import replace
from types import MappingProxyType

from app.services.capa_agent_capabilities import CAPA_CAPABILITIES
from .types import ApprovalFloor, CapabilitySpec
from app.services.agent_runtime.message_delivery_policy import TEXT_PROFILE


_LOCAL_METADATA_CAPABILITIES = MappingProxyType({
    "capa.d4.candidate.propose.v1": CAPA_CAPABILITIES["capa.d4.candidate.propose.v1"],
    "capa.d4.summary.masked.v1": replace(CAPA_CAPABILITIES["capa.d4.summary.masked.v1"],
        approval_floor=ApprovalFloor.DIRECT),
})


_LOCAL_TEXT_CAPABILITIES = MappingProxyType({
    "capa.d4.root_cause_candidate.masked.v1": replace(
        CAPA_CAPABILITIES["capa.d4.root_cause_candidate.masked.v1"], approval_floor=ApprovalFloor.DIRECT),
})


def get_capability(id: str, *, profile: str = "baseline") -> CapabilitySpec | None:
    if profile == "baseline":
        return CAPA_CAPABILITIES.get(id)
    if profile == "local_metadata_v1":
        return _LOCAL_METADATA_CAPABILITIES.get(id)
    if profile == 'model_d5_proposal_v1':
        if id in {'capa.d4.root_cause_candidate.masked.v1', 'capa.d5.proposal.save.v1', 'capa.d5.proposal.replace.v1'}:
            return replace(CAPA_CAPABILITIES[id], approval_floor=ApprovalFloor.DIRECT)
        return None
    if profile == 'model_d5_proposal_r6_v1':
        if id in {'capa.d2.snapshot.v1', 'capa.d3.snapshot.v1',
                  'capa.d4.root_cause_candidate.masked.v1',
                  'capa.d5.proposal.save.v1', 'capa.d5.proposal.replace.v1'}:
            return replace(CAPA_CAPABILITIES[id], approval_floor=ApprovalFloor.DIRECT)
        return None
    if profile == 'model_d4_candidate_v1':
        if id in {'capa.d2.snapshot.v1', 'capa.d3.snapshot.v1',
                  'capa.d4.candidate.propose.v1', 'capa.d4.fmea_input.masked.v1'}:
            return replace(CAPA_CAPABILITIES[id], approval_floor=ApprovalFloor.DIRECT)
        return None
    if profile == TEXT_PROFILE:
        return _LOCAL_TEXT_CAPABILITIES.get(id)
    return None
