from app.services.recommendation_service import RecommendationService
from app.schemas.recommendation import SuggestionList


def test_pfmea_prompt_builds_via_real_build_prompt_path():
    """Exercises the real _build_prompt merge (request.context as current_context,
    then _assemble_context top-level keys) to catch prompt/context field mismatches.

    This is the regression guard for review fix #1: the prompt must use {product_line}
    (what _assemble_context returns), not {product_line_code}."""
    svc = RecommendationService.__new__(RecommendationService)  # bypass __init__ deps; _build_prompt only needs PROMPT_TEMPLATES (class-level)
    # Shape mirrors what _assemble_context(fmea, request) returns:
    #   {fmea_type, product_line, current_context: request.context, historical_patterns}
    # and request.context (ScopeTagField) provides fmea_title/task/team.
    request_context = {"fmea_title": "SMT焊接生产线", "task": "PFMEA分析", "team": "张工"}
    ctx = {
        "fmea_type": "PFMEA",
        "product_line": "DC-DC-100",          # _assemble_context returns THIS key (not product_line_code)
        "current_context": request_context,
        "historical_patterns": "无",
    }
    for trig in ("pfmea_tool", "pfmea_trend"):
        rendered = svc._build_prompt(trig, ctx)
        # the product-line line must be filled (not empty), proving {product_line} resolved
        assert "产品线: DC-DC-100" in rendered, f"{trig} did not resolve {{product_line}} — check prompt placeholder"
        assert "SMT焊接生产线" in rendered          # {fmea_title} resolved from request.context
        assert "PFMEA分析" in rendered              # {task}
        assert "suggestions" in rendered
        assert "confidence" in rendered             # schema key, not "reason"
        # no leftover unresolved placeholders for the keys we expect to provide
        assert "{product_line}" not in rendered
        assert "{fmea_title}" not in rendered
        assert "{historical_patterns}" not in rendered


def test_pfmea_tool_llm_output_passes_suggestionlist_validation():
    """LLM output shaped per the prompt must pass SuggestionList validation
    (this is the gate that would otherwise drop to empty rule/graph fallback)."""
    raw = {
        "suggestions": [
            {"name": "过程流程图", "confidence": 0.9, "explanation": "PFMEA标准起点"},
            {"name": "鱼骨图(4M分析)", "confidence": 0.8, "explanation": "识别4M失效起因"},
        ]
    }
    validated = SuggestionList.model_validate(raw)
    assert len(validated.suggestions) == 2
    assert validated.suggestions[0].name == "过程流程图"


def test_rule_engine_returns_empty_for_pfmea_scope_triggers():
    from app.services.recommendation_service import RuleEngine
    engine = RuleEngine()
    for trig in ("pfmea_tool", "pfmea_trend"):
        result = engine.evaluate(trig, {"task": "PFMEA"})
        assert list(result.suggestions) == []


def test_rule_engine_uses_pfmea_verb_patterns_for_failure_mode():
    from app.services.recommendation_service import RuleEngine
    engine = RuleEngine()
    result = engine.evaluate("failure_mode", {"function_description": "焊接电阻到PCB", "fmea_type": "PFMEA"})
    assert any("焊点虚焊" == s.name for s in result.suggestions)


def test_rule_engine_uses_dfmea_verb_patterns_by_default():
    from app.services.recommendation_service import RuleEngine
    engine = RuleEngine()
    result = engine.evaluate("failure_mode", {"function_description": "采集温度信号", "fmea_type": "DFMEA"})
    assert any("无法采集" == s.name for s in result.suggestions)
