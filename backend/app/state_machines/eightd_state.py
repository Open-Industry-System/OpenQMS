from enum import Enum


class EightDState(str, Enum):
    D1_TEAM = "D1_TEAM"
    D2_DESCRIPTION = "D2_DESCRIPTION"
    D3_INTERIM = "D3_INTERIM"
    D4_ROOT_CAUSE = "D4_ROOT_CAUSE"
    D5_CORRECTION = "D5_CORRECTION"
    D6_VERIFICATION = "D6_VERIFICATION"
    D7_PREVENTION = "D7_PREVENTION"
    D7_COMPLETED = "D7_COMPLETED"
    D8_GATE_PENDING = "D8_GATE_PENDING"
    D8_APPROVAL_PENDING = "D8_APPROVAL_PENDING"
    D8_CLOSURE = "D8_CLOSURE"
    ARCHIVED = "ARCHIVED"


EIGHTD_TRANSITIONS: dict[EightDState, list[EightDState]] = {
    EightDState.D1_TEAM: [EightDState.D2_DESCRIPTION],
    EightDState.D2_DESCRIPTION: [EightDState.D3_INTERIM, EightDState.D1_TEAM],
    EightDState.D3_INTERIM: [EightDState.D4_ROOT_CAUSE],
    EightDState.D4_ROOT_CAUSE: [EightDState.D5_CORRECTION, EightDState.D3_INTERIM],
    EightDState.D5_CORRECTION: [EightDState.D6_VERIFICATION],
    EightDState.D6_VERIFICATION: [EightDState.D7_PREVENTION, EightDState.D5_CORRECTION],
    EightDState.D7_PREVENTION: [EightDState.D7_COMPLETED],
    EightDState.D7_COMPLETED: [EightDState.D8_GATE_PENDING],
    EightDState.D8_GATE_PENDING: [EightDState.D8_APPROVAL_PENDING],
    EightDState.D8_APPROVAL_PENDING: [EightDState.D8_CLOSURE, EightDState.D7_PREVENTION],
    EightDState.D8_CLOSURE: [EightDState.ARCHIVED],
    EightDState.ARCHIVED: [],
}


def can_transition(current: EightDState, target: EightDState) -> bool:
    return target in EIGHTD_TRANSITIONS.get(current, [])


# 线性推进表：仅 D1→D6→D7_PREVENTION 与 D8_CLOSURE→ARCHIVED。
# 壳/分支状态（D7_PREVENTION/D7_COMPLETED/D8_GATE_PENDING/D8_APPROVAL_PENDING）不在表内，
# 强制 advance_capa 显式传 target_state（_linear_next raise）。
_LINEAR_NEXT: dict[EightDState, EightDState] = {
    EightDState.D1_TEAM: EightDState.D2_DESCRIPTION,
    EightDState.D2_DESCRIPTION: EightDState.D3_INTERIM,
    EightDState.D3_INTERIM: EightDState.D4_ROOT_CAUSE,
    EightDState.D4_ROOT_CAUSE: EightDState.D5_CORRECTION,
    EightDState.D5_CORRECTION: EightDState.D6_VERIFICATION,
    EightDState.D6_VERIFICATION: EightDState.D7_PREVENTION,
    EightDState.D8_CLOSURE: EightDState.ARCHIVED,
}


def _linear_next(current: EightDState) -> EightDState:
    """服务层用：线性推进下一态。壳/分支状态 raise（强制显式 target_state）。"""
    if current not in _LINEAR_NEXT:
        raise ValueError(f"状态 {current.value} 需显式传 target_state，不可线性推进")
    return _LINEAR_NEXT[current]


def _linear_next_safe(status: str) -> EightDState | None:
    """权限层用：解析 target_state=None 时的实际 target。
    无线性边的状态返回 None（落 EDIT 默认分支）；D8_CLOSURE 返回 ARCHIVED（命中归档 APPROVE 边）。
    与 _linear_next 共用 _LINEAR_NEXT 表，但不 raise。"""
    try:
        current = EightDState(status)
    except ValueError:
        return None
    return _LINEAR_NEXT.get(current)


_CLOSED_STATES = {EightDState.D8_CLOSURE, EightDState.ARCHIVED}


def is_capa_open_value(status: str | EightDState) -> bool:
    """Python 值判断：D8_CLOSURE/ARCHIVED → False，其余（含 3 新状态）→ True。"""
    return EightDState(status) not in _CLOSED_STATES


def capa_open_clause(column):
    """SQLAlchemy 查询表达式：column NOT IN ('D8_CLOSURE','ARCHIVED')。
    用法：query.where(capa_open_clause(CAPAEightD.status))"""
    return column.notin_([EightDState.D8_CLOSURE.value, EightDState.ARCHIVED.value])


EIGHTD_STEP_LABELS = {
    EightDState.D1_TEAM: "D1 团队组建",
    EightDState.D2_DESCRIPTION: "D2 问题描述",
    EightDState.D3_INTERIM: "D3 临时措施",
    EightDState.D4_ROOT_CAUSE: "D4 根因分析",
    EightDState.D5_CORRECTION: "D5 永久措施",
    EightDState.D6_VERIFICATION: "D6 实施验证",
    EightDState.D7_PREVENTION: "D7 预防复发",
    EightDState.D7_COMPLETED: "D7 已完成",
    EightDState.D8_GATE_PENDING: "D8 文档门禁",
    EightDState.D8_APPROVAL_PENDING: "D8 待审批",
    EightDState.D8_CLOSURE: "D8 关闭",
    EightDState.ARCHIVED: "已归档",
}
