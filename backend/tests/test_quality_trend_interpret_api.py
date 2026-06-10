import os

os.environ.setdefault("SECRET_KEY", "test-non-default-secret-key")

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from app.core.permissions import PermissionLevel, get_current_user
from app.database import get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.user import User
from app.services.quality_trend_service import RateLimitError


@pytest.fixture(autouse=True)
def _clear_cache_and_rate_limit(monkeypatch):
    from app.services import quality_trend_service
    quality_trend_service._interpret_cache.clear()
    quality_trend_service._rate_limit.clear()


def _make_user():
    user = MagicMock(spec=User)
    user.user_id = uuid.uuid4()
    user.role_id = uuid.uuid4()
    user.role_definition = MagicMock()
    user.role_definition.bypass_row_level_security = True
    return user


class FakeLLMProvider:
    def __init__(self):
        self.last_prompt: str | None = None

    async def complete(self, prompt: str, response_schema: dict) -> dict:
        self.last_prompt = prompt
        return {
            "summary": "SPC 告警与 CAPA 超期共同推高趋势风险。",
            "possible_causes": ["制程波动未及时确认"],
            "impact_scope": ["DC-DC-100"],
            "recommended_actions": [
                {"priority": "high", "action": "复核未确认 SPC 告警", "reason": "SPC 告警数在 30 天内有上升趋势"}
            ],
            "evidence_refs": ["spc_alarm_count", "capa_overdue_count"],
            "confidence": "medium",
        }


async def _call_interpret(llm_provider):
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.scalar = AsyncMock(side_effect=[4, 1, 2, 3, 2])
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    async def mock_get_db():
        return db

    async def mock_get_current_user():
        return _make_user()

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.state.llm_provider = llm_provider

    async def mock_get_user_permission(user, module, db):
        return PermissionLevel.VIEW if module.value in {"dashboard", "spc", "capa", "fmea"} else PermissionLevel.NONE

    try:
        with patch("app.core.permissions.get_user_permission", new=mock_get_user_permission):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/dashboard/widgets/quality-trend/interpret",
                    json={"product_line": "DC-DC-100"},
                )
    finally:
        app.dependency_overrides.clear()
        if hasattr(app.state, "llm_provider"):
            delattr(app.state, "llm_provider")

    return response, db


@pytest.mark.anyio
async def test_interpret_returns_429_when_rate_limited_and_writes_audit(monkeypatch):
    def always_limited(user_id):
        raise RateLimitError("rate limit exceeded for user")

    monkeypatch.setattr("app.services.quality_trend_service._enforce_rate_limit", always_limited)
    response, db = await _call_interpret(FakeLLMProvider())
    assert response.status_code == 429
    audit = next(obj for obj in db.add.call_args_list if isinstance(obj.args[0], AuditLog)).args[0]
    assert audit.new_values["status"] == "rate_limited"
    assert "scope_hash" in audit.new_values
    assert "product_line_codes" in audit.new_values


@pytest.mark.anyio
async def test_interpret_returns_503_when_llm_not_configured_and_writes_audit():
    response, db = await _call_interpret(None)
    assert response.status_code == 503
    audit = next(obj for obj in db.add.call_args_list if isinstance(obj.args[0], AuditLog)).args[0]
    assert audit.table_name == "quality_trends"
    assert audit.action == "AI_TREND_INTERPRET"
    assert audit.new_values["status"] == "llm_not_configured"


@pytest.mark.anyio
async def test_interpret_returns_success_with_fake_llm_and_writes_audit():
    provider = FakeLLMProvider()
    response, db = await _call_interpret(provider)
    assert response.status_code == 200
    body = response.json()
    assert body["evidence_hash"] != ""
    assert body["scope_hash"] != ""
    assert body["cached"] is False
    # Verify prompt contains evidence ids so LLM knows valid refs
    assert provider.last_prompt is not None
    assert "id=spc_alarm_count" in provider.last_prompt
    assert "id=capa_overdue_count" in provider.last_prompt
    assert "evidence_refs 必须且只能使用上面列出的 evidence id" in provider.last_prompt
    audit = next(obj for obj in db.add.call_args_list if isinstance(obj.args[0], AuditLog)).args[0]
    assert audit.table_name == "quality_trends"
    assert audit.action == "AI_TREND_INTERPRET"
    assert audit.new_values["status"] == "success"
    assert audit.new_values["evidence_hash"] == body["evidence_hash"]


@pytest.mark.anyio
async def test_interpret_rejects_unknown_evidence_ref_without_caching():
    class BadRefsProvider:
        async def complete(self, prompt: str, response_schema: dict) -> dict:
            return {
                "summary": "bad",
                "possible_causes": [],
                "impact_scope": [],
                "recommended_actions": [],
                "evidence_refs": ["filtered_or_missing_ref"],
                "confidence": "low",
            }

    response, db = await _call_interpret(BadRefsProvider())
    assert response.status_code == 502
    audit = next(obj for obj in db.add.call_args_list if isinstance(obj.args[0], AuditLog)).args[0]
    assert audit.new_values["status"] == "parse_failed"


@pytest.mark.anyio
async def test_interpret_returns_422_for_insufficient_data_and_writes_audit(monkeypatch):
    async def insufficient_summary(*args, **kwargs):
        from app.schemas.quality_trend import QualityTrendMetadata, QualityTrendSummary

        return QualityTrendSummary(
            risk_level="insufficient_data",
            headline="数据不足以判断趋势",
            evidence=[],
            actions=[],
            data_window_days=30,
            generated_at="2026-06-09T00:00:00Z",
            evidence_hash="sha256:empty",
            scope_hash="",
            ai_available=False,
            metadata=QualityTrendMetadata(omitted_modules=["spc", "capa", "fmea"], available_modules=[]),
        )

    monkeypatch.setattr("app.services.quality_trend_service.build_quality_trend_summary", insufficient_summary)
    response, db = await _call_interpret(FakeLLMProvider())
    assert response.status_code == 422
    audit = next(obj for obj in db.add.call_args_list if isinstance(obj.args[0], AuditLog)).args[0]
    assert audit.new_values["status"] == "insufficient_data"


@pytest.mark.anyio
async def test_interpret_audits_llm_provider_failure():
    class FailingProvider:
        async def complete(self, prompt: str, response_schema: dict) -> dict:
            raise RuntimeError("provider timeout")

    response, db = await _call_interpret(FailingProvider())
    assert response.status_code == 502
    audit = next(obj for obj in db.add.call_args_list if isinstance(obj.args[0], AuditLog)).args[0]
    assert audit.new_values["status"] == "llm_failed"
    assert "provider timeout" in audit.new_values["error"]
