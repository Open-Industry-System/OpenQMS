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
        "d2_description": "焊接虚焊；焊接参数偏移",
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
        "d2_description": "焊接参数偏移；焊接虚焊",
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
