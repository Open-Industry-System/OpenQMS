"""
Unit tests for supplier_service pure functions.
Run: python tests/test_supplier.py

The app config requires SECRET_KEY to be non-default; we set a dummy value so the
import chain resolves without a real .env file.
"""
import sys
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")

# Allow running from the backend directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.supplier_service import _calculate_evaluation, _transition_status

# ─── helpers ───────────────────────────────────────────────────────────────

_passed = 0
_failed = 0


def check(name: str, condition: bool) -> None:
    global _passed, _failed
    if condition:
        print(f"  PASS  {name}")
        _passed += 1
    else:
        print(f"  FAIL  {name}")
        _failed += 1


def check_raises(name: str, exc_type, fn) -> None:
    global _passed, _failed
    try:
        fn()
        print(f"  FAIL  {name}  (no exception raised)")
        _failed += 1
    except exc_type:
        print(f"  PASS  {name}")
        _passed += 1
    except Exception as e:
        print(f"  FAIL  {name}  (wrong exception: {type(e).__name__}: {e})")
        _failed += 1


# ─── _calculate_evaluation ──────────────────────────────────────────────────

def test_calculate_evaluation_perfect_score():
    base, capa_pen, finding_pen, total, grade = _calculate_evaluation(100, 100, 100, 0, 0)
    # base = 100*0.35 + 100*0.30 + 100*0.15 = 80.0
    check("perfect: base == 80.0", base == 80.0)
    check("perfect: capa_penalty == 0", capa_pen == 0)
    check("perfect: finding_penalty == 0", finding_pen == 0)
    check("perfect: total == 80.0", total == 80.0)
    check("perfect: grade == 'A'", grade == "A")


def test_calculate_evaluation_grade_a():
    # Grade A threshold is now >= 72 (90% of max 80).
    # A perfect score (100/100/100, 0 CAPAs, 0 findings) gives total=80 → grade A.
    _, _, _, total, grade = _calculate_evaluation(100, 100, 100, 0, 0)
    check("grade A for perfect total=80.0", grade == "A")

    # Boundary at exactly 72: q=d=s=90 → base=90*0.80=72
    _, _, _, total72, grade72 = _calculate_evaluation(90, 90, 90, 0, 0)
    check("grade A boundary: total == 72.0", abs(total72 - 72.0) < 0.001)
    check("grade A boundary: grade == 'A'", grade72 == "A")


def test_calculate_evaluation_grade_b_boundary():
    # Grade B threshold is now >= 60 (75% of max 80).
    # Boundary at exactly 60: q=d=s=75 → base=75*0.80=60.0 → grade B
    base, capa_pen, finding_pen, total, grade = _calculate_evaluation(75, 75, 75, 0, 0)
    check("grade B boundary: total == 60.0", abs(total - 60.0) < 0.001)
    check("grade B boundary: grade == 'B'", grade == "B")

    # Just below A threshold (total=71.9...) → grade B
    # q=d=s=89.9 → base=89.9*0.80=71.92 → grade B
    _, _, _, total_below_a, grade_below_a = _calculate_evaluation(89.9, 89.9, 89.9, 0, 0)
    check("grade B just below A threshold", grade_below_a == "B")


def test_calculate_evaluation_grade_c():
    # Grade C threshold is now >= 48 (60% of max 80).
    # Boundary at exactly 48: q=d=s=60 → base=60*0.80=48.0 → grade C
    _, _, _, total, grade = _calculate_evaluation(60, 60, 60, 0, 0)
    check("grade C boundary: total == 48.0", abs(total - 48.0) < 0.001)
    check("grade C boundary: grade == 'C'", grade == "C")

    # Just below B threshold (total=59.9...) → grade C
    _, _, _, total_below_b, grade_below_b = _calculate_evaluation(74.9, 74.9, 74.9, 0, 0)
    check("grade C just below B threshold", grade_below_b == "C")


def test_calculate_evaluation_grade_d():
    # Grade D is now < 48.
    # q=d=s=50 → base = 50*0.80 = 40.0 → grade D
    _, _, _, total, grade = _calculate_evaluation(50, 50, 50, 0, 0)
    check("grade D: total == 40.0", abs(total - 40.0) < 0.001)
    check("grade D: grade == 'D'", grade == "D")


def test_calculate_evaluation_capa_cap():
    # 6 CAPAs → 6*2=12, capped at 10
    _, capa_pen, _, _, _ = _calculate_evaluation(100, 100, 100, 6, 0)
    check("capa cap at 10 for 6 CAPAs", capa_pen == 10)

    # exactly 5 CAPAs → 5*2=10 (at cap)
    _, capa_pen5, _, _, _ = _calculate_evaluation(100, 100, 100, 5, 0)
    check("capa cap at 10 for 5 CAPAs", capa_pen5 == 10)

    # 4 CAPAs → 4*2=8 (under cap)
    _, capa_pen4, _, _, _ = _calculate_evaluation(100, 100, 100, 4, 0)
    check("capa penalty 8 for 4 CAPAs", capa_pen4 == 8)


def test_calculate_evaluation_finding_cap():
    # 4 findings → 4*3=12, capped at 10
    _, _, finding_pen, _, _ = _calculate_evaluation(100, 100, 100, 0, 4)
    check("finding cap at 10 for 4 findings", finding_pen == 10)

    # exactly 3 findings → 3*3=9 (under cap but close)
    _, _, finding_pen3, _, _ = _calculate_evaluation(100, 100, 100, 0, 3)
    check("finding penalty 9 for 3 findings", finding_pen3 == 9)

    # 1 finding → 1*3=3
    _, _, finding_pen1, _, _ = _calculate_evaluation(100, 100, 100, 0, 1)
    check("finding penalty 3 for 1 finding", finding_pen1 == 3)


def test_calculate_evaluation_total_floor_at_zero():
    # Low scores + max penalties → total cannot go negative
    _, _, _, total, grade = _calculate_evaluation(0, 0, 0, 10, 10)
    check("total floored at 0", total == 0.0)
    check("grade D when total is 0", grade == "D")


def test_calculate_evaluation_combined_penalties():
    # q=d=s=100 → base=80, capa=3*2=6, finding=2*3=6; total=80-6-6=68
    base, capa_pen, finding_pen, total, grade = _calculate_evaluation(100, 100, 100, 3, 2)
    check("combined base == 80.0", base == 80.0)
    check("combined capa_penalty == 6", capa_pen == 6)
    check("combined finding_penalty == 6", finding_pen == 6)
    check("combined total == 68.0", abs(total - 68.0) < 0.001)
    check("combined grade == 'B'", grade == "B")


# ─── _transition_status ─────────────────────────────────────────────────────

def test_transition_pending_review_approve():
    result = _transition_status("pending_review", "approve")
    check("pending_review + approve → audit_required", result == "audit_required")


def test_transition_pending_review_reject():
    result = _transition_status("pending_review", "reject")
    check("pending_review + reject → rejected", result == "rejected")


def test_transition_audit_required_confirm_approved():
    result = _transition_status("audit_required", "confirm_approved")
    check("audit_required + confirm_approved → approved", result == "approved")


def test_transition_audit_required_reject():
    result = _transition_status("audit_required", "reject")
    check("audit_required + reject → rejected", result == "rejected")


def test_transition_approved_suspend():
    result = _transition_status("approved", "suspend")
    check("approved + suspend → suspended", result == "suspended")


def test_transition_suspended_reinstate():
    result = _transition_status("suspended", "reinstate")
    check("suspended + reinstate → approved", result == "approved")


def test_transition_invalid_action_on_valid_status():
    # 'approve' is not valid from 'approved'
    check_raises(
        "approved + approve raises ValueError",
        ValueError,
        lambda: _transition_status("approved", "approve"),
    )


def test_transition_unknown_action_on_valid_status():
    check_raises(
        "pending_review + nonexistent raises ValueError",
        ValueError,
        lambda: _transition_status("pending_review", "nonexistent"),
    )


def test_transition_unknown_status():
    # status not in VALID_TRANSITIONS → treated as empty transitions dict → ValueError
    check_raises(
        "unknown status raises ValueError",
        ValueError,
        lambda: _transition_status("not_a_status", "approve"),
    )


def test_transition_rejected_has_no_valid_actions():
    # rejected is a terminal state with no outgoing transitions
    check_raises(
        "rejected + any action raises ValueError",
        ValueError,
        lambda: _transition_status("rejected", "approve"),
    )


# ─── run ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== _calculate_evaluation ===")
    test_calculate_evaluation_perfect_score()
    test_calculate_evaluation_grade_a()
    test_calculate_evaluation_grade_b_boundary()
    test_calculate_evaluation_grade_c()
    test_calculate_evaluation_grade_d()
    test_calculate_evaluation_capa_cap()
    test_calculate_evaluation_finding_cap()
    test_calculate_evaluation_total_floor_at_zero()
    test_calculate_evaluation_combined_penalties()

    print("\n=== _transition_status ===")
    test_transition_pending_review_approve()
    test_transition_pending_review_reject()
    test_transition_audit_required_confirm_approved()
    test_transition_audit_required_reject()
    test_transition_approved_suspend()
    test_transition_suspended_reinstate()
    test_transition_invalid_action_on_valid_status()
    test_transition_unknown_action_on_valid_status()
    test_transition_unknown_status()
    test_transition_rejected_has_no_valid_actions()

    print(f"\n{'='*40}")
    print(f"Results: {_passed} passed, {_failed} failed")
    if _failed:
        sys.exit(1)
