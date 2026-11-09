"""Plugin-only runtime DTOs; no client supplied identity, target or delivery policy."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class RunClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installation_id: UUID
    secret: Annotated[str, StringConstraints(strict=True, min_length=20, max_length=200)] = Field(repr=False)
    request_key: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]


class RunClaimOut(BaseModel):
    run_id: UUID
    task_id: UUID
    token: str = Field(repr=False)
    lease_epoch: int
    lease_expires_at: datetime
    accepted_message_seq: int
    has_resume_checkpoint: bool


class RuntimeCapability(BaseModel):
    id: str
    allowed: bool
    required: bool
    projection: Literal["masked", "raw"] | None


class RuntimeCapabilities(BaseModel):
    capabilities: list[RuntimeCapability]


class MessageClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 20


class MessageAck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: UUID
    through_sequence: Annotated[int, Field(strict=True, ge=1)]


class RuntimeMessage(BaseModel):
    message_id: UUID
    sequence: int
    content: str


class MessageBatch(BaseModel):
    batch_id: UUID | None
    messages: list[RuntimeMessage]
    accepted_sequence: int


class MessageAckOut(BaseModel):
    accepted_sequence: int


class CapaContextQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: UUID | None = None
    view: Literal["report", "verifications"] = "report"


class CapaVerificationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    verification_id: str
    conclusion: Literal["pending", "passed", "failed"]
    is_verified: bool


class CapaContextProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    projection_id: Literal["capa.d4.summary.masked.v1"]
    source_capa_id: str
    data_class: Literal["internal"]
    report_id: str
    document_no: str = Field(max_length=50)
    status: str = Field(max_length=20)
    severity: str = Field(max_length=20)
    factory_id: str
    product_line_code: str = Field(max_length=20)
    updated_at: str
    verifications: list[CapaVerificationMetadata]
    projection_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


OutputKey = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
AnalysisText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=2000)]
AnalysisItems = Annotated[list[AnalysisText], Field(max_length=20)]


class RuntimeEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    stage: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)] | None = None
    message: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)] | None = None
    completed: Annotated[int, Field(strict=True, ge=0, le=1000000)] | None = None
    total: Annotated[int, Field(strict=True, ge=0, le=1000000)] | None = None


class RuntimeEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: OutputKey
    event_type: Literal["progress", "query_completed"]
    payload: RuntimeEventPayload
    receipt_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _require_query_sources(self):
        if self.event_type == "query_completed" and not self.receipt_ids:
            raise ValueError("query_completed requires sources")
        return self


class RuntimeResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    explanations: AnalysisItems = Field(default_factory=list)
    support: AnalysisItems = Field(default_factory=list)
    opposition: AnalysisItems = Field(default_factory=list)
    missing_information: AnalysisItems = Field(default_factory=list)
    conditional_recommendations: AnalysisItems = Field(default_factory=list)


class RuntimeResultCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: OutputKey
    receipt_ids: list[UUID] = Field(min_length=1, max_length=20)
    payload: RuntimeResultPayload


class RuntimeSourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_id: UUID
    source_capa_id: UUID
    projection_id: Literal["capa.d4.summary.masked.v1"]
    projection_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    data_class: Literal["internal"]


class RuntimeEventOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    task_id: UUID
    run_id: UUID
    event_type: Literal["progress", "query_completed"]
    payload: RuntimeEventPayload
    sources: list[RuntimeSourceOut] = Field(max_length=20)


class RuntimeResultOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_id: UUID
    task_id: UUID
    run_id: UUID
    data_class: Literal["restricted"]
    payload: RuntimeResultPayload
    sources: list[RuntimeSourceOut] = Field(min_length=1, max_length=20)


class ReadonlyCheckpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: OutputKey
    receipt_ids: list[UUID] = Field(min_length=1, max_length=20)


class ReadonlyCheckpointOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checkpoint_id: UUID
    task_id: UUID
    run_id: UUID
    lease_epoch: Annotated[int, Field(strict=True, ge=0)]
    tenant_generation: Annotated[int, Field(strict=True, ge=0)]
    accepted_message_seq: Annotated[int, Field(strict=True, ge=0)]
    update_sequence: Annotated[int, Field(strict=True, gt=0)]
    created_at: datetime
    sources: list[RuntimeSourceOut] = Field(min_length=1, max_length=20)


class ReadonlyCheckpointView(ReadonlyCheckpointOut):
    is_latest: bool
    prefix_eligible: bool


class MessageHistoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_sequence: Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)] = 0
    limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 20


class MessageHistoryHTTPQuery(MessageHistoryQuery):
    """Only canonical decimal query text is converted at the HTTP boundary."""
    @model_validator(mode="before")
    @classmethod
    def _decimal_query(cls, value):
        import re
        fields = dict(value)
        for name in ("after_sequence", "limit"):
            raw = fields.get(name)
            if isinstance(raw, str):
                if re.fullmatch(r"[0-9]{1,19}", raw) is None:
                    raise ValueError("Invalid sequence query")
                fields[name] = int(raw)
        return fields


class MessageHistoryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[RuntimeMessage] = Field(max_length=20)
    next_sequence: int
    complete: bool
