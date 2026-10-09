# D4 Text Redaction Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Inline execution follows the user's confirmed continuation; no multi-agent orchestration.

**Goal:** Add a default-off, current-authorized employee D4 redaction-candidate preview without business writes or plugin/model body delivery.

**Architecture:** A pure bounded redactor produces only restricted candidates. A module-owned service reads a tenant-bound readonly snapshot, validates declared FMEA sources and compares a fresh final source version/current authority before safe audit commit. A strict ordinary-user API and short-lived UI withdraw stale or denied content; R4a's protocol/catalog/worker remain unchanged.

**Tech Stack:** Existing Python/FastAPI/Pydantic/SQLAlchemy/PostgreSQL and React/TypeScript/Ant Design, pytest/vitest and installed Playwright/Chromium. Stdlib matching/HMAC only; no new dependency or migration.

**Status (2026-10-07):** Six tasks implemented and accepted. Frozen full backend and resumed actual `make check` each report **2926 passed /4 skipped /3 xfailed /2 xpassed**, exit0; frozen frontend **87 passed /8 files**, build/type/E2E tsc pass. All **1214** source/config hashes unchanged. Default closed/restricted/no external delivery unchanged; no commit/stage/push/merge/deploy. Exact evidence and preserved-resource notes below.

## Global Constraints

- Approved [design](../specs/2026-10-05-capa-d4-text-redaction-foundation-design.md), user confirmation on 2026-10-06. Every task includes all its requirements.
- Only `d4_root_cause`, verification `root_cause_text`, `result`; never load attachment/title/team/D2/D5 text or FMEA graph/body for output.
- Fixed `restricted`, `redaction_candidate`, `not_approved`, external_delivery_allowed=false; no new plugin capability/profile, model, declassification, raw exception, search/index/outbox or business update.
- replacement_terms: strict list 0–50, each stripped 1–100 characters, total UTF-8 <=8 KiB; no controls/duplicates/custom regex or templates. Request <=64 KiB before parse.
- <=200 verification rows, each text <=64 KiB, all text <=256 KiB, each source_ref <=2 KiB. Budget before materializing text/JSON, no partial/truncated preview.
- Feature `CAPA_D4_TEXT_PREVIEW_ENABLED=false`; hide only three preview paths before tenant/auth/body/DB. Ordinary user JWT, current CAPA/FMEA VIEW and current object scopes; runtime credentials never authorize.
- Lifetime 30 seconds; visible open preview checks source/rule version every2 seconds. Denial, network uncertainty, expiry, source/identity/target/terms change, hide/close abort and clear; no browser storage or stale re-publication.
- Safe preview audit only object/user/factory/rule/source-version/outcome. No raw, candidate text, terms/digest, matched substring, free error text or exception payload in audit/log/error responses.
- Preserve cumulative R1–R4a and main edits. No commit/stage/push/merge/deploy, enabling user environments, shared reset/container lifecycle or browser install. Reviews/evidence replace commits.

## Task 0 — Owned baseline and evidence

**Files:** temporary runner `/tmp/openqms_tenant_checks.py` already exists; new owned evidence directory `/tmp/openqms-d4-preview-Q5qVsWDl`; plan/PROGRESS only.

- [x] Read approved design, PROGRESS, relevant DECISIONS and existing current-access/source-ref/readonly code. CodeGraph became `database disk image is malformed`; use already-known files without repairing the index.
- [x] Snapshot original git status/diff/untracked list; original R4a freeze confirms 1197 unchanged source/config hashes. The existing runner still generates `openqms_r4a_<UUID>_test` for compatibility with normal-policy fixtures; each run is new and cleanup limited to its own database. Nested original migration fixtures remain owned-only.
- [x] Read current backend baseline result from `baseline-backend.log` (R4a147 plus D4 API/verification/gate groups), frontend baseline from `baseline-frontend.log`, inspect actual exit codes before touching existing source. If failure, diagnose before attribute changes.

Run owned checks from worktree root with:

```sh
PG15_CONTAINER=agent-module-permission-kernel-db-1 /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python /tmp/openqms_tenant_checks.py tests/services/agent/permissions tests/services/agent_runtime/test_trial_policy.py tests/services/agent_runtime/test_trial_admission.py tests/services/agent_runtime/test_trial_runtime.py tests/services/agent_runtime/test_trial_revoke.py tests/services/agent_runtime/test_trial_launcher.py tests/api/test_trial_peer.py tests/api/test_trial_runtime.py tests/api/test_trial_revoke.py tests/e2e/test_agent_local_trial_process.py tests/e2e/test_agent_local_trial_browser.py tests/capa/test_capa_verification_service.py tests/capa/test_capa_verification_source_ref.py tests/capa/test_capa_api_d4_d5.py tests/capa/test_capa_d4_gate.py -q -rs
make check-frontend
```

## Task 1 — Pure rules and strict contracts

**Files:** Create `backend/app/services/capa_d4_redaction.py`, `backend/app/schemas/capa_d4_text_preview.py`, `backend/tests/capa/test_d4_redaction.py`, `backend/tests/capa/test_d4_text_preview_schemas.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class RedactedText:
    text: str | None
    match_counts: dict[str, int]

RULE_VERSION = "capa.d4.redaction.v1"
def validate_terms(values: list[str]) -> tuple[str, ...]: ...
def redact_text(text: str | None, terms: tuple[str, ...]) -> RedactedText: ...
```

DTOs `D4PreviewRequest(replacement_terms=[])`, `D4PreviewField(field,verification_id,redacted_text,source_status,source_ref,match_counts)`, `D4TextPreview(report_id,rule_version,source_version,generated_at,expires_at,fields, fixed classification fields)`, `D4PreviewVersion(report_id,source_version,rule_version)` and `D4PreviewAvailability(enabled: Literal[True])`. Field literal set `d4_root_cause|root_cause_text|result`; source_status `unverified|validated_reference`; source_ref only canonical server-owned FMEA/node/version metadata or None. Rule count keys only literal,credential,url,email,id_number,mobile,phone; nonnegative strict ints. Responses forbid extra fields; caller cannot set classification.

- [x] Add independently derived literal cases first:

```python
@pytest.mark.parametrize("raw,terms,want", [
    ("联系 sam@example.test，扭矩 10 N·m", (), "联系 [邮箱已遮盖]，扭矩 10 N·m"),
    ("电话 +86 138-0013-8000，温度85°C", (), "[手机号已遮盖]，温度85°C"),
    ("客户 A+B 与零件 DC-100", ("A+B",), "客户 [指定词已遮盖] 与零件 DC-100"),
    ("访问 https://example.test/private?id=secret", (), "访问 [URL已遮盖]"),
])
def test_fixed_intervals_preserve_other_technical_text(raw, terms, want):
    assert redact_text(raw, terms).text == want
```

Also exact overlapping literal/credential/URL cases, longest literal first, repeated matches, fullwidth/casefold/decomposed accent mapping, None/empty, credential value/Bearer/JWT whole span, pattern boundary false positives. Metadata exposes only count keys, not matched strings. Normalize matching only; preserve unmatched original characters/units.

- [x] Strict DTO tests reject bool/integer terms, blank/controls, duplicate canonical terms, >50/>100/>8KiB, unknown request authority/labels; assert fixed restricted markers on every successful output. Run both nodes and observe feature-missing RED, not setup failure.
- [x] Implement a bounded canonical matching view with original-index interval map (NFKC/casefold clusters for supported equivalences), escaped literal searches and static linear patterns. Collect all spans on original input, prioritize literal→credential/url→other formats, merge overlapping spans and replace once; do not rescan markers. validate_terms shares canonical dedupe and literal semantics, no user regex execution. DTO validators enforce all explicit bounds.
- [x] Re-run both nodes to GREEN; review no false anonymization claim, no mutated original and no credential metadata.

## Task 2 — Current authorization and bounded readonly source snapshot

**Files:** Create `backend/app/services/capa_current_access.py`, `backend/app/services/capa_d4_text_preview.py`, `backend/tests/capa/d4_preview_support.py`, `backend/tests/capa/test_d4_text_preview.py`. Modify only current helper definitions/imports in `backend/app/services/agent_runtime/task_service.py`.

**Interfaces:** Shared access exports `require_business_namespace(db)`, `current_capa_access(db,scope)->(levels,factories,lines)`, `capa_target_filters(query,factories,lines)`, `current_capa_target(db,report_id,factories,lines)`. Preserve old task_service `_require_namespace`, `_current_access`, `_target_filters`, `_target` names as re-exports/wrappers so existing callers/test race hooks keep their contract. Move the established bodies, do not rewrite RBAC or restructure runtime.

Preview service exports frozen snapshot/field dataclasses, `read_snapshot(report_id,*,binding,engine=None)`, `source_version(snapshot)->str`, `get_version(db,scope,report_id)->D4PreviewVersion`, `create_preview(db,scope,report_id,request)->D4TextPreview`, `availability(db,scope,report_id)`. `PreviewConflict`/`PreviewSourceLimit` are ValueError subclasses with constant diagnostics. Audit commit stays service-owned and only happens after full final check.

- [x] Build owned real-commit fixture by reusing `owned_local_trial` infrastructure from `tests/e2e/agent_local_trial_harness.py` (only settings/engine/lifecycle/normal logins, no policy monkeypatch). Seed synthetic D4 text/verification/FMEA known nodes before actions; no business commands in preview. session()/client are actual production TenantSession/get_db. Add tests for output candidate masking and restriction, scalar audit allowlist, business/outbox snapshots unchanged, ordinary current viewer scope, current role inactivity and CAPA level withdrawal.

```python
@pytest.mark.asyncio
async def test_preview_only_mutates_safe_audit(owned_d4_preview):
    owned = owned_d4_preview
    before = await owned.business_snapshot()
    output = await owned.preview(["机密客户"])
    assert output.data_class == "restricted" and not output.external_delivery_allowed
    assert "机密客户" not in str(output.model_dump())
    assert await owned.business_snapshot() == before
    fields = (await owned.preview_audits())[0]
    assert set(fields) == {"report_id", "rule_version", "source_version", "outcome"}
```

- [x] Add budget cases using 201 rows, >64KiB one text, >256KiB combined and >2KiB reference; assert no partial result/success audit and query boundary does not first materialize over-budget text/JSON. Declared FMEA refs: current FMEA VIEW, actual object coordinates, linked report, FailureCause existence and source version; malformed/unknown/invisible source rejects entire preview/version with no source/count details. Unknown None ref remains unverified/restricted, not a permission claim. Observe RED.
- [x] Extract access helpers preserving namespace/current scalar semantics and re-exports; add a source snapshot transaction that sets RR/READ ONLY before binding. Explicit metadata/count/octet_length query comes before bounded text fetch. FMEA node existence uses SQL JSONB EXISTS, returns only bool/version/coordinates, never graph/body/title. Source hash domain `openqms.capa.d4-text-source.v1` HMAC-SHA256 of canonical complete snapshot + captured tenant/generation, with server secret, no raw hash/term hash.
- [x] After redaction, refresh current user/factory/line, perform final fresh snapshot/reference authorization and full source-version/coordinate comparison, then add safe audit and commit. Any final denial/conflict/commit failure means no successful content; read versions do not write preview audit. A successful candidate refers to the validated snapshot, not permanent authorization; later business changes are detected by version polling. Do not expand the preview contract into locking/reworking all unrelated business writers.
- [x] Real Events test holds processing after initial RR snapshot, commits each permission/field/child/ref/node/coordinate/generation change in another session, then releases; assert denied/stale and no audit. Real rollback injection verifies audit failure cannot commit or return output. Compare source versions when order alone changes (stable), contents/row set/reference version change (different); HMAC varies with tenant/generation and uses no terms.
- [x] Run new service nodes plus existing permissions/runtime/task/verification source/gate groups to GREEN. Preserve old `_current_access` hooks and R4a disabled/current-authority behavior, review extraction diff against baseline.

## Task 3 — Default-off ordinary-user API and content-safe input/error boundary

**Files:** Create `backend/app/api/capa_d4_text_preview.py`, `backend/tests/api/test_d4_text_preview.py`. Modify config/main/tenant_context only flag/router/early path guard.

- [x] First test actual global app/middleware off-before-tenant/auth/body/DB with invalid peer/slug/token/UUID/body. Test these exact three paths:

```python
@pytest.mark.asyncio
async def test_off_paths_do_not_echo_or_read_private_input(monkeypatch):
    monkeypatch.setattr(settings, "CAPA_D4_TEXT_PREVIEW_ENABLED", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for tail in ("", "/version", "/availability"):
            response = await client.post("/api/capa/not-uuid/d4-text-preview"+tail,
                content='{"replacement_terms":["SECRET-TERM"]}', headers={"X-Tenant-ID":"never-resolved"})
            assert response.status_code == 404 and "SECRET-TERM" not in response.text
```

- [x] Add actual owned API tests normal login/permission, runtime/installation credentials rejected, unknown fields and bad terms/UUID are constant422 without default validation input, raw body >64KiB constant413 before parse, source/budget/conflict constant errors and no partial DTO. No fault/error logs contain markers; no body query strings accepted.
- [x] Observe RED. Add flag false and an exact preview path/prefix matcher to early tenant middleware (only matching paths, no unrelated CAPA change). Ordinary dependencies remain current RequestScope/get_db.
- [x] Use router-scoped APIRoute handler to count bounded body stream, catch RequestValidationError locally and return only constant diagnostics; do not install global exception changes. Thin endpoints call service methods, map known errors and rollback on service failure; no source text in SQL/exception formatting. Bad runtime JWT cannot select ordinary identity.
- [x] Re-run new API, baseline CAPA D4 API/verification and runtime default-off matrices. Verify availability never loads text/refs and default-off discovery yields404; commit failure cannot return candidate success. Review ordinary-user boundary separately from redactor.

## Task 4 — Strict frontend API and readonly short-lived UI

**Files:** Create `frontend/src/types/capaD4TextPreview.ts`, `frontend/src/api/capaD4TextPreview.ts`, `frontend/src/api/capaD4TextPreview.test.ts`, `frontend/src/components/capa/D4TextRedactionPreview.tsx`, corresponding test. Modify only D4 mount/import in CAPADetailPage and its relevant test expectations.

**Interfaces:** `getD4PreviewAvailability(reportId,signal)`, `getD4PreviewVersion(reportId,signal)`, `createD4TextPreview(reportId,{replacement_terms},signal)` parse fixed readonly DTOs and validate actual report/rule/version/expiry/field/source/count shape. Component receives `reportId` and current identity/scope context; it owns only in-memory draft/result, never business callbacks or storage.

- [x] API RED cases real parser rejects expanded classification, unknown field/source type, bad digest/expiry/IDs/counters or target mismatch; metadata isn't accepted by cast only. Mock transport only, parse actual response shape through the real adapter.
- [x] Component RED with fake timers and controlled real adapter transport: hidden when404, only availability before explicit action, generate unverified restricted candidate, renders literal script/URL as text, no apply/save controls, terms editing invalidates result, 2s version check,30s expiry and failed/denied/version mismatch clear, close/hidden/auth/report/factory/line changes abort/clear, late old Promise cannot republish. No storage writes. Tests assert actual rendered output and intercepted requests, not mock existence.

```tsx
it('clears private text on uncertain version and prevents late response', async () => {
  const view = render(<D4TextRedactionPreview reportId={REPORT_ID} />);
  await user.click(screen.getByRole('button', { name: '正文脱敏候选预览' }));
  await user.click(screen.getByRole('button', { name: '生成受限候选' }));
  expect(await screen.findByText('受限技术叙述')).toBeVisible();
  versionRequest.reject(new Error('network unavailable'));
  await act(() => vi.advanceTimersByTimeAsync(2000));
  expect(screen.queryByText('受限技术叙述')).toBeNull();
});
```

The test fixture `versionRequest` is a controlled transport deferred value; complete DTO fixtures come from the new type contract. Configure it before the timer-triggered request and clean timers/controllers per test.

- [x] Implement existing Ant Design readonly Modal/Alert/textarea/plain text style; no new visual library, charts, model controls or AIDraftPreview reuse. Discover with availability only, key requests by identity/target/scope/draft epoch, maintain a separate expiry timer from polling and clear on uncertainty. Terms removed on closed/hidden/identity changes, not persisted.
- [x] Mount only in real D4 section without restructuring CAPADetailPage. Run API/component/page tests, frontend tsc/build and dedicated E2E tsc; review no new plaintext browser persistence or automatic body fetch.

## Task 5 — Actual browser, source withdrawal and existing readonly regressions

**Files:** Create `backend/tests/e2e/test_d4_text_preview_browser.py`, `frontend/e2e/specs/capa/d4-text-preview.spec.ts`; extend owned frontend Playwright config to explicit new spec while preserving old R3/R4a file selections. Extend only test harness infrastructure for new actual router/settings/user/FMEA seed.

- [x] Own fresh complete tenant, actual lifespan/get_db/login/APIs, allocated Vite/backend ports, already-installed Chromium. Enable only fixture-owned feature flag. Test employee UI literal terms→restricted preview, exact safe masking/untouched technical units, no business changes. No fake redaction/authorization/preview product response and no shared reset/global E2E setup.
- [x] Actual committed source changes/version polling clear and explicit regeneration, generation and CAPA/FMEA source withdrawal suppress all content/counters, no-network version check withdraws stale preview, page hidden/close stops work. Browser network faults use route.abort at wire only; all successful data is real backend output. Side fixture control endpoints live only in allocated app and require owned nonce.
- [x] No model/provider/external page calls; no Node/browser automatic install/skip. Missing executable fails with explicit existing executable override. Kill/wait only own subprocesses, clean own directory/port/tenant.
- [x] Run new browser plus R4a normal process/browser and old R2/R3 process/eight browser scenarios; explicit spec file selection prevents accidental cross-running or manufactured skip. Product defects found by integration keep the failing scenario, then focused RED→GREEN without weakening privacy or budgets.

## Task 6 — Operations, freeze, full acceptance and handoff

**Files:** Create `docs/development/capa-d4-text-preview.md`. Update related architecture/permissions/development/services/API/component README, design status, plan ledger and worktree PROGRESS/roadmap; main pointer only when authorized context permits.

- [x] Document ordinary employee internal candidate, restricted/no declassification/no external delivery, source_ref not authorization, rule limitations, explicit terms, exact budgets, default off, constant validation errors, source/rule version and30s expiry/2s polling. Distinguish preview from editing/approval and R4a metadata output; no raw exception or production capability implied.
- [x] Verify complete spec coverage/task interfaces/no unfinished placeholders in plan; record per-task actual RED/GREEN/review/evidence, not historical counts. Independent code/spec review only after actual code exists, via the requesting-code-review skill if needed; no broad architecture delegation.
- [x] Freeze new/current relevant sources/config once all focused/browser gates pass. Run configured full backend in new owned database:

```sh
PG15_CONTAINER=agent-module-permission-kernel-db-1 /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python /tmp/openqms_tenant_checks.py tests -q -rs --ignore=tests/test_graph_sync_worker.py --ignore=tests/test_graph_projection.py
make check-frontend
node frontend/node_modules/vitest/vitest.mjs run --root frontend src/api/capaD4TextPreview.test.ts src/components/capa/D4TextRedactionPreview.test.tsx src/pages/capa/CAPADetailPage.test.tsx src/api/agentTasks.test.ts src/api/client.agentTasks.test.ts src/components/agent
node frontend/node_modules/typescript/bin/tsc --project frontend/tsconfig.e2e.json --noEmit
```

- [x] Read actual complete exits/counts/reasons, configured graph exclusions, all real browser results, safe audit and complete business snapshots, cleanup evidence and frozen hash comparison. A source change after freeze requires affected recheck, not an unchanged-evidence claim. Pre-existing disposable databases are never guessed to be ours/deleted.
- [x] Local doc links/whitespace/diff checks, status/ledger exact final evidence and remaining limits. No commit/stage/push/merge/deploy; preserve worktree. R4b-1 complete only when all applicable new gates pass, body plugin/model/attachment/production still closed.

## Execution ledger

2026-10-06: written design approved by explicit user confirmation; inline continuation. Original R4a1197 sources unchanged at start. Fresh owned backend/frontend baseline evidence is under `/tmp/openqms-d4-preview-Q5qVsWDl`. CodeGraph reported a malformed index; it was not repaired. Temporary classifier connectivity failure recovered on retry without permission override.

### Observed implementation and acceptance

- Baseline: related R4a/D4 backend **186 passed** (133.79s, exit0); frontend type/build exit0; parent owned database cleaned.
- Task1 pure rules/strict contracts: RED **42 failed** for missing implementation; GREEN **42 passed**. Literal meta-characters, normalization/original span mapping, overlap union, format/credential whole spans, empty input, UTF-8 bounds and fixed restricted DTOs verified.
- Task2 real source service: initial fixture-registration error was not treated as valid RED. The two premature new implementations were removed; fixture import corrected, observed actual missing-service RED **1 failed**, then reimplemented to GREEN **17 passed** (60.44s). Fresh namespace/identity/object scope shared with existing runtime wrapper names. Real commits cover identity/coordinate/source withdrawal, all budgets, field/child/reference version races and no success audit. Shared service/runtime/task/control regression **643 passed** (1049.39s, exit0). Added audit-commit rollback and budget-before-materialization tests.
- Task3 actual API: RED **4 failed**, GREEN **4 passed** (11.60s, exit0). Default-off404 precedes tenant/auth/body/DB, ordinary employee credentials only, safe422 without private input echo, raw64KiB413, exact empty queries and uniform source denials. Body budget and exception mapping are route-local, not global changes.
- Task4 actual adapters/UI: exact preview client exception RED for factory injection/refresh replay; parser/client GREEN **8 passed**. Readonly modal initially retained private content during Ant close motion; immediate conditional unmount removes closed/hidden content. Stable accessible generation label fixes loading-icon name changes. Related API/client/component/page GREEN **39 passed**, then clock-skew RED and capped local30s lifetime; GREEN **40 passed**. Type/build/E2E tsc exit0. No body/terms browser persistence, HTML execution or business callbacks.
- Actual Chromium new employee scenario **1 passed** (19.06s): normal login, explicit literal terms, restricted masked output preserving technical units, live version change, declared FMEA source withdrawal, denied regeneration, restored source, real network failure and hide/close withdrawal. No fake success/authorization output, browser install or shared lifecycle/reset. Complete business snapshots unchanged except explicit fixture writes.
- New/old readonly process/browser focused run **119 passed** (385.60s), including normal R4a processes and old R3 eight Chromium scenarios; configured scripts select their own spec, no manufactured skip.
- Independent review found private terms surviving server-side loss and unnecessary verification metadata in source SELECT/HMAC. Verified first finding with RED **3 failed /5 passed**; second query-whitelist RED **1 failed**. Reviewer corrected an unsupported characterization: method/conclusion are constrained enums, not arbitrary narrative; minimization still applies. Fixed poll/generation authority failure term clearing and removed method/conclusion/is_verified from snapshot SELECT/canonical content without changing R4a. Post-fix real service/API/Chromium **25 passed** (94.36s), frontend related **40 passed**, build/type/E2E tsc exit0. Synthetic transport errors now preserve real Axios config so endpoint guards are tested honestly.

### Frozen gate — 2026-10-06

- Frozen **1214** source/config files; source hash comparison **0 changed**. Fixed stdlib worker hash unchanged: `ab4645b4a57a55f2d17117fad64bf1aabac8a450e34f445c8a718449b039ed54`.
- Complete command: `PG15_CONTAINER=agent-module-permission-kernel-db-1 /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python /tmp/openqms_tenant_checks.py tests -q -rs --ignore=tests/test_graph_sync_worker.py --ignore=tests/test_graph_projection.py`. Fresh fully migrated parent `openqms_r4a_88b2c0dcc4b845b69217845c8c950dfc_test`, **2926 passed /4 skipped /3 xfailed /2 xpassed /5 warnings**, **2067.61s**, **exit0**. Parent database dropped; full log `final-backend.log` in the evidence directory.
- Exclusions match Makefile's two existing graph exclusions. Skips: Redis unavailable in agent memory(1), old E2E_MODE endpoints not registered/seeded(3). New D4 and existing Agent actual browsers ran, not skipped. Existing non-strict MES transaction-visibility/SKIP LOCKED expected-failure/pass markers retained. Existing Pydantic/websocket deprecations remain.
- Frozen frontend `make check-frontend` exit0; related frontend **87 passed /8 files**, dedicated E2E tsc exit0. JSDOM pseudo-element getComputedStyle notice is not a skipped browser scenario; actual Chromium gate passed.
- Current evidence checker: **1214 unchanged**, **60 valid local links**, `git diff --check` exit0. No owned CLI/plugin/Vite/Playwright/runner processes left after that gate. Four matching disposable database names were preserved as pre-existing (same Sept27/28 directory birth dates already verified in R4a); no existing/shared/business DB deleted/reset.

### Resume gate — 2026-10-07

- On resume, source/config hashes again matched the frozen set. Run actual `make check` through `/tmp/openqms-d4-preview-Q5qVsWDl/make-check-owned.py`, creating a NEW runner-owned random `openqms_r4a_<UUID>_test` and setting TEST_DB/TEST_DATABASE_URL for the real Makefile targets, never shared qms_test. Output: `resume-make-check.log` in the evidence directory. This actual Makefile consistency gate completed with **2926 passed /4 skipped /3 xfailed /2 xpassed /5 warnings**, **2174.36s** (36:14), **exit0**, frontend type/build pass (Vite7.16s). New parent `openqms_r4a_09791dcc95f1466aa05736ed79930a11_test` was dropped. The same known Redis/E2E/MES reasons remain; new body/old Agent browsers ran, not skipped. Source comparison again reports1214/0changed,60/0invalid local links and clean diff. No owned runner/plugin/Vite/Playwright processes remain. Four same pre-existing Sept27/28 disposable databases remain untouched. This fresh run satisfies resumed clock-in/clock-out checks on unchanged code.
- Only documentation/status/checkbox handoff changes occur during that rerun. No commit/stage/push/merge/deploy or user-environment enablement. Classification stays restricted; source body/terms are not cached, persisted as preview results, indexed, sent to plugin/model or written into business records. Remaining attachment/raw-exception/declassification/SDK/deployment/production gates stay closed.

