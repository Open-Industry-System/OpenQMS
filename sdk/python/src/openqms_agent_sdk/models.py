"""Immutable protocol containers, not runtime schema or authorization checks.

The codec validates strict types, bounds, enums, aware timestamps and bindings.
Only ClientConfig validates local numeric resource settings here.
"""
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from .errors import ConfigError

REQUEST_BUDGET = 1024 * 1024
_MANAGED_LAUNCH_PROFILES = frozenset({
    ("r6.d4.launch.v1", "model_d4_candidate_v1"),
    ("r7.pfmea.launch.v1", "model_pfmea_impact_v1"),
})
SUPPORTED_OPERATIONS = MappingProxyType({
    "claim": ("POST", "/api/agent/runtime/claim"),
    "capabilities": ("GET", "/api/agent/runtime/capabilities"),
    "claim_messages": ("POST", "/api/agent/runtime/messages/claim"),
    "ack_messages": ("POST", "/api/agent/runtime/messages/ack"),
    "capa_context": ("GET", "/api/agent/runtime/capa/context"),
    "record_event": ("POST", "/api/agent/runtime/events"),
    "save_result": ("POST", "/api/agent/runtime/results"),
    "save_checkpoint": ("POST", "/api/agent/runtime/checkpoints"),
    "message_history": ("GET", "/api/agent/runtime/messages/history"),
    "finish": ("POST", "/api/agent/runtime/finish"),
    "model_turn": ("POST", "/api/agent/runtime/model/infer"),
    "model_tool": ("POST", "/api/agent/runtime/model/tools"),
    "save_d4_checkpoint": ("POST", "/api/agent/runtime/capa/d4/checkpoints"),
    "save_d4_candidate": ("POST", "/api/agent/runtime/capa/d4/candidates"),
    "pfmea_impact_material": ("GET", "/api/agent/runtime/pfmea-impact/material"),
    "pfmea_impact_search": ("POST", "/api/agent/runtime/pfmea-impact/search"),
    "pfmea_impact_page": ("POST", "/api/agent/runtime/pfmea-impact/page"),
    "pfmea_impact_confirm": ("POST", "/api/agent/runtime/pfmea-impact/confirm"),
    "pfmea_impact_result": ("POST", "/api/agent/runtime/pfmea-impact/result"),
})


@dataclass(frozen=True, slots=True)
class ClientConfig:
    base_url: str = field(repr=False)
    tenant_slug: str | None = field(default=None, repr=False)
    timeout: float = 10.0
    response_budget: int = 4 * 1024 * 1024

    def __post_init__(self):
        # Range check before isfinite avoids overflow for arbitrarily large ints.
        if type(self.timeout) not in (int, float) or not 1 <= self.timeout <= 120 or not isfinite(self.timeout):
            raise ConfigError("config", kind="invalid_timeout")
        if type(self.response_budget) is not int or not 64 * 1024 <= self.response_budget <= 16 * 1024 * 1024:
            raise ConfigError("config", kind="invalid_response_budget")


@dataclass(frozen=True, slots=True)
class EncodedRequest:
    body: bytes | None = field(repr=False)
    query: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class WireResponse:
    status: int
    body: bytes = field(repr=False)
    may_have_been_sent: bool


@dataclass(frozen=True, slots=True)
class RunClaim:
    run_id: UUID
    task_id: UUID
    lease_epoch: int
    lease_expires_at: datetime
    accepted_message_seq: int
    has_resume_checkpoint: bool


@dataclass(frozen=True, slots=True)
class ClaimEnvelope:
    claim: RunClaim
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class Capability:
    id: str
    allowed: bool
    required: bool
    projection: Literal["masked", "raw"] | None


@dataclass(frozen=True, slots=True)
class Capabilities:
    capabilities: tuple[Capability, ...]


@dataclass(frozen=True, slots=True)
class RuntimeMessage:
    message_id: UUID
    sequence: int
    content: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MessageBatch:
    batch_id: UUID | None
    messages: tuple[RuntimeMessage, ...]
    accepted_sequence: int


@dataclass(frozen=True, slots=True)
class MessageAck:
    accepted_sequence: int


@dataclass(frozen=True, slots=True)
class MessageHistory:
    messages: tuple[RuntimeMessage, ...]
    next_sequence: int
    complete: bool


@dataclass(frozen=True, slots=True)
class Verification:
    verification_id: UUID
    conclusion: Literal["pending", "passed", "failed"]
    is_verified: bool


@dataclass(frozen=True, slots=True)
class CapaContext:
    receipt_id: UUID
    source_capa_id: UUID
    report_id: UUID
    factory_id: UUID
    projection_id: str
    data_class: str
    document_no: str = field(repr=False)
    status: str = field(repr=False)
    severity: str = field(repr=False)
    product_line_code: str = field(repr=False)
    updated_at: datetime
    projection_digest: str
    verifications: tuple[Verification, ...] | None


@dataclass(frozen=True, slots=True)
class EventPayload:
    stage: str | None = field(default=None, repr=False)
    message: str | None = field(default=None, repr=False)
    completed: int | None = None
    total: int | None = None


@dataclass(frozen=True, slots=True)
class ResultPayload:
    explanations: tuple[str, ...] = field(default=(), repr=False)
    support: tuple[str, ...] = field(default=(), repr=False)
    opposition: tuple[str, ...] = field(default=(), repr=False)
    missing_information: tuple[str, ...] = field(default=(), repr=False)
    conditional_recommendations: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True, slots=True)
class Source:
    receipt_id: UUID
    source_capa_id: UUID
    projection_id: str
    projection_digest: str
    data_class: str


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    event_id: UUID
    task_id: UUID
    run_id: UUID
    event_type: str
    payload: EventPayload = field(repr=False)
    sources: tuple[Source, ...]


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    result_id: UUID
    task_id: UUID
    run_id: UUID
    data_class: str
    payload: ResultPayload = field(repr=False)
    sources: tuple[Source, ...]


@dataclass(frozen=True, slots=True)
class ReadonlyCheckpoint:
    checkpoint_id: UUID
    task_id: UUID
    run_id: UUID
    lease_epoch: int
    tenant_generation: int
    accepted_message_seq: int
    update_sequence: int
    created_at: datetime
    sources: tuple[Source, ...]


@dataclass(frozen=True, slots=True)
class FinishResult:
    task_id: UUID
    run_id: UUID
    task_status: str
    run_status: str
    lease_epoch: int


@dataclass(frozen=True, slots=True)
class D4CandidateReference:
    candidate_id: UUID
    command_id: UUID
    task_id: UUID
    run_id: UUID
    report_id: UUID
    state: str
    version: int


@dataclass(frozen=True, slots=True)
class ModelToolCall:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class ModelTurn:
    content: str = field(repr=False)
    tool_calls: tuple[ModelToolCall, ...]


@dataclass(frozen=True, slots=True)
class ModelToolResult:
    status: str
    candidate_id: UUID | None = None
    accepted_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class D4CandidateCheckpoint:
    checkpoint_id: UUID
    task_id: UUID
    run_id: UUID
    lease_epoch: int
    command_watermark: int


@dataclass(frozen=True, slots=True)
class ManagedLaunch:
    """Platform claim metadata only; the server validates the opaque token."""
    protocol: str
    profile: str
    api_origin: str = field(repr=False)
    tenant_slug: str = field(repr=False)
    token: str = field(repr=False)
    task_id: UUID
    run_id: UUID
    deployment_id: UUID
    lease_epoch: int
    lease_expires_at: datetime
    accepted_message_seq: int
    has_resume_checkpoint: bool

    def __post_init__(self):
        import re
        from datetime import timezone
        valid = (type(self.protocol) is str and type(self.profile) is str
            and (self.protocol, self.profile) in _MANAGED_LAUNCH_PROFILES
            and all(type(value) is UUID for value in (self.task_id,self.run_id,self.deployment_id))
            and type(self.token) is str and re.fullmatch(r'[A-Za-z0-9._-]{1,8192}',self.token) is not None
            and type(self.api_origin) is str and type(self.tenant_slug) is str
            and type(self.lease_epoch) is int and 0 <= self.lease_epoch <= 2**63-1
            and type(self.accepted_message_seq) is int and 0 <= self.accepted_message_seq <= 2**63-1
            and type(self.has_resume_checkpoint) is bool and type(self.lease_expires_at) is datetime
            and self.lease_expires_at.tzinfo is not None and self.lease_expires_at > datetime.now(timezone.utc))
        if not valid: raise ConfigError('config',kind='invalid_request')

    @classmethod
    def from_dict(cls, value):
        from ._codec import decode_managed_launch
        return decode_managed_launch(value)


@dataclass(frozen=True, slots=True)
class PfmeaImpactRelease:
    """Payload bytes checked against the bound release digest by the codec."""

    receipt_id: UUID
    run_id: UUID
    task_id: UUID
    lease_epoch: int
    projection_bytes: bytes = field(repr=False)
    payload_digest: str
    snapshot_digest: str
    scope_ref: str | None = field(repr=False)
    page_key: str | None
    confirmation_token: str | None = field(repr=False)
    next_cursor: str | None = field(repr=False)
    gap: str | None = None


@dataclass(frozen=True, slots=True)
class PfmeaImpactConfirmation:
    confirmation_id: UUID
    coverage_id: UUID | None
    run_id: UUID
    task_id: UUID
    lease_epoch: int


@dataclass(frozen=True, slots=True)
class PfmeaImpactResultRef:
    result_id: UUID
    run_id: UUID
    task_id: UUID
    lease_epoch: int


@dataclass(frozen=True, slots=True)
class PfmeaImpactAnalysis:
    analysis_ref: str = field(repr=False)
    reason: str = field(repr=False)
    fact_refs: tuple[str, ...] = field(default=(), repr=False)
    inference: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class PfmeaImpactAdjustment:
    target_ref: str = field(repr=False)
    proposal: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PfmeaImpactAssessment:
    measure_id: UUID
    formal_revision: UUID | None
    analysis_ref: str = field(repr=False)
    conclusion: Literal["impact_found", "no_impact_found", "insufficient_evidence"]
    evidence_refs: tuple[str, ...] = field(default=(), repr=False)
    coverage_refs: tuple[str, ...] = field(default=(), repr=False)
    exclusion_refs: tuple[str, ...] = field(default=(), repr=False)
    missing_information: tuple[str, ...] = field(default=(), repr=False)
    node_adjustments: tuple[PfmeaImpactAdjustment, ...] = field(default=(), repr=False)
