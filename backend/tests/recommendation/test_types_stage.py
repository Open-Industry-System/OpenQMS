from app.services.recommendation_types import RecommendationCandidate, RecommendationResult, StageRun


def test_stage_run_defaults():
    s = StageRun(index=3, name="semantic", source="semantic_search", status="done")
    assert s.hit_count == 0 and s.summary == "" and s.error is None
    assert s.llm_attempted is None and s.llm_succeeded is None and s.llm_failed is None


def test_to_d4_schema_emits_stage_index():
    c = RecommendationCandidate(source="fmea_graph", content="x", category=None, confidence=0.5,
                                 match_reason="r", metadata={"stage_index": 2, "failure_cause_node_id": "c1"})
    assert c.to_d4_schema()["stage_index"] == 2


def test_to_d5_suggestion_schema_emits_stage_index():
    c = RecommendationCandidate(source="rule_engine_measure", content="m", category="预防措施",
                                confidence=0.5, match_reason="r", metadata={"stage_index": 10})
    assert c.to_d5_suggestion_schema()["stage_index"] == 10
    assert c.to_d5_suggestion_schema()["match_source"] == "rule"


def test_to_d5_suggestion_schema_historical_capa_measure_provenance():
    # historical_capa_measure (D5) must emit source_capa_id/source_capa_document_no
    # so D5 adopt/audit provenance is preserved (not just historical_capa).
    c = RecommendationCandidate(source="historical_capa_measure", content="更换供应商批次",
                                category="纠正措施", confidence=0.8, match_reason="历史 CAPA 相似措施",
                                metadata={"stage_index": 5, "historical_capa_id": "capa-abc",
                                          "document_no": "8D-2026-001"})
    schema = c.to_d5_suggestion_schema()
    assert schema["match_source"] == "historical_capa_measure"
    assert schema["source_capa_id"] == "capa-abc"
    assert schema["source_capa_document_no"] == "8D-2026-001"


def test_to_d4_schema_knowledge_entry_provenance():
    entry_id = "entry-uuid-1"
    capa_id = "capa-uuid-1"
    c = RecommendationCandidate(
        source="knowledge_entry",
        content="沉淀经验摘要",
        category=None,
        confidence=0.7,
        match_reason="知识库条目相似命中",
        metadata={
            "stage_index": 5,
            "entry_id": entry_id,
            "document_no": "8D-KNOW-001",
            "capa_id": capa_id,
        },
    )
    schema = c.to_d4_schema()
    assert schema["match_source"] == "knowledge_entry"
    assert schema["source_knowledge_entry_id"] == entry_id
    assert schema["source_capa_document_no"] == "8D-KNOW-001"
    assert schema["source_capa_id"] == capa_id


def test_to_d5_suggestion_schema_knowledge_entry_provenance():
    entry_id = "entry-uuid-2"
    capa_id = "capa-uuid-2"
    c = RecommendationCandidate(
        source="knowledge_entry",
        content="知识条目措施",
        category="预防措施",
        confidence=0.65,
        match_reason="知识库条目相似命中",
        metadata={
            "stage_index": 5,
            "entry_id": entry_id,
            "document_no": "8D-KNOW-002",
            "capa_id": capa_id,
        },
    )
    schema = c.to_d5_suggestion_schema()
    assert schema["match_source"] == "knowledge_entry"
    assert schema["source_knowledge_entry_id"] == entry_id
    assert schema["source_capa_document_no"] == "8D-KNOW-002"
    assert schema["source_capa_id"] == capa_id


def test_recommendation_result_has_stages():
    r = RecommendationResult(items=[], stages=[StageRun(1, "ctx", "internal", "done")])
    assert len(r.stages) == 1
