# OpenQMS Release Stabilization Design

**Date:** 2026-09-05  
**Branch:** `chore/release-stabilization-20260905`  
**Base:** `main` at `98bca381`  
**Status:** Approved

## 1. Goal

Run a pure stabilization iteration that turns the current feature-complete OpenQMS mainline into a reproducible release-candidate baseline. The iteration cleans workspace artifacts, restores and verifies the local test environment, closes the confirmed collaboration factory-isolation gap, validates fresh-database migration and seed flows, runs the complete AI-enabled E2E suite including CAPA PPT output, and synchronizes project status documentation with verified facts.

This iteration does not add product functionality.

## 2. Scope

### 2.1 Workspace hygiene

- Remove the 25 untracked files whose basenames contain the duplicate suffix `2`, already verified byte-for-byte identical to their tracked originals.
- Preserve the unique untracked plan `docs/superpowers/plans/2026-07-26-fmea-n1-n7-fixes.md`.
- Add a completion notice to that plan identifying the merged N1–N7 implementation commits, then commit it as historical implementation documentation.
- Finish with no unexplained untracked or modified files.

### 2.2 Branch isolation

- Perform all changes on `chore/release-stabilization-20260905`, created from `main` at `98bca381`.
- Do not change or rewrite the `main` branch pointer.
- Do not merge, push, or create a pull request without separate authorization.
- Leave the completed work checked out on the stabilization branch for review.

### 2.3 Environment baseline

- Start or restore Docker and PostgreSQL prerequisites.
- Build the E2E backend image and prove `python-pptx` is installed in the resulting runtime rather than inferring it from requirements files.
- Check PostgreSQL, Redis, backend, and frontend service health.
- Run a pre-product-change baseline check so later failures can be attributed to environment, pre-existing code, or stabilization changes.
- If a test destructively rebuilds the shared suite database, move that test to an existing one-shot isolated-database fixture before continuing; this is test-infrastructure stabilization, not product scope.
- The user explicitly authorized deleting and recreating only the local `qms_test` database, and deleting the diagnostic database `qms_test_stabilization_diag_20260905_1844`, after root-cause evidence showed both are test-only. The development `qms` database remains prohibited.

### 2.4 Collaboration factory isolation

Apply the only product-code change known before the iteration:

- Protect collaboration `heartbeat`, `active-users`, and `leave` endpoints with the existing `RequestScope` and `check_factory_access` mechanisms.
- Resolve the owning document's factory and authorize it before reading or mutating collaboration sessions.
- Preserve the existing document-type support boundary: `fmea` is supported; an unsupported type returns `404` with `detail="unsupported_document_type"`; a missing FMEA returns `404` with `detail="document_not_found"`.
- Treat an inaccessible cross-factory document as not found: return `404` with `detail="document_not_found"` so the response does not disclose document existence.
- Require denial without side effects for each route:
  - rejected `heartbeat` creates no session and does not refresh `last_activity`, action, editing area, user name, or factory on an existing session;
  - rejected `active-users` returns no session/user projection from the inaccessible factory;
  - rejected `leave` deletes no session.
- Apply the same no-side-effect requirements to missing documents and unsupported document types.
- Preserve existing route shapes and successful same-factory behavior.
- Do not add Control Plan collaboration support or refactor unrelated collaboration code in this iteration.

Implementation follows test-driven development:

1. Add failing endpoint tests for cross-factory, missing-document, and unsupported-type requests.
2. For each route, snapshot the relevant collaboration rows before the request and assert both the response contract and unchanged database state afterward.
3. Confirm the tests fail for the expected authorization/validation reason, not from test setup.
4. Add the smallest shared preflight that resolves the document factory, checks scope, and only then dispatches to session read/write/delete logic.
5. Run negative tests plus same-factory positive controls.
6. Run related FMEA tests and the full repository gate.

### 2.5 Database release gate

- Use an isolated test or E2E database for destructive reset operations.
- Verify that a fresh database upgrades to the single Alembic head.
- Run the supported seed process after migration.
- Never delete or rebuild the existing development `qms` database.
- Before removing a database or Docker volume, inspect its resolved name and stop for confirmation if it is not clearly the repository's isolated test/E2E target.

### 2.6 Full verification

Run the following release evidence:

- `make check`
- Fresh-database `alembic upgrade head`
- Seed against the fresh database
- `make e2e-reset`
- Complete AI-enabled E2E using the existing `.env.e2e` configuration
- Targeted verification of CAPA PPT generation and review output
- Targeted verification of System Settings → System Integration menu permissions
- E2E helpers reuse authenticated storage-state tokens and localStorage so the suite exercises production login rate limiting without triggering a self-inflicted 429 cascade; global setup remains the single real five-role UI login path.
- CAPA story setup follows the current D3→D4 gate (four snapshots, done report, valid execution), and D3 Playwright requests retain the `/api` prefix.
- D3 execution validation surfaces the backend's specific 422 detail to the user instead of replacing it with a generic message.
- E2E cleanup removes dynamic CAPA D3 descendants in FK-safe order; D3 endpoints honor a selected effective factory; seed data is visible to the roles/scopes that exercise it.
- The aggregate CAPA story follows the current D7_COMPLETED → D8_GATE_PENDING shell, while mandatory dedicated specs retain doc-gate and D8-close coverage.
- Hit-bearing lateral-diffusion prompts explicitly request the JSON object consumed by `complete_json`; provider fallback must not silently turn prose into a release-blocking parse failure.
- Async E2E assertions read terminal full representations rather than POST summaries, seed recommendation probes with the fields their source consumes, and give LLM/background-worker stories an outer test timeout longer than their internal polling and multi-role workload, while using the established five-second tolerance for cross-process audit timestamps.

The E2E configuration may call the existing Alibaba Bailian model and incur limited external API usage. Secrets must not be printed, copied into documentation, or committed.

#### AI skip gate

A green Playwright exit code is insufficient when required AI scenarios were skipped. With the authorized `.env.e2e` credentials:

- the AI credential guard must pass rather than skip;
- all positive AI scenarios are mandatory, including D3 containment, D4 recommendation, AI draft, doc-gate impact analysis, knowledge sink, and lateral diffusion;
- the only allowed skips are the two inverse, no-credential-only tests whose exact titles are:
  - `no-LLM: D8 close is blocked (422 outcome=blocked)`;
  - `no creds: advice endpoint 422 blocked + import still 200 blocked`;
- any other skipped test, including a positive test that dynamically skips after receiving a provider-not-configured/BLOCKED response, makes the iteration **BLOCKED** even if Playwright exits zero;
- the JSON report is inspected after every full run to compare actual skipped titles with this allowlist.

#### Fixed Playwright execution and retry evidence

Do not inherit environment-dependent retry behavior from `frontend/playwright.config.ts`. Every stabilization run explicitly uses zero automatic retries and retains the first failing trace:

```bash
PLAYWRIGHT_JSON_OUTPUT_FILE=/tmp/openqms-stabilization-20260905/playwright/attempt-1.json \
  make e2e-run TEST_ARGS="--retries=0 --trace=retain-on-failure --reporter=list,json --output=/tmp/openqms-stabilization-20260905/playwright/attempt-1"
```

Before attempt 1, run `make e2e-reset` and verify the deterministic seed state. Preserve attempt 1 JSON, traces, screenshots, videos, and terminal output under `/tmp/openqms-stabilization-20260905/`.

If the only failure is plausibly intermittent external-provider behavior:

1. keep attempt 1 evidence unchanged;
2. run `make e2e-reset` to recreate only the isolated `openqms-e2e` database volume and reseed all mutable test data;
3. re-check the AI credential guard and seed state;
4. rerun the same scope once with paths named `attempt-2` and the same `--retries=0 --trace=retain-on-failure` parameters.

A repeated failure is a release or external-dependency blocker. Product-code fixes require a new clean full-suite attempt after `make e2e-reset`; a passing targeted retry alone is not release evidence.

#### CAPA PPT acceptance

A successful download alone does not pass the CAPA PPT gate because the API intentionally returns a file for `skipped` and `needs_review` outcomes. Acceptance requires all of the following:

1. **File structure:** HTTP 200, PPTX MIME type, non-empty valid OOXML package, exactly 11 slides, and the expected titles for cover, D1–D8, linkage appendix, and generation information. The designated acceptance seed must contain a nonempty structured D1 team so a rule-correct complete report is exercised.
2. **Source consistency:** parse the PPTX with `python-pptx` and compare the document number, title, severity, product line, status, D1–D8 values, and seeded linkage data against the source CAPA/API record. No invented or stale business data is allowed. Each appendix category must render explicitly; an absent association is represented as `无`, not by omitting the category.
3. **Review metadata by carrier:** use response header `X-PPT-Export-Id` to fetch `GET /api/capa/{report_id}/ppt-exports/{export_id}` and locate the `capa_ppt_export` row, then compare only fields exposed by each existing carrier:
   - response headers: export ID, `review_status`, and `review_rounds` must match the query API and database;
   - generation-information slide: version, `review_status`, and `review_rounds` must match the query API and database;
   - query API: export ID, version, `review_status`, `review_rounds`, and `review_report` must match the database row;
   - `review_report` is compared only between the query API and database because neither response headers nor the slide exposes it.
4. **Review outcome:** `review_status` must be `passed`; rounds must be in `1..3`; the persisted report must contain valid `issues` and `suggestions` lists consistent with the passing outcome. Review prompts must respect the render lifecycle: generation metadata is filled after review, and explicit no-link appendix values are valid when the database has no corresponding associations. UI feedback must interpolate the numeric review round rather than expose a raw localization placeholder.

For this AI-enabled release gate, `review_status=skipped` is **BLOCKED** because it proves the configured review agent did not run. `review_status=needs_review` is also **BLOCKED** pending an explicit human-review workflow outside this iteration; the presence of a downloadable file does not downgrade either state to pass.

### 2.7 Documentation synchronization

Update `PROGRESS.md` and `docs/ROADMAP.md` to reflect only verified facts:

- Current date, branch, and base commit
- PRs and feature epics already merged to main
- Current release-stabilization stage
- Latest backend, frontend, migration, and E2E evidence
- Confirmed blockers and remaining technical backlog
- Removal of stale statements that still describe already-merged branches or completed work as pending

The historical E2E reports remain immutable except for already-approved clarifications.

## 3. Execution Stages

The work proceeds through serial gates.

### Stage 1 — Workspace and branch baseline

1. Record branch, commit, and status.
2. Remove only verified identical duplicates.
3. Annotate and add the unique N1–N7 plan.
4. Confirm the diff contains no product-code changes.

### Stage 2 — Environment recovery and pre-change baseline

1. Restore Docker/PostgreSQL.
2. Build and inspect the E2E backend image.
3. Verify service health and `python-pptx` import.
4. Run the initial `make check`.
5. Classify every failure before changing code.

### Stage 3 — Collaboration isolation fix

1. Add cross-factory, missing-document, and unsupported-type tests with same-factory controls.
2. Demonstrate the current response and side-effect failures.
3. Add factory-scope preflight enforcement to all three routes.
4. Assert rejected heartbeat does not insert/refresh, rejected active-users leaks no users, and rejected leave does not delete.
5. Run targeted and related tests.

### Stage 4 — Fresh-database gate

1. Confirm the selected database and volume are isolated.
2. Reset only the isolated target.
3. Upgrade to Alembic head.
4. Seed and run database-dependent checks.

### Stage 5 — Full release verification

1. Run `make check`.
2. Reset and seed the isolated E2E stack.
3. Run all Playwright scenarios with the fixed zero-retry, retain-on-failure-trace parameters and JSON evidence paths.
4. Verify that the skipped-title set exactly matches the two no-credential inverse-test allowlist entries; any unexpected skip blocks release.
5. Verify CAPA PPT file structure, source consistency, persisted review metadata, and mandatory `passed` review outcome.
6. Verify integration-menu cases explicitly.
7. Diagnose failures without broadening product scope unnecessarily.

### Stage 6 — Documentation and delivery

1. Update project status documents from collected evidence.
2. Review the final diff for stabilization-only scope.
3. Run the final complete release gate after documentation changes.
4. Commit completed work in coherent units.
5. Report results and unresolved release blockers without merging or pushing.

## 4. Failure Classification

### 4.1 Environment failure

Examples include Docker not running, port collisions, missing image dependencies, or database connection refusal. Repair the environment or build configuration and rerun the same command. Do not classify the application as failing until the test actually executes.

### 4.2 Stabilization-change regression

A failure caused by the collaboration or documentation changes is fixed or the change is reverted. Do not extend the implementation into adjacent refactors.

### 4.3 Pre-existing product defect

Capture the command, scenario, error, and impact. A small release-blocking defect may be fixed with a new failing test and minimal patch. A defect requiring new business rules, architecture, schema, or substantial UI work is recorded as a blocker or follow-up rather than being improvised into this iteration.

### 4.4 External dependency failure

Record provider response and timing without exposing credentials. Use only the fixed zero-automatic-retry procedure in section 2.6: preserve attempt 1, restore the isolated E2E dataset with `make e2e-reset`, and permit one manually identified attempt 2. Repeated failures remain visible in the final status.

## 5. Data and Secret Safety

- Destructive commands are limited to confirmed test/E2E databases and volumes.
- The existing development `qms` database and user data are not reset.
- `.env.e2e` is runtime input only and must remain outside the Git diff.
- Logs and documentation must not contain API keys, tokens, passwords beyond repository-documented demo credentials, or full provider configuration secrets.
- Existing external LLM configuration is used as-is unless an environment-only correction is required; production settings are not changed.

## 6. Evidence to Retain

The final stabilization report records:

- Branch and base/current commit
- Final `git status`
- Docker/E2E service health
- Alembic current and head revisions
- Fresh migration and seed result
- Backend pytest passed/failed/skipped counts
- Frontend typecheck and build result
- Playwright command line, attempt number, JSON report, passed/failed/skipped counts, skipped titles, and retained trace paths
- CAPA PPT structure/source comparison plus carrier-aware metadata checks: headers and slide against API/database on their exposed fields, and `review_report` between API and database only
- Collaboration response contracts and before/after database evidence proving cross-factory, missing-document, and unsupported-type denials have no side effects
- Any unverified item or release blocker

## 7. Explicit Non-Goals

- New product modules or workflow behavior
- Copilot UI or new Agent tools
- Multi-tool LLM loop implementation
- Redis business caching
- Broad frontend bundle optimization
- Alembic squash or migration architecture changes
- Opportunistic refactors or formatting changes
- Implementing old CAPA doc-gate findings without current reproduction
- Changing E2E assertions merely to obtain a green run

## 8. Definition of Done

The stabilization iteration is complete only when all applicable conditions are satisfied:

- [ ] The 25 verified duplicate files whose basenames contain the suffix `2` are removed.
- [ ] The unique N1–N7 plan is annotated and tracked.
- [ ] All three collaboration endpoints enforce factory scope before session access.
- [ ] Cross-factory, missing-document, and unsupported-type requests satisfy their `404` contracts without inserting, refreshing, exposing, or deleting collaboration sessions; same-factory paths pass.
- [ ] The destructive `test_spc_fmea_match.py` fixture uses a one-shot isolated database and no longer removes migration-only DDL or seed data from `qms_test`.
- [ ] A fresh isolated database upgrades to a single Alembic head and seeds successfully.
- [ ] `make check` completes successfully.
- [ ] Hit-bearing lateral diffusion returns structured JSON, closes successfully with the configured provider, and executes all dedicated positive tests.
- [ ] Dynamic D3 E2E cleanup is FK-safe/idempotent, selected-factory D3 access is isolated, and seeded lateral/supplier records are visible to their intended test roles.
- [ ] Required D3/CAPA E2E paths retain `/api`, satisfy the current D3 gate, surface specific execution-validation details, and complete without a login 429 cascade.
- [ ] The complete AI-enabled E2E suite runs with zero automatic retries and retained JSON/trace evidence.
- [ ] The only skipped Playwright tests are the two explicitly allowlisted no-credential inverse scenarios; every positive AI scenario runs.
- [ ] CAPA PPT has 11 valid, source-consistent slides; response headers match API/database export ID and review fields; the generation slide matches API/database version and review fields; API and database match on all persisted fields including `review_report`; `review_status=passed` and `review_rounds` is in `1..3`; `skipped` or `needs_review` blocks release.
- [ ] System Integration menu permission scenarios pass.
- [ ] `PROGRESS.md` and `docs/ROADMAP.md` match verified repository state.
- [ ] The final diff contains only stabilization-related changes.
- [ ] The stabilization branch contains coherent commits and remains unmerged/unpushed pending authorization.

If any mandatory gate cannot pass, the iteration ends in **BLOCKED**, not complete, with reproducible evidence and the smallest next action documented.
