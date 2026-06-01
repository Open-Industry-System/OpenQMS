# D7 预防复发提示模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a CAPA reaches D7, show related FMEA failure modes that may need updating, with auto-fill from D5 correction measures and a soft gate before D8 advance.

**Architecture:** Backend service does all matching (graph traversal for linked FMEA + keyword search across same product line). Frontend renders a recommendation panel with confirm/skip actions. Skip reasons are written to AuditLog via an extended advance endpoint.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy async | React 18 + TypeScript + Ant Design 5

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/app/utils/text.py` | **New.** `extract_keywords()` — splits text by punctuation/spaces, filters short/numeric tokens |
| `backend/app/schemas/capa.py` | **Modify.** Add `fmea_node_id` to `CAPAResponse`/`CAPAUpdate`; add `D7Recommendation`, `D7RecommendationResponse`, `AdvanceRequest` schemas |
| `backend/app/services/capa_service.py` | **Modify.** Add `fmea_node_id` to `link_fmea()`; add `d7_skip_reasons` to `advance_capa()`; add `get_d7_recommendations()` |
| `backend/app/api/capa.py` | **Modify.** Add `GET /{id}/d7-fmea-recommendations`; extend `POST /{id}/advance` with optional body; add `fmea_node_id` to link-fmea |
| `frontend/src/types/index.ts` | **Modify.** Add `D7Recommendation` type |
| `frontend/src/api/capa.ts` | **Modify.** Add `getD7Recommendations()`; extend `advanceCAPA()` with optional skip reasons |
| `frontend/src/components/capa/D7RecPanel.tsx` | **New.** Recommendation panel with confirm/skip state, auto-fill action |
| `frontend/src/pages/capa/CAPADetailPage.tsx` | **Modify.** Embed `D7RecPanel` in D7 step; add soft gate logic to advance handler |

---

### Task 1: extract_keywords utility function

**Files:**
- Create: `backend/app/utils/text.py`
- Create: `backend/tests/test_text.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_text.py
from app.utils.text import extract_keywords


def test_chinese_punctuation_split():
    result = extract_keywords("焊接虚焊；参数偏移，温度过高")
    assert result == ["焊接虚焊", "参数偏移", "温度过高"]


def test_english_space_split():
    result = extract_keywords("welding defect parameter drift")
    assert result == ["welding", "defect", "parameter", "drift"]


def test_mixed_text():
    result = extract_keywords("焊接虚焊 welding defect；温度异常")
    assert "焊接虚焊" in result
    assert "welding" in result
    assert "defect" in result
    assert "温度异常" in result


def test_filters_short_tokens():
    result = extract_keywords("A B 你好 world")
    # "A", "B", "你好" (2 chars OK), "world" OK
    assert "A" not in result
    assert "B" not in result
    assert "你好" in result
    assert "world" in result


def test_filters_numbers():
    result = extract_keywords("温度 123 偏移 456")
    assert result == ["温度", "偏移"]


def test_empty_string():
    result = extract_keywords("")
    assert result == []


def test_dedup_preserves_order():
    result = extract_keywords("虚焊；虚焊；偏移")
    assert result == ["虚焊", "偏移"]


def test_min_length_param():
    result = extract_keywords("A BC DEF", min_length=3)
    assert result == ["DEF"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/test_text.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.text'`

- [ ] **Step 3: Implement extract_keywords**

```python
# backend/app/utils/text.py
import re


def extract_keywords(text: str, min_length: int = 2) -> list[str]:
    """Extract keywords from text.

    Strategy (stdlib only, no jieba dependency):
    - Split by Chinese punctuation, English punctuation, spaces, newlines
    - Filter out pure numeric tokens and tokens shorter than min_length
    - Deduplicate preserving order
    """
    if not text:
        return []

    # Split on Chinese/English punctuation, whitespace, newlines
    tokens = re.split(r"[；，。、！？：；\s,.!?;:\n\r\t]+", text)

    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        token = token.strip()
        if not token or len(token) < min_length:
            continue
        if token.isdigit():
            continue
        if token not in seen:
            seen.add(token)
            result.append(token)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/test_text.py -v
```

Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/text.py backend/tests/test_text.py
git commit -m "feat(d7): add extract_keywords utility for D7 FMEA matching"
```

---

### Task 2: CAPA schema updates

**Files:**
- Modify: `backend/app/schemas/capa.py`

- [ ] **Step 1: Add fmea_node_id to CAPAUpdate and CAPAResponse**

Add `fmea_node_id: str | None = None` to `CAPAUpdate` (after `fmea_ref_id` line). Note: FMEA node IDs are strings (not UUIDs), e.g. `n${Date.now()}_fm`.

Add `fmea_node_id: str | None = None` to `CAPAResponse` (after `fmea_ref_id` line).

- [ ] **Step 2: Add D7 recommendation schemas**

Add after `CAPAListResponse`:

```python
class D7Recommendation(BaseModel):
    fmea_id: uuid.UUID
    fmea_document_no: str
    failure_mode_node_id: str
    failure_mode_name: str
    failure_cause_node_id: str | None = None
    failure_cause_name: str | None = None
    prevention_control_node_id: str | None = None
    prevention_control_name: str | None = None
    match_source: str  # "linked" | "keyword"
    match_reason: str
    related_d4_keywords: list[str] = []
    suggested_prevention: str | None = None


class D7RecommendationResponse(BaseModel):
    recommendations: list[D7Recommendation]


class AdvanceRequest(BaseModel):
    d7_skip_reasons: list[dict] | None = None
```

- [ ] **Step 3: Run schema test to verify imports**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.schemas.capa import D7Recommendation, D7RecommendationResponse, AdvanceRequest; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/capa.py
git commit -m "feat(d7): add fmea_node_id to CAPA schemas + D7 recommendation schemas"
```

---

### Task 3: capa_service — link_fmea and advance_capa updates

**Files:**
- Modify: `backend/app/services/capa_service.py`

- [ ] **Step 1: Update link_fmea to accept fmea_node_id**

Change the `link_fmea` function signature and body:

```python
async def link_fmea(
    db: AsyncSession,
    capa: CAPAEightD,
    fmea_ref_id: uuid.UUID,
    user_id: uuid.UUID,
    fmea_node_id: str | None = None,
) -> CAPAEightD:
    old_fmea_ref_id = capa.fmea_ref_id
    old_fmea_node_id = capa.fmea_node_id
    capa.fmea_ref_id = fmea_ref_id
    capa.fmea_node_id = fmea_node_id

    # Audit log
    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=capa.report_id,
        action="LINK_FMEA",
        changed_fields={
            "old_fmea_ref_id": str(old_fmea_ref_id) if old_fmea_ref_id else None,
            "new_fmea_ref_id": str(fmea_ref_id),
            "old_fmea_node_id": old_fmea_node_id,
            "new_fmea_node_id": fmea_node_id,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    await db.commit()
    await db.refresh(capa)
    return capa
```

- [ ] **Step 2: Update advance_capa to accept d7_skip_reasons**

Change the `advance_capa` function signature and add audit logging before commit:

```python
async def advance_capa(
    db: AsyncSession,
    capa: CAPAEightD,
    user_id: uuid.UUID,
    d7_skip_reasons: list[dict] | None = None,
) -> CAPAEightD:
    current = EightDState(capa.status)
    transitions = [
        EightDState.D1_TEAM,
        EightDState.D2_DESCRIPTION,
        EightDState.D3_INTERIM,
        EightDState.D4_ROOT_CAUSE,
        EightDState.D5_CORRECTION,
        EightDState.D6_VERIFICATION,
        EightDState.D7_PREVENTION,
        EightDState.D8_CLOSURE,
        EightDState.ARCHIVED,
    ]

    if current in transitions:
        idx = transitions.index(current)
        next_state = transitions[idx + 1] if idx + 1 < len(transitions) else EightDState.ARCHIVED
    else:
        raise ValueError(f"Cannot advance from {capa.status}")

    if not can_transition(current, next_state):
        raise ValueError(f"Cannot transition from {capa.status} to {next_state.value}")

    old_status = capa.status
    capa.status = next_state.value

    # Audit log for transition
    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=capa.report_id,
        action="TRANSITION",
        changed_fields={
            "old_status": old_status,
            "new_status": next_state.value,
        },
        operated_by=user_id,
    )
    db.add(audit_log)

    # D7 skip reasons audit
    if d7_skip_reasons and old_status == "D7_PREVENTION":
        skip_log = AuditLog(
            table_name="capa_eightd",
            record_id=capa.report_id,
            action="D7_SKIP_CONFIRMATION",
            changed_fields={"skipped_nodes": d7_skip_reasons},
            operated_by=user_id,
        )
        db.add(skip_log)

    await db.commit()
    await db.refresh(capa)
    return capa
```

- [ ] **Step 3: Verify existing tests still pass**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/ -v -x --timeout=10 2>&1 | head -40
```

Expected: Existing tests pass (no regressions from signature changes since `fmea_node_id` and `d7_skip_reasons` default to `None`).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/capa_service.py
git commit -m "feat(d7): extend link_fmea with fmea_node_id, advance_capa with skip reasons"
```

---

### Task 4: capa_service — get_d7_recommendations

**Files:**
- Modify: `backend/app/services/capa_service.py`
- Create: `backend/tests/test_d7_recommendations.py`

- [ ] **Step 1: Write failing tests for recommendations**

```python
# backend/tests/test_d7_recommendations.py
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.capa_service import get_d7_recommendations


@pytest.fixture
def sample_graph():
    """A minimal FMEA graph with one FailureMode, one FailureCause, one PreventionControl."""
    fm_id = str(uuid.uuid4())
    cause_id = str(uuid.uuid4())
    control_id = str(uuid.uuid4())
    func_id = str(uuid.uuid4())

    return {
        "nodes": [
            {"id": func_id, "type": "ProcessStepFunction", "name": "焊接功能", "severity": 8, "occurrence": 5, "detection": 6},
            {"id": fm_id, "type": "FailureMode", "name": "焊接虚焊", "severity": 8, "occurrence": 5, "detection": 6},
            {"id": cause_id, "type": "FailureCause", "name": "焊接参数偏移", "severity": 8, "occurrence": 5, "detection": 6},
            {"id": control_id, "type": "PreventionControl", "name": "焊接参数监控", "severity": 8, "occurrence": 5, "detection": 6},
        ],
        "edges": [
            {"source": func_id, "target": fm_id, "type": "HAS_FAILURE_MODE"},
            {"source": cause_id, "target": fm_id, "type": "CAUSE_OF"},
            {"source": cause_id, "target": control_id, "type": "PREVENTED_BY"},
        ],
    }


def test_extract_keywords_basic():
    from app.utils.text import extract_keywords
    result = extract_keywords("焊接虚焊；参数偏移")
    assert "焊接虚焊" in result
    assert "参数偏移" in result


def test_linked_match_returns_failure_cause_and_control(sample_graph):
    capa_data = {
        "fmea_ref_id": uuid.uuid4(),
        "fmea_node_id": sample_graph["nodes"][1]["id"],  # FailureMode
        "d4_root_cause": "焊接参数偏移导致虚焊",
        "d5_correction": "增加焊接参数在线监控",
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [
        {
            "fmea_id": capa_data["fmea_ref_id"],
            "document_no": "PFMEA-2026-001",
            "graph_data": sample_graph,
        }
    ]

    results = get_d7_recommendations(capa_data, fmea_docs, allowed_product_lines=["DC-DC-100"])

    assert len(results) >= 1
    rec = results[0]
    assert rec["failure_mode_name"] == "焊接虚焊"
    assert rec["failure_cause_name"] == "焊接参数偏移"
    assert rec["prevention_control_name"] == "焊接参数监控"
    assert rec["match_source"] == "linked"


def test_linked_match_filters_no_cause_fmea():
    """FailureMode without FailureCause should be excluded from linked results."""
    fm_id = str(uuid.uuid4())
    func_id = str(uuid.uuid4())
    graph = {
        "nodes": [
            {"id": func_id, "type": "ProcessStepFunction", "name": "测试功能", "severity": 5, "occurrence": 3, "detection": 4},
            {"id": fm_id, "type": "FailureMode", "name": "无原因失效", "severity": 5, "occurrence": 3, "detection": 4},
        ],
        "edges": [
            {"source": func_id, "target": fm_id, "type": "HAS_FAILURE_MODE"},
        ],
    }
    fmea_id = uuid.uuid4()
    capa_data = {
        "fmea_ref_id": fmea_id,
        "fmea_node_id": fm_id,
        "d4_root_cause": "测试",
        "d5_correction": None,
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [{"fmea_id": fmea_id, "document_no": "PFMEA-2026-002", "graph_data": graph}]

    results = get_d7_recommendations(capa_data, fmea_docs, allowed_product_lines=["DC-DC-100"])
    assert len(results) == 0


def test_keyword_match_finds_similar_fmea(sample_graph):
    capa_data = {
        "fmea_ref_id": uuid.uuid4(),  # different FMEA
        "fmea_node_id": None,
        "d4_root_cause": "焊接参数偏移导致虚焊",
        "d5_correction": "增加焊接参数在线监控",
        "product_line_code": "DC-DC-100",
    }
    other_fmea_id = uuid.uuid4()
    fmea_docs = [
        {
            "fmea_id": other_fmea_id,
            "document_no": "PFMEA-2026-003",
            "graph_data": sample_graph,
        }
    ]

    results = get_d7_recommendations(capa_data, fmea_docs, allowed_product_lines=["DC-DC-100"])

    assert len(results) >= 1
    assert results[0]["match_source"] == "keyword"
    assert "焊接虚焊" in results[0]["failure_mode_name"] or len(results[0]["related_d4_keywords"]) > 0


def test_linked_match_from_failure_cause_node(sample_graph):
    """When fmea_node_id is a FailureCause, find its parent FailureMode via CAUSE_OF forward."""
    cause_id = sample_graph["nodes"][2]["id"]
    capa_data = {
        "fmea_ref_id": uuid.uuid4(),
        "fmea_node_id": cause_id,  # pointing to FailureCause
        "d4_root_cause": "焊接参数偏移",
        "d5_correction": "增加焊接参数在线监控",
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [
        {
            "fmea_id": capa_data["fmea_ref_id"],
            "document_no": "PFMEA-2026-001",
            "graph_data": sample_graph,
        }
    ]

    results = get_d7_recommendations(capa_data, fmea_docs, allowed_product_lines=["DC-DC-100"])

    assert len(results) == 1
    assert results[0]["failure_mode_name"] == "焊接虚焊"
    assert results[0]["failure_cause_name"] == "焊接参数偏移"
    assert results[0]["match_source"] == "linked"


def test_keyword_match_via_failure_cause_name():
    """Keywords matching FailureCause name (not FailureMode name) should still recommend."""
    fm_id = str(uuid.uuid4())
    cause_id = str(uuid.uuid4())
    func_id = str(uuid.uuid4())
    graph = {
        "nodes": [
            {"id": func_id, "type": "ProcessStepFunction", "name": "焊接功能", "severity": 8, "occurrence": 5, "detection": 6},
            {"id": fm_id, "type": "FailureMode", "name": "虚焊", "severity": 8, "occurrence": 5, "detection": 6},
            {"id": cause_id, "type": "FailureCause", "name": "焊接参数偏移导致接触不良", "severity": 8, "occurrence": 5, "detection": 6},
        ],
        "edges": [
            {"source": func_id, "target": fm_id, "type": "HAS_FAILURE_MODE"},
            {"source": cause_id, "target": fm_id, "type": "CAUSE_OF"},
        ],
    }
    fmea_id = uuid.uuid4()
    capa_data = {
        "fmea_ref_id": uuid.uuid4(),  # different FMEA (not linked)
        "fmea_node_id": None,
        "d4_root_cause": "焊接参数偏移",
        "d5_correction": None,
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [{"fmea_id": fmea_id, "document_no": "PFMEA-2026-005", "graph_data": graph}]

    results = get_d7_recommendations(capa_data, fmea_docs, allowed_product_lines=["DC-DC-100"])

    # "焊接参数偏移" matches FailureCause name, so FailureMode "虚焊" should be recommended
    assert len(results) >= 1
    assert any(r["failure_mode_name"] == "虚焊" for r in results)


def test_empty_graph_returns_empty():
    capa_data = {
        "fmea_ref_id": uuid.uuid4(),
        "fmea_node_id": None,
        "d4_root_cause": "测试原因",
        "d5_correction": None,
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = [
        {
            "fmea_id": capa_data["fmea_ref_id"],
            "document_no": "PFMEA-2026-004",
            "graph_data": {"nodes": [], "edges": []},
        }
    ]

    results = get_d7_recommendations(capa_data, fmea_docs, allowed_product_lines=["DC-DC-100"])
    assert results == []


def test_product_line_filter_excludes():
    capa_data = {
        "fmea_ref_id": uuid.uuid4(),
        "fmea_node_id": None,
        "d4_root_cause": "焊接参数偏移",
        "d5_correction": None,
        "product_line_code": "DC-DC-100",
    }
    fmea_docs = []  # no FMEAs in allowed list

    results = get_d7_recommendations(capa_data, fmea_docs, allowed_product_lines=["OTHER-LINE"])
    assert results == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/test_d7_recommendations.py -v
```

Expected: FAIL — `ImportError: cannot import name 'get_d7_recommendations'`

- [ ] **Step 3: Implement get_d7_recommendations**

Add to `backend/app/services/capa_service.py`:

```python
from app.utils.text import extract_keywords


def get_d7_recommendations(
    capa_data: dict,
    fmea_docs: list[dict],
    allowed_product_lines: list[str] | None = None,
) -> list[dict]:
    """Compute D7 FMEA recommendations for a CAPA.

    Args:
        capa_data: dict with fmea_ref_id, fmea_node_id, d4_root_cause, d5_correction, product_line_code
        fmea_docs: list of dicts with fmea_id, document_no, graph_data (already filtered by product line)
        allowed_product_lines: user's accessible product line codes

    Returns:
        List of recommendation dicts matching D7Recommendation schema.
    """
    recommendations: list[dict] = []

    # Split into linked FMEA and other FMEAs
    linked_fmea_id = capa_data.get("fmea_ref_id")
    linked_fmea = None
    other_fmeas = []

    for doc in fmea_docs:
        if doc["fmea_id"] == linked_fmea_id:
            linked_fmea = doc
        else:
            other_fmeas.append(doc)

    # --- Linked matching ---
    if linked_fmea and linked_fmea.get("graph_data"):
        graph = linked_fmea["graph_data"]
        node_map = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])

        # Build reverse index: target -> list of (source, edge_type)
        reverse_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            reverse_edges.setdefault(e["target"], []).append((e["source"], e["type"]))

        # Build forward index: source -> list of (target, edge_type)
        forward_edges: dict[str, list[tuple[str, str]]] = {}
        for e in edges:
            forward_edges.setdefault(e["source"], []).append((e["target"], e["type"]))

        target_node_id = capa_data.get("fmea_node_id")
        target_node = node_map.get(target_node_id) if target_node_id else None

        failure_mode_ids: list[str] = []

        if target_node:
            if target_node["type"] == "FailureCause":
                # Find parent FailureMode via CAUSE_OF forward (FailureCause -> FailureMode)
                for tgt, etype in forward_edges.get(target_node_id, []):
                    if etype == "CAUSE_OF" and node_map.get(tgt, {}).get("type") == "FailureMode":
                        failure_mode_ids.append(tgt)
            elif target_node["type"] == "FailureMode":
                failure_mode_ids.append(target_node_id)
            else:
                # Function or other type: find FailureModes via HAS_FAILURE_MODE
                for tgt, etype in forward_edges.get(target_node_id, []):
                    if etype == "HAS_FAILURE_MODE" and node_map.get(tgt, {}).get("type") == "FailureMode":
                        failure_mode_ids.append(tgt)
        else:
            # No specific node: find FailureModes matching D4 keywords
            keywords = extract_keywords(capa_data.get("d4_root_cause", ""))
            for n in graph.get("nodes", []):
                if n.get("type") == "FailureMode":
                    name = n.get("name", "")
                    if any(kw in name for kw in keywords):
                        failure_mode_ids.append(n["id"])

        # For each FailureMode, find FailureCauses and PreventionControls
        for fm_id in failure_mode_ids:
            fm_node = node_map.get(fm_id)
            if not fm_node:
                continue

            # Find FailureCauses via CAUSE_OF reverse (FailureCause --CAUSE_OF--> FailureMode)
            cause_ids = []
            for src, etype in reverse_edges.get(fm_id, []):
                if etype == "CAUSE_OF" and node_map.get(src, {}).get("type") == "FailureCause":
                    cause_ids.append(src)

            if not cause_ids:
                # No FailureCause — skip (linked matching filters these out)
                continue

            for cause_id in cause_ids:
                cause_node = node_map.get(cause_id)
                # Find PreventionControl via PREVENTED_BY forward
                control_id = None
                control_name = None
                for tgt, etype in forward_edges.get(cause_id, []):
                    if etype == "PREVENTED_BY" and node_map.get(tgt, {}).get("type") == "PreventionControl":
                        control_id = tgt
                        control_name = node_map[tgt].get("name")
                        break

                recommendations.append({
                    "fmea_id": linked_fmea["fmea_id"],
                    "fmea_document_no": linked_fmea["document_no"],
                    "failure_mode_node_id": fm_id,
                    "failure_mode_name": fm_node.get("name", ""),
                    "failure_cause_node_id": cause_id,
                    "failure_cause_name": cause_node.get("name", "") if cause_node else None,
                    "prevention_control_node_id": control_id,
                    "prevention_control_name": control_name,
                    "match_source": "linked",
                    "match_reason": "关联FMEA失效模式",
                    "related_d4_keywords": extract_keywords(capa_data.get("d4_root_cause", "")),
                    "suggested_prevention": capa_data.get("d5_correction"),
                })

    # --- Keyword matching (other FMEAs) ---
    keywords = extract_keywords(capa_data.get("d4_root_cause", ""))
    if keywords and other_fmeas:
        seen_keys: set[str] = set()
        # Exclude already-added linked recommendations
        for r in recommendations:
            seen_keys.add(f"{r['fmea_id']}_{r['failure_mode_node_id']}")

        keyword_results: list[tuple[int, dict]] = []  # (match_count, rec)

        for doc in other_fmeas:
            # product_line filtering already done at query level
            graph = doc.get("graph_data")
            if not graph:
                continue

            node_map = {n["id"]: n for n in graph.get("nodes", [])}
            edges = graph.get("edges", [])

            reverse_edges_kw: dict[str, list[tuple[str, str]]] = {}
            for e in edges:
                reverse_edges_kw.setdefault(e["target"], []).append((e["source"], e["type"]))

            forward_edges_kw: dict[str, list[tuple[str, str]]] = {}
            for e in edges:
                forward_edges_kw.setdefault(e["source"], []).append((e["target"], e["type"]))

            # Pre-index FailureCause names+descriptions per FailureMode for broader keyword matching
            fm_cause_texts: dict[str, list[str]] = {}  # fm_id -> [cause_name, cause_desc, ...]
            for e in edges:
                if e["type"] == "CAUSE_OF":
                    cause_node = node_map.get(e["source"])
                    if cause_node and cause_node.get("type") == "FailureCause":
                        texts = [cause_node.get("name", "")]
                        if cause_node.get("description"):
                            texts.append(cause_node["description"])
                        fm_cause_texts.setdefault(e["target"], []).extend(texts)

            for n in graph.get("nodes", []):
                if n.get("type") != "FailureMode":
                    continue

                # Match against FailureMode name/description AND its FailureCause name/description
                all_text = [n.get("name", "")]
                if n.get("description"):
                    all_text.append(n["description"])
                all_text.extend(fm_cause_texts.get(n["id"], []))
                matched_kws = [kw for kw in keywords if any(kw in t for t in all_text)]
                if not matched_kws:
                    continue

                dedup_key = f"{doc['fmea_id']}_{n['id']}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                # Find FailureCauses
                cause_ids = []
                for src, etype in reverse_edges_kw.get(n["id"], []):
                    if etype == "CAUSE_OF" and node_map.get(src, {}).get("type") == "FailureCause":
                        cause_ids.append(src)

                if not cause_ids:
                    # No FailureCause — include with null cause/control, disable auto-fill
                    keyword_results.append((len(matched_kws), {
                        "fmea_id": doc["fmea_id"],
                        "fmea_document_no": doc["document_no"],
                        "failure_mode_node_id": n["id"],
                        "failure_mode_name": name,
                        "failure_cause_node_id": None,
                        "failure_cause_name": None,
                        "prevention_control_node_id": None,
                        "prevention_control_name": None,
                        "match_source": "keyword",
                        "match_reason": f"关键词匹配: {', '.join(matched_kws)}",
                        "related_d4_keywords": matched_kws,
                        "suggested_prevention": capa_data.get("d5_correction"),
                    }))
                    continue

                for cause_id in cause_ids:
                    cause_node = node_map.get(cause_id)
                    control_id = None
                    control_name = None
                    for tgt, etype in forward_edges_kw.get(cause_id, []):
                        if etype == "PREVENTED_BY" and node_map.get(tgt, {}).get("type") == "PreventionControl":
                            control_id = tgt
                            control_name = node_map[tgt].get("name")
                            break

                    keyword_results.append((len(matched_kws), {
                        "fmea_id": doc["fmea_id"],
                        "fmea_document_no": doc["document_no"],
                        "failure_mode_node_id": n["id"],
                        "failure_mode_name": name,
                        "failure_cause_node_id": cause_id,
                        "failure_cause_name": cause_node.get("name", "") if cause_node else None,
                        "prevention_control_node_id": control_id,
                        "prevention_control_name": control_name,
                        "match_source": "keyword",
                        "match_reason": f"关键词匹配: {', '.join(matched_kws)}",
                        "related_d4_keywords": matched_kws,
                        "suggested_prevention": capa_data.get("d5_correction"),
                    }))

        # Sort by match count descending, take top 5
        keyword_results.sort(key=lambda x: x[0], reverse=True)
        for _, rec in keyword_results[:5]:
            recommendations.append(rec)

    return recommendations
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/test_d7_recommendations.py -v
```

Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/capa_service.py backend/tests/test_d7_recommendations.py
git commit -m "feat(d7): implement get_d7_recommendations matching algorithm"
```

---

### Task 5: API routes — recommendations endpoint + advance extension

**Files:**
- Modify: `backend/app/api/capa.py`

- [ ] **Step 1: Add GET /{id}/d7-fmea-recommendations endpoint**

Add after the existing `get_related_fmea` endpoint:

```python
@router.get("/{report_id}/d7-fmea-recommendations")
async def get_d7_fmea_recommendations(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW)),
):
    from app.models.fmea import FMEADocument
    from app.core.permissions import get_user_permission
    from app.services.capa_service import get_d7_recommendations

    # Require both CAPA VIEW and FMEA VIEW
    fmea_level = await get_user_permission(user, Module.FMEA, db)
    if fmea_level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 FMEA 模块的 VIEW 权限")

    capa = await capa_service.get_capa(db, report_id)
    if capa is None:
        raise HTTPException(status_code=404, detail="8D report not found")
    await enforce_product_line_access(user, capa.product_line_code, db)

    # Get user's accessible product lines (bypass for admins)
    if user.role_definition.bypass_row_level_security:
        allowed_pls = None  # no restriction
    else:
        allowed_pls = await get_user_product_line_codes(user, db)
        if not allowed_pls:
            return {"recommendations": []}

    # Fetch FMEA documents (filtered by product line for non-admins)
    fmea_query = select(FMEADocument)
    if allowed_pls is not None:
        fmea_query = fmea_query.where(FMEADocument.product_line_code.in_(allowed_pls))
    fmea_result = await db.execute(fmea_query)
    fmea_docs = [
        {
            "fmea_id": f.fmea_id,
            "document_no": f.document_no,
            "graph_data": f.graph_data,
        }
        for f in fmea_result.scalars().all()
    ]

    capa_data = {
        "fmea_ref_id": capa.fmea_ref_id,
        "fmea_node_id": capa.fmea_node_id,
        "d4_root_cause": capa.d4_root_cause or "",
        "d5_correction": capa.d5_correction,
        "product_line_code": capa.product_line_code,
    }

    recs = get_d7_recommendations(capa_data, fmea_docs, allowed_pls)
    return {"recommendations": recs}
```

- [ ] **Step 2: Extend POST /{id}/advance with optional AdvanceRequest body**

Change the `advance_capa` route to accept an optional body:

```python
@router.post("/{report_id}/advance", response_model=CAPAResponse)
async def advance_capa(
    report_id: uuid.UUID,
    body: AdvanceRequest | None = None,
    db: AsyncSession = Depends(get_db),
    result: tuple[User, Any] = Depends(require_close_permission),
):
    user, capa = result
    skip_reasons = body.d7_skip_reasons if body else None
    try:
        capa = await capa_service.advance_capa(db, capa, user.user_id, skip_reasons)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CAPAResponse.model_validate(capa)
```

Add `AdvanceRequest` to the imports at the top of the file.

- [ ] **Step 3: Add fmea_node_id to link-fmea endpoint**

Change the `link_fmea` route to accept optional `fmea_node_id` query param:

```python
@router.post("/{report_id}/link-fmea", response_model=CAPAResponse)
async def link_fmea(
    report_id: uuid.UUID,
    fmea_id: uuid.UUID,
    fmea_node_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Module.CAPA, PermissionLevel.EDIT)),
):
    # ... existing validation ...
    capa = await capa_service.link_fmea(db, capa, fmea_id, user.user_id, fmea_node_id)
    return CAPAResponse.model_validate(capa)
```

- [ ] **Step 4: Verify server starts without errors**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.api.capa import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/capa.py
git commit -m "feat(d7): add d7-recommendations endpoint, extend advance with skip reasons"
```

---

### Task 6: Frontend types and API functions

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/capa.ts`

- [ ] **Step 1: Add D7Recommendation type**

Add to `frontend/src/types/index.ts`:

```typescript
export interface D7Recommendation {
  fmea_id: string;
  fmea_document_no: string;
  failure_mode_node_id: string;
  failure_mode_name: string;
  failure_cause_node_id: string | null;
  failure_cause_name: string | null;
  prevention_control_node_id: string | null;
  prevention_control_name: string | null;
  match_source: "linked" | "keyword";
  match_reason: string;
  related_d4_keywords: string[];
  suggested_prevention: string | null;
}

export interface D7RecommendationResponse {
  recommendations: D7Recommendation[];
}
```

- [ ] **Step 2: Add API functions**

Add to `frontend/src/api/capa.ts`:

```typescript
import type { D7RecommendationResponse } from "../types";

export async function getD7Recommendations(id: string): Promise<D7RecommendationResponse> {
  const resp = await client.get(`/capa/${id}/d7-fmea-recommendations`);
  return resp.data;
}
```

Update `advanceCAPA` to accept optional skip reasons:

```typescript
export async function advanceCAPA(
  id: string,
  skipReasons?: { d7_skip_reasons?: Array<{ fmea_id: string; node_id: string; reason: string }> }
): Promise<CAPAReport> {
  const resp = await client.post(`/capa/${id}/advance`, skipReasons ?? {});
  return resp.data;
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: No new type errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/capa.ts
git commit -m "feat(d7): add D7 recommendation types and API functions"
```

---

### Task 7: D7RecPanel component

**Files:**
- Create: `frontend/src/components/capa/D7RecPanel.tsx`

- [ ] **Step 1: Create the D7RecPanel component**

```tsx
import { useEffect, useState, useMemo } from "react";
import {
  Card, List, Tag, Button, Space, Typography, Tooltip, Badge, App, Empty, Spin,
} from "antd";
import {
  LinkOutlined, CheckOutlined, CloseOutlined, ThunderboltOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import client from "../../api/client";
import { getD7Recommendations } from "../../api/capa";
import { updateFMEA } from "../../api/fmea";
import type { D7Recommendation } from "../../types";

const { Text } = Typography;

export interface D7UnconfirmedItem {
  fmea_id: string;
  failure_mode_node_id: string;
  failure_mode_name: string;
  failure_cause_node_id: string | null;
}

interface D7RecPanelProps {
  capaId: string;
  d5Correction: string | null;
  onConfirmationChange: (allConfirmed: boolean, unconfirmedItems: D7UnconfirmedItem[]) => void;
}

export default function D7RecPanel({
  capaId,
  d5Correction,
  onConfirmationChange,
}: D7RecPanelProps) {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [recommendations, setRecommendations] = useState<D7Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirmedNodes, setConfirmedNodes] = useState<Map<string, "updated" | "skipped">>(new Map());
  const [fillingNode, setFillingNode] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getD7Recommendations(capaId)
      .then((res) => setRecommendations(res.recommendations))
      .catch(() => message.error("加载推荐失败"))
      .finally(() => setLoading(false));
  }, [capaId]);

  useEffect(() => {
    if (recommendations.length === 0) {
      onConfirmationChange(true, []);
      return;
    }
    const unconfirmed: D7UnconfirmedItem[] = recommendations
      .filter((r) => !confirmedNodes.has(r.failure_mode_node_id + (r.failure_cause_node_id || "")))
      .map((r) => ({
        fmea_id: String(r.fmea_id),
        failure_mode_node_id: r.failure_mode_node_id,
        failure_mode_name: r.failure_mode_name,
        failure_cause_node_id: r.failure_cause_node_id,
      }));
    onConfirmationChange(unconfirmed.length === 0, unconfirmed);
  }, [confirmedNodes, recommendations]);

  const linked = useMemo(
    () => recommendations.filter((r) => r.match_source === "linked"),
    [recommendations]
  );
  const keyword = useMemo(
    () => recommendations.filter((r) => r.match_source === "keyword"),
    [recommendations]
  );

  const confirmedCount = useMemo(() => {
    return recommendations.filter((r) =>
      confirmedNodes.has(r.failure_mode_node_id + (r.failure_cause_node_id || ""))
    ).length;
  }, [confirmedNodes, recommendations]);

  const handleConfirm = (rec: D7Recommendation, status: "updated" | "skipped") => {
    const key = rec.failure_mode_node_id + (rec.failure_cause_node_id || "");
    setConfirmedNodes((prev) => new Map(prev).set(key, status));
  };

  const handleAutoFill = async (rec: D7Recommendation) => {
    if (!d5Correction || !rec.failure_cause_node_id) return;
    setFillingNode(rec.failure_cause_node_id);
    try {
      // Fetch current FMEA to get graph_data
      const fmeaResp = await client.get(`/fmea/${rec.fmea_id}`);
      const fmea = fmeaResp.data;
      const graph = fmea.graph_data;

      // Find and update or create PreventionControl
      const nodeMap = new Map(graph.nodes.map((n: any) => [n.id, n]));
      const existingControl = graph.nodes.find(
        (n: any) =>
          n.type === "PreventionControl" &&
          graph.edges.some(
            (e: any) =>
              e.source === rec.failure_cause_node_id &&
              e.target === n.id &&
              e.type === "PREVENTED_BY"
          )
      );

      if (existingControl) {
        existingControl.name = d5Correction;
      } else {
        const newControlId = crypto.randomUUID();
        graph.nodes.push({
          id: newControlId,
          type: "PreventionControl",
          name: d5Correction,
          severity: 1,
          occurrence: 1,
          detection: 1,
        });
        graph.edges.push({
          source: rec.failure_cause_node_id,
          target: newControlId,
          type: "PREVENTED_BY",
        });
      }

      await updateFMEA(rec.fmea_id, { graph_data: graph });
      message.success("已自动填充预防措施");

      // Mark as updated
      handleConfirm(rec, "updated");

      // Refresh recommendations
      const refreshed = await getD7Recommendations(capaId);
      setRecommendations(refreshed.recommendations);
    } catch {
      message.error("自动填充失败");
    } finally {
      setFillingNode(null);
    }
  };

  const handleJump = (rec: D7Recommendation) => {
    navigate(`/fmea/${rec.fmea_id}?node=${rec.failure_mode_node_id}`);
  };

  if (loading) return <Spin size="small" />;

  if (recommendations.length === 0) {
    return (
      <Card title="🔔 预防复发提示" size="small">
        <Empty description="暂无相关 FMEA 推荐" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  const renderRecItem = (rec: D7Recommendation) => {
    const key = rec.failure_mode_node_id + (rec.failure_cause_node_id || "");
    const confirmed = confirmedNodes.get(key);

    return (
      <List.Item
        key={key}
        actions={[
          <Button
            key="jump"
            size="small"
            icon={<LinkOutlined />}
            onClick={() => handleJump(rec)}
          >
            跳转
          </Button>,
          rec.failure_cause_node_id && d5Correction ? (
            <Tooltip
              key="fill"
              title={
                rec.prevention_control_node_id
                  ? "更新已有预防控制"
                  : "新增预防控制节点"
              }
            >
              <Button
                size="small"
                type="primary"
                ghost
                icon={<ThunderboltOutlined />}
                loading={fillingNode === rec.failure_cause_node_id}
                onClick={() => handleAutoFill(rec)}
              >
                自动填充
              </Button>
            </Tooltip>
          ) : (
            <Tooltip key="fill-disabled" title={!rec.failure_cause_node_id ? "无原因节点，请手动处理" : "无D5措施可填充"}>
              <Button size="small" icon={<ThunderboltOutlined />} disabled>
                自动填充
              </Button>
            </Tooltip>
          ),
          <Button
            key="confirm"
            size="small"
            type={confirmed === "updated" ? "primary" : "default"}
            icon={<CheckOutlined />}
            onClick={() => handleConfirm(rec, "updated")}
          >
            已更新
          </Button>,
          <Button
            key="skip"
            size="small"
            danger={confirmed === "skipped"}
            icon={<CloseOutlined />}
            onClick={() => handleConfirm(rec, "skipped")}
          >
            无需更新
          </Button>,
        ]}
      >
        <List.Item.Meta
          title={
            <Space>
              <Text strong>{rec.failure_mode_name}</Text>
              {rec.failure_cause_name && (
                <Text type="secondary">→ {rec.failure_cause_name}</Text>
              )}
              {rec.prevention_control_name && (
                <Tag color="green">已有: {rec.prevention_control_name}</Tag>
              )}
              {!rec.prevention_control_name && rec.failure_cause_node_id && (
                <Tag color="orange">需新增</Tag>
              )}
            </Space>
          }
          description={
            <Space>
              <Tag color="blue">{rec.fmea_document_no}</Tag>
              <Tag>{rec.match_source === "linked" ? "已关联" : "相似"}</Tag>
              {rec.match_reason && <Text type="secondary">{rec.match_reason}</Text>}
              {confirmed && (
                <Tag color={confirmed === "updated" ? "green" : "default"}>
                  {confirmed === "updated" ? "✓ 已更新" : "✗ 已跳过"}
                </Tag>
              )}
            </Space>
          }
        />
      </List.Item>
    );
  };

  return (
    <Card
      title={
        <Space>
          🔔 预防复发提示
          <Badge count={confirmedCount} overflowCount={99} style={{ backgroundColor: "#52c41a" }} />
          <Text type="secondary">/ {recommendations.length}</Text>
        </Space>
      }
      size="small"
    >
      {linked.length > 0 && (
        <>
          <Text strong style={{ display: "block", marginBottom: 8 }}>📋 已关联 FMEA 节点</Text>
          <List
            size="small"
            dataSource={linked}
            renderItem={renderRecItem}
            style={{ marginBottom: 16 }}
          />
        </>
      )}
      {keyword.length > 0 && (
        <>
          <Text strong style={{ display: "block", marginBottom: 8 }}>
            🔍 同产品线相似失效模式
          </Text>
          <List size="small" dataSource={keyword} renderItem={renderRecItem} />
        </>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: No new type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/capa/D7RecPanel.tsx
git commit -m "feat(d7): add D7RecPanel component with recommendation list and auto-fill"
```

---

### Task 8: CAPADetailPage integration + soft gate

**Files:**
- Modify: `frontend/src/pages/capa/CAPADetailPage.tsx`

- [ ] **Step 1: Import D7RecPanel and add state**

Add import at top:

```typescript
import D7RecPanel, { type D7UnconfirmedItem } from "../../components/capa/D7RecPanel";
```

Add state variable inside `CAPADetailPage`:

```typescript
const [allD7Confirmed, setAllD7Confirmed] = useState(true);
const [d7UnconfirmedItems, setD7UnconfirmedItems] = useState<D7UnconfirmedItem[]>([]);
const [d7SkipDialogOpen, setD7SkipDialogOpen] = useState(false);
const [d7SkipReasons, setD7SkipReasons] = useState<Record<string, string>>({});
```

- [ ] **Step 2: Embed D7RecPanel in D7 step**

Replace the existing D7 section (the `{capa.status === "D7_PREVENTION" && (` block) with:

```tsx
{capa.status === "D7_PREVENTION" && (
  <>
    <Form layout="vertical">
      <Form.Item label="预防复发措施">
        <TextArea
          rows={4}
          disabled={!canEdit('capa')}
          value={localData.d7_prevention || ""}
          onChange={(e) => setLocalData({ ...localData, d7_prevention: e.target.value })}
          onBlur={() => handleUpdate("d7_prevention", localData.d7_prevention)}
        />
      </Form.Item>
    </Form>
    <Divider />
    <D7RecPanel
      capaId={id!}
      d5Correction={localData.d5_correction}
      onConfirmationChange={(allConfirmed, unconfirmed) => {
        setAllD7Confirmed(allConfirmed);
        setD7UnconfirmedItems(unconfirmed);
      }}
    />
  </>
)}
```

- [ ] **Step 3: Add soft gate to handleAdvance**

Replace the existing `handleAdvance` function:

```typescript
const handleAdvance = async () => {
  if (!id) return;

  // D7 soft gate: check for unconfirmed recommendations
  if (capa?.status === "D7_PREVENTION" && !allD7Confirmed) {
    setD7SkipDialogOpen(true);
    return;
  }

  try {
    const updated = await advanceCAPA(id);
    setCapa(updated);
    message.success("已推进到下一步");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } };
    message.error(err?.response?.data?.detail || "推进失败");
  }
};

const handleD7SkipConfirm = async () => {
  if (!id) return;
  setD7SkipDialogOpen(false);

  const globalReason = (d7SkipReasons["__global__"] || "").trim();
  const skipReasonsList = d7UnconfirmedItems.map((item) => ({
    fmea_id: item.fmea_id,
    node_id: item.failure_mode_node_id,
    reason: globalReason || "未填写理由",
  }));

  try {
    const updated = await advanceCAPA(id, {
      d7_skip_reasons: skipReasonsList.length > 0 ? skipReasonsList : undefined,
    });
    setCapa(updated);
    message.success("已推进到下一步");
    setD7SkipReasons({});
    setD7UnconfirmedItems([]);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } };
    message.error(err?.response?.data?.detail || "推进失败");
  }
};
```

- [ ] **Step 4: Add skip confirmation Modal**

Wrap the existing `return (<div>...</div>);` in a fragment and add the Modal inside:

```tsx
// Change the return statement from:
//   return (<div>...</div>);
// To:
return (
  <>
    <div>
      {/* ... all existing JSX ... */}
    </div>

    <Modal
      title="⚠️ 以下 FMEA 节点尚未确认"
      open={d7SkipDialogOpen}
      onOk={handleD7SkipConfirm}
      onCancel={() => setD7SkipDialogOpen(false)}
      okText="确认跳过并推进"
      cancelText="取消"
      width={600}
    >
      <p>以下推荐的 FMEA 节点尚未标记为"已更新"或"无需更新"：</p>
      <ul>
        {d7UnconfirmedItems.map((item) => (
          <li key={item.failure_mode_node_id}>
            {item.failure_mode_name}
            {item.failure_cause_node_id && ` (原因: ${item.failure_cause_node_id})`}
          </li>
        ))}
      </ul>
      <p>如需跳过，请填写理由（可选）：</p>
      <Input.TextArea
        rows={3}
        placeholder="跳过理由（可选）"
        value={d7SkipReasons["__global__"] || ""}
        onChange={(e) =>
          setD7SkipReasons({ ...d7SkipReasons, __global__: e.target.value })
        }
      />
    </Modal>
  </>
);
```

Add `Modal` to the antd imports at the top of the file.

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: No new type errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/capa/CAPADetailPage.tsx
git commit -m "feat(d7): integrate D7RecPanel into CAPADetailPage with soft gate"
```

---

### Task 9: End-to-end verification

- [ ] **Step 1: Run backend tests**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/test_text.py tests/test_d7_recommendations.py -v
```

Expected: All tests PASS

- [ ] **Step 2: Run frontend build**

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend && npm run build
```

Expected: Build succeeds with no errors

- [ ] **Step 3: Start backend and verify endpoint**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && timeout 5 python -c "
from app.main import app
from app.api.capa import router
print('Routes registered:')
for route in router.routes:
    if hasattr(route, 'methods'):
        print(f'  {route.methods} {route.path}')
" 2>&1
```

Expected: Shows `GET /{report_id}/d7-fmea-recommendations` in route list

- [ ] **Step 4: Final commit (if any fixups needed)**

```bash
git add -A && git commit -m "feat(d7): D7 prevention recurrence module complete"
```
