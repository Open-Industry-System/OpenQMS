# Agent R3 Sidebar and Readonly Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent unified sidebar and auditable pause/resume/cancel/latest-checkpoint restart to the accepted D4 metadata runtime, proving old credentials cannot deliver after a control transition.

**Architecture:** Keep the existing INSTALL→TASK→RUN locks, tenant transaction gate and current source permission checks. Server-owned checkpoints preserve receipt versions and actual accepted input; a new run reconstructs inputs and rereads current business facts. The browser talks only to user APIs, refreshing bounded activity windows even when no new update arrives.

**Tech Stack:** Existing FastAPI/SQLAlchemy/PostgreSQL 15/Alembic, React/TypeScript/Ant Design, pytest, Vitest and local real HTTP/subprocess acceptance. No new framework or model dependency.

**Status:** 2026-10-01 execution approved after the two P2 corrections to the [R3 specification](../specs/2026-10-01-agent-sidebar-readonly-controls-design.md). User confirmed same-run pause/resume and new-run readonly restart with no plugin internal-memory restore. Two P2 findings from the written-spec review have been addressed: completion admission against unconfirmed input, and contiguous two-page refresh with atomic replacement. Task1 models/migrations accepted (162 passed, 416.87s; spec/quality approved), Task2 ordered updates accepted (200 passed, 331.23s; spec/quality approved), Task3 controls/finish accepted (247 passed, 560.60s, exit0; spec/quality approved), Task4 checkpoints/history/restart accepted (fixed affected101 passed, 260.06s, exit0; spec/quality approved), Task5 current-source reads accepted (final affected72 passed, 167.09s, exit0; spec/quality approved), Task6 sidebar accepted (final focused78 passed/7 files, exit0; spec/quality approved), Task7 accepted, including display/cancellation followups and final whole-slice review with no unresolved Critical/Important. Final frozen backend gate: 2731 passed / 4 skipped / 3 xfailed / 2 xpassed (1729.61s, exit0, owned DB removed); final frontend78/7 files, type/build and dedicated E2E typecheck exit0. Prior R2 frozen backend gate2526/4/3/2 is historical evidence.

## Scope and execution gates

Work in `.claude/worktrees/agent-module-permission-kernel`, preserving its existing uncommitted tenant/R1/R2 work and main-workspace user changes. Read PROGRESS, current relevant docs and actual code before edits. No deployment, production capability activation, push/merge, blanket staging or fixture-global database reset. Task checkpoints below mean recorded review/verification evidence; do not create commits unless separately authorized.

Spec review precedes implementation. Execute Tasks 1–7 in order; each task requires an observed RED on its meaningful contract, GREEN, independent spec/quality review where the chosen execution workflow requires it, and a ledger entry. Do not treat this plan as an accepted migration manifest.

Current local acceptance runner (already used for R2, not a production command):

```sh
PG15_CONTAINER=agent-module-permission-kernel-db-1 /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python /tmp/openqms_tenant_checks.py tests/services/agent_runtime -q -rs
```

The runner creates/migrates its own random `_test` database and deletes only that database in finally. For another development machine supply an equivalent owned isolated database; never silently fall back to `qms` or reuse a seeded/production database. Existing `committed_runtime` uses actual complete tenants, NullPool, TenantSession and real commits. Root `db.commit` is flush-only and cannot prove persistence or concurrent races.

## File responsibilities

| File | Responsibility |
|---|---|
| `backend/app/models/agent_readonly_control.py` (new) | Control idempotency, immutable checkpoint/receipt links, task updates |
| `backend/app/models/agent_task.py` | New nullable run checkpoint association only |
| `backend/app/schemas/agent_control.py` (new) | Strict user controls, plugin checkpoint/finish/history and bounded activity DTOs |
| `backend/app/services/agent_runtime/task_updates.py` (new) | Allocate updates only while owning TASK lock, within caller transaction |
| `backend/app/services/agent_runtime/task_controls.py` (new) | Current user authority, INSTALL→TASK→RUN locking, idempotent transitions |
| `backend/app/services/agent_runtime/checkpoint_service.py` (new) | Actual input position, current receipt saving, controlled historical checkpoint reads |
| `backend/app/services/agent_runtime/task_reads.py` (new) | Current-user install directory, runs/messages/event/receipt windows |
| `backend/app/services/agent_runtime/readonly_delivery.py` | Reusable historical source checks; existing result semantics preserved |
| `backend/app/services/agent_runtime/runtime_messages.py` | Persist claimed state; restricted accepted-prefix history reads |
| `backend/app/services/agent_runtime/run_dispatch.py` | Return actual accepted position/checkpoint presence after current admission |
| `backend/app/api/agent_tasks.py`, `agent_runtime.py`, runtime `routes.py` | Thin endpoints and exact JWT/offgate route registry |
| `frontend/src/api/agentTasks.ts`, `types/agentTask.ts` (new) | User-only typed requests and contracts |
| `frontend/src/components/agent/AgentSidebar.tsx`, `useAgentTaskActivity.ts`, `AgentActivity.tsx`, `AgentTaskContext.tsx` (new) | AppLayout-owned selection, local polling/content and rendered controls |
| `frontend/src/components/layout/AppLayout.tsx`, `pages/capa/CAPADetailPage.tsx`, `api/client.ts` | Mount, explicit report-create entry, exclude task GETs from factory injection |

Do not move unrelated existing modules. New tests live alongside each responsibility below.

## Task 1 — Models, exact migrations and nonempty upgrade evidence

**Files:** Create `backend/app/models/agent_readonly_control.py`, `backend/alembic/versions/20261001_agent_readonly_controls.py`, `backend/alembic_tenant/versions/tv004_agent_readonly_controls.py`, `backend/tests/migrations/test_agent_readonly_controls_delta.py`. Modify models `__init__.py`, `agent_task.py`, tenant `__init__.py`, `tenant_migrator.py`, `tenant_schema_diff.py` and tests for latest head/parity.

- [x] Add model/schema contract tests for the following actual database shape. Use UUID v4 and UTC server timestamps; do not store `source_versions` supplied by clients.

```text
agent_task_controls:
  control_id UUID PK; task_id FK; run_id nullable FK;
  key varchar(100); action varchar(16); expected_epoch nullable int;
  checkpoint_id nullable FK; resulting_run_id nullable FK; created_at;
  UNIQUE(task_id,key), CHECK action IN(pause,resume,cancel,restart).
agent_readonly_checkpoints:
  checkpoint_id UUID PK; task_id FK; run_id FK; key varchar(100);
  lease_epoch int>=0; tenant_generation int>=0; accepted_message_seq int>=0;
  update_sequence int>0; created_at; UNIQUE(run_id,key).
agent_checkpoint_receipts:
  checkpoint_id FK + receipt_id FK as composite PK.
agent_task_updates:
  update_id UUID PK; task_id FK; sequence bigint>0;
  kind varchar(32); object_id UUID; created_at;
  UNIQUE(task_id,sequence); CHECK kind IN(run_created,message,ack,claim,control,finish,event,result,checkpoint).
agent_runs.resume_checkpoint_id nullable FK(agent_readonly_checkpoints.checkpoint_id).
```

- [x] Observe RED for absent schema/constraints and missing latest chain. Test FK violations, duplicate keys, strict status constraints and public/tenant parity on real PG15.
- [x] Implement both static equivalent deltas; create checkpoint tables before adding run FK, remove run FK before downgrade table drops. Register tv004 in reviewed revisions. Explicitly enumerate cumulative additions for v2/v3 reference validation, never filter tenant-side objects.
- [x] Implement deterministic owned-maintenance backfill of existing message/run/event/result updates. Use one union of historical source rows, `row_number() OVER(PARTITION BY task_id ORDER BY created_at,kind,object_id)`; preserve original records, accepted positions and audit logs. Historical run rows use run_created, including pending runs; never label creation timestamps as an actual claim. Include source-less old events without inventing receipt authority.
- [x] Prove nonempty tv001/tv002/tv003→tv004 upgrades, newest parity, extra/missing/partial predecessor rejection and owned tv004 downgrade. Verify frozen snapshot exports/checksums remain unchanged. Run new migration tests and relevant tenant/rebuild/parity tests in the owned runner. Record actual counts and reviewed object allowlist.

## Task 2 — Ordered committed activity updates

**Files:** Create `task_updates.py`, `backend/tests/services/agent_runtime/test_task_updates.py`. Modify `task_service.py`, `message_queue.py`, `runtime_messages.py`, `run_dispatch.py`, `readonly_delivery.py` only at effective mutation/commit points.

- [x] Add RED two-connection test: first writer owns TASK, appends event then blocks before commit; second writer cannot receive a later sequence until the first commits. Rollback of first leaves no visible update/object. Same-key event/result/message/claim/ACK retries do not increment update count.
- [x] Implement the caller-owned sequence allocator with no separate session/commit:

```python
async def append_update(db, *, task_id, kind, object_id):
    # Caller already owns this task's FOR UPDATE lock; do not acquire INSTALL here.
    sequence = 1 + (await db.scalar(select(func.max(AgentTaskUpdate.sequence))
        .where(AgentTaskUpdate.task_id == task_id)) or 0)
    row = AgentTaskUpdate(task_id=task_id, sequence=sequence,
                          kind=kind, object_id=object_id)
    db.add(row)
    await db.flush()
    return row
```

- [x] Add it to original successful transitions before their existing atomic commit. In create_task the initial message and pending run are inserted directly: append message/run_created updates inside that same savepoint/transaction (the new uncommitted task row is exclusively owned), including blocked tasks whose initial input still needs display. Same-key creation retries must not emit another update. Keep full final authorization before dirty values; do not re-resolve identity after dirty values may be overwritten by populate_existing. First message claim sets actual state=claimed, with original batch/epoch behavior; retries keep immutable batch.
- [x] Run message/output/claim affected tests plus new persistence/ordering tests. Update expected claimed state intentionally and retain old cross-run batch/corruption/concurrency regressions. Do not weaken assertions to accept both states.

## Task 3 — Durable pause/resume/cancel and plugin finish

**Files:** Create `agent_control.py`, `task_controls.py`, `backend/tests/services/agent_runtime/test_task_controls.py`, `backend/tests/api/test_agent_controls.py`. Modify both thin APIs and runtime routes; add updates from Task 2.

- [x] Define strict requests `TaskControl(action=pause|resume|cancel, run_id, expected_epoch, idempotency_key)` and `RuntimeFinish(status=completed|failed)`. Nullable run/epoch only for blocked-capability cancel. Task4 extends this reviewed DTO with restart and its checkpoint_id after real checkpoint admission exists; do not add a placeholder restart branch in Task3. Add extra-field/bool/numeric-string/bounds RED tests.
- [x] Write real committed same-key retry and two-connection competing pause/resume/cancel tests. Capture the actual pretransition run epoch, invoke `control_task`, then assert persisted task/run state, epoch, lease/key and one control/audit/update. Example contract:

```python
@pytest.mark.asyncio
async def test_pause_fences_old_run_token(delivery):
    from app.schemas.agent_control import TaskControl
    from app.services.agent_runtime.task_controls import control_task
    owned = delivery
    async with owned.factory(binding=owned.binding) as db:
        identity = await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
        body = TaskControl(action="pause", run_id=identity.run.run_id,
            expected_epoch=identity.run.lease_epoch, idempotency_key="pause-once")
        await control_task(db, identity.scope, owned.task_id, body)
    async with owned.factory(binding=owned.binding) as db:
        with pytest.raises(PermissionError):
            await runtime_access.verify_runtime_identity(db, owned.token, owned.binding)
```

Import `delivery` from the existing `test_runtime_messages` fixture, which in turn imports `ready_owned` and `direct_caps`; do not replace bcrypt/token/namespace gates with auth mocks.

- [x] Implement INSTALL→TASK→RUN locking from fresh associations, post-wait current initiator/business access, fresh association checks. Look up idempotency after current authority but before comparing current epoch/state for a new mutation, so the exact original key can acknowledge an already committed operation without executing it again; same key/different parameters 409. New mutations must compare expected epoch and state. Pause/cancel admit disabled plugin under user business access; resume additionally verifies enabled pinned version, canonical grant intersection and current restricted delivery policy.
- [x] Clear lease/key and increment epoch on each effective control; clear only unaccepted batch markers under the task lock. Keep accepted message prefix. Record operation, update and content-free audit, then commit before response. Implement `finish_run` under full current runtime identity, status transition and one effective update/audit. For completed, query actual task messages under the same TASK lock after full final authorization and before dirty state: any queued/claimed input, inconsistent accepted prefix or watermark returns409 with no change to task/run/lease/epoch/message/audit/update. For failed/cancel retain unconfirmed input records without fabricating ACK. After success all old-token retries, including finish, deny; use current-user activity to resolve a lost completion response.
- [x] Add actual two-connection completion-vs-append tests using explicit lock/acquisition/commit events, not timed sleeps or merely serial calls. Start active with its initial prefix already ACKed. Direction A: append owns TASK, queues a new message, finish starts and waits, append commits; finish must see the row and return409, with run still active and no finish audit/update/epoch change. Repeat with a claimed but unconfirmed message. Direction B: completed finish owns TASK with no pending input, append starts and waits, finish commits; append must return409 after lock acquisition with no inserted message/audit/update. Also prove failed/cancelled retain unconfirmed inputs and accepted proofs without fabricating ACK. Terminal UI labels and the actual queued/claimed delivery distinction remain Task6 verification; ACK alone does not prove execution.
- [x] Prove pause while RR query is reading (real second connection commit) denies final content/receipt/audit; output-before-pause remains stored; pause-before-output/ACK/finish denies. Test lock-wait role/factory/PL/install changes, terminal refusal, missing/foreign run, default off before auth/body and wrong JWT domain. Run control/API + affected runtime/metadata suites.

## Task 4 — Immutable checkpoints, latest-safe restart and history

**Files:** Create `checkpoint_service.py`, `backend/tests/services/agent_runtime/test_readonly_checkpoints.py`, `backend/tests/api/test_readonly_checkpoints.py`. Modify `task_controls.py`, `runtime_messages.py`, `run_dispatch.py`, runtime DTOs/routes/API.

- [x] Add RED: old/other-run receipt refused; client-provided watermark/digest/generation refused; same key+sources exactly one checkpoint; pending unconfirmed batch refuses. Use real delivered context receipts and actual ACK.
- [x] Implement `save_checkpoint(db,identity,body)` under existing runtime lock/full refresh. Validate 1–20 actual current receipts with existing recognized-source rules, actual contiguous accepted prefix and no outstanding claimed batch; sort unique receipt IDs. Derive stored position/epochs/update sequence solely server-side, save links/update/audit atomically. Idempotency compares source set and saved accepted position.
- [x] Implement user `get_checkpoint_for_view` with task and every actual source permission, no live-plugin/lease requirement. Reuse R2 historical source checks, never use a client-supplied sensitivity class. More recent generation is allowed only as historical reference in the same current admitted namespace.
- [x] Extend TaskControl with action=restart and checkpoint_id (only restart accepts it), then implement restart branch: only paused run's latest checkpoint with exact current complete accepted prefix; stop/invalidate old run, insert pending pinned-version run, inherit prefix and resume_checkpoint_id, clear only unaccepted markers. Preserve original accepted rows. Check missing/old/foreign checkpoint, prefix drift/gap and current source/plugin/grant/trust refusal before writes. Two competing restarts create one new run.
- [x] Add strict plugin history query `after_sequence>=0,limit=1..20`. Return only actual contiguous accepted rows up to current run watermark, `next_sequence` and completion flag; no history beyond that prefix. Refresh complete identity + restricted delivery after SELECT, before returning text. Do not mutate watermark or ACK proof from a GET. Claim response returns actual accepted position/checkpoint presence; selector/secret remains absent.
- [x] Run actual pause after partial ACK, append while paused, resume/claim new epoch, history reconstruction, next pending batch/ACK tests. Assert old token, old batch, old receipt and stopped old run stay refused. Source versions can differ; do not falsely require every receipt digest identical. Run checkpoint/history/control plus old R2 suites.

## Task 5 — Current-source activity and installation directory

**Files:** Create `task_reads.py`, `backend/tests/services/agent_runtime/test_task_reads.py`, `backend/tests/api/test_agent_activity.py`. Extend `readonly_delivery.py` with narrow reusable user source admission/event read helpers; modify user API/DTOs.

- [x] Add RED actual user HTTP routes: availability, target-authorized installation directory, activity newest/history window. Requests use actual User JWT and tenant middleware; default false must return404 before tenant/body handling. Register availability/installations before UUID task routes.
- [x] Implement installation candidate discovery using the same R1 current-access/target/_read_grants canonical intersection, enabled pinned manifest and actual plugin grants. Return only ID/name/version; catalog DENY returns no candidates. Do not create hypothetical persisted tasks/grants just to call authorize_task.
- [x] Implement activity query with the update ordering:

```python
query = select(AgentTaskUpdate).where(AgentTaskUpdate.task_id == task_id)
if before_sequence is not None:
    if window_end_sequence is None or not 1 <= before_sequence <= window_end_sequence + 1:
        raise ValueError("Invalid activity window")
    query = query.where(AgentTaskUpdate.sequence < before_sequence)
if window_end_sequence is not None:
    query = query.where(AgentTaskUpdate.sequence <= window_end_sequence)
rows = list((await db.scalars(query.order_by(AgentTaskUpdate.sequence.desc())
                             .limit(page_size + 1))).all())
# Newest-page W is its highest row sequence (or0), never a mutable later MAX query.
# For historical pages echo the supplied W, retaining the same record range.
# Resolve page_size rows, authorize all sources, then final-recheck before returning
# ascending records, W and next_before_sequence=min(page.sequence) if more remain.
```

- [x] Resolve every UUID to the actual matching task/run object. Return restricted messages after initiator access; results use the accepted R2 read service; checkpoints/events validate all actual receipts. Unsourced progress returns a fixed presentation code/time with no free text/counters. If any visible-window source denied return403, no partial page/cursor/count.
- [x] Re-read task/source authority after window materialization. Actual grant/role/PL/target change during reads must return no payload. History browser still works after plugin disable/finish/retained-generation maintenance if current user source access remains; restart does not inherit that exception.
- [x] Test strict nonnegative W and positive before_sequence, requiring W for history and before<=W+1. Persist updates1–100; obtain first page51–100/W100, commit101–110 on a different connection before historical query, prove historical page1–50 still belongs to W100. Next cycle must produce61–110/W110 and adjacent11–60, retaining51–60. Pagination/idempotent rows, forged object UUID/task association, receipt corruption, after-row-read revocation, factory selection independence and missing installation secret fields stay covered. Run read APIs/services and R2 source-result tests.

## Task 6 — Unified sidebar with fresh bounded windows

**Files:** Create frontend API/types/components listed above and `frontend/src/components/agent/AgentSidebar.test.tsx`, `useAgentTaskActivity.test.tsx`, `AgentActivity.test.tsx`, `frontend/src/api/agentTasks.test.ts`. Modify AppLayout, CAPADetailPage, client and their focused tests.

- [x] Add meaningful frontend RED tests using controlled delayed promises and fake timers: report A task stays A after navigating to B; logout/tenant change clears; disabled availability hides entry; send/control retry uses the same generated key; expected epoch refreshes after409; old response from a prior task never replaces current content.
- [x] Implement user-only API wrapper `/agent/tasks`, strict local types matching Task 3–5 DTOs, abort signals, shared existing axios identity. Explicitly add `/agent/tasks` to factory injection exclusions, with an interceptor regression that ordinary business GETs still receive selected factory_id.
- [x] Mount `AgentTaskContext` + `AgentSidebar` in AppLayout above Outlet. CAPA explicit create action passes immutable report UUID; opening a new report is not a side effect of navigation. Availability404 hides entry; install directory0 disables submit with explanation. No prompt for an installation secret in UI.
- [x] Implement one in-flight polling cycle per selected task. Every2s stage the fresh newest page, then stage its adjacent history page using that response's W and next_before_sequence; never reuse the previous cycle's history cursor. Replace max2/100items in one state update only after both requested pages are authorized and the cycle generation still matches. New writes between page requests stay above W and enter the next cycle. Close/hidden aborts the whole cycle. Either-page network/parse error discards staged pages, hides old bodies and retries after5s from the newest page; permission/not-found/auth failure clears immediately. No first-page-only update or stale second-page retry. Late-response generation guard includes task, tenant/user identity, visibility and request generation. No permanent result cache or incremental-only permission refresh.
- [x] Add controlled-promise frontend RED tests for 51–100/1–50 →61–110/11–60 after10 new records, exact new W/history cursor arguments, a write between page requests, no visible replacement while second-page response is pending, and second-page403/network/parse failures discarding both. Prove retry obtains a new W, empty history produces one valid page, and same-cycle page_size is stable; old cycle response cannot repopulate hidden content.
- [x] Render escaped React text, not HTML/markdown from plugin. Show fixed report UUID/document anchor, plugin/run/state, queued/claimed/accepted messages, restricted analysis sources/digests, pause/resume/cancel/latest-safe restart and pending state. Label accepted as 已确认接收; queued/claimed input on failed/cancelled tasks as 终止时未确认接收（不代表已处理） while retaining their actual delivery states; never imply ACK proves execution. Restart describes rereading current facts, not restoring business state. Historical checkpoint buttons disabled with explicit latest/prefix eligibility from server.
- [x] Test both visible windows revalidated with no new update, revoked source clearing, keyboard focus/close/live-region status, error retry keys, click races and history de-duplication. Run:

```sh
cd frontend
npx vitest run src/components/agent src/api/agentTasks.test.ts src/pages/capa/CAPADetailPage.test.tsx
```

Then `make check-frontend` from worktree root. Record actual output; do not infer passing from typechecking.

## Task 7 — Independent process/browser acceptance and final gate

**Files:** Create `backend/tests/e2e/test_agent_readonly_resume_process.py` and `frontend/e2e/specs/agent/readonly-sidebar.spec.ts`; modify existing sample only to add the explicitly scoped checkpoint/history/finish protocol while preserving credential/URL/redirect/error guards. Update docs/architecture.md, permissions.md, development.md, PROGRESS.md and this ledger after observed results.

- [x] Write RED real HTTP test using a complete synthetic tenant, actual registration/grants/task service and stdlib separate process. Existing fixture process cleanup owns only its socket/children/tenant. Add service-owned test DIRECT/trust tuples only in fixture; product catalog remains unchanged.
- [x] Run two scenarios: pause/resume same run with new epoch and old-token denial; checkpoint/restart new run, accepted history before new queued message, business metadata changed by separate test user transaction then reread current digest, new receipt result. Show stopped predecessor cannot write, historical authorized result still viewable, CAPA changes are only the explicit fixture edit—not plugin writes. No model/key/provider.
- [x] Run real local browser against fixture-owned backend plus frontend on allocated ports; synthetic user/installation only. Confirm sidebar preserves target across navigation, closed panel does not stop process, pause blocks second query, restart reconstructs input, revoked source clears bodies, duplicate control click remains one operation. Cover completed finish versus a concurrently appended user message in both commit orders and actual two-page refresh after intervening writes; second-page failure exposes no partial first page. Existing shared E2E reset/database/container lifecycle is not part of this test. Test owns its server and subprocess cleanup.
- [x] Run all changed frontend tests, final relevant backend/migration/multitenancy/process suites, then frozen-code full backend and frontend checks:

```sh
PG15_CONTAINER=agent-module-permission-kernel-db-1 /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python /tmp/openqms_tenant_checks.py tests -q -rs --ignore=tests/test_graph_sync_worker.py --ignore=tests/test_graph_projection.py
make check-frontend
```

Only after actual exit0, precise pass/skip/xfail/xpass output and owned DB cleanup, close R3 ledger. Retained historical expected failures/skips must be reported, not claimed eliminated.

- [x] Perform final whole-slice review. Update fact docs to implemented behavior only after green; keep default-off/DENY and empty trust limitations. Final documentation link/diff checks and targeted change-scope review; preserve worktree and all prior changes.

## Requirement-to-task review

| Spec | Plan coverage |
|---|---|
| 1–2 scope, alternatives and target persistence | Gates, Tasks5–7 |
| 3 authority, locks, state/epoch, idempotency, in-flight delivery and finish/append admission | Tasks2–3, Task7 |
| 4 exact message semantics/history | Tasks2,4,6–7 |
| 5 server receipts/position/latest restart and immutable history | Tasks1,4,7 |
| 6 stable order, W-bounded adjacent pages, whole-cycle replacement and current-source polling | Tasks2,5–7 |
| 7 thin strict APIs, JWT domain and default404 | Tasks3–6 |
| 8 public/tenant static chains and retained data | Task1 |
| 9 real independent chain and frontend/final evidence | Task7 |

## Execution ledger

| Task | State | Evidence |
|---|---|---|
| 1 Models/migrations | Accepted; spec and quality approved | Baseline31 passed; absent-schema/head RED observed; controlled missing-backfill RED3 failed/1 passed with exact restoration; final related matrix162 passed/0 skipped (416.87s, exit0), PG15 frozen export included, owned DB removed. Frozen five files unchanged; compile/diff0. |
| 2 Committed updates | Accepted; spec and quality approved | Unchanged service baseline178 passed; meaningful RED14 failed (38.19s); dedicated GREEN14 passed (39.10s); final service/API matrix200 passed/0 skipped (331.23s, exit0), owned DB removed. Compile/diff0; seven-file isolated delta frozen. |
| 3 Controls/finish | Accepted; spec and quality approved | Baseline5 passed; core/API/boundary meaningful RED observed; fixture errors corrected separately. Late-authority RED5 failed → GREEN10 passed. Final affected services/API247 passed/0 skipped (560.60s, exit0), owned DB removed. Eight frozen hashes match; compile/diff0. |
| 4 Checkpoints/history/restart | Accepted; fixed spec and quality approved | Baseline90 passed; meaningful RED and expanded GREEN42 passed. Broader265 passed/1 pause-audit compatibility failure; restart-only audit fix independently re-reviewed. Final fixed affected101 passed/0 skipped (260.06s, exit0), owned DB removed. Thirteen frozen hashes match; compile/diff/patch0. Sample claim adapter and process checks remain Task7. |
| 5 Current-source reads | Accepted; fixed spec and quality approved | Baseline6 passed; meaningful interface/source-guard RED; focused GREEN29 passed. Broad matrix192 passed/1 factory-withdrawal fixture failure, corrected separately. Directory target/install/grant races and checkpoint source/origin replacement reproduced and fixed (review-fix GREEN11 passed); final refrozen affected72 passed/0 skipped (167.09s, exit0), owned DB removed. Six frozen hashes match; compile/diff0. Nonblocking duplicate directory prefetch reads retained. |
| 6 Sidebar | Accepted; fixed spec and quality approved | Initial CAPA test fixture omissions corrected separately; unchanged CAPA23 and layout permissions4 passed. Meaningful API/poll/UI, bounds, withdrawal, rapid hide/reopen, control epoch/retry, paginated selection and SPA target-navigation RED observed. Final focused75 passed/7 files (5.54s, exit0); type/build exit0 (build7.17s). Fifteen frozen hashes match; isolated patch reverse-check0. Independent spec review found task-directory401/403/404 did not immediately withdraw existing activity; RED3 failed → GREEN3 passed. Final refrozen focused78 passed/7 files (5.62s, exit0); type/build exit0 (build7.52s). Immediate withdrawal and no late body restoration or denial request loop proved; fixed spec and quality approved. No backend/sample edits; actual browser remains Task7. |
| 7 Actual process/browser and full gate | Accepted; final whole-slice review and frozen gates passed | Actual old R2 baseline13 failed/9 passed (58.55s), five-field sample parser versus seven-field claim. Meaningful history/CP, resumed-result keys, canonical D4_ROOT_CAUSE and malformed checkpoint/finish REDs fixed. Combined49 passed/0 skipped (262.70s, exit0; old22 + new27 including8 browsers); browser fixture final8 passed (101.36s), portable executable override1 passed (27.13s). Relevant backend202 passed (589.32s), frontend78/7 and type/build/E2E tsc exit0. All owned DBs removed; five frozen files and prior56 unchanged, isolated patch verified; spec/quality approved. Whole-slice visual followup: actual Chromium digest overflow499/432px reproduced, minimal wrapping fixed to432/432px and activity579/512→512/512, full digests matched actual result/checkpoint200. Lifecycle1 passed, frontend78/type/build/E2E tsc exit0; followup spec/quality approved. Final review then found cancel incorrectly resetting claimed input to queued; retained terminal delivery distinction fixed: RED2 failed/1 passed → GREEN3 passed (8.84s), current User Activity preserves received/claimed/queued and stopped-run batch proof; old runtime token denied, same-key retry remains one control/audit/update. Fix spec/quality and whole-slice re-review approved; final relevant control/activity/message/checkpoint service/API188 passed/0 skipped (489.98s, exit0), owned DB removed, final61 hashes unchanged. First complete gate deliberately interrupted before source correction (1012 passed/1 skipped, exit2; owned DB removed), not treated as green. Fresh complete backend gate 2731 passed / 4 skipped / 3 xfailed / 2 xpassed (1729.61s, exit0), owned DB removed; all61 final hashes unchanged. Independent final frontend78/7 files (5.85s), types/build (7.47s) and E2E tsc exit0. Final whole-slice review approved, no unresolved Critical/Important. |

## Written-spec review corrections — 2026-10-01

- P2 completion/append race: Task3 defines completed admission and both real commit orders; failed/cancelled history and non-execution ACK labels are covered in Task6; actual HTTP/browser evidence is in Task7.
- P2 two-window gaps: Task5 defines strict W-bounded adjacent pagination and real intervening writes; Task6 stages two newly adjacent pages and tests atomic replacement/failure/retry; Task7 covers the actual browser chain.
- The P2 corrections above are written-spec evidence. Tasks1–7 and the two final followups have passed their recorded implementation/review gates; complete-backend and final documentation checkboxes are closed after observed exit0, cleanup and link/diff checks. No runtime-test or migration success is inferred from static review.

## Final frozen acceptance — 2026-10-01

- Configured complete backend command above: **2731 passed / 4 skipped / 3 xfailed / 2 xpassed**, 1729.61s, exit0. Runner removed its own `qms_tenant_review_ff127be7792c47aeaef0602e69d53ca3_test` database. Skips: Redis unavailable1, legacy E2E_MODE endpoints3; existing expected-failure/pass markers retained. The two graph test files excluded by the command remain outside this configured gate.
- All61 final source hashes match after the complete run. Frozen tenant predecessor files/checksums remain unchanged. Final scope/patch evidence for both whole-slice fixes reviewed independently; no unresolved Critical/Important.
- Actual readonly process scenarios include original22 plus new27, including eight real Chromium cases; all are part of this complete backend run. Accepted same-run input reconstruction and new-run current-facts restart do not restore internal plugin memory or execute message text.
- Independent final frontend:78 passed/7 files (5.85s); TypeScript and production build exit0 (7.47s); dedicated E2E TypeScript exit0. Browser result/checkpoint source digests verified complete and within available width.
- Documentation local links and whitespace/scope checked. Worktree retained without staging, commit, merge, push or deployment. Runtime remains off, canonical CAPA capabilities DENY, trusted delivery declarations empty. R4 controlled trial/trusted deployment requires its own design and acceptance.
