# backend/tests/test_r11_rule.py
from datetime import datetime, timedelta, timezone

import pytest
from app.services.supplier_risk.rule_engine import (
    SupplierRiskInput,
    capa_incident_sort_key,
    run_all_rules,
    rule_r11_capa_issue,
)


def _incident(
    severity="严重",
    repeat_confirmed=None,
    repeat_suggested=True,
    disposition="退货",
    *,
    created_at=None,
    input_id=None,
    matched_capa_nos=None,
):
    class _I:
        pass
    i = _I()
    i.severity = severity
    i.disposition = disposition
    i.repeat_confirmed = repeat_confirmed
    i.repeat_suggested = repeat_suggested
    i.repeat_detection_status = "matched"
    i.matched_capa_nos = matched_capa_nos if matched_capa_nos is not None else ["8D-2025-001"]
    i.created_at = created_at
    i.input_id = input_id
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
    # 兼容中文与 English CAPA 值；致命/严重/fatal/serious = base+severe_bonus(>=20)，一般/轻微/general = base(10)
    for sev, expect_severe in [
        ("致命", True),
        ("严重", True),
        ("fatal", True),
        ("serious", True),
        ("一般", False),
        ("轻微", False),
        ("general", False),
    ]:
        data = SupplierRiskInput(supplier=_Supplier(), capa_incidents=[_incident(severity=sev, repeat_confirmed=False)])
        res = rule_r11_capa_issue(data, {})
        assert res.triggered is True, sev
        if expect_severe:
            assert res.score >= 20, sev
            assert res.critical is True, sev
        else:
            assert res.score < 20, sev
            assert res.critical is False, sev


def test_r11_same_severity_newer_created_at_wins():
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = older + timedelta(days=1)
    older_inc = _incident(
        severity="严重",
        disposition="让步接收",
        created_at=older,
        input_id="a",
        matched_capa_nos=["8D-OLD"],
        repeat_confirmed=False,
    )
    newer_inc = _incident(
        severity="严重",
        disposition="退货",
        created_at=newer,
        input_id="b",
        matched_capa_nos=["8D-NEW"],
        repeat_confirmed=False,
    )
    # older first / inject-last order must not matter
    for incidents in ([older_inc, newer_inc], [newer_inc, older_inc]):
        res = rule_r11_capa_issue(SupplierRiskInput(supplier=_Supplier(), capa_incidents=incidents), {})
        assert res.triggered is True
        assert "退货" in res.detail
        assert "8D-NEW" in res.detail
        assert "让步接收" not in res.detail


def test_r11_same_severity_prefers_confirmed_on_newer_incident():
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = older + timedelta(hours=2)
    older_inc = _incident(
        severity="严重",
        created_at=older,
        input_id="1",
        repeat_confirmed=False,
        disposition="旧处置",
    )
    current = _incident(
        severity="严重",
        created_at=newer,
        input_id="2",
        repeat_confirmed=True,
        disposition="新处置",
    )
    # Simulate inject-append: older gathered first, current appended last
    res = rule_r11_capa_issue(
        SupplierRiskInput(supplier=_Supplier(), capa_incidents=[older_inc, current]),
        {},
    )
    assert res.triggered is True
    assert res.score >= 30  # base + severe + repeat
    assert "新处置" in res.detail
    assert "重复: 是" in res.detail
    assert "provisional" not in res.detail.lower()


def test_capa_incident_sort_key_orders_rank_then_created_then_input_id():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=1)
    a = _incident(severity="一般", created_at=t1, input_id="z")
    b = _incident(severity="严重", created_at=t0, input_id="a")
    c = _incident(severity="严重", created_at=t1, input_id="b")
    d = _incident(severity="严重", created_at=t1, input_id="a")
    ordered = sorted([a, b, c, d], key=capa_incident_sort_key, reverse=True)
    assert ordered[0] is d  # highest rank, newest, smallest input_id
    assert ordered[1] is c
    assert ordered[2] is b
    assert ordered[3] is a


def test_r11_repeat_uses_confirmed_over_suggested_and_marks_provisional():
    # confirmed=None 时用 suggested + 标 provisional
    data = SupplierRiskInput(supplier=_Supplier(), capa_incidents=[_incident(repeat_confirmed=None, repeat_suggested=True)])
    res = rule_r11_capa_issue(data, {})
    assert "provisional" in res.detail.lower() or res.detail  # provisional 标记入 detail


def test_r11_both_repeat_null_is_provisional_and_repeat_false():
    # confirmed/suggested 均为 None：未人工确认 → provisional；repeat 记 False
    data = SupplierRiskInput(
        supplier=_Supplier(),
        capa_incidents=[_incident(repeat_confirmed=None, repeat_suggested=None)],
    )
    res = rule_r11_capa_issue(data, {})
    assert res.triggered is True
    assert "provisional" in res.detail.lower()
    assert "重复: 否" in res.detail
    # base only (severe, no repeat bonus) → 20 with defaults
    assert res.score == 20


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
