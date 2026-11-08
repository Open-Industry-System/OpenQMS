from app.schemas.fmea import (
    FMEAUpdate, GraphNodeSchema, RecommendationAdoption, TransitionRequest,
)


def test_recommendation_adoption_roundtrip():
    a = RecommendationAdoption(
        field_id="fm_node_123", recommendation_id="rec_abc456",
        source="graph", stage_index=2, adopted_text="焊接电流不足",
    )
    assert a.recommendation_id == "rec_abc456"
    assert a.stage_index == 2


def test_fmea_update_has_adoptions_field():
    u = FMEAUpdate(adoptions=[{
        "field_id": "fm1", "recommendation_id": "r1",
        "source": "llm", "stage_index": 0, "adopted_text": "x",
    }])
    assert u.adoptions is not None and u.adoptions[0].recommendation_id == "r1"


def test_transition_request_accepts_reason():
    t = TransitionRequest(target_status="rework", reason="数据不完整")
    assert t.reason == "数据不完整"
    assert TransitionRequest(target_status="approved").reason is None


def test_graph_node_risk_fields_and_canonical_status():
    n = GraphNodeSchema(
        id="fc1", type="FailureCause", name="原因",
        control_sufficiency_reason="现有控制充分",
        management_review_evidence="管理层已评审",
        recommended_action_status="not_executed",
    )
    assert n.control_sufficiency_reason == "现有控制充分"
    assert n.recommended_action_status == "not_executed"


def test_recommended_action_status_rejects_legacy_value():
    import pytest
    with pytest.raises(Exception):
        GraphNodeSchema(id="ra1", type="RecommendedAction", name="m",
                        recommended_action_status="undecided")


def test_graph_node_distinguishes_absent_and_explicit_empty_characteristics():
    absent = GraphNodeSchema(id="sf-legacy", type="ProcessStepFunction", name="旧功能")
    explicit_empty = GraphNodeSchema(
        id="sf-empty", type="ProcessStepFunction", name="新功能", characteristics=[],
    )

    assert "characteristics" not in absent.model_fields_set
    assert absent.characteristics is None
    assert "characteristics" in explicit_empty.model_fields_set
    assert explicit_empty.characteristics == []
