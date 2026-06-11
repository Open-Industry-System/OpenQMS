"""Tests for supplier risk rule engine — 2 tests per rule (20 total)."""
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.supplier_risk.rule_engine import (
    SupplierRiskInput,
    RuleResult,
    rule_r01_ppm,
    rule_r02_acceptance_rate_decline,
    rule_r03_consecutive_rejection,
    rule_r04_scar_overdue,
    rule_r05_scar_frequent,
    rule_r06_delivery_score_decline,
    rule_r07_grade_downgrade,
    rule_r08_cert_expiry,
    rule_r09_score_decline,
    rule_r10_safety_defect,
    run_all_rules,
    RULE_REGISTRY,
)


# ── Helpers ──────────────────────────────────────────────────────────


def make_input(**overrides):
    defaults = dict(
        supplier=SimpleNamespace(supplier_id=uuid.uuid4(), name="Test Supplier"),
        inspections=[],
        scars=[],
        evaluations=[],
        certifications=[],
    )
    defaults.update(overrides)
    return SupplierRiskInput(**defaults)


def make_config(rule_id, thresholds=None, enabled=True, weight=None, category=None):
    return SimpleNamespace(
        rule_id=rule_id,
        enabled=enabled,
        thresholds=thresholds or {},
        weight=weight,
        category=category,
    )


# ── R01  PPM超标 ────────────────────────────────────────────────────


class TestR01PPM:
    def test_ppm_exceeds_limit(self):
        data = make_input(inspections=[
            SimpleNamespace(
                inspection_result="rejected", defect_qty=50, lot_qty=1000,
                inspection_date=date.today(), status="judged", product_line_code=None,
            ),
            SimpleNamespace(
                inspection_result="accepted", defect_qty=0, lot_qty=1000,
                inspection_date=date.today(), status="judged", product_line_code=None,
            ),
        ])
        result = rule_r01_ppm(data, {"ppm_limit": 1000, "window_days": 90})
        assert result.triggered is True
        assert result.category == "quality"
        assert result.score > 0

    def test_ppm_within_limit(self):
        data = make_input(inspections=[
            SimpleNamespace(
                inspection_result="accepted", defect_qty=0, lot_qty=1000,
                inspection_date=date.today(), status="judged", product_line_code=None,
            ),
        ])
        result = rule_r01_ppm(data, {"ppm_limit": 1000, "window_days": 90})
        assert result.triggered is False
        assert result.score == 0


# ── R02  批次合格率下降 ──────────────────────────────────────────────


class TestR02AcceptanceRate:
    def test_acceptance_rate_below_min(self):
        today = date.today()
        # 4 rejected, 1 accepted in current window → rate = 0.2
        insps = []
        for i in range(4):
            insps.append(SimpleNamespace(
                inspection_result="rejected", defect_qty=0, lot_qty=100,
                inspection_date=today - timedelta(days=i),
                status="judged", product_line_code=None,
            ))
        insps.append(SimpleNamespace(
            inspection_result="accepted", defect_qty=0, lot_qty=100,
            inspection_date=today - timedelta(days=5),
            status="judged", product_line_code=None,
        ))
        data = make_input(inspections=insps)
        result = rule_r02_acceptance_rate_decline(data, {
            "acceptance_rate_min": 0.9, "decline_ratio": 0.1,
            "window_days": 90, "compare_window_days": 180,
        })
        assert result.triggered is True
        assert result.category == "quality"

    def test_acceptance_rate_normal(self):
        today = date.today()
        insps = [
            SimpleNamespace(
                inspection_result="accepted", defect_qty=0, lot_qty=100,
                inspection_date=today - timedelta(days=i),
                status="judged", product_line_code=None,
            )
            for i in range(5)
        ]
        data = make_input(inspections=insps)
        result = rule_r02_acceptance_rate_decline(data, {
            "acceptance_rate_min": 0.9, "decline_ratio": 0.1,
            "window_days": 90, "compare_window_days": 180,
        })
        assert result.triggered is False


# ── R03  连续拒收 ────────────────────────────────────────────────────


class TestR03ConsecutiveRejection:
    def test_consecutive_rejection_triggered(self):
        today = date.today()
        insps = [
            SimpleNamespace(
                inspection_result="rejected", defect_qty=5, lot_qty=100,
                inspection_date=today - timedelta(days=i),
                status="judged", product_line_code=None,
            )
            for i in range(4)
        ]
        data = make_input(inspections=insps)
        result = rule_r03_consecutive_rejection(data, {"consecutive_batches": 3, "batch_limit": 10})
        assert result.triggered is True
        assert result.score > 0

    def test_consecutive_rejection_not_triggered(self):
        today = date.today()
        insps = [
            # Most recent is accepted, breaks the streak
            SimpleNamespace(
                inspection_result="accepted", defect_qty=0, lot_qty=100,
                inspection_date=today, status="judged", product_line_code=None,
            ),
            SimpleNamespace(
                inspection_result="rejected", defect_qty=5, lot_qty=100,
                inspection_date=today - timedelta(days=1), status="judged", product_line_code=None,
            ),
            SimpleNamespace(
                inspection_result="rejected", defect_qty=5, lot_qty=100,
                inspection_date=today - timedelta(days=2), status="judged", product_line_code=None,
            ),
        ]
        data = make_input(inspections=insps)
        result = rule_r03_consecutive_rejection(data, {"consecutive_batches": 3, "batch_limit": 10})
        assert result.triggered is False


# ── R04  SCAR超期未关闭 ──────────────────────────────────────────────


class TestR04SCAROverdue:
    def test_scar_overdue_triggered(self):
        data = make_input(scars=[
            SimpleNamespace(
                status="open",
                issued_date=date.today() - timedelta(days=45),
                supplier_id=uuid.uuid4(), product_line_code=None,
            ),
        ])
        result = rule_r04_scar_overdue(data, {"open_days_limit": 30})
        assert result.triggered is True
        assert result.score > 0

    def test_scar_no_overdue(self):
        data = make_input(scars=[
            SimpleNamespace(
                status="open",
                issued_date=date.today() - timedelta(days=10),
                supplier_id=uuid.uuid4(), product_line_code=None,
            ),
        ])
        result = rule_r04_scar_overdue(data, {"open_days_limit": 30})
        assert result.triggered is False


# ── R05  SCAR频发 ────────────────────────────────────────────────────


class TestR05SCARFrequent:
    def test_scar_frequent_triggered(self):
        today = date.today()
        scars = [
            SimpleNamespace(
                status="open",
                issued_date=today - timedelta(days=i * 10),
                supplier_id=uuid.uuid4(), product_line_code=None,
            )
            for i in range(5)
        ]
        data = make_input(scars=scars)
        result = rule_r05_scar_frequent(data, {"scar_count_limit": 3, "window_days": 90})
        assert result.triggered is True
        assert result.score > 0

    def test_scar_frequent_not_triggered(self):
        today = date.today()
        scars = [
            SimpleNamespace(
                status="open",
                issued_date=today - timedelta(days=i * 10),
                supplier_id=uuid.uuid4(), product_line_code=None,
            )
            for i in range(2)
        ]
        data = make_input(scars=scars)
        result = rule_r05_scar_frequent(data, {"scar_count_limit": 3, "window_days": 90})
        assert result.triggered is False


# ── R06  交付准时率下降 ──────────────────────────────────────────────


class TestR06DeliveryScore:
    def test_delivery_score_below_min(self):
        data = make_input(evaluations=[
            SimpleNamespace(delivery_score=50, total_score=60, grade="C",
                            supplier_id=uuid.uuid4(), created_at=date.today()),
        ])
        result = rule_r06_delivery_score_decline(data, {"delivery_score_min": 70, "decline_ratio": 0.15})
        assert result.triggered is True
        assert result.category == "delivery"

    def test_delivery_score_normal(self):
        data = make_input(evaluations=[
            SimpleNamespace(delivery_score=85, total_score=90, grade="A",
                            supplier_id=uuid.uuid4(), created_at=date.today()),
        ])
        result = rule_r06_delivery_score_decline(data, {"delivery_score_min": 70, "decline_ratio": 0.15})
        assert result.triggered is False


# ── R07  评级降级 ────────────────────────────────────────────────────


class TestR07GradeDowngrade:
    def test_grade_downgrade_triggered(self):
        data = make_input(evaluations=[
            SimpleNamespace(delivery_score=60, total_score=60, grade="C",
                            supplier_id=uuid.uuid4(), created_at=date.today()),
            SimpleNamespace(delivery_score=90, total_score=90, grade="A",
                            supplier_id=uuid.uuid4(), created_at=date.today() - timedelta(days=30)),
        ])
        result = rule_r07_grade_downgrade(data, {"from_grades": ["A", "B"], "to_grades": ["C", "D"]})
        assert result.triggered is True
        assert result.score == 80

    def test_grade_no_downgrade(self):
        data = make_input(evaluations=[
            SimpleNamespace(delivery_score=90, total_score=90, grade="A",
                            supplier_id=uuid.uuid4(), created_at=date.today()),
            SimpleNamespace(delivery_score=85, total_score=85, grade="B",
                            supplier_id=uuid.uuid4(), created_at=date.today() - timedelta(days=30)),
        ])
        result = rule_r07_grade_downgrade(data, {"from_grades": ["A", "B"], "to_grades": ["C", "D"]})
        assert result.triggered is False


# ── R08  证书即将过期 ────────────────────────────────────────────────


class TestR08CertExpiry:
    def test_cert_near_expiry_triggered(self):
        data = make_input(certifications=[
            SimpleNamespace(
                expiry_date=date.today() + timedelta(days=20),
                supplier_id=uuid.uuid4(),
            ),
        ])
        result = rule_r08_cert_expiry(data, {"warning_days": [90, 60, 30]})
        assert result.triggered is True
        assert result.score == 100  # <30 days

    def test_cert_no_expiry_risk(self):
        data = make_input(certifications=[
            SimpleNamespace(
                expiry_date=date.today() + timedelta(days=120),
                supplier_id=uuid.uuid4(),
            ),
        ])
        result = rule_r08_cert_expiry(data, {"warning_days": [90, 60, 30]})
        assert result.triggered is False


# ── R09  评价分数下滑 ────────────────────────────────────────────────


class TestR09ScoreDecline:
    def test_score_decline_triggered(self):
        data = make_input(evaluations=[
            SimpleNamespace(delivery_score=60, total_score=60, grade="C",
                            supplier_id=uuid.uuid4(), created_at=date.today()),
            SimpleNamespace(delivery_score=90, total_score=90, grade="A",
                            supplier_id=uuid.uuid4(), created_at=date.today() - timedelta(days=30)),
        ])
        result = rule_r09_score_decline(data, {"score_decline_limit": 15})
        assert result.triggered is True
        assert result.score > 0

    def test_score_decline_not_triggered(self):
        data = make_input(evaluations=[
            SimpleNamespace(delivery_score=88, total_score=88, grade="A",
                            supplier_id=uuid.uuid4(), created_at=date.today()),
            SimpleNamespace(delivery_score=90, total_score=90, grade="A",
                            supplier_id=uuid.uuid4(), created_at=date.today() - timedelta(days=30)),
        ])
        result = rule_r09_score_decline(data, {"score_decline_limit": 15})
        assert result.triggered is False


# ── R10  安全缺陷检测 ────────────────────────────────────────────────


class TestR10SafetyDefect:
    def test_safety_defect_triggered(self):
        data = make_input(inspections=[
            SimpleNamespace(
                inspection_result="rejected", defect_qty=5, lot_qty=100,
                inspection_date=date.today(), status="judged",
                defect_description="发现安全特性不合格",
                product_line_code=None,
            ),
        ])
        result = rule_r10_safety_defect(data, {"keywords": ["安全", "安全特性", "safety"]})
        assert result.triggered is True
        assert result.score == 100
        assert result.critical is True

    def test_safety_defect_not_triggered(self):
        data = make_input(inspections=[
            SimpleNamespace(
                inspection_result="rejected", defect_qty=5, lot_qty=100,
                inspection_date=date.today(), status="judged",
                defect_description="尺寸偏差",
                product_line_code=None,
            ),
        ])
        result = rule_r10_safety_defect(data, {"keywords": ["安全", "安全特性", "safety"]})
        assert result.triggered is False
        assert result.critical is False


# ── run_all_rules ────────────────────────────────────────────────────


class TestRunAllRules:
    def test_run_all_rules_enabled(self):
        data = make_input()
        configs = [make_config(rid, thresholds={}) for rid, *_ in RULE_REGISTRY]
        results, failed = run_all_rules(data, configs)
        assert len(results) == len(RULE_REGISTRY)
        assert failed == []

    def test_run_all_rules_disabled_and_missing(self):
        data = make_input()
        configs = [
            make_config("R01", enabled=False),
            make_config("R99", enabled=True),  # does not exist
        ]
        results, failed = run_all_rules(data, configs)
        assert len(results) == 0
        assert "R99" in failed


# ── Scorer tests ────────────────────────────────────────────────────────

from app.services.supplier_risk.scorer import calculate_risk_score, RiskScore


def _make_default_configs():
    """All 10 rules enabled with default weights."""
    configs = [
        SimpleNamespace(rule_id="R01", weight=15.0, category="quality", enabled=True),
        SimpleNamespace(rule_id="R02", weight=12.0, category="quality", enabled=True),
        SimpleNamespace(rule_id="R03", weight=18.0, category="quality", enabled=True),
        SimpleNamespace(rule_id="R04", weight=10.0, category="quality", enabled=True),
        SimpleNamespace(rule_id="R05", weight=12.0, category="quality", enabled=True),
        SimpleNamespace(rule_id="R06", weight=12.0, category="delivery", enabled=True),
        SimpleNamespace(rule_id="R07", weight=10.0, category="delivery", enabled=True),
        SimpleNamespace(rule_id="R08", weight=8.0, category="compliance", enabled=True),
        SimpleNamespace(rule_id="R09", weight=8.0, category="compliance", enabled=True),
        SimpleNamespace(rule_id="R10", weight=15.0, category="compliance", enabled=True),
    ]
    return configs


def test_scorer_all_low_risk():
    """No rules triggered → score 0, level low."""
    configs = _make_default_configs()
    results = [RuleResult(rule_id=f"R{i:02d}", triggered=False, score=0, detail="", category=cat)
               for i, cat in [(1, "quality"), (2, "quality"), (3, "quality"), (4, "quality"), (5, "quality"),
                              (6, "delivery"), (7, "delivery"), (8, "compliance"), (9, "compliance"), (10, "compliance")]]
    score = calculate_risk_score(results, configs)
    assert score.risk_score == 0.0
    assert score.risk_level == "low"


def test_scorer_quality_triggered():
    """Only quality rules triggered → moderate score."""
    configs = _make_default_configs()
    results = [
        RuleResult(rule_id="R01", triggered=True, score=50, detail="", category="quality"),
        RuleResult(rule_id="R02", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R03", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R04", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R05", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R06", triggered=False, score=0, detail="", category="delivery"),
        RuleResult(rule_id="R07", triggered=False, score=0, detail="", category="delivery"),
        RuleResult(rule_id="R08", triggered=False, score=0, detail="", category="compliance"),
        RuleResult(rule_id="R09", triggered=False, score=0, detail="", category="compliance"),
        RuleResult(rule_id="R10", triggered=False, score=0, detail="", category="compliance"),
    ]
    score = calculate_risk_score(results, configs)
    # Quality: 50*15 / (15+12+18+10+12) = 750/67 = 11.19
    # Overall: 11.19 * 0.50 = 5.60
    assert score.risk_score > 0
    assert score.quality_score > 0
    assert score.delivery_score == 0
    assert score.compliance_score == 0
    assert score.risk_level == "low"  # 5.6 is still low


def test_scorer_multiple_categories():
    """Multiple categories triggered → higher score."""
    configs = _make_default_configs()
    results = [
        RuleResult(rule_id="R01", triggered=True, score=80, detail="", category="quality"),
        RuleResult(rule_id="R02", triggered=True, score=60, detail="", category="quality"),
        RuleResult(rule_id="R03", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R04", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R05", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R06", triggered=True, score=70, detail="", category="delivery"),
        RuleResult(rule_id="R07", triggered=False, score=0, detail="", category="delivery"),
        RuleResult(rule_id="R08", triggered=True, score=60, detail="", category="compliance"),
        RuleResult(rule_id="R09", triggered=False, score=0, detail="", category="compliance"),
        RuleResult(rule_id="R10", triggered=False, score=0, detail="", category="compliance", critical=False),
    ]
    score = calculate_risk_score(results, configs)
    assert score.risk_score > 25  # Multiple categories push score up
    assert score.quality_score > 0
    assert score.delivery_score > 0
    assert score.compliance_score > 0


def test_scorer_critical_bypass():
    """R10 critical bypass → score >= 61 (high) even if math says lower."""
    configs = _make_default_configs()
    results = [
        RuleResult(rule_id="R01", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R02", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R03", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R04", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R05", triggered=False, score=0, detail="", category="quality"),
        RuleResult(rule_id="R06", triggered=False, score=0, detail="", category="delivery"),
        RuleResult(rule_id="R07", triggered=False, score=0, detail="", category="delivery"),
        RuleResult(rule_id="R08", triggered=False, score=0, detail="", category="compliance"),
        RuleResult(rule_id="R09", triggered=False, score=0, detail="", category="compliance"),
        RuleResult(rule_id="R10", triggered=True, score=100, detail="安全缺陷", category="compliance", critical=True),
    ]
    score = calculate_risk_score(results, configs)
    # Without bypass: compliance = 100*15/31 * 0.20 = ~9.68
    # With bypass: max(9.68, 61) = 61
    assert score.risk_score >= 61.0
    assert score.risk_level in ("high", "critical")
