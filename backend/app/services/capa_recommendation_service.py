# backend/app/services/capa_recommendation_service.py
"""D4/D5 recommendation logic for CAPA 8D reports.

Pure functions (no DB access) mirroring get_d7_recommendations pattern.
"""
from __future__ import annotations

from typing import Any

from app.utils.text import extract_keywords


def get_d4_recommendations(
    capa_data: dict[str, Any],
    fmea_docs: list[dict[str, Any]],
    allowed_product_lines: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Compute D4 root cause recommendations for a CAPA.

    Args:
        capa_data: dict with d2_description, d3_interim, fmea_ref_id, fmea_node_id, product_line_code
        fmea_docs: list of dicts with fmea_id, document_no, graph_data
        allowed_product_lines: user's accessible product line codes

    Returns:
        List of recommendation dicts matching D4Recommendation schema.
    """
    recommendations: list[dict[str, Any]] = []
    keywords = extract_keywords(capa_data.get("d2_description", ""))
    if not keywords:
        return recommendations

    # Split into linked FMEA and other FMEAs
    linked_fmea_id = capa_data.get("fmea_ref_id")
    linked_fmea = None
    other_fmeas: list[dict[str, Any]] = []

    for doc in fmea_docs:
        if doc["fmea_id"] == linked_fmea_id:
            linked_fmea = doc
        else:
            other_fmeas.append(doc)

    seen_keys: set[tuple[str | None, str]] = set()

    # --- Strategy A: Linked FMEA matching ---
    if linked_fmea and linked_fmea.get("graph_data"):
        linked_results = _match_linked_fmea_d4(
            linked_fmea, capa_data, keywords,
        )
        for rec in linked_results:
            key = (rec.get("failure_cause_node_id"), rec.get("failure_cause_name"))
            if key not in seen_keys:
                seen_keys.add(key)
                recommendations.append(rec)

    # --- Strategy B: Cross-FMEA keyword matching ---
    cross_results = _match_cross_fmea_d4(other_fmeas, keywords, seen_keys)
    recommendations.extend(cross_results)

    # --- Strategy C: Rule engine fallback ---
    if not recommendations:
        rule_results = _rule_engine_d4(capa_data)
        recommendations.extend(rule_results)

    return recommendations


def _match_linked_fmea_d4(
    fmea_doc: dict[str, Any],
    capa_data: dict[str, Any],
    keywords: list[str],
) -> list[dict[str, Any]]:
    """Match within the linked FMEA graph."""
    graph = fmea_doc["graph_data"]
    node_map = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])

    forward_edges: dict[str, list[tuple[str, str]]] = {}
    for e in edges:
        forward_edges.setdefault(e["source"], []).append((e["target"], e["type"]))

    reverse_edges: dict[str, list[tuple[str, str]]] = {}
    for e in edges:
        reverse_edges.setdefault(e["target"], []).append((e["source"], e["type"]))

    target_node_id = capa_data.get("fmea_node_id")
    target_node = node_map.get(target_node_id) if target_node_id else None

    # Resolve to FailureMode IDs
    failure_mode_ids: list[str] = []

    if target_node:
        ntype = target_node["type"]
        if ntype == "FailureCause":
            for tgt, etype in forward_edges.get(target_node_id, []):
                if etype == "CAUSE_OF" and node_map.get(tgt, {}).get("type") == "FailureMode":
                    failure_mode_ids.append(tgt)
        elif ntype == "FailureMode":
            failure_mode_ids.append(target_node_id)
        elif ntype in ("Function", "ProcessStepFunction", "ProcessItemFunction", "ProcessWorkElementFunction"):
            for tgt, etype in forward_edges.get(target_node_id, []):
                if etype == "HAS_FAILURE_MODE" and node_map.get(tgt, {}).get("type") == "FailureMode":
                    failure_mode_ids.append(tgt)
    else:
        # No node ID — search by D2 keywords against both FailureMode and FailureCause
        for node in graph.get("nodes", []):
            if node["type"] == "FailureMode":
                name = node.get("name", "")
                desc = node.get("description", "")
                if any(kw in name or kw in desc for kw in keywords):
                    failure_mode_ids.append(node["id"])
            elif node["type"] == "FailureCause":
                name = node.get("name", "")
                desc = node.get("description", "")
                if any(kw in name or kw in desc for kw in keywords):
                    # Find parent FailureMode via CAUSE_OF forward edge
                    for tgt, etype in forward_edges.get(node["id"], []):
                        if etype == "CAUSE_OF" and node_map.get(tgt, {}).get("type") == "FailureMode":
                            if tgt not in failure_mode_ids:
                                failure_mode_ids.append(tgt)

    # For each FailureMode, find FailureCauses and match keywords
    results: list[dict[str, Any]] = []
    for fm_id in failure_mode_ids:
        fm_node = node_map.get(fm_id, {})
        cause_ids = [
            src for src, etype in reverse_edges.get(fm_id, [])
            if etype == "CAUSE_OF" and node_map.get(src, {}).get("type") == "FailureCause"
        ]
        for cause_id in cause_ids:
            cause_node = node_map.get(cause_id, {})
            cause_name = cause_node.get("name", "")
            cause_desc = cause_node.get("description", "")
            matched_kws = [kw for kw in keywords if kw in cause_name or kw in cause_desc]
            if matched_kws or not target_node_id:
                results.append({
                    "failure_cause_node_id": cause_id,
                    "failure_cause_name": cause_name,
                    "failure_cause_desc": cause_desc or None,
                    "failure_mode_node_id": fm_id,
                    "failure_mode_name": fm_node.get("name"),
                    "fmea_document_no": fmea_doc.get("document_no"),
                    "fmea_id": str(fmea_doc["fmea_id"]),
                    "match_source": "linked",
                    "match_reason": "关联 FMEA 失效原因",
                    "related_d2_keywords": matched_kws,
                    "confidence": min(0.5 + 0.1 * len(matched_kws), 0.9),
                })

    # If no FailureCause matched but FailureMode was found, still return FM-level match
    if not results and failure_mode_ids:
        for fm_id in failure_mode_ids:
            fm_node = node_map.get(fm_id, {})
            name = fm_node.get("name", "")
            matched_kws = [kw for kw in keywords if kw in name]
            if matched_kws:
                results.append({
                    "failure_cause_node_id": None,
                    "failure_cause_name": name,
                    "failure_cause_desc": fm_node.get("description"),
                    "failure_mode_node_id": fm_id,
                    "failure_mode_name": name,
                    "fmea_document_no": fmea_doc.get("document_no"),
                    "fmea_id": str(fmea_doc["fmea_id"]),
                    "match_source": "linked",
                    "match_reason": "关联 FMEA 失效模式",
                    "related_d2_keywords": matched_kws,
                    "confidence": 0.4,
                })

    return results


def _match_cross_fmea_d4(
    fmea_docs: list[dict[str, Any]],
    keywords: list[str],
    seen_keys: set[tuple[str | None, str]],
) -> list[dict[str, Any]]:
    """Match across other FMEAs by keyword substring."""
    results: list[dict[str, Any]] = []

    for doc in fmea_docs:
        graph = doc.get("graph_data")
        if not graph:
            continue

        node_map = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])

        # Build reverse CAUSE_OF index: FailureMode -> [FailureCause]
        reverse_cause: dict[str, list[str]] = {}
        for e in edges:
            if e["type"] == "CAUSE_OF":
                reverse_cause.setdefault(e["target"], []).append(e["source"])

        for node in graph.get("nodes", []):
            if node["type"] != "FailureCause":
                continue
            name = node.get("name", "")
            desc = node.get("description", "")
            matched_kws = [kw for kw in keywords if kw in name or kw in desc]
            if not matched_kws:
                continue

            key = (node["id"], name)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Find parent FailureMode
            fm_id = None
            fm_name = None
            for e in edges:
                if e["source"] == node["id"] and e["type"] == "CAUSE_OF":
                    fm = node_map.get(e["target"])
                    if fm and fm.get("type") == "FailureMode":
                        fm_id = fm["id"]
                        fm_name = fm.get("name")
                        break

            results.append({
                "failure_cause_node_id": node["id"],
                "failure_cause_name": name,
                "failure_cause_desc": desc or None,
                "failure_mode_node_id": fm_id,
                "failure_mode_name": fm_name,
                "fmea_document_no": doc.get("document_no"),
                "fmea_id": str(doc["fmea_id"]),
                "match_source": "keyword",
                "match_reason": "相似失效原因",
                "related_d2_keywords": matched_kws,
                "confidence": min(0.3 + 0.1 * len(matched_kws), 0.8),
            })

    # Sort by match count, cap at 5
    results.sort(key=lambda r: len(r.get("related_d2_keywords", [])), reverse=True)
    return results[:5]


def _rule_engine_d4(capa_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Rule engine fallback — generic root cause suggestions from D2 description."""
    from app.services.recommendation_service import RuleEngine

    engine = RuleEngine()
    d2 = capa_data.get("d2_description", "")
    result = engine.evaluate("failure_cause", {"input_text": d2, "failure_mode": d2})

    suggestions = []
    for s in result.suggestions:
        suggestions.append({
            "failure_cause_node_id": None,
            "failure_cause_name": s.name,
            "failure_cause_desc": s.explanation,
            "failure_mode_node_id": None,
            "failure_mode_name": None,
            "fmea_document_no": None,
            "fmea_id": None,
            "match_source": "rule",
            "match_reason": "规则引擎推断",
            "related_d2_keywords": [],
            "confidence": s.confidence * 0.5,  # lower confidence for generic
        })
    return suggestions


def get_d5_recommendations(
    capa_data: dict[str, Any],
    fmea_docs: list[dict[str, Any]],
    allowed_product_lines: list[str] | None = None,
) -> dict[str, Any]:
    """Compute D5 corrective action recommendations for a CAPA.

    Args:
        capa_data: dict with d4_root_cause, d2_description, fmea_ref_id, fmea_node_id, product_line_code
        fmea_docs: list of dicts with fmea_id, document_no, graph_data
        allowed_product_lines: user's accessible product line codes

    Returns:
        Dict with existing_controls and general_suggestions lists.
    """
    d4_text = capa_data.get("d4_root_cause", "")
    keywords = extract_keywords(d4_text)
    if not keywords:
        keywords = extract_keywords(capa_data.get("d2_description", ""))

    existing_controls = _match_existing_controls(capa_data, fmea_docs, keywords)
    general_suggestions = _generate_general_suggestions(capa_data, fmea_docs)

    # Map "检测措施" -> "探测措施" for consistency
    for s in general_suggestions:
        if s["category"] == "检测措施":
            s["category"] = "探测措施"

    return {
        "existing_controls": existing_controls,
        "general_suggestions": general_suggestions,
    }


def _match_existing_controls(
    capa_data: dict[str, Any],
    fmea_docs: list[dict[str, Any]],
    keywords: list[str],
) -> list[dict[str, Any]]:
    """Find PreventionControl/DetectionControl nodes matching D4 keywords."""
    controls: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    linked_fmea_id = capa_data.get("fmea_ref_id")
    linked_fmea = None
    other_fmeas: list[dict[str, Any]] = []

    for doc in fmea_docs:
        if doc["fmea_id"] == linked_fmea_id:
            linked_fmea = doc
        else:
            other_fmeas.append(doc)

    # Process linked FMEA first, then others
    fmea_queue = []
    if linked_fmea and linked_fmea.get("graph_data"):
        fmea_queue.append(("linked", linked_fmea))
    for doc in other_fmeas:
        if doc.get("graph_data"):
            fmea_queue.append(("keyword", doc))

    for match_source, doc in fmea_queue:
        graph = doc["graph_data"]
        node_map = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])

        reverse_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            reverse_edges.setdefault(e["target"], []).append((e["source"], e["type"]))

        forward_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            forward_edges.setdefault(e["source"], []).append((e["target"], e["type"]))

        # Find FailureCause nodes matching keywords
        matched_causes: list[tuple[str, dict]] = []
        for node in graph.get("nodes", []):
            if node["type"] != "FailureCause":
                continue
            name = node.get("name", "")
            desc = node.get("description", "")
            if any(kw in name or kw in desc for kw in keywords):
                matched_causes.append((node["id"], node))

        for cause_id, cause_node in matched_causes:
            # Find parent FailureMode
            fm_id = None
            fm_name = None
            for tgt, etype in forward_edges.get(cause_id, []):
                if etype == "CAUSE_OF":
                    fm = node_map.get(tgt)
                    if fm and fm.get("type") == "FailureMode":
                        fm_id = fm["id"]
                        fm_name = fm.get("name")
                        break

            # Path 1: FailureCause --PREVENTED_BY--> PreventionControl
            for tgt, etype in forward_edges.get(cause_id, []):
                if etype == "PREVENTED_BY":
                    ctrl = node_map.get(tgt)
                    if ctrl and ctrl.get("type") == "PreventionControl":
                        key = (tgt, "prevention")
                        if key not in seen:
                            seen.add(key)
                            controls.append({
                                "failure_mode_node_id": fm_id,
                                "failure_mode_name": fm_name,
                                "failure_cause_node_id": cause_id,
                                "failure_cause_name": cause_node.get("name"),
                                "control_node_id": tgt,
                                "control_name": ctrl.get("name"),
                                "control_type": "prevention",
                                "match_source": match_source,
                                "match_reason": "FMEA 预防措施",
                                "fmea_id": str(doc["fmea_id"]),
                                "fmea_document_no": doc.get("document_no"),
                            })

            # Path 2: FailureCause --DETECTED_BY--> DetectionControl
            for tgt, etype in forward_edges.get(cause_id, []):
                if etype == "DETECTED_BY":
                    ctrl = node_map.get(tgt)
                    if ctrl and ctrl.get("type") == "DetectionControl":
                        key = (tgt, "detection")
                        if key not in seen:
                            seen.add(key)
                            controls.append({
                                "failure_mode_node_id": fm_id,
                                "failure_mode_name": fm_name,
                                "failure_cause_node_id": cause_id,
                                "failure_cause_name": cause_node.get("name"),
                                "control_node_id": tgt,
                                "control_name": ctrl.get("name"),
                                "control_type": "detection",
                                "match_source": match_source,
                                "match_reason": "FMEA 探测措施（原因级）",
                                "fmea_id": str(doc["fmea_id"]),
                                "fmea_document_no": doc.get("document_no"),
                            })

            # Path 3: FailureMode --DETECTED_BY--> DetectionControl
            if fm_id:
                for tgt, etype in forward_edges.get(fm_id, []):
                    if etype == "DETECTED_BY":
                        ctrl = node_map.get(tgt)
                        if ctrl and ctrl.get("type") == "DetectionControl":
                            key = (tgt, "detection")
                            if key not in seen:
                                seen.add(key)
                                controls.append({
                                    "failure_mode_node_id": fm_id,
                                    "failure_mode_name": fm_name,
                                    "failure_cause_node_id": cause_id,
                                    "failure_cause_name": cause_node.get("name"),
                                    "control_node_id": tgt,
                                    "control_name": ctrl.get("name"),
                                    "control_type": "detection",
                                    "match_source": match_source,
                                    "match_reason": "FMEA 探测措施（失效模式级）",
                                    "fmea_id": str(doc["fmea_id"]),
                                    "fmea_document_no": doc.get("document_no"),
                                })

    return controls


def _generate_general_suggestions(
    capa_data: dict[str, Any],
    fmea_docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate generic measure suggestions using RuleEngine."""
    from app.services.recommendation_service import RuleEngine

    engine = RuleEngine()

    # Try to get AP level from linked FMEA
    ap_level = None
    linked_fmea_id = capa_data.get("fmea_ref_id")
    for doc in fmea_docs:
        if doc["fmea_id"] == linked_fmea_id and doc.get("graph_data"):
            for node in doc["graph_data"].get("nodes", []):
                if node.get("type") == "FailureMode" and node.get("ap"):
                    ap_level = node["ap"]
                    break
            break

    failure_mode_text = capa_data.get("d2_description", "")
    context = {"failure_mode": failure_mode_text, "ap": ap_level or "M"}
    result = engine.evaluate("measure", context)

    suggestions = []
    for s in result.suggestions:
        suggestions.append({
            "content": s.name,
            "category": s.explanation or "预防措施",
            "basis": f"AP={ap_level or 'M'}",
            "confidence": s.confidence,
        })
    return suggestions
