"""FMEA graph utilities shared between frontend logic and backend services."""

from typing import Any


def build_rpn_rows(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Build RPN calculation rows from FMEA graph data.
    One row per FailureCause -> FailureMode -> FailureEffect chain.
    Returns rows with severity, occurrence, detection extracted from correct node types.
    """
    node_map = {n["id"]: n for n in nodes}
    rows: list[dict[str, Any]] = []

    # Find all FailureMode nodes
    failure_modes = [n for n in nodes if n.get("type") == "FailureMode"]

    for fm_node in failure_modes:
        fm_id = fm_node["id"]

        # Find FailureEffects via EFFECT_OF edges (source=FailureMode, target=FailureEffect)
        effect_ids = [
            e["target"] for e in edges
            if e.get("source") == fm_id and e.get("type") == "EFFECT_OF"
        ]

        # Find FailureCauses via CAUSE_OF edges (source=FailureCause, target=FailureMode)
        cause_ids = [
            e["source"] for e in edges
            if e.get("target") == fm_id and e.get("type") == "CAUSE_OF"
        ]

        # Find DetectionControls via DETECTED_BY edges from FailureMode or FailureCauses
        detection_ids = [
            e["target"] for e in edges
            if e.get("source") == fm_id and e.get("type") == "DETECTED_BY"
        ]
        for cid in cause_ids:
            detection_ids.extend([
                e["target"] for e in edges
                if e.get("source") == cid and e.get("type") == "DETECTED_BY"
            ])

        if not cause_ids:
            # Row without cause: use first effect's severity, 0 occurrence, first detection
            effect = node_map.get(effect_ids[0]) if effect_ids else None
            detection = node_map.get(detection_ids[0]) if detection_ids else None
            rows.append({
                "severity": effect.get("severity", 0) if effect else 0,
                "occurrence": 0,
                "detection": detection.get("detection", 0) if detection else 0,
            })
        else:
            for cid in cause_ids:
                cause = node_map.get(cid)
                effect = node_map.get(effect_ids[0]) if effect_ids else None
                detection = node_map.get(detection_ids[0]) if detection_ids else None
                rows.append({
                    "severity": effect.get("severity", 0) if effect else 0,
                    "occurrence": cause.get("occurrence", 0) if cause else 0,
                    "detection": detection.get("detection", 0) if detection else 0,
                })

    return rows
