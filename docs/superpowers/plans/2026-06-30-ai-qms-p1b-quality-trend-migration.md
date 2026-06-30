# P1-B Quality Trend AI Interpretation Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `quality_trend_service.interpret_quality_trend`'s LLM call from the legacy `LLMProvider.complete()` onto the P0 agent base `provider_adapter` (new `complete_json`) and unify its audit through the base `audit` helper (new `write_audit_raw`), with no behavior change to the 7-state machine / cache / rate limit.

**Architecture:** Thin migration — add `complete_json` (single-shot JSON LLM call, parity with legacy `complete`) and `ProviderNotConfiguredError` to `provider_adapter`; add `write_audit_raw` (AgentContext-free audit) to `audit` and refactor `write_audit` to delegate; rewire `interpret_quality_trend` to use both; adapt the dashboard route + tests. No agent tool / harness / session. Legacy `LLMProvider` class stays (other consumers migrate in P1-C/D/E).

**Tech Stack:** Python 3.11 + FastAPI 0.115 (async) · SQLAlchemy 2.0 async (asyncpg) · already-installed `openai`/`anthropic` SDKs · Pydantic v2 · pytest (async, real DB).

**Spec:** `docs/superpowers/specs/2026-06-30-ai-qms-p1b-quality-trend-migration-design.md`

## Global Constraints

- **No `pydantic-ai`** (conflicts with pinned `pydantic==2.9.2`). Use already-installed `openai>=1.50`/`anthropic>=0.40` SDKs.
- Base must NOT import business-layer exceptions. `provider_adapter` defines `ProviderNotConfiguredError`; `interpret_quality_trend` catches it and raises business-layer `LLMNotConfiguredError`.
- `build_client` raises `ProviderNotConfiguredError` when: `llm_provider` empty; OR provider != `local` and `llm_api_key` empty; OR provider == `local` and (`llm_base_url` empty or `llm_model` empty). **claude/openai with empty `llm_model` does NOT raise** — use provider default (`claude-sonnet-4-6-20250514` / `gpt-4o`), matching legacy `create_llm_provider`. **`local` with complete config is supported** (httpx `POST {base_url}/api/generate`, mirroring legacy `LocalProvider.complete`) — do NOT raise "not supported". (P0 `build_client` currently never raises — this plan adds the raise path; P0 test `test_build_client_returns_provider_client` is adapted in Task 1.)
- `factory_id: uuid.UUID | None` (nullable — matches `RequestScope.effective_factory_id` + dashboard "None=global" + `AuditLog.factory_id` nullable).
- `tenant_schema` resolved via a `_tenant_schema(request)` helper (`getattr(request.state, "tenant", None)` → `schema_name`, else `"public"`) — mirror `backend/app/api/agent/sessions.py:17`.
- `_extract_json` + `MAX_RESPONSE_BYTES` extracted to a **shared util** (`backend/app/services/agent/llm_json.py`); `llm_provider.py` imports from it (legacy `OpenAIProvider.complete` keeps working). Do NOT delete `llm_provider.py`'s symbols.
- Legacy `LLMProvider` class is NOT removed (P1-C/D/E consumers still use it). `app.state.llm_provider` is no longer read by the quality-trend path.
- 7 audit states preserved: `rate_limited` / `insufficient_data` / `llm_not_configured` / `llm_failed` / `parse_failed` / `cache_hit` / `success`. `LLM_TIMEOUT=30.0` preserved.
- `_write_interpret_audit` keeps its `await db.commit()` (it independently commits; `write_audit_raw` only flushes).
- `correlation_id` = stable UUID via `uuid.uuid5(uuid.NAMESPACE_URL, f"quality_trend:{scope_hash}")`.
- Backend tests: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest <path> -v`. Worktree has no local venv — use the shared one. **Test env has NO LLM config** (`LLM_PROVIDER=""`, `LLM_API_KEY=""`, `LLM_MODEL=""`), so any `build_client(db)` call against real `db` without injected config raises `ProviderNotConfiguredError`; tests must stub `build_client`/`complete_json` or inject config.
- Commits: one per task (or per TDD red→green). Match existing style (`feat(scope): ...`, `refactor(scope): ...`).
- `ruff check --fix` on touched files only (leave E702 one-liners — codebase style). Do NOT run ruff on unrelated files.

---

## File Structure

| Path | Responsibility |
|---|---|
| `backend/app/services/agent/llm_json.py` | NEW shared util: `extract_json(text) -> dict`, `MAX_RESPONSE_BYTES` |
| `backend/app/services/agent/provider_adapter.py` | Add `ProviderNotConfiguredError`, `complete_json`; make `build_client` raise on unconfigured |
| `backend/app/services/llm_provider.py` | Import `extract_json`/`MAX_RESPONSE_BYTES` from shared util (keep legacy symbols) |
| `backend/app/services/agent/audit.py` | Add `write_audit_raw`; refactor `write_audit` to delegate |
| `backend/app/services/quality_trend_service.py` | Rewire `interpret_quality_trend` + `_write_interpret_audit` to base provider/audit |
| `backend/app/api/dashboard.py` | Route: drop `llm_provider`, pass `factory_id`/`tenant_schema`; add `_tenant_schema` helper |
| `backend/tests/services/agent/test_provider_adapter.py` | Add `complete_json` + `ProviderNotConfiguredError` tests; adapt `test_build_client` |
| `backend/tests/services/agent/test_audit.py` | NEW: `write_audit_raw` tests |
| `backend/tests/test_quality_trend_interpret_api.py` | Rewire stubs: `build_client`/`complete_json` instead of `app.state.llm_provider` |
| `backend/tests/test_quality_trend_service.py` | Adapt if it calls `interpret_quality_trend` directly (check first) |

---

## Task 1: Shared `llm_json` util + `complete_json` + `ProviderNotConfiguredError` + `build_client` raise

**Files:**
- Create: `backend/app/services/agent/llm_json.py`
- Modify: `backend/app/services/agent/provider_adapter.py`
- Modify: `backend/app/services/llm_provider.py`
- Test: `backend/tests/services/agent/test_provider_adapter.py`

**Interfaces:**
- Produces: `llm_json.extract_json(text) -> dict`, `llm_json.MAX_RESPONSE_BYTES`; `provider_adapter.ProviderNotConfiguredError`; `provider_adapter.complete_json(pc, prompt, response_schema) -> dict`; `build_client` now raises `ProviderNotConfiguredError` when unconfigured.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/services/agent/test_provider_adapter.py`:
```python
import pytest
from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import (
    ProviderClient, ProviderNotConfiguredError, complete_json,
)


def test_extract_json_strips_code_fence():
    from app.services.agent.llm_json import extract_json
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('{"b": 2}') == {"b": 2}


@pytest.mark.asyncio
async def test_complete_json_openai_success(monkeypatch):
    pc = ProviderClient(provider="openai", client=object(), model="m")

    class _Msg:
        content = '{"summary": "ok", "evidence_refs": []}'

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})]

    async def _create(**kwargs):
        assert kwargs.get("response_format") == {"type": "json_object"}
        return _Resp()

    pc.client = type("C", (), {"chat": type("CH", (), {"completions": type("CM", (), {"create": _create})})})()
    out = await complete_json(pc, "prompt", {"type": "object"})
    assert out == {"summary": "ok", "evidence_refs": []}


@pytest.mark.asyncio
async def test_complete_json_openai_retries_without_response_format(monkeypatch):
    pc = ProviderClient(provider="openai", client=object(), model="m")
    calls = []

    class _Msg:
        content = '{"x": 1}'

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})]

    async def _create(**kwargs):
        calls.append(kwargs.get("response_format"))
        if kwargs.get("response_format") and len(calls) == 1:
            raise RuntimeError("json_object is not supported by this model")
        return _Resp()

    pc.client = type("C", (), {"chat": type("CH", (), {"completions": type("CM", (), {"create": _create})})})()
    out = await complete_json(pc, "p", {})
    assert out == {"x": 1}
    assert calls[0] == {"type": "json_object"}
    assert calls[1] is None  # retry without response_format


@pytest.mark.asyncio
async def test_complete_json_openai_oversize_raises():
    pc = ProviderClient(provider="openai", client=object(), model="m")
    big = '{"x": "' + "a" * 11_000 + '"}'

    class _Msg:
        content = big

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})]

    async def _create(**kwargs):
        return _Resp()

    pc.client = type("C", (), {"chat": type("CH", (), {"completions": type("CM", (), {"create": _create})})})()
    with pytest.raises(ValueError):
        await complete_json(pc, "p", {})


@pytest.mark.asyncio
async def test_complete_json_anthropic_success():
    pc = ProviderClient(provider="anthropic", client=object(), model="m")

    class _Block:
        type = "text"
        text = '{"y": 2}'

    class _Resp:
        content = [_Block()]

    async def _create(**kwargs):
        assert kwargs.get("max_tokens")
        return _Resp()

    pc.client = type("C", (), {"messages": type("M", (), {"create": _create})})()
    out = await complete_json(pc, "p", {})
    assert out == {"y": 2}


@pytest.mark.asyncio
async def test_build_client_raises_when_unconfigured(monkeypatch):
    """Empty provider/api_key (non-local) -> ProviderNotConfiguredError. Mirrors
    legacy create_llm_provider returning None for rule-only mode."""
    from app.schemas.ai_config import AIConfigOut

    async def _empty_cfg(db):
        return AIConfigOut(llm_provider="", llm_api_key="", llm_model="",
                           llm_base_url="", llm_timeout=30, capa_draft_llm_timeout=15,
                           report_llm_timeout=10, embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _empty_cfg)
    with pytest.raises(ProviderNotConfiguredError):
        await provider_adapter.build_client(object())


@pytest.mark.asyncio
async def test_build_client_openai_empty_model_uses_default(monkeypatch):
    """claude/openai with empty model does NOT raise — uses provider default."""
    from app.schemas.ai_config import AIConfigOut

    async def _cfg(db):
        return AIConfigOut(llm_provider="openai", llm_api_key="sk-x", llm_model="",
                           llm_base_url="", llm_timeout=30, capa_draft_llm_timeout=15,
                           report_llm_timeout=10, embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _cfg)
    pc = await provider_adapter.build_client(object())
    assert pc.model == "gpt-4o"
    assert pc.provider == "openai"
```

Also **adapt the existing P0 test** `test_build_client_returns_provider_client` (it currently calls `build_client(db)` against a real db with empty test-env config and relied on defaults). Replace it with a version that injects config so it doesn't depend on env, AND asserts the raise on empty:
```python
@pytest.mark.asyncio
async def test_build_client_returns_provider_client(monkeypatch):
    from app.schemas.ai_config import AIConfigOut

    async def _cfg(db):
        return AIConfigOut(llm_provider="openai", llm_api_key="sk-x", llm_model="gpt-4o-mini",
                           llm_base_url="https://demo/v1", llm_timeout=30, capa_draft_llm_timeout=15,
                           report_llm_timeout=10, embedding_provider="", embedding_api_key="",
                           embedding_model="", embedding_base_url="", embedding_dimensions=1536,
                           search_vector_weight=0.7, search_fulltext_weight=0.3)

    monkeypatch.setattr(provider_adapter, "get_raw_ai_config", _cfg)
    pc = await provider_adapter.build_client(object())
    assert pc.provider in ("openai", "anthropic")
    assert pc.client is not None
    assert pc.model  # non-empty model name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/services/agent/test_provider_adapter.py -v`
Expected: FAIL — `ProviderNotConfiguredError`/`complete_json` not defined; `extract_json` import fails.

- [ ] **Step 3: Create the shared util**

`backend/app/services/agent/llm_json.py`:
```python
"""Shared JSON-from-LLM-text util + size cap.

Used by provider_adapter.complete_json (agent base) and the legacy
LLMProvider.complete (llm_provider.py) so both parse identically.
"""
import json

MAX_RESPONSE_BYTES = 10_240  # 10KB


def extract_json(text: str) -> dict:
    """Parse JSON from an LLM response, tolerating ```json code fences."""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
```

- [ ] **Step 4: Update `llm_provider.py` to import from the shared util**

In `backend/app/services/llm_provider.py`, replace the local `MAX_RESPONSE_BYTES` constant and `_extract_json` function with imports (keep the names re-exported so existing call sites `MAX_RESPONSE_BYTES` / `_extract_json` still work):
```python
# At top, after existing imports, replace the local definitions with:
from app.services.agent.llm_json import MAX_RESPONSE_BYTES, extract_json as _extract_json
```
Delete the local `MAX_RESPONSE_BYTES = 10_240` line and the local `def _extract_json(...)` body (the import replaces both). Keep everything else in `llm_provider.py` unchanged.

- [ ] **Step 5: Implement `complete_json` + `ProviderNotConfiguredError` + `build_client` raise in `provider_adapter.py`**

Add to `backend/app/services/agent/provider_adapter.py` (after the imports, add `import logging`; add the exception class near the top; modify `build_client`; add `complete_json` at the end):
```python
import logging
from app.services.agent.llm_json import MAX_RESPONSE_BYTES, extract_json

logger = logging.getLogger(__name__)


class ProviderNotConfiguredError(RuntimeError):
    """Raised by build_client when AI config is missing (rule-only mode)."""


async def build_client(db: AsyncSession) -> ProviderClient:
    cfg: AIConfigOut = await get_raw_ai_config(db)
    provider = (cfg.llm_provider or "").lower()
    if not provider:
        raise ProviderNotConfiguredError("LLM_PROVIDER 未配置（纯规则引擎模式）")
    if provider in ("anthropic", "claude"):
        if not cfg.llm_api_key:
            raise ProviderNotConfiguredError("anthropic/claude 需要 LLM_API_KEY")
        from anthropic import AsyncAnthropic
        return ProviderClient(
            provider="anthropic",
            client=AsyncAnthropic(api_key=cfg.llm_api_key),
            model=cfg.llm_model or "claude-sonnet-4-6-20250514",
        )
    if provider == "local":
        if not cfg.llm_base_url:
            raise ProviderNotConfiguredError("local 需要 LLM_BASE_URL")
        if not cfg.llm_model:
            raise ProviderNotConfiguredError("local 需要 LLM_MODEL")
        import httpx
        return ProviderClient(
            provider="local",
            client=httpx.AsyncClient(base_url=cfg.llm_base_url.rstrip("/"), timeout=30),
            model=cfg.llm_model,
        )
    # openai-compatible (openai / deepseek / ark via base_url)
    if not cfg.llm_api_key:
        raise ProviderNotConfiguredError(f"{provider} 需要 LLM_API_KEY")
    from openai import AsyncOpenAI
    return ProviderClient(
        provider="openai",
        client=AsyncOpenAI(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url or None),
        model=cfg.llm_model or "gpt-4o",
    )


async def complete_json(pc: ProviderClient, prompt: str, response_schema: dict) -> dict:
    """Single-shot JSON LLM call: prompt -> dict. Parity with legacy LLMProvider.complete.

    openai: response_format=json_object, retry without it if the gateway rejects.
    anthropic: messages.create + json.loads.
    Both enforce MAX_RESPONSE_BYTES and use extract_json for fenced JSON.
    local: httpx POST {base_url}/api/generate (mirrors legacy LocalProvider.complete).
    """
    messages = [{"role": "user", "content": prompt}]
    if pc.provider == "openai":
        try:
            resp = await pc.client.chat.completions.create(
                model=pc.model, messages=messages,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            if "json_object" in str(e) or "response_format" in str(e):
                logger.info("LLM rejected response_format=json_object, retrying without: %s", e)
                resp = await pc.client.chat.completions.create(model=pc.model, messages=messages)
            else:
                raise
        text = resp.choices[0].message.content or ""
    elif pc.provider == "local":
        resp = await pc.client.post(
            "/api/generate",
            json={"model": pc.model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")
    else:  # anthropic
        resp = await pc.client.messages.create(
            model=pc.model, messages=messages, max_tokens=1024,
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    if len(text.encode()) > MAX_RESPONSE_BYTES:
        raise ValueError("LLM response too large")
    return extract_json(text)
```
Remove the now-duplicate `import json` if it becomes unused (keep it if `chat_with_tools` still uses it — it does).

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/services/agent/test_provider_adapter.py tests/test_provider_adapter_smoke.py -v`
Expected: PASS (new tests + P0 smoke + adapted build_client test).

- [ ] **Step 7: Run the full agent suite to confirm no P0 regression**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/services/agent/ tests/api/agent/ tests/test_provider_adapter_smoke.py tests/models/test_agent_models.py tests/test_audit.py -q`
Expected: all pass (harness loop tests stub `build_client`, so the raise-on-empty doesn't affect them).
`ruff check --fix` on `llm_json.py`, `provider_adapter.py`, `llm_provider.py`, `test_provider_adapter.py` only.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/agent/llm_json.py backend/app/services/agent/provider_adapter.py backend/app/services/llm_provider.py backend/tests/services/agent/test_provider_adapter.py
git commit -m "feat(agent): shared llm_json util + complete_json + ProviderNotConfiguredError; build_client raises when unconfigured"
```

---

## Task 2: `write_audit_raw` + refactor `write_audit` to delegate

**Files:**
- Modify: `backend/app/services/agent/audit.py`
- Create: `backend/tests/services/agent/test_audit.py`

**Interfaces:**
- Produces: `audit.write_audit_raw(db, *, user_id, factory_id, tenant_schema, table_name, record_id, action, correlation_id=None, changed_fields=None, old_values=None, new_values=None) -> AuditLog`. `write_audit(ctx, ...)` delegates to it.

- [ ] **Step 1: Write the failing tests**

`backend/tests/services/agent/test_audit.py`:
```python
import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.services.agent import audit


@pytest.mark.asyncio
async def test_write_audit_raw_writes_factory_tenant_correlation(db, admin_user, default_factory):
    corr = uuid.uuid4()
    rec = uuid.uuid4()
    log = await audit.write_audit_raw(
        db, user_id=admin_user.user_id, factory_id=default_factory.id,
        tenant_schema="public", table_name="quality_trends", record_id=rec,
        action="AI_TREND_INTERPRET", correlation_id=corr,
        new_values={"status": "success"},
    )
    got = (await db.execute(select(AuditLog).where(AuditLog.log_id == log.log_id))).scalar_one()
    assert got.factory_id == default_factory.id
    assert got.tenant_schema == "public"
    assert got.correlation_id == corr
    assert got.operated_by == admin_user.user_id
    assert got.new_values == {"status": "success"}


@pytest.mark.asyncio
async def test_write_audit_raw_accepts_none_factory(db, admin_user):
    """factory_id is nullable (None = global scope)."""
    log = await audit.write_audit_raw(
        db, user_id=admin_user.user_id, factory_id=None,
        tenant_schema="public", table_name="quality_trends",
        record_id=uuid.uuid4(), action="AI_TREND_INTERPRET",
    )
    assert log.factory_id is None


@pytest.mark.asyncio
async def test_write_audit_delegates_to_raw(db, admin_user, default_factory):
    """write_audit(ctx, ...) still works after refactor (P0 callers unchanged)."""
    from app.services.agent import harness
    s = await harness.create_session(db, admin_user, default_factory.id, "public", "copilot")
    ctx = await harness.build_context(db, s, admin_user)
    log = await audit.write_audit(db, ctx, "agent_tool_calls", uuid.uuid4(), "call", uuid.uuid4())
    assert log.factory_id == default_factory.id
    assert log.operated_by == admin_user.user_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/services/agent/test_audit.py -v`
Expected: FAIL — `write_audit_raw` not defined.

- [ ] **Step 3: Implement `write_audit_raw` + refactor `write_audit`**

Replace `backend/app/services/agent/audit.py` with:
```python
"""Audit helpers shared by agent harness, gateway, and non-agent consumers."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def write_audit_raw(
    db: AsyncSession, *, user_id: uuid.UUID, factory_id: uuid.UUID | None,
    tenant_schema: str, table_name: str, record_id: uuid.UUID, action: str,
    correlation_id: uuid.UUID | None = None, changed_fields: dict | None = None,
    old_values: dict | None = None, new_values: dict | None = None,
) -> AuditLog:
    """Write an audit log without an AgentContext (for non-agent-session callers).

    flushes only; the caller decides commit timing.
    """
    log = AuditLog(
        log_id=uuid.uuid4(),
        table_name=table_name,
        record_id=record_id,
        action=action,
        changed_fields=changed_fields,
        old_values=old_values,
        new_values=new_values,
        operated_by=user_id,
        factory_id=factory_id,
        tenant_schema=tenant_schema,
        correlation_id=correlation_id,
    )
    db.add(log)
    await db.flush()
    return log


async def write_audit(
    db: AsyncSession, ctx, table_name: str, record_id: uuid.UUID, action: str,
    correlation_id: uuid.UUID | None = None, changed_fields: dict | None = None,
    old_values: dict | None = None, new_values: dict | None = None,
) -> AuditLog:
    """Write an audit log using an AgentContext for scope. Delegates to write_audit_raw."""
    # Late import to avoid a circular reference at module load (registry <-> audit).
    return await write_audit_raw(
        db, user_id=ctx.user_id, factory_id=ctx.factory_id,
        tenant_schema=ctx.tenant_schema, table_name=table_name, record_id=record_id,
        action=action, correlation_id=correlation_id, changed_fields=changed_fields,
        old_values=old_values, new_values=new_values,
    )
```
Note: the `AgentContext` import is removed (no longer needed at module top; `ctx` is duck-typed). Confirm no P0 caller imports `AgentContext` from `audit.py` (it doesn't — `audit.py` is consumed via `audit.write_audit`). `harness.py` imports `write_audit` from `audit`; `approval.py` imports `write_audit` from `audit` (Task 11 round-4 fix). Both still work.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/services/agent/test_audit.py tests/services/agent/test_approval.py tests/services/agent/test_harness_lifecycle.py -v`
Expected: PASS (new audit tests + P0 approval/harness still pass — they use `write_audit`).
`ruff check --fix` on `audit.py`, `test_audit.py` only.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agent/audit.py backend/tests/services/agent/test_audit.py
git commit -m "feat(agent): write_audit_raw for non-agent callers; write_audit delegates"
```

---

## Task 3: Rewire `interpret_quality_trend` + `_write_interpret_audit`

**Files:**
- Modify: `backend/app/services/quality_trend_service.py`

**Interfaces:**
- Consumes: `provider_adapter.build_client`/`complete_json`/`ProviderNotConfiguredError` (Task 1); `audit.write_audit_raw` (Task 2).
- Produces: `interpret_quality_trend(db, user_id, factory_id, tenant_schema, filter_codes, allowed_modules, scope_description, selected_product_line, scope_hash)` (no `llm_provider`).

- [ ] **Step 1: Write the failing test (unit-level, service direct)**

Check first whether `backend/tests/test_quality_trend_service.py` exists and calls `interpret_quality_trend` directly:
Run: `ls backend/tests/test_quality_trend_service.py && grep -n "interpret_quality_trend\|llm_provider" backend/tests/test_quality_trend_service.py`
If it exists and calls the service directly, adapt those call sites in Task 3 Step 4. If it does not exist / does not call interpret, create a focused unit test:

`backend/tests/test_quality_trend_service.py` (append, or create):
```python
import uuid
import pytest
from app.services import quality_trend_service
from app.services.quality_trend_service import LLMNotConfiguredError


@pytest.mark.asyncio
async def test_interpret_raises_llm_not_configured_when_provider_unconfigured(
    db, admin_user, default_factory, monkeypatch
):
    """build_client raises ProviderNotConfiguredError -> interpret translates to
    LLMNotConfiguredError and writes llm_not_configured audit."""
    from app.services.agent import provider_adapter
    from sqlalchemy import select
    from app.models.audit import AuditLog

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_quality_trend_service.py -v`
Expected: FAIL — `interpret_quality_trend` still takes `llm_provider`, not `factory_id`/`tenant_schema` (TypeError on the new kwargs).

- [ ] **Step 3: Rewire `interpret_quality_trend` + `_write_interpret_audit`**

In `backend/app/services/quality_trend_service.py`:

(a) Add imports near the top (after existing imports):
```python
from app.services.agent import provider_adapter
from app.services.agent.audit import write_audit_raw
```

(b) Change the `interpret_quality_trend` signature — replace `llm_provider,` param with `factory_id: uuid_mod.UUID | None, tenant_schema: str,`. **Note:** this file uses `import uuid as uuid_mod` (line 168) — use `uuid_mod.UUID` (not `uuid.UUID`) so the annotation matches the file's alias and doesn't trip an implementer who copies verbatim. With `from __future__ import annotations` the annotation is a string at runtime, but keep the alias consistent:
```python
async def interpret_quality_trend(
    db,
    user_id: str,
    factory_id: uuid_mod.UUID | None,
    tenant_schema: str,
    filter_codes: list[str],
    allowed_modules: set[str],
    scope_description: str,
    selected_product_line: str | None,
    scope_hash: str,
) -> QualityTrendInterpretation:
```

(c) Replace the `if llm_provider is None:` block and the `llm_provider.complete(...)` call. The new body from the `llm_provider is None` check onward:
```python
    cache_key = f"{scope_hash}:{summary.data_window_days}:{summary.evidence_hash}"
    cached = _get_cached_interpretation(cache_key)
    if cached:
        await _write_interpret_audit(db, user_id, "cache_hit", audit_context, factory_id, tenant_schema, scope_hash)
        return cached

    prompt = _build_interpret_prompt(summary, allowed_modules, scope_description)
    try:
        pc = await provider_adapter.build_client(db)
        raw = await asyncio.wait_for(
            provider_adapter.complete_json(pc, prompt, _interpret_response_schema()),
            timeout=LLM_TIMEOUT,
        )
    except provider_adapter.ProviderNotConfiguredError:
        await _write_interpret_audit(db, user_id, "llm_not_configured", audit_context, factory_id, tenant_schema, scope_hash)
        raise LLMNotConfiguredError("LLM 未配置")
    except TimeoutError as exc:
        await _write_interpret_audit(db, user_id, "llm_failed", audit_context | {"error": f"LLM 调用超时（>{LLM_TIMEOUT}s）"}, factory_id, tenant_schema, scope_hash)
        raise LLMNotConfiguredError("AI 解读服务响应超时，请稍后重试") from exc
    except Exception as exc:
        await _write_interpret_audit(db, user_id, "llm_failed", audit_context | {"error": str(exc)}, factory_id, tenant_schema, scope_hash)
        raise

    try:
        result = _parse_interpretation(raw, summary, scope_hash)
    except LLMResponseParseError as exc:
        await _write_interpret_audit(db, user_id, "parse_failed", audit_context | {"error": str(exc)}, factory_id, tenant_schema, scope_hash)
        raise

    _set_cached_interpretation(cache_key, result)
    await _write_interpret_audit(db, user_id, "success", audit_context | {"model": result.model}, factory_id, tenant_schema, scope_hash)
    return result
```
Keep the rate-limited + insufficient_data blocks at the top, but update their `_write_interpret_audit` calls to pass the 3 new args (`factory_id, tenant_schema, scope_hash`).

(d) Replace `_write_interpret_audit`:
```python
async def _write_interpret_audit(
    db, user_id: str, status: str, context: dict,
    factory_id, tenant_schema: str, scope_hash: str,
) -> None:
    correlation_id = uuid_mod.uuid5(uuid_mod.NAMESPACE_URL, f"quality_trend:{scope_hash}")
    await write_audit_raw(
        db,
        user_id=uuid_mod.UUID(str(user_id)),
        factory_id=factory_id,
        tenant_schema=tenant_schema,
        table_name="quality_trends",
        record_id=uuid_mod.uuid4(),
        action="AI_TREND_INTERPRET",
        correlation_id=correlation_id,
        changed_fields={"status": status},
        new_values={"status": status, **context},
    )
    await db.commit()
```
(`uuid_mod` is the existing alias in this file for the `uuid` module — confirm the alias name by grepping `import uuid` in the file; if it's `import uuid` directly, use `uuid.uuid5`/`uuid.UUID`.)

- [ ] **Step 4: Verify the `uuid` alias + adapt any direct service-test callers**

Run: `grep -n "import uuid\|uuid_mod" backend/app/services/quality_trend_service.py | head`
Use the matching alias in Step 3(d). If `test_quality_trend_service.py` had other direct `interpret_quality_trend(...)` callers, update their kwargs to the new signature (drop `llm_provider=`, add `factory_id=`/`tenant_schema=`).

- [ ] **Step 5: Run the service test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_quality_trend_service.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/quality_trend_service.py backend/tests/test_quality_trend_service.py
git commit -m "refactor(quality-trend): interpret_quality_trend on agent base provider + audit"
```

---

## Task 4: Adapt dashboard route + `_tenant_schema` helper

**Files:**
- Modify: `backend/app/api/dashboard.py`

**Interfaces:** none new — route passes `factory_id`/`tenant_schema` to the service.

- [ ] **Step 1: Write the failing test (route-level)**

The existing `backend/tests/test_quality_trend_interpret_api.py` tests will break (they set `app.state.llm_provider` and pass it through). Defer the full rewire to Task 5; here, add a focused route test asserting the route no longer reads `app.state.llm_provider` and passes factory/tenant through. Append to `backend/tests/test_quality_trend_interpret_api.py`:
```python
@pytest.mark.anyio
async def test_interpret_route_does_not_read_app_state_llm_provider(monkeypatch):
    """Route must not read app.state.llm_provider; it builds via provider_adapter."""
    from app.services.agent import provider_adapter
    from app.services import quality_trend_service

    captured = {}

    async def _no_cfg(db):
        raise provider_adapter.ProviderNotConfiguredError("test")
    monkeypatch.setattr(provider_adapter, "build_client", _no_cfg)
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

    # explicitly do NOT set app.state.llm_provider
    if hasattr(app.state, "llm_provider"):
        delattr(app.state, "llm_provider")

    response, _db = await _call_interpret(None)  # llm_provider arg now ignored by _call_interpret
    assert response.status_code == 503  # LLMNotConfiguredError -> 503
```
(If `_call_interpret` still sets `app.state.llm_provider = llm_provider`, that's fine — the route no longer reads it. The test asserts the route works without relying on it.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_quality_trend_interpret_api.py::test_interpret_route_does_not_read_app_state_llm_provider -v`
Expected: FAIL — route still reads `app.state.llm_provider` and passes `llm_provider=` to the service (which no longer accepts it → TypeError → 502, not 503).

- [ ] **Step 3: Add `_tenant_schema` helper + rewire the route**

In `backend/app/api/dashboard.py`, add a module-level helper (near other helpers, mirror `agent/sessions.py`):
```python
def _tenant_schema(request: Request) -> str:
    tenant = getattr(request.state, "tenant", None)
    return tenant.schema_name if tenant else "public"
```

Replace the `interpret_quality_trend` route body — remove the `llm_provider = getattr(request.app.state, "llm_provider", None)` line and change the service call:
```python
    scope_description = build_scope_description(filter_codes or None)
    scope_hash = await build_scope_hash(filter_codes)

    try:
        return await interpret_quality_trend_service(
            db=db,
            user_id=str(scope.user.user_id),
            factory_id=scope.effective_factory_id,
            tenant_schema=_tenant_schema(request),
            filter_codes=filter_codes,
            allowed_modules=quality_trend_allowed_modules,
            scope_description=scope_description,
            selected_product_line=filter_codes[0] if filter_codes and len(filter_codes) == 1 else None,
            scope_hash=scope_hash,
        )
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InsufficientTrendDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMResponseParseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="AI 解读生成失败") from exc
```
Keep the permission check, `_resolve_filter_codes`, and `quality_trend_allowed_modules` building unchanged.

- [ ] **Step 4: Run the route test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_quality_trend_interpret_api.py::test_interpret_route_does_not_read_app_state_llm_provider -v`
Expected: PASS.
`ruff check --fix` on `dashboard.py` only.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/dashboard.py backend/tests/test_quality_trend_interpret_api.py
git commit -m "refactor(dashboard): quality-trend interpret route via agent base (factory_id/tenant_schema, no app.state.llm_provider)"
```

---

## Task 5: Rewire the quality-trend API test suite + full regression

**Files:**
- Modify: `backend/tests/test_quality_trend_interpret_api.py`

**Interfaces:** none.

- [ ] **Step 1: Rewire `_call_interpret` + provider stubs**

The existing tests stub via `app.state.llm_provider = <FakeLLMProvider>` and the route read it. Now the route calls `provider_adapter.build_client(db)` + `complete_json(pc, ...)`. The test `db` is a `MagicMock`, so `build_client` can't run against it. Rewire:

In `backend/tests/test_quality_trend_interpret_api.py`, change `_call_interpret` to stub `provider_adapter.build_client` + `complete_json` instead of setting `app.state.llm_provider`. Keep the `llm_provider` parameter of `_call_interpret` as a backward-compatible shim OR rename — simplest: replace the body's `app.state.llm_provider = llm_provider` with a monkeypatch-based stub. Since `_call_interpret` isn't a pytest fixture, use `unittest.mock.patch` context managers:
```python
async def _call_interpret(llm_provider):
    from app.services.agent import provider_adapter
    from app.services.agent.provider_adapter import ProviderClient

    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.scalar = AsyncMock(side_effect=[4, 1, 2, 3, 2])
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    async def mock_get_db():
        return db
    user = _make_user()

    async def mock_get_current_user():
        return user
    mock_scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=user.factory_id),
        effective_factory_id=user.factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=["DC-DC-100"]),
        user=user,
    )

    async def mock_get_request_scope():
        return mock_scope

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_request_scope] = mock_get_request_scope

    async def mock_get_user_permission(user, module, db):
        return PermissionLevel.VIEW if module.value in {"dashboard", "spc", "capa", "fmea"} else PermissionLevel.NONE

    # Stub the agent-base provider layer. llm_provider is None -> unconfigured (503).
    # Otherwise treat llm_provider as a legacy .complete() stub and adapt via complete_json.
    async def _build_client(_db):
        if llm_provider is None:
            raise provider_adapter.ProviderNotConfiguredError("none in test")
        return ProviderClient(provider="openai", client=object(), model="test")

    async def _complete_json(pc, prompt, schema):
        if llm_provider is None:
            raise provider_adapter.ProviderNotConfiguredError("none")
        # delegate to the legacy-style stub: FakeLLMProvider.complete(prompt, schema)
        return await llm_provider.complete(prompt, schema)

    try:
        with patch("app.core.permissions.get_user_permission", new=mock_get_user_permission), \
             patch("app.api.dashboard.get_user_permission", new=mock_get_user_permission), \
             patch("app.services.agent.provider_adapter.build_client", new=_build_client), \
             patch("app.services.agent.provider_adapter.complete_json", new=_complete_json):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/dashboard/widgets/quality-trend/interpret",
                    json={"product_line": "DC-DC-100"},
                )
    finally:
        app.dependency_overrides.clear()
    return response, db
```
This keeps every existing test's `FakeLLMProvider`/`BadRefsProvider`/`FailingProvider` working (they define `.complete(prompt, schema)`), and `_call_interpret(None)` now raises `ProviderNotConfiguredError` → 503. The `delattr(app.state, "llm_provider")` cleanup is no longer needed (remove it).

- [ ] **Step 2: Run the full quality-trend API suite**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/test_quality_trend_interpret_api.py tests/test_dashboard_quality_trend_api.py -v`
Expected: all pass. If a test asserts on `db.add` AuditLog rows, those still hold (`write_audit_raw` does `db.add`). If `test_interpret_audits_llm_provider_failure` relied on `FailingProvider.complete` raising, `_complete_json` re-raises it → `llm_failed` audit → 502 (unchanged).

- [ ] **Step 3: Run the full backend regression**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest tests/ -q`
Expected: all pass. Pay attention to: agent suite, quality-trend tests, dashboard tests, audit tests, ai-config tests (the `get_raw_ai_config` added in P0 is reused).
`ruff check --fix` on `test_quality_trend_interpret_api.py` only.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_quality_trend_interpret_api.py
git commit -m "test(quality-trend): rewire API tests to stub provider_adapter build_client/complete_json"
```

---

## Self-Review (run after writing, before handoff)

1. **Spec coverage:**
   - §2.1 `complete_json` + `ProviderNotConfiguredError` + `build_client` raise + shared `_extract_json` util → Task 1. ✓
   - §2.2 `write_audit_raw` + `write_audit` delegate → Task 2. ✓
   - §2.3 `interpret_quality_trend` rewire + `_write_interpret_audit` via `write_audit_raw` + stable `correlation_id` + `factory_id: UUID | None` → Task 3. ✓
   - §2.4 dashboard route + `_tenant_schema` helper → Task 4. ✓
   - §5 tests (complete_json openai/anthropic/retry/oversize, build_client raise + model-default, write_audit_raw incl None, interpret 7-state, route no app.state.llm_provider) → Tasks 1-5. ✓
   - §6 exclusions (no agent tool, no LLMProvider deletion, no chat_with_tools change, no other consumers) → respected. ✓
2. **Placeholder scan:** Task 3 Step 4 has a "verify the uuid alias" instruction (a verification, not a placeholder — the alias is confirmed by grep in-step). No TBD/TODO. All code blocks complete.
3. **Type consistency:** `ProviderNotConfiguredError` defined Task 1, used Task 1/3/4/5. `complete_json(pc, prompt, response_schema) -> dict` consistent. `write_audit_raw` signature consistent Task 2/3. `interpret_quality_trend` new signature consistent Task 3/4. `_tenant_schema` consistent Task 4. `ProviderClient` consistent. `factory_id: uuid.UUID | None` consistent throughout.
4. **Open items for implementer (called out inline):** confirm `uuid` alias in `quality_trend_service.py` (Task 3 Step 4); adapt any pre-existing direct callers in `test_quality_trend_service.py` (Task 3 Step 4).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-30-ai-qms-p1b-quality-trend-migration.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
