import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.recommendation_sources import (
    FMEAGraphSource,
    SemanticSearchSource,
    HistoricalCAPASource,
    RuleEngineSource,
    RuleEngineMeasureSource,
    FMEAControlExpander,
)
from app.services.recommendation_types import RecommendationContext, RecommendationCandidate


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


class TestHistoricalCAPASource:
    @pytest.mark.asyncio
    async def test_empty_user_pls_returns_empty(self):
        """Empty user_pls means no permission — should return empty without querying DB."""
        mock_db = AsyncMock()
        mock_embedding = AsyncMock()

        source = HistoricalCAPASource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接问题", "product_line_code": "DC-DC-100"},
            user_product_lines=[],  # no permission
            stage="d4",
        )
        results = await source.retrieve(ctx)
        assert results == []
        mock_embedding.embed.assert_not_called()
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_retrieve_returns_historical_capa_candidates(self):
        """HistoricalCAPASource returns candidates from D8_CLOSURE CAPA."""
        mock_db = AsyncMock()
        mock_row = {
            "entity_id": uuid.uuid4(),
            "chunk_text": "温度不稳定",
            "similarity": 0.75,
            "document_no": "8D-2026-001",
            "severity": "严重",
            "source_updated_at": "2026-05-01",
            "d4_root_cause": "温度不稳定",
            "d5_correction": "增加温控",
            "product_line_code": "DC-DC-100",
        }
        mock_mappings = MagicMock()
        mock_mappings.__iter__.return_value = iter([mock_row])
        # mappings() is called as a method and returns an iterable
        mock_execute_result = MagicMock()
        mock_execute_result.mappings.return_value = mock_mappings
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        source = HistoricalCAPASource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接温度问题", "product_line_code": "DC-DC-100"},
            user_product_lines=["DC-DC-100"],
            stage="d4",
        )
        results = await source.retrieve(ctx)
        assert len(results) >= 1
        assert results[0].source == "historical_capa"
        assert results[0].content == "温度不稳定"
        assert results[0].confidence == pytest.approx(0.6, abs=0.01)  # 0.75 * 0.8 = 0.6

        # Verify SQL contains CAST and D8_CLOSURE
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "CAST(:query_vector AS vector)" in sql_text
        assert "D8_CLOSURE" in sql_text


class TestSemanticSearchSourceWithGraph:
    @pytest.mark.asyncio
    async def test_d4_returns_failurecause_candidate(self):
        """SemanticSearchSource returns FailureCause candidate with graph backtracking."""
        import uuid

        fmea_id = uuid.uuid4()
        node_id = str(uuid.uuid4())
        fm_id = str(uuid.uuid4())

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(fmea_id=fmea_id, node_id=node_id, similarity=0.8, product_line_code="DC-DC-100")
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        doc = {
            "fmea_id": fmea_id,
            "document_no": "PFMEA-001",
            "product_line_code": "DC-DC-100",
            "graph_data": {
                "nodes": [
                    {"id": node_id, "type": "FailureCause", "name": "焊接参数偏移"},
                    {"id": fm_id, "type": "FailureMode", "name": "焊接虚焊"},
                ],
                "edges": [
                    {"source": node_id, "target": fm_id, "type": "CAUSE_OF"},
                ],
            },
        }

        source = SemanticSearchSource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接问题", "product_line_code": "DC-DC-100"},
            user_product_lines=["DC-DC-100"],
            stage="d4",
            fmea_docs=[doc],
        )
        results = await source.retrieve(ctx)
        assert len(results) == 1
        assert results[0].content == "焊接参数偏移"
        assert results[0].source == "semantic_search"
        assert results[0].confidence == pytest.approx(0.56, abs=0.01)  # 0.8 * 0.7 = 0.56
        assert results[0].metadata["failure_mode_node_id"] == fm_id
        assert results[0].metadata["failure_mode_name"] == "焊接虚焊"

    @pytest.mark.asyncio
    async def test_empty_user_pls_returns_empty(self):
        """Empty user_pls means no permission — should return empty without querying DB."""
        mock_db = AsyncMock()
        mock_embedding = AsyncMock()

        source = SemanticSearchSource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接问题", "product_line_code": "DC-DC-100"},
            user_product_lines=[],  # no permission
            stage="d4",
            fmea_docs=[],
        )
        results = await source.retrieve(ctx)
        assert results == []
        mock_embedding.embed.assert_not_called()
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_no_pl_filter(self):
        """Admin (user_pls=None) should not add PL filter to SQL."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        source = SemanticSearchSource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接问题"},
            user_product_lines=None,  # admin
            stage="d4",
            fmea_docs=[],
        )
        results = await source.retrieve(ctx)
        assert results == []

        # Verify SQL does NOT contain ANY filter
        call_args = mock_db.execute.call_args
        sql_text = str(call_args[0][0])
        assert "product_line_code = ANY" not in sql_text


class TestSemanticSearchSource:
    @pytest.mark.asyncio
    async def test_d4_uses_d2_description(self):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        source = SemanticSearchSource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接虚焊问题", "d4_root_cause": ""},
            user_product_lines=None,
            stage="d4",
            fmea_docs=[],
        )
        results = await source.retrieve(ctx)
        assert results == []
        mock_embedding.embed.assert_called_once_with(["焊接虚焊问题"])

    @pytest.mark.asyncio
    async def test_d5_uses_d4_root_cause(self):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        source = SemanticSearchSource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接虚焊问题", "d4_root_cause": "参数偏移"},
            user_product_lines=None,
            stage="d5",
            fmea_docs=[],
        )
        results = await source.retrieve(ctx)
        assert results == []
        mock_embedding.embed.assert_called_once_with(["参数偏移"])

    @pytest.mark.asyncio
    async def test_d5_falls_back_to_d2_when_d4_empty(self):
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_embedding = AsyncMock()
        mock_embedding.embed = AsyncMock(return_value=[[0.1] * 768])

        source = SemanticSearchSource(mock_db, mock_embedding)
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接虚焊问题", "d4_root_cause": ""},
            user_product_lines=None,
            stage="d5",
            fmea_docs=[],
        )
        results = await source.retrieve(ctx)
        assert results == []
        mock_embedding.embed.assert_called_once_with(["焊接虚焊问题"])


class TestRuleEngineSource:
    @pytest.mark.asyncio
    async def test_returns_candidates_for_d2_text(self):
        source = RuleEngineSource()
        ctx = RecommendationContext(
            capa_data={"d2_description": "密封失效"},
            user_product_lines=None,
            stage="d4",
        )
        results = await source.retrieve(ctx)
        # RuleEngine should produce at least one suggestion for "密封失效"
        assert len(results) >= 1
        assert results[0].source == "rule_engine"
        assert results[0].confidence <= 0.5  # scaled by 0.5
        assert results[0].match_reason == "规则引擎推断"

    @pytest.mark.asyncio
    async def test_empty_d2_returns_empty(self):
        source = RuleEngineSource()
        ctx = RecommendationContext(
            capa_data={"d2_description": ""},
            user_product_lines=None,
            stage="d4",
        )
        results = await source.retrieve(ctx)
        assert results == []


class TestRuleEngineMeasureSource:
    @pytest.mark.asyncio
    async def test_returns_measure_candidates(self):
        source = RuleEngineMeasureSource()
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接虚焊"},
            user_product_lines=None,
            stage="d5",
        )
        results = await source.retrieve(ctx)
        assert len(results) >= 1
        assert results[0].source == "rule_engine"
        # Category should be mapped correctly
        assert results[0].category in ("预防措施", "探测措施")

    @pytest.mark.asyncio
    async def test_ap_lookup_from_linked_fmea(self):
        fmea_id = uuid.uuid4()
        fm_id = str(uuid.uuid4())
        source = RuleEngineMeasureSource()
        ctx = RecommendationContext(
            capa_data={"d2_description": "焊接虚焊", "fmea_node_id": fm_id},
            user_product_lines=None,
            stage="d5",
            linked_fmea={
                "fmea_id": fmea_id,
                "document_no": "PFMEA-001",
                "graph_data": {
                    "nodes": [
                        {"id": fm_id, "type": "FailureMode", "name": "焊接虚焊", "ap": "H"},
                    ],
                    "edges": [],
                },
            },
        )
        results = await source.retrieve(ctx)
        assert len(results) >= 1
        # match_reason should contain AP=H
        assert "AP=H" in results[0].match_reason


class TestFMEAControlExpander:
    @pytest.mark.asyncio
    async def test_expands_prevention_and_detection_controls(self):
        expander = FMEAControlExpander()

        fmea_id = str(uuid.uuid4())
        cause_id = str(uuid.uuid4())
        fm_id = str(uuid.uuid4())
        prev_id = str(uuid.uuid4())
        det_id = str(uuid.uuid4())

        cause_candidate = RecommendationCandidate(
            source="semantic_search",
            content="焊接参数偏移",
            category=None,
            confidence=0.7,
            match_reason="语义匹配",
            metadata={
                "failure_cause_node_id": cause_id,
                "failure_mode_node_id": fm_id,
                "failure_mode_name": "焊接虚焊",
                "fmea_id": fmea_id,
            },
        )

        fmea_docs = [{
            "fmea_id": fmea_id,
            "document_no": "PFMEA-001",
            "graph_data": {
                "nodes": [
                    {"id": cause_id, "type": "FailureCause", "name": "焊接参数偏移"},
                    {"id": fm_id, "type": "FailureMode", "name": "焊接虚焊"},
                    {"id": prev_id, "type": "PreventionControl", "name": "参数监控"},
                    {"id": det_id, "type": "DetectionControl", "name": "AOI检测"},
                ],
                "edges": [
                    {"source": cause_id, "target": fm_id, "type": "CAUSE_OF"},
                    {"source": cause_id, "target": prev_id, "type": "PREVENTED_BY"},
                    {"source": cause_id, "target": det_id, "type": "DETECTED_BY"},
                ],
            },
        }]

        results = await expander.expand([cause_candidate], fmea_docs)

        assert len(results) == 2
        prevention = [r for r in results if r.metadata.get("control_type") == "prevention"]
        detection = [r for r in results if r.metadata.get("control_type") == "detection"]
        assert len(prevention) == 1
        assert len(detection) == 1
        assert prevention[0].content == "参数监控"
        assert detection[0].content == "AOI检测"
        assert prevention[0].confidence == 0.6
        assert detection[0].confidence == 0.55

    @pytest.mark.asyncio
    async def test_deduplicates_same_control(self):
        expander = FMEAControlExpander()

        fmea_id = str(uuid.uuid4())
        cause_id = str(uuid.uuid4())
        fm_id = str(uuid.uuid4())
        prev_id = str(uuid.uuid4())

        # Two cause candidates pointing to the same control
        candidates = [
            RecommendationCandidate(
                source="semantic_search",
                content="原因A",
                category=None,
                confidence=0.7,
                match_reason="",
                metadata={
                    "failure_cause_node_id": cause_id,
                    "failure_mode_node_id": fm_id,
                    "fmea_id": fmea_id,
                },
            ),
            RecommendationCandidate(
                source="semantic_search",
                content="原因B",
                category=None,
                confidence=0.7,
                match_reason="",
                metadata={
                    "failure_cause_node_id": cause_id,
                    "failure_mode_node_id": fm_id,
                    "fmea_id": fmea_id,
                },
            ),
        ]

        fmea_docs = [{
            "fmea_id": fmea_id,
            "document_no": "PFMEA-001",
            "graph_data": {
                "nodes": [
                    {"id": cause_id, "type": "FailureCause", "name": "原因"},
                    {"id": fm_id, "type": "FailureMode", "name": "失效"},
                    {"id": prev_id, "type": "PreventionControl", "name": "监控"},
                ],
                "edges": [
                    {"source": cause_id, "target": fm_id, "type": "CAUSE_OF"},
                    {"source": cause_id, "target": prev_id, "type": "PREVENTED_BY"},
                ],
            },
        }]

        results = await expander.expand(candidates, fmea_docs)
        # Should deduplicate — only one control returned
        assert len(results) == 1
