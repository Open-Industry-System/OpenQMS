# 8D D4/D5 Smart Recommendation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add intelligent recommendation panels to CAPA D4 (root cause) and D5 (corrective action) steps, powered by FMEA graph matching.

**Architecture:** New `capa_recommendation_service.py` with pure functions (mirroring `get_d7_recommendations` pattern). Two new API endpoints (`GET /d4-fmea-recommendations`, `/d5-fmea-recommendations`). Two new React panels (`D4RecPanel`, `D5RecPanel`) inserted above existing form fields in `CAPADetailPage`.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, React 18, TypeScript, Ant Design 5

**Spec:** `docs/superpowers/specs/2026-06-02-8d-d4-d5-recommendation-design.md`

---

## File Map

| Operation | File | Responsibility |
|-----------|------|----------------|
| Create | `backend/app/services/capa_recommendation_service.py` | D4/D5 recommendation pure functions |
| Create | `backend/tests/test_capa_recommendation.py` | Backend tests |
| Modify | `backend/app/schemas/capa.py` | Add D4/D5 recommendation schemas |
| Modify | `backend/app/api/capa.py` | Add two API endpoints |
| Create | `frontend/src/components/capa/D4RecPanel.tsx` | D4 recommendation panel |
| Create | `frontend/src/components/capa/D5RecPanel.tsx` | D5 recommendation panel |
| Modify | `frontend/src/pages/capa/CAPADetailPage.tsx` | Insert D4/D5 panels |
| Modify | `frontend/src/api/capa.ts` | Add API call functions |
| Modify | `frontend/src/types/index.ts` | Add TypeScript interfaces |

---

### Task 1: Backend Schemas

**Files:**
- Modify: `backend/app/schemas/capa.py`

- [ ] **Step 1: Add D4/D5 recommendation schemas to capa.py**

Append after the existing `D7Recommendation` class (around line 80):

```python
class D4Recommendation(BaseModel):
    failure_cause_node_id: str | None = None
    failure_cause_name: str
    failure_cause_desc: str | None = None
    failure_mode_node_id: str | None = None
    failure_mode_name: str | None = None
    fmea_document_no: str | None = None
    fmea_id: str | None = None
    match_source: str  # "linked" | "keyword" | "rule"
    match_reason: str
    related_d2_keywords: list[str] = []
    confidence: float = 0.5


class D4RecommendationResponse(BaseModel):
    items: list[D4Recommendation]


class D5ExistingControl(BaseModel):
    failure_mode_node_id: str | None = None
    failure_mode_name: str | None = None
    failure_cause_node_id: str | None = None
    failure_cause_name: str | None = None
    control_node_id: str
    control_name: str
    control_type: str  # "prevention" | "detection"
    match_source: str
    match_reason: str
    fmea_id: str | None = None
    fmea_document_no: str | None = None


class D5GeneralSuggestion(BaseModel):
    content: str
    category: str  # "预防措施" | "探测措施"
    basis: str
    confidence: float


class D5RecommendationResponse(BaseModel):
    existing_controls: list[D5ExistingControl]
    general_suggestions: list[D5GeneralSuggestion]
```

- [ ] **Step 2: Verify schemas import correctly**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.schemas.capa import D4Recommendation, D5RecommendationResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/capa.py
git commit -m "feat(capa): add D4/D5 recommendation Pydantic schemas"
```

---

### Task 2: Backend Recommendation Service — D4

**Files:**
- Create: `backend/app/services/capa_recommendation_service.py`

- [ ] **Step 1: Create the service file with D4 recommendation function**

```python
# backend/app/services/capa_recommendation_service.py
"""D4/D5 recommendation logic for CAPA 8D reports.

Pure functions (no DB access) mirroring get_d7_recommendations pattern.
"""
from __future__ import annotations

import uuid
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

    seen_keys: set[str] = set()

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
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.services.capa_recommendation_service import get_d4_recommendations; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/capa_recommendation_service.py
git commit -m "feat(capa): add D4 recommendation service with FMEA graph matching"
```

---

### Task 3: Backend Recommendation Service — D5

**Files:**
- Modify: `backend/app/services/capa_recommendation_service.py`

- [ ] **Step 1: Add D5 recommendation function to the service file**

Append after the `_rule_engine_d4` function:

```python
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
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.services.capa_recommendation_service import get_d4_recommendations, get_d5_recommendations; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/capa_recommendation_service.py
git commit -m "feat(capa): add D5 recommendation service with 3-path control matching"
```

---

### Task 4: Backend API Endpoints

**Files:**
- Modify: `backend/app/api/capa.py`

- [ ] **Step 1: Add D4 recommendation endpoint**

Insert after the existing `get_d7_fmea_recommendations` endpoint (around line 252):

```python
@router.get("/{report_id}/d4-fmea-recommendations")
async def get_d4_fmea_recommendations(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    from app.models.fmea import FMEADocument
    from app.services.capa_recommendation_service import get_d4_recommendations

    fmea_level = await get_user_permission(user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)

    if user.role_definition.bypass_row_level_security:
        allowed_pls = None
    else:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return {"items": []}

    fmea_query = select(FMEADocument).where(FMEADocument.product_line_code == capa.product_line_code)
    if allowed_pls is not None:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(allowed_pls))
    fmea_result = await db.execute(fmea_query)
    fmea_docs = [
        {"fmea_id": f.fmea_id, "document_no": f.document_no, "graph_data": f.graph_data}
        for f in fmea_result.scalars().all()
    ]

    capa_data = {
        "d2_description": capa.d2_description or "",
        "d3_interim": capa.d3_interim or "",
        "fmea_ref_id": capa.fmea_ref_id,  # keep as UUID, matching D7 pattern
        "fmea_node_id": capa.fmea_node_id,
        "product_line_code": capa.product_line_code,
    }

    items = get_d4_recommendations(capa_data, fmea_docs, allowed_pls)
    return {"items": items}
```

- [ ] **Step 2: Add D5 recommendation endpoint**

Insert after the D4 endpoint:

```python
@router.get("/{report_id}/d5-fmea-recommendations")
async def get_d5_fmea_recommendations(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    from app.models.fmea import FMEADocument
    from app.services.capa_recommendation_service import get_d5_recommendations

    fmea_level = await get_user_permission(user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)

    if user.role_definition.bypass_row_level_security:
        allowed_pls = None
    else:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return {"existing_controls": [], "general_suggestions": []}

    fmea_query = select(FMEADocument).where(FMEADocument.product_line_code == capa.product_line_code)
    if allowed_pls is not None:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(allowed_pls))
    fmea_result = await db.execute(fmea_query)
    fmea_docs = [
        {"fmea_id": f.fmea_id, "document_no": f.document_no, "graph_data": f.graph_data}
        for f in fmea_result.scalars().all()
    ]

    capa_data = {
        "d4_root_cause": capa.d4_root_cause or "",
        "d2_description": capa.d2_description or "",
        "fmea_ref_id": capa.fmea_ref_id,  # keep as UUID, matching D7 pattern
        "fmea_node_id": capa.fmea_node_id,
        "product_line_code": capa.product_line_code,
    }

    result = get_d5_recommendations(capa_data, fmea_docs, allowed_pls)
    return result
```

- [ ] **Step 3: Verify backend starts without errors**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.api.capa import router; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/capa.py
git commit -m "feat(capa): add D4/D5 FMEA recommendation API endpoints"
```

---

### Task 5: Backend Tests

**Files:**
- Create: `backend/tests/test_capa_recommendation.py`

- [ ] **Step 1: Write the test file**

```python
# backend/tests/test_capa_recommendation.py
import uuid
import pytest
from app.services.capa_recommendation_service import (
    get_d4_recommendations,
    get_d5_recommendations,
)


@pytest.fixture
def sample_graph():
    """FMEA graph with FailureMode, FailureCause, PreventionControl, DetectionControl."""
    fm_id = str(uuid.uuid4())
    cause_id = str(uuid.uuid4())
    prev_ctrl_id = str(uuid.uuid4())
    det_ctrl_id = str(uuid.uuid4())
    det_fm_ctrl_id = str(uuid.uuid4())
    func_id = str(uuid.uuid4())

    return {
        "nodes": [
            {"id": func_id, "type": "ProcessStepFunction", "name": "焊接功能"},
            {"id": fm_id, "type": "FailureMode", "name": "焊接虚焊", "ap": "H"},
            {"id": cause_id, "type": "FailureCause", "name": "焊接参数偏移"},
            {"id": prev_ctrl_id, "type": "PreventionControl", "name": "焊接参数监控"},
            {"id": det_ctrl_id, "type": "DetectionControl", "name": "AOI光学检测"},
            {"id": det_fm_ctrl_id, "type": "DetectionControl", "name": "X-Ray检测"},
        ],
        "edges": [
            {"source": func_id, "target": fm_id, "type": "HAS_FAILURE_MODE"},
            {"source": cause_id, "target": fm_id, "type": "CAUSE_OF"},
            {"source": cause_id, "target": prev_ctrl_id, "type": "PREVENTED_BY"},
            {"source": cause_id, "target": det_ctrl_id, "type": "DETECTED_BY"},
            {"source": fm_id, "target": det_fm_ctrl_id, "type": "DETECTED_BY"},
        ],
    }


def _make_fmea_doc(fmea_id=None, graph=None, doc_no="PFMEA-2026-001"):
    return {
        "fmea_id": fmea_id or uuid.uuid4(),
        "document_no": doc_no,
        "graph_data": graph,
    }


# --- D4 Tests ---

def test_d4_linked_match_with_node_id(sample_graph):
    """CAPA with fmea_ref_id + fmea_node_id (FailureMode) returns linked FailureCause."""
    fmea_id = uuid.uuid4()
    fm_id = sample_graph["nodes"][1]["id"]
    capa_data = {
        "d2_description": "焊接虚焊问题",
        "d3_interim": "",
        "fmea_ref_id": fmea_id,
        "fmea_node_id": fm_id,
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [_make_fmea_doc(fmea_id, sample_graph)]

    results = get_d4_recommendations(capa_data, fmea_docs)

    assert len(results) >= 1
    assert results[0]["failure_cause_name"] == "焊接参数偏移"
    assert results[0]["match_source"] == "linked"


def test_d4_linked_match_without_node_id(sample_graph):
    """CAPA with fmea_ref_id but no fmea_node_id searches by D2 keywords."""
    fmea_id = uuid.uuid4()
    capa_data = {
        "d2_description": "焊接参数偏移",
        "d3_interim": "",
        "fmea_ref_id": fmea_id,
        "fmea_node_id": None,
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [_make_fmea_doc(fmea_id, sample_graph)]

    results = get_d4_recommendations(capa_data, fmea_docs)

    assert len(results) >= 1
    found_names = [r["failure_cause_name"] for r in results]
    assert "焊接参数偏移" in found_names


def test_d4_keyword_match_across_fmeas(sample_graph):
    """No linked FMEA — matches by keyword across all FMEAs."""
    capa_data = {
        "d2_description": "焊接参数偏移导致虚焊",
        "d3_interim": "",
        "fmea_ref_id": None,
        "fmea_node_id": None,
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [_make_fmea_doc(graph=sample_graph)]

    results = get_d4_recommendations(capa_data, fmea_docs)

    assert len(results) >= 1
    assert results[0]["match_source"] == "keyword"


def test_d4_empty_description_returns_empty():
    """Empty D2 description returns no recommendations."""
    capa_data = {
        "d2_description": "",
        "d3_interim": "",
        "fmea_ref_id": None,
        "fmea_node_id": None,
        "product_line_code": "DC-DC-100",
    }
    results = get_d4_recommendations(capa_data, [])
    assert results == []


def test_d4_no_match_returns_rule_fallback():
    """No FMEA match falls back to rule engine."""
    capa_data = {
        "d2_description": "产品密封失效",
        "d3_interim": "",
        "fmea_ref_id": None,
        "fmea_node_id": None,
        "product_line_code": "DC-DC-100",
    }
    results = get_d4_recommendations(capa_data, [])
    assert len(results) >= 1
    assert results[0]["match_source"] == "rule"


# --- D5 Tests ---

def test_d5_existing_controls_three_paths(sample_graph):
    """D5 finds PreventionControl, cause-level DetectionControl, and FM-level DetectionControl."""
    fmea_id = uuid.uuid4()
    capa_data = {
        "d4_root_cause": "焊接参数偏移",
        "d2_description": "焊接虚焊",
        "fmea_ref_id": fmea_id,
        "fmea_node_id": sample_graph["nodes"][1]["id"],
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [_make_fmea_doc(fmea_id, sample_graph)]

    result = get_d5_recommendations(capa_data, fmea_docs)

    controls = result["existing_controls"]
    assert len(controls) >= 3

    ctrl_types = {(c["control_node_id"], c["control_type"]) for c in controls}
    prevention = [c for c in controls if c["control_type"] == "prevention"]
    detection = [c for c in controls if c["control_type"] == "detection"]
    assert len(prevention) >= 1
    assert len(detection) >= 2  # cause-level + FM-level


def test_d5_general_suggestions(sample_graph):
    """D5 returns rule engine general suggestions."""
    fmea_id = uuid.uuid4()
    capa_data = {
        "d4_root_cause": "焊接参数偏移",
        "d2_description": "焊接虚焊",
        "fmea_ref_id": fmea_id,
        "fmea_node_id": sample_graph["nodes"][1]["id"],
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [_make_fmea_doc(fmea_id, sample_graph)]

    result = get_d5_recommendations(capa_data, fmea_docs)

    assert len(result["general_suggestions"]) >= 1
    # Verify "检测措施" -> "探测措施" mapping
    for s in result["general_suggestions"]:
        assert s["category"] in ("预防措施", "探测措施")


def test_d5_empty_root_cause_falls_back_to_d2(sample_graph):
    """Empty D4 text falls back to D2 keywords for matching."""
    fmea_id = uuid.uuid4()
    capa_data = {
        "d4_root_cause": "",
        "d2_description": "焊接参数偏移",
        "fmea_ref_id": fmea_id,
        "fmea_node_id": sample_graph["nodes"][1]["id"],
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [_make_fmea_doc(fmea_id, sample_graph)]

    result = get_d5_recommendations(capa_data, fmea_docs)

    assert len(result["existing_controls"]) >= 1


def test_d5_cause_level_detection_control(sample_graph):
    """FailureCause --DETECTED_BY--> DetectionControl is found."""
    fmea_id = uuid.uuid4()
    capa_data = {
        "d4_root_cause": "焊接参数偏移",
        "d2_description": "焊接虚焊",
        "fmea_ref_id": fmea_id,
        "fmea_node_id": sample_graph["nodes"][1]["id"],
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [_make_fmea_doc(fmea_id, sample_graph)]

    result = get_d5_recommendations(capa_data, fmea_docs)

    cause_det = [c for c in result["existing_controls"]
                 if c["control_type"] == "detection" and "原因级" in c.get("match_reason", "")]
    assert len(cause_det) >= 1
    assert cause_det[0]["control_name"] == "AOI光学检测"
```

- [ ] **Step 2: Run the tests**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/test_capa_recommendation.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_capa_recommendation.py
git commit -m "test(capa): add D4/D5 recommendation service tests"
```

---

### Task 6: Frontend Types and API Functions

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/capa.ts`

- [ ] **Step 1: Add TypeScript interfaces to types/index.ts**

Append after the existing `D7Recommendation` interface (around line 1285):

```typescript
export interface D4Recommendation {
  failure_cause_node_id: string | null;
  failure_cause_name: string;
  failure_cause_desc: string | null;
  failure_mode_node_id: string | null;
  failure_mode_name: string | null;
  fmea_document_no: string | null;
  fmea_id: string | null;
  match_source: "linked" | "keyword" | "rule";
  match_reason: string;
  related_d2_keywords: string[];
  confidence: number;
}

export interface D4RecommendationResponse {
  items: D4Recommendation[];
}

export interface D5ExistingControl {
  failure_mode_node_id: string | null;
  failure_mode_name: string | null;
  failure_cause_node_id: string | null;
  failure_cause_name: string | null;
  control_node_id: string;
  control_name: string;
  control_type: "prevention" | "detection";
  match_source: string;
  match_reason: string;
  fmea_id: string | null;
  fmea_document_no: string | null;
}

export interface D5GeneralSuggestion {
  content: string;
  category: string;
  basis: string;
  confidence: number;
}

export interface D5RecommendationResponse {
  existing_controls: D5ExistingControl[];
  general_suggestions: D5GeneralSuggestion[];
}
```

- [ ] **Step 2: Update type imports in api/capa.ts**

Find the existing import at the top of `frontend/src/api/capa.ts`:

```typescript
import type { CAPAReport, CAPAListResponse, D7RecommendationResponse } from "../types";
```

Replace with:

```typescript
import type { CAPAReport, CAPAListResponse, D7RecommendationResponse, D4RecommendationResponse, D5RecommendationResponse } from "../types";
```

- [ ] **Step 3: Add API functions to api/capa.ts**

Append after the existing `getD7Recommendations` function:

```typescript
export async function getD4Recommendations(id: string): Promise<D4RecommendationResponse> {
  const resp = await client.get(`/capa/${id}/d4-fmea-recommendations`);
  return resp.data;
}

export async function getD5Recommendations(id: string): Promise<D5RecommendationResponse> {
  const resp = await client.get(`/capa/${id}/d5-fmea-recommendations`);
  return resp.data;
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/capa.ts
git commit -m "feat(capa): add D4/D5 recommendation types and API functions"
```

---

### Task 7: D4RecPanel Component

**Files:**
- Create: `frontend/src/components/capa/D4RecPanel.tsx`

- [ ] **Step 1: Create D4RecPanel component**

```tsx
import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Space, Typography, Empty, Spin, App } from "antd";
import { CheckOutlined, CloseOutlined, SearchOutlined } from "@ant-design/icons";
import { getD4Recommendations } from "../../api/capa";
import type { D4Recommendation } from "../../types";

const { Text } = Typography;

interface D4RecPanelProps {
  capaId: string;
  onAdopt: (adoptedText: string) => void;
  canAdopt?: boolean;
}

export default function D4RecPanel({ capaId, onAdopt, canAdopt = true }: D4RecPanelProps) {
  const { message } = App.useApp();
  const [recommendations, setRecommendations] = useState<D4Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    getD4Recommendations(capaId)
      .then((res) => setRecommendations(res.items))
      .catch(() => message.error("加载 D4 推荐失败"))
      .finally(() => setLoading(false));
  }, [capaId]);

  if (loading) return <Spin size="small" />;
  if (recommendations.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <span>
            暂无推荐
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              提示：在 D2 描述中用空格或逗号分隔关键词可提高匹配率
            </Text>
          </span>
        }
      />
    );
  }

  const groups = {
    linked: recommendations.filter((r) => r.match_source === "linked"),
    keyword: recommendations.filter((r) => r.match_source === "keyword"),
    rule: recommendations.filter((r) => r.match_source === "rule"),
  };

  const renderGroup = (title: string, items: D4Recommendation[]) => {
    if (items.length === 0) return null;
    return (
      <>
        <Text strong style={{ fontSize: 12, color: "#888" }}>{title}</Text>
        <List
          size="small"
          dataSource={items}
          renderItem={(item) => {
            const key = item.failure_cause_node_id || item.failure_cause_name;
            const isSkipped = skipped.has(key);
            return (
              <List.Item
                style={isSkipped ? { opacity: 0.4, textDecoration: "line-through" } : {}}
                actions={[
                  <Button
                    key="adopt"
                    type="link"
                    size="small"
                    icon={<CheckOutlined />}
                    disabled={!canAdopt}
                    title={!canAdopt ? "只读用户无法采纳" : undefined}
                    onClick={() => onAdopt(item.failure_cause_name)}
                  >
                    采纳
                  </Button>,
                  !isSkipped && (
                    <Button
                      key="skip"
                      type="link"
                      size="small"
                      icon={<CloseOutlined />}
                      onClick={() => setSkipped(new Set(skipped).add(key))}
                    >
                      跳过
                    </Button>
                  ),
                ]}
              >
                <List.Item.Meta
                  title={item.failure_cause_name}
                  description={
                    <Space size={4} wrap>
                      {item.failure_mode_name && <Tag>{item.failure_mode_name}</Tag>}
                      {item.fmea_document_no && <Tag color="blue">{item.fmea_document_no}</Tag>}
                      {item.match_reason && <Tag color="default">{item.match_reason}</Tag>}
                      {item.related_d2_keywords?.map((kw) => (
                        <Tag key={kw} color="green">{kw}</Tag>
                      ))}
                    </Space>
                  }
                />
              </List.Item>
            );
          }}
        />
      </>
    );
  };

  return (
    <Card
      size="small"
      title={<Space><SearchOutlined />D4 根因推荐</Space>}
      style={{ marginBottom: 16 }}
      extra={<Text type="secondary" style={{ fontSize: 12 }}>基于 D2 问题描述和关联 FMEA 分析</Text>}
    >
      {renderGroup("关联 FMEA", groups.linked)}
      {renderGroup("相似失效模式", groups.keyword)}
      {renderGroup("规则引擎建议", groups.rule)}
    </Card>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/capa/D4RecPanel.tsx
git commit -m "feat(capa): add D4RecPanel component"
```

---

### Task 8: D5RecPanel Component

**Files:**
- Create: `frontend/src/components/capa/D5RecPanel.tsx`

- [ ] **Step 1: Create D5RecPanel component**

```tsx
import { useEffect, useState } from "react";
import { Card, List, Tag, Button, Space, Typography, Empty, Spin, App, Collapse } from "antd";
import { CheckOutlined, CloseOutlined, ShieldOutlined } from "@ant-design/icons";
import { getD5Recommendations } from "../../api/capa";
import type { D5ExistingControl, D5GeneralSuggestion } from "../../types";

const { Text } = Typography;

interface D5RecPanelProps {
  capaId: string;
  onAdopt: (adoptedText: string) => void;
  canAdopt?: boolean;
}

export default function D5RecPanel({ capaId, onAdopt, canAdopt = true }: D5RecPanelProps) {
  const { message } = App.useApp();
  const [controls, setControls] = useState<D5ExistingControl[]>([]);
  const [suggestions, setSuggestions] = useState<D5GeneralSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    getD5Recommendations(capaId)
      .then((res) => {
        setControls(res.existing_controls);
        setSuggestions(res.general_suggestions);
      })
      .catch(() => message.error("加载 D5 推荐失败"))
      .finally(() => setLoading(false));
  }, [capaId]);

  if (loading) return <Spin size="small" />;
  if (controls.length === 0 && suggestions.length === 0) {
    return <Empty description="暂无推荐" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const renderControl = (item: D5ExistingControl) => {
    const key = item.control_node_id;
    const isSkipped = skipped.has(key);
    return (
      <List.Item
        style={isSkipped ? { opacity: 0.4, textDecoration: "line-through" } : {}}
        actions={[
          <Button
            key="adopt"
            type="link"
            size="small"
            icon={<CheckOutlined />}
            disabled={!canAdopt}
            title={!canAdopt ? "只读用户无法采纳" : undefined}
            onClick={() => onAdopt(item.control_name)}
          >
            采纳
          </Button>,
          !isSkipped && (
            <Button
              key="skip"
              type="link"
              size="small"
              icon={<CloseOutlined />}
              onClick={() => setSkipped(new Set(skipped).add(key))}
            >
              跳过
            </Button>
          ),
        ]}
      >
        <List.Item.Meta
          title={
            <Space>
              {item.control_name}
              <Tag color={item.control_type === "prevention" ? "green" : "orange"}>
                {item.control_type === "prevention" ? "预防" : "探测"}
              </Tag>
            </Space>
          }
          description={
            <Space size={4} wrap>
              {item.failure_cause_name && <Tag>{item.failure_cause_name}</Tag>}
              {item.failure_mode_name && <Tag>{item.failure_mode_name}</Tag>}
              {item.fmea_document_no && <Tag color="blue">{item.fmea_document_no}</Tag>}
            </Space>
          }
        />
      </List.Item>
    );
  };

  const renderSuggestion = (item: D5GeneralSuggestion, index: number) => {
    const key = `suggestion-${index}`;
    const isSkipped = skipped.has(key);
    return (
      <List.Item
        style={isSkipped ? { opacity: 0.4, textDecoration: "line-through" } : {}}
        actions={[
          <Button
            key="adopt"
            type="link"
            size="small"
            icon={<CheckOutlined />}
            disabled={!canAdopt}
            title={!canAdopt ? "只读用户无法采纳" : undefined}
            onClick={() => onAdopt(item.content)}
          >
            采纳
          </Button>,
          !isSkipped && (
            <Button
              key="skip"
              type="link"
              size="small"
              icon={<CloseOutlined />}
              onClick={() => setSkipped(new Set(skipped).add(key))}
            >
              跳过
            </Button>
          ),
        ]}
      >
        <List.Item.Meta
          title={item.content}
          description={
            <Space size={4}>
              <Tag color={item.category === "预防措施" ? "green" : "orange"}>{item.category}</Tag>
              <Tag color="default">{item.basis}</Tag>
            </Space>
          }
        />
      </List.Item>
    );
  };

  const collapseItems = [];

  if (controls.length > 0) {
    collapseItems.push({
      key: "controls",
      label: `FMEA 已有控制措施 (${controls.length})`,
      children: (
        <List
          size="small"
          dataSource={controls}
          renderItem={renderControl}
        />
      ),
    });
  }

  if (suggestions.length > 0) {
    collapseItems.push({
      key: "suggestions",
      label: `通用建议 (${suggestions.length})`,
      children: (
        <List
          size="small"
          dataSource={suggestions}
          renderItem={renderSuggestion}
        />
      ),
    });
  }

  return (
    <Card
      size="small"
      title={<Space><ShieldOutlined />D5 纠正措施推荐</Space>}
      style={{ marginBottom: 16 }}
    >
      <Collapse defaultActiveKey={["controls", "suggestions"]} items={collapseItems} />
    </Card>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/capa/D5RecPanel.tsx
git commit -m "feat(capa): add D5RecPanel component"
```

---

### Task 9: Integrate Panels into CAPADetailPage

**Files:**
- Modify: `frontend/src/pages/capa/CAPADetailPage.tsx`

- [ ] **Step 1: Add imports**

Add to the existing imports at the top of the file:

```typescript
import D4RecPanel from "../../components/capa/D4RecPanel";
import D5RecPanel from "../../components/capa/D5RecPanel";
```

- [ ] **Step 2: Insert D4RecPanel above the D4 form**

Replace the D4 section (lines 301-313):

```tsx
{capa.status === "D4_ROOT_CAUSE" && (
  <>
    <D4RecPanel
      capaId={id!}
      canAdopt={canEdit('capa')}
      onAdopt={(text) => {
        const current = localData.d4_root_cause || "";
        const newVal = current ? `${current}\n${text}` : text;
        setLocalData({ ...localData, d4_root_cause: newVal });
        handleUpdate("d4_root_cause", newVal);
      }}
    />
    <Form layout="vertical">
      <Form.Item label="根因分析 (5Why / 鱼骨图)">
        <TextArea
          rows={6}
          disabled={!canEdit('capa')}
          value={localData.d4_root_cause || ""}
          onChange={(e) => setLocalData({ ...localData, d4_root_cause: e.target.value })}
          onBlur={() => handleUpdate("d4_root_cause", localData.d4_root_cause)}
        />
      </Form.Item>
    </Form>
  </>
)}
```

- [ ] **Step 3: Insert D5RecPanel above the D5 form**

Replace the D5 section (lines 315-327):

```tsx
{capa.status === "D5_CORRECTION" && (
  <>
    <D5RecPanel
      capaId={id!}
      canAdopt={canEdit('capa')}
      onAdopt={(text) => {
        const current = localData.d5_correction || "";
        const newVal = current ? `${current}\n${text}` : text;
        setLocalData({ ...localData, d5_correction: newVal });
        handleUpdate("d5_correction", newVal);
      }}
    />
    <Form layout="vertical">
      <Form.Item label="永久纠正措施">
        <TextArea
          rows={4}
          disabled={!canEdit('capa')}
          value={localData.d5_correction || ""}
          onChange={(e) => setLocalData({ ...localData, d5_correction: e.target.value })}
          onBlur={() => handleUpdate("d5_correction", localData.d5_correction)}
        />
      </Form.Item>
    </Form>
  </>
)}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/capa/CAPADetailPage.tsx
git commit -m "feat(capa): integrate D4/D5 recommendation panels into CAPA detail page"
```

---

### Task 10: End-to-End Smoke Test

- [ ] **Step 1: Start backend and seed data**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && uvicorn app.main:app --reload --port 8000`

- [ ] **Step 2: Start frontend**

Run: `cd /Users/sam/Documents/Code/OpenQMS/frontend && npm run dev`

- [ ] **Step 3: Manual verification**

1. Login as `engineer` / `Engineer@2026`
2. Navigate to a CAPA report in D4_ROOT_CAUSE status
3. Verify D4 recommendation panel appears above the textarea
4. Click "采纳" on a recommendation — verify text is appended to textarea
5. Navigate to a CAPA in D5_CORRECTION status
6. Verify D5 recommendation panel appears with existing controls and general suggestions
7. Click "采纳" — verify text is appended

- [ ] **Step 4: Run backend tests**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/test_capa_recommendation.py -v`
Expected: All tests PASS

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: 8D D4/D5 smart recommendation complete"
```
