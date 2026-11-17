"""
Unit tests for supplier_service pure functions.
Run: python tests/test_supplier.py

The app config requires SECRET_KEY to be non-default; we set a dummy value so the
import chain resolves without a real .env file.
"""
import sys
import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")

# Allow running from the backend directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.supplier_service import _calculate_evaluation, _transition_status

# ─── _calculate_evaluation ──────────────────────────────────────────────────

def test_calculate_evaluation_perfect_score():
    base, capa_pen, finding_pen, pf_pen, cd_pen, total, grade = _calculate_evaluation(100, 100, 100, 0, 0)
    # base = 100*0.35 + 100*0.30 + 100*0.15 = 80.0
    assert base == 80.0, "perfect: base == 80.0"
    assert capa_pen == 0, "perfect: capa_penalty == 0"
    assert finding_pen == 0, "perfect: finding_penalty == 0"
    assert pf_pen == 0, "perfect: premium_freight_penalty == 0"
    assert cd_pen == 0, "perfect: customer_disruption_penalty == 0"
    assert total == 80.0, "perfect: total == 80.0"
    assert grade == "A", "perfect: grade == 'A'"


def test_calculate_evaluation_grade_a():
    # Grade A threshold is >= 72.
    # The perfect-score case is covered by test_calculate_evaluation_perfect_score.
    # Boundary at exactly 72: q=d=s=90 → base=90*0.80=72
    _, _, _, _, _, total72, grade72 = _calculate_evaluation(90, 90, 90, 0, 0)
    assert abs(total72 - 72.0) < 0.001, "grade A boundary: total == 72.0"
    assert grade72 == "A", "grade A boundary: grade == 'A'"


def test_calculate_evaluation_grade_b_boundary():
    # Grade B threshold is >= 60.
    # Boundary at exactly 60: q=d=s=75 → base=75*0.80=60.0 → grade B
    base, capa_pen, finding_pen, pf_pen, cd_pen, total, grade = _calculate_evaluation(75, 75, 75, 0, 0)
    assert abs(total - 60.0) < 0.001, "grade B boundary: total == 60.0"
    assert grade == "B", "grade B boundary: grade == 'B'"

    # Just below A threshold → grade B
    _, _, _, _, _, total_below_a, grade_below_a = _calculate_evaluation(89.9, 89.9, 89.9, 0, 0)
    assert grade_below_a == "B", "grade B just below A threshold"


def test_calculate_evaluation_grade_c():
    # Grade C threshold is >= 48.
    # Boundary at exactly 48: q=d=s=60 → base=60*0.80=48.0 → grade C
    _, _, _, _, _, total, grade = _calculate_evaluation(60, 60, 60, 0, 0)
    assert abs(total - 48.0) < 0.001, "grade C boundary: total == 48.0"
    assert grade == "C", "grade C boundary: grade == 'C'"

    # Just below B threshold → grade C
    _, _, _, _, _, total_below_b, grade_below_b = _calculate_evaluation(74.9, 74.9, 74.9, 0, 0)
    assert grade_below_b == "C", "grade C just below B threshold"


def test_calculate_evaluation_grade_d():
    # Grade D is < 48.
    # q=d=s=50 → base = 50*0.80 = 40.0 → grade D
    _, _, _, _, _, total, grade = _calculate_evaluation(50, 50, 50, 0, 0)
    assert abs(total - 40.0) < 0.001, "grade D: total == 40.0"
    assert grade == "D", "grade D: grade == 'D'"


def test_calculate_evaluation_capa_cap():
    # 6 CAPAs → 6*2=12, capped at 10
    _, capa_pen, _, _, _, _, _ = _calculate_evaluation(100, 100, 100, 6, 0)
    assert capa_pen == 10, "capa cap at 10 for 6 CAPAs"

    # exactly 5 CAPAs → 5*2=10 (at cap)
    _, capa_pen5, _, _, _, _, _ = _calculate_evaluation(100, 100, 100, 5, 0)
    assert capa_pen5 == 10, "capa cap at 10 for 5 CAPAs"

    # 4 CAPAs → 4*2=8 (under cap)
    _, capa_pen4, _, _, _, _, _ = _calculate_evaluation(100, 100, 100, 4, 0)
    assert capa_pen4 == 8, "capa penalty 8 for 4 CAPAs"


def test_calculate_evaluation_finding_cap():
    # 4 findings → 4*3=12, capped at 10
    _, _, finding_pen, _, _, _, _ = _calculate_evaluation(100, 100, 100, 0, 4)
    assert finding_pen == 10, "finding cap at 10 for 4 findings"

    # exactly 3 findings → 3*3=9 (under cap but close)
    _, _, finding_pen3, _, _, _, _ = _calculate_evaluation(100, 100, 100, 0, 3)
    assert finding_pen3 == 9, "finding penalty 9 for 3 findings"

    # 1 finding → 1*3=3
    _, _, finding_pen1, _, _, _, _ = _calculate_evaluation(100, 100, 100, 0, 1)
    assert finding_pen1 == 3, "finding penalty 3 for 1 finding"


def test_calculate_evaluation_premium_freight_penalty():
    # 3 premium freight → 3*5=15, capped at 10
    _, _, _, pf_pen, _, _, _ = _calculate_evaluation(100, 100, 100, 0, 0, 3, 0)
    assert pf_pen == 10, "premium freight cap at 10 for 3 occurrences"

    # exactly 2 premium freight → 2*5=10 (at cap)
    _, _, _, pf_pen2, _, _, _ = _calculate_evaluation(100, 100, 100, 0, 0, 2, 0)
    assert pf_pen2 == 10, "premium freight penalty 10 for 2 occurrences"

    # 1 premium freight → 1*5=5
    _, _, _, pf_pen1, _, total, _ = _calculate_evaluation(100, 100, 100, 0, 0, 1, 0)
    assert pf_pen1 == 5, "premium freight penalty 5 for 1 occurrence"
    assert abs(total - 75.0) < 0.001, "total reduced by premium freight"


def test_calculate_evaluation_customer_disruption_penalty():
    # 3 customer disruptions → 3*5=15, capped at 10
    _, _, _, _, cd_pen, _, _ = _calculate_evaluation(100, 100, 100, 0, 0, 0, 3)
    assert cd_pen == 10, "customer disruption cap at 10 for 3 occurrences"

    # 1 customer disruption → 1*5=5
    _, _, _, _, cd_pen1, total, _ = _calculate_evaluation(100, 100, 100, 0, 0, 0, 1)
    assert cd_pen1 == 5, "customer disruption penalty 5 for 1 occurrence"
    assert abs(total - 75.0) < 0.001, "total reduced by customer disruption"


def test_calculate_evaluation_total_floor_at_zero():
    # Low scores + max penalties → total cannot go negative
    _, _, _, _, _, total, grade = _calculate_evaluation(0, 0, 0, 10, 10, 10, 10)
    assert total == 0.0, "total floored at 0"
    assert grade == "D", "grade D when total is 0"


def test_calculate_evaluation_combined_penalties():
    # q=d=s=100 → base=80, capa=3*2=6, finding=2*3=6; total=80-6-6=68
    base, capa_pen, finding_pen, pf_pen, cd_pen, total, grade = _calculate_evaluation(100, 100, 100, 3, 2)
    assert base == 80.0, "combined base == 80.0"
    assert capa_pen == 6, "combined capa_penalty == 6"
    assert finding_pen == 6, "combined finding_penalty == 6"
    assert pf_pen == 0, "combined premium_freight_penalty == 0"
    assert cd_pen == 0, "combined customer_disruption_penalty == 0"
    assert abs(total - 68.0) < 0.001, "combined total == 68.0"
    assert grade == "B", "combined grade == 'B'"


def test_calculate_evaluation_all_penalties():
    # All penalty types active: capa=3*2=6, finding=2*3=6, premium=2*5=10, disruption=1*5=5
    # base = 100*0.35+100*0.30+100*0.15 = 80; total = 80 - 6 - 6 - 10 - 5 = 53
    base, capa_pen, finding_pen, pf_pen, cd_pen, total, grade = _calculate_evaluation(100, 100, 100, 3, 2, 2, 1)
    assert base == 80.0, "all penalties base == 80.0"
    assert capa_pen == 6, "all penalties capa == 6"
    assert finding_pen == 6, "all penalties finding == 6"
    assert pf_pen == 10, "all penalties premium_freight == 10"
    assert cd_pen == 5, "all penalties customer_disruption == 5"
    assert abs(total - 53.0) < 0.001, "all penalties total == 53.0"
    assert grade == "C", "all penalties grade == 'C'"


# ─── _transition_status ─────────────────────────────────────────────────────

def test_transition_pending_review_approve():
    result = _transition_status("pending_review", "approve")
    assert result == "audit_required", "pending_review + approve -> audit_required"


def test_transition_pending_review_reject():
    result = _transition_status("pending_review", "reject")
    assert result == "rejected", "pending_review + reject -> rejected"


def test_transition_audit_required_confirm_approved():
    result = _transition_status("audit_required", "confirm_approved")
    assert result == "approved", "audit_required + confirm_approved -> approved"


def test_transition_audit_required_reject():
    result = _transition_status("audit_required", "reject")
    assert result == "rejected", "audit_required + reject -> rejected"


def test_transition_approved_suspend():
    result = _transition_status("approved", "suspend")
    assert result == "suspended", "approved + suspend -> suspended"


def test_transition_suspended_reinstate():
    result = _transition_status("suspended", "reinstate")
    assert result == "approved", "suspended + reinstate -> approved"


def test_transition_invalid_action_on_valid_status():
    # 'approve' is not valid from 'approved'
    with pytest.raises(ValueError):
        _transition_status("approved", "approve")


def test_transition_unknown_action_on_valid_status():
    with pytest.raises(ValueError):
        _transition_status("pending_review", "nonexistent")


def test_transition_unknown_status():
    # status not in VALID_TRANSITIONS → treated as empty transitions dict → ValueError
    with pytest.raises(ValueError):
        _transition_status("not_a_status", "approve")


def test_transition_rejected_has_no_valid_actions():
    # rejected is a terminal state with no outgoing transitions
    with pytest.raises(ValueError):
        _transition_status("rejected", "approve")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
