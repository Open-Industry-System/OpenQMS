from app.services.capa_lateral_diffusion_service import (
    normalize,
    aggregate_by_type,
)


def test_normalize():
    assert normalize("  Foo   BAR ") == "foo bar"
    assert normalize("") == ""
    assert normalize(None) == ""


def test_aggregate_unknown_type_for_untyped_pl():
    hits = [{
        "product_line_code": "PL-X",
        "product_type_code": None,
        "factory_id": "f1",
        "hit_criteria": ["shared_fmea_mode"],
        "evidence": {},
    }]
    out, truncated = aggregate_by_type(hits)
    assert out[0]["product_type_code"] == "unknown"
    assert out[0]["product_type_name"] == "未分类"
    assert out[0]["product_lines"][0]["code"] == "PL-X"
    assert truncated is False


def test_aggregate_dedup_pl_and_union_criteria():
    hits = [
        {
            "product_line_code": "PL-A",
            "product_type_code": "T",
            "factory_id": "f1",
            "hit_criteria": ["same_product_type"],
            "evidence": {},
        },
        {
            "product_line_code": "PL-A",
            "product_type_code": "T",
            "factory_id": "f1",
            "hit_criteria": ["shared_fmea_mode"],
            "evidence": {},
        },
    ]
    out, truncated = aggregate_by_type(hits)
    assert len(out[0]["product_lines"]) == 1
    assert set(out[0]["hit_criteria"]) == {"same_product_type", "shared_fmea_mode"}
    assert truncated is False


def test_truncation():
    hits = [
        {
            "product_line_code": f"PL-{i}",
            "product_type_code": "T",
            "factory_id": "f1",
            "hit_criteria": ["same_product_type"],
            "evidence": {},
        }
        for i in range(40)
    ]
    out, truncated = aggregate_by_type(hits, max_types=50, max_pls_per_type=30)
    assert truncated is True
    assert len(out[0]["product_lines"]) == 30
