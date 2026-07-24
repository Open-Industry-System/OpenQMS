"""8D 状态机细化真值表 + 辅助函数测试（US-E2E-01.3 状态机切片）。"""
import pytest
from app.state_machines.eightd_state import (
    EIGHTD_TRANSITIONS,
    EightDState,
    _linear_next,
    _linear_next_safe,
    can_transition,
    capa_open_clause,
    is_capa_open_value,
)


def test_d7_prevention_no_longer_transitions_directly_to_d8_closure():
    # 回归守卫：D7_PREVENTION→D8_CLOSURE 直连已废除
    assert can_transition(EightDState.D7_PREVENTION, EightDState.D8_CLOSURE) is False


def test_new_forward_chain():
    assert can_transition(EightDState.D7_PREVENTION, EightDState.D7_COMPLETED) is True
    assert can_transition(EightDState.D7_COMPLETED, EightDState.D8_GATE_PENDING) is True
    assert can_transition(EightDState.D8_GATE_PENDING, EightDState.D8_APPROVAL_PENDING) is True
    assert can_transition(EightDState.D8_APPROVAL_PENDING, EightDState.D8_CLOSURE) is True


def test_reject_edge_d8_approval_to_d7_prevention():
    assert can_transition(EightDState.D8_APPROVAL_PENDING, EightDState.D7_PREVENTION) is True


def test_d8_closure_to_archived_unchanged():
    assert can_transition(EightDState.D8_CLOSURE, EightDState.ARCHIVED) is True


@pytest.mark.parametrize("shell_state", [
    EightDState.D7_PREVENTION,
    EightDState.D7_COMPLETED,
    EightDState.D8_GATE_PENDING,
    EightDState.D8_APPROVAL_PENDING,
])
def test_linear_next_raises_on_shell_states(shell_state):
    with pytest.raises(ValueError, match="需显式传 target_state"):
        _linear_next(shell_state)


@pytest.mark.parametrize("current,expected", [
    (EightDState.D1_TEAM, EightDState.D2_DESCRIPTION),
    (EightDState.D2_DESCRIPTION, EightDState.D3_INTERIM),
    (EightDState.D3_INTERIM, EightDState.D4_ROOT_CAUSE),
    (EightDState.D4_ROOT_CAUSE, EightDState.D5_CORRECTION),
    (EightDState.D5_CORRECTION, EightDState.D6_VERIFICATION),
    (EightDState.D6_VERIFICATION, EightDState.D7_PREVENTION),
    (EightDState.D8_CLOSURE, EightDState.ARCHIVED),
])
def test_linear_next_for_linear_states(current, expected):
    assert _linear_next(current) == expected


def test_linear_next_safe_returns_none_for_shell_states():
    assert _linear_next_safe(EightDState.D7_PREVENTION.value) is None
    assert _linear_next_safe(EightDState.D8_APPROVAL_PENDING.value) is None


def test_linear_next_safe_returns_archived_for_d8_closure():
    # 关键：D8_CLOSURE→ARCHIVED 线性，权限层用此解析归档边
    assert _linear_next_safe(EightDState.D8_CLOSURE.value) == EightDState.ARCHIVED


@pytest.mark.parametrize("status,expected_open", [
    (EightDState.D7_COMPLETED.value, True),
    (EightDState.D8_GATE_PENDING.value, True),
    (EightDState.D8_APPROVAL_PENDING.value, True),
    (EightDState.D7_PREVENTION.value, True),
    (EightDState.D8_CLOSURE.value, False),
    (EightDState.ARCHIVED.value, False),
])
def test_is_capa_open_value(status, expected_open):
    assert is_capa_open_value(status) is expected_open


def test_capa_open_clause_compiles_to_not_in():
    from sqlalchemy import Column, String
    from sqlalchemy.dialects import postgresql
    col = Column("status", String(20))
    expr = capa_open_clause(col)
    compiled = str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "NOT IN" in compiled
    assert "D8_CLOSURE" in compiled
    assert "ARCHIVED" in compiled
