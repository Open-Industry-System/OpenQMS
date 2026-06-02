from app.services.graph_projection_service import build_cypher_sync


def test_build_cypher_sync_includes_product_line_name():
    """FMEDocument CREATE 语句 params 必须包含 product_line_name。"""
    statements = build_cypher_sync(
        fmea_id="f1", document_no="PFMEA-001", title="测试",
        fmea_type="PFMEA", product_line_code="DC-DC-100",
        product_line_name="DC-DC 电源模块",
        status="approved", version=1,
        graph_data={"nodes": [{"id": "n1", "type": "FailureMode", "name": "测试"}], "edges": []},
    )
    # 找到 CREATE FMEDocument 语句
    doc_statements = [s for s in statements if "CREATE (d:FMEDocument" in s[0]]
    assert len(doc_statements) == 1
    _, params = doc_statements[0]
    assert "product_line_name" in params
    assert params["product_line_name"] == "DC-DC 电源模块"
