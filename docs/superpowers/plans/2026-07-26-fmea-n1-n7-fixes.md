# FMEA N1–N7 Acceptance-Defect Fixes Implementation Plan

> **Implementation status (2026-09-05): COMPLETED and merged via PR #16.**
> The checkboxes below are preserved as the original execution plan, not as current work.
> N1 `5145e017`; N2 `7b36a973`; N5 `b5b907fe`; N4/N7 `fef560d4`;
> N6 `0af30f5c`; N3 clarification `3bf9ad1f`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 7 defects (N1–N7) discovered during the US-E2E-02 FMEA-lifecycle acceptance walk, so the FMEA approval cycle works end-to-end, editor save no longer destroys wizard metadata, the transition endpoint enforces edit permission, and collaboration presence works.

**Architecture:** Each defect is a small, independent, surgical fix with its own failing-test-first cycle. N1/N2 are one-line "pass the missing `factory_id`" bugs. N4 is a frontend contract fix (send full `graph_data` including `wizardScope`) plus a backend safety net (reject updates that would drop required metadata on a completed doc). N5 is a one-line RBAC check. N6 is a frontend Popover-trigger fix. N7 is a downstream symptom of N4 and is verified, not separately coded. N3 is **not a product defect** — it is a spec/skill endpoint-wording clarification (verify-only, no product code).

**Tech Stack:** FastAPI 0.115 (async) + SQLAlchemy 2.0 (async) + Pydantic v2 · React 18 + TS 5.6 + Ant Design 5.29 · pytest (backend) + vitest (frontend) · PostgreSQL 15.

## Global Constraints

- **Branch:** `fix/fmea-fixes`. Do NOT work on `main`.
- **Backend tests:** `cd backend && SECRET_KEY=test-secret-key pytest tests/ -x --tb=short`. Targeted file: `SECRET_KEY=test-secret-key pytest tests/<file> -x --tb=short`.
- **Frontend tests:** `cd frontend && npx vitest run <file>`. Type+build gate: `npm run build` (runs `tsc --noEmit` + vite build).
- **Surgical changes only** (CLAUDE.md §3): touch only what the defect requires; match existing style; do not refactor adjacent code.
- **`factory_id` is NOT NULL on all business tables** (CLAUDE.md) — N1/N2 fixes must *populate* it, never relax the constraint.
- **Services raise `ValueError`; the API layer converts to `HTTPException`** (CLAUDE.md).
- **Docs sync** (CLAUDE.md §5): after changing `backend/app/` or `frontend/src/`, check whether `docs/`, `CLAUDE.md`, or a module `README.md` needs an update; update in the same change or note `docs-not-needed`. These are internal bugfixes with no architecture/API-surface doc change expected — state that justification in each commit if no doc touched.
- **N3 requires no product code.** It is resolved by confirming the real endpoint and annotating the finding; see Task 6.
- Keep the existing E2E report (`docs/e2e/reports/US-E2E-02-2026-07-25/`) untouched — it is a historical record of the walk. Do not edit it to claim the defects are fixed.

## Defect → Fix Map

| # | Sev | Root cause (verified) | Fix | Task |
|---|-----|----------------------|-----|------|
| N1 | blocker | `version_service.py:135` `FMEAVersion(...)` omits `factory_id` → NOT NULL violation → submit/approve 500 | pass `factory_id=fmea.factory_id` | 1 |
| N2 | high | `collaboration_service.upsert_session` never sets NOT NULL `CollaborationSession.factory_id` → heartbeat 500 → permanent "sync failed" | resolve doc's factory, pass through | 2 |
| N5 | security | `require_approve_permission` (`api/fmea.py:190`) only checks APPROVE when `target=="approved"`; no EDIT gate → viewer can transition | require EDIT for all transitions, APPROVE additionally for `approved` | 3 |
| N4 | high | editor `save`/force-save send `graph_data:{nodes,edges}` (drops `wizardScope`); backend overwrites wholesale → wizard metadata lost | frontend sends full `graph_data` incl. `wizardScope`; backend rejects metadata-dropping update on completed doc | 4 |
| N7 | med | editor renders "No data" when `wizardScope` wiped — downstream of N4 | no new code; verified by Task 4 regression test | 4 |
| N3 | — | walk probed `/api/collaboration/online` (404); real presence endpoint is `/{type}/{id}/active-users` (exists, wired) | verify-only: confirm + annotate finding; no product code | 6 |
| N6 | med | RiskTable severity `Popover` fails to open on click (playwright) | make Popover a controlled component driven by the button's click | 5 |

---

## Task 1: N1 — FMEAVersion missing `factory_id` (blocker)

**Files:**
- Modify: `backend/app/services/version_service.py:135-145`
- Test: `backend/tests/fmea/test_fmea_version_factory_id.py` (create)

**Interfaces:**
- Consumes: `_create_fmea_version_no_commit(db, fmea, change_type, change_summary, user_id)` (existing; called from `fmea_service.transition_fmea` and `version_service.create_fmea_version`).
- Produces: a persisted `FMEAVersion` whose `factory_id == fmea.factory_id` (no signature change).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/fmea/test_fmea_version_factory_id.py`. `_make_fmea` is a module-level helper in `backend/tests/fmea/test_fmea_update_core.py` (not exported for reuse) — copy it verbatim into this new file. Fixtures `db`, `default_factory`, `admin_user` come from the repo's `conftest.py`.

```python
import uuid
import pytest
from sqlalchemy import select

from app.models.fmea import FMEADocument
from app.models.fmea_version import FMEAVersion
from app.services.version_service import create_fmea_version

pytestmark = pytest.mark.requires_db


async def _make_fmea(db, factory_id, user_id, graph=None):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-VER-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=factory_id,
        status="draft", created_by=user_id, graph_data=graph or {"nodes": [], "edges": []},
    )
    db.add(fmea); await db.flush()
    return fmea


@pytest.mark.asyncio
async def test_fmea_version_carries_factory_id(db, default_factory, admin_user):
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id,
                            graph={"nodes": [], "edges": []})
    version = await create_fmea_version(db, fmea, "submit", "提交评审", admin_user.user_id)
    assert version.factory_id == default_factory.id

    # round-trip from DB to prove the column is populated, not just the ORM object
    row = (await db.execute(
        select(FMEAVersion).where(FMEAVersion.version_id == version.version_id)
    )).scalar_one()
    assert row.factory_id == default_factory.id
```

> `FMEADocument` is imported from `app.models.fmea` (as in `test_fmea_update_core.py`). Use the same `pytestmark = pytest.mark.requires_db` so the test is gated exactly like its neighbors.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/fmea/test_fmea_version_factory_id.py -x --tb=short`
Expected: FAIL — `IntegrityError`/`NOT NULL violation` on `fmea_versions.factory_id` (or `version.factory_id is None`/attribute mismatch) because `factory_id` is not passed.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/version_service.py`, inside `_create_fmea_version_no_commit`, add `factory_id=fmea.factory_id` to the `FMEAVersion(...)` constructor (around line 135):

```python
    version = FMEAVersion(
        version_id=uuid.uuid4(),
        fmea_id=fmea.fmea_id,
        factory_id=fmea.factory_id,
        major_no=major_no,
        minor_no=minor_no,
        snapshot=snapshot,
        sha256_hash=sha256_hash,
        change_summary=change_summary,
        change_type=change_type,
        created_by=user_id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/fmea/test_fmea_version_factory_id.py -x --tb=short`
Expected: PASS

- [ ] **Step 5: Run the version + transition suites**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/fmea/ -x --tb=short`
Expected: PASS (no regressions in version/transition/update tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/version_service.py backend/tests/fmea/test_fmea_version_factory_id.py
git commit -m "fix(fmea): populate FMEAVersion.factory_id on snapshot (N1) — submit/approve 500 NOT NULL violation. docs-not-needed: internal bugfix, no API/architecture change"
```

---

## Task 2: N2 — Collaboration heartbeat missing `factory_id`

**Files:**
- Modify: `backend/app/services/collaboration_service.py:13-45`
- Modify: `backend/app/api/collaboration.py:15-29` (resolve factory, pass to service)
- Test: `backend/tests/test_collaboration.py` (extend)

**Interfaces:**
- Consumes: `upsert_session(db, document_type, document_id, user_id, user_name, action, editing_area)`; `CollaborationSession.factory_id` (NOT NULL, FK `factories.id`).
- Produces: `upsert_session(..., factory_id: uuid.UUID)` — new required keyword param; heartbeat resolves the document's factory and passes it. Presence (`get_active_users`) is unchanged.

The session's `factory_id` must equal the owning document's factory. For `document_type == "fmea"` the source is `FMEADocument.factory_id`. Only `fmea` (and CP, which shares the editor) use collaboration today; resolve via a small lookup and raise `ValueError("document_not_found")` when the document does not exist (API converts to 404).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_collaboration.py`. Note: this file currently mocks the DB session (`AsyncMock`) for the pure-service tests, but it also has real-DB FMEA tests (`test_fmea_lock_version_mismatch`, etc.) that use the real `db` fixture. Write the new test against the **real** `db` fixture and construct an `FMEADocument` inline (same pattern as `_make_fmea` in `test_fmea_update_core.py`):

```python
import pytest
from sqlalchemy import select

from app.models.collaboration_session import CollaborationSession
from app.models.fmea import FMEADocument
from app.services import collaboration_service


@pytest.mark.asyncio
async def test_heartbeat_session_carries_factory_id(db, default_factory, admin_user):
    fmea = FMEADocument(
        fmea_id=uuid.uuid4(), document_no=f"PFMEA-COLLAB-{uuid.uuid4().hex[:6]}", title="t",
        fmea_type="PFMEA", product_line_code="DC-DC-100", factory_id=default_factory.id,
        status="draft", created_by=admin_user.user_id, graph_data={"nodes": [], "edges": []},
    )
    db.add(fmea); await db.flush()

    await collaboration_service.upsert_session(
        db,
        document_type="fmea",
        document_id=fmea.fmea_id,
        user_id=admin_user.user_id,
        user_name="admin",
        action="viewing",
        editing_area=None,
        factory_id=fmea.factory_id,
    )
    row = (await db.execute(
        select(CollaborationSession).where(
            CollaborationSession.document_id == fmea.fmea_id,
            CollaborationSession.user_id == admin_user.user_id,
        )
    )).scalar_one()
    assert row.factory_id == default_factory.id
```

> `uuid` and `pytest` are already imported at the top of `test_collaboration.py`. Add `from sqlalchemy import select`, `from app.models.fmea import FMEADocument` if not present. If the real-DB tests in this file are gated by a marker (e.g. `pytest.mark.requires_db`) or fixtures differ, match that gating.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_collaboration.py -x --tb=short`
Expected: FAIL — `TypeError: upsert_session() got an unexpected keyword argument 'factory_id'` (and, without it, a NOT NULL violation on insert).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/collaboration_service.py`, add `factory_id` to the signature and to both the insert `values(...)` and the `on_conflict_do_update` `set_` (so a session that somehow exists under a different factory is corrected):

```python
async def upsert_session(
    db: AsyncSession,
    document_type: str,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    user_name: str,
    action: str,
    editing_area: dict | None,
    factory_id: uuid.UUID,
) -> None:
    """Upsert collaboration session on heartbeat."""
    stmt = (
        insert(CollaborationSession)
        .values(
            document_type=document_type,
            document_id=document_id,
            user_id=user_id,
            user_name=user_name,
            action=action,
            editing_area=editing_area,
            last_activity=datetime.now(UTC),
            factory_id=factory_id,
        )
        .on_conflict_do_update(
            index_elements=["document_type", "document_id", "user_id"],
            set_={
                "user_name": user_name,
                "action": action,
                "editing_area": editing_area,
                "last_activity": datetime.now(UTC),
                "factory_id": factory_id,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()
```

In `backend/app/api/collaboration.py` `heartbeat`, resolve the document's factory before calling the service. Add a helper in the service (or inline) that loads the FMEA and returns its `factory_id`:

```python
# collaboration_service.py
from app.models.fmea_document import FMEADocument

async def resolve_document_factory_id(
    db: AsyncSession, document_type: str, document_id: uuid.UUID
) -> uuid.UUID:
    if document_type == "fmea":
        factory_id = await db.scalar(
            select(FMEADocument.factory_id).where(FMEADocument.fmea_id == document_id)
        )
        if factory_id is None:
            raise ValueError("document_not_found")
        return factory_id
    raise ValueError("unsupported_document_type")
```

```python
# api/collaboration.py heartbeat
    try:
        factory_id = await collaboration_service.resolve_document_factory_id(
            db, req.document_type, req.document_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await collaboration_service.upsert_session(
        db,
        document_type=req.document_type,
        document_id=req.document_id,
        user_id=user.user_id,
        user_name=user.display_name or user.username,
        action=req.action,
        editing_area=req.editing_area.model_dump() if req.editing_area else None,
        factory_id=factory_id,
    )
```

> Confirm the FMEA model import path (`app.models.fmea_document` vs the actual module) and the `HTTPException` import in `api/collaboration.py` (add `from fastapi import HTTPException` if absent). Match the model's real table/PK names.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_collaboration.py -x --tb=short`
Expected: PASS (new test + existing collaboration tests, including any heartbeat 500 regression now gone).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/collaboration_service.py backend/app/api/collaboration.py backend/tests/test_collaboration.py
git commit -m "fix(collab): populate CollaborationSession.factory_id on heartbeat (N2) — 500 on upsert. docs-not-needed: internal bugfix, no API/architecture change"
```

---

## Task 3: N5 — Transition endpoint missing EDIT check (security)

**Files:**
- Modify: `backend/app/api/fmea.py:190-199`
- Test: `backend/tests/fmea/test_fmea_transition_permissions.py` (create)

**Interfaces:**
- Consumes: `require_approve_permission(req, scope, db)` dependency; `get_user_permission(user, Module.FMEA, db)`; `PermissionLevel.EDIT` / `PermissionLevel.APPROVE`.
- Produces: every transition requires ≥ EDIT; `target_status == "approved"` additionally requires ≥ APPROVE. No change to `transition_fmea` service.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/fmea/test_fmea_transition_permissions.py`. The cleanest end-to-end check is through the API route (`POST /api/fmea/{id}/transition`), which is exactly what N5 exploited — exercise it with the repo's HTTP test client + auth helpers. **First, find an existing API-level permission test to copy the harness from** (search `backend/tests` for a test that builds users with different `RolePermission.permission_level` values and calls a protected route, e.g. `grep -rln "permission_level\|RolePermission\|403" backend/tests`). Mirror that construction.

Two security-relevant assertions:

```python
# Case A: a user with only VIEW (PermissionLevel 1) on module fmea
#         POST /api/fmea/{id}/transition {target_status:"in_review"}  -> 403
#         (today: succeeds — the privilege escalation)
# Case B: a user with EDIT (2) but not APPROVE on module fmea
#         POST /api/fmea/{id}/transition {target_status:"approved"}   -> 403
# Positive control: a user with EDIT submits (draft->in_review) -> 200,
#                   a user with APPROVE approves (in_review->approved) -> 200.
```

> The FMEA document must be `factory_id = <the user's factory>` and `status="draft"` (Case A) / `"in_review"` (Case B) so the state machine permits the transition — the point is the *permission* gate, not the state gate. Use the real `db` + `default_factory` fixtures and build the target users with the same `RolePermission` rows the existing permission tests use.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/fmea/test_fmea_transition_permissions.py -x --tb=short`
Expected: FAIL — Case A currently passes (viewer can transition) proving the escalation.

- [ ] **Step 3: Write minimal implementation**

Rewrite `require_approve_permission` in `backend/app/api/fmea.py`:

```python
async def require_approve_permission(
    req: TransitionRequest,
    scope: RequestScope = Depends(get_request_scope),
    db: AsyncSession = Depends(get_db),
) -> RequestScope:
    level = await get_user_permission(scope.user, Module.FMEA, db)
    if level < PermissionLevel.EDIT:
        raise HTTPException(status_code=403, detail="需要 fmea 模块的 EDIT 权限")
    if req.target_status == "approved" and level < PermissionLevel.APPROVE:
        raise HTTPException(status_code=403, detail="审批权限不足")
    return scope
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/fmea/test_fmea_transition_permissions.py -x --tb=short`
Expected: PASS

- [ ] **Step 5: Run the FMEA API suites**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/fmea/ -x --tb=short`
Expected: PASS (no regression — legitimate editor/manager transitions still allowed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/fmea.py backend/tests/fmea/test_fmea_transition_permissions.py
git commit -m "fix(fmea): require EDIT for all transitions, APPROVE for approve (N5) — privilege escalation. docs-not-needed: security bugfix, no API-contract change beyond enforcing documented RBAC"
```

---

## Task 4: N4 + N7 — Editor save drops `wizardScope` (data loss)

**Files:**
- Modify: `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx:565-573` (`save`) and `:627-640` (`handleConflictForceSave`)
- Modify: `backend/app/services/fmea_service.py:238-244` (safety net)
- Test: `frontend/src/pages/planning/fmea/FMEAEditorPage.test.tsx` (extend or create; see existing wizard/editor tests for the render harness)
- Test: `backend/tests/fmea/test_fmea_update_core.py` (extend)

**Interfaces:**
- Consumes: `updateFMEA(id, { title, graph_data, lock_version, confirmed_latest_lock_version? })`; `doc.graph_data.wizardScope` (loaded at `:413-419`); backend `_apply_fmea_update`.
- Produces: the PUT body always carries the full `graph_data` (`{ nodes, edges, wizardScope }`), so the backend wholesale overwrite preserves metadata. Backend additionally rejects a `graph_data` that drops `wizardScope`/`wizard_completed` when the stored doc already has it (`ValueError`, → 400), so no client can silently wipe wizard metadata on a completed doc. N7 ("No data" on wiped `wizardScope`) is fixed transitively; no separate code.

**Part A — frontend sends full graph_data.**

- [ ] **Step 1: Write the failing frontend test**

In the editor test, seed `getFMEA` to return a doc whose `graph_data.wizardScope = { wizard_completed: true, team: "...", timeframe: "...", tool: "...", task: "...", trend: "..." }`, render, trigger a save, and assert the `updateFMEA` mock received `graph_data` containing `wizardScope` (deep-equal to the loaded value) alongside `nodes`/`edges`.

```ts
it("save preserves wizardScope in graph_data payload", async () => {
  // arrange: getFMEA resolves a doc with graph_data.wizardScope.wizard_completed = true
  // act: click save
  // assert: updateFMEA called with graph_data.wizardScope present and equal to the loaded wizardScope
});
```

> Mirror the existing editor/wizard test setup (mock `../../api` `getFMEA`/`updateFMEA`). If `FMEAEditorPage.test.tsx` does not exist, find the nearest wizard/editor test (e.g. under `frontend/src/components/pfmea/`) and copy its render+mock harness.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorPage.test.tsx`
Expected: FAIL — payload lacks `wizardScope`.

- [ ] **Step 3: Frontend implementation**

In both `save` and `handleConflictForceSave`, spread the loaded wizardScope into the payload. Use the `fmea` state already loaded (its `graph_data.wizardScope`):

```ts
      const updated = await updateFMEA(id, {
        title: fmea.title,
        graph_data: { nodes, edges, wizardScope: fmea.graph_data?.wizardScope },
        lock_version: fmea.lock_version,
      });
```

Apply the identical `graph_data` change at the force-save site (`handleConflictForceSave`). Ensure the object passed to `updateFMEA` is typed to allow `wizardScope` (the `FMEAUpdate`/graph type already carries it per `GraphDataSchema`).

- [ ] **Step 4: Run frontend test + type gate**

Run: `cd frontend && npx vitest run src/pages/planning/fmea/FMEAEditorPage.test.tsx`
Expected: PASS
Run: `cd frontend && npm run build`
Expected: `tsc --noEmit` clean + build succeeds.

**Part B — backend safety net.**

- [ ] **Step 5: Write the failing backend test**

Add to `backend/tests/fmea/test_fmea_update_core.py`:

```python
@pytest.mark.asyncio
async def test_update_cannot_drop_wizard_scope(db, default_factory, admin_user):
    graph = {
        "nodes": [{"id": "n1", "type": "FailureMode", "name": "x"}],
        "edges": [],
        "wizardScope": {"wizard_completed": True},
    }
    fmea = await _make_fmea(db, default_factory.id, admin_user.user_id, graph=graph)
    with pytest.raises(ValueError):
        await update_fmea(
            db, fmea, title=None,
            graph_data={"nodes": [], "edges": []},  # wizardScope dropped
            user_id=admin_user.user_id,
        )
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/fmea/test_fmea_update_core.py -x --tb=short`
Expected: FAIL — update succeeds (no guard).

- [ ] **Step 7: Backend implementation**

In `backend/app/services/fmea_service.py` `_apply_fmea_update`, before applying the new `graph_data`, reject when the stored graph has `wizardScope` but the incoming one does not:

```python
    if graph_data is not None:
        existing_scope = (fmea.graph_data or {}).get("wizardScope")
        if existing_scope is not None and graph_data.get("wizardScope") is None:
            raise ValueError("wizard_scope_required")
        import json
        old_graph = json.dumps(fmea.graph_data, sort_keys=True) if fmea.graph_data else ""
        new_graph = json.dumps(graph_data, sort_keys=True)
        if new_graph != old_graph:
            changed_fields["graph_data"] = graph_data
            fmea.graph_data = graph_data
```

> The API layer already maps unknown `ValueError` to 400 (`api/fmea.py:163`); no API change needed. Confirm `graph_data` here is a plain dict (the route does `req.graph_data.model_dump()`), so `.get("wizardScope")` works.

- [ ] **Step 8: Run backend tests to verify**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/fmea/ -x --tb=short`
Expected: PASS (new guard test + all existing, including `test_update_fmea_public_behavior_unchanged` — note: that test's graph has no `wizardScope`, so the guard does not trip it).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/planning/fmea/FMEAEditorPage.tsx backend/app/services/fmea_service.py \
        frontend/src/pages/planning/fmea/FMEAEditorPage.test.tsx backend/tests/fmea/test_fmea_update_core.py
git commit -m "fix(fmea): preserve wizardScope on editor save + backend guard against metadata drop (N4/N7). docs-not-needed: bugfix restoring documented save-preserves-wizardScope behavior"
```

---

## Task 5: N6 — RiskTable severity Popover does not open

**Files:**
- Modify: `frontend/src/components/pfmea/RiskTable.tsx:48-77` (severity column) and `:127-143` (`ButtonLike`)
- Test: `frontend/src/components/pfmea/RiskTable.test.tsx` (extend)

**Interfaces:**
- Consumes: Ant `Popover`, the existing severity `content` grid, `updateNode`, `computeSeverity`.
- Produces: clicking the severity cell opens the Popover reliably (controlled `open` state), in both the real browser and playwright. Behavior (3 InputNumbers → `updateNode`) unchanged.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/components/pfmea/RiskTable.test.tsx`:

```tsx
it("opens the severity popover when the severity cell is clicked", async () => {
  // arrange: render RiskTable with a row that has a failureEffect node
  // act: click the severity button (role=button, aria-label /^severity/)
  // assert: the popover content (severityPlant / severityDialog) becomes visible
});
```

> Use `@testing-library/user-event` `click` and `findByText`/`findByLabelText` for `wizard.risk.severityPlant` (match the i18n mock the existing test uses). Read the current test file to reuse its `nodeMap`/`rows` fixtures and i18n setup.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/pfmea/RiskTable.test.tsx`
Expected: FAIL — popover content not found after click.

- [ ] **Step 3: Implementation — controlled Popover**

Make the Popover controlled so the anchor's own click toggles it (removes reliance on the `<a>` child's event bubbling / aria-role handling, which is what fails under playwright):

```tsx
function SeverityCell({ fe, feId, updateNode, content }: {
  fe: GraphNode | undefined;
  feId: string | undefined;
  updateNode: (id: string, patch: Partial<GraphNode>) => void;
  content: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      content={content}
      title={t('wizard.risk.severityDialog')}
      trigger="click"
      open={open}
      onOpenChange={setOpen}
    >
      <ButtonLike value={fe?.severity ?? 0} onClick={() => setOpen((v) => !v)} />
    </Popover>
  );
}
```

and extend `ButtonLike` to forward the click:

```tsx
function ButtonLike({ value, onClick }: { value: number; onClick?: () => void }) {
  return (
    <a role="button" tabIndex={0}
      aria-label={typeof value === 'number' && value > 0 ? `severity ${value}` : 'severity unrated'}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.(); }
      }}
    >
      {value || '-'}
    </a>
  );
}
```

> The severity column's `render` already builds `content` and computes `feId`/`fe`; keep that body, but return `<SeverityCell fe={fe} feId={feId} updateNode={updateNode} content={content} />` instead of the inline `<Popover>`. `GraphNode` is already imported (`../../types`). Add `useState` to the React import (the file currently imports no React hooks — add `import { useState } from 'react';`). `t` is available at component top level via `useTranslation`; `SeverityCell` is defined inside the component or receives `t` — match how `t` is scoped (it is used inside `render` closures today, so keep `SeverityCell` inside the main component so `t` stays in scope).

- [ ] **Step 4: Run test + type gate**

Run: `cd frontend && npx vitest run src/components/pfmea/RiskTable.test.tsx`
Expected: PASS
Run: `cd frontend && npm run build`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/pfmea/RiskTable.tsx frontend/src/components/pfmea/RiskTable.test.tsx
git commit -m "fix(pfmea): open severity Popover via controlled state (N6) — click failed under playwright. docs-not-needed: UI bugfix, no behavior/contract change"
```

---

## Task 6: N3 — `/api/collaboration/online` 404 (verify-only, no product code)

**Files:**
- Modify: `docs/e2e/reports/US-E2E-02-2026-07-25/report.md` (annotation only — see note below)

**Interfaces:**
- Consumes: the finding "N3: `GET /api/collaboration/online` → 404".
- Produces: a documented correction — the real presence endpoint is `GET /api/collaboration/{document_type}/{document_id}/active-users` (exists, `api/collaboration.py:47`, consumed by `useCollaboration.ts`). `/online` is not referenced by any product code or the 02.17 spec (which is behavioral: "在线用户列表"). No endpoint is added.

**Why no product code:** The 02.17 spec requires the online-user *feature* (list + polling), asserted behaviorally — it does not name `/online`. The frontend uses `/active-users`. N2 (heartbeat 500) was the actual presence-breaking bug; once Task 2 lands, the online list works. Adding an `/online` alias would be unrequested surface area (YAGNI).

- [ ] **Step 1: Confirm `/active-users` works and `/online` is unreferenced**

Run: `cd /Users/sam/Documents/Code/OpenQMS && grep -rn "collaboration/online" frontend/src backend/app docs/user-stories/US-E2E-02-fmea-lifecycle/ || echo NO_PRODUCT_OR_SPEC_REF`
Expected: `NO_PRODUCT_OR_SPEC_REF` (no product/spec reference to `/online`).

- [ ] **Step 2: Annotate the finding in the report**

Append a clarification to the N3 entry in `docs/e2e/reports/US-E2E-02-2026-07-25/report.md` (edit only the N3 line/section; do not alter the historical verdicts of other defects):

```markdown
- **N3 澄清（2026-07-26）**: `/api/collaboration/online` 非产品/规格端点——走查探测了错误 URL。真实在线状态端点为 `GET /api/collaboration/{document_type}/{document_id}/active-users`（`api/collaboration.py:47`，由 `useCollaboration.ts` 消费）。02.17 规格为行为式（"在线用户列表 + 短轮询"），未指名 `/online`。真正的在线功能缺陷是 N2（heartbeat 500），已由 Task 2 修复；N3 无需产品改动。
```

> This edits the report's *finding annotation*, not its acceptance verdicts/tally. Acceptable per Global Constraint (we are clarifying, not rewriting history). If the team prefers the report frozen, instead add the note to `docs/e2e/reports/US-E2E-02-2026-07-25/evidence/` as `n3-clarification.md` and reference it from the fix branch.

- [ ] **Step 3: Commit**

```bash
git add docs/e2e/reports/US-E2E-02-2026-07-25/report.md
git commit -m "docs(e2e): clarify N3 — /api/collaboration/online is not a real endpoint; presence is /active-users (fixed via N2)"
```

---

## Sequencing & Dependencies

```
Task 1 (N1 version factory_id)      ─┐
Task 2 (N2 collab factory_id)       ─┤  independent, any order
Task 3 (N5 transition RBAC)         ─┤
Task 5 (N6 severity Popover)        ─┘
Task 4 (N4/N7 wizardScope)          ── independent (frontend + backend guard)
Task 6 (N3 verify-only)             ── after Task 2 (references N2 fix)
```

Tasks 1, 2, 3, 5 are fully independent. Task 4 is independent of the others (different files). Task 6 should land after Task 2 so its annotation can truthfully reference the N2 fix. Recommended order: **1 → 3 → 2 → 4 → 5 → 6** (blocker + security first).

## Definition of Done

- N1: submitting/approving a new FMEA creates a `FMEAVersion` with `factory_id` set (no 500); test green.
- N2: collaboration heartbeat returns 204 and the session row carries `factory_id`; no more permanent "sync failed"; test green.
- N3: finding annotated; `/active-users` confirmed as the real endpoint; no product code added.
- N4/N7: editor save (and force-save) send full `graph_data` incl. `wizardScope`; backend rejects metadata-dropping updates on completed docs; "No data" regression covered; frontend + backend tests green, `npm run build` clean.
- N5: VIEW-only user gets 403 on any transition; EDIT-without-APPROVE gets 403 on approve; legitimate submit/approve still work; tests green.
- N6: severity Popover opens on click; test green.
- Full backend suite (`SECRET_KEY=test-secret-key pytest tests/ -x --tb=short`) and frontend `npm run build` are green at the end.
- No changes beyond the 7 defect fixes; historical E2E report verdicts/tally untouched (N3 annotation excepted).
