"""The current-report outcome read contract; not a decision-write request."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.capa_verification import D7NodeActionResponse, VerificationResponse


class OutcomeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutcomeCore(OutcomeModel):
    d4_root_cause: str | None = Field(repr=False)
    d5_correction: str | None = Field(repr=False)
    d6_verification: str | None = Field(repr=False)
    d7_prevention: str | None = Field(repr=False)


class OutcomeDocumentRef(OutcomeModel):
    module: Literal["fmea", "planning"]
    object_id: UUID
    version_id: UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class OutcomeDocGate(OutcomeModel):
    decision_id: UUID
    analysis_id: UUID
    audit_run_id: UUID | None
    revision: int
    factory_id: UUID
    decision: Literal["passed", "blocked", "deferred"]
    no_affected_confirmed: bool
    version_snapshot: list = Field(repr=False)
    defer_reason: str | None = Field(repr=False)
    defer_owner: UUID | None
    defer_deadline: date | None
    waiver_reason: str | None = Field(repr=False)
    waiver_items: list | None = Field(repr=False)
    decided_by: UUID
    decided_at: datetime


class OutcomeDecision(OutcomeModel):
    action: Literal["approved", "rejected"]
    actor_id: UUID | None
    operated_at: datetime
    audit_id: UUID


class OutcomeSupplement(OutcomeModel):
    text: str | None = Field(repr=False)
    review_scope: Literal["unreviewed_supplement"] = "unreviewed_supplement"
    updated_by: UUID | None
    updated_at: datetime | None


class CapaOutcomeReview(OutcomeModel):
    report_id: UUID
    status: str
    contract: Literal["capa.outcome-review.v1"] = "capa.outcome-review.v1"
    review_round_id: UUID | None
    revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_status: Literal["pending", "verified", "legacy_unversioned", "unverifiable"]
    core: OutcomeCore = Field(repr=False)
    verifications: list[VerificationResponse] = Field(repr=False)
    d7_actions: list[D7NodeActionResponse] = Field(repr=False)
    doc_gate: OutcomeDocGate | None = Field(repr=False)
    documents: list[OutcomeDocumentRef]
    decision: OutcomeDecision | None
    supplement: OutcomeSupplement = Field(repr=False)
