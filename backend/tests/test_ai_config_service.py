"""Regression tests for the runtime AI config service.

Covers:
1. Masked-key round-trip — submitting the masked sentinel ("********") must NOT
   overwrite the stored key with the literal string, GET must mask keys, and the
   rebuilt provider must receive the *real* key (not the masked placeholder).
   Regression: _rebuild_providers used to authenticate with "********" after a
   save, silently forcing every LLM call back to the rule engine.
2. AuditLog on update_ai_config — every config update writes an audit row, and
   the changed_fields never contain raw API key values.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from sqlalchemy import select

import app.models  # noqa: F401 — register all FK-referenced tables
from app.models.audit import AuditLog
from app.models.system_setting import SystemSetting
from app.schemas.ai_config import AIConfigUpdate
from app.services import ai_config_service
from app.services.ai_config_service import MASKED_VALUE, get_ai_config, update_ai_config


def _make_update(**overrides) -> AIConfigUpdate:
    """Build an AIConfigUpdate, defaulting api keys to the masked sentinel so the
    existing key is preserved unless a test explicitly overrides it."""
    base = {
        "llm_provider": "openai",
        "llm_api_key": MASKED_VALUE,
        "llm_model": "gpt-4o",
        "llm_base_url": "",
        "llm_timeout": 5,
        "capa_draft_llm_timeout": 15,
        "report_llm_timeout": 10,
        "embedding_provider": "",
        "embedding_api_key": MASKED_VALUE,
        "embedding_model": "",
        "embedding_base_url": "",
        "embedding_dimensions": 1536,
        "search_vector_weight": 0.7,
        "search_fulltext_weight": 0.3,
    }
    base.update(overrides)
    return AIConfigUpdate(**base)


async def _seed_setting(db, key: str, value: str) -> SystemSetting:
    """Fetch-or-update a system_settings row (idempotent).

    The test DB may already contain seeded config rows (e.g. llm_api_key), so a
    blind INSERT would violate the unique key constraint. We upsert instead; the
    `db` fixture rolls back each test's transaction.
    """
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = SystemSetting(
            key=key,
            value=value,
            description=f"AI / LLM configuration: {key}",
        )
        db.add(row)
    else:
        row.value = value
    await db.flush()
    return row


async def test_masked_key_sentinel_keeps_stored_key(db, admin_user):
    """Submitting the masked sentinel must not overwrite the stored key."""
    real_key = "sk-real-key-" + uuid.uuid4().hex
    await _seed_setting(db, "llm_api_key", real_key)
    await _seed_setting(db, "llm_provider", "openai")
    await _seed_setting(db, "llm_base_url", "")
    await _seed_setting(db, "embedding_provider", "")
    await _seed_setting(db, "embedding_base_url", "")

    await update_ai_config(db, _make_update(), admin_user.user_id, SimpleNamespace())

    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == "llm_api_key")
    )
    row = result.scalar_one()
    assert row.value == real_key, (
        f"masked sentinel overwrote the stored key: {row.value!r}"
    )


async def test_get_ai_config_masks_keys(db):
    """get_ai_config must mask API keys in its response."""
    real_key = "sk-real-" + uuid.uuid4().hex
    await _seed_setting(db, "llm_api_key", real_key)
    await _seed_setting(db, "embedding_api_key", "sk-emb-" + uuid.uuid4().hex)

    config = await get_ai_config(db)
    assert config.llm_api_key == MASKED_VALUE
    assert config.embedding_api_key == MASKED_VALUE


async def test_rebuilt_provider_authenticates_with_real_key(db, admin_user):
    """_rebuild_providers must hand the *real* key (not the masked placeholder)
    to the LLM provider factory.

    Regression: the rebuilt OpenAIProvider used to authenticate with the literal
    string "********", causing the gateway to return 401 and recommend() to fall
    back to the rule engine. We mock create_llm_provider to capture the config
    snapshot (avoids the openai package dependency) and assert on the key.
    """
    real_key = "sk-real-key-" + uuid.uuid4().hex
    await _seed_setting(db, "llm_api_key", real_key)
    await _seed_setting(db, "llm_provider", "openai")
    await _seed_setting(db, "llm_model", "gpt-4o")

    captured: dict[str, SimpleNamespace] = {}

    def _capture(config):
        captured["snapshot"] = config
        return None  # None => rule-only; avoids needing the openai package

    app_state = SimpleNamespace()
    with patch("app.services.llm_provider.create_llm_provider", side_effect=_capture) as mock_llm, \
         patch("app.services.embedding_provider.create_embedding_provider", return_value=None):
        await ai_config_service._rebuild_providers(db, app_state)

    assert mock_llm.called, "create_llm_provider was not invoked"
    snapshot = captured["snapshot"]
    assert real_key == snapshot.LLM_API_KEY, (
        f"rebuilt provider received masked/wrong key: {snapshot.LLM_API_KEY!r}"
    )
    assert snapshot.LLM_API_KEY != MASKED_VALUE


async def test_update_ai_config_writes_audit_log_without_raw_keys(db, admin_user):
    """Every config update writes an AuditLog; raw API key values never appear."""
    # Seed a real key + a known llm_timeout so the change is deterministic
    # regardless of any pre-existing seeded rows.
    real_key = "sk-real-" + uuid.uuid4().hex
    await _seed_setting(db, "llm_api_key", real_key)
    await _seed_setting(db, "llm_timeout", "5")

    new_key = "sk-new-" + uuid.uuid4().hex
    await update_ai_config(
        db,
        _make_update(llm_api_key=new_key, llm_timeout=20),
        admin_user.user_id,
        SimpleNamespace(),
    )

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.table_name == "system_settings")
        .where(AuditLog.action == "UPDATE")
        .order_by(AuditLog.operated_at.desc())
    )
    audit = result.scalars().first()
    assert audit is not None, "update_ai_config wrote no AuditLog"
    assert audit.operated_by == admin_user.user_id
    assert audit.record_id == uuid.UUID(int=0)
    changed = audit.changed_fields or {}

    # llm_timeout changed 5 -> 20
    assert "llm_timeout" in changed
    assert changed["llm_timeout"] == {"old": "5", "new": "20"}
    # The raw new/old API key values must never appear in the audit row.
    assert changed.get("llm_api_key") == "<changed>"
    audit_text = repr(changed)
    assert real_key not in audit_text, "raw old API key leaked into AuditLog"
    assert new_key not in audit_text, "raw new API key leaked into AuditLog"


@pytest.mark.parametrize("model_key_source", ["db", "env"])
async def test_cross_origin_key_source_switch_preserves_database_and_audit(
    db, admin_user, monkeypatch, model_key_source
):
    environment = AIConfigUpdate().model_dump()
    if model_key_source == "env":
        environment["llm_api_key"] = "synthetic-environment-model-key"
    monkeypatch.setattr(ai_config_service, "_env_default", environment.__getitem__)
    values = {
        "llm_provider": "openai",
        "llm_api_key": "synthetic-model-key" if model_key_source == "db" else "",
        "llm_base_url": "https://model.example/v1",
        "embedding_provider": "openai",
        "embedding_api_key": "synthetic-vector-key",
        "embedding_base_url": "https://vectors.example/v1",
    }
    for key, value in values.items():
        await _seed_setting(db, key, value)

    async def snapshot():
        rows = (await db.scalars(select(SystemSetting))).all()
        audits = (await db.scalars(select(AuditLog).where(
            AuditLog.table_name == "system_settings",
            AuditLog.operated_by == admin_user.user_id,
        ))).all()
        return {row.key: row.value for row in rows}, len(audits)

    before = await snapshot()
    update = _make_update(
        llm_base_url=values["llm_base_url"],
        embedding_provider="openai",
        embedding_base_url=values["embedding_base_url"],
        embedding_api_key="",
    )
    with patch.object(ai_config_service, "_rebuild_providers", new_callable=AsyncMock) as rebuild:
        with pytest.raises(ValueError, match="credential source.*re-entry"):
            await update_ai_config(db, update, admin_user.user_id, SimpleNamespace())
        rebuild.assert_not_awaited()

    await db.flush()
    assert await snapshot() == before
