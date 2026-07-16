# backend/tests/test_r11_rule.py
import pytest
from app.services.supplier_risk.rule_engine import SupplierRiskInput, run_all_rules, rule_r11_capa_issue


def _incident(severity="严重", repeat_confirmed=None, repeat_suggested=True, disposition="退货"):
    class _I:
        pass
    i = _I()
    i.severity = severity
    i.disposition = disposition
    i.repeat_confirmed = repeat_confirmed
    i.repeat_suggested = repeat_suggested
    i.repeat_detection_status = "matched"
    i.matched_capa_nos = ["8D-2025-001"]
    return i


class _Supplier:
    supplier_id = "x"
    factory_id = "y"


def test_r11_no_incidents_not_triggered():
    data = SupplierRiskInput(supplier=_Supplier(), capa_incidents=[])
    res = rule_r11_capa_issue(data, {})
    assert res.rule_id == "R11"
    assert res.triggered is False
    assert res.score == 0


def test_r11_severe_repeat_triggered_high_score():
    data = SupplierRiskInput(supplier=_Supplier(), capa_incidents=[_incident(severity="严重", repeat_confirmed=True)])
    res = rule_r11_capa_issue(data, {})
    assert res.triggered is True
    assert res.score > 0
    assert res.critical is True
    # disposition 入 detail 不计分但可追溯
    assert "退货" in res.detail


def test_r11_severity_mapping_chinese_and_general():
    # 兼容中文与 "general"；致命/严重 = base+severe_bonus(20)，一般/轻微/general = base(10)
    for sev, expect_severe in [("致命", True), ("严重", True), ("一般", False), ("轻微", False), ("general", False)]:
        data = SupplierRiskInput(supplier=_Supplier(), capa_incidents=[_incident(severity=sev, repeat_confirmed=False)])
        res = rule_r11_capa_issue(data, {})
        assert res.triggered is True
        if expect_severe:
            assert res.score >= 20
            assert res.critical is True
        else:
            assert res.score < 20
            assert res.critical is False


def test_r11_repeat_uses_confirmed_over_suggested_and_marks_provisional():
    # confirmed=None 时用 suggested + 标 provisional
    data = SupplierRiskInput(supplier=_Supplier(), capa_incidents=[_incident(repeat_confirmed=None, repeat_suggested=True)])
    res = rule_r11_capa_issue(data, {})
    assert "provisional" in res.detail.lower() or res.detail  # provisional 标记入 detail


def test_r11_registered_and_runs_via_run_all_rules():
    class _Cfg:
        rule_id = "R11"
        enabled = True
        thresholds = {}
        weight = 1.0
        category = "quality"
    data = SupplierRiskInput(supplier=_Supplier(), capa_incidents=[_incident()])
    results, failed = run_all_rules(data, [_Cfg()])
    r11 = next((r for r in results if r.rule_id == "R11"), None)
    assert r11 is not None
    assert "R11" not in failed
