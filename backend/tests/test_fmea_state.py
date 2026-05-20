import pytest
from app.state_machines.fmea_state import compute_ap, compute_rpn, can_transition, FMEAState


class TestComputeAP:
    """Test AIAG-VDA 2019 AP matrix (ported from frontend calculateAP)."""

    # Severity 9-10
    def test_s10_o4_d1_returns_H(self):
        assert compute_ap(10, 4, 1) == "H"

    def test_s10_o3_d7_returns_H(self):
        assert compute_ap(10, 3, 7) == "H"

    def test_s10_o3_d4_returns_M(self):
        assert compute_ap(10, 3, 4) == "M"

    def test_s10_o3_d3_returns_L(self):
        assert compute_ap(10, 3, 3) == "L"

    def test_s10_o1_d1_returns_L(self):
        assert compute_ap(10, 1, 1) == "L"

    # Severity 7-8
    def test_s8_o8_d1_returns_H(self):
        assert compute_ap(8, 8, 1) == "H"

    def test_s8_o6_d2_returns_H(self):
        assert compute_ap(8, 6, 2) == "H"

    def test_s8_o6_d1_returns_M(self):
        assert compute_ap(8, 6, 1) == "M"

    def test_s8_o4_d7_returns_H(self):
        assert compute_ap(8, 4, 7) == "H"

    def test_s8_o4_d6_returns_M(self):
        assert compute_ap(8, 4, 6) == "M"

    def test_s8_o2_d5_returns_M(self):
        assert compute_ap(8, 2, 5) == "M"

    def test_s8_o2_d4_returns_L(self):
        assert compute_ap(8, 2, 4) == "L"

    # Severity 4-6
    def test_s6_o8_d5_returns_H(self):
        assert compute_ap(6, 8, 5) == "H"

    def test_s6_o8_d4_returns_M(self):
        assert compute_ap(6, 8, 4) == "M"

    def test_s6_o6_d2_returns_M(self):
        assert compute_ap(6, 6, 2) == "M"

    def test_s6_o6_d1_returns_L(self):
        assert compute_ap(6, 6, 1) == "L"

    # Severity 1-3
    def test_s3_o8_d5_returns_M(self):
        assert compute_ap(3, 8, 5) == "M"

    def test_s3_o8_d4_returns_L(self):
        assert compute_ap(3, 8, 4) == "L"

    def test_s3_o1_d1_returns_L(self):
        assert compute_ap(3, 1, 1) == "L"

    # Invalid input
    def test_out_of_range_returns_empty(self):
        assert compute_ap(11, 5, 5) == ""
        assert compute_ap(5, 0, 5) == ""
        assert compute_ap(5, 5, 11) == ""


class TestComputeRPN:
    def test_rpn_calculation(self):
        assert compute_rpn(8, 4, 3) == 96
        assert compute_rpn(10, 10, 10) == 1000
        assert compute_rpn(0, 0, 0) == 0


class TestCanTransition:
    def test_valid_transitions(self):
        assert can_transition(FMEAState.DRAFT, FMEAState.IN_REVIEW) is True
        assert can_transition(FMEAState.IN_REVIEW, FMEAState.APPROVED) is True

    def test_invalid_transitions(self):
        assert can_transition(FMEAState.DRAFT, FMEAState.APPROVED) is False
        assert can_transition(FMEAState.ARCHIVED, FMEAState.DRAFT) is False
