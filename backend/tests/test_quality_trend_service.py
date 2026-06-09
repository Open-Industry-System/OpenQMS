import pytest
from pydantic import ValidationError
from app.schemas.quality_trend import (
    QualityTrendMetadata,
    QualityTrendSummary,
    QualityTrendInterpretation,
)


def test_quality_trend_summary_metadata_fields():
    summary = QualityTrendSummary(
        risk_level="medium",
        headline="SPC 异常增加",
        evidence=[{"id": "spc_alarm_count", "label": "SPC 异常告警", "value": 4, "trend": "+2", "severity": "warning"}],
        actions=[{"priority": "high", "text": "复核异常"}],
        data_window_days=30,
        generated_at="2026-06-09T00:00:00Z",
        evidence_hash="hash",
        scope_hash="scope_hash_abc",
        ai_available=True,
        metadata=QualityTrendMetadata(
            omitted_modules=[],
            available_modules=["spc", "capa"],
            scope_description="产品线范围：DC-DC-100",
            selected_product_line="DC-DC-100",
        ),
    )
    assert summary.metadata.available_modules == ["spc", "capa"]
    assert summary.metadata.omitted_modules == []


def test_quality_trend_interpretation_instantiation():
    interp = QualityTrendInterpretation(
        summary="趋势分析",
        possible_causes=["原因1"],
        impact_scope=["DC-DC-100"],
        recommended_actions=[{"priority": "high", "action": "采取行动", "reason": "原因"}],
        evidence_refs=["ref1"],
        confidence="high",
        model="claude",
        evidence_hash="hash",
        scope_hash="scope",
        generated_at="2026-06-09T00:00:00Z",
    )
    assert interp.confidence == "high"
    assert interp.cached is False  # default


def test_quality_trend_summary_default_window_days():
    summary = QualityTrendSummary(
        risk_level="low",
        headline="正常",
        evidence=[],
        actions=[],
        generated_at="2026-06-09T00:00:00Z",
        evidence_hash="hash",
        scope_hash="scope",
        ai_available=True,
    )
    assert summary.data_window_days == 30


def test_invalid_risk_level_raises_validation_error():
    with pytest.raises(ValidationError):
        QualityTrendSummary(
            risk_level="invalid_level",
            headline="测试",
            evidence=[],
            actions=[],
            generated_at="2026-06-09T00:00:00Z",
            evidence_hash="hash",
            scope_hash="scope",
            ai_available=True,
        )
