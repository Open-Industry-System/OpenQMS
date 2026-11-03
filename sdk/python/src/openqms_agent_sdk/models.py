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
