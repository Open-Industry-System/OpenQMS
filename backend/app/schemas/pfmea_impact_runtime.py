"""Strict protected R7 worker protocol."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

from app.services.agent_runtime.pfmea_impact_completion import Analysis, Assessment, Conclusion, NodeAdjustment
from app.services.agent_runtime.pfmea_impact_results import ImpactResultSubmission

Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Cursor = Annotated[str, StringConstraints(min_length=1, max_length=4096, pattern=r"^[!-~]+$")]
Text = Annotated[str, StringConstraints(max_length=16384)]
Refs = Annotated[list[Text], Field(max_length=256)]


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Search(Empty):
    term: str = Field(min_length=1, max_length=120)
    cursor: Cursor | None


class Page(Empty):
    scope_ref: Cursor
    cursor: Cursor | None


class Confirm(Empty):
    release_id: UUID
    page_key: Digest
    payload_digest: Digest
    token: Digest


class AnalysisInput(Empty):
    analysis_ref: Text
    reason: Text
    fact_refs: Refs
    inference: Text


class AdjustmentInput(Empty):
    target_ref: Text
    proposal: Text


class AssessmentInput(Empty):
    measure_id: UUID
    formal_revision: UUID | None
    analysis_ref: Text
    conclusion: Conclusion
    evidence_refs: Refs
    coverage_refs: Refs
    exclusion_refs: Refs
    missing_information: Refs
    node_adjustments: list[AdjustmentInput] = Field(max_length=256)


class Candidate(Empty):
    analyses: list[AnalysisInput] = Field(min_length=1, max_length=32)
    assessments: list[AssessmentInput] = Field(min_length=1, max_length=32)


class Result(Candidate):
    operation_key: str = Field(min_length=1, max_length=100)

    def submission(self):
        return ImpactResultSubmission(
            self.operation_key,
            tuple(Analysis(item.analysis_ref, item.reason, tuple(item.fact_refs), item.inference)
                  for item in self.analyses),
            tuple(Assessment(
                item.measure_id, item.formal_revision, item.analysis_ref, item.conclusion,
                tuple(item.evidence_refs), tuple(item.coverage_refs), tuple(item.exclusion_refs),
                tuple(item.missing_information),
                tuple(NodeAdjustment(change.target_ref, change.proposal) for change in item.node_adjustments),
            ) for item in self.assessments),
        )


class SearchAction(Search):
    kind: Literal["search"]


class PageAction(Page):
    kind: Literal["page"]


class CompleteAction(Candidate):
    kind: Literal["complete"]


class FailAction(Empty):
    kind: Literal["fail"]


Action = TypeAdapter(Annotated[SearchAction | PageAction | CompleteAction | FailAction, Field(discriminator="kind")])
