# FMEA Lifecycle Contract Backfill Implementation Plan

> **⚠️ STATUS (2026-07-25): OUT OF SCOPE for the US-E2E-02 acceptance effort.**
> This plan was written under a mistaken goal — it modifies **product code** to close
> the spec's FAILED gaps. The actual goal of US-E2E-02 is to **verify** the product
> end-to-end via `verify-fmea-lifecycle-*` skills and report the gaps as FAIL/MISSING,
> NOT to pre-fix them. This document is retained only as a reference for a **future**
> "补齐实现" effort, after the verify skills have run and reported. Do not execute it
> as part of the acceptance walk. The active plan is
> `docs/superpowers/plans/2026-07-25-fmea-lifecycle-verify-skills.md`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the backend contract gaps that `docs/user-stories/US-E2E-02-fmea-lifecycle/` deliberately marks FAILED, so the 19 sub-story acceptance contracts (and their derived verify skills) can pass.

**Architecture:** This epic's spec is an E2E acceptance contract over mostly-existing wizard/editor/approval flows. The wizard steps (02.1–02.14), editor CRUD (02.15), and collaborative editing (02.17) already behave per spec and are exercised by verify skills (scaffolded in the final task) — they need **no re-implementation**. The real work is a set of **backend contract backfills** the spec flags as gaps: AI recommendation must query 3 retrievers with observability, AI adoption must be audited, RecommendedAction needs a canonical 4-state status, FailureCause/FailureMode need risk-handling fields, CP sync must become a durable outbox (not a direct two-phase call), and the approval endpoint needs permission/reason/editable-state/wizard gates. Each gap is one TDD task.

**Tech Stack:** Python 3.11, FastAPI 0.115 (async), SQLAlchemy 2.0 (async) + asyncpg, Pydantic v2, Alembic (hand-written), pytest + pytest-asyncio, pgvector.

## Global Constraints

- **Branch:** `fix/fmea-fixes`. Do all work here.
- **Backend test command:** `cd backend && SECRET_KEY=test-secret-key pytest tests/ -x --tb=short` (use the project venv: `backend/.venv` or `backend/.venv312`).
- **Spec of record:** `docs/user-stories/US-E2E-02-fmea-lifecycle/` (README v3 + 19 sub-stories). Field names, enum values, edge types, and audit actions below are copied verbatim from it — do not paraphrase.
- **RecommendedAction canonical status enum:** `{open, in_progress, completed, not_executed}`. Legacy mapping: `undecided→open, planned→in_progress, done→completed, notExecuted→not_executed, closed→completed`.
- **AI required retrievers (must appear in `source_executions`):** `graph`, `semantic_search`, `lessons_learned`. `status ∈ {success, empty, unavailable, error}`. `rule` is NOT a required retriever. `context_execution.current_product_structure ∈ {assembled, unavailable}` and `generation_execution.llm ∈ {success, unavailable, error}` are separate top-level fields, not in `source_executions`.
- **AuditLog `action` enum (separate from Outbox `event_type`):** `CREATE / UPDATE / DELETE / TRANSITION / FORCE_SAVE_OVERRIDE / ADOPT_RECOMMENDATION`.
- **CP sync = Durable outbox** targeting a NEW `cp_sync_outbox` table + NEW worker. **Never reuse `GraphSyncOutbox`/`graph_sync_worker`** (Neo4j-oriented). CP audit `changed_fields` records only `sync_pending: false→true` + `trigger_fmea_version_id` (context) — never `source_fmea_version_id`.
- **Idempotency keys:** CP outbox event key = `(fmea_id, fmea_version_id, event_type='cp.sync_pending_set')`; worker processing key = `(outbox_id, cp_id)`. Already-`sync_pending=true` CPs are not re-audited.
- **Risk-handling fields** live on `FailureCause` (row model = FM×FC) with fallback to `FailureMode` for cause-less placeholder rows: `control_sufficiency_reason`, `risk_acceptance_reason`, `management_review_evidence`.
- **DB is JSONB graph**: `FMEADocument.graph_data = {nodes: [...], edges: [...], wizardScope: {...}}`. New node fields are new optional keys on `GraphNodeSchema` — no DB column migration needed for node fields, only for the new outbox table.
- Services raise `ValueError`; the API layer converts to `HTTPException`. Match this pattern.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/schemas/fmea.py` | Add `RecommendationAdoption`, `FMEAUpdate.adoptions`, `TransitionRequest.reason`, node risk fields, `RecommendedActionStatus` literal |
| `backend/app/schemas/recommendation.py` | Add `SourceExecution`, `ContextExecution`, `GenerationExecution`; extend `RecommendResponse`; widen `SuggestionItem.source` |
| `backend/app/services/recommendation_service.py` | Wire 3 retrievers + observability into `recommend()` |
| `backend/app/services/retriever_executions.py` | NEW: run graph/semantic/lessons retrievers, capture `SourceExecution` |
| `backend/app/services/adoption_audit.py` | NEW: dedupe + write `ADOPT_RECOMMENDATION` audit |
| `backend/app/services/fmea_service.py` | `update_fmea` adoptions param; `transition_fmea` reason/wizard/CP-outbox; remove direct CP call |
| `backend/app/services/control_plan_service.py` | `apply_cp_sync_pending(outbox)` idempotent worker-side applier |
| `backend/app/models/cp_sync_outbox.py` | NEW: `CPSyncOutbox` model |
| `backend/app/services/cp_sync_worker.py` | NEW: poll/lock/apply/retry worker |
| `backend/alembic/versions/20260725_add_cp_sync_outbox.py` | NEW: `cp_sync_outbox` table migration |
| `backend/app/api/fmea.py` | approval permission matrix, reason 422, wizard_completed 422, editable-state 409 |
| `.claude/skills/verify-fmea-lifecycle*` | 1 epic skill + 19 sub-story verify skills (scaffold) |

Interface notes for implementers (exact current signatures):
- `RecommendationService.recommend(fmea_id, request: RecommendRequest, user, request_scope) -> RecommendResponse` at `recommendation_service.py:564`.
- `LessonsLearnedService(db, embedding).recommend(doc_id, doc_type, problem_description, user, skip_fmea_sources=False) -> LessonsLearnedResponse` at `lessons_learned/service.py:36`.
- `LessonsSemanticSource(db, embedding).name == "semantic_search"`, `.retrieve(context) -> list[RecommendationCandidate]` at `lessons_learned/sources/semantic.py:9`.
- `update_fmea(db, fmea, title, graph_data, user_id, product_line_code=None, lock_version=None, confirmed_latest_lock_version=None)` at `fmea_service.py:190`.
- `transition_fmea(db, fmea, target_status, user_id)` at `fmea_service.py:330`; commits at `:378`; direct CP call at `:381-383`.
- `mark_cp_sync_pending_on_fmea_approve(db, fmea_id, fmea_version_id)` at `control_plan_service.py:649` (currently commits at `:665` — will be replaced by the outbox path).
- `_create_fmea_version_no_commit(db, fmea, change_type, change_summary, user_id) -> FMEAVersion` (sets `.version_id`) at `version_service.py:86`.
- `get_user_permission(user, Module.FMEA, db) -> PermissionLevel`; `PermissionLevel.{VIEW,EDIT,APPROVE}`; `Module.FMEA` — used at `api/fmea.py:115,193`.

---

---

## Task 1: Schema extensions (adoptions, transition reason, node risk/status fields)

**Files:**
- Modify: `backend/app/schemas/fmea.py`
- Test: `backend/tests/test_fmea_schema_extensions.py`

**Interfaces:**
- Consumes: existing `GraphNodeSchema`, `FMEAUpdate`, `TransitionRequest`.
- Produces:
  - `class RecommendationAdoption(BaseModel)` with fields `field_id: str`, `recommendation_id: str`, `source: str`, `stage_index: int`, `adopted_text: str`.
  - `FMEAUpdate.adoptions: list[RecommendationAdoption] | None = None`.
  - `TransitionRequest.reason: str | None = None`.
  - `GraphNodeSchema` new optional fields: `control_sufficiency_reason: str | None`, `risk_acceptance_reason: str | None`, `management_review_evidence: str | None`.
  - `RecommendedActionStatus = Literal["open", "in_progress", "completed", "not_executed"]`.
  - `GraphNodeSchema.recommended_action_status: RecommendedActionStatus | None = None` (canonical field; legacy `status: str` retained for back-compat).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_fmea_schema_extensions.py
from app.schemas.fmea import (
    FMEAUpdate, GraphNodeSchema, RecommendationAdoption, TransitionRequest,
)


def test_recommendation_adoption_roundtrip():
    a = RecommendationAdoption(
        field_id="fm_node_123", recommendation_id="rec_abc456",
        source="graph", stage_index=2, adopted_text="焊接电流不足",
    )
    assert a.recommendation_id == "rec_abc456"
    assert a.stage_index == 2


def test_fmea_update_has_adoptions_field():
    u = FMEAUpdate(adoptions=[{
        "field_id": "fm1", "recommendation_id": "r1",
        "source": "llm", "stage_index": 0, "adopted_text": "x",
    }])
    assert u.adoptions is not None and u.adoptions[0].recommendation_id == "r1"


def test_transition_request_accepts_reason():
    t = TransitionRequest(target_status="rework", reason="数据不完整")
    assert t.reason == "数据不完整"
    t2 = TransitionRequest(target_status="approved")
    assert t2.reason is None


def test_graph_node_risk_fields_and_canonical_status():
    n = GraphNodeSchema(
        id="fc1", type="FailureCause", name="原因",
        control_sufficiency_reason="现有控制充分",
        risk_acceptance_reason=None,
        management_review_evidence="管理层已评审",
        recommended_action_status="not_executed",
    )
    assert n.control_sufficiency_reason == "现有控制充分"
    assert n.management_review_evidence == "管理层已评审"
    assert n.recommended_action_status == "not_executed"


def test_recommended_action_status_rejects_legacy_value():
    import pytest
    with pytest.raises(Exception):
        GraphNodeSchema(id="ra1", type="RecommendedAction", name="m",
                        recommended_action_status="undecided")  # legacy not allowed in canonical field
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_schema_extensions.py -v`
Expected: FAIL — `ImportError: cannot import name 'RecommendationAdoption'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas/fmea.py`, add `Literal` to the `typing` import and add:

```python
from typing import Literal  # merge into existing typing import

RecommendedActionStatus = Literal["open", "in_progress", "completed", "not_executed"]


class RecommendationAdoption(BaseModel):
    field_id: str
    recommendation_id: str
    source: str
    stage_index: int
    adopted_text: str
```

Add to `GraphNodeSchema` (after `revised_ap`):

```python
    # Step 6 风险处置理由（挂 FailureCause；placeholder 行回退到 FailureMode）
    control_sufficiency_reason: str | None = None
    risk_acceptance_reason: str | None = None
    management_review_evidence: str | None = None
    # RecommendedAction canonical 状态（与 legacy `status` 并存，迁移期）
    recommended_action_status: RecommendedActionStatus | None = None
```

Add to `FMEAUpdate`:

```python
    adoptions: list[RecommendationAdoption] | None = None
```

Add to `TransitionRequest`:

```python
    reason: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_schema_extensions.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/fmea.py backend/tests/test_fmea_schema_extensions.py
git commit -m "feat(fmea): schema extensions — adoptions, transition reason, node risk fields, canonical action status"
```

---

## Task 2: Recommendation observability schemas

**Files:**
- Modify: `backend/app/schemas/recommendation.py`
- Test: `backend/tests/test_recommendation_observability_schema.py`

**Interfaces:**
- Consumes: existing `SuggestionItem`, `RecommendResponse`.
- Produces:
  - `class SourceExecution(BaseModel)`: `source: str`, `status: Literal["success","empty","unavailable","error"]`, `hit_count: int = 0`, `latency_ms: int = 0`.
  - `class ContextExecution(BaseModel)`: `current_product_structure: Literal["assembled","unavailable"] = "assembled"`.
  - `class GenerationExecution(BaseModel)`: `llm: Literal["success","unavailable","error"] = "unavailable"`.
  - `RecommendResponse` new fields: `source_executions: list[SourceExecution] = []`, `context_execution: ContextExecution = ContextExecution()`, `generation_execution: GenerationExecution = GenerationExecution()`.
  - `SuggestionItem.source` widened to `Literal["rule","graph","semantic_search","lessons_learned","llm"]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_recommendation_observability_schema.py
from app.schemas.recommendation import (
    ContextExecution, GenerationExecution, RecommendResponse,
    SourceExecution, SuggestionItem,
)


def test_source_execution_status_enum():
    se = SourceExecution(source="graph", status="success", hit_count=3, latency_ms=12)
    assert se.status == "success"
    for ok in ("success", "empty", "unavailable", "error"):
        SourceExecution(source="semantic_search", status=ok)
    import pytest
    with pytest.raises(Exception):
        SourceExecution(source="graph", status="bogus")


def test_suggestion_item_source_widened():
    for s in ("rule", "graph", "semantic_search", "lessons_learned", "llm"):
        item = SuggestionItem(name="x", confidence=0.5, source=s)
        assert item.source == s


def test_recommend_response_has_observability_fields():
    r = RecommendResponse(
        suggestions=[], source="hybrid",
        source_executions=[SourceExecution(source="graph", status="empty", hit_count=0)],
        context_execution=ContextExecution(current_product_structure="assembled"),
        generation_execution=GenerationExecution(llm="success"),
    )
    assert r.source_executions[0].source == "graph"
    assert r.context_execution.current_product_structure == "assembled"
    assert r.generation_execution.llm == "success"
    # defaults present when omitted
    r2 = RecommendResponse(suggestions=[], source="rule")
    assert r2.source_executions == []
    assert r2.generation_execution.llm == "unavailable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommendation_observability_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'SourceExecution'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas/recommendation.py`, change the `SuggestionItem.source` line to:

```python
    source: Literal["rule", "graph", "semantic_search", "lessons_learned", "llm"] = "rule"
```

Add these classes before `RecommendResponse`:

```python
class SourceExecution(BaseModel):
    source: str
    status: Literal["success", "empty", "unavailable", "error"]
    hit_count: int = 0
    latency_ms: int = 0


class ContextExecution(BaseModel):
    current_product_structure: Literal["assembled", "unavailable"] = "assembled"


class GenerationExecution(BaseModel):
    llm: Literal["success", "unavailable", "error"] = "unavailable"
```

Add to `RecommendResponse`:

```python
    source_executions: list[SourceExecution] = Field(default_factory=list)
    context_execution: ContextExecution = Field(default_factory=ContextExecution)
    generation_execution: GenerationExecution = Field(default_factory=GenerationExecution)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommendation_observability_schema.py -v`
Expected: 3 PASS. Then run the full recommendation schema/service tests to ensure the widened `source` literal didn't break existing tests:
Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -k "recommend" --tb=short`
Expected: no new failures (existing `source` values rule/graph/llm still valid).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/recommendation.py backend/tests/test_recommendation_observability_schema.py
git commit -m "feat(recommend): observability schemas — SourceExecution/ContextExecution/GenerationExecution, widen SuggestionItem.source"
```

---

## Task 3: Retriever execution collector (semantic_search + lessons_learned)

**Files:**
- Create: `backend/app/services/retriever_executions.py`
- Test: `backend/tests/test_retriever_executions.py`

**Interfaces:**
- Consumes: `LessonsLearnedService(db, embedding)` (`lessons_learned/service.py:24`), `LessonsSemanticSource(db, embedding)` (`lessons_learned/sources/semantic.py:9`, `.name == "semantic_search"`, `.retrieve(context)`), `LessonsLearnedContext` (`lessons_learned/context.py`), `SourceExecution` (Task 2).
- Produces:
  - `async def run_retrievers(db, embedding, *, query_text: str, user_product_lines: list[str] | None) -> tuple[list[SourceExecution], list[SuggestionItem]]`
    - Runs `semantic_search` and `lessons_learned` retrievers with per-retriever timing + status classification.
    - Returns the 2 `SourceExecution` rows (graph is added by the caller in Task 4) and the semantic/lessons candidates mapped to `SuggestionItem` (with `source` set to the retriever name).
    - Status rules per retriever: `embedding is None` → `unavailable`; exception during retrieve → `error`; zero candidates → `empty`; ≥1 candidate → `success`.
    - Never raises: all exceptions are caught and converted to a `SourceExecution(status="error")` + empty candidate list.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_retriever_executions.py
import pytest
from app.services.retriever_executions import run_retrievers


class _FakeEmbedding:
    async def embed(self, texts):
        return [[0.01] * 1536 for _ in texts]


@pytest.mark.asyncio
async def test_unavailable_when_no_embedding(db_session):
    execs, items = await run_retrievers(
        db_session, None, query_text="焊接", user_product_lines=None
    )
    by_src = {e.source: e for e in execs}
    assert by_src["semantic_search"].status == "unavailable"
    assert by_src["lessons_learned"].status == "unavailable"
    assert items == []


@pytest.mark.asyncio
async def test_status_is_empty_or_success_never_raises(db_session):
    # With an embedding present but (likely) no matching rows in the test DB,
    # each retriever must report a valid status and not raise.
    execs, items = await run_retrievers(
        db_session, _FakeEmbedding(), query_text="不存在的失效模式xyz", user_product_lines=None
    )
    by_src = {e.source: e for e in execs}
    for name in ("semantic_search", "lessons_learned"):
        assert by_src[name].status in ("success", "empty")
        assert by_src[name].hit_count >= 0
        assert by_src[name].latency_ms >= 0
    # every returned suggestion carries a widened source
    for it in items:
        assert it.source in ("semantic_search", "lessons_learned")
```

The `db_session` fixture already exists in `backend/tests/conftest.py`; if the name differs, reuse the existing async-session fixture used by neighboring service tests (e.g. `tests/test_recommendation_service.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_retriever_executions.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.retriever_executions`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/retriever_executions.py
"""Run external knowledge retrievers for FMEA recommendation with observability.

Each retriever is classified into a SourceExecution status so E2E can
distinguish "called but zero hits" (empty) from "not called / no creds"
(unavailable) from "raised" (error). Never raises.
"""
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.recommendation import SourceExecution, SuggestionItem


async def _run_one(name, coro_factory) -> tuple[SourceExecution, list]:
    start = time.monotonic()
    try:
        candidates = await coro_factory()
    except Exception:
        return SourceExecution(
            source=name, status="error", hit_count=0,
            latency_ms=int((time.monotonic() - start) * 1000),
        ), []
    latency = int((time.monotonic() - start) * 1000)
    status = "success" if candidates else "empty"
    return SourceExecution(
        source=name, status=status, hit_count=len(candidates), latency_ms=latency
    ), candidates


async def run_retrievers(
    db: AsyncSession,
    embedding: object | None,
    *,
    query_text: str,
    user_product_lines: list[str] | None,
) -> tuple[list[SourceExecution], list[SuggestionItem]]:
    from app.services.lessons_learned.context import LessonsLearnedContext
    from app.services.lessons_learned.service import LessonsLearnedService
    from app.services.lessons_learned.sources.semantic import LessonsSemanticSource

    executions: list[SourceExecution] = []
    suggestions: list[SuggestionItem] = []

    if embedding is None:
        executions.append(SourceExecution(source="semantic_search", status="unavailable"))
        executions.append(SourceExecution(source="lessons_learned", status="unavailable"))
        return executions, suggestions

    context = LessonsLearnedContext(
        query_text=query_text, user_product_lines=user_product_lines
    )

    sem_src = LessonsSemanticSource(db, embedding)
    sem_exec, sem_cands = await _run_one(
        "semantic_search", lambda: sem_src.retrieve(context)
    )
    executions.append(sem_exec)
    suggestions.extend(
        SuggestionItem(
            name=getattr(c, "name", "") or getattr(c, "text", ""),
            confidence=float(getattr(c, "score", 0.5) or 0.5),
            source="semantic_search",
            source_document_no=getattr(c, "source_document_no", None),
            explanation=getattr(c, "explanation", "") or "",
        )
        for c in sem_cands
    )

    lessons_svc = LessonsLearnedService(db, embedding)

    async def _lessons():
        resp = await lessons_svc.recommend(
            doc_id=None, doc_type="fmea",
            problem_description=query_text, user=None,
        )
        return getattr(resp, "cards", []) or getattr(resp, "lessons", []) or []

    les_exec, les_cards = await _run_one("lessons_learned", _lessons)
    executions.append(les_exec)
    suggestions.extend(
        SuggestionItem(
            name=getattr(c, "title", "") or getattr(c, "name", ""),
            confidence=float(getattr(c, "score", 0.5) or 0.5),
            source="lessons_learned",
            source_document_no=getattr(c, "source_document_no", None),
            explanation=getattr(c, "summary", "") or getattr(c, "explanation", "") or "",
        )
        for c in les_cards
    )

    return executions, suggestions
```

> **Note for implementer:** `LessonsLearnedContext` and `LessonsLearnedService.recommend` signatures differ from the sketch above — read `backend/app/services/lessons_learned/context.py` and `service.py:36` and construct the context with its real fields, and call `recommend` with its real required params (it requires a `doc_id`/`user`; if they are non-optional, adapt by querying lessons sources directly via `LessonsCAPASource`/`HistoricalFMEASource` instead of the orchestrator). The contract that MUST hold: two `SourceExecution` rows named exactly `semantic_search` and `lessons_learned`, correct status classification, and `SuggestionItem.source` set to the retriever name. Keep `run_retrievers`'s own signature stable — Task 4 depends on it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_retriever_executions.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/retriever_executions.py backend/tests/test_retriever_executions.py
git commit -m "feat(recommend): retriever execution collector for semantic_search + lessons_learned"
```

---

## Task 4: Wire 3 retrievers + observability into RecommendationService.recommend

**Files:**
- Modify: `backend/app/services/recommendation_service.py:564-670`
- Test: `backend/tests/test_recommend_observability.py`

**Interfaces:**
- Consumes: `run_retrievers` (Task 3), `SourceExecution/ContextExecution/GenerationExecution` (Task 2), existing `_query_graph_similarity`, `_assemble_context`, `self.llm`.
- Produces: `recommend()` returns `RecommendResponse` with `source_executions` containing exactly the 3 required retrievers (`graph`, `semantic_search`, `lessons_learned`), plus `context_execution` and `generation_execution`. The `RecommendationService.__init__` gains an `embedding: object | None = None` kwarg (default None → semantic/lessons report `unavailable`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_recommend_observability.py
import pytest
from app.schemas.recommendation import RecommendRequest


@pytest.mark.asyncio
async def test_recommend_reports_three_required_retrievers(
    client, auth_headers, seeded_fmea
):
    resp = await client.post(
        f"/api/fmea/{seeded_fmea}/recommend",
        json={"trigger_type": "failure_mode", "context": {"function_description": "焊接"}, "include_graph": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    sources = {e["source"] for e in body["source_executions"]}
    assert {"graph", "semantic_search", "lessons_learned"} <= sources
    for e in body["source_executions"]:
        assert e["status"] in ("success", "empty", "unavailable", "error")
    assert body["context_execution"]["current_product_structure"] in ("assembled", "unavailable")
    assert body["generation_execution"]["llm"] in ("success", "unavailable", "error")
```

Reuse the API/fixture names from the existing recommend endpoint test (`backend/tests/test_recommend*.py` or `test_fmea_api*.py`); adapt `client`/`auth_headers`/`seeded_fmea` to the real fixtures.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommend_observability.py -v`
Expected: FAIL — response has no `source_executions` (KeyError / assertion on the set).

- [ ] **Step 3: Write minimal implementation**

In `RecommendationService.__init__` add `embedding: object | None = None` and store `self.embedding = embedding`.

In `recommend()`, after the graph block (`:606-617`), build the graph execution row and call the retrievers:

```python
        from app.schemas.recommendation import (
            ContextExecution, GenerationExecution, SourceExecution,
        )
        from app.services.retriever_executions import run_retrievers

        source_executions: list[SourceExecution] = []
        if include_graph:
            source_executions.append(SourceExecution(
                source="graph",
                status="success" if graph_suggestions else "empty",
                hit_count=len(graph_suggestions),
            ))
        else:
            source_executions.append(SourceExecution(source="graph", status="unavailable"))

        query_text = (
            request.context.get("function_description")
            or request.context.get("input_text")
            or ""
        )
        retriever_execs, retriever_items = await run_retrievers(
            self.db, self.embedding,
            query_text=query_text, user_product_lines=product_line_codes,
        )
        source_executions.extend(retriever_execs)
        all_suggestions = self._merge_and_deduplicate(all_suggestions, retriever_items)
```

Move the `all_suggestions = self._merge_and_deduplicate(rule_suggestions, graph_suggestions)` at `:620` so `all_suggestions` exists before the retriever merge (initialize it right after the graph block, before appending retriever items).

Track `generation_execution` and `context_execution` around the LLM block (`:630-657`):

```python
        generation_execution = GenerationExecution(
            llm="unavailable" if self.llm is None else "success"
        )
        context_execution = ContextExecution(current_product_structure="assembled")
        # inside the `if need_llm:` try: after `llm_context = await self._assemble_context(...)`
        #     context_execution.current_product_structure = "assembled" if llm_context else "unavailable"
        # inside the LLM `except` block:
        #     generation_execution.llm = "error"
```

Populate the response (`:659-666`):

```python
        response = RecommendResponse(
            suggestions=all_suggestions[:10],
            source=source,
            cached=False,
            llm_available=self.llm is not None,
            graph_match_count=len(graph_suggestions),
            effective_scope=effective_scope,
            source_executions=source_executions,
            context_execution=context_execution,
            generation_execution=generation_execution,
        )
```

For cache hits (`:590-595`): cached responses were serialized before these fields existed. When returning a cached response, backfill empty observability so the contract holds:

```python
                cached_response.source_executions = cached_response.source_executions or []
                return cached_response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommend_observability.py -v`
Expected: PASS. Then regression:
Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -k "recommend" --tb=short`
Expected: no new failures.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/tests/test_recommend_observability.py
git commit -m "feat(recommend): query graph+semantic+lessons retrievers with source_executions/context/generation observability"
```

---

## Task 5: Adoption audit service (ADOPT_RECOMMENDATION)

**Files:**
- Create: `backend/app/services/adoption_audit.py`
- Test: `backend/tests/test_adoption_audit.py`

**Interfaces:**
- Consumes: `RecommendationAdoption` (Task 1), `AuditLog` model (`app/models/audit.py`).
- Produces:
  - `async def write_adoption_audits(db, fmea_id, adoptions: list[RecommendationAdoption], user_id) -> int`
    - Dedupes by `recommendation_id` (idempotent — repeated saves of the same `recommendation_id` produce no duplicate audit).
    - Idempotency is enforced by checking for an existing `AuditLog` with `action="ADOPT_RECOMMENDATION"` whose `changed_fields->>'recommendation_id'` matches, before inserting.
    - Writes one `AuditLog` per new adoption: `table_name="fmea_documents"`, `record_id=fmea_id`, `action="ADOPT_RECOMMENDATION"`, `changed_fields={field_id, recommendation_id, source, stage_index, adopted_text}`, `operated_by=user_id`.
    - Does NOT commit (caller commits); returns count of audits written.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_adoption_audit.py
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.schemas.fmea import RecommendationAdoption
from app.services.adoption_audit import write_adoption_audits


def _a(rid, fid="fm1"):
    return RecommendationAdoption(
        field_id=fid, recommendation_id=rid, source="graph",
        stage_index=0, adopted_text="焊接电流不足",
    )


@pytest.mark.asyncio
async def test_writes_one_audit_per_adoption(db_session, seeded_fmea_id, user_id):
    n = await write_adoption_audits(db_session, seeded_fmea_id, [_a("r1"), _a("r2")], user_id)
    await db_session.commit()
    assert n == 2
    rows = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ADOPT_RECOMMENDATION")
    )).scalars().all()
    assert len(rows) == 2
    assert rows[0].changed_fields["recommendation_id"] in ("r1", "r2")


@pytest.mark.asyncio
async def test_idempotent_by_recommendation_id(db_session, seeded_fmea_id, user_id):
    await write_adoption_audits(db_session, seeded_fmea_id, [_a("r1")], user_id)
    await db_session.commit()
    # second save of the same recommendation_id -> no new audit
    n2 = await write_adoption_audits(db_session, seeded_fmea_id, [_a("r1")], user_id)
    await db_session.commit()
    assert n2 == 0
    rows = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ADOPT_RECOMMENDATION")
    )).scalars().all()
    assert len(rows) == 1
```

Use the existing async-session fixture and a seeded FMEA id fixture from `conftest.py` (adapt names to the real fixtures).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_adoption_audit.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.adoption_audit`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/adoption_audit.py
"""Write ADOPT_RECOMMENDATION audit logs, idempotent by recommendation_id."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.schemas.fmea import RecommendationAdoption


async def write_adoption_audits(
    db: AsyncSession,
    fmea_id: uuid.UUID,
    adoptions: list[RecommendationAdoption],
    user_id: uuid.UUID,
) -> int:
    if not adoptions:
        return 0
    existing = (await db.execute(
        select(AuditLog.changed_fields["recommendation_id"].astext).where(
            AuditLog.table_name == "fmea_documents",
            AuditLog.action == "ADOPT_RECOMMENDATION",
        )
    )).scalars().all()
    seen = set(existing)
    written = 0
    for a in adoptions:
        if a.recommendation_id in seen:
            continue
        seen.add(a.recommendation_id)
        db.add(AuditLog(
            table_name="fmea_documents",
            record_id=fmea_id,
            action="ADOPT_RECOMMENDATION",
            changed_fields={
                "field_id": a.field_id,
                "recommendation_id": a.recommendation_id,
                "source": a.source,
                "stage_index": a.stage_index,
                "adopted_text": a.adopted_text,
            },
            operated_by=user_id,
        ))
        written += 1
    return written
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_adoption_audit.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/adoption_audit.py backend/tests/test_adoption_audit.py
git commit -m "feat(fmea): adoption audit service (ADOPT_RECOMMENDATION, idempotent by recommendation_id)"
```

---

## Task 6: RecommendedAction canonical status normalization + wire adoptions into update_fmea

**Files:**
- Create: `backend/app/services/recommended_action_status.py`
- Modify: `backend/app/services/fmea_service.py:190-272` (`update_fmea` signature + adoption hook)
- Modify: `backend/app/api/fmea.py:127-133` (pass `req.adoptions` through to the service)
- Test: `backend/tests/test_recommended_action_status.py`

**Interfaces:**
- Consumes: `RecommendedActionStatus` (Task 1), `write_adoption_audits` (Task 5), `RecommendationAdoption` (Task 1).
- Produces:
  - `def normalize_action_status(value: str | None) -> RecommendedActionStatus | None` — deterministic legacy mapping `undecided→open, planned→in_progress, done→completed, notExecuted→not_executed, closed→completed`; already-canonical values pass through; unknown/empty → `None`.
  - `update_fmea(..., adoptions: list[RecommendationAdoption] | None = None)` — new trailing kwarg; when non-empty, calls `write_adoption_audits(db, fmea.fmea_id, adoptions, user_id)` inside the same transaction (before the existing `await db.commit()` at `:270`).
  - The `PUT /api/fmea/{fmea_id}` route forwards `req.adoptions` so the adoption-audit path is reachable end-to-end.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_recommended_action_status.py
import pytest
from app.services.recommended_action_status import normalize_action_status


@pytest.mark.parametrize("legacy,expected", [
    ("undecided", "open"),
    ("planned", "in_progress"),
    ("done", "completed"),
    ("notExecuted", "not_executed"),
    ("closed", "completed"),
    ("open", "open"),
    ("in_progress", "in_progress"),
    ("completed", "completed"),
    ("not_executed", "not_executed"),
    (None, None),
    ("", None),
    ("bogus", None),
])
def test_normalize_action_status(legacy, expected):
    assert normalize_action_status(legacy) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommended_action_status.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/recommended_action_status.py
"""Deterministic mapping of legacy RecommendedAction status to canonical 4-state."""
_LEGACY_MAP = {
    "undecided": "open",
    "planned": "in_progress",
    "done": "completed",
    "notExecuted": "not_executed",
    "closed": "completed",
}
_CANONICAL = {"open", "in_progress", "completed", "not_executed"}


def normalize_action_status(value: str | None) -> str | None:
    if not value:
        return None
    if value in _CANONICAL:
        return value
    return _LEGACY_MAP.get(value)
```

Then in `fmea_service.update_fmea`, add `adoptions: list | None = None` to the signature and, immediately before `await db.commit()` (`:270`), add:

```python
    if adoptions:
        from app.services.adoption_audit import write_adoption_audits
        await write_adoption_audits(db, fmea.fmea_id, adoptions, user_id)
```

Then wire the API route. In `api/fmea.py` `update_fmea` (`:129-133`), pass `req.adoptions` through:

```python
        fmea = await fmea_service.update_fmea(
            db, fmea, req.title, graph_dict, scope.user.user_id, req.product_line_code,
            lock_version=req.lock_version,
            confirmed_latest_lock_version=req.confirmed_latest_lock_version,
            adoptions=req.adoptions,
        )
```

Add an end-to-end test to the existing test file confirming the route writes an `ADOPT_RECOMMENDATION` audit:

```python
@pytest.mark.asyncio
async def test_put_with_adoptions_writes_audit(client, engineer_headers, draft_fmea_id, db_session):
    from sqlalchemy import select
    from app.models.audit import AuditLog
    resp = await client.put(
        f"/api/fmea/{draft_fmea_id}",
        json={"adoptions": [{
            "field_id": "fm1", "recommendation_id": "rec_e2e_1",
            "source": "graph", "stage_index": 0, "adopted_text": "焊接电流不足",
        }]},
        headers=engineer_headers,
    )
    assert resp.status_code == 200
    rows = (await db_session.execute(select(AuditLog).where(
        AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert any(r.changed_fields.get("recommendation_id") == "rec_e2e_1" for r in rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommended_action_status.py -v`
Expected: 12 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommended_action_status.py backend/app/services/fmea_service.py backend/tests/test_recommended_action_status.py
git commit -m "feat(fmea): canonical action-status normalizer + adoptions hook in update_fmea"
```

---

## Task 7: CPSyncOutbox model + migration

**Files:**
- Create: `backend/app/models/cp_sync_outbox.py`
- Create: `backend/alembic/versions/20260725_add_cp_sync_outbox.py`
- Modify: `backend/app/models/__init__.py` (register model)
- Test: `backend/tests/test_cp_sync_outbox_model.py`

**Interfaces:**
- Consumes: `app.database.Base`; migration pattern from `alembic/versions/027_add_graph_sync_outbox.py`.
- Produces:
  - `class CPSyncOutbox(Base)`, `__tablename__ = "cp_sync_outbox"`, columns: `id` (UUID pk), `fmea_id` (UUID, not null), `fmea_version_id` (UUID, not null), `event_type` (String, default `"cp.sync_pending_set"`), `payload` (JSONB, default `{}`), `status` (String, default `"pending"` — pending/processing/completed/dead), `attempt_count` (Int, default 0), `max_attempts` (Int, default 5), `next_attempt_at` (DateTime tz, default now), `last_error` (Text, nullable), `locked_at` (DateTime tz, nullable), `created_at` (DateTime tz, default now), `processed_at` (DateTime tz, nullable).
  - Unique constraint `uq_cp_sync_outbox_event` on `(fmea_id, fmea_version_id, event_type)` — enforces one outbox event per approved version.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cp_sync_outbox_model.py
import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from app.models.cp_sync_outbox import CPSyncOutbox


@pytest.mark.asyncio
async def test_model_persists_and_unique_event_key(db_session):
    fmea_id, version_id = uuid.uuid4(), uuid.uuid4()
    db_session.add(CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=version_id,
                                event_type="cp.sync_pending_set", payload={}))
    await db_session.commit()
    # duplicate (fmea_id, fmea_version_id, event_type) violates unique key
    db_session.add(CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=version_id,
                                event_type="cp.sync_pending_set", payload={}))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    # a NEW version for the SAME fmea is allowed (re-approval after rework)
    db_session.add(CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=uuid.uuid4(),
                                event_type="cp.sync_pending_set", payload={}))
    await db_session.commit()
```

- [ ] **Step 2: Run migration then test to verify it fails before model exists**

Run: `cd backend && SECRET_KEY=test-secret-key alembic upgrade head`
Then: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_cp_sync_outbox_model.py -v`
Expected (first run, before Step 3): FAIL — `ModuleNotFoundError: app.models.cp_sync_outbox`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/models/cp_sync_outbox.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CPSyncOutbox(Base):
    __tablename__ = "cp_sync_outbox"
    __table_args__ = (
        UniqueConstraint("fmea_id", "fmea_version_id", "event_type",
                         name="uq_cp_sync_outbox_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fmea_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fmea_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, default="cp.sync_pending_set")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Migration `backend/alembic/versions/20260725_add_cp_sync_outbox.py` (set `down_revision` to the current head — run `alembic heads` to find it; do not guess):

```python
"""add cp_sync_outbox table for durable CP sync on FMEA approval

Revision ID: 20260725
Revises: <CURRENT_HEAD>
Create Date: 2026-07-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '20260725'
down_revision: Union[str, None] = '<CURRENT_HEAD>'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cp_sync_outbox',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('fmea_id', UUID(as_uuid=True), nullable=False),
        sa.Column('fmea_version_id', UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False, server_default='cp.sync_pending_set'),
        sa.Column('payload', JSONB, nullable=False, server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('fmea_id', 'fmea_version_id', 'event_type', name='uq_cp_sync_outbox_event'),
    )
    op.create_index(
        'idx_cp_sync_outbox_pending', 'cp_sync_outbox', ['next_attempt_at'],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index('idx_cp_sync_outbox_pending')
    op.drop_table('cp_sync_outbox')
```

Register in `backend/app/models/__init__.py` (add the import next to the other model imports):

```python
from app.models.cp_sync_outbox import CPSyncOutbox  # noqa: F401
```

- [ ] **Step 4: Run migration + test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key alembic upgrade head && SECRET_KEY=test-secret-key pytest tests/test_cp_sync_outbox_model.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/cp_sync_outbox.py backend/app/models/__init__.py backend/alembic/versions/20260725_add_cp_sync_outbox.py backend/tests/test_cp_sync_outbox_model.py
git commit -m "feat(fmea): CPSyncOutbox model + migration with (fmea_id,fmea_version_id,event_type) unique key"
```

---

## Task 8: CP sync applier + durable worker

**Files:**
- Modify: `backend/app/services/control_plan_service.py` (replace `mark_cp_sync_pending_on_fmea_approve` internals with an idempotent applier)
- Create: `backend/app/services/cp_sync_worker.py`
- Test: `backend/tests/test_cp_sync_worker.py`

**Interfaces:**
- Consumes: `CPSyncOutbox` (Task 7), `ControlPlan` (`fmea_ref_id`, `sync_pending`, `source_fmea_version_id` — `models/control_plan.py:19,22,41`), `AuditLog`.
- Produces:
  - `async def apply_cp_sync_pending(db, outbox: CPSyncOutbox, user_id) -> int` in `control_plan_service.py`. For each `ControlPlan` where `fmea_ref_id == outbox.fmea_id` AND `sync_pending == False`: set `sync_pending = True`, write one `AuditLog(table_name="control_plans", record_id=cp.control_plan_id, action="UPDATE", changed_fields={"sync_pending": "false->true", "trigger_fmea_version_id": str(outbox.fmea_version_id)}, operated_by=user_id)`. Returns count of CPs flipped. Already-pending CPs are skipped (no audit) → idempotent per `(outbox_id, cp_id)`. Does NOT commit (worker commits atomically with outbox status).
  - `async def process_cp_sync_outbox_batch(db, batch_size: int = 10) -> int` in `cp_sync_worker.py`: poll `pending` rows due (`next_attempt_at <= now`) with `FOR UPDATE SKIP LOCKED`, for each call `apply_cp_sync_pending`, set `status="completed"` + `processed_at=now`, commit once per row; on exception set `attempt_count += 1`, `next_attempt_at = now + backoff`, `last_error`, `status="dead"` if attempts exhausted, commit. Returns rows processed. A `__main__` loop polls with `POLL_INTERVAL = 5` (mirrors `graph_sync_worker.py`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cp_sync_worker.py
import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.control_plan import ControlPlan
from app.models.cp_sync_outbox import CPSyncOutbox
from app.services.control_plan_service import apply_cp_sync_pending
from app.services.cp_sync_worker import process_cp_sync_outbox_batch


@pytest.mark.asyncio
async def test_applier_flips_only_pending_and_audits_each(db_session, two_cps_for_fmea, user_id):
    fmea_id, version_id = two_cps_for_fmea  # fixture: 2 CPs linked, both sync_pending=False
    outbox = CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=version_id, payload={})
    n = await apply_cp_sync_pending(db_session, outbox, user_id)
    await db_session.commit()
    assert n == 2
    audits = (await db_session.execute(
        select(AuditLog).where(AuditLog.table_name == "control_plans",
                               AuditLog.action == "UPDATE")
    )).scalars().all()
    assert len(audits) == 2  # 2 + N rule: one per flipped CP
    for a in audits:
        assert a.changed_fields["sync_pending"] == "false->true"
        assert "source_fmea_version_id" not in a.changed_fields
        assert a.changed_fields["trigger_fmea_version_id"] == str(version_id)


@pytest.mark.asyncio
async def test_worker_idempotent_no_duplicate_audit(db_session, two_cps_for_fmea, user_id):
    fmea_id, version_id = two_cps_for_fmea
    db_session.add(CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=version_id, payload={}))
    await db_session.commit()
    await process_cp_sync_outbox_batch(db_session)
    await process_cp_sync_outbox_batch(db_session)  # second run: row already completed
    audits = (await db_session.execute(
        select(AuditLog).where(AuditLog.table_name == "control_plans",
                               AuditLog.action == "UPDATE")
    )).scalars().all()
    assert len(audits) == 2  # still exactly one per CP, no duplicates
```

Create a `two_cps_for_fmea` fixture in the test (or `conftest.py`) that builds one `FMEADocument` + two `ControlPlan` rows with `fmea_ref_id` set and `sync_pending=False`, matching the required NOT-NULL columns (`factory_id`, etc.) used by neighboring CP tests.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_cp_sync_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.cp_sync_worker` and `apply_cp_sync_pending` missing.

- [ ] **Step 3: Write minimal implementation**

In `control_plan_service.py` add (keep `mark_cp_sync_pending_on_fmea_approve` as a thin deprecated wrapper or remove if unreferenced after Task 9 — grep first):

```python
async def apply_cp_sync_pending(db: AsyncSession, outbox, user_id: uuid.UUID) -> int:
    """Idempotently mark linked CPs sync_pending + audit each flip.

    Only flips CPs currently sync_pending=False; already-pending CPs are
    skipped (no duplicate audit), giving idempotency per (outbox_id, cp_id).
    Does NOT commit — the worker commits atomically with the outbox status.
    """
    from app.models.audit import AuditLog
    result = await db.execute(
        select(ControlPlan).where(
            ControlPlan.fmea_ref_id == outbox.fmea_id,
            ControlPlan.sync_pending == False,  # noqa: E712
        )
    )
    cps = list(result.scalars().all())
    for cp in cps:
        cp.sync_pending = True
        db.add(AuditLog(
            table_name="control_plans",
            record_id=cp.control_plan_id,
            action="UPDATE",
            changed_fields={
                "sync_pending": "false->true",
                "trigger_fmea_version_id": str(outbox.fmea_version_id),
            },
            operated_by=user_id,
        ))
    return len(cps)
```

New `backend/app/services/cp_sync_worker.py`:

```python
"""CPSyncWorker: durable outbox consumer for FMEA-approval -> CP sync_pending.

Run: python -m app.services.cp_sync_worker
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.cp_sync_outbox import CPSyncOutbox
from app.services.control_plan_service import apply_cp_sync_pending

logger = logging.getLogger(__name__)
POLL_INTERVAL = 5
BATCH_SIZE = 10
_BACKOFF = {1: 10, 2: 30, 3: 90, 4: 270}
_SYSTEM_USER = None  # resolved from outbox payload / system user in Task 9


async def process_cp_sync_outbox_batch(db: AsyncSession, batch_size: int = BATCH_SIZE) -> int:
    now = datetime.now(UTC)
    rows = (await db.execute(
        select(CPSyncOutbox)
        .where(CPSyncOutbox.status == "pending", CPSyncOutbox.next_attempt_at <= now)
        .order_by(CPSyncOutbox.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )).scalars().all()
    processed = 0
    for row in rows:
        try:
            user_id = row.payload.get("user_id") or _SYSTEM_USER
            await apply_cp_sync_pending(db, row, user_id)
            row.status = "completed"
            row.processed_at = datetime.now(UTC)
            processed += 1
        except Exception as e:  # noqa: BLE001
            row.attempt_count += 1
            row.last_error = f"{type(e).__name__}: {e}"
            if row.attempt_count >= row.max_attempts:
                row.status = "dead"
            else:
                row.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=_BACKOFF.get(row.attempt_count, 270)
                )
        await db.commit()
    return processed


async def _loop() -> None:
    while True:
        async with async_session() as db:
            try:
                await process_cp_sync_outbox_batch(db)
            except Exception:  # noqa: BLE001
                logger.exception("cp_sync batch failed")
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(_loop())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_cp_sync_worker.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/control_plan_service.py backend/app/services/cp_sync_worker.py backend/tests/test_cp_sync_worker.py
git commit -m "feat(fmea): CP sync applier + durable outbox worker (idempotent, 2+N audits, sync_pending-only changed_fields)"
```

---

## Task 9: Produce CP outbox event on approval; remove direct CP call

**Files:**
- Modify: `backend/app/services/fmea_service.py:370-386` (`transition_fmea`)
- Test: `backend/tests/test_transition_cp_outbox.py`

**Interfaces:**
- Consumes: `CPSyncOutbox` (Task 7), `_create_fmea_version_no_commit` (returns `version` with `.version_id`).
- Produces: `transition_fmea` on `APPROVED` writes a `CPSyncOutbox(fmea_id, fmea_version_id=version.version_id, event_type="cp.sync_pending_set", payload={"user_id": str(user_id)})` inside the SAME transaction that commits at `:378`; the direct `mark_cp_sync_pending_on_fmea_approve` call at `:381-383` is removed. CP `sync_pending` is no longer set synchronously (worker does it).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_transition_cp_outbox.py
import pytest
from sqlalchemy import select
from app.models.cp_sync_outbox import CPSyncOutbox
from app.services import fmea_service


@pytest.mark.asyncio
async def test_approve_enqueues_cp_outbox_and_does_not_set_pending_sync(
    db_session, draft_pfmea_with_cp, user_id
):
    fmea, cp = draft_pfmea_with_cp  # fixture: PFMEA draft + 1 linked CP (sync_pending=False)
    await fmea_service.transition_fmea(db_session, fmea, "approved", user_id)
    rows = (await db_session.execute(
        select(CPSyncOutbox).where(CPSyncOutbox.fmea_id == fmea.fmea_id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == "cp.sync_pending_set"
    assert rows[0].fmea_version_id is not None
    # direct synchronous set is gone: worker has not run yet
    await db_session.refresh(cp)
    assert cp.sync_pending is False


@pytest.mark.asyncio
async def test_submit_does_not_enqueue_cp_outbox(db_session, draft_pfmea_with_cp, user_id):
    fmea, _ = draft_pfmea_with_cp
    await fmea_service.transition_fmea(db_session, fmea, "in_review", user_id)
    rows = (await db_session.execute(select(CPSyncOutbox))).scalars().all()
    assert rows == []
```

Create a `draft_pfmea_with_cp` fixture producing a DRAFT PFMEA with a linked `ControlPlan`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_transition_cp_outbox.py -v`
Expected: FAIL — no `CPSyncOutbox` row created (and CP still set synchronously today).

- [ ] **Step 3: Write minimal implementation**

In `transition_fmea`, after the `GraphSyncOutbox` add (`:371-376`) and before `await db.commit()` (`:378`), add:

```python
    if target == FMEAState.APPROVED and version is not None:
        from app.models.cp_sync_outbox import CPSyncOutbox
        db.add(CPSyncOutbox(
            fmea_id=fmea.fmea_id,
            fmea_version_id=version.version_id,
            event_type="cp.sync_pending_set",
            payload={"user_id": str(user_id)},
        ))
```

Then delete the direct call block (`:380-383`):

```python
    # Trigger CP sync when FMEA is approved
    if target == FMEAState.APPROVED and version:
        from app.services.control_plan_service import mark_cp_sync_pending_on_fmea_approve
        await mark_cp_sync_pending_on_fmea_approve(db, fmea.fmea_id, version.version_id)
```

Verify `mark_cp_sync_pending_on_fmea_approve` has no other callers (`grep -rn "mark_cp_sync_pending_on_fmea_approve" backend/`) and remove it if now unused.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_transition_cp_outbox.py -v`
Expected: 2 PASS. Then regression on transitions:
Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -k "transition or control_plan" --tb=short`
Expected: no new failures (update any test that asserted the old synchronous CP-set behavior).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/fmea_service.py backend/app/services/control_plan_service.py backend/tests/test_transition_cp_outbox.py
git commit -m "feat(fmea): enqueue CPSyncOutbox on approval (durable), drop direct synchronous CP set"
```

---

## Task 10: Approval permission matrix + reason/wizard/editable-state gates

**Files:**
- Modify: `backend/app/api/fmea.py:187-214` (`require_approve_permission`, `transition_fmea`) and `:108-133` (`update_fmea` editable-state guard)
- Test: `backend/tests/test_fmea_approval_gates.py`

**Interfaces:**
- Consumes: `TransitionRequest.reason` (Task 1), `get_user_permission`/`PermissionLevel`/`Module.FMEA`, `FMEAState` (`state_machines/fmea_state.py`).
- Produces (per spec "审批权限矩阵"):
  - `IN_REVIEW → APPROVED`, `IN_REVIEW → REWORK`, `APPROVED → REWORK` → require `APPROVE`.
  - `DRAFT/REWORK → IN_REVIEW` → require `EDIT` + backend-enforced `wizardScope.wizard_completed == true` else **422**.
  - `REWORK` target → require non-empty `reason` else **422**.
  - `PUT /{fmea_id}` on `IN_REVIEW/APPROVED/ARCHIVED` → **409/403** (not editable); only `DRAFT/REWORK` editable.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_fmea_approval_gates.py
import pytest


@pytest.mark.asyncio
async def test_rework_requires_approve_permission(client, viewer_headers, in_review_fmea):
    resp = await client.post(f"/api/fmea/{in_review_fmea}/transition",
                             json={"target_status": "rework", "reason": "x"},
                             headers=viewer_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rework_requires_nonempty_reason(client, manager_headers, in_review_fmea):
    resp = await client.post(f"/api/fmea/{in_review_fmea}/transition",
                             json={"target_status": "rework", "reason": "  "},
                             headers=manager_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_requires_wizard_completed(client, engineer_headers, draft_fmea_incomplete_wizard):
    resp = await client.post(f"/api/fmea/{draft_fmea_incomplete_wizard}/transition",
                             json={"target_status": "in_review"},
                             headers=engineer_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_rejected_when_in_review(client, engineer_headers, in_review_fmea):
    resp = await client.put(f"/api/fmea/{in_review_fmea}",
                            json={"title": "新标题"}, headers=engineer_headers)
    assert resp.status_code in (409, 403)


@pytest.mark.asyncio
async def test_approved_to_rework_keeps_approved_by(client, manager_headers, approved_fmea):
    resp = await client.post(f"/api/fmea/{approved_fmea}/transition",
                             json={"target_status": "rework", "reason": "复审"},
                             headers=manager_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rework"
    assert body["approved_by"] is not None  # 保留历史，不清空
```

Adapt the header/FMEA fixtures to existing API-test fixtures (roles: viewer=L1, engineer=L2 EDIT, manager=L3+ APPROVE).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_approval_gates.py -v`
Expected: FAIL — rework currently allowed without APPROVE, no reason check, no wizard gate, PUT allowed on IN_REVIEW.

- [ ] **Step 3: Write minimal implementation**

Replace `require_approve_permission` (`api/fmea.py:187-196`) with a full matrix:

```python
_APPROVE_TARGETS = {"approved", "rework"}


async def require_transition_permission(
    req: TransitionRequest,
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
) -> RequestScope:
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if req.target_status in _APPROVE_TARGETS:
        if level < PermissionLevel.APPROVE:
            raise HTTPException(status_code=403, detail="审批权限不足")
    elif req.target_status == "in_review":
        if level < PermissionLevel.EDIT:
            raise HTTPException(status_code=403, detail="需要 fmea 模块的 EDIT 权限")
    if req.target_status == "rework" and not (req.reason and req.reason.strip()):
        raise HTTPException(status_code=422, detail="驳回必须携带非空 reason")
    return scope
```

Update the transition route to use `require_transition_permission` and add the wizard gate after fetching `fmea` (`:206-209`):

```python
    if req.target_status == "in_review":
        wizard_scope = (fmea.graph_data or {}).get("wizardScope") or {}
        if wizard_scope.get("wizard_completed") is not True:
            raise HTTPException(status_code=422, detail="向导未完成，不能提交评审")
```

Pass `reason` through to the service call if you persist it (optional; the audit `changed_fields` may include `reason`). In `update_fmea` (`:118-126`), after the factory checks, add the editable-state guard:

```python
    if fmea.status not in ("draft", "rework"):
        raise HTTPException(status_code=409, detail="当前状态不可编辑（仅草稿/返工可编辑）")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_approval_gates.py -v`
Expected: 5 PASS. Then regression:
Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -k "fmea" --tb=short`
Expected: no new failures (update tests that relied on the loose transitions).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/fmea.py backend/tests/test_fmea_approval_gates.py
git commit -m "feat(fmea): approval permission matrix + rework reason 422 + wizard_completed 422 + editable-state 409"
```

---

## Task 11: Verify-skill scaffold (1 epic + 19 sub-story skills)

**Files:**
- Create: `.claude/skills/verify-fmea-lifecycle/SKILL.md`
- Create: `.claude/skills/verify-fmea-lifecycle-<name>/SKILL.md` for each of the 19 sub-stories (names in the spec README "子故事索引", e.g. `verify-fmea-lifecycle-pfmea-step1-planning`, …, `verify-fmea-lifecycle-approval-cycle`).

**Interfaces:**
- Consumes: `docs/user-stories/US-E2E-02-fmea-lifecycle/` README + 19 sub-story files (each sub-story names its skill at the top, e.g. `` `verify-fmea-lifecycle-pfmea-step1-planning`（待生成）``).
- Produces: 20 skill files. Each sub-story skill's `description` front-matter must state it verifies that sub-story's acceptance contract; the body links the sub-story file and enumerates its PASS/FAILED/BLOCKED checks as a runnable checklist. The epic skill aggregates the 19.

- [ ] **Step 1: Read the US-E2E-01 precedent to match conventions**

Run: `ls .claude/skills/ | grep -i capa` and read one existing closed-loop verify skill (the spec mirrors `US-E2E-01-capa-8d-closed-loop`).
Expected: a `SKILL.md` with YAML front-matter (`name`, `description`) + a verification checklist body.

- [ ] **Step 2: Generate the epic skill**

Write `.claude/skills/verify-fmea-lifecycle/SKILL.md` with front-matter `name: verify-fmea-lifecycle`, a `description` stating it runs the full FMEA lifecycle E2E acceptance (wizard → editor → approval), and a body that: (a) links the spec README, (b) lists the 19 sub-skills, (c) states epic PASS = conjunction of all sub-story PASS, with the AI_REQUIRED→BLOCKED rule (no LLM creds) and functional-error→FAILED rule verbatim from the README.

- [ ] **Step 3: Generate the 19 sub-story skills**

For each sub-story file, create `.claude/skills/verify-fmea-lifecycle-<slug>/SKILL.md` whose `<slug>` matches the skill name declared in that sub-story's "关联 skill" line. Body: link the sub-story file, restate its 验收契约 通过条件/失败条件/阻塞条件 as an executable checklist, and note AI_REQUIRED (true → BLOCKED without LLM creds). Use the exact skill names from the spec (do not invent new slugs).

- [ ] **Step 4: Verify all 20 skills resolve**

Run: `ls .claude/skills/ | grep verify-fmea-lifecycle | wc -l`
Expected: `20`. Cross-check each of the 19 spec "关联 skill" names has a matching directory:
Run: `grep -rho 'verify-fmea-lifecycle[a-z0-9-]*' docs/user-stories/US-E2E-02-fmea-lifecycle/ | sort -u`
Expected: every printed name has a corresponding `.claude/skills/<name>/SKILL.md`.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/
git commit -m "feat(fmea): scaffold verify-fmea-lifecycle skill + 19 sub-story verify skills"
```

---

## Sequencing & Dependencies

```
Task 1 (schemas) ──┬─> Task 5 (adoption audit) ──> Task 6 (status + update_fmea hook)
                   └─> Task 10 (approval gates, uses TransitionRequest.reason)
Task 2 (observability schemas) ──> Task 3 (retrievers) ──> Task 4 (wire into recommend)
Task 7 (CPSyncOutbox) ──> Task 8 (worker+applier) ──> Task 9 (producer in transition)
Task 11 (verify skills) — independent; can run last or in parallel
```

Recommended order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11. Tasks 1→(5,6), 2→3→4, 7→8→9 are hard chains; 10 depends only on Task 1; 11 is independent.

## Definition of Done

- All new + existing backend tests pass: `cd backend && SECRET_KEY=test-secret-key pytest tests/ --tb=short`.
- `alembic upgrade head` clean on a fresh DB.
- Each spec-marked FAILED gap now has a corresponding implemented contract: 3-retriever `source_executions` + `context_execution` + `generation_execution`; `ADOPT_RECOMMENDATION` audit (idempotent); canonical RecommendedAction status; FailureCause/FailureMode risk fields; CP durable outbox (2+N audits, correct changed_fields, correct idempotency keys); approval permission/reason/wizard/editable gates.
- 20 verify skills scaffolded and resolvable.
