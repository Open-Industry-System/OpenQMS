from enum import Enum


class EightDState(str, Enum):
    D1_TEAM = "D1_TEAM"
    D2_DESCRIPTION = "D2_DESCRIPTION"
    D3_INTERIM = "D3_INTERIM"
    D4_ROOT_CAUSE = "D4_ROOT_CAUSE"
    D5_CORRECTION = "D5_CORRECTION"
    D6_VERIFICATION = "D6_VERIFICATION"
    D7_PREVENTION = "D7_PREVENTION"
    D8_CLOSURE = "D8_CLOSURE"
    ARCHIVED = "ARCHIVED"


EIGHTD_TRANSITIONS: dict[EightDState, list[EightDState]] = {
    EightDState.D1_TEAM: [EightDState.D2_DESCRIPTION],
    EightDState.D2_DESCRIPTION: [EightDState.D3_INTERIM, EightDState.D1_TEAM],
    EightDState.D3_INTERIM: [EightDState.D4_ROOT_CAUSE],
    EightDState.D4_ROOT_CAUSE: [EightDState.D5_CORRECTION, EightDState.D3_INTERIM],
    EightDState.D5_CORRECTION: [EightDState.D6_VERIFICATION],
    EightDState.D6_VERIFICATION: [EightDState.D7_PREVENTION, EightDState.D5_CORRECTION],
    EightDState.D7_PREVENTION: [EightDState.D8_CLOSURE],
    EightDState.D8_CLOSURE: [EightDState.ARCHIVED],
    EightDState.ARCHIVED: [],
}


def can_transition(current: EightDState, target: EightDState) -> bool:
    return target in EIGHTD_TRANSITIONS.get(current, [])


EIGHTD_STEP_LABELS = {
    EightDState.D1_TEAM: "D1 团队组建",
    EightDState.D2_DESCRIPTION: "D2 问题描述",
    EightDState.D3_INTERIM: "D3 临时措施",
    EightDState.D4_ROOT_CAUSE: "D4 根因分析",
    EightDState.D5_CORRECTION: "D5 永久措施",
    EightDState.D6_VERIFICATION: "D6 实施验证",
    EightDState.D7_PREVENTION: "D7 预防复发",
    EightDState.D8_CLOSURE: "D8 关闭",
    EightDState.ARCHIVED: "已归档",
}
