import json
import re
from typing import Any

from app.schemas.characteristic import CharacteristicSourceRef


_FUNCTION_OWNERS = {"ProcessStep", "ProcessWorkElement", "System", "Subsystem", "Component"}


def source_key(ref: CharacteristicSourceRef) -> str:
    """Return the stable identity for rows derived from one FMEA characteristic."""
    return json.dumps(
        {
            "fmea_id": str(ref.fmea_id),
            "step_id": ref.step_id,
            "function_id": ref.function_id,
            "characteristic_id": str(ref.characteristic_id),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _single_owner(
    function_id: str,
    owner_ids_by_function: dict[str, list[str]],
    node_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    owner_ids = owner_ids_by_function.get(function_id, [])
    if len(owner_ids) != 1:
        raise ValueError("characteristic function must have exactly one structural owner")
    owner = node_map.get(owner_ids[0])
    if owner is None or owner.get("type") not in _FUNCTION_OWNERS:
        raise ValueError("characteristic function has an invalid structural owner")
    return owner


def _pfmea_step_id(
    owner: dict[str, Any],
    work_element_parent_ids: dict[str, list[str]],
    node_map: dict[str, dict[str, Any]],
) -> str:
    if owner.get("type") == "ProcessStep":
        return str(owner["id"])
    if owner.get("type") != "ProcessWorkElement":
        raise ValueError("PFMEA characteristic must belong to a process step or work element")
    parent_ids = work_element_parent_ids.get(str(owner["id"]), [])
    if len(parent_ids) != 1:
        raise ValueError("PFMEA work element must have exactly one process step")
    step = node_map.get(parent_ids[0])
    if step is None or step.get("type") != "ProcessStep":
        raise ValueError("PFMEA work element must be owned by a process step")
    return str(step["id"])


def validate_characteristics(fmea_type: str, graph: dict) -> None:
    """Validate explicitly supplied structured characteristic collections.

    Legacy nodes without the ``characteristics`` key are deliberately skipped.
    Validation derives FMEA semantics from actual structural ownership edges, not
    from function type names, because DFMEA reuses the Process* function types.
    """
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_map = {str(node.get("id")): node for node in nodes if node.get("id") is not None}
    owner_ids_by_function: dict[str, list[str]] = {}
    work_element_parent_ids: dict[str, list[str]] = {}
    for edge in edges:
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        if edge.get("type") == "HAS_FUNCTION":
            owner_ids_by_function.setdefault(target, []).append(source)
        elif edge.get("type") == "HAS_WORK_ELEMENT":
            work_element_parent_ids.setdefault(target, []).append(source)

    characteristics_by_id: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    for node in nodes:
        if "characteristics" not in node or node.get("characteristics") is None:
            continue
        characteristics = node["characteristics"]
        if not isinstance(characteristics, list):
            raise ValueError("characteristics must be a list when supplied")
        if not str(node.get("type") or "").endswith("Function"):
            raise ValueError("characteristics may only be attached to function nodes")

        function_id = str(node.get("id"))
        owner = _single_owner(function_id, owner_ids_by_function, node_map)
        if fmea_type == "PFMEA":
            step_id = _pfmea_step_id(owner, work_element_parent_ids, node_map)
            expected_kind = "product" if owner.get("type") == "ProcessStep" else "process"
        elif fmea_type == "DFMEA":
            if owner.get("type") not in {"System", "Subsystem", "Component"}:
                raise ValueError("DFMEA characteristic must belong to a design structure function")
            step_id = None
            expected_kind = "product"
        else:
            raise ValueError("characteristics require a PFMEA or DFMEA document")

        for characteristic in characteristics:
            if not isinstance(characteristic, dict):
                raise ValueError("characteristic must be an object")
            characteristic_id = characteristic.get("id")
            characteristic_key = str(characteristic_id)
            if characteristic_id is None or characteristic_key in characteristics_by_id:
                raise ValueError("characteristic id must be unique within the FMEA document")
            if not isinstance(characteristic.get("name"), str) or not characteristic["name"].strip():
                raise ValueError("characteristic name must not be empty")
            if characteristic.get("kind") != expected_kind:
                raise ValueError("characteristic kind does not match its structural ownership")
            related_ids = characteristic.get("related_product_characteristic_ids", [])
            if not isinstance(related_ids, list):
                raise ValueError("related_product_characteristic_ids must be a list")
            if expected_kind != "process" and related_ids:
                raise ValueError("only PFMEA process characteristics may reference products")
            record = {
                "characteristic": characteristic,
                "function_id": function_id,
                "step_id": step_id,
                "expected_kind": expected_kind,
            }
            characteristics_by_id[characteristic_key] = record
            records.append(record)

    for record in records:
        if record["expected_kind"] != "process":
            continue
        for product_id in record["characteristic"].get("related_product_characteristic_ids", []):
            product = characteristics_by_id.get(str(product_id))
            if product is None:
                raise ValueError("related product characteristic does not exist in this FMEA")
            if product["expected_kind"] != "product":
                raise ValueError("related characteristic must be a product characteristic")
            if product["step_id"] != record["step_id"]:
                raise ValueError("related product characteristic must belong to the same process step")

def criteria_with_unit(specification: str | None, unit: str | None) -> str | None:
    """Project into the existing criteria column; units never supply criteria.

    Preserve already-unit-bearing text without interpreting quantities or
    converting units. Letter-unit boundaries also allow compact numeric forms
    such as 3N, while avoiding mistaking m inside mm or s inside mm/s.
    """
    if specification is None or not specification.strip() or not unit or not unit.strip():
        return specification
    unit = unit.strip()
    left = r"(?<![^\W\d])(?<!/)" if unit[0].isalnum() else ""
    right = r"(?![\w/])" if unit[-1].isalnum() else ""
    if re.search(left + re.escape(unit) + right, specification):
        return specification
    return f"{specification.rstrip()} {unit}"
