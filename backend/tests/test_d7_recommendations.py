# backend/tests/test_d7_recommendations.py
import uuid
import pytest
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
