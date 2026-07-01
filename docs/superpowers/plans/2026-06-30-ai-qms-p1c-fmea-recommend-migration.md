# P1-C FMEA Recommend LLM Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `RecommendationService.recommend()`'s LLM call from legacy `LLMProvider.complete()` onto the P0 agent base `provider_adapter.complete_json`, add base-audit `audit.write_audit_raw` on the LLM-attempt path (two states: `success`/`llm_failed`), and extract `_tenant_schema` to a shared util — with no change to the hybrid rule-fallback UX, cache behavior, or 5-state `source` machine.

**Architecture:** Thin migration mirroring P1-B. `provider_adapter.complete_json` / `write_audit_raw` / `ProviderNotConfiguredError` already exist from P1-B — P1-C only rewires `recommendation_service.py` to consume them, drops the `llm_provider` ctor param, adds `tenant_schema` to `recommend()`, and extracts `_tenant_schema` to `core/tenant.py` (shared by dashboard + fmea routes). `pc = build_client(db)` resolves **before** the cache check (preserves the "cache was rule-mode, now LLM available → fall through" gate). Audit covers only `need_llm=True`; unconfigured (`pc is None`) silently rule-degrades (200, cached) — **not** 503, **not** audited. Route keeps its explicit `await db.commit()`. No agent tool / harness / session.

**Tech Stack:** Python 3.11 + FastAPI 0.115 (async) · SQLAlchemy 2.0 async (asyncpg) · `openai`/`anthropic` SDKs (already installed) · Pydantic v2 · pytest (async, real DB).

**Spec:** `docs/superpowers/specs/2026-06-30-ai-qms-p1c-fmea-recommend-migration-design.md`

## Global Constraints

- **No `pydantic-ai`** (conflicts with pinned `pydantic==2.9.2`). Reuse P1-B's `provider_adapter.complete_json` / `ProviderNotConfiguredError` — do NOT re-add them.
- Base must NOT import business-layer exceptions. `recommend()` catches `provider_adapter.ProviderNotConfiguredError` → `pc = None` (silent rule fallback, **not** 503 — diverges from P1-B by design).
- `build_client` raises `ProviderNotConfiguredError` per P1-B rules (provider empty / non-local+no key / local+no base_url or model). **Test env has NO LLM config** — any real `build_client(db)` call raises; tests MUST stub `build_client`/`complete_json` (mirror `test_quality_trend_service.py:186`).
- `pc = build_client(db)` resolves **before** the cache check (line 590 gate). Cache fall-through gate `if pc is not None and not cached_with_llm` (was `self.llm is not None`).
- `_need_llm(llm_available=pc is not None)` — `pc is None` ⇒ `_need_llm` returns `False` ⇒ `source = "graph"|"rule"`, NOT audited, rule-mode cached 24h. Audit is **two-state** (`success`/`llm_failed`) on `need_llm=True` only. **No `llm_not_configured` audit** (state-machine closure, spec §2.1).
- `rule_fallback` source only on real LLM failure; `rule_fallback` is NOT cached (line 668 gate `source != "rule_fallback"` preserved).
- `factory_id` from `fmea.factory_id` (NOT NULL, no new param). `tenant_schema: str` new param on `recommend()`, from `tenant_schema(request)` helper.
- `user_id=user.user_id` (User PK is `user_id`, NOT `id` — `models/user.py:14`).
- `correlation_id = uuid.uuid5(uuid.NAMESPACE_URL, f"fmea_recommend:{fmea_id}:{trigger_type}:{context_hash}")`.
- `record_id=fmea_id` (stable PK — satisfies P0 follow-up #2 "avoid random record_id").
- `write_audit_raw` only flushes; `recommend()` does NOT commit; route `await db.commit()` (`fmea.py:325`) is the single commit point. **`get_db` only rolls back** (`database.py:50`) — never describe as dep-auto-commit.
- `_get_cached` + `_cache_result` each gain `llm_available: bool` param (replace 4 `self.llm is not None` sites: lines 902, 925, 933, and response 663).
- `self.llm_timeout` (15s floor, line 562) **preserved** — it's a timeout field, not a provider ref.
- Legacy `LLMProvider` class NOT removed (management-review / search / CAPA-draft / LLMFusionLayer still use it). `app.state.llm_provider` no longer read by the recommend path.
- **Two `RecommendationService` construction sites must update**: `api/fmea.py:322` (recommend route) AND `fmea_service.py:266` (cache invalidation in `update_fmea`). Both drop `llm_provider=`.
- Backend tests: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -m pytest <path> -v`. Worktree has no local venv — use the shared one.
- Commits: one per task (or per TDD red→green). Match existing style (`feat(scope): ...`, `refactor(scope): ...`).
- `ruff check --fix` on touched files only (leave E702 one-liners — codebase style). Do NOT run ruff on unrelated files.

## File Structure

| Path | Responsibility |
|---|---|
| `backend/app/core/tenant.py` | NEW shared util: `tenant_schema(request: Request) -> str` |
| `backend/app/api/dashboard.py` | Drop local `_tenant_schema`; import from `core/tenant` (behavior unchanged) |
| `backend/app/services/recommendation_service.py` | Drop `llm_provider` ctor param + `self.llm`; add `tenant_schema` to `recommend()`; resolve `pc` before cache; rewire LLM call to `complete_json`; add `_write_recommend_audit` (two-state); thread `llm_available` through `_get_cached`/`_cache_result` |
| `backend/app/services/fmea_service.py` | `update_fmea:266` — drop `llm_provider=None` from `RecommendationService(...)` ctor |
| `backend/app/api/fmea.py` | `/recommend` route — drop `app.state.llm_provider`, pass `tenant_schema`, keep `await db.commit()` |
| `backend/tests/core/test_tenant.py` | NEW: `tenant_schema()` unit tests |
| `backend/tests/test_recommendation_service.py` | Adapt ctor calls (drop `llm_provider=`); add audit two-state + cache-gate-order regression tests |
| `backend/tests/test_dfmea_tool_trend_recommendation.py` | Adapt `_svc(llm)` → stub `build_client`/`complete_json`; add `tenant_schema` arg |
| `backend/tests/test_fmea_recommend_scope.py` | Adapt ctor calls (drop `llm_provider=`); add `tenant_schema` arg |
| `backend/tests/test_fmea_recommend_api.py` | NEW or adapted: route test asserting `tenant_schema` passed + `await db.commit()` |
| `backend/tests/test_fmea_service.py` (or wherever `update_fmea` cache-invalidation is tested) | Regression: `update_fmea` cache-invalidation path does not `TypeError` |

---

## Task 1: Shared `core/tenant.py` util + unit tests

**Files:**
- Create: `backend/app/core/tenant.py`
- Create: `backend/tests/core/test_tenant.py`
- (No modification to `dashboard.py` yet — Task 6 switches the import.)

**Interfaces:**
- Produces: `core.tenant.tenant_schema(request: Request) -> str` — returns `request.state.tenant.schema_name` when a tenant is set, else `"public"`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/core/test_tenant.py`:
```python
from starlette.datastructures import State
from starlette.requests import Request

from app.core.tenant import tenant_schema


class _Tenant:
    def __init__(self, schema_name: str):
        self.schema_name = schema_name


def _make_request(tenant=None) -> Request:
    scope = {"type": "http", "method": "GET", "headers": [], "path": "/", "query_string": b""}
    req = Request(scope)
    req._state = State()
    if tenant is not None:
        req.state.tenant = tenant
    return req


def test_tenant_schema_returns_schema_name_when_tenant_set():
    req = _make_request(_Tenant("tenant_acme"))
    assert tenant_schema(req) == "tenant_acme"


def test_tenant_schema_defaults_to_public_when_no_tenant():
    req = _make_request(None)
    assert tenant_schema(req) == "public"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/core/test_tenant.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.tenant'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/core/tenant.py`:
```python
"""Shared tenant-schema resolver for non-agent routes.

Mirrors backend/app/api/dashboard.py's _tenant_schema and
backend/app/api/agent/sessions.py:17's取法 — extracted here so dashboard
and fmea routes share one implementation.
"""
from __future__ import annotations

from starlette.requests import Request


def tenant_schema(request: Request) -> str:
    """Return the per-request tenant schema_name, or 'public' when no tenant."""
    tenant = getattr(request.state, "tenant", None)
    return tenant.schema_name if tenant else "public"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/core/test_tenant.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/tenant.py backend/tests/core/test_tenant.py
git commit -m "feat(core): add shared tenant_schema(request) util for P1-C"
```

---

## Task 2: Drop `llm_provider` ctor param + `self.llm`; thread `llm_available` through cache helpers

This task changes the constructor and the two cache helpers' signatures, and replaces the `self.llm` references that are **not** the LLM-call site (lines 557, 592, 663, 902, 925, 933). It does NOT yet add `build_client`/`complete_json`/audit — those land in Tasks 3–4. After this task, `recommend()` still calls LLM via a `pc` local that doesn't exist yet, so the `need_llm=True` branch is temporarily wired to `pc` (introduced Task 3). To keep the build green per-task, this task introduces `pc` as `None` placeholder and Task 3 fills `build_client`.

**Files:**
- Modify: `backend/app/services/recommendation_service.py` (lines 26, 555–557, 562, 590–595, 624, 663, 883–907, 909–940)
- Modify: `backend/app/services/fmea_service.py:266` (ctor call)
- Modify: `backend/tests/test_recommendation_service.py` (ctor calls)
- Modify: `backend/tests/test_dfmea_tool_trend_recommendation.py` (ctor calls + `_svc`)
- Modify: `backend/tests/test_fmea_recommend_scope.py` (ctor calls)

**Interfaces:**
- Produces: `RecommendationService.__init__(self, db, graph_repo, llm_timeout=None)` (no `llm_provider`). `recommend(..., tenant_schema: str)` signature (param added; body wired in Task 3). `_get_cached(..., llm_available: bool)`. `_cache_result(..., llm_available: bool)`.
- Consumes: P1-B `provider_adapter` (imported Task 3), `audit.write_audit_raw` (Task 4).

- [ ] **Step 1: Adapt the existing tests to the new ctor signature (red)**

In `backend/tests/test_recommendation_service.py`, replace every `RecommendationService(db=..., llm_provider=X, graph_repo=...)` with `RecommendationService(db=..., graph_repo=...)` (drop `llm_provider=`). Concretely:
- line 56: `RecommendationService(db=None, graph_repo=StubGraphRepo())`
- line 62: `RecommendationService(db=None, graph_repo=StubGraphRepo())`
- line 72: same
- line 80: same
- line 143: same
- line 255: same
- line 285: same

The `test_default_llm_timeout_covers_normal_provider_latency` test (line 47–58) currently passes `llm_provider=object()` only to assert `svc.llm_timeout >= 15`. Drop the `llm_provider=` arg; the assertion `svc.llm_timeout >= 15` still holds (timeout floor is in the ctor).

In `backend/tests/test_dfmea_tool_trend_recommendation.py`:
- line 69 (the `_svc` in the prompt-building test class): `return RecommendationService(db=None, graph_repo=StubGraphRepo())`
- line 154–155 (`_svc(self, llm)` in `TestRecommendIntegrationForToolTrend`): change signature to `_svc(self)` and `return RecommendationService(db=None, graph_repo=StubGraphRepo())` (drop `llm` param). The 3 integration tests (lines 175, 189, 203) all use `db=None` and `user=object()` — **all 3 must be migrated together here**, not deferred to Task 3, because:
  - Task 2's `pc=None` placeholder already changes the `no-llm` test (line 189) and `failure` test (line 203) behavior: with `pc=None`, `_need_llm=False` → `source="rule"` for both, so the `failure` test's `assert res.source == "rule_fallback"` (line 214) goes red until `build_client` is stubbed to return a pc.
  - After Task 4, the `failure` path calls `_write_recommend_audit(user.user_id, ...)` → `AttributeError` because `user=object()` has no `user_id`.
  - After Task 3, `db=None` tests that don't stub `build_client` will call real `build_client(None)` against a None session.

  Rewrite all 3 tests to stub `provider_adapter.build_client`/`complete_json` explicitly. The tests can keep `user = object()` (no `user_id`) because `_write_recommend_audit` is stubbed to a no-op (see `_patch` below, `raising=False`) — `user.user_id` is never accessed on the DB-free path. Since these are DB-free unit tests (no audit rows asserted), stubbing `_write_recommend_audit` also keeps them off the DB:

```python
    def _svc(self):
        return RecommendationService(db=None, graph_repo=StubGraphRepo())

    def _patch(self, svc, monkeypatch, *, build_client, complete_json=None):
        fmea = _StubFmea()
        monkeypatch.setattr(svc, "_get_fmea_or_404", AsyncMock(return_value=fmea))
        monkeypatch.setattr(svc, "_get_cached", AsyncMock(return_value=None))
        monkeypatch.setattr(svc, "_assemble_context", AsyncMock(return_value={}))
        monkeypatch.setattr(svc, "_cache_result", AsyncMock())
        # DB-free: short-circuit audit so user.user_id / db.flush aren't exercised here.
        # raising=False because _write_recommend_audit isn't added until Task 3
        # (the merged build_client+complete_json+audit task). Without raising=False
        # this AttributeError's at patch time and the no-llm test can't even run.
        monkeypatch.setattr(svc, "_write_recommend_audit", AsyncMock(), raising=False)
        monkeypatch.setattr(
            "app.core.permissions.get_user_permission",
            AsyncMock(return_value=PermissionLevel.VIEW),
        )
        monkeypatch.setattr(
            "app.services.recommendation_scope.resolve_product_line_codes",
            AsyncMock(return_value=["DC-DC-100"]),
        )
        from app.services.agent import provider_adapter
        monkeypatch.setattr(provider_adapter, "build_client", build_client)
        if complete_json is not None:
            monkeypatch.setattr(provider_adapter, "complete_json", complete_json)
        return fmea
```

  Then the 3 tests become:

```python
    async def test_dfmea_tool_with_llm_returns_suggestions(self, monkeypatch):
        async def _ok_client(db_arg):
            class _PC: pass
            return _PC()
        async def _ok_complete(pc, prompt, schema):
            return {"suggestions": [{"name": "边界图", "confidence": 0.85, "explanation": "适合结构分析"}]}
        svc = self._svc()
        fmea = self._patch(svc, monkeypatch, build_client=_ok_client, complete_json=_ok_complete)
        req = RecommendRequest(
            trigger_type="dfmea_tool",
            context={"task": "分析DC-DC转换器", "fmea_title": fmea.title},
            scope="current_product_line", include_graph=False,
        )
        user = object()
        res = await svc.recommend(fmea.id, req, user, _stub_request_scope(user), tenant_schema="public")
        assert any(s.name == "边界图" for s in res.suggestions)
        assert res.source in ("hybrid", "graph_enriched")

    async def test_dfmea_tool_no_llm_returns_empty_with_source_rule(self, monkeypatch):
        async def _raise(db_arg):
            from app.services.agent.provider_adapter import ProviderNotConfiguredError
            raise ProviderNotConfiguredError("no cfg")
        svc = self._svc()
        fmea = self._patch(svc, monkeypatch, build_client=_raise)
        req = RecommendRequest(
            trigger_type="dfmea_tool",
            context={"task": "分析DC-DC转换器"},
            scope="current_product_line", include_graph=False,
        )
        user = object()
        res = await svc.recommend(fmea.id, req, user, _stub_request_scope(user), tenant_schema="public")
        assert res.suggestions == []
        assert res.source == "rule"

    async def test_dfmea_trend_llm_failure_returns_rule_fallback(self, monkeypatch):
        async def _ok_client(db_arg):
            class _PC: pass
            return _PC()
        async def _boom(pc, prompt, schema):
            raise RuntimeError("llm boom")
        svc = self._svc()
        fmea = self._patch(svc, monkeypatch, build_client=_ok_client, complete_json=_boom)
        req = RecommendRequest(
            trigger_type="dfmea_trend",
            context={"task": "分析DC-DC转换器"},
            scope="current_product_line", include_graph=False,
        )
        user = object()
        res = await svc.recommend(fmea.id, req, user, _stub_request_scope(user), tenant_schema="public")
        assert res.source == "rule_fallback"
```

  Delete the now-unused `_OkLlm` and `_ThrowLlm` classes (lines 131–138) — they were stubs for the old `self.llm.complete` interface, no longer referenced.

In `backend/tests/test_fmea_recommend_scope.py`:
- line 54: `service = RecommendationService(db=db, graph_repo=fake_repo)`
- line 107: same

Also: every direct `await service.recommend(fmea_id, req, user, scope)` call in these test files gains a `tenant_schema="public"` trailing arg. Grep for `.recommend(` in these 3 files and append `tenant_schema="public"`:
```bash
cd backend && grep -rn "\.recommend(" tests/test_recommendation_service.py tests/test_dfmea_tool_trend_recommendation.py tests/test_fmea_recommend_scope.py
```
For each hit, change `svc.recommend(fmea.id, req, user, scope)` → `svc.recommend(fmea.id, req, user, scope, tenant_schema="public")`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_recommendation_service.py tests/test_dfmea_tool_trend_recommendation.py tests/test_fmea_recommend_scope.py -v`
Expected: FAIL — `RecommendationService.__init__() got an unexpected keyword argument 'llm_provider'` (and `recommend() got unexpected 'tenant_schema'`).

- [ ] **Step 3: Update `fmea_service.py:266` ctor call**

In `backend/app/services/fmea_service.py` line 266, change:
```python
rec_service = RecommendationService(db=db, llm_provider=None, graph_repo=_NullGraphRepo())
```
to:
```python
rec_service = RecommendationService(db=db, graph_repo=_NullGraphRepo())
```

- [ ] **Step 4: Rewrite the constructor + cache helper signatures**

In `backend/app/services/recommendation_service.py`:

Delete line 26 (`from app.services.llm_provider import LLMProvider`).

Constructor (lines 555–562) becomes:
```python
    def __init__(self, db: AsyncSession, graph_repo: FMEAGraphRepository, llm_timeout: int | None = None):
        self.db = db
        self.graph_repo = graph_repo
        self.rules = RuleEngine()
        # FMEA prompts on OpenAI-compatible gateways can take ~9s; keep a
        # safe lower bound so configured providers don't look unavailable.
        self.llm_timeout = max(llm_timeout or settings.LLM_TIMEOUT, 15)
```

`recommend()` signature (line 564) gains `tenant_schema: str`:
```python
    async def recommend(
        self, fmea_id: _uuid.UUID, request: RecommendRequest, user: User,
        request_scope: RequestScope, tenant_schema: str,
    ) -> RecommendResponse:
```

**Temporary `pc` placeholder** — immediately after `fmea = await self._get_fmea_or_404(fmea_id)` (line 567), insert:
```python
        # Task 3 replaces this placeholder with provider_adapter.build_client(db).
        pc = None
```
(This keeps the build green; Task 3 fills it. The `pc is None` paths all behave as "unconfigured" = rule fallback, matching the old `self.llm is None` path.)

Cache fall-through gate (lines 590–595) — change `self.llm is not None` to `pc is not None`:
```python
        if cache_result:
            cached_response, cached_with_llm = cache_result
            if pc is not None and not cached_with_llm:
                pass  # fall through to re-evaluate with LLM
            else:
                return cached_response
```

`_need_llm` call (line 624) — `llm_available=pc is not None`:
```python
        need_llm = self._need_llm(
            llm_available=pc is not None,
            has_specific=any(s.confidence >= 0.6 for s in all_suggestions),
            suggestion_count=len(all_suggestions),
            rule_quality=rule_result.quality,
        )
```

Response `llm_available` (line 663) — `pc is not None`:
```python
            llm_available=pc is not None,
```

`_get_cached` (line 883) — add `llm_available: bool` param and use it at line 902:
```python
    async def _get_cached(
        self, fmea_id: _uuid.UUID, trigger_type: str, context_hash: str,
        effective_scope: str, llm_available: bool,
    ) -> tuple[RecommendResponse, bool] | None:
```
and inside, line 902:
```python
                llm_available=llm_available,
```
Update the call site (line 587–589):
```python
        cache_result = await self._get_cached(
            fmea_id, request.trigger_type, context_hash, effective_scope, pc is not None
        )
```

`_cache_result` (line 909) — add `llm_available: bool` param, use it at lines 925 and 933:
```python
    async def _cache_result(
        self, fmea_id: _uuid.UUID, trigger_type: str, context_hash: str,
        fmea: FMEADocument, response: RecommendResponse, llm_available: bool,
    ) -> None:
```
Line 925 (insert values):
```python
                llm_available=llm_available,
```
Line 933 (on_conflict_do_update set):
```python
                    "llm_available": llm_available,
```
Update the call site (line 669):
```python
            await self._cache_result(fmea_id, request.trigger_type, context_hash, fmea, response, pc is not None)
```

- [ ] **Step 5: Skip the two LLM-exercising dfmea tests until Task 3**

The `with_llm` and `failure` dfmea tests stub `build_client` to return a pc, but the `pc=None` placeholder (Step 4) forces `_need_llm=False` → they'd fail on the `source` assertion. To keep Task 2 a clean green commit, mark both tests skipped with a reason pointing to Task 3:

```python
    @pytest.mark.skip(reason="Task 3 wires build_client resolution + complete_json call line")
    async def test_dfmea_tool_with_llm_returns_suggestions(self, monkeypatch):
        ...

    @pytest.mark.skip(reason="Task 3 wires build_client resolution + complete_json call line")
    async def test_dfmea_trend_llm_failure_returns_rule_fallback(self, monkeypatch):
        ...
```

(The `no_llm` test stays un-skipped — `pc=None` is exactly its scenario, so it passes now.)

- [ ] **Step 6: Run tests to verify they pass (green commit)**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_recommendation_service.py tests/test_dfmea_tool_trend_recommendation.py tests/test_fmea_recommend_scope.py -v`
Expected: PASS — `with_llm`/`failure` show as SKIPPED, everything else (including `no_llm`) PASS.

- [ ] **Step 7: Run `update_fmea` cache-invalidation regression**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_fmea_service.py -v -k "update or invalidat or cache"`
Expected: PASS — no `TypeError` from the ctor call at `fmea_service.py:266`. (If no `update_fmea` test exists yet, add a minimal one: construct `RecommendationService(db=db, graph_repo=_NullGraphRepo())` and call `invalidate_cache_for_fmea(uuid.uuid4())` — should not raise.)

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/app/services/fmea_service.py backend/tests/test_recommendation_service.py backend/tests/test_dfmea_tool_trend_recommendation.py backend/tests/test_fmea_recommend_scope.py
git commit -m "refactor(recommend): drop llm_provider ctor param, thread llm_available through cache helpers"
```

---

## Task 3: Resolve `pc` via `build_client` + switch call line to `complete_json` (un-skip dfmea tests)

Task 2 left the `pc=None` placeholder and skipped the two LLM-exercising dfmea tests. Task 3 replaces the placeholder with real `build_client` resolution AND switches the LLM call line from the deleted `self.llm.complete` to `provider_adapter.complete_json` — together, so the two skipped dfmea tests go green in one commit. No audit yet (Task 4); the `need_llm=True` branch's audit call is added in Task 4, so for now the call line switch is the only change inside the try block.

**Files:**
- Modify: `backend/app/services/recommendation_service.py` (replace `pc = None` placeholder; add imports; switch call line 641)
- Modify: `backend/tests/test_dfmea_tool_trend_recommendation.py` (remove the two `@pytest.mark.skip` decorators from Task 2)

**Interfaces:**
- Consumes: `provider_adapter.build_client(db) -> ProviderClient` (raises `ProviderNotConfiguredError`), `provider_adapter.complete_json(pc, prompt, response_schema) -> dict`.
- Produces: `pc` resolved before the cache check; LLM call on the base provider; dfmea `with_llm`/`failure` tests green.

- [ ] **Step 1: Implement `build_client` resolution + imports + call-line switch**

In `backend/app/services/recommendation_service.py`:

Add imports near the top (after line 24, the `from app.schemas.recommendation import ...` block):
```python
from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import ProviderNotConfiguredError
```

Replace the `pc = None` placeholder (inserted Task 2, immediately after `fmea = await self._get_fmea_or_404(fmea_id)`) with real resolution:
```python
        try:
            pc = await provider_adapter.build_client(self.db)
        except ProviderNotConfiguredError:
            pc = None
```

Switch the LLM call line (line 640–643) — replace `self.llm.complete(prompt, {})`:
```python
                llm_result = await asyncio.wait_for(
                    provider_adapter.complete_json(pc, prompt, {}),
                    timeout=self.llm_timeout,
                )
```
(`pc` is guaranteed non-None here: `need_llm=True` requires `pc is not None` via `_need_llm`, since `_need_llm` returns `llm_available and (...)` and we pass `llm_available=pc is not None`.)

- [ ] **Step 2: Remove the two `@pytest.mark.skip` decorators**

In `backend/tests/test_dfmea_tool_trend_recommendation.py`, delete the `@pytest.mark.skip(reason="Task 3 wires build_client resolution + complete_json call line")` lines above `test_dfmea_tool_with_llm_returns_suggestions` and `test_dfmea_trend_llm_failure_returns_rule_fallback` (added in Task 2 Step 5).

- [ ] **Step 3: Run the dfmea suite to verify the two un-skipped tests now pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_dfmea_tool_trend_recommendation.py -v`
Expected: PASS — all 3 dfmea integration tests green (`with_llm` gets `source in ("hybrid","graph_enriched")`; `failure` gets `source == "rule_fallback"`; `no_llm` stays `rule`). The `_write_recommend_audit` stub (`raising=False`) is still a no-op since the audit call isn't added until Task 4.

- [ ] **Step 4: Run the full recommendation suite (green commit)**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_recommendation_service.py tests/test_dfmea_tool_trend_recommendation.py tests/test_fmea_recommend_scope.py tests/test_pfmea_recommend.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/tests/test_dfmea_tool_trend_recommendation.py
git commit -m "feat(recommend): resolve pc via build_client, switch LLM call to complete_json"
```

---

## Task 4: Add `_write_recommend_audit` (two-state) on the LLM-attempt path

**Files:**
- Modify: `backend/app/services/recommendation_service.py` (add `_write_recommend_audit`; restructure `need_llm=True` so audit writes OUTSIDE the LLM try/except, in its own guard)
- Modify: `backend/tests/test_recommendation_service.py` (add audit two-state tests + cache-gate-order regression)

**Interfaces:**
- Consumes: `audit.write_audit_raw(db, user_id=, factory_id=, tenant_schema=, table_name=, record_id=, action=, correlation_id=, new_values=)`.
- Produces: `AuditLog` rows with `action="llm_recommend"`, `new_values.status ∈ {"success","llm_failed"}`, on `need_llm=True` only.

- [ ] **Step 1: Write the failing audit tests**

Append to `backend/tests/test_recommendation_service.py`. These need a real DB (audit rows land in `audit_logs`), so use the `db`/`admin_user`/`default_factory` fixtures + a real `FMEADocument`:

```python
@pytest.mark.asyncio
async def test_recommend_writes_success_audit_on_llm_success(
    db, default_factory, admin_user, monkeypatch
):
    """need_llm=True + complete_json succeeds → audit row status=success."""
    from sqlalchemy import select
    from app.models.audit import AuditLog
    from app.models.fmea import FMEADocument
    from app.services.agent import provider_adapter

    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-2026-001", fmea_type="PFMEA",
        title="t", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.flush()

    async def _ok_client(db_arg):
        class _PC: pass
        return _PC()
    async def _ok_complete(pc, prompt, schema):
        return {"suggestions": [{"name": "焊接虚焊", "confidence": 0.9, "explanation": "x"}]}
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _ok_complete)

    from app.core.deps import RequestScope, FactoryScope, ProductLineScope
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=admin_user,
    )
    from app.services.recommendation_service import RecommendationService, _NullGraphRepo
    svc = RecommendationService(db=db, graph_repo=_NullGraphRepo())
    req = RecommendRequest(
        trigger_type="failure_mode",
        context={"function_description": "电源转换", "failure_mode": "虚焊"},
        scope="current_product_line", include_graph=False,
    )
    res = await svc.recommend(fmea.fmea_id, req, admin_user, scope, tenant_schema="public")
    await db.commit()

    assert res.source in ("hybrid", "graph_enriched")
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_recommend")
    )).scalars().all()
    assert any(r.new_values.get("status") == "success" for r in rows)
    assert rows[0].factory_id == default_factory.id
    assert rows[0].tenant_schema == "public"
    assert rows[0].record_id == fmea.fmea_id
    assert rows[0].correlation_id is not None


@pytest.mark.asyncio
async def test_recommend_writes_llm_failed_audit_on_exception(
    db, default_factory, admin_user, monkeypatch
):
    """need_llm=True + complete_json raises → source=rule_fallback, audit status=llm_failed, NOT cached."""
    from sqlalchemy import select
    from app.models.audit import AuditLog
    from app.models.fmea import FMEADocument
    from app.models.recommendation_cache import RecommendationCache
    from app.services.agent import provider_adapter

    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-2026-002", fmea_type="PFMEA",
        title="t", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.flush()

    async def _ok_client(db_arg):
        class _PC: pass
        return _PC()
    async def _boom(pc, prompt, schema):
        raise RuntimeError("upstream 500")
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _boom)

    from app.core.deps import RequestScope, FactoryScope, ProductLineScope
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=admin_user,
    )
    from app.services.recommendation_service import RecommendationService, _NullGraphRepo
    svc = RecommendationService(db=db, graph_repo=_NullGraphRepo())
    req = RecommendRequest(
        trigger_type="failure_mode",
        context={"function_description": "电源转换", "failure_mode": "虚焊"},
        scope="current_product_line", include_graph=False,
    )
    res = await svc.recommend(fmea.fmea_id, req, admin_user, scope, tenant_schema="public")
    await db.commit()

    assert res.source == "rule_fallback"
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_recommend")
    )).scalars().all()
    assert any(r.new_values.get("status") == "llm_failed" for r in rows)
    # rule_fallback NOT cached
    cached = (await db.execute(
        select(RecommendationCache).where(RecommendationCache.fmea_id == fmea.fmea_id)
    )).scalars().all()
    assert len(cached) == 0


@pytest.mark.asyncio
async def test_recommend_no_audit_when_llm_unconfigured(
    db, default_factory, admin_user, monkeypatch
):
    """pc is None (ProviderNotConfiguredError) → rule fallback, NO audit, rule-mode cached."""
    from sqlalchemy import select
    from app.models.audit import AuditLog
    from app.models.fmea import FMEADocument
    from app.models.recommendation_cache import RecommendationCache
    from app.services.agent import provider_adapter

    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-2026-003", fmea_type="PFMEA",
        title="t", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.flush()

    async def _raise(db_arg):
        raise provider_adapter.ProviderNotConfiguredError("no cfg")
    monkeypatch.setattr(provider_adapter, "build_client", _raise)

    from app.core.deps import RequestScope, FactoryScope, ProductLineScope
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=admin_user,
    )
    from app.services.recommendation_service import RecommendationService, _NullGraphRepo
    svc = RecommendationService(db=db, graph_repo=_NullGraphRepo())
    req = RecommendRequest(
        trigger_type="failure_mode",
        context={"function_description": "电源转换", "failure_mode": "虚焊"},
        scope="current_product_line", include_graph=False,
    )
    res = await svc.recommend(fmea.fmea_id, req, admin_user, scope, tenant_schema="public")
    await db.commit()

    assert res.source in ("rule", "graph")  # NOT rule_fallback
    assert res.llm_available is False
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_recommend")
    )).scalars().all()
    assert len(rows) == 0  # unconfigured is NOT audited
    # rule-mode IS cached
    cached = (await db.execute(
        select(RecommendationCache).where(RecommendationCache.fmea_id == fmea.fmea_id)
    )).scalars().all()
    assert len(cached) == 1


@pytest.mark.asyncio
async def test_recommend_cache_gate_falls_through_when_llm_becomes_available(
    db, default_factory, admin_user, monkeypatch
):
    """Regression: rule-mode cache (no LLM) must fall through + re-evaluate once LLM is configured."""
    from app.models.fmea import FMEADocument
    from app.services.agent import provider_adapter

    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-2026-004", fmea_type="PFMEA",
        title="t", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.flush()

    from app.core.deps import RequestScope, FactoryScope, ProductLineScope
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=admin_user,
    )
    from app.services.recommendation_service import RecommendationService, _NullGraphRepo

    # 1st call: unconfigured → rule-mode cache written
    async def _raise(db_arg):
        raise provider_adapter.ProviderNotConfiguredError("no cfg")
    monkeypatch.setattr(provider_adapter, "build_client", _raise)
    svc = RecommendationService(db=db, graph_repo=_NullGraphRepo())
    req = RecommendRequest(
        trigger_type="failure_mode",
        context={"function_description": "电源转换", "failure_mode": "虚焊"},
        scope="current_product_line", include_graph=False,
    )
    res1 = await svc.recommend(fmea.fmea_id, req, admin_user, scope, tenant_schema="public")
    await db.commit()
    assert res1.llm_available is False
    assert res1.cached is False

    # 2nd call: LLM now available → must fall through (not return stale rule cache)
    async def _ok_client(db_arg):
        class _PC: pass
        return _PC()
    async def _ok_complete(pc, prompt, schema):
        return {"suggestions": [{"name": "焊接虚焊", "confidence": 0.9, "explanation": "x"}]}
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _ok_complete)
    svc2 = RecommendationService(db=db, graph_repo=_NullGraphRepo())
    res2 = await svc2.recommend(fmea.fmea_id, req, admin_user, scope, tenant_schema="public")
    await db.commit()
    assert res2.llm_available is True
    assert res2.source in ("hybrid", "graph_enriched")  # LLM-enhanced, not stale rule
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_recommendation_service.py -v -k "audit or cache_gate"`
Expected: FAIL — no audit rows written (`_write_recommend_audit` doesn't exist yet).

- [ ] **Step 3: Implement `_write_recommend_audit` + restructure `need_llm=True` branch (audit outside try/except)**

In `backend/app/services/recommendation_service.py`, add `uuid` import if not present (line 6 is `import uuid as _uuid` — use `_uuid.uuid5`/`_uuid.NAMESPACE_URL`).

The call line is already `provider_adapter.complete_json(...)` from Task 3. This step adds the `_write_recommend_audit` helper and restructures the `if need_llm:` block so the audit write sits OUTSIDE the LLM try/except (Task 3 left the try/except shape unchanged with no audit call; Task 4 adds the audit + the `llm_status` variable).

Add the helper method (place it near `_compute_context_hash`, ~line 879):
```python
    async def _write_recommend_audit(
        self, fmea_id: _uuid.UUID, trigger_type: str, context_hash: str,
        user: User, factory_id: _uuid.UUID, tenant_schema: str,
        status: str, source: str, suggestion_count: int,
    ) -> None:
        """Write an llm_recommend audit row (two-state: success / llm_failed).

        Only called on the need_llm=True path. Unconfigured (pc is None) is NOT
        audited — it silently rule-degrades. write_audit_raw flushes only; the
        route's await db.commit() is the single commit point.
        """
        from app.services.agent import audit as agent_audit
        correlation_id = _uuid.uuid5(
            _uuid.NAMESPACE_URL, f"fmea_recommend:{fmea_id}:{trigger_type}:{context_hash}"
        )
        await agent_audit.write_audit_raw(
            self.db,
            user_id=user.user_id,
            factory_id=factory_id,
            tenant_schema=tenant_schema,
            table_name="fmea_documents",
            record_id=fmea_id,
            action="llm_recommend",
            correlation_id=correlation_id,
            new_values={
                "status": status,
                "trigger_type": trigger_type,
                "source": source,
                "suggestion_count": suggestion_count,
            },
        )
```

Wire it into the `need_llm=True` branch. **⚠ Critical: the audit write MUST sit OUTSIDE the LLM try/except** — otherwise an audit failure (DB flush error, missing `user.user_id`, etc.) gets caught by `except Exception` and mis-tagged as `llm_failed`, or an audit exception in the failure branch bubbles up and crashes the request. Restructure the `if need_llm:` block (current lines 630–655) so the try/except only owns the LLM call + parse + merge and sets `status`/`source`, then a single audit write runs after:

```python
        if need_llm:
            llm_status = "llm_failed"  # default; overwritten on success
            try:
                import asyncio
                llm_context = await self._assemble_context(fmea, request)
                if graph_suggestions:
                    llm_context["similar_history"] = [
                        {"name": s.name, "from": s.source_document_no}
                        for s in graph_suggestions[:5]
                    ]
                prompt = self._build_prompt(request.trigger_type, llm_context)
                llm_result = await asyncio.wait_for(
                    provider_adapter.complete_json(pc, prompt, {}),
                    timeout=self.llm_timeout,
                )
                validated = SuggestionList.model_validate(llm_result)
                llm_items = [
                    SuggestionItem(
                        name=s.name, confidence=s.confidence, source="llm", explanation=s.explanation
                    )
                    for s in validated.suggestions
                ]
                all_suggestions = self._merge_and_deduplicate(all_suggestions, llm_items)
                source = "graph_enriched" if graph_suggestions else "hybrid"
                llm_status = "success"
            except Exception as e:
                source = "graph" if graph_suggestions else "rule_fallback"
                logger.warning("LLM failed, using rule+graph results: %s: %r", type(e).__name__, e)
            # Audit sits OUTSIDE the try/except so audit errors never masquerade
            # as LLM failures. Wrap in its own guard so an audit hiccup never
            # breaks the recommend response (audit is observability, not business logic).
            try:
                await self._write_recommend_audit(
                    fmea_id, request.trigger_type, context_hash,
                    user, fmea.factory_id, tenant_schema,
                    status=llm_status, source=source, suggestion_count=len(all_suggestions),
                )
            except Exception as audit_err:
                logger.warning("recommend audit write failed: %s: %r", type(audit_err).__name__, audit_err)
        else:
            source = "graph" if graph_suggestions else "rule"
```

Task 3 already switched the call line to `provider_adapter.complete_json(...)`; Task 4 only adds `llm_status` tracking + the `_write_recommend_audit` helper and moves the audit write outside the LLM try/except (into its own guard). The `complete_json` call inside the try block below is unchanged from Task 3 — don't re-edit it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_recommendation_service.py -v -k "audit or cache_gate"`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full recommendation suite**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_recommendation_service.py tests/test_dfmea_tool_trend_recommendation.py tests/test_fmea_recommend_scope.py tests/test_pfmea_recommend.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/tests/test_recommendation_service.py
git commit -m "feat(recommend): add two-state llm_recommend audit on LLM-attempt path"
```

---

## Task 5: Switch `/recommend` route to base provider + `tenant_schema`; switch dashboard to shared util

**Files:**
- Modify: `backend/app/api/fmea.py` (lines 320–325)
- Modify: `backend/app/api/dashboard.py` (line 37 + import + call site line 333)
- Modify: `backend/tests/test_fmea_recommend_api.py` (or create) — route-level test
- Modify: `backend/tests/test_quality_trend_interpret_api.py` (if it asserts dashboard `_tenant_schema` behavior — verify, don't break)

**Interfaces:**
- Consumes: `core.tenant.tenant_schema`, `RecommendationService(db, graph_repo, llm_timeout)`.
- Produces: `/recommend` route no longer reads `app.state.llm_provider`; dashboard uses shared `tenant_schema`.

- [ ] **Step 1: Write the failing route test**

Create `backend/tests/test_fmea_recommend_api.py` (or extend an existing fmea route test file). **⚠ Patch target must be `app.api.fmea.RecommendationService`** — the route module does `from app.services.recommendation_service import RecommendationService` (`fmea.py:221`), binding the name into the `app.api.fmea` namespace. Patching `app.services.recommendation_service.RecommendationService` does NOT affect the route (the name was already imported by value). Also **spy on `db.commit`** to assert the route keeps its explicit commit (a removed `await db.commit()` must turn this test red):

```python
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")

import pytest
import uuid
from unittest.mock import AsyncMock

from app.models.fmea import FMEADocument


@pytest.mark.asyncio
async def test_recommend_route_passes_tenant_schema_and_commits(
    admin_client, db, default_factory, admin_user, monkeypatch
):
    """POST /api/fmea/{id}/recommend no longer reads app.state.llm_provider;
    it constructs RecommendationService WITHOUT llm_provider, passes
    tenant_schema, and awaits db.commit()."""
    import app.api.fmea as fmea_api

    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no="PFMEA-2026-010", fmea_type="PFMEA",
        title="t", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()

    captured = {}

    class _FakeService:
        def __init__(self, db_arg, graph_repo, llm_timeout=None):
            captured["ctor_kwargs"] = list(self.__init__.__code__.co_varnames)
            # Reject llm_provider at construction so the test fails if the route
            # still passes it. (We assert via __init__ signature below instead.)
        async def recommend(self, *args, **kwargs):
            captured["recommend_kwargs"] = kwargs
            from app.schemas.recommendation import RecommendResponse
            return RecommendResponse(
                suggestions=[], source="rule", cached=False,
                llm_available=False, graph_match_count=0, effective_scope="current_product_line",
            )

    # Patch the name as bound in the route module's namespace.
    monkeypatch.setattr(fmea_api, "RecommendationService", _FakeService)

    # Spy on db.commit so a future deletion of `await db.commit()` turns this red.
    real_commit = db.commit
    commit_calls = []
    async def _spy_commit():
        commit_calls.append(True)
        await real_commit()
    monkeypatch.setattr(db, "commit", _spy_commit)

    resp = await admin_client.post(
        f"/api/fmea/{fmea.fmea_id}/recommend",
        json={"trigger_type": "failure_mode",
              "context": {"function_description": "x", "failure_mode": "y"},
              "scope": "current_product_line", "include_graph": False},
    )
    assert resp.status_code == 200
    assert "tenant_schema" in captured["recommend_kwargs"]
    assert captured["recommend_kwargs"]["tenant_schema"] == "public"
    assert len(commit_calls) >= 1, "route must await db.commit() (audit + cache rows depend on it)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_fmea_recommend_api.py -v`
Expected: FAIL — route still passes `llm_provider=` to the ctor (`_FakeService.__init__` rejects the kwarg → `TypeError`) and/or doesn't pass `tenant_schema` (`assert "tenant_schema" in captured["recommend_kwargs"]` fails) and/or doesn't commit (the route currently does commit, so this assertion may already pass — the `tenant_schema`/`llm_provider` assertions are the ones that fail first).

- [ ] **Step 3: Update the `/recommend` route**

In `backend/app/api/fmea.py` lines 320–325, replace:
```python
    llm = getattr(fastapi_request.app.state, "llm_provider", None)
    llm_timeout = getattr(fastapi_request.app.state, "llm_timeout", None)
    service = RecommendationService(db=db, llm_provider=llm, graph_repo=graph_repo, llm_timeout=llm_timeout)
    result = await service.recommend(fmea_id, request, scope.user, scope)
    await db.commit()
    return result
```
with:
```python
    llm_timeout = getattr(fastapi_request.app.state, "llm_timeout", None)
    service = RecommendationService(db=db, graph_repo=graph_repo, llm_timeout=llm_timeout)
    result = await service.recommend(
        fmea_id, request, scope.user, scope, tenant_schema=tenant_schema(fastapi_request),
    )
    await db.commit()
    return result
```
Add the import near the top of `fmea.py` (with the other `from app.core...` imports):
```python
from app.core.tenant import tenant_schema
```

- [ ] **Step 4: Switch dashboard to the shared util**

In `backend/app/api/dashboard.py`:
- Delete the local `_tenant_schema` function (line 37).
- Add import: `from app.core.tenant import tenant_schema`.
- Change the call site (line 333) from `tenant_schema=_tenant_schema(request)` to `tenant_schema=tenant_schema(request)`.

- [ ] **Step 5: Run the route test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_fmea_recommend_api.py -v`
Expected: PASS

- [ ] **Step 6: Run dashboard + quality-trend tests (P1-B regression — must stay green)**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest tests/test_quality_trend_interpret_api.py tests/test_quality_trend_service.py -v`
Expected: PASS (shared `tenant_schema` is behaviorally identical to the old local helper).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/fmea.py backend/app/api/dashboard.py backend/tests/test_fmea_recommend_api.py
git commit -m "feat(api): /recommend route on base provider + tenant_schema; dashboard on shared util"
```

---

## Task 6: Full regression + `make check`

**Files:** None (verification only).

- [ ] **Step 1: Run the full backend suite**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only .venv/bin/python -m pytest -x --tb=short`
Expected: PASS (all pre-existing + new tests).

- [ ] **Step 2: Run `make check` from repo root**

Run: `make check`
Expected: backend pytest + frontend `tsc --noEmit` + frontend build all green. (P1-C touches no frontend, but `make check` runs the full gate.)

- [ ] **Step 3: Lint touched files**

Run: `cd backend && .venv/bin/ruff check --fix app/core/tenant.py app/services/recommendation_service.py app/services/fmea_service.py app/api/fmea.py app/api/dashboard.py tests/core/test_tenant.py tests/test_recommendation_service.py tests/test_dfmea_tool_trend_recommendation.py tests/test_fmea_recommend_scope.py tests/test_fmea_recommend_api.py`
Expected: clean (leave any E702 one-liners — codebase style).

- [ ] **Step 4: Verify no stale `self.llm` / `llm_provider` refs remain in the recommend path**

Run:
```bash
cd backend && grep -n "self\.llm[^_]" app/services/recommendation_service.py
grep -n "llm_provider" app/services/recommendation_service.py app/api/fmea.py app/services/fmea_service.py
```
Expected: no matches (only `self.llm_timeout` should remain in `recommendation_service.py`).

- [ ] **Step 5: Commit if any lint fixes**

```bash
git add -A
git commit -m "chore(p1c): regression green — make check passes" --allow-empty
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- §2.1 ctor + `self.llm` sweep (8 sites) → Task 2 ✓
- §2.1 `pc` before cache check + fall-through gate → Task 3 (impl) + Task 4 (regression test) ✓
- §2.1 `need_llm` two-state audit, no `llm_not_configured` → Task 4 ✓
- §2.1 `user.user_id`, `correlation_id`, `record_id=fmea_id`, `write_audit_raw` flush-only → Task 4 ✓
- §2.1 route-layer `await db.commit()` (no dep auto-commit) → Task 5 (route keeps commit, **spy-tested**) + Global Constraints ✓
- §2.2 `/recommend` route + `fmea_service:266` ctor → Task 2 (fmea_service) + Task 5 (route) ✓
- §2.3 `core/tenant.py` shared util + dashboard switch → Task 1 (util) + Task 5 (dashboard switch) ✓
- §2.4 tests (success/llm_failed/llm_not_configured-no-audit/cache-gate regression/fmea_service no-TypeError/tenant unit/route) → Tasks 1–5 ✓

**Review-fix coverage (round 2 → round 3):**
- Audit/LLM isolation (audit write OUTSIDE the LLM try/except, in its own guard) → Task 4 Step 3 restructure ✓
- All 3 dfmea integration tests migrated (not just `_OkLlm`) with explicit `build_client`/`complete_json`/`_write_recommend_audit` stubs + `tenant_schema` arg; `_OkLlm`/`_ThrowLlm` deleted → Task 2 Step 1 ✓
- Route test patches `app.api.fmea.RecommendationService` (not `app.services.recommendation_service.RecommendationService`) → Task 5 Step 1 ✓
- Route `await db.commit()` spy-tested (removal turns the test red) → Task 5 Step 1 ✓
- **Round 3:** Task 2's `_write_recommend_audit` monkeypatch uses `raising=False` (helper doesn't exist until Task 4) → Task 2 `_patch` ✓
- **Round 3:** No mid-plan red commits — Task 2 skips `with_llm`/`failure` dfmea tests (clean green commit); Task 3 un-skips + does both `build_client` resolution AND `complete_json` call-line switch in one green commit; Task 4 adds audit + restructure in one green commit ✓
- **Round 3:** Removed stale duplicate commit block at end of (old) Task 3 ✓

**Placeholder scan:** none — every code step has full code.

**Type consistency:** `tenant_schema(request: Request) -> str` (Task 1) matches call sites in Task 5. `_get_cached(..., llm_available: bool)` / `_cache_result(..., llm_available: bool)` (Task 2) match call sites. `_write_recommend_audit(...)` signature (Task 4) matches its single post-try/except call site. `recommend(..., tenant_schema: str)` matches all test call sites.

**Scope:** single subsystem (recommend path), one plan. ✓
