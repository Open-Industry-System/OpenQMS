import uuid
import pytest
from app.services.recommendation_sources import FMEAGraphSource
from app.services.recommendation_types import RecommendationContext


@pytest.fixture
def sample_graph():
    fm_id = str(uuid.uuid4())
    cause_id = str(uuid.uuid4())
    func_id = str(uuid.uuid4())
    return {
        "nodes": [
            {"id": func_id, "type": "ProcessStepFunction", "name": "焊接功能"},
            {"id": fm_id, "type": "FailureMode", "name": "焊接虚焊"},
            {"id": cause_id, "type": "FailureCause", "name": "焊接参数偏移"},
        ],
        "edges": [
            {"source": func_id, "target": fm_id, "type": "HAS_FAILURE_MODE"},
            {"source": cause_id, "target": fm_id, "type": "CAUSE_OF"},
        ],
    }


class TestFMEAGraphSource:
    @pytest.mark.asyncio
    async def test_linked_fmea_with_failuremode_node(self, sample_graph):
        source = FMEAGraphSource()
        fmea_id = uuid.uuid4()
        fm_id = sample_graph["nodes"][1]["id"]
        ctx = RecommendationContext(
            capa_data={
                "fmea_ref_id": fmea_id,
                "fmea_node_id": fm_id,
                "d2_description": "",
            },
            user_product_lines=None,
            stage="d4",
            linked_fmea={"fmea_id": fmea_id, "document_no": "PFMEA-001", "graph_data": sample_graph},
        )
        results = await source.retrieve(ctx)
        assert len(results) == 1
        assert results[0].content == "焊接参数偏移"
        assert results[0].source == "fmea_graph"
        assert results[0].metadata["failure_mode_node_id"] == fm_id

    @pytest.mark.asyncio
    async def test_no_linked_fmea_returns_empty(self):
        source = FMEAGraphSource()
        ctx = RecommendationContext(
            capa_data={"fmea_ref_id": None, "fmea_node_id": None},
            user_product_lines=None,
            stage="d4",
        )
        results = await source.retrieve(ctx)
        assert results == []
