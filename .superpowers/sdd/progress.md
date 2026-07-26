# SDD Progress — FMEA Lifecycle Contract Backfill (Full-Stack, Option X)

Plan: docs/superpowers/plans/2026-07-26-fmea-lifecycle-backfill-full-stack.md
Source: D1-D9 spec gaps blocking US-E2E-02 all-PASS (docs/e2e/reports/US-E2E-02-2026-07-25/)
Branch: fix/fmea-fixes
Base: ca95fa0c

Goal: implement backend contract D1-D9 + embedding wiring + content-hash recommendation_id
(Phase 1), frontend adoption wiring (Phase 2), then re-run full verify-fmea-lifecycle walk
for all-PASS. Surgical, TDD, no scope creep. Pre-existing dev-DB drift failures in
tests/fmea/test_fmea_update_core.py (embedding_sync_outbox.content_hash, pgcrypto) are
out of scope — do NOT fix.

## Phase 1 — Backend contract (D1-D9)
Order: P1.1 → P1.2 → P1.3 → P1.4 → P1.5 → P1.6 → P1.7 → P1.8 → P1.9 → P1.10

P1.1: complete (commit 2288247e, review spec-✅ + quality-approved). 5/5 new tests; baseline unchanged (39f+2e pre-existing). Minors (non-blocking, verbatim-from-brief): broad pytest.raises(Exception), function-level import pytest.
P1.2: complete (commit b27bc9f2, review spec-✅ + quality-approved, no findings). 4/4 new tests; recommend-scope delta +4 passed/0 new. ⚠️ resolved: all SuggestionItem keyword-constructed (field-order safe); baseline match confirmed.
P1.3: complete (commit 74ed18f3, review spec-✅ + quality-approved; deviation ACCEPTABLE brief-authorized). 2/2 new + P1.2 4/4. DEVIATION: lessons leg queries LessonsCAPASource+AuditFindingSource+LessonsRuleSource directly (NOT LessonsLearnedService.recommend) because recommendation_cache.stage_runs column missing in drifted schema → orchestrator always raises. Contract+signature preserved; semantic_search kept separate. ⚠️ follow-up: reconcile stage_runs drift (memory: recommendation-cache-stage-runs-drift), then can restore orchestrator. ⚠️ P1.4 must pass real user+fmea_id to run_retrievers (signature-stable, orchestrator-restoration will consume user).
P1.4: complete (commit c7cbb6c8, review spec-✅ all-8 + quality-approved; generation_execution semantics ACCEPTABLE spec-safe). New observability test PASS; 18/18 focused; baseline 28=28 no-new. Fixed in-task: _StubFmea gained fmea_id (real PK), _FakeService accepts embedding=None. Env: stage_runs column added to local dev DB (matches migration 20260709_capa_cache_stage_runs, alembic_version untouched) — CI uses real migration. Reviewer confirmed verify skills only require generation_execution.llm PRESENCE (any enum), so success-when-not-called can't false-PASS.

## Phase 2 — Frontend adoption wiring (after Phase 1 backend green)
Order: P2.1 → P2.2 → P2.3 → P2.4

P2.1: complete (commit a6a954d4, review spec-✅ + quality-approved, no findings). vitest 2/2; tsc --noEmit + vite build clean (widened union didn't break SmartSuggestionDropdown). Suggestion.source→5-enum + recommendation_id; RecommendationAdoption exported (frontend source=string loose, matches brief); updateFMEA adoptions.
P2.2: complete (commit 8b71ee78, review spec-✅ + quality-approved; debouncedSave adoptions extension ACCEPTABLE — same optional-trailing pattern, no timing change, controller-authorized since P2.4 wizards save via debouncedSave). 22/22 hook tests (new + existing). enqueueSave/immediateSave/debouncedSave all thread adoptions, omit-when-empty. ⚠️ for P2.4: (1) no debouncedSave-adoptions test yet — add when P2.4 exercises it e2e; (2) adoptions are last-write-wins snapshot at save time, NOT merged — P2.4 must pass the FULL accumulated snapshot each save, not a delta.
P2.3: complete (commit b269e560, review spec-✅ + quality-approved). Editor FMEAEditorPage: adoptionsRef + recordAdoption (skip empty rec_id, dedupe last-write-wins), 5/5 SmartSuggestionDropdown onSelect wired with correct field_id (1011/1152/1233/1260/1412), both save paths (save + handleConflictForceSave) send adoptions omit-when-empty + clear-on-success-only. SmartSuggestionDropdown.tsx untouched. 68/68 fmea-page tests; build clean. ⚠️ obs: 409 non-force-save path leaves adoptions for next save (intended snapshot semantics).
P2.4: complete (commit 3ff3180c, review spec-✅ + quality-approved; clear-only-on-handleFinish decision ACCEPTABLE — backend dedupes per (fmea_id,recommendation_id) so debounced re-sends are DB no-ops; audit is append-only event record (revert ≠ un-adopt); clearing on unobservable debounced success is strictly worse). PFMEA+DFMEA symmetric: recordAdoption + 5/5 dropdowns/page wired (10 total), adoptionsRef threaded to all 4 save sites/page (8 total), cleared only on handleFinish success. useWizardSave/SmartSuggestionDropdown/ScopeTagField untouched. New test covers debouncedSave e2e (closes P2.2 ⚠️). 69/69 fmea-page tests; build clean. No DFMEA-specific test (symmetry, acceptable).

## Phase 2 — FRONTEND ADOPTION WIRING COMPLETE. All 4 tasks reviewed clean.
## ALL 14 IMPLEMENTATION TASKS COMPLETE (Phase 1 backend P1.1-P1.10 + Phase 2 frontend P2.1-P2.4).

## Final
FINAL WHOLE-BRANCH REVIEW (opus, ca95fa0c..3ff3180c, 16 commits/37 files): **READY TO MERGE**. All 5 integration-coherence checks PASS: (1) adoption contract frontend↔backend aligned end-to-end; (2) recommendation_id echoed not recomputed, snake_case both sides; (3) CP-sync chain intact — producer payload.user_id↔worker read, worker cols ⊆ model, mark_cp_sync_pending_on_fmea_approve fully removed (grep zero refs); (4) transition gates coherent (rework→editable, approved_by preserved); (5) no cross-cutting defects. No Critical/Important. 6 Minors triaged ALL follow-up (strongest: P1.10 rework reason validated-but-not-persisted = audit-trail gap, schedule first post-merge). Dev-DB drift confirmed not depended-on. Branch neither relies on nor worsens drift.

## REMAINING: re-run full verify-fmea-lifecycle E2E walk for all-PASS confirmation.
(pending) full verify-fmea-lifecycle walk for all-PASS

## BASELINE (pre-existing failures — diff target for all "no new failures" gates)
Established at P1.1 (commit 2288247e), verified identical via stash before/after.
`-k fmea` keyword suite: 39 failed + 2 errors + 118 passed (see baseline-fmea-failures.txt).
Most are tests/capa/* matching the "fmea" keyword + embedding_sync_outbox.content_hash drift.
Plan's "2 known in test_fmea_update_core.py" note was UNDERSTATED — the true pre-existing
baseline is the full list in baseline-fmea-failures.txt. Later tasks: your new tests must pass
and this baseline set must NOT grow. Full-suite baseline being captured separately.

## FULL-SUITE BASELINE (local dev DB is heavily drifted)
Full `pytest tests/` at 2288247e: 381 failed + 201 errors / 1256 passed (baseline-full-failures.txt).
This is NOT a green repo locally — the drift is broad (capa/embedding/plm tables). Do NOT try to
make the full local suite green; that's a separate cleanup. The DoD "all backend tests pass" gate
runs on the clean CI / e2e stack, not here. LOCALLY, each task's gate = (a) its own new tests pass,
(b) the pre-existing baseline set does not grow by any NEW failure the task introduced. Diff every
task's failures against baseline-full-failures.txt (full) or baseline-fmea-failures.txt (fmea scope).

## PLAN-AMENDMENT (controller decision, P1.5 review)
Reviewer found DEFECT in P1.5 dedupe scope: write_adoption_audits dedupe query is globally
scoped, but recommendation_id = content hash EXCLUDES fmea_id → same suggestion adopted into
two different FMEAs drops the 2nd FMEA's ADOPT_RECOMMENDATION audit silently. Plan/brief encoded
this verbatim (my plan bug, not implementer deviation). DECISION: fix is correct + necessary —
idempotency = "same adoption for the SAME FMEA doesn't double-write", scope dedupe by record_id.
Amend plan: add `AuditLog.record_id == fmea_id` to the dedupe WHERE + a cross-FMEA regression test.
Also apply the same scoping to the P1.6 route test mental model (per-FMEA dedupe). Fix dispatched.
P1.5: complete (commits 783760ed + fix 9bd7a617, re-review Critical-RESOLVED + spec-✅ + quality-approved). 3/3 tests (incl new cross-FMEA regression). Dedupe now scoped (fmea_id, recommendation_id).
P1.6: complete (commit bb7b704c, review spec-✅ + quality-approved; enqueue_embedding mock ACCEPTABLE — correctly targeted on fmea_service namespace, orthogonal to AuditLog assertion, matches test_collaboration.py pattern, can't mask broken adoptions path). 13/13 new tests (12 normalize + 1 route). ⚠️ follow-up: test-DB content_hash drift now mocked around in 5+ tests — reconcile schema later to drop mocks (out of scope here).
P1.7: complete (commit 61a6d5f5, review spec-✅ + quality-approved; model↔migration parity ✅ all 13 cols + unique key + partial index). 1/1 test PASS on clean throwaway DB (local dev DB blocked by pre-existing stage_runs drift — honestly scoped, not a defect). down_revision=20260721_capa_lateral_diffusion. New head=20260726_add_cp_sync_outbox.
P1.8: complete (commit 33e93176, review spec-✅ + quality-approved; test-helper db.flush() deviation ACCEPTABLE — test-only, root-caused to bare FK fmea_ref_id + flush-only conftest commit patch, doesn't change assertions). 2/2 PASS on throwaway DB qms_p18_test. Applier doesn't commit; worker commits/row; trigger_fmea_version_id (never source_); mark_cp_sync_pending_on_fmea_approve preserved for P1.9. ⚠️ minors (verbatim-from-brief, obs only): _BACKOFF gap at attempt 5 (default max_attempts=5 → straight to dead); "2+N audits" comment vs test asserting N=2.
P1.9: complete (commit ddc9afca, review spec-✅ all-3 + quality-approved; _mk flush-split deviation ACCEPTABLE — test-only, same bare-FK root cause as P1.8). 2/2 new PASS; regression 70p/1 pre-existing fail (trg_cp_version_no_update trigger missing on fresh DB — stash-verified unrelated, separate cleanup). P1.8 worker tests still pass. mark_cp_sync_pending_on_fmea_approve removed (grep clean), apply_cp_sync_pending survives as worker path. Approval now enqueues CPSyncOutbox pre-commit (durable), CP flip deferred to worker.
P1.10: complete (commit 02e11804, review SECURITY-PASS + spec-✅ + quality-approved; both test-data changes ACCEPTABLE — (A) N5 _make_fmea wizard_completed=True preserves EDIT-can-submit intent, wizard-incomplete now covered by new test; (B) _mk approved_by/at fixture-correctness, verified service never clears on REWORK). 9/9 (5 new + 4 N5); fmea regression 173p/0f (drift baseline doesn't reproduce on fresh DB). require_approve_permission→require_transition_permission: EDIT floor intact, APPROVE for approved+rework, rework-reason 422, wizard_completed 422 on in_review, PUT 409 outside draft/rework. ⚠️ follow-ups: reason validated-but-not-persisted (audit-trail gap); frontend must surface 422/409 + disable edit outside draft/rework.

## Phase 1 — BACKEND CONTRACT (D1-D9) COMPLETE. All 10 tasks reviewed clean. Base ca95fa0c → HEAD 02e11804.
