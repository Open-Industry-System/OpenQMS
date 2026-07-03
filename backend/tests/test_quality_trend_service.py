import os

os.environ.setdefault("SECRET_KEY", "test-non-default-secret-key")


import pytest
from pydantic import ValidationError

from app.schemas.quality_trend import (
    QualityTrendInterpretation,
    QualityTrendMetadata,
    QualityTrendSummary,
)
from app.services import quality_trend_service
from app.services.dashboard_service import WIDGET_MIN_SIZES, WIDGET_MODULE_MAP
from app.services.quality_trend_service import LLMNotConfiguredError


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


@pytest.mark.asyncio
async def test_interpret_raises_llm_not_configured_when_provider_unconfigured(
    db, admin_user, default_factory, monkeypatch
):
    """build_client raises ProviderNotConfiguredError -> interpret translates to
    LLMNotConfiguredError and writes llm_not_configured audit."""
    from sqlalchemy import select

    from app.models.audit import AuditLog
    from app.services.agent import provider_adapter

    async def _raise(db):
        raise provider_adapter.ProviderNotConfiguredError("no cfg")

    monkeypatch.setattr(provider_adapter, "build_client", _raise)
    # force past rate limit + sufficient data + cache miss
    monkeypatch.setattr(quality_trend_service, "_enforce_rate_limit", lambda uid: None)

    from app.schemas.quality_trend import QualityTrendMetadata, QualityTrendSummary
    async def _summary(*a, **k):
        return QualityTrendSummary(
            risk_level="high", headline="h", evidence=[], actions=[],
            data_window_days=30, generated_at="2026-06-30T00:00:00Z",
            evidence_hash="sha256:x", scope_hash="", ai_available=True,
            metadata=QualityTrendMetadata(omitted_modules=[], available_modules=["spc"]),
        )
    monkeypatch.setattr(quality_trend_service, "build_quality_trend_summary", _summary)
    monkeypatch.setattr(quality_trend_service, "_get_cached_interpretation", lambda k: None)

    with pytest.raises(LLMNotConfiguredError):
        await quality_trend_service.interpret_quality_trend(
            db=db, user_id=str(admin_user.user_id),
            factory_id=default_factory.id, tenant_schema="public",
            filter_codes=["DC-DC-100"], allowed_modules={"spc"},
            scope_description="d", selected_product_line="DC-DC-100",
            scope_hash="hash1",
        )
    rows = (await db.execute(select(AuditLog).where(AuditLog.action == "AI_TREND_INTERPRET"))).scalars().all()
    assert any(r.new_values.get("status") == "llm_not_configured" for r in rows)


@pytest.mark.asyncio
async def test_interpret_raises_llm_not_configured_even_when_cache_warm(
    db, admin_user, default_factory, monkeypatch
):
    """Regression: unconfigured LLM must raise before cache lookup, even if a warm
    cached entry exists for the same scope_hash."""
    from sqlalchemy import select

    from app.models.audit import AuditLog
    from app.services.agent import provider_adapter

    async def _raise(db):
        raise provider_adapter.ProviderNotConfiguredError("no cfg")

    monkeypatch.setattr(provider_adapter, "build_client", _raise)
    monkeypatch.setattr(quality_trend_service, "_enforce_rate_limit", lambda uid: None)

    from app.schemas.quality_trend import QualityTrendInterpretation, QualityTrendMetadata, QualityTrendSummary
    async def _summary(*a, **k):
        return QualityTrendSummary(
            risk_level="high", headline="h", evidence=[], actions=[],
            data_window_days=30, generated_at="2026-06-30T00:00:00Z",
            evidence_hash="sha256:x", scope_hash="", ai_available=True,
            metadata=QualityTrendMetadata(omitted_modules=[], available_modules=["spc"]),
        )
    monkeypatch.setattr(quality_trend_service, "build_quality_trend_summary", _summary)

    scope_hash = "hash1"
    cache_key = f"{scope_hash}:30:sha256:x"
    quality_trend_service._set_cached_interpretation(
        cache_key,
        QualityTrendInterpretation(
            summary="cached", possible_causes=[], impact_scope=[],
            recommended_actions=[], evidence_refs=[], confidence="low",
            model="cached-model", evidence_hash="sha256:x", scope_hash=scope_hash,
            generated_at="2026-06-30T00:00:00Z",
        ),
    )

    with pytest.raises(LLMNotConfiguredError):
        await quality_trend_service.interpret_quality_trend(
            db=db, user_id=str(admin_user.user_id),
            factory_id=default_factory.id, tenant_schema="public",
            filter_codes=["DC-DC-100"], allowed_modules={"spc"},
            scope_description="d", selected_product_line="DC-DC-100",
            scope_hash=scope_hash,
        )
    rows = (await db.execute(select(AuditLog).where(AuditLog.action == "AI_TREND_INTERPRET"))).scalars().all()
    assert any(r.new_values.get("status") == "llm_not_configured" for r in rows)
    assert not any(r.new_values.get("status") == "cache_hit" for r in rows)
