"""Pure R7 completion rules. The runtime provides the current authorized verifier."""
from dataclasses import replace
from uuid import UUID

import pytest

from app.services.agent_runtime.pfmea_impact_completion import (
    Analysis,
    Assessment,
    CompletionError,
    Conclusion,
    NodeAdjustment,
    validate_completion,
)

M1 = UUID(int=1)
M2 = UUID(int=2)
R2 = UUID(int=20)
R4 = UUID(int=40)
MEASURES = {(M1, R2), (M2, R4)}
SHARED = Analysis("shared", reason="Compare the press operation.", fact_refs=("d4-fact",))
IMPACT = Assessment(
    M1, R2, "shared", Conclusion.IMPACT_FOUND,
    evidence_refs=("m1-evidence",),
    node_adjustments=(NodeAdjustment("approved-failure-mode", "Review the reaction plan."),),
)
INSUFFICIENT = Assessment(
    M2, R4, "shared", Conclusion.INSUFFICIENT_EVIDENCE,
    missing_information=("The alternate line has no process identifier.",),
)
NO_IMPACT = Assessment(
    M2, R4, "shared", Conclusion.NO_IMPACT_FOUND,
    coverage_refs=("complete-range",),
    exclusion_refs=("documented-exclusion",),
)


class Verifier:
    def verify_evidence(self, measure, refs):
        allowed = {
            (M1, R2): {"d4-fact", "m1-evidence"},
            (M2, R4): {"d4-fact", "m2-evidence"},
        }
        return set(refs) <= allowed[measure]

    def verify_impact_path(self, measure, target_ref, evidence_refs):
        return (
            measure == (M1, R2)
            and target_ref == "approved-failure-mode"
            and evidence_refs == ("m1-evidence",)
        )

    def verify_coverage(self, measure, refs):
        return measure in MEASURES and refs == ("complete-range",)

    def verify_exclusion(self, measure, refs, coverage_refs):
        return (
            measure in MEASURES
            and refs == ("documented-exclusion",)
            and coverage_refs == ("complete-range",)
        )


def test_shared_analysis_preserves_individual_conclusions_and_derives_aggregate():
    result = validate_completion(MEASURES, [SHARED], [IMPACT, INSUFFICIENT], verifier=Verifier())

    assert result == Conclusion.IMPACT_FOUND


@pytest.mark.parametrize(
    "second",
    [None, IMPACT, replace(INSUFFICIENT, measure_id=UUID(int=3)),
     replace(INSUFFICIENT, formal_revision=UUID(int=30)), replace(INSUFFICIENT, analysis_ref="unknown")],
    ids=["missing", "duplicate", "unknown-measure", "old-revision", "unknown-analysis"],
)
def test_complete_requires_each_bound_measure_revision_exactly_once(second):
    with pytest.raises(CompletionError):
        validate_completion(
            MEASURES, [SHARED], [IMPACT] if second is None else [IMPACT, second],
            verifier=Verifier(),
        )


def test_zero_expected_measures_is_not_a_vacuous_negative_result():
    with pytest.raises(CompletionError):
        validate_completion(set(), [], [], verifier=Verifier())


def test_insufficient_evidence_precedes_no_impact():
    first = replace(NO_IMPACT, measure_id=M1, formal_revision=R2)
    assert (
        validate_completion(MEASURES, [SHARED], [first, INSUFFICIENT], verifier=Verifier())
        == Conclusion.INSUFFICIENT_EVIDENCE
    )


def test_all_measures_can_complete_without_impact_only_with_formal_exclusion_and_coverage():
    first = replace(NO_IMPACT, measure_id=M1, formal_revision=R2)
    assert (
        validate_completion(MEASURES, [SHARED], [first, NO_IMPACT], verifier=Verifier())
        == Conclusion.NO_IMPACT_FOUND
    )


@pytest.mark.parametrize(
    "invalid",
    [
        replace(NO_IMPACT, coverage_refs=()),
        replace(NO_IMPACT, coverage_refs=("keyword-page-only",)),
        replace(NO_IMPACT, coverage_refs=("wrong-run",)),
        replace(NO_IMPACT, coverage_refs=("wrong-operation",)),
        replace(NO_IMPACT, exclusion_refs=()),
        replace(NO_IMPACT, exclusion_refs=("formal-but-not-applicable",)),
    ],
)
def test_no_impact_rejects_missing_or_inapplicable_coverage_and_exclusion(invalid):
    with pytest.raises(CompletionError):
        validate_completion(MEASURES, [SHARED], [IMPACT, invalid], verifier=Verifier())


@pytest.mark.parametrize(
    "invalid",
    [
        replace(INSUFFICIENT, missing_information=()),
        replace(INSUFFICIENT, missing_information=(" ",)),
        replace(INSUFFICIENT, node_adjustments=IMPACT.node_adjustments),
    ],
)
def test_insufficient_evidence_names_missing_information_and_cannot_carry_adjustments(invalid):
    with pytest.raises(CompletionError):
        validate_completion(MEASURES, [SHARED], [IMPACT, invalid], verifier=Verifier())


def test_shared_analysis_does_not_transfer_per_measure_evidence():
    invalid = replace(INSUFFICIENT, evidence_refs=IMPACT.evidence_refs)
    with pytest.raises(CompletionError):
        validate_completion(MEASURES, [SHARED], [IMPACT, invalid], verifier=Verifier())


def test_analysis_fact_references_are_revalidated_for_each_measure():
    invalid_analysis = replace(SHARED, fact_refs=IMPACT.evidence_refs)
    with pytest.raises(CompletionError):
        validate_completion(MEASURES, [invalid_analysis], [IMPACT, INSUFFICIENT], verifier=Verifier())


@pytest.mark.parametrize(
    "invalid",
    [
        replace(IMPACT, evidence_refs=()),
        replace(IMPACT, node_adjustments=()),
        replace(IMPACT, node_adjustments=(NodeAdjustment("other-version", "Review it."),)),
    ],
)
def test_impact_requires_real_supported_location_and_adjustment(invalid):
    with pytest.raises(CompletionError):
        validate_completion(MEASURES, [SHARED], [invalid, INSUFFICIENT], verifier=Verifier())


def test_analysis_ids_are_unique_and_every_analysis_is_referenced():
    for analyses in ([SHARED, SHARED], [SHARED, replace(SHARED, analysis_ref="unused")]):
        with pytest.raises(CompletionError):
            validate_completion(MEASURES, analyses, [IMPACT, INSUFFICIENT], verifier=Verifier())


def test_original_measure_revision_is_distinct_from_any_correction():
    original = replace(INSUFFICIENT, formal_revision=None)
    analysis = replace(SHARED, fact_refs=())
    assert (
        validate_completion({(M2, None)}, [analysis], [original], verifier=Verifier())
        == Conclusion.INSUFFICIENT_EVIDENCE
    )

    with pytest.raises(CompletionError):
        validate_completion({(M2, None)}, [analysis], [INSUFFICIENT], verifier=Verifier())


def test_evidence_check_must_explicitly_approve_the_reference():
    class IndeterminateVerifier(Verifier):
        def verify_evidence(self, measure, refs):
            return None

    with pytest.raises(CompletionError):
        validate_completion(MEASURES, [SHARED], [IMPACT, INSUFFICIENT], verifier=IndeterminateVerifier())
