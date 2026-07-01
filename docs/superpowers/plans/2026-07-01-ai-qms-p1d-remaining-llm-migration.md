# P1-D — Remaining LLM Consumers Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the 4 remaining `LLMProvider.complete()` consumers (8D D4/D5 fusion, RAG Q&A, management-review report, CAPA draft) onto the P0 agent base `provider_adapter.complete_json`, adding base `write_audit_raw` audit to the first three and preserving each consumer's existing degrade semantics.

**Architecture:** Thin migration — no agent tools, no harness, no `agent_session`. Each consumer resolves a `ProviderClient` via `provider_adapter.build_client(db)` (`ProviderNotConfiguredError` → `pc=None` → hybrid degrade / CAPA-draft 503), calls `provider_adapter.complete_json(pc, prompt, schema)` instead of `self.llm.complete(...)`, and (except CAPA draft) writes one `audit.write_audit_raw` row with status in `new_values`. CAPA draft keeps its existing `AI_DRAFT` audit and only swaps the provider call.

**Tech Stack:** Python 3.11 / FastAPI 0.115 / SQLAlchemy 2.0 async / pytest-asyncio. Agent base: `app.services.agent.provider_adapter` (`ProviderClient`, `build_client`, `complete_json`, `ProviderNotConfiguredError`), `app.services.agent.audit.write_audit_raw`. Shared: `app.core.tenant.tenant_schema(request)` (added in P1-C).

## Global Constraints

Copied verbatim from spec `docs/superpowers/specs/2026-07-01-ai-qms-p1d-remaining-llm-migration-design.md` (commit `5ddf8b5`):

- pydantic **2.9.2** pinned — **no pydantic-ai** (conflicts); use existing openai/anthropic SDKs via `provider_adapter`.
- `provider_adapter.complete_json(pc: ProviderClient, prompt: str, response_schema: dict) -> dict` (signature at `backend/app/services/agent/provider_adapter.py:154`). Internal `response_format=json_object`-rejected retry is transparent to callers.
- `provider_adapter.build_client(db) -> ProviderClient` raises `provider_adapter.ProviderNotConfiguredError` when LLM not configured.
- `ProviderClient` dataclass fields: `provider`, `client`, `model: str`, `base_url` (`provider_adapter.py:22-27`). **`pc` may be `None`** on unconfigured paths — guard `pc.model` with `(pc.model if pc else None)`.
- `audit.write_audit_raw(db, *, user_id, factory_id, tenant_schema, table_name, record_id, action, correlation_id=None, changed_fields=None, old_values=None, new_values=None) -> AuditLog` — **flushes only, no commit**; caller commits (`backend/app/services/agent/audit.py:11-36`). **No `status` parameter** — write status to `new_values={"status": ...}`.
- `audit_logs.record_id` is **`nullable=False`** (`backend/app/models/audit.py:18`) — never pass `None`; use a stable sentinel UUID where no business PK exists.
- `audit_logs.factory_id` / `correlation_id` are **nullable** (P0 migration `c0b6287b3d61`).
- `tenant_schema(request)` from `backend/app/core/tenant.py` — returns `request.state.tenant.schema_name` or `"public"`.
- **Do NOT delete `LLMProvider`** class — `ai_config_service` self-check still uses it.
- **Do NOT unify timeouts** to `settings.LLM_TIMEOUT` 15s. Preserve each consumer's existing source: D4/D5 `LLMFusionLayer.timeout=2.0`; mgmt `report_llm_timeout or settings.REPORT_LLM_TIMEOUT`; RAG `complete_json` internal httpx 30s; CAPA draft `capa_draft_llm_timeout`.
- Chinese UI/comments preserved; match surrounding style.
- Surgical changes only — every changed line traces to the spec.

**Test runner:** The worktree has **no `backend/.venv`**. Use the main checkout's venv pytest:
```
PYTEST=/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/pytest
```
All test runs below use: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST <path>::<test> -x -v` (run from the worktree's `backend/` so the worktree's `app/` is imported; the main venv supplies installed deps). `conftest.py:12` also sets `SECRET_KEY` via `setdefault`, so the env var is belt-and-suspenders. Tests need a live Postgres (the `db` fixture skips if unavailable — run against the dev DB).

**Existing test fixtures** (`backend/tests/conftest.py`): `db` (async session, flush-only), `default_factory` (stable Factory), `admin_user` (admin User in `default_factory`), `admin_client` (httpx ASGI client logged in as admin, L250). `_scope_for(user, default_factory, accessible_factory_ids=None, ...)` builds a `RequestScope`.

**P1-C test pattern to follow** (see `backend/tests/test_recommendation_service.py:318-372`): stub via `monkeypatch.setattr(provider_adapter, "build_client", _ok_client)` / `"complete_json", _ok_complete`; assert audit rows via `select(AuditLog).where(AuditLog.action == "...")`.

---

## File Structure

**Modified (no new production files):**

| File | Responsibility | Change |
|---|---|---|
| `backend/app/services/llm_fusion_layer.py` | LLM fusion + fallback for D4/D5 | Add `LLMOutcome` dataclass; `__init__(pc)`; `enrich()` returns `LLMOutcome`; call `complete_json` |
| `backend/app/services/hybrid_recommendation_pipeline.py` | D4/D5 pipeline orchestration | `__init__(pc)`; `recommend()` gains audit ctx params + writes `write_audit_raw` 3-state |
| `backend/app/api/capa.py` | D4/D5 + draft + capabilities routes | D4/D5: `build_client` + pass audit ctx + `await db.commit()`; `capa_capabilities` (L112): `build_client` probe |
| `backend/app/services/search_service.py` | RAG Q&A | `__init__` drops `llm_provider`; `ask()` resolves `pc` + `complete_json` + `write_audit_raw` 2-state |
| `backend/app/api/search.py` | search routes | `_get_search_service` drops `llm_provider`; `ask_question` passes user/tenant_schema + `await db.commit()` |
| `backend/app/services/management_review_report_service.py` | mgmt review report gen | `generate_report` drops `llm_provider`, resolves `pc`; helpers return outcome; `model_name` null-guard; add `write_audit_raw` 2-state |
| `backend/app/api/management_review.py` | mgmt review routes | generate route drops `app.state.llm_provider`, passes `tenant_schema` (no route commit) |
| `backend/app/services/capa_draft_service.py` | 8D draft D2-D8 | `build_client` replaces `app.state.llm_provider`; `complete_json` replaces `.complete()`; `llm_model_name` null-guard; keep `AI_DRAFT` audit |

**Test files (add new test functions to existing files):**

| File | Tests added |
|---|---|
| `backend/tests/test_llm_fusion_layer.py` | `LLMOutcome` return + 2-stage counting |
| `backend/tests/test_hybrid_pipeline.py` | pipeline `write_audit_raw` 3-state + no-audit-when-pc-None |
| `backend/tests/test_capa_recommendation.py` | D4/D5 route: tenant_schema + `await db.commit()` spy |
| `backend/tests/test_search_service.py` | RAG 2-state audit + sentinel record_id + sort/dedup correlation_id |
| `backend/tests/test_management_review_report_service.py` | helper outcome return + 2-state audit + pc=None model_name guard + CRUD audit coexists |
| `backend/tests/test_management_review_report_api.py` | generate route: no `app.state.llm_provider`, passes tenant_schema, no route commit |
| `backend/tests/test_capa_draft_service.py` | `complete_json` swap + 503 on pc=None + `llm_model_name` null-guard + no `write_audit_raw` introduced |
| `backend/tests/test_capa_draft_api.py` | `capa_capabilities` (L112) probes `build_client`; `draft_capabilities` (L480) unchanged |

---

## Task 1: 8D D4/D5 — LLMFusionLayer + pipeline + route

P1-C's natural extension. Three sub-cycles: (a) `LLMOutcome` + `enrich` return, (b) pipeline audit, (c) route wiring.

### Task 1a: `LLMOutcome` + `enrich()` return upgrade

**Files:**
- Modify: `backend/app/services/llm_fusion_layer.py` (whole file)
- Test: `backend/tests/test_llm_fusion_layer.py`

**Interfaces:**
- Produces: `LLMOutcome(candidates: list[RecommendationCandidate], attempted: int, succeeded: int, failed: int)`; `LLMFusionLayer.enrich(candidates, context) -> LLMOutcome`; `LLMFusionLayer.__init__(pc, timeout=2.0)`.

- [ ] **Step 1: Write failing tests** — append to `backend/tests/test_llm_fusion_layer.py`:

```python
import pytest
import asyncio
from app.services.llm_fusion_layer import LLMFusionLayer, LLMOutcome
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext
from app.services.agent import provider_adapter


def _ctx(stage="d4"):
    return RecommendationContext(
        capa_data={"d2_description": "虚焊", "d4_root_cause": "温度不足"},
        user_product_lines=None, stage=stage, fmea_docs=[], linked_fmea=None,
    )


def _cands(n=3):
    return [RecommendationCandidate(source="rule", content=f"c{i}", confidence=0.5,
            match_reason="r", metadata={}) for i in range(n)]


class _PC:
    model = "test-model"


@pytest.mark.asyncio
async def test_enrich_pc_none_no_attempt(monkeypatch):
    layer = LLMFusionLayer(pc=None)
    out = await layer.enrich(_cands(), _ctx())
    assert isinstance(out, LLMOutcome)
    assert out.attempted == 0 and out.succeeded == 0 and out.failed == 0
    assert out.candidates == _cands()


@pytest.mark.asyncio
async def test_enrich_success_counts_fusion(monkeypatch):
    async def _ok(pc, prompt, schema):
        return [{"candidate_id": 0, "match_reason": "x"},
                {"candidate_id": 1, "match_reason": "y"},
                {"candidate_id": 2, "match_reason": "z"}]
    monkeypatch.setattr(provider_adapter, "complete_json", _ok)
    layer = LLMFusionLayer(pc=_PC())
    out = await layer.enrich(_cands(3), _ctx())
    assert out.attempted >= 1 and out.failed == 0 and out.succeeded >= 1
    assert len(out.candidates) == 3  # 3 candidates, no fallback (<3 is false)


@pytest.mark.asyncio
async def test_enrich_partial_fusion_ok_fallback_fail(monkeypatch):
    # fusion returns 3 reasons (no fallback needed by count) — to exercise fallback
    # failure path, force enriched<3 by returning a non-list from fusion.
    calls = {"n": 0}
    async def _fusion_ok_fallback_boom(pc, prompt, schema):
        calls["n"] += 1
        if calls["n"] == 1:
            return "not-a-list"  # _merge_explanations returns candidates unchanged → still 3
        raise RuntimeError("fallback boom")
    monkeypatch.setattr(provider_adapter, "complete_json", _fusion_ok_fallback_boom)
    layer = LLMFusionLayer(pc=_PC())
    out = await layer.enrich(_cands(2), _ctx())  # 2 candidates → len<3 → fallback attempted
    assert out.attempted == 2
    assert out.succeeded == 1 and out.failed == 1  # fusion ok, fallback failed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_llm_fusion_layer.py -x -v` (set `PYTEST=/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/pytest` first).
Expected: FAIL — `LLMOutcome` import error / `enrich` returns a list not `LLMOutcome` / `__init__` signature mismatch (`pc` vs `llm_provider`).

- [ ] **Step 3: Implement** — rewrite `backend/app/services/llm_fusion_layer.py`:

```python
import asyncio
import dataclasses
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.services.agent import provider_adapter
from app.services.recommendation_types import RecommendationCandidate, RecommendationContext

logger = logging.getLogger(__name__)


@dataclass
class LLMOutcome:
    """Result of an enrich() call: fused candidates + per-stage LLM counts."""
    candidates: list[RecommendationCandidate]
    attempted: int = 0   # stage-1 fusion + stage-2 fallback (max 2)
    succeeded: int = 0
    failed: int = 0


class LLMFusionLayer:
    """LLM 融合层：为候选生成推荐理由 + 候选不足时回退生成。"""

    def __init__(self, pc, timeout: float = 2.0):
        self.pc = pc
        self.timeout = timeout

    async def enrich(
        self,
        candidates: list[RecommendationCandidate],
        context: RecommendationContext | None,
    ) -> LLMOutcome:
        if self.pc is None:
            return LLMOutcome(candidates=list(candidates) if candidates else [], attempted=0)

        attempted = 0
        succeeded = 0
        failed = 0
        enriched: list[RecommendationCandidate] = []

        # 阶段 1：为候选生成推荐理由（一次批量 fusion 调用）
        if candidates:
            attempted += 1
            try:
                prompt = self._build_fusion_prompt(candidates, context)
                result = await asyncio.wait_for(
                    provider_adapter.complete_json(self.pc, prompt, {}),
                    timeout=self.timeout,
                )
                enriched = self._merge_explanations(candidates, result)
                succeeded += 1
            except Exception as e:
                logger.warning(f"LLM fusion failed: {e}")
                enriched = list(candidates)
                failed += 1
        else:
            enriched = []

        # 阶段 2：候选不足时独立生成（一次 fallback 调用）
        if len(enriched) < 3 and context is not None:
            attempted += 1
            try:
                generated = await self._generate_fallback(context)
                enriched.extend(generated)
                succeeded += 1
            except Exception as e:
                logger.warning(f"LLM fallback generation failed: {e}")
                failed += 1

        return LLMOutcome(candidates=enriched, attempted=attempted,
                          succeeded=succeeded, failed=failed)

    # _build_fusion_prompt / _merge_explanations / _generate_fallback unchanged EXCEPT:
    # _generate_fallback replaces `self.llm.complete(prompt, {})` with:
    #   result = await asyncio.wait_for(
    #       provider_adapter.complete_json(self.pc, prompt, {}),
    #       timeout=self.timeout,
    #   )
    # (keep the rest of _build_fusion_prompt / _merge_explanations / _generate_fallback
    #  bodies exactly as today — only the LLM call line + `self.llm`→`self.pc` change)
```

> **Implementer note:** `_build_fusion_prompt`, `_merge_explanations`, and `_generate_fallback` (lines 53-155 of the current file) stay byte-for-byte the same except: (1) in `_generate_fallback` the call `self.llm.complete(prompt, {})` → `provider_adapter.complete_json(self.pc, prompt, {})` inside the existing `asyncio.wait_for(..., timeout=self.timeout)`; (2) no other `self.llm` references remain. Do not change prompt text, JSON parsing, or `RecommendationCandidate` construction.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_llm_fusion_layer.py -x -v`
Expected: PASS (all 4 new tests + existing fusion-layer tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm_fusion_layer.py backend/tests/test_llm_fusion_layer.py
git commit -m "feat(p1d): LLMFusionLayer.enrich returns LLMOutcome with 2-stage LLM counts"
```

### Task 1b: pipeline `write_audit_raw` 3-state

**Files:**
- Modify: `backend/app/services/hybrid_recommendation_pipeline.py:25-89`
- Test: `backend/tests/test_hybrid_pipeline.py`

**Interfaces:**
- Consumes: `LLMOutcome` (from 1a); `audit.write_audit_raw`; `tenant_schema` (str, passed in).
- Produces: `HybridRecommendationPipeline.__init__(self, db, pc, embedding_provider)`; `HybridRecommendationPipeline.recommend(context, *, user, report_id, factory_id, tenant_schema) -> RecommendationResult`.

- [ ] **Step 1: Write failing tests** — append to `backend/tests/test_hybrid_pipeline.py`:

```python
import uuid, hashlib, json
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.services.agent import provider_adapter
from app.services.hybrid_recommendation_pipeline import HybridRecommendationPipeline
from app.services.recommendation_types import RecommendationContext


def _ctx(stage="d4"):
    return RecommendationContext(
        capa_data={"d2_description": "x", "fmea_ref_id": None, "fmea_node_id": None,
                   "product_line_code": "DC-DC-100"},
        user_product_lines=None, stage=stage, fmea_docs=[], linked_fmea=None,
    )


class _PC:
    model = "test-model"


@pytest.mark.asyncio
async def test_pipeline_writes_success_audit(db, default_factory, admin_user, monkeypatch):
    async def _ok(pc, prompt, schema):
        return [{"candidate_id": 0, "match_reason": "r"}]
    async def _ok_client(db_arg):
        return _PC()
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _ok)
    # Stub embedding provider so SemanticSearchSource doesn't raise on construction;
    # returns no extra candidates so the fused list stays small + deterministic.
    class _NoEmbed:
        async def embed(self, text):
            return [0.0] * 8
        async def search(self, *a, **k):
            return []
    pipeline = HybridRecommendationPipeline(db=db, pc=_PC(), embedding_provider=_NoEmbed())
    report_id = uuid.uuid4()
    res = await pipeline.recommend(
        _ctx("d4"), user=admin_user, report_id=report_id,
        factory_id=default_factory.id, tenant_schema="public",
    )
    await db.commit()
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_recommend")
        .where(AuditLog.record_id == report_id)
    )).scalars().all()
    assert any(r.new_values.get("status") == "success" for r in rows), rows
    assert rows[0].factory_id == default_factory.id
    assert rows[0].tenant_schema == "public"
    assert rows[0].correlation_id is not None
```

> **Embedding stub:** `_NoEmbed` prevents `SemanticSearchSource(db, embedding_provider)` from raising when `embedding_provider=None`. If `SemanticSearchSource` calls `embed`/`search` at construction time (not just at `retrieve`), keep `_NoEmbed` as shown; if it only needs a non-None object, a bare `object()` suffices. Verify by running the test.

Add three more tests in the same file mirroring the success test:
- `test_pipeline_writes_partial_audit` — `complete_json` raises on the 2nd call only (fusion ok, fallback boom): assert `new_values.status == "partial"` and `new_values.failed == 1`.
- `test_pipeline_writes_llm_failed_audit` — `complete_json` always raises: assert `new_values.status == "llm_failed"`.
- `test_pipeline_no_audit_when_pc_none` — `build_client` raises `ProviderNotConfiguredError`; pass `pc=None` to the pipeline constructor; assert **zero** `llm_recommend` audit rows for that `report_id`.

(For the partial/failed tests, force `enrich` to attempt 2 stages by giving the fused list <3 candidates — set `embedding_provider=None` so only `RuleEngineSource` returns 0-2 candidates, or stub sources. Simplest: monkeypatch `pipeline.fusion.merge` to return a 2-element list so fallback triggers.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_hybrid_pipeline.py -x -v`
Expected: FAIL — `recommend()` rejects keyword args `user/report_id/factory_id/tenant_schema` (signature mismatch) / no audit row written.

- [ ] **Step 3: Implement** — edit `backend/app/services/hybrid_recommendation_pipeline.py`:

```python
import hashlib
import uuid

from app.services.agent import audit as audit_mod
from app.services.agent import provider_adapter
from app.services.fusion_engine import FusionEngine
from app.services.llm_fusion_layer import LLMFusionLayer
# ... existing recommendation_sources / recommendation_types imports ...
from app.models.user import User


class HybridRecommendationPipeline:
    """8D D4/D5 全混合推荐管道。"""

    def __init__(self, db, pc, embedding_provider):
        self.db = db
        self.pc = pc
        self.embedding = embedding_provider
        # ... d4_sources / d5_sources / d5_control_expander unchanged ...
        self.fusion = FusionEngine()
        self.llm_layer = LLMFusionLayer(pc)

    async def recommend(
        self,
        context: RecommendationContext,
        *,
        user: User,
        report_id: uuid.UUID,
        factory_id: uuid.UUID,
        tenant_schema: str,
    ) -> RecommendationResult:
        """执行完整推荐管道。"""
        # ... Stage 1 召回 / D5 Stage 2 control expansion / Stage 3 融合 unchanged ...

        # --- Stage 4: LLM 增强 ---
        outcome = await self.llm_layer.enrich(fused, context)

        # --- Stage 5: LLM 审计（仅当真正尝试过 LLM） ---
        if outcome.attempted > 0:
            if outcome.failed == 0:
                status = "success"
            elif outcome.failed < outcome.attempted:
                status = "partial"
            else:
                status = "llm_failed"
            capa_hash = hashlib.sha256(
                json.dumps(context.capa_data, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            correlation_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{context.stage}_recommend:{report_id}:{capa_hash}",
            )
            await audit_mod.write_audit_raw(
                self.db,
                user_id=user.user_id,
                factory_id=factory_id,
                tenant_schema=tenant_schema,
                table_name="capa_eightd",
                record_id=report_id,
                action="llm_recommend",
                correlation_id=correlation_id,
                new_values={
                    "status": status,
                    "trigger": context.stage,
                    "attempted": outcome.attempted,
                    "succeeded": outcome.succeeded,
                    "failed": outcome.failed,
                },
            )

        return RecommendationResult(items=outcome.candidates)
```

> Add `import hashlib, json, uuid` at top. Keep all of Stage 1 / D5 Stage 2 / Stage 3 code (lines 53-84) exactly as-is — only `self.llm`→`self.pc` in `__init__` (line 27) and the Stage 4/5 block above replace lines 86-89. The `json` import is already present in the file? No — add it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_hybrid_pipeline.py -x -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/hybrid_recommendation_pipeline.py backend/tests/test_hybrid_pipeline.py
git commit -m "feat(p1d): HybridRecommendationPipeline writes 3-state llm_recommend audit"
```

### Task 1c: D4/D5 route wiring + commit

**Files:**
- Modify: `backend/app/api/capa.py:374-393` (D4) and `:444-...` (D5) — the `llm_provider = request.app.state.llm_provider` ... `pipeline.recommend(context)` ... `return` blocks.
- Test: `backend/tests/test_capa_recommendation.py`

**Interfaces:**
- Consumes: `HybridRecommendationPipeline(db, pc, embedding_provider)`, `pipeline.recommend(context, *, user, report_id, factory_id, tenant_schema)`, `provider_adapter.build_client`, `tenant_schema(request)`.
- Produces: D4/D5 routes resolve `pc` via `build_client`, pass audit ctx, `await db.commit()`.

- [ ] **Step 1: Write failing route test** — append to `backend/tests/test_capa_recommendation.py`:

```python
import pytest
from app.services.agent import provider_adapter


@pytest.mark.asyncio
async def test_d4_route_passes_audit_ctx_and_commits(
    admin_client, db, default_factory, admin_user, monkeypatch
):
    """D4 route resolves pc via build_client, passes user/report_id/factory_id/
    tenant_schema to pipeline.recommend, and awaits db.commit()."""
    import app.api.capa as capa_api

    captured = {}

    class _FakePipeline:
        def __init__(self, db_arg, pc, embedding_provider):
            captured["pc"] = pc
        async def recommend(self, context, *, user, report_id, factory_id, tenant_schema):
            captured["recommend_kwargs"] = {
                "user": user, "report_id": report_id,
                "factory_id": factory_id, "tenant_schema": tenant_schema,
            }
            from app.services.recommendation_types import RecommendationResult
            return RecommendationResult(items=[])

    monkeypatch.setattr(capa_api, "HybridRecommendationPipeline", _FakePipeline)

    class _PC:
        model = "test-model"
    async def _ok_client(db_arg):
        return _PC()
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)

    real_commit = db.commit
    commit_calls = []
    async def _spy_commit():
        commit_calls.append(True)
        await real_commit()
    monkeypatch.setattr(db, "commit", _spy_commit)

    # Create a CAPA row for the route to load (factory_id = default_factory.id)
    from app.models.capa import CAPAEightD
    import uuid
    capa = CAPAEightD(report_id=uuid.uuid4(), document_no="8D-2026-901", title="t",
                      factory_id=default_factory.id, product_line_code="DC-DC-100",
                      status="D2_DESCRIPTION")
    db.add(capa)
    await db.commit()

    resp = await admin_client.get(f"/api/capa/{capa.report_id}/d4-fmea-recommendations")
    assert resp.status_code == 200, resp.text
    assert captured["recommend_kwargs"]["tenant_schema"] == "public"
    assert captured["recommend_kwargs"]["factory_id"] == default_factory.id
    assert captured["pc"] is not None
    assert len(commit_calls) >= 1, "route must await db.commit() (audit row depends on it)"
```

> **Implementer note:** Adjust the `CAPAEightD` constructor required fields to match the model (`backend/app/models/capa.py`). The `db` fixture is flush-only, but the ASGI route resolves through the real `get_db` (a different session) — the spy on the fixture `db` works because `admin_client` is wired to the same fixture session via `conftest.py:250` dependency overrides. If the spy does not fire, follow the exact wiring in `test_fmea_recommend_api.py:13-64` (P1-C's route test).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_capa_recommendation.py::test_d4_route_passes_audit_ctx_and_commits -x -v`
Expected: FAIL — route still reads `app.state.llm_provider` / `recommend()` called without audit ctx kwargs / no commit.

- [ ] **Step 3: Implement** — edit `backend/app/api/capa.py` D4 endpoint (around L374-393):

```python
    # replace:
    #   llm_provider = request.app.state.llm_provider
    #   embedding_provider = request.app.state.embedding_provider
    #   pipeline = HybridRecommendationPipeline(db, llm_provider, embedding_provider)
    # with:
    embedding_provider = request.app.state.embedding_provider
    from app.services.agent import provider_adapter
    from app.services.agent.provider_adapter import ProviderNotConfiguredError
    try:
        pc = await provider_adapter.build_client(db)
    except ProviderNotConfiguredError:
        pc = None
    pipeline = HybridRecommendationPipeline(db, pc, embedding_provider)
```

And replace `result = await pipeline.recommend(context)` + `return {"items": [...]}` with:

```python
    result = await pipeline.recommend(
        context,
        user=scope.user,
        report_id=report_id,
        factory_id=capa.factory_id,
        tenant_schema=tenant_schema(request),
    )
    await db.commit()
    return {"items": [c.to_d4_schema() for c in result.items]}
```

Add at top of `capa.py` (with other imports): `from app.core.tenant import tenant_schema`.

Apply the **identical** change to the D5 endpoint (`get_d5_fmea_recommendations`, around L444-end): same `pc` resolution, same `pipeline.recommend(...)` with audit ctx, `await db.commit()`, return. (D5 returns `{"existing_controls": ..., "general_suggestions": ...}` — keep its existing return shape; only wrap the `pipeline.recommend` call + add commit.)

> **D5 return shape caution:** The D5 endpoint currently returns `{"existing_controls": [...], "general_suggestions": [...]}` built from `result.items` (or similar). Do not change that mapping — only replace the `pipeline.recommend(context)` call with the kwargs form + add `await db.commit()` before the return.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_capa_recommendation.py -x -v`
Expected: PASS (new route test + existing D4/D5 tests; existing tests that asserted on `app.state.llm_provider` must be updated to stub `build_client` instead — fix any that break).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/capa.py backend/tests/test_capa_recommendation.py
git commit -m "feat(p1d): D4/D5 routes resolve pc via build_client, pass audit ctx, commit"
```

---

## Task 2: RAG search — `search_service.py` + `search.py`

**Files:**
- Modify: `backend/app/services/search_service.py:27-29` (`__init__`), `:215-284` (`ask` LLM block)
- Modify: `backend/app/api/search.py:19-25` (`_get_search_service`), `:54-77` (`ask_question`)
- Test: `backend/tests/test_search_service.py`

**Interfaces:**
- Consumes: `provider_adapter.build_client` / `complete_json`, `audit.write_audit_raw`, `tenant_schema(request)`.
- Produces: `SearchService(db, embedding_provider)` (no `llm_provider`); `SearchService.ask(question, user, tenant_schema, product_line_code=None, product_type_code=None, max_context_chunks=...) -> QAResponse`.

- [ ] **Step 1: Write failing tests** — append to `backend/tests/test_search_service.py`:

```python
import uuid, hashlib
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.services.agent import provider_adapter


class _PC:
    model = "test-model"


@pytest.mark.asyncio
async def test_rag_writes_success_audit(db, default_factory, admin_user, monkeypatch):
    """pc ok + complete_json returns answer → audit new_values.status=success,
    record_id is a stable sentinel (table_name='rag_qa')."""
    async def _ok_client(db_arg):
        return _PC()
    async def _ok_complete(pc, prompt, schema):
        return {"answer": "建议：检查焊接温度。"}
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _ok_complete)
    # Stub semantic_search so sources are returned without real embeddings
    from app.services.search_service import SearchService
    svc = SearchService(db=db, embedding_provider=None)
    monkeypatch.setattr(svc, "semantic_search", _fake_semantic_search)
    res = await svc.ask(question="虚焊怎么办", user=admin_user, tenant_schema="public")
    await db.commit()
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_rag_qa")
    )).scalars().all()
    assert any(r.new_values.get("status") == "success" for r in rows), rows
    assert rows[0].table_name == "rag_qa"
    assert rows[0].factory_id is None
    assert rows[0].record_id is not None  # sentinel UUID, not None
    # same question+sources → same record_id (stable)
    assert rows[0].correlation_id is not None


@pytest.mark.asyncio
async def test_rag_writes_llm_failed_audit(db, default_factory, admin_user, monkeypatch):
    async def _ok_client(db_arg):
        return _PC()
    async def _boom(pc, prompt, schema):
        raise RuntimeError("provider down")
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _boom)
    from app.services.search_service import SearchService
    svc = SearchService(db=db, embedding_provider=None)
    monkeypatch.setattr(svc, "semantic_search", _fake_semantic_search)
    res = await svc.ask(question="虚焊怎么办", user=admin_user, tenant_schema="public")
    assert "LLM 调用失败" in res.answer  # existing degrade behavior preserved
    await db.commit()
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_rag_qa")
    )).scalars().all()
    assert any(r.new_values.get("status") == "llm_failed" for r in rows)


@pytest.mark.asyncio
async def test_rag_no_audit_when_pc_none(db, default_factory, admin_user, monkeypatch):
    async def _raise(db_arg):
        raise provider_adapter.ProviderNotConfiguredError("no cfg")
    monkeypatch.setattr(provider_adapter, "build_client", _raise)
    from app.services.search_service import SearchService
    svc = SearchService(db=db, embedding_provider=None)
    monkeypatch.setattr(svc, "semantic_search", _fake_semantic_search)
    res = await svc.ask(question="虚焊怎么办", user=admin_user, tenant_schema="public")
    assert res.llm_available is False
    await db.commit()
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_rag_qa")
    )).scalars().all()
    assert rows == []


async def _fake_semantic_search(self, **kw):
    """Return one fake source so ask() reaches the LLM branch."""
    from app.schemas.search import SemanticSearchResponse, SearchResultItem
    return SemanticSearchResponse(results=[
        SearchResultItem(entity_type="fmea", entity_id=uuid.uuid4(),
                         chunk_text="焊接虚焊", score=0.9, source="vector",
                         metadata={"document_no": "PFMEA-2026-001"})
    ], total=1, query_time_ms=10)
```

> **Schema note:** `backend/app/schemas/search.py` defines `SearchResultItem` (fields `entity_type: str`, `entity_id: uuid.UUID`, `chunk_text: str`, `score: float`, `source: str`, `metadata: dict = {}` — **`document_no` is NOT a field**, it's read from `metadata["document_no"]` inside `ask()`) and `SemanticSearchResponse` (`results: list[SearchResultItem]`, `total: int`, `query_time_ms: int`). `QASource`/`QAResponse` are separate. The test's intent: `ask()` gets ≥1 source so it proceeds past the "no results" early return and into the LLM branch. Also add `test_rag_correlation_id_stable_across_source_order` — call `ask` twice with sources in different orders (monkeypatch `semantic_search` to return reversed `entity_id` lists), assert both audit rows share the same `correlation_id` (verifies sort/dedup before hashing). **Also add `test_rag_no_results_reports_llm_available_true_when_configured`**: `build_client` succeeds (pc not None), `semantic_search` returns `results=[]`; assert the response `llm_available is True` (old `self.llm is not None` semantics preserved — pc resolved *before* the no-results early return). This guards against the regression where the no-results branch hardcodes `llm_available=False`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_search_service.py -x -v`
Expected: FAIL — `SearchService.__init__` still requires `llm_provider` / `ask` signature lacks `user`/`tenant_schema` / no audit.

- [ ] **Step 3: Implement** — edit `backend/app/services/search_service.py`:

`__init__` (L27-29):
```python
    def __init__(self, db: AsyncSession, embedding_provider=None):
        self.db = db
        self.embedding = embedding_provider
```
Remove `self.llm = llm_provider`. Remove any `self.llm` attribute. (Audit: grep `self.llm` in the file — there are refs at L223, L237, L277; all handled below.)

`ask()` signature — add `user: User, tenant_schema: str` params (keep existing `question`, `product_line_code`, `product_type_code`, `max_context_chunks`). **Resolve `pc` at the TOP of `ask()` — before `semantic_search` — so the no-results early return can report `llm_available=pc is not None` truthfully** (matches old `self.llm is not None`; setting it `False` when LLM is configured but no hits is a behavior regression). Replace the body from `start = time.monotonic()` through the old `if not self.llm:` block (L237-247) with:

```python
        """RAG Q&A: search + LLM answer with citations."""
        start = time.monotonic()

        from app.services.agent import provider_adapter
        from app.services.agent.provider_adapter import ProviderNotConfiguredError
        try:
            pc = await provider_adapter.build_client(self.db)
        except ProviderNotConfiguredError:
            pc = None

        search_result = await self.semantic_search(
            query=question, user=user, product_line_code=product_line_code,
            product_type_code=product_type_code, limit=max_context_chunks,
        )

        if not search_result.results:
            elapsed = int((time.monotonic() - start) * 1000)
            return QAResponse(
                answer="未找到相关记录。",
                sources=[],
                llm_available=pc is not None,
                query_time_ms=elapsed,
            )

        sources = []
        for r in search_result.results:
            sources.append(QASource(
                entity_type=r.entity_type, entity_id=r.entity_id,
                document_no=r.metadata.get("document_no", ""),
                chunk_text=r.chunk_text, relevance_score=r.score,
            ))

        if pc is None:
            elapsed = int((time.monotonic() - start) * 1000)
            answer_parts = ["未配置 LLM，无法生成智能回答。以下是相关搜索结果：\n"]
            for i, s in enumerate(sources, 1):
                answer_parts.append(f"[{i}] {s.document_no} — {s.chunk_text[:100]}...")
            return QAResponse(
                answer="\n".join(answer_parts),
                sources=sources,
                llm_available=False,
                query_time_ms=elapsed,
            )
```

Then the prompt-building + LLM call block (the old L249-281: `context_parts`/`prompt`/`try: rag_schema = ... llm_response = await self.llm.complete(...)`) — replace the `try`/`except` with the audit-wrapped version:

```python
        from app.services.agent import audit as audit_mod
        # uuid + hashlib are module-level imports (see top-of-file note below)

        try:
            rag_schema = {
                "type": "object",
                "properties": {
                    "answer": {"type": "string", "description": "基于上下文生成的回答，支持 markdown 格式"}
                },
                "required": ["answer"],
            }
            llm_response = await provider_adapter.complete_json(pc, prompt, rag_schema)
            answer = llm_response.get("answer", "生成回答失败。")
            await audit_mod.write_audit_raw(
                self.db,
                user_id=user.user_id,
                factory_id=None,
                tenant_schema=tenant_schema,
                table_name="rag_qa",
                record_id=uuid.uuid5(uuid.NAMESPACE_URL, f"rag_qa:{_stable_query_hash(question)}"),
                action="llm_rag_qa",
                correlation_id=uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"rag_qa:{_stable_query_hash(question)}:{_stable_source_hash(sources)}",
                ),
                new_values={"status": "success", "model": pc.model},
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            answer = f"LLM 调用失败: {e}"
            await audit_mod.write_audit_raw(
                self.db,
                user_id=user.user_id,
                factory_id=None,
                tenant_schema=tenant_schema,
                table_name="rag_qa",
                record_id=uuid.uuid5(uuid.NAMESPACE_URL, f"rag_qa:{_stable_query_hash(question)}"),
                action="llm_rag_qa",
                correlation_id=uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"rag_qa:{_stable_query_hash(question)}:{_stable_source_hash(sources)}",
                ),
                new_values={"status": "llm_failed", "error": str(e), "model": (pc.model if pc else None)},
            )
```

**Top-of-file imports** (`search_service.py`): add `import hashlib` and `import uuid` at module level (the helpers below are module-level and need `hashlib`; `uuid` is used in `ask()`). Do NOT rely on a local `import uuid, hashlib` inside `ask()` — that is not visible to module-level helpers.

Add module-level helpers near the top of `search_service.py`:

```python
def _stable_query_hash(question: str) -> str:
    return hashlib.sha256(question.strip().encode()).hexdigest()[:16]


def _stable_source_hash(sources) -> str:
    # sort + dedup entity_ids before hashing so source order doesn't split correlation_id
    ids = sorted({str(getattr(s, "entity_id", "")) for s in sources})
    return hashlib.sha256(":".join(ids).encode()).hexdigest()[:16]
```

Audit the full `ask` body for any remaining `self.llm` and replace per spec §3.2 (`self.llm` → `pc`; all three old refs L223/L237/L277 are covered by the blocks above).

- [ ] **Step 4: Edit `backend/app/api/search.py`**:

`_get_search_service` (L19-25) — drop `llm_provider`:
```python
def _get_search_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SearchService:
    embedding_provider = getattr(request.app.state, "embedding_provider", None)
    return SearchService(db=db, embedding_provider=embedding_provider)
```

`ask_question` (L54-77) — replace the `if not service.llm and not service.embedding:` guard (which references the removed `service.llm`) and the `service.ask(...)` call:
```python
    level = await get_user_permission(user, Module.KNOWLEDGE_GRAPH, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 knowledge_graph 模块的 VIEW 权限")
    if not service.embedding:
        raise HTTPException(status_code=503, detail="搜索服务未配置（无 embedding provider）")
    from app.core.tenant import tenant_schema
    res = await service.ask(
        question=body.question,
        user=user,
        tenant_schema=tenant_schema(request),
        product_line_code=body.product_line_code,
        product_type_code=body.product_type_code,
        max_context_chunks=body.max_context_chunks,
    )
    await db.commit()
    return res
```

> **Guard change rationale:** Old guard `not service.llm and not service.embedding` → 503. Now `service.llm` is gone; RAG degrade when LLM unconfigured is **200 sources-only** (hybrid, spec §3.2), not 503. So the 503 guard becomes embedding-only (no embedding = can't search at all). This preserves the "no embedding → 503" path and lets the LLM-unconfigured case return 200 with sources.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_search_service.py -x -v`
Expected: PASS. Fix any existing `test_search_service.py` tests that constructed `SearchService(db, llm_provider=..., embedding_provider=...)` — drop the `llm_provider` arg.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/search_service.py backend/app/api/search.py backend/tests/test_search_service.py
git commit -m "feat(p1d): RAG ask migrates to complete_json + 2-state write_audit_raw (sentinel record_id)"
```

---

## Task 3: Management review report — helper outcome + 2-state audit

**Files:**
- Modify: `backend/app/services/management_review_report_service.py:137-161` (`_enrich_with_llm`), `:180-210` (`_generate_executive_summary`), `:219-264` (`generate_report`)
- Modify: `backend/app/api/management_review.py:426-432` (generate route)
- Test: `backend/tests/test_management_review_report_service.py`, `backend/tests/test_management_review_report_api.py`

**Interfaces:**
- Consumes: `provider_adapter.build_client` / `complete_json`, `audit.write_audit_raw`, `tenant_schema(request)`.
- Produces: `_enrich_with_llm(sections, review, pc, report_llm_timeout) -> (sections, section_attempted, section_failed_keys)`; `_generate_executive_summary(sections, review, pc, report_llm_timeout) -> (summary, recs, summary_failed)`; `generate_report(db, review, user, *, use_llm, report_llm_timeout, tenant_schema) -> content` (no `llm_provider` param).

- [ ] **Step 1: Write failing service tests** — append to `backend/tests/test_management_review_report_service.py`:

```python
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.services.agent import provider_adapter


class _PC:
    model = "test-model"


@pytest.mark.asyncio
async def test_enrich_returns_section_outcome(db, monkeypatch):
    """_enrich_with_llm returns (sections, section_attempted, section_failed_keys)."""
    from app.services.management_review_report_service import _enrich_with_llm
    async def _ok(pc, prompt, schema):
        return {"analysis": "a", "findings": ["f"], "recommendations": ["r"]}
    monkeypatch.setattr(provider_adapter, "complete_json", _ok)
    sections = [{"key": "k1", "title": "t1", "base_text": "b1"},
                {"key": "k2", "title": "t2", "base_text": "b2"}]
    out_sections, attempted, failed_keys = await _enrich_with_llm(sections, _review(), _PC(), None)
    assert attempted == 2 and failed_keys == []


@pytest.mark.asyncio
async def test_enrich_tracks_failed_sections(db, monkeypatch):
    from app.services.management_review_report_service import _enrich_with_llm
    calls = {"n": 0}
    async def _boom_on_second(pc, prompt, schema):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return {"analysis": "a", "findings": [], "recommendations": []}
    monkeypatch.setattr(provider_adapter, "complete_json", _boom_on_second)
    sections = [{"key": "k1", "title": "t1", "base_text": "b1"},
                {"key": "k2", "title": "t2", "base_text": "b2"}]
    _, attempted, failed_keys = await _enrich_with_llm(sections, _review(), _PC(), None)
    assert attempted == 2 and failed_keys == ["k2"]


@pytest.mark.asyncio
async def test_generate_report_writes_success_audit(db, default_factory, admin_user, monkeypatch):
    async def _ok_client(db_arg):
        return _PC()
    async def _ok(pc, prompt, schema):
        # section schema vs summary schema — return plausible dict for either
        return {"analysis": "a", "findings": [], "recommendations": [],
                "executive_summary": "s", "overall_recommendations": []}
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _ok)
    from app.services.management_review_report_service import generate_report
    review = _review(db, default_factory)  # build a ManagementReview row
    content = await generate_report(db, review, admin_user, use_llm=True,
                                    report_llm_timeout=None, tenant_schema="public")
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_report_generate")
        .where(AuditLog.record_id == review.review_id)
    )).scalars().all()
    assert any(r.new_values.get("status") == "success" for r in rows), rows
    assert rows[0].tenant_schema == "public"
    # CRUD audit still present
    crud = (await db.execute(
        select(AuditLog).where(AuditLog.action == "REPORT_GENERATE")
    )).scalars().all()
    assert len(crud) >= 1


@pytest.mark.asyncio
async def test_generate_report_llm_failed_audit_with_detail(db, default_factory, admin_user, monkeypatch):
    async def _ok_client(db_arg):
        return _PC()
    async def _boom(pc, prompt, schema):
        raise RuntimeError("down")
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _boom)
    from app.services.management_review_report_service import generate_report
    review = _review(db, default_factory)
    content = await generate_report(db, review, admin_user, use_llm=True,
                                    report_llm_timeout=None, tenant_schema="public")
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_report_generate")
    )).scalars().all()
    assert any(r.new_values.get("status") == "llm_failed" for r in rows)
    # failed detail present (section_failed_keys non-empty and/or summary_failed True)
    assert any(
        r.new_values.get("section_failed_keys") or r.new_values.get("summary_failed")
        for r in rows
    )


@pytest.mark.asyncio
async def test_generate_report_pc_none_no_audit_no_attribute_error(db, default_factory, admin_user, monkeypatch):
    async def _raise(db_arg):
        raise provider_adapter.ProviderNotConfiguredError("no cfg")
    monkeypatch.setattr(provider_adapter, "build_client", _raise)
    from app.services.management_review_report_service import generate_report
    review = _review(db, default_factory)
    # Must not raise AttributeError on pc.model when pc is None
    content = await generate_report(db, review, admin_user, use_llm=True,
                                    report_llm_timeout=None, tenant_schema="public")
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "llm_report_generate")
    )).scalars().all()
    assert rows == []
```

> **Implementer note:** Add a `_review(db, default_factory)` helper in this test file that inserts a `ManagementReview` row (factory_id=default_factory.id) and returns it — mirror how `test_management_review_report_service.py` already builds reviews (read its existing fixtures).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_management_review_report_service.py -x -v`
Expected: FAIL — helpers return `(sections, bool)` not outcome tuple / `generate_report` rejects `tenant_schema` kwarg / `llm_provider` param still required.

- [ ] **Step 3: Implement helpers** — edit `backend/app/services/management_review_report_service.py`:

`_enrich_with_llm` (L137-161) — change signature + return:
```python
async def _enrich_with_llm(
    sections: list[dict],
    review: ManagementReview,
    pc,                                    # was: llm_provider: "LLMProvider | None"
    report_llm_timeout: int | None = None,
) -> tuple[list[dict], int, list[str]]:
    if pc is None:
        return sections, 0, []
    timeout = report_llm_timeout or settings.REPORT_LLM_TIMEOUT
    section_attempted = 0
    section_failed_keys: list[str] = []
    for section in sections:
        section_attempted += 1
        try:
            prompt = _build_section_prompt(section, review)
            response = await asyncio.wait_for(
                provider_adapter.complete_json(pc, prompt, LLM_SECTION_SCHEMA),
                timeout=timeout,
            )
            section["ai_analysis"] = str(response.get("analysis", "")).strip()
            section["findings"] = [str(x) for x in response.get("findings", []) if x]
            section["recommendations"] = [str(x) for x in response.get("recommendations", []) if x]
        except Exception as e:
            logger.warning("LLM enrichment failed for section %s: %s", section["key"], e)
            section_failed_keys.append(section["key"])
    return sections, section_attempted, section_failed_keys
```

`_generate_executive_summary` (L180-210) — change signature + return:
```python
async def _generate_executive_summary(
    sections: list[dict],
    review: ManagementReview,
    pc,                                    # was: llm_provider
    report_llm_timeout: int | None = None,
) -> tuple[str, list[str], bool]:
    if pc is None:
        return _fallback_executive_summary(review), [], False
    timeout = report_llm_timeout or settings.REPORT_LLM_TIMEOUT
    try:
        response = await asyncio.wait_for(
            provider_adapter.complete_json(
                pc,
                _build_executive_prompt(sections, review),
                {
                    "type": "object",
                    "properties": {
                        "executive_summary": {"type": "string"},
                        "overall_recommendations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["executive_summary", "overall_recommendations"],
                },
            ),
            timeout=timeout,
        )
        return (
            str(response.get("executive_summary", "")).strip(),
            [str(x) for x in response.get("overall_recommendations", []) if x],
            False,
        )
    except Exception as e:
        logger.warning("LLM executive summary failed: %s", e)
        return _fallback_executive_summary(review), [], True
```

Add import at top: `from app.services.agent import provider_adapter, audit as audit_mod` and `import uuid, hashlib`.

- [ ] **Step 4: Implement `generate_report`** — edit L219-264. Drop the `llm_provider` parameter, resolve `pc`, call helpers with new signatures, compute `model_name` with null-guard, write LLM audit, keep CRUD `_write_audit` + the existing `await db.commit()` at L264:

```python
async def generate_report(
    db: AsyncSession,
    review: ManagementReview,
    user: User,
    *,
    use_llm: bool = True,
    report_llm_timeout: int | None = None,
    tenant_schema: str = "public",
) -> dict:
    # ... existing _build_sections etc. unchanged ...

    try:
        pc = await provider_adapter.build_client(db)
    except provider_adapter.ProviderNotConfiguredError:
        pc = None

    section_failed_keys: list[str] = []
    summary_failed = False
    section_attempted = 0

    if use_llm and pc is not None:
        sections, section_attempted, section_failed_keys = await _enrich_with_llm(
            sections, review, pc, report_llm_timeout=report_llm_timeout
        )

    if use_llm and pc is not None:
        summary, recs, summary_failed = await _generate_executive_summary(
            sections, review, pc, report_llm_timeout=report_llm_timeout
        )
    else:
        summary, recs = _fallback_executive_summary(review), []

    model_name = (pc.model if pc else None) or settings.LLM_MODEL or "rule-only"

    # Recompute llm_enriched (old _enrich_with_llm returned this bool) for content
    # assembly + CRUD audit changed_fields that previously read it. Semantic:
    # "at least one section was LLM-enriched" = attempted > 0 and not all failed.
    llm_enriched = section_attempted > 0 and section_attempted > len(section_failed_keys)

    # --- LLM audit (only when LLM was attempted) ---
    if use_llm and pc is not None:
        if not section_failed_keys and not summary_failed:
            audit_status = "success"
        else:
            audit_status = "llm_failed"
        sections_hash = hashlib.sha256(
            json.dumps([s["key"] for s in sections], sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        await audit_mod.write_audit_raw(
            db,
            user_id=user.user_id,
            factory_id=review.factory_id,
            tenant_schema=tenant_schema,
            table_name="management_reviews",
            record_id=review.review_id,
            action="llm_report_generate",
            correlation_id=uuid.uuid5(
                uuid.NAMESPACE_URL, f"mgmt_review:{review.review_id}:{sections_hash}"
            ),
            new_values={
                "status": audit_status,
                "model": model_name,
                "section_attempted": section_attempted,
                "section_failed_keys": section_failed_keys,
                "summary_failed": summary_failed,
            },
        )

    # ... existing content dict assembly, model_name used where previously getattr(llm_provider,'model') ...

    await _write_audit(db, review.review_id, user.user_id, "REPORT_GENERATE", {
        # ... existing changed_fields, with model_name substituted for getattr(llm_provider,"model") ...
    })
    await db.commit()   # L264 — KEEP; commits LLM audit + CRUD audit
    return content
```

> **Implementer note:** The real `generate_report` body (L219-264) assembles `content` (which embeds `llm_enriched`) and calls `_write_audit(REPORT_GENERATE, {...})` then `await db.commit()`. Preserve all of that — the only changes are: (1) drop `llm_provider` param, add `tenant_schema` keyword param; (2) resolve `pc`; (3) call helpers with `pc` and unpack their new 3-tuple returns (`sections, section_attempted, section_failed_keys` / `summary, recs, summary_failed`); (4) `model_name` null-guard; (5) **recompute `llm_enriched`** (see line above — the old helper returned this bool; `content` assembly + CRUD `_write_audit(REPORT_GENERATE, {...})` changed_fields both read it, so feed the recomputed value into both where the old code used the helper's bool); (6) insert the LLM `write_audit_raw` block **before** the existing `_write_audit` + `await db.commit()` so both audit rows ride the L264 commit. Do **not** add a route-level commit (Task 3 Step 5 confirms). Read the actual L219-264 body and carry over every line not shown above — in particular find every read of the old `llm_enriched` bool and replace with the recomputed value.

- [ ] **Step 5: Edit route** — `backend/app/api/management_review.py:426-432`:

```python
    try:
        report_llm_timeout = getattr(request.app.state, "report_llm_timeout", None)
        from app.core.tenant import tenant_schema
        content = await report_service.generate_report(
            db, review, scope.user,
            use_llm=req.use_llm,
            report_llm_timeout=report_llm_timeout,
            tenant_schema=tenant_schema(request),
        )
        # NO db.commit() here — generate_report commits internally (service L264)
        return schemas.management_review.ReportGenerateResponse(
            report_status=review.report_status,
            generated_report=schemas.management_review.ReportContent.model_validate(content),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

Remove the `llm_provider = getattr(request.app.state, "llm_provider", None)` line.

- [ ] **Step 6: Run service tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_management_review_report_service.py -x -v`
Expected: PASS. Fix existing tests in that file that called `generate_report(..., llm_provider=..., ...)` or `_enrich_with_llm(sections, review, llm_provider)` — update to new signatures.

- [ ] **Step 7: Write + run route test** — append to `backend/tests/test_management_review_report_api.py` a test mirroring `test_fmea_recommend_api.py:13-64`: monkeypatch `report_service.generate_report` to capture `tenant_schema` kwarg + assert no `app.state.llm_provider` read + assert route does **not** call `db.commit` (the service commits). Run:

`cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_management_review_report_api.py -x -v` → PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/management_review_report_service.py backend/app/api/management_review.py backend/tests/test_management_review_report_service.py backend/tests/test_management_review_report_api.py
git commit -m "feat(p1d): mgmt review generate_report migrates to complete_json + 2-state audit (helper outcome)"
```

---

## Task 4: CAPA draft — provider swap only, keep `AI_DRAFT` audit

**Files:**
- Modify: `backend/app/services/capa_draft_service.py:239-240` (resolve pc + model_name), `:387-389` (503 guard), `:408` (complete call)
- Modify: `backend/app/api/capa.py:112-126` (`capa_capabilities`)
- Test: `backend/tests/test_capa_draft_service.py`, `backend/tests/test_capa_draft_api.py`

**Interfaces:**
- Consumes: `provider_adapter.build_client` / `complete_json`.
- Produces: `generate_draft(db, report_id, step, req, user, request)` resolves `pc` internally; 503 when `pc is None`; existing `_write_audit` unchanged.

- [ ] **Step 1: Write failing service tests** — append to `backend/tests/test_capa_draft_service.py`:

```python
import pytest
from app.services.agent import provider_adapter


class _PC:
    model = "test-model"


@pytest.mark.asyncio
async def test_draft_uses_complete_json_and_no_write_audit_raw(
    db, default_factory, admin_user, monkeypatch
):
    """generate_draft calls provider_adapter.complete_json (not llm_provider.complete);
    does NOT introduce write_audit_raw (keeps existing AI_DRAFT AuditLog audit)."""
    async def _ok_client(db_arg):
        return _PC()
    async def _ok_complete(pc, prompt, schema):
        # paragraph format validates against ParagraphLLMOutput(content: str)
        return {"content": "AI 草稿正文"}
    monkeypatch.setattr(provider_adapter, "build_client", _ok_client)
    monkeypatch.setattr(provider_adapter, "complete_json", _ok_complete)

    # Spy: write_audit_raw must NOT be called
    from app.services.agent import audit as audit_mod
    raw_calls = []
    async def _spy_raw(*a, **k):
        raw_calls.append(True)
        raise AssertionError("write_audit_raw must not be introduced in CAPA draft")
    monkeypatch.setattr(audit_mod, "write_audit_raw", _spy_raw)

    from app.services.capa_draft_service import generate_draft
    from app.schemas.capa_draft import DraftRequest
    from app.models.capa import CAPAEightD
    import uuid
    # CAPAEightD: document_no (not doc_no) is the field; title is nullable=False.
    capa = CAPAEightD(report_id=uuid.uuid4(), document_no="8D-2026-902", title="测试标题足够长",
                      factory_id=default_factory.id, product_line_code="DC-DC-100",
                      status="D2_DESCRIPTION")
    db.add(capa); await db.commit()

    # paragraph format → no structured schema validation; request_id is parsed as
    # UUID internally, so pass a valid UUID4 string (not "r1").
    req = DraftRequest(format="paragraph", request_id=str(uuid.uuid4()))
    # build a fake Request with app.state carrying timeout
    class _Req:
        class app:
            class state:
                capa_draft_llm_timeout = 30
    result = await generate_draft(db, capa.report_id, "d2", req, admin_user, _Req())
    assert raw_calls == []  # no write_audit_raw introduced
    assert result is not None


@pytest.mark.asyncio
async def test_draft_503_when_pc_none_no_attribute_error(
    db, default_factory, admin_user, monkeypatch
):
    async def _raise(db_arg):
        raise provider_adapter.ProviderNotConfiguredError("no cfg")
    monkeypatch.setattr(provider_adapter, "build_client", _raise)
    from app.services.capa_draft_service import generate_draft
    from app.schemas.capa_draft import DraftRequest
    from app.models.capa import CAPAEightD
    import uuid
    from fastapi import HTTPException
    capa = CAPAEightD(report_id=uuid.uuid4(), document_no="8D-2026-903", title="测试标题足够长",
                      factory_id=default_factory.id, product_line_code="DC-DC-100",
                      status="D2_DESCRIPTION")
    db.add(capa); await db.commit()
    req = DraftRequest(format="paragraph", request_id=str(uuid.uuid4()))
    class _Req:
        class app:
            class state:
                capa_draft_llm_timeout = 30
    with pytest.raises(HTTPException) as ei:
        await generate_draft(db, capa.report_id, "d2", req, admin_user, _Req())
    assert ei.value.status_code == 503
    # llm_model_name null-guard: the 503 audit row's model must be "unknown", not crash.
    # The 503 path runs the existing _write_audit (AI_DRAFT) in a separate session;
    # assert its changed_fields model == "unknown" via a fresh query if feasible
    # (the audit commits in get_tenant_aware_session, not on `db`).
```

> **Implementer note:** The test now uses the correct model fields (`document_no` + `title`, both `nullable=False` on `CAPAEightD`) with **`title="测试标题足够长"` (≥6 chars)** — d2's precondition gate (`_FIELD_MIN_LENGTH["title"]=6`, checked at L358-364) runs **before** the LLM provider/503 check (L387); a 1-char `title` would raise 409 before reaching the migration path, making both tests assert the wrong branch. `format="paragraph"` validates against `ParagraphLLMOutput(content: str)` (simpler than the structured `D2StructuredLLMOutput`). `request_id` is a valid UUID4 string (parsed as UUID internally; "r1" would break the parse). The `_Req` fake satisfies `request.app.state.capa_draft_llm_timeout` (L248-252) — after migration `generate_draft` no longer reads `app.state.llm_provider`. To assert the 503 audit row's `model == "unknown"`: query `AuditLog` where `action == "AI_DRAFT"` and `record_id == capa.report_id` — note `_write_audit` commits in a separate `get_tenant_aware_session()`, so query a fresh session (or `db.execute` after the 503, since the audit session committed independently). Verify `request_id` UUID parsing: read `generate_draft` L255-265 for the `normalized_request_id` parse — if it wraps in try/except, any string works; if not, the UUID4 string is required.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_capa_draft_service.py -x -v`
Expected: FAIL — `generate_draft` still reads `app.state.llm_provider` (missing on `_Req` → AttributeError or `None` → wrong path) / calls `llm_provider.complete` not `complete_json`.

- [ ] **Step 3: Implement** — edit `backend/app/services/capa_draft_service.py`:

L239-240 (resolve pc + model_name):
```python
    from app.services.agent import provider_adapter
    from app.services.agent.provider_adapter import ProviderNotConfiguredError
    try:
        pc = await provider_adapter.build_client(db)
    except ProviderNotConfiguredError:
        pc = None
    llm_model_name = (pc.model if pc else None) or settings.LLM_MODEL or "unknown"
```
(Replace the old `llm_provider = getattr(request.app.state, "llm_provider", None)` + `llm_model_name = getattr(llm_provider, "model", None) or settings.LLM_MODEL or "unknown"`.)

L387-389 (503 guard):
```python
        # 10. LLM Provider
        if pc is None:
            audit_status_code = 503
            raise HTTPException(status_code=503, detail="AI 服务未配置")
```
(Replace `if llm_provider is None:`.)

L408 (the complete call inside `_generate_and_validate`):
```python
                llm_raw = await asyncio.wait_for(
                    provider_adapter.complete_json(pc, prompt, response_schema),
                    timeout=capa_draft_llm_timeout,
                )
```
(Replace `llm_provider.complete(prompt, response_schema)`.)

> **Do not touch** `_write_audit` (L261-288), the `AI_DRAFT` action, the independent `get_tenant_aware_session()` commit, or the L411-418 except branches. The `audit_success`/`audit_error`/`audit_status_code`/`model` (`llm_model_name`) flow into `changed_fields` unchanged.

- [ ] **Step 4: Edit `capa_capabilities`** — `backend/app/api/capa.py:112-126`:

```python
@router.get("/capabilities")
async def capa_capabilities(
    request: Request,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    """获取 AI 草拟功能是否可用及当前 LLM Provider"""
    level = await get_user_permission(scope.user, Module.CAPA, db)
    if level < PermissionLevel.VIEW:
        raise HTTPException(status_code=403, detail="需要 capa 模块的 VIEW 权限")
    from app.services.agent import provider_adapter
    from app.services.agent.provider_adapter import ProviderNotConfiguredError
    try:
        pc = await provider_adapter.build_client(db)
        ai_draft_enabled = True
        llm_provider_name = pc.model or settings.LLM_MODEL or None
    except ProviderNotConfiguredError:
        ai_draft_enabled = False
        llm_provider_name = None
    return {
        "ai_draft_enabled": ai_draft_enabled,
        "llm_provider": llm_provider_name,
    }
```

> **Do NOT touch** `draft_capabilities` at `capa.py:480` (it returns `available_steps`/`current_step`, doesn't read `app.state.llm_provider`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST tests/test_capa_draft_service.py tests/test_capa_draft_api.py -x -v`
Expected: PASS. Add a route test in `test_capa_draft_api.py`: `GET /api/capa/capabilities` returns `ai_draft_enabled=True` + `llm_provider="test-model"` when `build_client` succeeds, `ai_draft_enabled=False` when it raises `ProviderNotConfiguredError` (stub via monkeypatch on `provider_adapter.build_client`). Fix existing tests that asserted on `app.state.llm_provider`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/capa_draft_service.py backend/app/api/capa.py backend/tests/test_capa_draft_service.py backend/tests/test_capa_draft_api.py
git commit -m "feat(p1d): CAPA draft swaps to complete_json, keeps AI_DRAFT audit; capa_capabilities probes build_client"
```

---

## Task 5: Full regression + `make check`

**Files:** none (verification only)

- [ ] **Step 1: Grep-sweep for stale `app.state.llm_provider` readers**

Run:
```bash
cd backend && grep -rnE "app\.state\.llm_provider|request\.app\.state\.llm_provider|\.llm_provider" app/ --include="*.py"
```
Expected: only `ai_config_service.py` (excluded) and `main.py` (app-state setup, leave it — `LLMProvider` class not deleted). No remaining readers in capa.py / search.py / management_review.py / capa_draft_service.py / hybrid_recommendation_pipeline.py / llm_fusion_layer.py / search_service.py / management_review_report_service.py.

- [ ] **Step 2: Grep-sweep for stale `self.llm` / `LLMProvider` imports in migrated files**

Run:
```bash
cd backend && grep -rnE "self\.llm|from app\.services\.llm_provider import LLMProvider" app/services/llm_fusion_layer.py app/services/hybrid_recommendation_pipeline.py app/services/search_service.py app/services/management_review_report_service.py app/services/capa_draft_service.py
```
Expected: no matches (all migrated). `management_review_report_service.py` may retain a `LLMProvider` string in a type-alias import at L19 — remove it if now unused.

- [ ] **Step 3: Backend full suite**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only $PYTEST -x --tb=short`
Expected: PASS (all backend tests green). Investigate any failure before proceeding.

- [ ] **Step 4: `make check` (backend pytest + frontend tsc + frontend build)**

Run: `make check`
Expected: green. (Frontend is untouched by P1-D, but `make check` runs `tsc --noEmit` + `vite build` to confirm no breakage.)

- [ ] **Step 5: Manual spec checklist**

Verify each spec §8 回归 item against the green suite:
- (a) D4/D5 `LLMOutcome` 3-state + route commit + 2s timeout preserved (`test_llm_fusion_layer.py`, `test_hybrid_pipeline.py`, `test_capa_recommendation.py`).
- (b) RAG sentinel `record_id` stable + `correlation_id` sort/dedup + route commit (`test_search_service.py`).
- (c) mgmt helper outcome + 2-state audit + CRUD coexists + service L264 commit + route no-commit + `pc=None` model_name guard (`test_management_review_report_service.py`, `test_management_review_report_api.py`).
- (d) CAPA draft `AI_DRAFT` audit unchanged + `model` null-guard + no `write_audit_raw` + `capa_capabilities:112` probes / `draft_capabilities:480` untouched (`test_capa_draft_service.py`, `test_capa_draft_api.py`).
- (e) all audit status in `new_values={"status":...}`.
- (f) `LLMProvider` class still imported by `ai_config_service.py` (grep step 2 confirms not deleted).
- (g) per-consumer timeouts unchanged (D4/D5 2s / mgmt `REPORT_LLM_TIMEOUT` / RAG httpx 30s / CAPA draft `CAPA_DRAFT_LLM_TIMEOUT`).
- (h) RAG `/ask` with configured LLM but **no search hits** returns `llm_available=True` (pc resolved before the no-results early return; NOT `False`) — add/keep a test for this.
- (i) mgmt `generate_report` content + CRUD `REPORT_GENERATE` audit `changed_fields` use the **recomputed `llm_enriched`** (`section_attempted > len(section_failed_keys)`), not a stale/dropped bool.
- (j) CAPA draft tests reach the migration behavior (not fail on setup): `CAPAEightD` uses `document_no`+`title` with **`title` ≥ 6 chars** (d2 precondition gate `_FIELD_MIN_LENGTH["title"]=6` runs before the provider/503 check — short titles 409 before migration path); `DraftRequest` uses `format="paragraph"` + valid UUID4 `request_id`; `_ok_complete` returns `{"content": ...}` (ParagraphLLMOutput).

- [ ] **Step 6: Final commit (docs sync)**

Update `PROGRESS.md` §四 "当前在做" — mark P1-D landed; update `docs/ROADMAP.md` if it references P1-D. (Per CLAUDE.md §5: code under `backend/app/` changed → check `docs/` sync; add `docs-not-needed` PR label with justification only if truly no doc change. Here PROGRESS.md does need a tick.)

```bash
git add PROGRESS.md docs/ROADMAP.md  # if changed
git commit -m "docs(p1d): mark P1-D remaining-LLM-migration landed"
```

---

## Self-Review Notes (for the implementer, run before declaring done)

- **Spec coverage:** Every spec §3.1–§3.4 change point maps to a task step (1a/1b/1c, 2, 3, 4). Spec §6 exclusions (no `LLMProvider` deletion, no `ai_config` migration, no schema change, no timeout unification) are enforced by Task 5 grep sweeps + the explicit "do not touch" notes.
- **Type consistency:** `LLMOutcome` fields (`candidates/attempted/succeeded/failed`) match across `llm_fusion_layer.py` (defines) → `hybrid_recommendation_pipeline.py` (consumes) → tests. Helper return tuples `(sections, section_attempted, section_failed_keys)` / `(summary, recs, summary_failed)` match across `management_review_report_service.py` defines → `generate_report` consumes → tests. `recommend(context, *, user, report_id, factory_id, tenant_schema)` signature matches across pipeline define → capa.py call → route test.
- **No placeholders:** Every code step shows the actual code; every test step shows actual test code. Where a helper says "... unchanged ...", the note explicitly says which lines stay byte-for-byte and which line changes — no "implement later".