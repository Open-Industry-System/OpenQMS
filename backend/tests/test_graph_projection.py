from app.services.graph_projection_service import build_cypher_sync


def test_build_cypher_sync_basic_structure():
    """验证生成的 Cypher 语句序列包含 DELETE + FMEDocument + nodes + edges。"""
    statements = build_cypher_sync(
        fmea_id="f1", document_no="PFMEA-001", title="测试",
        fmea_type="PFMEA", product_line_code="DC-DC-100",
        product_line_name="DC-DC 电源模块",
        status="approved", version=1,
        graph_data={
            "nodes": [
                {"id": "n1", "type": "FailureMode", "name": "焊接虚焊"},
                {"id": "n2", "type": "FailureEffect", "name": "功能丧失"},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "type": "EFFECT_OF"},
            ],
        },
    )

    # 1 DELETE + 1 FMEDocument + (2 nodes × 2 each) + 1 edge = 7 statements
    assert len(statements) == 7

    # 第 1 条是 DELETE
    assert "DETACH DELETE" in statements[0][0]

    # 第 2 条是 FMEDocument
    assert "CREATE (d:FMEDocument" in statements[1][0]

    # 检查 edge 语句
    edge_statements = [s for s in statements if "EFFECT_OF" in s[0]]
    assert len(edge_statements) == 1


def test_build_cypher_sync_empty_graph():
    """空 graph_data 时只返回 DELETE 语句。"""
    statements = build_cypher_sync(
        fmea_id="f1", document_no="PFMEA-001", title="测试",
        fmea_type="PFMEA", product_line_code="DC-DC-100",
        product_line_name="DC-DC 电源模块",
        status="approved", version=1,
        graph_data={"nodes": [], "edges": []},
    )
    assert len(statements) == 1
    assert "DETACH DELETE" in statements[0][0]


def test_build_cypher_sync_skips_unknown_node_type():
    """未知节点类型被跳过，不生成 Cypher。"""
    statements = build_cypher_sync(
        fmea_id="f1", document_no="PFMEA-001", title="测试",
        fmea_type="PFMEA", product_line_code="DC-DC-100",
        product_line_name="DC-DC 电源模块",
        status="approved", version=1,
        graph_data={
            "nodes": [
                {"id": "n1", "type": "UnknownType", "name": "未知"},
                {"id": "n2", "type": "FailureMode", "name": "焊接虚焊"},
            ],
            "edges": [],
        },
    )
    # 1 DELETE + 1 FMEDocument + 1 valid node (2 statements) = 4
    assert len(statements) == 4
    node_create_statements = [s for s in statements if "CREATE (n:GraphNode" in s[0]]
    assert len(node_create_statements) == 1


def test_build_cypher_sync_skips_unknown_edge_type():
    """未知边类型被跳过。"""
    statements = build_cypher_sync(
        fmea_id="f1", document_no="PFMEA-001", title="测试",
        fmea_type="PFMEA", product_line_code="DC-DC-100",
        product_line_name="DC-DC 电源模块",
        status="approved", version=1,
        graph_data={
            "nodes": [
                {"id": "n1", "type": "FailureMode", "name": "焊接虚焊"},
                {"id": "n2", "type": "FailureEffect", "name": "功能丧失"},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "type": "UNKNOWN_EDGE"},
            ],
        },
    )
    # 没有未知边语句
    edge_statements = [s for s in statements if "UNKNOWN_EDGE" in s[0]]
    assert len(edge_statements) == 0


def test_build_cypher_sync_skips_edge_with_missing_node():
    """边的 source/target 不在 nodes 中时跳过。"""
    statements = build_cypher_sync(
        fmea_id="f1", document_no="PFMEA-001", title="测试",
        fmea_type="PFMEA", product_line_code="DC-DC-100",
        product_line_name="DC-DC 电源模块",
        status="approved", version=1,
        graph_data={
            "nodes": [
                {"id": "n1", "type": "FailureMode", "name": "焊接虚焊"},
            ],
            "edges": [
                {"source": "n1", "target": "n_missing", "type": "EFFECT_OF"},
            ],
        },
    )
    edge_statements = [s for s in statements if "EFFECT_OF" in s[0]]
    assert len(edge_statements) == 0


def test_build_cypher_sync_control_label_mapping():
    """PreventionControl/DetectionControl 映射为 Control label。"""
    statements = build_cypher_sync(
        fmea_id="f1", document_no="PFMEA-001", title="测试",
        fmea_type="PFMEA", product_line_code="DC-DC-100",
        product_line_name="DC-DC 电源模块",
        status="approved", version=1,
        graph_data={
            "nodes": [
                {"id": "n1", "type": "PreventionControl", "name": "参数监控"},
                {"id": "n2", "type": "DetectionControl", "name": "AOI检测"},
            ],
            "edges": [],
        },
    )
    node_creates = [s for s in statements if "CREATE (n:GraphNode" in s[0]]
    assert len(node_creates) == 2
    assert ":GraphNode:Control" in node_creates[0][0]
    assert ":GraphNode:Control" in node_creates[1][0]


def test_build_cypher_sync_includes_product_line_name():
    """FMEDocument CREATE 语句 params 必须包含 product_line_name。"""
    statements = build_cypher_sync(
        fmea_id="f1", document_no="PFMEA-001", title="测试",
        fmea_type="PFMEA", product_line_code="DC-DC-100",
        product_line_name="DC-DC 电源模块",
        status="approved", version=1,
        graph_data={"nodes": [{"id": "n1", "type": "FailureMode", "name": "测试"}], "edges": []},
    )
    doc_statements = [s for s in statements if "CREATE (d:FMEDocument" in s[0]]
    assert len(doc_statements) == 1
    _, params = doc_statements[0]
    assert "product_line_name" in params
    assert params["product_line_name"] == "DC-DC 电源模块"
