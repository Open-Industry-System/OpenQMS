"""Pure PFMEA characteristic-to-control-plan initial-row mapping."""

from __future__ import annotations


from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any
from uuid import UUID

from app.schemas.characteristic import Characteristic, CharacteristicSourceRef
from app.services.fmea_characteristics import criteria_with_unit, source_key, validate_characteristics


@dataclass(frozen=True)
class MappingIssue:
    code: str
    node_id: str
    blocking: bool
    message: str


@dataclass(frozen=True)
class MappedCPItem:
    source_ref: CharacteristicSourceRef
    fields: dict[str, str | None]


@dataclass(frozen=True)
class MappingResult:
    items: tuple[MappedCPItem, ...]
    issues: tuple[MappingIssue, ...]


def candidate_key(
    action: str,
    source_ref: CharacteristicSourceRef,
    item_id: UUID | None,
) -> str:
    """Return a stable candidate identity, not an authorization token."""
    payload = json.dumps(
        {
            "action": action,
            "item_id": str(item_id) if item_id is not None else None,
            "source_key": source_key(source_ref),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def derive_cp_items(
    *,
    fmea_id: UUID,
    fmea_type: str,
    graph: dict,
    step_ids: tuple[str, ...],
) -> MappingResult:
    """Map explicitly selected PFMEA steps into independent initial CP rows."""
    if fmea_type != "PFMEA":
        return _blocked("unsupported_fmea_type", "", "Only PFMEA characteristics can seed control-plan rows.")
    if not step_ids:
        return _blocked("empty_step_selection", "", "At least one process step must be selected.")

    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_map = {str(node.get("id")): node for node in nodes if isinstance(node, dict) and node.get("id") is not None}
    selected_steps = _selected_steps(step_ids, node_map)
    if selected_steps is None:
        invalid_step = next(
            step_id
            for step_id in step_ids
            if node_map.get(step_id, {}).get("type") != "ProcessStep"
        )
        return _blocked("invalid_step_selection", invalid_step, "Selected node is not a PFMEA process step.")

    legacy_issues = _legacy_issues(selected_steps, edges, node_map)
    if legacy_issues:
        return MappingResult(items=(), issues=tuple(legacy_issues))

    try:
        validate_characteristics("PFMEA", graph)
    except (TypeError, ValueError):
        return _blocked(
            "invalid_characteristic_graph",
            "",
            "Structured characteristics must have valid PFMEA structural ownership.",
        )

    items: list[MappedCPItem] = []
    issues: list[MappingIssue] = []
    for step in selected_steps:
        step_id = str(step["id"])
        machine_elements = _machine_elements(step_id, edges, node_map)
        for function in _children(step_id, "HAS_FUNCTION", edges, node_map):
            _map_function(
                items=items,
                issues=issues,
                fmea_id=fmea_id,
                step=step,
                function=function,
                work_element=None,
                product_machine_elements=machine_elements,
            )
        for work_element in _children(step_id, "HAS_WORK_ELEMENT", edges, node_map):
            if work_element.get("type") != "ProcessWorkElement":
                continue
            for function in _children(str(work_element["id"]), "HAS_FUNCTION", edges, node_map):
                _map_function(
                    items=items,
                    issues=issues,
                    fmea_id=fmea_id,
                    step=step,
                    function=function,
                    work_element=work_element,
                    product_machine_elements=machine_elements,
                )

    return MappingResult(items=tuple(items), issues=tuple(issues))


def _blocked(code: str, node_id: str, message: str) -> MappingResult:
    return MappingResult(items=(), issues=(MappingIssue(code, node_id, True, message),))


def _selected_steps(step_ids: tuple[str, ...], node_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]] | None:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for step_id in step_ids:
        if step_id in seen:
            continue
        seen.add(step_id)
        step = node_map.get(step_id)
        if step is None or step.get("type") != "ProcessStep":
            return None
        selected.append(step)
    return selected


def _legacy_issues(
    selected_steps: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    node_map: dict[str, dict[str, Any]],
) -> list[MappingIssue]:
    issues: list[MappingIssue] = []
    for step in selected_steps:
        step_id = str(step["id"])
        functions = _children(step_id, "HAS_FUNCTION", edges, node_map)
        for work_element in _children(step_id, "HAS_WORK_ELEMENT", edges, node_map):
            if work_element.get("type") == "ProcessWorkElement":
                functions.extend(_children(str(work_element["id"]), "HAS_FUNCTION", edges, node_map))
        for function in functions:
            if (
                str(function.get("type", "")).endswith("Function")
                and function.get("characteristics") is None
            ):
                issues.append(
                    MappingIssue(
                        "legacy_characteristics_missing",
                        str(function.get("id")),
                        True,
                        "Legacy free-text function data cannot be converted into a structured characteristic.",
                    )
                )
    return issues


def _children(
    source_id: str,
    edge_type: str,
    edges: list[dict[str, Any]],
    node_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("type") != edge_type or str(edge.get("source")) != source_id:
            continue
        child = node_map.get(str(edge.get("target")))
        if child is not None:
            children.append(child)
    return children


def _machine_elements(
    step_id: str,
    edges: list[dict[str, Any]],
    node_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        element
        for element in _children(step_id, "HAS_WORK_ELEMENT", edges, node_map)
        if element.get("type") == "ProcessWorkElement"
        and element.get("classification") == "Machine"
        and isinstance(element.get("name"), str)
        and element["name"].strip()
    ]


def _map_function(
    *,
    items: list[MappedCPItem],
    issues: list[MappingIssue],
    fmea_id: UUID,
    step: dict[str, Any],
    function: dict[str, Any],
    work_element: dict[str, Any] | None,
    product_machine_elements: list[dict[str, Any]],
) -> None:
    function_id = str(function.get("id"))
    characteristics = function.get("characteristics")
    if characteristics is None:
        issues.append(
            MappingIssue(
                "legacy_characteristics_missing",
                function_id,
                True,
                "Legacy free-text function data cannot be converted into a structured characteristic.",
            )
        )
        return

    parsed_characteristics = [Characteristic.model_validate(raw) for raw in characteristics]
    product_equipment = _product_equipment_for(
        function_id=function_id,
        product_machine_elements=product_machine_elements,
        issues=issues,
    ) if any(characteristic.kind == "product" for characteristic in parsed_characteristics) else None
    process_equipment = _process_equipment_for(function_id, work_element, issues) if any(
        characteristic.kind == "process" for characteristic in parsed_characteristics
    ) else None

    for characteristic in parsed_characteristics:
        equipment = product_equipment if characteristic.kind == "product" else process_equipment
        if characteristic.kind == "process" and not characteristic.related_product_characteristic_ids:
            issues.append(
                MappingIssue(
                    "missing_product_relation",
                    function_id,
                    False,
                    "Process characteristic has no related product characteristic.",
                )
            )
        source_ref = CharacteristicSourceRef(
            mapping_version=1,
            fmea_id=fmea_id,
            step_id=str(step["id"]),
            function_id=function_id,
            work_element_id=str(work_element["id"]) if work_element is not None else None,
            characteristic_id=characteristic.id,
        )
        items.append(
            MappedCPItem(
                source_ref=source_ref,
                fields={
                    "step_no": step.get("process_number") or "",
                    "process_name": step.get("name") or "",
                    "equipment": equipment,
                    "product_characteristic": characteristic.name if characteristic.kind == "product" else None,
                    "process_characteristic": characteristic.name if characteristic.kind == "process" else None,
                    "specification_tolerance": criteria_with_unit(characteristic.specification, characteristic.unit),
                    "special_class": characteristic.classification,
                },
            )
        )


def _product_equipment_for(
    *,
    function_id: str,
    product_machine_elements: list[dict[str, Any]],
    issues: list[MappingIssue],
) -> str | None:
    if len(product_machine_elements) == 1:
        return str(product_machine_elements[0]["name"])
    code = "ambiguous_product_equipment" if product_machine_elements else "unresolved_product_equipment"
    issues.append(
        MappingIssue(
            code,
            function_id,
            False,
            "Product characteristic does not have one unambiguous Machine work-element owner.",
        )
    )
    return None


def _process_equipment_for(
    function_id: str,
    work_element: dict[str, Any] | None,
    issues: list[MappingIssue],
) -> str | None:
    if (
        work_element is not None
        and work_element.get("type") == "ProcessWorkElement"
        and work_element.get("classification") == "Machine"
        and isinstance(work_element.get("name"), str)
        and work_element["name"].strip()
    ):
        return str(work_element["name"])
    issues.append(
        MappingIssue(
            "unresolved_process_equipment",
            function_id,
            False,
            "Process characteristic is not owned by a named Machine work element.",
        )
    )
    return None
