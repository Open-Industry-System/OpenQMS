"""Rule-based validation engine for Control Plans.

All rules are pure functions: (items, fmea_graph) -> (list[ValidationFinding], list[failed_rule_id]).
No database access. Fast synchronous execution.

Key design: finding_hash uses stable business keys (source_fmea_node_id or step_no),
NOT volatile item UUIDs that change on every CP save (update_control_plan deletes +
recreates items).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationFinding:
    rule_id: str
    severity: str
    category: str
    title: str
    description: str
    stable_key: str = ""
    key_content: str = ""
    item_id: str | None = None


_PLACEHOLDER_METHODS = {"", "见sop", "见 sop", "无", "待定", "tbd", "暂无", "暂不", "n/a", "na"}
_PLACEHOLDER_REACTIONS = {"", "无", "待定", "tbd", "暂无", "暂不", "n/a", "na"}


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _is_placeholder(val: str | None, placeholders: set[str]) -> bool:
    return _norm(val) in placeholders


def _stable_key(item: Any) -> str:
    """Business-stable identifier: FMEA node id + characteristic, else step_no + characteristic."""
    base = item.source_fmea_node_id or item.step_no or ""
    char = item.product_characteristic or item.process_characteristic or ""
    if char:
        return f"{base}|{char}"
    # Fallback for items without characteristic text
    order = str(getattr(item, "sort_order", 0))
    return f"{base}|#{order}"



# ─── Rule R001: Control method coverage ────────────────────────────────────

def rule_r001_control_method(items: list[Any]) -> tuple[list[ValidationFinding], list[str]]:
    findings = []
    for item in items:
        if _is_placeholder(item.control_method, _PLACEHOLDER_METHODS):
            sk = _stable_key(item)
            findings.append(ValidationFinding(
                rule_id="R001",
                severity="error",
                category="completeness",
                title="控制方法缺失",
                description=f"工序 {item.step_no or '?'}/{item.process_name or '?'} 的控制方法为空或仅含占位符",
                stable_key=sk,
                key_content="control_method_empty",
                item_id=str(item.item_id),
            ))
    return findings, []


# ─── Rule R002: Reaction plan completeness ─────────────────────────────────

def rule_r002_reaction_plan(items: list[Any]) -> tuple[list[ValidationFinding], list[str]]:
    findings = []
    for item in items:
        if _is_placeholder(item.reaction_plan, _PLACEHOLDER_REACTIONS):
            sk = _stable_key(item)
            findings.append(ValidationFinding(
                rule_id="R002",
                severity="error",
                category="completeness",
                title="反应计划缺失",
                description=f"工序 {item.step_no or '?'}/{item.process_name or '?'} 的反应计划为空或仅含占位符",
                stable_key=sk,
                key_content="reaction_plan_empty",
                item_id=str(item.item_id),
            ))
    return findings, []


# ─── Rule R003: Process step consistency with FMEA ─────────────────────────

def rule_r003_fmea_consistency(items: list[Any], fmea_graph: dict | None) -> tuple[list[ValidationFinding], list[str]]:
    if not fmea_graph:
        return [], []

    nodes = fmea_graph.get("nodes", [])
    node_map = {n.get("id"): n for n in nodes if n.get("id")}
    findings = []

    for item in items:
        if not item.source_fmea_node_id:
            continue
        node = node_map.get(item.source_fmea_node_id)
        if node is None:
            findings.append(ValidationFinding(
                rule_id="R003",
                severity="warning",
                category="consistency",
                title="FMEA源工序已删除",
                description=f"工序 {item.step_no or '?'} 关联的FMEA节点已不存在",
                stable_key=_stable_key(item),
                key_content="node_deleted",
                item_id=str(item.item_id),
            ))
            continue

        fmea_step_no = str(node.get("process_number") or "")
        fmea_name = str(node.get("name") or "")
        cp_step_no = str(item.step_no or "")
        cp_name = str(item.process_name or "")

        if fmea_step_no != cp_step_no or fmea_name != cp_name:
            findings.append(ValidationFinding(
                rule_id="R003",
                severity="warning",
                category="consistency",
                title="工序与FMEA不一致",
                description=f"工序号/名称与FMEA源不同: CP=({cp_step_no}/{cp_name}) vs FMEA=({fmea_step_no}/{fmea_name})",
                stable_key=_stable_key(item),
                key_content="mismatch",
                item_id=str(item.item_id),
            ))

    return findings, []


# ─── Rule R004: Special class annotation check ─────────────────────────────

def rule_r004_special_class(items: list[Any]) -> tuple[list[ValidationFinding], list[str]]:
    findings = []
    for item in items:
        sc = _norm(item.special_class)
        if sc not in ("cc", "sc"):
            continue
        missing = []
        if _is_placeholder(item.evaluation_method, _PLACEHOLDER_METHODS):
            missing.append("evaluation_method")
        if _is_placeholder(item.control_method, _PLACEHOLDER_METHODS):
            missing.append("control_method")
        if missing:
            sk = _stable_key(item)
            findings.append(ValidationFinding(
                rule_id="R004",
                severity="warning",
                category="coverage",
                title="特殊特性控制不完整",
                description=f"工序 {item.step_no or '?'} 标记为 {item.special_class}，但{','.join(missing)}为空",
                stable_key=sk,
                key_content=f"special_class_{sc}",
                item_id=str(item.item_id),
            ))
    return findings, []


# ─── Rule registry ─────────────────────────────────────────────────────────

RULE_REGISTRY: list = [
    ("R001", rule_r001_control_method),
    ("R002", rule_r002_reaction_plan),
    ("R003", rule_r003_fmea_consistency),
    ("R004", rule_r004_special_class),
]


def run_all_rules(cp: Any, items: list[Any], fmea_graph: dict | None) -> tuple[list[ValidationFinding], list[str]]:
    """Execute all rules and return (merged_findings, failed_rule_ids)."""
    all_findings: list[ValidationFinding] = []
    failed_rules: list[str] = []

    for rule_id, rule_fn in RULE_REGISTRY:
        try:
            if rule_id == "R003":
                findings, _ = rule_fn(items, fmea_graph)
            else:
                findings, _ = rule_fn(items)
            all_findings.extend(findings)
        except Exception:
            failed_rules.append(rule_id)

    return all_findings, failed_rules
