"""测试 GraphProjectionService 的 Cypher 构建逻辑（不连 Neo4j，只测映射）。"""
import pytest
from app.services.graph_projection_service import build_cypher_sync


SAMPLE_GRAPH = {
    "nodes": [
        {"id": "sys_1", "type": "System", "name": "BMS", "severity": 0, "occurrence": 0, "detection": 0},
        {"id": "fm_1", "type": "FailureMode", "name": "电压漂移", "severity": 8, "occurrence": 5, "detection": 4, "ap": "H"},
        {"id": "fe_1", "type": "FailureEffect", "name": "热失控", "severity": 10},
        {"id": "fc_1", "type": "FailureCause", "name": "温漂", "severity": 0, "occurrence": 5, "detection": 0},
        {"id": "pc_1", "type": "PreventionControl", "name": "AEC-Q100 认证"},
        {"id": "dc_1", "type": "DetectionControl", "name": "上电自检", "detection": 4},
    ],
    "edges": [
        {"source": "sys_1", "target": "fm_1", "type": "HAS_FAILURE_MODE"},
        {"source": "fm_1", "target": "fe_1", "type": "EFFECT_OF"},
        {"source": "fc_1", "target": "fm_1", "type": "CAUSE_OF"},
        {"source": "fc_1", "target": "pc_1", "type": "PREVENTED_BY"},
        {"source": "fc_1", "target": "dc_1", "type": "DETECTED_BY"},
    ],
}


def test_build_cypher_sync_returns_delete_doc_nodes_edges():
    """build_cypher_sync 应返回：1 DELETE + 1 FMEDoc + N nodes + M edges。"""
    statements = build_cypher_sync(
        fmea_id="00000000-0000-0000-0000-000000000001",
        document_no="PFMEA-2026-001",
        title="测试",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        status="draft",
        version=1,
        graph_data=SAMPLE_GRAPH,
    )
    # 1 DELETE + 1 FMEDoc + (6 node creates + 6 HAS_NODE) + 5 edges = 19
    assert len(statements) == 19
    # 第一条是 DELETE
    assert "DETACH DELETE" in statements[0][0]
    # 第二条是 FMEDocument
    assert "FMEDocument" in statements[1][0]
    # 后续是节点和边创建
    node_stmts = [s for s in statements if "CREATE (n:GraphNode" in s[0]]
    has_node_stmts = [s for s in statements if "HAS_NODE" in s[0]]
    edge_stmts = [s for s in statements if "MATCH (s:GraphNode" in s[0] and "HAS_NODE" not in s[0]]
    assert len(node_stmts) == 6
    assert len(has_node_stmts) == 6
    assert len(edge_stmts) == 5


def test_build_cypher_sync_maps_node_types_to_labels():
    """每个节点应有 GraphNode + 具体类型双标签。"""
    statements = build_cypher_sync(
        fmea_id="00000000-0000-0000-0000-000000000001",
        document_no="PFMEA-2026-001",
        title="测试",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        status="draft",
        version=1,
        graph_data=SAMPLE_GRAPH,
    )
    node_stmts = [s[0] for s in statements if "GraphNode" in s[0] and "MATCH" not in s[0]]
    cypher_text = " ".join(node_stmts)
    assert ":GraphNode:FailureMode" in cypher_text
    assert ":GraphNode:System" in cypher_text
    # PreventionControl/DetectionControl → Control
    assert ":GraphNode:Control" in cypher_text


def test_build_cypher_sync_empty_graph():
    """空 graph_data 也能正常生成（只做 DELETE）。"""
    statements = build_cypher_sync(
        fmea_id="00000000-0000-0000-0000-000000000001",
        document_no="PFMEA-2026-001",
        title="空文档",
        fmea_type="PFMEA",
        product_line_code="DC-DC-100",
        status="draft",
        version=1,
        graph_data={"nodes": [], "edges": []},
    )
    assert len(statements) == 1  # 只有 DELETE
    assert "DETACH DELETE" in statements[0][0]


def test_build_cypher_sync_skips_unknown_types():
    """未知节点类型和边类型被安全跳过，不进入 Cypher。"""
    graph = {
        "nodes": [
            {"id": "x1", "type": "EvilNode", "name": "bad", "severity": 0, "occurrence": 0, "detection": 0},
            {"id": "x2", "type": "FailureMode", "name": "ok", "severity": 0, "occurrence": 0, "detection": 0},
        ],
        "edges": [
            {"source": "x2", "target": "x2", "type": "EVIL_RELATIONSHIP"},
            {"source": "x2", "target": "x2", "type": "CAUSE_OF"},
        ],
    }
    statements = build_cypher_sync(
        fmea_id="00000000-0000-0000-0000-000000000001",
        document_no="T-001", title="t", fmea_type="PFMEA",
        product_line_code="DC-DC-100", status="draft", version=1,
        graph_data=graph,
    )
    cypher_text = " ".join(s[0] for s in statements)
    assert "EvilNode" not in cypher_text
    assert "EVIL_RELATIONSHIP" not in cypher_text
    assert "FailureMode" in cypher_text
    assert "CAUSE_OF" in cypher_text
