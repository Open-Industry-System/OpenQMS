# CAPA Doc-Gate Round 25 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make structured waiver issuance, runtime enforcement, deployment preflight, migration, and rollout fail closed under stale, malformed, historical, or concurrent state.

**Architecture:** Add one focused waiver-validation module shared by issuance, D8 runtime gate, and preflight. Add a successor Alembic revision that invalidates every pre-Round-25 waiver, and replace the Make prerequisite DAG with a serial release script that requires an explicit rollout command.

**Tech Stack:** Python 3.11, FastAPI services, SQLAlchemy async ORM, PostgreSQL/Alembic, pytest/pytest-asyncio, Bash, GNU Make.

---

## File map

- Create `backend/app/services/capa_doc_gate_waiver.py`: strict audit-batch, item-shape, residual, audit/live-version, and snapshot validation.
- Modify `backend/app/services/capa_doc_gate_service.py`: delegate waiver preparation to the shared validator.
- Modify `backend/app/services/capa_service.py`: fail closed by validating persisted waiver before D8 advancement.
- Modify `backend/app/services/capa_doc_gate_preflight.py`: recompute C9 and validate waiver before suppressing exact breaks.
- Create `backend/alembic/versions/20260716_doc_gate_waiver_hardening.py`: invalidate all waivers issued before the new validator existed.
- Modify `backend/tests/capa/test_capa_doc_gate_regression.py`: audit/waiver race and malformed persisted-waiver tests.
- Modify `backend/tests/capa/test_capa_doc_gate_preflight.py`: stale C9 and malformed waiver preflight tests.
- Modify `backend/tests/capa/test_doc_gate_migration.py`: old-head-to-new-head waiver invalidation test.
- Create `scripts/deploy-release.sh`: serial migration, check, preflight, rollout.
- Create `backend/tests/capa/test_doc_gate_release_script.py`: release ordering and missing-rollout tests.
- Modify `Makefile` and `docs/deployment.md`: expose only the serial release entry.

### Task 1: Reject audit-to-waiver version drift

**Files:**
- Test: `backend/tests/capa/test_capa_doc_gate_regression.py`
- Create: `backend/app/services/capa_doc_gate_waiver.py`
- Modify: `backend/app/services/capa_doc_gate_service.py`

- [ ] **Step 1: Write the failing race regression**

Add a test that runs `run_audit()`, inserts a newer CP version that still omits the target key, and then calls `record_gate_waiver()`:

```python
with pytest.raises(ValueError, match="审核后文档已变更"):
    await capa_doc_gate_service.record_gate_waiver(
        db, capa, "accepted", [{
            "doc_type": "control_plan", "doc_id": str(cp.cp_id),
            "target_key": tk, "field": field,
        }], user.user_id,
    )
```

- [ ] **Step 2: Verify RED**

Run:

```bash
SECRET_KEY=test-secret-key-not-default pytest backend/tests/capa/test_capa_doc_gate_regression.py::test_waiver_rejects_version_created_after_audit -q
```

Expected: FAIL because the current implementation accepts and binds the unaudited version.

- [ ] **Step 3: Implement the shared preparation validator**

Create `prepare_structured_waiver(db, analysis, audit_run_id, raw_items)` returning enriched items and the complete C8 snapshot. It must load the complete audit batch, require audit identities to equal `analysis.affected_docs`, require the requested key set to equal all uncovered keys, and compare each audit `version_after.version_id/sha256` with live latest before returning:

```python
if latest is None or str(latest.version_id) != str(version_after["version_id"]):
    raise ValueError("审核后文档已变更，请重新运行审核")
if latest.sha256_hash != version_after.get("sha256"):
    raise ValueError("审核后文档已变更，请重新运行审核")
```

Move item-ID snapshot parsing into this module so all consumers use one implementation.

- [ ] **Step 4: Delegate issuance and verify GREEN**

Replace the duplicated residual/snapshot construction in `record_gate_waiver()` with the shared function while retaining the analysis row lock and latest blocked-decision reread.

Run the single test, then:

```bash
SECRET_KEY=test-secret-key-not-default pytest backend/tests/capa/test_capa_doc_gate_regression.py -q
```

Expected: PASS.

### Task 2: Make persisted waiver validation fail closed

**Files:**
- Test: `backend/tests/capa/test_capa_doc_gate_regression.py`
- Modify: `backend/app/services/capa_doc_gate_waiver.py`
- Modify: `backend/app/services/capa_service.py`

- [ ] **Step 1: Write failing persisted-data tests**

Add separate tests that replace a passed decision's items with `[{}]`, change an item's `audit_run_id`, and delete one audit row. Each calls `_d8_doc_gate_gate()` and expects `ValueError("waiver_items 非法|waiver audit 不完整")`.

- [ ] **Step 2: Verify RED**

Run the three named tests. Expected: malformed entries are currently skipped or incomplete audit batches are trusted.

- [ ] **Step 3: Implement strict persisted validation**

Add:

```python
async def validate_persisted_waiver(db, analysis, decision) -> set[tuple[str, str, str]]:
    if decision.decision != "passed" or not decision.waiver_reason:
        raise ValueError("waiver decision 非法")
    if not isinstance(decision.waiver_items, list) or not decision.waiver_items:
        raise ValueError("waiver_items 非法，请重新审核")
    # Require every field, matching audit_run_id, complete audit identities,
    # exact residual key set, exact audit/live/item version binding, and snapshots.
```

Do not `continue` on malformed entries. Compare the decision snapshot, ignoring order, with the snapshot derived from the complete audit batch.

- [ ] **Step 4: Call it from D8 and verify GREEN**

After normal C9 and decision lookup, invoke strict validation whenever either `waiver_reason` or `waiver_items` is present. A one-sided or malformed representation must block.

Run the regression and freshness suites. Expected: PASS.

### Task 3: Make preflight enforce C9 and shared waiver validity

**Files:**
- Test: `backend/tests/capa/test_capa_doc_gate_preflight.py`
- Modify: `backend/app/services/capa_doc_gate_preflight.py`

- [ ] **Step 1: Write failing preflight tests**

Add one test that changes a C9 CAPA semantic input after a valid waiver without changing the CP, and one that corrupts the waiver's audit binding. Assert returned breaks include `kind == "stale_analysis"` and `kind == "invalid_waiver"` respectively.

- [ ] **Step 2: Verify RED**

Run both tests. Expected: the current scanner suppresses the lineage break or omits the invalid state.

- [ ] **Step 3: Implement C9 and validator integration**

For every current analysis, rebuild candidates using `_build_allowlist()` and compare `_compute_input_hash()` before indexing waiver keys:

```python
if _compute_input_hash(capa, await _build_allowlist(db, capa)) != analysis.analysis_input_hash:
    breaks.append({"kind": "stale_analysis", ...})
    continue
```

Load only the latest decision for that analysis. If it contains waiver state, call `validate_persisted_waiver()`; on `ValueError`, append `invalid_waiver` and do not suppress any key.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
SECRET_KEY=test-secret-key-not-default pytest backend/tests/capa/test_capa_doc_gate_preflight.py backend/tests/capa/test_capa_doc_gate_regression.py -q
```

Expected: PASS, and `run_preflight()` treats `stale_analysis`/`invalid_waiver` as blocking.

### Task 4: Add a real successor migration

**Files:**
- Create: `backend/alembic/versions/20260716_doc_gate_waiver_hardening.py`
- Test: `backend/tests/capa/test_doc_gate_migration.py`

- [ ] **Step 1: Write the failing old-head upgrade test**

Upgrade specifically to `20260715_waiver_items`, insert a valid-looking Round 23 structured passed waiver, then upgrade `head`. Assert the decision becomes blocked, waiver fields/snapshot are cleared, the current analysis contains an invalidation error, and an immutable `DOC_GATE_WAIVER_INVALIDATED` audit row exists.

- [ ] **Step 2: Verify RED**

Run the named migration test. Expected: FAIL because current head equals the old revision and no successor executes.

- [ ] **Step 3: Add successor migration**

Use `down_revision = "20260715_waiver_items"`. Before updating decisions, insert audit rows by selecting affected decisions joined to analyses. Then invalidate every row with either waiver field present and annotate affected current analyses. Downgrade must be a documented no-op for the data invalidation; it may not resurrect bypasses.

- [ ] **Step 4: Verify GREEN and one head**

Run migration tests and:

```bash
cd backend && .venv/bin/alembic heads
```

Expected: migration tests PASS and only `20260716_doc_gate_waiver_hardening` is head.

### Task 5: Enforce serial release including rollout

**Files:**
- Create: `scripts/deploy-release.sh`
- Create: `backend/tests/capa/test_doc_gate_release_script.py`
- Modify: `Makefile`
- Modify: `docs/deployment.md`

- [ ] **Step 1: Write failing script contract tests**

Run the script with temporary stub commands that append `migrate`, `check`, `preflight`, and `rollout` to a log. Assert exact order. Add a second test omitting `ROLLOUT_CMD` and assert nonzero exit before migration.

- [ ] **Step 2: Verify RED**

Run the test file. Expected: FAIL because the script does not exist.

- [ ] **Step 3: Implement the serial script**

The script must start with `set -euo pipefail`, require `DATABASE_URL` and `ROLLOUT_CMD`, support command overrides for tests, and invoke each step synchronously:

```bash
run_step migrate "$MIGRATE_CMD"
run_step check "$CHECK_CMD"
run_step preflight "$PREFLIGHT_CMD"
run_step rollout "$ROLLOUT_CMD"
```

Do not background commands. Use the target `DATABASE_URL` for migration and preflight.

- [ ] **Step 4: Wire Make and docs**

Change `deploy-release` to a recipe invoking `scripts/deploy-release.sh`; remove `deploy-migrate deploy-check` prerequisites. Document `ROLLOUT_CMD='docker compose up -d backend frontend' make deploy-release` as the sole non-local entry.

- [ ] **Step 5: Verify GREEN**

Run the release-script tests plus `make -n -j2 deploy-release`; the latter must show one script invocation rather than independent migrate/check prerequisites.

### Task 6: Full verification

**Files:** all files above.

- [ ] Run focused CAPA doc-gate and migration suites.
- [ ] Run the complete backend suite required by `make check-backend`.
- [ ] Run frontend `tsc --noEmit` and build.
- [ ] Run Python compilation, Alembic heads, shell syntax check, and `git diff --check`.
- [ ] Review `git status` and ensure the user's untracked `package-lock.json` remains untouched.
- [ ] Commit implementation files without including unrelated user changes.
