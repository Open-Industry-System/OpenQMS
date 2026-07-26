# FMEA Lifecycle Contract Backfill — Full-Stack (Option X)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the backend contract gaps D1–D9 plus the frontend AI-adoption wiring, so the 19 `verify-fmea-lifecycle-*` acceptance sub-stories can reach **all-PASS** on a re-run of the US-E2E-02 walk.

**Architecture:** The wizard steps (02.1–02.14), editor CRUD (02.15), and collaborative editing (02.17) already behave per spec — no re-implementation. The work is a set of **backend contract backfills** (D1–D9): AI recommendation must query 3 retrievers with observability (`source_executions`/`context_execution`/`generation_execution`), suggestions must carry a deterministic content-hash `recommendation_id`, AI adoption must be audited (`ADOPT_RECOMMENDATION`), RecommendedAction needs a canonical 4-state status, FailureCause/FailureMode need risk-handling fields, CP sync must become a durable outbox (not a direct two-phase call), and the approval endpoint needs the full permission/reason/wizard/editable-state gates — **plus** the **frontend adoption wiring** that captures a suggestion selection into `FMEAUpdate.adoptions` so the `ADOPT_RECOMMENDATION` audit is reachable end-to-end.

**Tech Stack:** Python 3.11, FastAPI 0.115 (async), SQLAlchemy 2.0 (async) + asyncpg, Pydantic v2, Alembic (hand-written), pytest + pytest-asyncio, pgvector | React 18 + TypeScript 5.6 + Vite 5.4 + Ant Design 5.29, vitest.

**Why this replaces the earlier plan:** `2026-07-25-fmea-lifecycle-contract-backfill.md` was marked OUT-OF-SCOPE and is now **superseded**. This revision: (a) drops its Task 11 (the 20 verify skills already exist — commit `cb06d1ea`); (b) merges its Task 10 with the N5 fix already on this branch (`require_approve_permission` now gates EDIT-for-all + APPROVE-for-approved, commit `b5b907fe`) into one unified transition gate that **adds the remaining rework/reason/wizard gates**; (c) adds embedding wiring (`app.state.embedding_provider` → `RecommendationService`); (d) adds the content-hash `recommendation_id`; (e) adds **Phase 2 frontend** adoption tasks. The acceptance walk can only reach all-PASS with these implemented.

## Global Constraints

- **Branch:** `fix/fmea-fixes`. Do all work here. Do NOT work on `main`.
- **Backend test command:** `cd backend && SECRET_KEY=test-secret-key pytest tests/ -x --tb=short`.
- **Frontend test command:** `cd frontend && npx vitest run <file>`; full type+build gate `cd frontend && npm run build` (runs `tsc --noEmit` + `vite build`).
- **Spec of record:** `docs/user-stories/US-E2E-02-fmea-lifecycle/` (README v3 + 19 sub-stories). Field names, enum values, and audit actions below are copied verbatim from it — do not paraphrase.
- **`recommendation_id` = content hash.** Computed backend-side, deterministic and idempotent, **zero migration** (suggestions are transient, not persisted). Format: `"rec_" + sha256(trigger_type + "|" + anchor + "|" + name + "|" + source)[:12]`, where `anchor` is the same anchor text used by `_recommend_anchor` / `run_retrievers` (the trigger's query text). The frontend echoes this value back in `RecommendationAdoption.recommendation_id`; the backend dedupes `ADOPT_RECOMMENDATION` audits by it.
- **RecommendedAction canonical status enum:** `{open, in_progress, completed, not_executed}`. Legacy mapping: `undecided→open, planned→in_progress, done→completed, notExecuted→not_executed, closed→completed`.
- **AI required retrievers (must appear in `source_executions`):** `graph`, `semantic_search`, `lessons_learned`. `status ∈ {success, empty, unavailable, error}`. `rule` is NOT a required retriever. `context_execution.current_product_structure ∈ {assembled, unavailable}` and `generation_execution.llm ∈ {success, unavailable, error}` are separate top-level fields, not in `source_executions`.
- **AuditLog `action` enum (separate from Outbox `event_type`):** `CREATE / UPDATE / DELETE / TRANSITION / FORCE_SAVE_OVERRIDE / ADOPT_RECOMMENDATION`.
- **CP sync = Durable outbox** targeting a NEW `cp_sync_outbox` table + NEW worker. **Never reuse `GraphSyncOutbox`/`graph_sync_worker`** (Neo4j-only). CP audit `changed_fields` records only `sync_pending: "false->true"` + `trigger_fmea_version_id` — never `source_fmea_version_id`.
- **Idempotency keys:** CP outbox event key = `(fmea_id, fmea_version_id, event_type='cp.sync_pending_set')`; worker processing key = `(outbox_id, cp_id)`. Already-`sync_pending=true` CPs are not re-audited.
- **Risk-handling fields** live on `GraphNodeSchema` (FailureCause rows; cause-less placeholder rows fall back to FailureMode): `control_sufficiency_reason`, `risk_acceptance_reason`, `management_review_evidence`.
- **DB is JSONB graph**: `FMEADocument.graph_data = {nodes, edges, wizardScope}`. New node fields are new optional keys on `GraphNodeSchema` — no DB column migration needed for node fields, only for the new outbox table.
- **`factory_id` NOT NULL on all business tables** — populate, never relax.
- **Services raise `ValueError`; the API layer converts to `HTTPException`.** Match this pattern.
- **Pre-existing dev-DB drift** (`embedding_sync_outbox.content_hash`, pgcrypto, `shipment_records.factory_id`) causes 2 known failures in `tests/fmea/test_fmea_update_core.py`. These are **pre-existing and out of scope** — do NOT fix them, do NOT chase them. Identify precisely and move on.
- **Surgical changes only; match existing style.** No refactors beyond the task.

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/schemas/fmea.py` | `RecommendationAdoption`, `FMEAUpdate.adoptions`, `TransitionRequest.reason`, node risk fields, `RecommendedActionStatus` |
| `backend/app/schemas/recommendation.py` | `SourceExecution`/`ContextExecution`/`GenerationExecution`, widen `SuggestionItem.source`, add `SuggestionItem.recommendation_id` |
| `backend/app/services/recommendation_service.py` | wire 3 retrievers + observability + `recommendation_id` stamping into `recommend()`; `__init__` gains `embedding` |
| `backend/app/services/retriever_executions.py` | NEW: run semantic_search + lessons_learned retrievers, capture `SourceExecution` |
| `backend/app/services/adoption_audit.py` | NEW: dedupe + write `ADOPT_RECOMMENDATION` audit |
| `backend/app/services/recommended_action_status.py` | NEW: legacy→canonical status normalizer |
| `backend/app/services/fmea_service.py` | `update_fmea` adoptions param; `transition_fmea` CP-outbox producer (remove direct CP call) |
| `backend/app/services/control_plan_service.py` | `apply_cp_sync_pending(outbox)` idempotent worker-side applier |
| `backend/app/models/cp_sync_outbox.py` | NEW: `CPSyncOutbox` model |
| `backend/app/services/cp_sync_worker.py` | NEW: poll/lock/apply/retry worker |
| `backend/alembic/versions/20260726_add_cp_sync_outbox.py` | NEW: `cp_sync_outbox` table migration |
| `backend/app/api/fmea.py` | unified transition gate (rework APPROVE + reason 422 + wizard 422), editable-state 409, embedding wiring into recommend route |
| `frontend/src/api/recommendation.ts` | widen `Suggestion.source` (5), add `recommendation_id` |
| `frontend/src/api/fmea.ts` | `updateFMEA` accepts `adoptions`; add `RecommendationAdoption` type |
| `frontend/src/hooks/useWizardSave.ts` | `enqueueSave`/`immediateSave` accept + forward `adoptions` |
| `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx` | `onSelect` widened to carry the full `Suggestion` (already does) — no signature change; callers wire adoption |
| `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` | capture suggestion selection → `adoptions`, pass through save |
| `frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx` | same adoption wiring (wizard save path) |
| `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx` | same adoption wiring (wizard save path) |

Interface notes for implementers (exact current signatures, verified against this branch):
- `RecommendationService.__init__(self, db, graph_repo, llm_timeout=None)` at `recommendation_service.py:556`. `recommend(fmea_id, request, user, request_scope, tenant_schema)` at `:564`.
- `recommend()` internals: `pc` (provider client or `None`) at `:573`; `product_line_codes` at `:585`; `rule_suggestions` at `:610`; `graph_suggestions: list[SuggestionItem]` at `:615-624`; `all_suggestions = self._merge_and_deduplicate(rule_suggestions, graph_suggestions)` at `:627`; `need_llm` at `:630`; LLM block `:636-676` (success sets `llm_status`/merges `llm_items`; `except` at `:662`); `response = RecommendResponse(...)` at `:679`; cache return at `:590-602`.
- `LessonsSemanticSource(db, embedding).name == "semantic_search"`, `.retrieve(context) -> list[RecommendationCandidate]` at `lessons_learned/sources/semantic.py:9`. Candidate fields: `.content`, `.confidence`, `.match_reason`, `.metadata` (dict with `document_no`, `product_line_code`, `node_id`, `fmea_id`).
- `LessonsLearnedService(db, embedding).recommend(doc_id, doc_type, problem_description, user, skip_fmea_sources=False) -> LessonsLearnedResponse` at `lessons_learned/service.py:36`. `LessonsLearnedResponse.cards: list[LessonCard]`; `LessonCard` has `.title`, `.summary`.
- `RecommendationCandidate` dataclass at `recommendation_types.py:36` — fields `source/content/category/confidence/match_reason/metadata`.
- `update_fmea` route at `api/fmea.py:111`; service `_apply_fmea_update` core at `fmea_service.py:196` (the public `update_fmea` wraps it and commits). **Confirm the exact public `update_fmea` signature before editing** — it is the wrapper that takes `db, fmea, title, graph_data, user_id, product_line_code, lock_version, confirmed_latest_lock_version`.
- `transition_fmea(db, fmea, target_status, user_id)` at `fmea_service.py:373`; version snapshot at `:398-406` (`version` = `_create_fmea_version_no_commit(...)`); `await db.commit()` at `:427`; direct CP call at `:429-432` (remove in Phase-1 Task 9).
- `_create_fmea_version_no_commit(db, fmea, change_type, change_summary, user_id) -> FMEAVersion` (sets `.version_id`) at `version_service.py:86`.
- `require_approve_permission` at `api/fmea.py:190-200` (N5 version — EDIT-for-all + APPROVE-for-approved). Transition route `transition_fmea` at `api/fmea.py:203-218` (uses `scope: RequestScope = Depends(require_approve_permission)`).
- Recommend route `recommend` at `api/fmea.py:272-330`; constructs `RecommendationService(db=db, graph_repo=graph_repo, llm_timeout=llm_timeout)` at `:325`.
- Embedding accessor (existing pattern): `embedding = getattr(request.app.state, "embedding_provider", None)` — used at `api/search.py:23`, `api/fmea.py:400`.
- `get_user_permission(user, Module.FMEA, db) -> PermissionLevel`; `PermissionLevel.{VIEW,EDIT,APPROVE}`; `Module.FMEA`.
- ControlPlan: PK `cp_id`, `fmea_ref_id` (nullable FK→fmea_documents), `sync_pending: bool default False`, `factory_id` NOT NULL, `document_no` unique NOT NULL, `title` NOT NULL — `models/control_plan.py:12-41`.
- Frontend `Suggestion` at `api/recommendation.ts:3`; `updateFMEA` at `api/fmea.ts:32`; `useWizardSave.enqueueSave(graphData, title, dataHash)` at `hooks/useWizardSave.ts:65` → `updateFMEA(fmeaId, {title, graph_data, lock_version})` at `:78`; `SmartSuggestionDropdown` `onSelect: (suggestion: Suggestion) => void` at `components/dfmea/SmartSuggestionDropdown.tsx:16`, `handleSelect` at `:153`.

---

# PHASE 1 — Backend contract (D1–D9) + embedding + recommendation_id

Goal of this phase: all backend tests green; the recommend/transition/update endpoints emit the full contract. No frontend changes yet.

## Task P1.1: Schema extensions (adoptions, transition reason, node risk/status fields)

**Files:**
- Modify: `backend/app/schemas/fmea.py`
- Test: `backend/tests/test_fmea_schema_extensions.py`

**Interfaces:**
- Consumes: existing `GraphNodeSchema` (`schemas/fmea.py:11`), `FMEAUpdate` (`:93`), `TransitionRequest` (`:127`).
- Produces:
  - `class RecommendationAdoption(BaseModel)`: `field_id: str`, `recommendation_id: str`, `source: str`, `stage_index: int`, `adopted_text: str`.
  - `FMEAUpdate.adoptions: list[RecommendationAdoption] | None = None`.
  - `TransitionRequest.reason: str | None = None`.
  - `RecommendedActionStatus = Literal["open", "in_progress", "completed", "not_executed"]`.
  - `GraphNodeSchema` new optional fields (after `revised_ap` at `:44`): `control_sufficiency_reason: str | None`, `risk_acceptance_reason: str | None`, `management_review_evidence: str | None`, `recommended_action_status: RecommendedActionStatus | None`. Legacy `status: str` (`:36`) retained for back-compat.

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
    assert TransitionRequest(target_status="approved").reason is None


def test_graph_node_risk_fields_and_canonical_status():
    n = GraphNodeSchema(
        id="fc1", type="FailureCause", name="原因",
        control_sufficiency_reason="现有控制充分",
        management_review_evidence="管理层已评审",
        recommended_action_status="not_executed",
    )
    assert n.control_sufficiency_reason == "现有控制充分"
    assert n.recommended_action_status == "not_executed"


def test_recommended_action_status_rejects_legacy_value():
    import pytest
    with pytest.raises(Exception):
        GraphNodeSchema(id="ra1", type="RecommendedAction", name="m",
                        recommended_action_status="undecided")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_schema_extensions.py -v`
Expected: FAIL — `ImportError: cannot import name 'RecommendationAdoption'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas/fmea.py`, add `Literal` to the `typing` import (file currently imports `uuid`, `datetime`, pydantic — add `from typing import Literal`), then add after the imports:

```python
RecommendedActionStatus = Literal["open", "in_progress", "completed", "not_executed"]


class RecommendationAdoption(BaseModel):
    field_id: str
    recommendation_id: str
    source: str
    stage_index: int
    adopted_text: str
```

Add to `GraphNodeSchema` after `revised_ap` (`:44`):

```python
    # Step 6 风险处置理由（挂 FailureCause；placeholder 行回退到 FailureMode）
    control_sufficiency_reason: str | None = None
    risk_acceptance_reason: str | None = None
    management_review_evidence: str | None = None
    # RecommendedAction canonical 状态（与 legacy `status` 并存，迁移期）
    recommended_action_status: RecommendedActionStatus | None = None
```

Add to `FMEAUpdate` (`:93`): `adoptions: list[RecommendationAdoption] | None = None`
Add to `TransitionRequest` (`:127`): `reason: str | None = None`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_schema_extensions.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/fmea.py backend/tests/test_fmea_schema_extensions.py
git commit -m "feat(fmea): schema extensions — adoptions, transition reason, node risk fields, canonical action status"
```

---

## Task P1.2: Recommendation observability schemas + content-hash recommendation_id

**Files:**
- Modify: `backend/app/schemas/recommendation.py`
- Test: `backend/tests/test_recommendation_observability_schema.py`

**Interfaces:**
- Consumes: existing `SuggestionItem` (`schemas/recommendation.py:18`), `RecommendResponse` (`:34`).
- Produces:
  - `class SourceExecution(BaseModel)`: `source: str`, `status: Literal["success","empty","unavailable","error"]`, `hit_count: int = 0`, `latency_ms: int = 0`.
  - `class ContextExecution(BaseModel)`: `current_product_structure: Literal["assembled","unavailable"] = "assembled"`.
  - `class GenerationExecution(BaseModel)`: `llm: Literal["success","unavailable","error"] = "unavailable"`.
  - `RecommendResponse` new fields: `source_executions: list[SourceExecution] = []`, `context_execution: ContextExecution = ContextExecution()`, `generation_execution: GenerationExecution = GenerationExecution()`.
  - `SuggestionItem.source` widened to `Literal["rule","graph","semantic_search","lessons_learned","llm"]`.
  - `SuggestionItem.recommendation_id: str | None = None` (populated backend-side in Phase-1 Task P1.4).
  - `def compute_recommendation_id(trigger_type: str, anchor: str, name: str, source: str) -> str` — module-level helper, `"rec_" + sha256(trigger_type + "|" + anchor + "|" + name + "|" + source)[:12]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_recommendation_observability_schema.py
from app.schemas.recommendation import (
    ContextExecution, GenerationExecution, RecommendResponse,
    SourceExecution, SuggestionItem, compute_recommendation_id,
)


def test_source_execution_status_enum():
    SourceExecution(source="graph", status="success", hit_count=3, latency_ms=12)
    for ok in ("success", "empty", "unavailable", "error"):
        SourceExecution(source="semantic_search", status=ok)
    import pytest
    with pytest.raises(Exception):
        SourceExecution(source="graph", status="bogus")


def test_suggestion_item_source_widened_and_recommendation_id():
    for s in ("rule", "graph", "semantic_search", "lessons_learned", "llm"):
        item = SuggestionItem(name="x", confidence=0.5, source=s)
        assert item.source == s
        assert item.recommendation_id is None  # default until stamped
    item2 = SuggestionItem(name="x", confidence=0.5, source="llm", recommendation_id="rec_1")
    assert item2.recommendation_id == "rec_1"


def test_recommend_response_has_observability_fields():
    r = RecommendResponse(
        suggestions=[], source="hybrid",
        source_executions=[SourceExecution(source="graph", status="empty")],
        context_execution=ContextExecution(current_product_structure="assembled"),
        generation_execution=GenerationExecution(llm="success"),
    )
    assert r.source_executions[0].source == "graph"
    assert r.context_execution.current_product_structure == "assembled"
    assert r.generation_execution.llm == "success"
    r2 = RecommendResponse(suggestions=[], source="rule")
    assert r2.source_executions == []
    assert r2.generation_execution.llm == "unavailable"


def test_compute_recommendation_id_deterministic_and_scoped():
    a = compute_recommendation_id("failure_mode", "焊接", "电流不足", "graph")
    b = compute_recommendation_id("failure_mode", "焊接", "电流不足", "graph")
    c = compute_recommendation_id("failure_mode", "焊接", "电流不足", "llm")
    d = compute_recommendation_id("failure_mode", "焊接", "电压不足", "graph")
    assert a == b                      # deterministic
    assert a.startswith("rec_") and len(a) == 16
    assert a != c                      # source is part of the hash
    assert a != d                      # name is part of the hash
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommendation_observability_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'SourceExecution'` (and `compute_recommendation_id`).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas/recommendation.py`, change the `SuggestionItem.source` line (`:21`) to:

```python
    source: Literal["rule", "graph", "semantic_search", "lessons_learned", "llm"] = "rule"
    recommendation_id: str | None = None  # backend-stamped content hash (Phase-1 Task P1.4)
```

Add at the top of the file (after imports) and the new classes before `RecommendResponse` (`:34`):

```python
import hashlib


def compute_recommendation_id(trigger_type: str, anchor: str, name: str, source: str) -> str:
    """Deterministic content-hash id for a suggestion. Idempotent across re-fetch
    of the same suggestion; distinct across source/name. Suggestions are transient
    (not persisted), so a content hash — not a DB id — is the natural key for
    adoption-audit dedupe. Zero migration."""
    raw = f"{trigger_type}|{anchor}|{name}|{source}"
    return "rec_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


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
Expected: 4 PASS. Then regression on the widened `source` literal:
Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -k "recommend" --tb=short`
Expected: no new failures (rule/graph/llm still valid).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/recommendation.py backend/tests/test_recommendation_observability_schema.py
git commit -m "feat(recommend): observability schemas + content-hash recommendation_id, widen SuggestionItem.source"
```

---

## Task P1.3: Retriever execution collector (semantic_search + lessons_learned)

**Files:**
- Create: `backend/app/services/retriever_executions.py`
- Test: `backend/tests/test_retriever_executions.py`

**Interfaces:**
- Consumes: `LessonsSemanticSource(db, embedding)` (`lessons_learned/sources/semantic.py:9`), `LessonsLearnedService(db, embedding)` (`lessons_learned/service.py:24`), `SourceExecution`/`SuggestionItem` (Task P1.2), `RecommendationCandidate` (`recommendation_types.py:36`).
- Produces:
  - `async def run_retrievers(db, embedding, *, query_text, user_product_lines, fmea_id, fmea_type, product_line_code, user) -> tuple[list[SourceExecution], list[SuggestionItem]]`
    - Runs `semantic_search` (via `LessonsSemanticSource.retrieve`) and `lessons_learned` (via `LessonsLearnedService.recommend`, which needs the real `doc_id`/`user`) with per-retriever timing + status classification.
    - Returns 2 `SourceExecution` rows (graph is added by the caller in Task P1.4) + the candidates mapped to `SuggestionItem` with `source` set to the retriever name.
    - Status rules: `embedding is None` → `unavailable`; exception → `error`; zero candidates → `empty`; ≥1 → `success`. Never raises.
  - `SuggestionItem` mapping reads `RecommendationCandidate.content` (not `.name`) for semantic, and `LessonCard.title`/`summary` for lessons.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_retriever_executions.py
import uuid
import pytest
from app.models.fmea import FMEADocument
from app.services.retriever_executions import run_retrievers


class _FakeEmbedding:
    async def embed(self, texts):
        return [[0.01] * 1536 for _ in texts]


@pytest.mark.asyncio
async def test_unavailable_when_no_embedding(db, default_factory, admin_user):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-RET-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()
    execs, items = await run_retrievers(
        db, None, query_text="焊接", user_product_lines=None,
        fmea_id=fmea.fmea_id, fmea_type="PFMEA",
        product_line_code="DC-DC-100", user=admin_user,
    )
    by_src = {e.source: e for e in execs}
    assert by_src["semantic_search"].status == "unavailable"
    assert by_src["lessons_learned"].status == "unavailable"
    assert items == []


@pytest.mark.asyncio
async def test_status_is_empty_or_success_never_raises(db, default_factory, admin_user):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-RET-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()
    execs, items = await run_retrievers(
        db, _FakeEmbedding(), query_text="不存在的失效模式xyz", user_product_lines=None,
        fmea_id=fmea.fmea_id, fmea_type="PFMEA",
        product_line_code="DC-DC-100", user=admin_user,
    )
    by_src = {e.source: e for e in execs}
    for name in ("semantic_search", "lessons_learned"):
        assert by_src[name].status in ("success", "empty")
        assert by_src[name].hit_count >= 0 and by_src[name].latency_ms >= 0
    for it in items:
        assert it.source in ("semantic_search", "lessons_learned")
```

The `db`, `default_factory`, `admin_user` fixtures already exist in `backend/tests/conftest.py` (`db` is the async-session fixture; verify the exact name — neighboring tests use `db`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_retriever_executions.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.retriever_executions`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/retriever_executions.py
"""Run external knowledge retrievers for FMEA recommendation with observability.

Each retriever is classified into a SourceExecution status so E2E can distinguish
"called but zero hits" (empty) from "not called / no creds" (unavailable) from
"raised" (error). Never raises — degradations are returned as 200 with status rows.
"""
import time
import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.recommendation import SourceExecution, SuggestionItem


async def _run_one(name, coro_factory):
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
    fmea_id: _uuid.UUID,
    fmea_type: str,
    product_line_code: str,
    user,
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
        doc_type="fmea", doc_id=fmea_id, query_text=query_text,
        fmea_type=fmea_type, severity=None,
        product_line_code=product_line_code, user_product_lines=user_product_lines,
    )

    # --- semantic_search (pgvector over FMEA node embeddings) ---
    sem_src = LessonsSemanticSource(db, embedding)
    sem_exec, sem_cands = await _run_one(
        "semantic_search", lambda: sem_src.retrieve(context)
    )
    executions.append(sem_exec)
    suggestions.extend(
        SuggestionItem(
            name=c.content,
            confidence=float(c.confidence or 0.5),
            source="semantic_search",
            source_document_no=(c.metadata or {}).get("document_no"),
            explanation=c.match_reason or "",
        )
        for c in sem_cands
    )

    # --- lessons_learned (经验教训库 orchestrator; needs real doc_id + user) ---
    lessons_svc = LessonsLearnedService(db, embedding)

    async def _lessons():
        resp = await lessons_svc.recommend(
            fmea_id, "fmea", query_text or None, user,
        )
        return getattr(resp, "cards", []) or []

    les_exec, les_cards = await _run_one("lessons_learned", _lessons)
    executions.append(les_exec)
    suggestions.extend(
        SuggestionItem(
            name=getattr(c, "title", "") or "",
            confidence=0.5,
            source="lessons_learned",
            explanation=getattr(c, "summary", "") or "",
        )
        for c in les_cards
    )

    return executions, suggestions
```

> **Note for implementer:** `LessonsLearnedService.recommend` requires a real `doc_id` and `user` — pass them through from the caller (Task P1.4). If the orchestrator's multi-source fusion is too heavy / raises in the test DB, fall back to querying the lessons sources directly (`HistoricalFMEASource`, `LessonsCAPASource`) — but the **contract that MUST hold**: two `SourceExecution` rows named exactly `semantic_search` and `lessons_learned`, correct status classification, `SuggestionItem.source` set to the retriever name, never raises. Keep `run_retrievers`'s signature stable — Task P1.4 depends on it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_retriever_executions.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/retriever_executions.py backend/tests/test_retriever_executions.py
git commit -m "feat(recommend): retriever execution collector for semantic_search + lessons_learned"
```

---

## Task P1.4: Wire 3 retrievers + observability + recommendation_id into RecommendationService.recommend (+ embedding)

**Files:**
- Modify: `backend/app/services/recommendation_service.py` (`__init__` at `:556`, `recommend` at `:564-690`)
- Modify: `backend/app/api/fmea.py` (recommend route at `:272-330`)
- Test: `backend/tests/test_recommend_observability.py`

**Interfaces:**
- Consumes: `run_retrievers` (Task P1.3), `SourceExecution/ContextExecution/GenerationExecution/compute_recommendation_id` (Task P1.2), existing `_query_graph_similarity`, `_assemble_context`, `pc`, `product_line_codes`.
- Produces: `recommend()` returns `RecommendResponse` with `source_executions` (3 required retrievers), `context_execution`, `generation_execution`; every `SuggestionItem` carries a stamped `recommendation_id`. `RecommendationService.__init__` gains `embedding: object | None = None`. The recommend **route** passes `embedding = getattr(fastapi_request.app.state, "embedding_provider", None)`.

- [ ] **Step 1: Write the failing test**

Reuse the `admin_client`/`db`/`default_factory`/`admin_user` + `FMEADocument` construction pattern from `backend/tests/test_fmea_recommend_api.py`:

```python
# backend/tests/test_recommend_observability.py
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
import uuid
import pytest
from app.models.fmea import FMEADocument


@pytest.mark.asyncio
async def test_recommend_reports_three_required_retrievers(
    admin_client, db, default_factory, admin_user
):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-OBS-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()
    resp = await admin_client.post(
        f"/api/fmea/{fmea.fmea_id}/recommend",
        json={"trigger_type": "failure_mode",
              "context": {"function_description": "焊接"},
              "include_graph": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    sources = {e["source"] for e in body["source_executions"]}
    assert {"graph", "semantic_search", "lessons_learned"} <= sources
    for e in body["source_executions"]:
        assert e["status"] in ("success", "empty", "unavailable", "error")
    assert body["context_execution"]["current_product_structure"] in ("assembled", "unavailable")
    assert body["generation_execution"]["llm"] in ("success", "unavailable", "error")
    # every suggestion carries a stamped recommendation_id
    for s in body["suggestions"]:
        assert s["recommendation_id"] and s["recommendation_id"].startswith("rec_")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommend_observability.py -v`
Expected: FAIL — `KeyError: 'source_executions'` (response lacks the field).

- [ ] **Step 3: Write minimal implementation**

**(a) `RecommendationService.__init__` (`:556`)** — add the kwarg:

```python
    def __init__(self, db: AsyncSession, graph_repo: FMEAGraphRepository,
                 llm_timeout: int | None = None, embedding: object | None = None):
        self.db = db
        self.graph_repo = graph_repo
        self.rules = RuleEngine()
        self.embedding = embedding
        self.llm_timeout = max(llm_timeout or settings.LLM_TIMEOUT, 15)
```

**(b) recommend route (`api/fmea.py:324-325`)** — pass embedding:

```python
    llm_timeout = getattr(fastapi_request.app.state, "llm_timeout", None)
    embedding = getattr(fastapi_request.app.state, "embedding_provider", None)
    service = RecommendationService(db=db, graph_repo=graph_repo, llm_timeout=llm_timeout, embedding=embedding)
```

**(c) `recommend()`** — after the graph block (`:615-624`) and the existing merge (`:627`), build the graph execution row and run the external retrievers. Compute the `anchor` (same query text used for the content hash). Insert after `:627`:

```python
        from app.schemas.recommendation import (
            ContextExecution, GenerationExecution, SourceExecution,
            compute_recommendation_id,
        )
        from app.services.retriever_executions import run_retrievers

        anchor = (
            request.context.get("function_description")
            or request.context.get("input_text")
            or request.context.get("failure_mode")
            or ""
        )

        source_executions: list[SourceExecution] = []
        if include_graph:
            source_executions.append(SourceExecution(
                source="graph",
                status="success" if graph_suggestions else "empty",
                hit_count=len(graph_suggestions),
            ))
        else:
            source_executions.append(SourceExecution(source="graph", status="unavailable"))

        retriever_execs, retriever_items = await run_retrievers(
            self.db, self.embedding,
            query_text=anchor, user_product_lines=product_line_codes,
            fmea_id=fmea.fmea_id, fmea_type=fmea.fmea_type,
            product_line_code=fmea.product_line_code, user=user,
        )
        source_executions.extend(retriever_execs)
        all_suggestions = self._merge_and_deduplicate(all_suggestions, retriever_items)
```

**(d)** Track `generation_execution`/`context_execution` around the LLM block (`:630-676`). Initialize before `if need_llm:`; set `context_execution` from `_assemble_context` and `generation_execution.llm = "error"` in the `except` block:

```python
        generation_execution = GenerationExecution(
            llm="unavailable" if pc is None else "success"
        )
        context_execution = ContextExecution(current_product_structure="assembled")
        # inside `if need_llm:` try, after `llm_context = await self._assemble_context(...)`:
        #     context_execution.current_product_structure = "assembled" if llm_context else "unavailable"
        # inside the LLM `except` block (`:662`):
        #     generation_execution.llm = "error"
```

**(e)** Stamp `recommendation_id` on every suggestion just before building the response (`:679`):

```python
        for s in all_suggestions:
            if not s.recommendation_id:
                s.recommendation_id = compute_recommendation_id(
                    request.trigger_type, anchor, s.name, s.source,
                )

        response = RecommendResponse(
            suggestions=all_suggestions[:10],
            source=source,
            cached=False,
            llm_available=pc is not None,
            graph_match_count=len(graph_suggestions),
            effective_scope=effective_scope,
            source_executions=source_executions,
            context_execution=context_execution,
            generation_execution=generation_execution,
        )
```

**(f)** Cache return (`:590-602`): cached responses were serialized before these fields existed — backfill so the contract holds (the schema defaults already make them `[]`/default; just ensure the return doesn't break). No code change needed if the cached object is a `RecommendResponse` (defaults apply); add a defensive comment only.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommend_observability.py -v`
Expected: PASS. Then regression:
Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -k "recommend" --tb=short`
Expected: no new failures. (The `_FakeService` in `test_fmea_recommend_api.py` constructs with `(db, graph_repo, llm_timeout=None)` — if it now breaks because the route passes `embedding=`, update that fake's `__init__` to accept `embedding=None` too.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_service.py backend/app/api/fmea.py backend/tests/test_recommend_observability.py
git commit -m "feat(recommend): wire graph+semantic+lessons retrievers + observability + recommendation_id; pass embedding from app.state"
```

---

## Task P1.5: Adoption audit service (ADOPT_RECOMMENDATION)

**Files:**
- Create: `backend/app/services/adoption_audit.py`
- Test: `backend/tests/test_adoption_audit.py`

**Interfaces:**
- Consumes: `RecommendationAdoption` (Task P1.1), `AuditLog` model (`app/models/audit.py`).
- Produces:
  - `async def write_adoption_audits(db, fmea_id, adoptions, user_id) -> int` — dedupes by `recommendation_id` (existing `AuditLog` with `action="ADOPT_RECOMMENDATION"` whose `changed_fields->>'recommendation_id'` matches is skipped); writes one `AuditLog` per new adoption (`table_name="fmea_documents"`, `record_id=fmea_id`, `action="ADOPT_RECOMMENDATION"`, `changed_fields={field_id, recommendation_id, source, stage_index, adopted_text}`, `operated_by=user_id`); does NOT commit; returns count written.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_adoption_audit.py
import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.fmea import FMEADocument
from app.schemas.fmea import RecommendationAdoption
from app.services.adoption_audit import write_adoption_audits


def _a(rid, fid="fm1"):
    return RecommendationAdoption(
        field_id=fid, recommendation_id=rid, source="graph",
        stage_index=0, adopted_text="焊接电流不足",
    )


async def _mk(db, factory_id):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-ADO-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=factory_id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()
    return fmea


@pytest.mark.asyncio
async def test_writes_one_audit_per_adoption(db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id)
    n = await write_adoption_audits(db, fmea.fmea_id, [_a("r1"), _a("r2")], admin_user.user_id)
    await db.commit()
    assert n == 2
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert len(rows) == 2
    assert rows[0].changed_fields["recommendation_id"] in ("r1", "r2")


@pytest.mark.asyncio
async def test_idempotent_by_recommendation_id(db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id)
    await write_adoption_audits(db, fmea.fmea_id, [_a("r1")], admin_user.user_id)
    await db.commit()
    n2 = await write_adoption_audits(db, fmea.fmea_id, [_a("r1")], admin_user.user_id)
    await db.commit()
    assert n2 == 0
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert len(rows) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_adoption_audit.py -v`
Expected: FAIL — `ModuleNotFoundError`.

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

## Task P1.6: Canonical action-status normalizer + wire adoptions into update_fmea

**Files:**
- Create: `backend/app/services/recommended_action_status.py`
- Modify: `backend/app/services/fmea_service.py` (`update_fmea` signature + adoption hook before its commit)
- Modify: `backend/app/api/fmea.py` (`update_fmea` route at `:111-164`, pass `req.adoptions`)
- Test: `backend/tests/test_recommended_action_status.py`

**Interfaces:**
- Consumes: `RecommendedActionStatus`/`RecommendationAdoption` (Task P1.1), `write_adoption_audits` (Task P1.5).
- Produces:
  - `def normalize_action_status(value: str | None) -> str | None` — legacy map `undecided→open, planned→in_progress, done→completed, notExecuted→not_executed, closed→completed`; canonical pass-through; unknown/empty → `None`.
  - `update_fmea(..., adoptions: list | None = None)` — trailing kwarg; when non-empty, calls `write_adoption_audits(db, fmea.fmea_id, adoptions, user_id)` inside the same transaction before commit.
  - PUT route forwards `req.adoptions`.

> **Note:** `update_fmea`'s real signature is a wrapper over `_apply_fmea_update` (`fmea_service.py:196`). Read the public `update_fmea` first, add the `adoptions` kwarg there, and call `write_adoption_audits` in the same function that calls `db.commit()` so the audit is atomic with the update.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_recommended_action_status.py
import pytest
from app.services.recommended_action_status import normalize_action_status


@pytest.mark.parametrize("legacy,expected", [
    ("undecided", "open"), ("planned", "in_progress"), ("done", "completed"),
    ("notExecuted", "not_executed"), ("closed", "completed"),
    ("open", "open"), ("in_progress", "in_progress"),
    ("completed", "completed"), ("not_executed", "not_executed"),
    (None, None), ("", None), ("bogus", None),
])
def test_normalize_action_status(legacy, expected):
    assert normalize_action_status(legacy) == expected
```

And an end-to-end route test (append to the same file or a new `test_fmea_update_adoptions.py`), reusing `admin_client`/`db`/`default_factory`/`admin_user`:

```python
@pytest.mark.asyncio
async def test_put_with_adoptions_writes_audit(admin_client, db, default_factory, admin_user):
    import uuid
    from sqlalchemy import select
    from app.models.audit import AuditLog
    from app.models.fmea import FMEADocument
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-PUT-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=default_factory.id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    await db.commit()
    resp = await admin_client.put(
        f"/api/fmea/{fmea.fmea_id}",
        json={"adoptions": [{
            "field_id": "fm1", "recommendation_id": "rec_e2e_1",
            "source": "graph", "stage_index": 0, "adopted_text": "焊接电流不足",
        }]},
    )
    assert resp.status_code == 200
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.action == "ADOPT_RECOMMENDATION"))).scalars().all()
    assert any(r.changed_fields.get("recommendation_id") == "rec_e2e_1" for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommended_action_status.py -v`
Expected: FAIL — `ModuleNotFoundError` (and route test fails: `update_fmea` ignores `adoptions`).

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

In the public `update_fmea` (in `fmea_service.py`), add `adoptions: list | None = None` to the signature and, immediately before its `await db.commit()`:

```python
    if adoptions:
        from app.services.adoption_audit import write_adoption_audits
        await write_adoption_audits(db, fmea.fmea_id, adoptions, user_id)
```

In `api/fmea.py` `update_fmea` route (`:132-136`), pass `req.adoptions` through:

```python
        fmea = await fmea_service.update_fmea(
            db, fmea, req.title, graph_dict, scope.user.user_id, req.product_line_code,
            lock_version=req.lock_version,
            confirmed_latest_lock_version=req.confirmed_latest_lock_version,
            adoptions=req.adoptions,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommended_action_status.py -v`
Expected: 12 PASS + route test PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommended_action_status.py backend/app/services/fmea_service.py backend/app/api/fmea.py backend/tests/test_recommended_action_status.py
git commit -m "feat(fmea): canonical action-status normalizer + adoptions hook in update_fmea"
```

---

## Task P1.7: CPSyncOutbox model + migration

**Files:**
- Create: `backend/app/models/cp_sync_outbox.py`
- Create: `backend/alembic/versions/20260726_add_cp_sync_outbox.py`
- Modify: `backend/app/models/__init__.py` (register model)
- Test: `backend/tests/test_cp_sync_outbox_model.py`

**Interfaces:**
- Consumes: `app.database.Base`; migration pattern from `alembic/versions/027_add_graph_sync_outbox.py`. **Current alembic head = `20260721_capa_lateral_diffusion`** (verified via `alembic heads`) — use it as `down_revision`.
- Produces: `class CPSyncOutbox(Base)`, `__tablename__ = "cp_sync_outbox"`, columns: `id` UUID pk, `fmea_id` UUID not null, `fmea_version_id` UUID not null, `event_type` String default `"cp.sync_pending_set"`, `payload` JSONB default `{}`, `status` String default `"pending"` (pending/processing/completed/dead), `attempt_count` Int default 0, `max_attempts` Int default 5, `next_attempt_at` DateTime tz default now, `last_error` Text nullable, `locked_at` DateTime tz nullable, `created_at` DateTime tz default now, `processed_at` DateTime tz nullable. Unique constraint `uq_cp_sync_outbox_event` on `(fmea_id, fmea_version_id, event_type)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cp_sync_outbox_model.py
import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from app.models.cp_sync_outbox import CPSyncOutbox


@pytest.mark.asyncio
async def test_model_persists_and_unique_event_key(db):
    fmea_id, version_id = uuid.uuid4(), uuid.uuid4()
    db.add(CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=version_id,
                        event_type="cp.sync_pending_set", payload={}))
    await db.commit()
    db.add(CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=version_id,
                        event_type="cp.sync_pending_set", payload={}))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
    db.add(CPSyncOutbox(fmea_id=fmea_id, fmea_version_id=uuid.uuid4(),
                        event_type="cp.sync_pending_set", payload={}))
    await db.commit()
```

- [ ] **Step 2: Run migration then test to verify it fails before model exists**

Run: `cd backend && SECRET_KEY=test-secret-key alembic upgrade head`
Then: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_cp_sync_outbox_model.py -v`
Expected (first run, before Step 3): FAIL — `ModuleNotFoundError`.

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

Migration `backend/alembic/versions/20260726_add_cp_sync_outbox.py` (`down_revision = "20260721_capa_lateral_diffusion"`):

```python
"""add cp_sync_outbox table for durable CP sync on FMEA approval

Revision ID: 20260726_add_cp_sync_outbox
Revises: 20260721_capa_lateral_diffusion
Create Date: 2026-07-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = '20260726_add_cp_sync_outbox'
down_revision: Union[str, None] = '20260721_capa_lateral_diffusion'
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
    op.create_index('idx_cp_sync_outbox_pending', 'cp_sync_outbox', ['next_attempt_at'],
                    postgresql_where=sa.text("status = 'pending'"))


def downgrade() -> None:
    op.drop_index('idx_cp_sync_outbox_pending')
    op.drop_table('cp_sync_outbox')
```

Register in `backend/app/models/__init__.py` (add next to other model imports):

```python
from app.models.cp_sync_outbox import CPSyncOutbox  # noqa: F401
```

- [ ] **Step 4: Run migration + test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key alembic upgrade head && SECRET_KEY=test-secret-key pytest tests/test_cp_sync_outbox_model.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/cp_sync_outbox.py backend/app/models/__init__.py backend/alembic/versions/20260726_add_cp_sync_outbox.py backend/tests/test_cp_sync_outbox_model.py
git commit -m "feat(fmea): CPSyncOutbox model + migration with (fmea_id,fmea_version_id,event_type) unique key"
```

---

## Task P1.8: CP sync applier + durable worker

**Files:**
- Modify: `backend/app/services/control_plan_service.py` (add `apply_cp_sync_pending`)
- Create: `backend/app/services/cp_sync_worker.py`
- Test: `backend/tests/test_cp_sync_worker.py`

**Interfaces:**
- Consumes: `CPSyncOutbox` (Task P1.7), `ControlPlan` (`fmea_ref_id`, `sync_pending`, `cp_id`, `factory_id`, `document_no`, `title` — `models/control_plan.py:12-41`), `AuditLog`.
- Produces:
  - `async def apply_cp_sync_pending(db, outbox, user_id) -> int` in `control_plan_service.py`. For each `ControlPlan` where `fmea_ref_id == outbox.fmea_id` AND `sync_pending == False`: set `sync_pending = True`, write one `AuditLog(table_name="control_plans", record_id=cp.cp_id, action="UPDATE", changed_fields={"sync_pending": "false->true", "trigger_fmea_version_id": str(outbox.fmea_version_id)}, operated_by=user_id)`. Returns count flipped. Already-pending CPs skipped (no audit) → idempotent per `(outbox_id, cp_id)`. Does NOT commit (worker commits with outbox status).
  - `async def process_cp_sync_outbox_batch(db, batch_size: int = 10) -> int` in `cp_sync_worker.py`: poll `pending` due rows `FOR UPDATE SKIP LOCKED`, apply, set `completed`/`processed_at`, commit per row; on exception `attempt_count += 1`, backoff `next_attempt_at`, `last_error`, `status="dead"` if exhausted. `__main__` loop `POLL_INTERVAL = 5`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cp_sync_worker.py
import uuid
import pytest
from sqlalchemy import select
from app.models.audit import AuditLog
from app.models.control_plan import ControlPlan
from app.models.cp_sync_outbox import CPSyncOutbox
from app.models.fmea import FMEADocument
from app.services.control_plan_service import apply_cp_sync_pending
from app.services.cp_sync_worker import process_cp_sync_outbox_batch


async def _mk_fmea_with_cps(db, factory_id, n=2):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-CPS-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=factory_id, status="draft",
        graph_data={"nodes": [], "edges": []}, version=1,
    )
    db.add(fmea)
    cps = []
    for i in range(n):
        cp = ControlPlan(
            cp_id=uuid.uuid4(), document_no=f"CP-{uuid.uuid4().hex[:8]}",
            title=f"cp{i}", fmea_ref_id=fmea.fmea_id,
            product_line_code="DC-DC-100", factory_id=factory_id, sync_pending=False,
        )
        db.add(cp)
        cps.append(cp)
    await db.commit()
    return fmea, cps


@pytest.mark.asyncio
async def test_applier_flips_only_pending_and_audits_each(db, default_factory, admin_user):
    fmea, cps = await _mk_fmea_with_cps(db, default_factory.id, 2)
    version_id = uuid.uuid4()
    outbox = CPSyncOutbox(fmea_id=fmea.fmea_id, fmea_version_id=version_id, payload={})
    n = await apply_cp_sync_pending(db, outbox, admin_user.user_id)
    await db.commit()
    assert n == 2
    audits = (await db.execute(select(AuditLog).where(
        AuditLog.table_name == "control_plans", AuditLog.action == "UPDATE"))).scalars().all()
    assert len(audits) == 2  # 2 + N rule: one per flipped CP
    for a in audits:
        assert a.changed_fields["sync_pending"] == "false->true"
        assert "source_fmea_version_id" not in a.changed_fields
        assert a.changed_fields["trigger_fmea_version_id"] == str(version_id)


@pytest.mark.asyncio
async def test_worker_idempotent_no_duplicate_audit(db, default_factory, admin_user):
    fmea, cps = await _mk_fmea_with_cps(db, default_factory.id, 2)
    db.add(CPSyncOutbox(fmea_id=fmea.fmea_id, fmea_version_id=uuid.uuid4(),
                        payload={"user_id": str(admin_user.user_id)}))
    await db.commit()
    await process_cp_sync_outbox_batch(db)
    await process_cp_sync_outbox_batch(db)  # second run: row already completed
    audits = (await db.execute(select(AuditLog).where(
        AuditLog.table_name == "control_plans", AuditLog.action == "UPDATE"))).scalars().all()
    assert len(audits) == 2  # still exactly one per CP
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_cp_sync_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.cp_sync_worker` and `apply_cp_sync_pending` missing.

- [ ] **Step 3: Write minimal implementation**

In `control_plan_service.py` add (keep `mark_cp_sync_pending_on_fmea_approve` for now — Task P1.9 removes its caller; grep before removing the function):

```python
async def apply_cp_sync_pending(db: AsyncSession, outbox, user_id: uuid.UUID) -> int:
    """Idempotently mark linked CPs sync_pending + audit each flip.

    Only flips CPs currently sync_pending=False; already-pending CPs are skipped
    (no duplicate audit), giving idempotency per (outbox_id, cp_id). Does NOT
    commit — the worker commits atomically with the outbox status."""
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
            record_id=cp.cp_id,
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
import uuid
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
            user_id = uuid.UUID(row.payload["user_id"]) if row.payload.get("user_id") else None
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

> **Note:** `AuditLog.operated_by` is **nullable** (`models/audit.py:25`), so passing `None` when the outbox payload lacks `user_id` is safe; the producer (Task P1.9) always sets `payload.user_id`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_cp_sync_worker.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/control_plan_service.py backend/app/services/cp_sync_worker.py backend/tests/test_cp_sync_worker.py
git commit -m "feat(fmea): CP sync applier + durable outbox worker (idempotent, 2+N audits, sync_pending-only changed_fields)"
```

---

## Task P1.9: Produce CP outbox on approval; remove direct CP call

**Files:**
- Modify: `backend/app/services/fmea_service.py` (`transition_fmea` at `:373-435`)
- Test: `backend/tests/test_transition_cp_outbox.py`

**Interfaces:**
- Consumes: `CPSyncOutbox` (Task P1.7), `version` from `_create_fmea_version_no_commit` (`:398-406`).
- Produces: `transition_fmea` on `APPROVED` writes a `CPSyncOutbox(fmea_id, fmea_version_id=version.version_id, event_type="cp.sync_pending_set", payload={"user_id": str(user_id)})` inside the SAME transaction that commits at `:427`; the direct `mark_cp_sync_pending_on_fmea_approve` call at `:429-432` is removed.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_transition_cp_outbox.py
import uuid
import pytest
from sqlalchemy import select
from app.models.control_plan import ControlPlan
from app.models.cp_sync_outbox import CPSyncOutbox
from app.models.fmea import FMEADocument
from app.services import fmea_service


async def _mk(db, factory_id):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-TR-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=factory_id, status="draft",
        graph_data={"nodes": [], "edges": [], "wizardScope": {"wizard_completed": True}},
        version=1,
    )
    cp = ControlPlan(
        cp_id=uuid.uuid4(), document_no=f"CP-{uuid.uuid4().hex[:8]}",
        title="cp", fmea_ref_id=fmea.fmea_id,
        product_line_code="DC-DC-100", factory_id=factory_id, sync_pending=False,
    )
    db.add_all([fmea, cp])
    await db.commit()
    return fmea, cp


@pytest.mark.asyncio
async def test_approve_enqueues_cp_outbox_and_does_not_set_pending_sync(db, default_factory, admin_user):
    fmea, cp = await _mk(db, default_factory.id)
    # drive draft -> in_review -> approved
    await fmea_service.transition_fmea(db, fmea, "in_review", admin_user.user_id)
    await fmea_service.transition_fmea(db, fmea, "approved", admin_user.user_id)
    rows = (await db.execute(select(CPSyncOutbox).where(
        CPSyncOutbox.fmea_id == fmea.fmea_id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == "cp.sync_pending_set"
    assert rows[0].fmea_version_id is not None
    await db.refresh(cp)
    assert cp.sync_pending is False  # worker has not run


@pytest.mark.asyncio
async def test_submit_does_not_enqueue_cp_outbox(db, default_factory, admin_user):
    fmea, _ = await _mk(db, default_factory.id)
    await fmea_service.transition_fmea(db, fmea, "in_review", admin_user.user_id)
    rows = (await db.execute(select(CPSyncOutbox))).scalars().all()
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_transition_cp_outbox.py -v`
Expected: FAIL — no `CPSyncOutbox` row (and CP set synchronously today).

- [ ] **Step 3: Write minimal implementation**

In `transition_fmea`, move the CP logic to **before** `await db.commit()` (`:427`). Replace the current post-commit block (`:429-432`):

```python
    # (DELETE this post-commit block)
    # if target == FMEAState.APPROVED and version:
    #     from app.services.control_plan_service import mark_cp_sync_pending_on_fmea_approve
    #     await mark_cp_sync_pending_on_fmea_approve(db, fmea.fmea_id, version.version_id)
```

with a pre-commit outbox add placed after the `GraphSyncOutbox` add (`:421-425`) and before `await db.commit()` (`:427`):

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

Then `grep -rn "mark_cp_sync_pending_on_fmea_approve" backend/` — if no other callers remain, remove the now-dead function from `control_plan_service.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_transition_cp_outbox.py -v`
Expected: 2 PASS. Then regression:
Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -k "transition or control_plan" --tb=short`
Expected: no new failures (update any test asserting the old synchronous CP-set).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/fmea_service.py backend/app/services/control_plan_service.py backend/tests/test_transition_cp_outbox.py
git commit -m "feat(fmea): enqueue CPSyncOutbox on approval (durable), drop direct synchronous CP set"
```

---

## Task P1.10: Unified transition gate (rework APPROVE + reason 422 + wizard 422) + editable-state 409

**Files:**
- Modify: `backend/app/api/fmea.py` (`require_approve_permission` at `:190-200`, `transition_fmea` route at `:203-218`, `update_fmea` route at `:111-164`)
- Test: `backend/tests/test_fmea_approval_gates.py`

**Interfaces:**
- Consumes: `TransitionRequest.reason` (Task P1.1), `get_user_permission`/`PermissionLevel`/`Module.FMEA`.
- Produces (per spec "审批权限矩阵" + the N5 EDIT-for-all already in place):
  - `IN_REVIEW→APPROVED`, `IN_REVIEW→REWORK`, `APPROVED→REWORK` → require `APPROVE`.
  - `DRAFT/REWORK→IN_REVIEW` → require `EDIT` (already) + backend-enforced `wizardScope.wizard_completed == true` else **422**.
  - `REWORK` target → require non-empty `reason` else **422**.
  - `PUT /{fmea_id}` on `IN_REVIEW/APPROVED/ARCHIVED` → **409**; only `DRAFT/REWORK` editable.

> **Note on N5 merge:** the N5 fix (`b5b907fe`) made `require_approve_permission` = EDIT-for-all + APPROVE-only-for-`approved`. The spec additionally requires `rework` targets to need APPROVE and a non-empty reason. This task **extends** that dependency (rename it `require_transition_permission` for clarity) and adds the reason/wizard gates — it does NOT re-open the EDIT-for-all decision. The existing `test_fmea_transition_permissions.py` must stay green (it asserts draft→in_review needs EDIT, approved needs APPROVE).

- [ ] **Step 1: Write the failing test**

The `perm_client_builder` fixture is **local to** `backend/tests/fmea/test_fmea_transition_permissions.py:34-51` (not in conftest). Copy it verbatim into this new file. Its `_build` signature is `_build(fmea_level: int)` (keyword `fmea_level`, NOT a module-name first arg) — call `await perm_client_builder(fmea_level=3)` for EDIT, `fmea_level=4` for APPROVE. The `_mk` helper below seeds the FMEA + `wizardScope` (the N5 `_make_fmea` has no `wizardScope`, so don't reuse it — `wizard_completed` must be controllable).

```python
# backend/tests/test_fmea_approval_gates.py
"""审批闭环门禁（spec「审批权限矩阵」）。

权限级别：NONE=0/VIEW=1/CREATE=2/EDIT=3/APPROVE=4/ADMIN=5。
perm_client_builder 复制自 tests/fmea/test_fmea_transition_permissions.py:34-51。
"""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.core.deps import get_current_user, get_db, get_request_scope
from app.main import app
from app.models.fmea import FMEADocument
from app.models.role import RolePermission
from tests.conftest import _scope_for

pytestmark = pytest.mark.requires_db


@pytest.fixture
async def perm_client_builder(db, admin_user, default_factory):
    """工厂：按指定 fmea 权限级别构造 AsyncClient（复制自 test_fmea_transition_permissions.py）。"""
    async def _build(fmea_level: int):
        existing = (await db.execute(select(RolePermission).where(
            RolePermission.role_id == admin_user.role_id, RolePermission.module == "fmea"))).scalar_one_or_none()
        if existing is None:
            db.add(RolePermission(role_id=admin_user.role_id, module="fmea", permission_level=fmea_level))
        else:
            existing.permission_level = fmea_level
        await db.flush()
        scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_request_scope] = lambda: scope
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield _build
    app.dependency_overrides.clear()


async def _mk(db, factory_id, user_id, status, wizard_done=True):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-GATE-{uuid.uuid4().hex[:6]}",
        fmea_type="PFMEA", title="t", product_line_code="DC-DC-100",
        factory_id=factory_id, status=status,
        graph_data={"nodes": [], "edges": [],
                    "wizardScope": {"wizard_completed": wizard_done}},
        version=1, created_by=user_id,
    )
    db.add(fmea)
    await db.commit()
    return fmea


@pytest.mark.asyncio
async def test_edit_cannot_rework(perm_client_builder, db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "in_review")
    client = await perm_client_builder(fmea_level=3)  # EDIT, not APPROVE
    resp = await client.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "rework", "reason": "x"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rework_requires_nonempty_reason(perm_client_builder, db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "in_review")
    client = await perm_client_builder(fmea_level=4)  # APPROVE
    resp = await client.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "rework", "reason": "  "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_requires_wizard_completed(perm_client_builder, db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "draft", wizard_done=False)
    client = await perm_client_builder(fmea_level=3)  # EDIT
    resp = await client.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "in_review"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_rejected_when_in_review(perm_client_builder, db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "in_review")
    client = await perm_client_builder(fmea_level=3)
    resp = await client.put(f"/api/fmea/{fmea.fmea_id}", json={"title": "新标题"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_approved_to_rework_keeps_approved_by(perm_client_builder, db, default_factory, admin_user):
    fmea = await _mk(db, default_factory.id, admin_user.user_id, "approved")
    client = await perm_client_builder(fmea_level=4)
    resp = await client.post(f"/api/fmea/{fmea.fmea_id}/transition",
                             json={"target_status": "rework", "reason": "复审"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rework"
    assert resp.json()["approved_by"] is not None  # 保留历史，不清空
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_approval_gates.py -v`
Expected: FAIL — EDIT can rework today, no reason/wizard gate, PUT allowed on IN_REVIEW.

- [ ] **Step 3: Write minimal implementation**

Rename `require_approve_permission` → `require_transition_permission` and extend it (`:190-200`):

```python
async def require_transition_permission(
    req: TransitionRequest,
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
) -> RequestScope:
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 EDIT 权限")
    if req.target_status in ("approved", "rework") and level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="审批权限不足")
    if req.target_status == "rework" and not (req.reason and req.reason.strip()):
        raise HTTPException(status_code=422, detail="驳回必须携带非空 reason")
    return scope
```

Update the transition route dependency (`:208`) to `Depends(require_transition_permission)`, and add the wizard gate after the factory checks (`:213`):

```python
    if req.target_status == "in_review":
        wizard_scope = (fmea.graph_data or {}).get("wizardScope") or {}
        if wizard_scope.get("wizard_completed") is not True:
            raise HTTPException(status_code=422, detail="向导未完成，不能提交评审")
```

In `update_fmea` route (`:121-129`, after the factory checks), add the editable-state guard:

```python
    if fmea.status not in ("draft", "rework"):
        raise HTTPException(status_code=409, detail="当前状态不可编辑（仅草稿/返工可编辑）")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_fmea_approval_gates.py tests/fmea/test_fmea_transition_permissions.py -v`
Expected: all PASS (new 5 + existing N5 4 stay green). Then regression:
Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -k "fmea" --tb=short`
Expected: no new failures beyond the 2 known pre-existing drift failures in `test_fmea_update_core.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/fmea.py backend/tests/test_fmea_approval_gates.py
git commit -m "feat(fmea): unified transition gate — rework APPROVE + reason 422 + wizard_completed 422 + editable-state 409"
```

---

# PHASE 2 — Frontend adoption wiring

Goal: a suggestion selection in the editor / PFMEA wizard / DFMEA wizard produces a `RecommendationAdoption` that rides the next save's `updateFMEA` payload as `adoptions`, so the backend writes the `ADOPT_RECOMMENDATION` audit (Phase-1 Task P1.6). `field_id` = the graph node id the suggestion was applied to.

## Task P2.1: Frontend types — widen Suggestion.source + recommendation_id + RecommendationAdoption

**Files:**
- Modify: `frontend/src/api/recommendation.ts`
- Modify: `frontend/src/api/fmea.ts`
- Test: `frontend/src/api/__tests__/adoption-types.test.ts` (new; type-level + a runtime helper test)

**Interfaces:**
- Consumes: existing `Suggestion` (`api/recommendation.ts:3`), `updateFMEA` (`api/fmea.ts:32`).
- Produces:
  - `Suggestion.source` widened to `"rule" | "graph" | "semantic_search" | "lessons_learned" | "llm"`.
  - `Suggestion.recommendation_id?: string`.
  - `interface RecommendationAdoption { field_id: string; recommendation_id: string; source: string; stage_index: number; adopted_text: string }` (export from `api/fmea.ts`).
  - `updateFMEA(id, data)` `data` gains `adoptions?: RecommendationAdoption[]`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/api/__tests__/adoption-types.test.ts
import { describe, it, expect } from "vitest";
import type { Suggestion } from "../recommendation";
import type { RecommendationAdoption } from "../fmea";

describe("adoption types", () => {
  it("Suggestion supports the 5 sources + recommendation_id", () => {
    const s: Suggestion = {
      name: "焊接电流不足", confidence: 0.8,
      source: "semantic_search", explanation: "",
      recommendation_id: "rec_abc123",
    };
    expect(s.recommendation_id).toBe("rec_abc123");
    expect(s.source).toBe("semantic_search");
  });

  it("RecommendationAdoption shape", () => {
    const a: RecommendationAdoption = {
      field_id: "fm_node_1", recommendation_id: "rec_abc123",
      source: "graph", stage_index: 0, adopted_text: "焊接电流不足",
    };
    expect(a.field_id).toBe("fm_node_1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/api/__tests__/adoption-types.test.ts`
Expected: FAIL — `recommendation_id` / 5-source / `RecommendationAdoption` not exported (TS error surfaces in vitest via esbuild type strip → use a runtime assertion that doesn't depend on the missing types, OR rely on `tsc --noEmit` in Step 4). Simplest: make the test construct plain objects and assert the helper below.

- [ ] **Step 3: Write minimal implementation**

In `api/recommendation.ts`, widen the `source` union and add `recommendation_id`:

```ts
export interface Suggestion {
  name: string;
  confidence: number;
  source: "rule" | "graph" | "semantic_search" | "lessons_learned" | "llm";
  explanation: string;
  recommendation_id?: string;
  source_fmea_id?: string;
  // ... (rest unchanged)
}
```

In `api/fmea.ts`, add the type + widen `updateFMEA`:

```ts
export interface RecommendationAdoption {
  field_id: string;
  recommendation_id: string;
  source: string;
  stage_index: number;
  adopted_text: string;
}

export async function updateFMEA(
  id: string,
  data: {
    title?: string;
    graph_data?: GraphData;
    lock_version?: number;
    confirmed_latest_lock_version?: number;
    adoptions?: RecommendationAdoption[];
  }
): Promise<FMEADocument> {
  const resp = await client.put(`/fmea/${id}`, data);
  return resp.data;
}
```

- [ ] **Step 4: Run test + type gate to verify it passes**

Run: `cd frontend && npx vitest run src/api/__tests__/adoption-types.test.ts && npm run build`
Expected: vitest PASS; `tsc --noEmit` clean (the widened source union must not break `SmartSuggestionDropdown`'s `SourceTag`/`sourceIcon`, which currently only special-case graph/rule/llm — they fall through to `null`/default icon for the 2 new sources, which is acceptable; do NOT add new tag branches unless a test needs it).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/recommendation.ts frontend/src/api/fmea.ts frontend/src/api/__tests__/adoption-types.test.ts
git commit -m "feat(fmea-frontend): widen Suggestion.source (5) + recommendation_id; add RecommendationAdoption; updateFMEA adoptions"
```

---

## Task P2.2: useWizardSave — accept + forward adoptions

**Files:**
- Modify: `frontend/src/hooks/useWizardSave.ts`
- Test: `frontend/src/hooks/useWizardSave.adoptions.test.tsx` (new)

**Interfaces:**
- Consumes: `updateFMEA` with `adoptions` (Task P2.1), existing `enqueueSave`/`immediateSave`.
- Produces: `enqueueSave(graphData, title, dataHash, adoptions?)` and `immediateSave(graphData, title, dataHash, adoptions?)` — new optional trailing param forwarded to `updateFMEA`. When omitted/empty, no `adoptions` key is sent.

- [ ] **Step 1: Write the failing test**

Mock `../api/fmea`'s `updateFMEA` and assert the adoptions array is forwarded:

```tsx
// frontend/src/hooks/useWizardSave.adoptions.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useWizardSave } from "./useWizardSave";
import * as fmeaApi from "../api/fmea";

vi.mock("../api/fmea", () => ({
  updateFMEA: vi.fn(async (_id: string, _data: unknown) => ({ lock_version: 2, version: 2 })),
}));

const graph = { nodes: [], edges: [] } as never;

describe("useWizardSave adoptions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("forwards adoptions to updateFMEA", async () => {
    const { result } = renderHook(() => useWizardSave({ fmeaId: "f1" }));
    const adoptions = [{
      field_id: "fm1", recommendation_id: "rec_1", source: "graph",
      stage_index: 0, adopted_text: "焊接电流不足",
    }];
    await act(async () => {
      await result.current.immediateSave(graph, "t", "h", adoptions);
    });
    expect(fmeaApi.updateFMEA).toHaveBeenCalledWith(
      "f1",
      expect.objectContaining({ adoptions }),
    );
  });

  it("omits adoptions key when not provided", async () => {
    const { result } = renderHook(() => useWizardSave({ fmeaId: "f1" }));
    await act(async () => {
      await result.current.immediateSave(graph, "t", "h");
    });
    const data = (fmeaApi.updateFMEA as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect("adoptions" in data).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/useWizardSave.adoptions.test.tsx`
Expected: FAIL — `immediateSave` takes ≤3 args; `updateFMEA` not called with `adoptions`.

- [ ] **Step 3: Write minimal implementation**

In `useWizardSave.ts`, import the type and thread an optional `adoptions` param through `enqueueSave` → `updateFMEA`, and through `immediateSave`:

```ts
import { updateFMEA, type RecommendationAdoption } from '../api/fmea';

// enqueueSave signature gains a trailing optional param:
const enqueueSave = useCallback(async (
  graphData: GraphData,
  title?: string,
  dataHash?: string,
  adoptions?: RecommendationAdoption[],
): Promise<boolean> => {
  // ...
  const resp = await updateFMEA(fmeaId, {
    ...(title ? { title } : {}),
    graph_data: graphData,
    lock_version: lockVersionRef.current,
    ...(adoptions && adoptions.length ? { adoptions } : {}),
  });
  // ...
}, [fmeaId, onConflict, safeSetStatus]);

// immediateSave forwards it:
const immediateSave = useCallback(async (
  graphData: GraphData,
  title?: string,
  dataHash?: string,
  adoptions?: RecommendationAdoption[],
): Promise<boolean> => {
  // ... cancel debounce ...
  return await enqueueSave(graphData, title, dataHash, adoptions);
}, [enqueueSave]);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/hooks/ && npm run build`
Expected: PASS; existing `useWizardSave`/`useWizardValidation` tests stay green; `tsc --noEmit` clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useWizardSave.ts frontend/src/hooks/useWizardSave.adoptions.test.tsx
git commit -m "feat(fmea-frontend): useWizardSave accepts + forwards adoptions to updateFMEA"
```

---

## Task P2.3: Editor adoption capture (FMEAEditorPage)

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx`
- Test: `frontend/src/pages/planning/fmea/FMEAEditorPage.adoptions.test.tsx` (new)

**Interfaces:**
- Consumes: `SmartSuggestionDropdown.onSelect: (suggestion: Suggestion) => void` (`components/dfmea/SmartSuggestionDropdown.tsx:16`), `updateFMEA` with `adoptions` (Task P2.1).
- Produces: when a user picks a suggestion in the editor, the page builds a `RecommendationAdoption { field_id: <target graph node id>, recommendation_id: suggestion.recommendation_id, source: suggestion.source, stage_index: 0, adopted_text: suggestion.name }` and includes it (deduped by `recommendation_id`) in the `updateFMEA` payload for that save.

> **Note for implementer:** `FMEAEditorPage` calls `updateFMEA` directly (not via `useWizardSave`). Locate the `SmartSuggestionDropdown` usage(s) and the save call. Add a `useRef<RecommendationAdoption[]>` (or state) accumulating adoptions; in the `onSelect` handler, push the new adoption (replacing any existing entry with the same `recommendation_id`); on save, pass `adoptions` and clear the accumulator after a successful save. `field_id` is the id of the node being edited at that cell. Keep the change minimal — this is wiring, not a redesign of the editor's save flow.

- [ ] **Step 1: Write the failing test**

Render the editor (mirror the existing `FMEAEditorPage.test.tsx` setup/mocks), simulate a suggestion `onSelect`, trigger a save, assert `updateFMEA` received the matching `adoptions` entry with the right `field_id`/`recommendation_id`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorPage.adoptions.test.tsx`
Expected: FAIL — `updateFMEA` not called with `adoptions`.

- [ ] **Step 3: Write minimal implementation**

Wire the accumulator + `onSelect` + save pass-through as described above.

- [ ] **Step 4: Run test + build to verify it passes**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/ && npm run build`
Expected: PASS; existing editor tests stay green; `tsc --noEmit` clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx frontend/src/pages/planning/fmea/FMEAEditorPage.adoptions.test.tsx
git commit -m "feat(fmea-frontend): editor captures AI suggestion adoption into updateFMEA.adoptions"
```

---

## Task P2.4: Wizard adoption capture (PFMEA + DFMEA)

**Files:**
- Modify: `frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx`
- Modify: `frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx`
- Test: `frontend/src/pages/planning/fmea/PFMEAWizardPage.adoptions.test.tsx` (new)

**Interfaces:**
- Consumes: `useWizardSave` with `adoptions` (Task P2.2), `SmartSuggestionDropdown.onSelect` (and any wizard-specific suggestion fields — `ScopeTagField`, `EffectLinesEditor`).
- Produces: PFMEA and DFMEA wizards accumulate `RecommendationAdoption` on suggestion select and pass them through their `immediateSave`/`debouncedSave` calls. `field_id` = the graph node id the suggestion was applied to.

> **Note for implementer:** the two wizards use `useWizardSave` (which now accepts adoptions). Add the same accumulator pattern as Task P2.3, pass `adoptions` on the wizard's save, and clear on success. Keep it symmetric between the two pages. If a wizard's suggestion field is nested (`ScopeTagField`/`EffectLinesEditor`), thread an `onAdopt` callback up — do NOT reach into child component state.

- [ ] **Step 1: Write the failing test**

Render the PFMEA wizard (mirror `PFMEAWizardPage.test.tsx`), simulate a suggestion adoption, trigger save, assert the save path forwarded `adoptions`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/PFMEAWizardPage.adoptions.test.tsx`
Expected: FAIL — save not called with `adoptions`.

- [ ] **Step 3: Write minimal implementation**

Wire accumulator + `onSelect`/`onAdopt` + save pass-through on both wizard pages.

- [ ] **Step 4: Run test + build to verify it passes**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/ && npm run build`
Expected: PASS; existing wizard tests stay green; `tsc --noEmit` clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/planning/fmea/PFMEAWizardPage.tsx frontend/src/pages/planning/fmea/DFMEAWizardPage.tsx frontend/src/pages/planning/fmea/PFMEAWizardPage.adoptions.test.tsx
git commit -m "feat(fmea-frontend): PFMEA + DFMEA wizards capture AI suggestion adoption into save payload"
```

---

## Sequencing & Dependencies

```
Phase 1 (backend):
P1.1 (schemas) ──┬─> P1.5 (adoption audit) ──> P1.6 (status + update_fmea hook)
                 └─> P1.10 (transition gates, uses TransitionRequest.reason)
P1.2 (observability + recommendation_id) ──> P1.3 (retrievers) ──> P1.4 (wire into recommend + embedding)
P1.7 (CPSyncOutbox) ──> P1.8 (worker+applier) ──> P1.9 (producer in transition)

Phase 2 (frontend, after Phase 1 backend contract is green):
P2.1 (types) ──> P2.2 (useWizardSave) ──> P2.4 (wizards)
P2.1 (types) ──> P2.3 (editor)         [editor calls updateFMEA directly, independent of P2.2]
```

Recommended order: **Phase 1**: P1.1 → P1.2 → P1.3 → P1.4 → P1.5 → P1.6 → P1.7 → P1.8 → P1.9 → P1.10. Hard chains: P1.1→(P1.5,P1.6,P1.10), P1.2→P1.3→P1.4, P1.7→P1.8→P1.9. **Phase 2** (only after Phase 1 backend green): P2.1 → P2.2 → P2.3 → P2.4. Then one full verify-fmea-lifecycle walk.

## Definition of Done

- **Phase 1:** all new + existing backend tests pass: `cd backend && SECRET_KEY=test-secret-key pytest tests/ --tb=short` (allowing only the 2 known pre-existing `test_fmea_update_core.py` drift failures). `alembic upgrade head` clean on a fresh DB.
- **Phase 1 contract:** recommend returns `source_executions` (graph/semantic_search/lessons_learned) + `context_execution` + `generation_execution`; suggestions carry `recommendation_id`; PUT with `adoptions` writes `ADOPT_RECOMMENDATION` (idempotent); transition gate enforces rework-APPROVE/reason-422/wizard-422; PUT on IN_REVIEW/APPROVED → 409; approval enqueues `CPSyncOutbox` (no synchronous CP set); CP worker flips `sync_pending` idempotently with correct `changed_fields`.
- **Phase 2:** `cd frontend && npm run build` clean (`tsc --noEmit` + vite build); new vitest files pass; existing editor/wizard/hook tests stay green; a suggestion select in editor + both wizards produces a `RecommendationAdoption` forwarded on save.
- **Final:** one full `verify-fmea-lifecycle` walk re-run reaches **all-PASS** (the D1–D9-driven FAIL/MISSING items now pass).
