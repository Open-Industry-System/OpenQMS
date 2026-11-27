"""Validate R7 result claims against authorized evidence of a single run."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


# An uncorrected, immutable CAPA measure has no correction revision.
MeasureKey = tuple[UUID, UUID | None]


class CompletionError(ValueError):
    """The submitted assessment cannot complete the task."""


class Conclusion(StrEnum):
    IMPACT_FOUND = "impact_found"
    NO_IMPACT_FOUND = "no_impact_found"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True, slots=True)
class Analysis:
    analysis_ref: str
    reason: str
    fact_refs: tuple[str, ...] = ()
    inference: str = ""


@dataclass(frozen=True, slots=True)
class NodeAdjustment:
    target_ref: str
    proposal: str


@dataclass(frozen=True, slots=True)
class Assessment:
    measure_id: UUID
    formal_revision: UUID | None
    analysis_ref: str
    conclusion: Conclusion
    evidence_refs: tuple[str, ...] = ()
    coverage_refs: tuple[str, ...] = ()
    exclusion_refs: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    node_adjustments: tuple[NodeAdjustment, ...] = ()

    @property
    def measure_key(self) -> MeasureKey:
        return self.measure_id, self.formal_revision


class EvidenceVerifier(Protocol):
    """The runtime resolves authorized references against its bound run and snapshot.

    Each method checks every supplied reference for the given measure and rejects
    unknown references, incomplete coverage and inapplicable claims. Implement
    these checks from server evidence. Plugin-provided receipts alone prove nothing.
    """

    def verify_evidence(self, measure: MeasureKey, refs: tuple[str, ...]) -> bool: ...

    def verify_impact_path(
        self, measure: MeasureKey, target_ref: str, evidence_refs: tuple[str, ...],
    ) -> bool: ...

    def verify_coverage(self, measure: MeasureKey, refs: tuple[str, ...]) -> bool: ...

    def verify_exclusion(
        self, measure: MeasureKey, refs: tuple[str, ...], coverage_refs: tuple[str, ...],
    ) -> bool: ...


def validate_completion(
    expected_measures: Collection[MeasureKey],
    analyses: Sequence[Analysis],
    assessments: Sequence[Assessment],
    *,
    verifier: EvidenceVerifier,
) -> Conclusion:
    """Check a parsed proposal and derive its conclusion without persisting it."""
    expected = set(expected_measures)
    submitted = {item.measure_key for item in assessments}
    if (
        not expected
        or len(expected) != len(expected_measures)
        or len({measure_id for measure_id, _ in expected}) != len(expected)
        or len(submitted) != len(assessments)
        or submitted != expected
    ):
        raise CompletionError("Assessment must include every bound measure revision exactly once")

    by_ref = {analysis.analysis_ref: analysis for analysis in analyses}
    used_refs = {item.analysis_ref for item in assessments}
    if len(by_ref) != len(analyses) or used_refs != by_ref.keys():
        raise CompletionError("Analysis references must resolve without duplicates or unused analyses")
    if any(not analysis.analysis_ref.strip() or not analysis.reason.strip() for analysis in analyses):
        raise CompletionError("Each analysis needs a reference and rationale")

    for item in assessments:
        _validate_assessment(item, by_ref[item.analysis_ref], verifier)

    conclusions = {item.conclusion for item in assessments}
    if Conclusion.IMPACT_FOUND in conclusions:
        return Conclusion.IMPACT_FOUND
    if Conclusion.INSUFFICIENT_EVIDENCE in conclusions:
        return Conclusion.INSUFFICIENT_EVIDENCE
    return Conclusion.NO_IMPACT_FOUND


def _validate_assessment(item: Assessment, analysis: Analysis, verifier: EvidenceVerifier) -> None:
    measure = item.measure_key
    refs = analysis.fact_refs + item.evidence_refs
    if refs and verifier.verify_evidence(measure, refs) is not True:
        raise CompletionError("Evidence is not authorized for this measure")
    if any(not gap.strip() for gap in item.missing_information):
        raise CompletionError("Missing information must specify a gap")

    if item.conclusion == Conclusion.NO_IMPACT_FOUND:
        if item.node_adjustments:
            raise CompletionError("A no-impact result cannot propose node adjustments")
        if not item.coverage_refs or verifier.verify_coverage(measure, item.coverage_refs) is not True:
            raise CompletionError("A no-impact result requires complete applicable coverage")
        if not item.exclusion_refs or verifier.verify_exclusion(
            measure, item.exclusion_refs, item.coverage_refs,
        ) is not True:
            raise CompletionError("A no-impact result requires formal applicable exclusion evidence")
        return

    if item.coverage_refs or item.exclusion_refs:
        raise CompletionError("Use coverage and exclusion proof only for a no-impact claim")

    if item.conclusion == Conclusion.IMPACT_FOUND:
        if not item.evidence_refs or not item.node_adjustments:
            raise CompletionError("An impact finding requires measure evidence and proposed adjustments")
        for adjustment in item.node_adjustments:
            if not adjustment.proposal.strip() or verifier.verify_impact_path(
                measure, adjustment.target_ref, item.evidence_refs,
            ) is not True:
                raise CompletionError("A proposed adjustment requires a supported location and rationale")
    elif item.conclusion == Conclusion.INSUFFICIENT_EVIDENCE:
        if not item.missing_information or item.node_adjustments:
            raise CompletionError("Insufficient evidence requires a named gap and no node adjustment")
    else:
        raise CompletionError("Unsupported impact conclusion")
