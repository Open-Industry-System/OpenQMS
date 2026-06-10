import os

os.environ.setdefault("SECRET_KEY", "test-non-default-secret-key")

import pytest
from pydantic import ValidationError
from app.schemas.quality_trend import (
    QualityTrendMetadata,
    QualityTrendSummary,
    QualityTrendInterpretation,
)
from app.services.dashboard_service import WIDGET_MODULE_MAP, WIDGET_MIN_SIZES


def test_quality_trend_widget_registered():
    assert WIDGET_MODULE_MAP["quality_trend_ai_summary"] == "dashboard"
    assert WIDGET_MIN_SIZES["quality_trend_ai_summary"]["w"] >= 4
    assert WIDGET_MIN_SIZES["quality_trend_ai_summary"]["h"] >= 3


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


# ---------------------------------------------------------------------------
# Aggregation service tests
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock
from app.services.quality_trend_service import build_quality_trend_summary


@pytest.mark.anyio
async def test_returns_insufficient_data_when_no_modules_allowed():
    summary = await build_quality_trend_summary(
        db=AsyncMock(),
        filter_codes=["DC-DC-100"],
        allowed_modules=set(),
        scope_description="产品线范围：DC-DC-100",
        selected_product_line="DC-DC-100",
    )
    assert summary.risk_level == "insufficient_data"
    assert summary.ai_available is False
    assert summary.metadata.available_modules == []
    assert summary.metadata.omitted_modules == ["capa", "fmea", "spc"]


@pytest.mark.anyio
async def test_single_effective_module_is_insufficient_data():
    db = AsyncMock()
    db.scalar.side_effect = [
        4,   # SPC current window
        1,   # SPC previous window
        2,   # SPC open alarms
    ]

    summary = await build_quality_trend_summary(
        db=db,
        filter_codes=["DC-DC-100"],
        allowed_modules={"spc"},
        scope_description="产品线范围：DC-DC-100",
        selected_product_line="DC-DC-100",
    )
    assert summary.risk_level == "insufficient_data"
    assert summary.ai_available is False
    assert [e.id for e in summary.evidence] == ["spc_alarm_count", "spc_open_unack"]


@pytest.mark.anyio
async def test_detects_open_spc_and_capa_risk():
    db = AsyncMock()
    db.scalar.side_effect = [
        4,   # SPC current window
        1,   # SPC previous window
        2,   # SPC open alarms
        3,   # CAPA open
        2,   # CAPA overdue
    ]

    summary = await build_quality_trend_summary(
        db=db,
        filter_codes=["DC-DC-100"],
        allowed_modules={"spc", "capa"},
        scope_description="产品线范围：DC-DC-100",
        selected_product_line="DC-DC-100",
    )
    assert summary.risk_level in {"medium", "high"}
    assert any(e.id == "spc_alarm_count" for e in summary.evidence)
    assert any(e.id == "capa_overdue_count" for e in summary.evidence)
    assert summary.ai_available is True


@pytest.mark.anyio
async def test_scope_hash_is_order_independent():
    from app.services.quality_trend_service import build_scope_hash
    h_ab = await build_scope_hash(["A", "B"])
    h_ba = await build_scope_hash(["B", "A"])
    h_dup = await build_scope_hash(["A", "B", "A"])
    assert h_ab == h_ba
    assert h_ab == h_dup
    assert h_ab.startswith("sha256:")
