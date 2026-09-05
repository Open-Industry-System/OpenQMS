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

- Remove the 25 untracked ` 2.*` files already verified byte-for-byte identical to their tracked originals.
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

### 2.4 Collaboration factory isolation

Apply the only product-code change known before the iteration:

- Protect collaboration `heartbeat`, `active-users`, and `leave` endpoints with the existing `RequestScope` and `check_factory_access` mechanisms.
- Resolve the owning document's factory before reading or mutating collaboration sessions.
- Reject cross-factory requests without exposing inaccessible document data.
- Preserve existing route shapes and successful same-factory behavior.
- Do not refactor unrelated collaboration code.

Implementation follows test-driven development:

1. Add failing cross-factory endpoint tests.
2. Confirm the tests fail for the expected authorization reason.
3. Add the smallest scope enforcement change.
4. Run negative and positive collaboration tests.
5. Run related FMEA tests and the full repository gate.

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

The E2E configuration may call the existing Alibaba Bailian model and incur limited external API usage. Secrets must not be printed, copied into documentation, or committed.

If an external model call times out intermittently, retain the first failure evidence and retry once. A repeated failure is recorded as a release blocker or external-dependency blocker; it is not converted into a pass by skipping the scenario or weakening assertions.

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

1. Add cross-factory failure tests and same-factory controls.
2. Demonstrate the current failure.
3. Add factory-scope enforcement to all three routes.
4. Run targeted and related tests.

### Stage 4 — Fresh-database gate

1. Confirm the selected database and volume are isolated.
2. Reset only the isolated target.
3. Upgrade to Alembic head.
4. Seed and run database-dependent checks.

### Stage 5 — Full release verification

1. Run `make check`.
2. Reset and seed the isolated E2E stack.
3. Run all AI-enabled Playwright scenarios.
4. Verify CAPA PPT and integration-menu cases explicitly.
5. Diagnose failures without broadening product scope unnecessarily.

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

Record provider response and timing without exposing credentials. Retry one intermittent failure. Repeated failures remain visible in the final status.

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
- Playwright passed/failed/skipped counts
- CAPA PPT generation and structural review result
- Collaboration cross-factory rejection and same-factory success results
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

- [ ] The 25 duplicate ` 2.*` files are removed.
- [ ] The unique N1–N7 plan is annotated and tracked.
- [ ] All three collaboration endpoints enforce factory scope.
- [ ] Cross-factory collaboration requests are rejected and same-factory paths pass.
- [ ] A fresh isolated database upgrades to a single Alembic head and seeds successfully.
- [ ] `make check` completes successfully.
- [ ] The complete AI-enabled E2E suite runs; every failure is fixed or explicitly classified as a release blocker.
- [ ] CAPA PPT generation is exercised successfully.
- [ ] System Integration menu permission scenarios pass.
- [ ] `PROGRESS.md` and `docs/ROADMAP.md` match verified repository state.
- [ ] The final diff contains only stabilization-related changes.
- [ ] The stabilization branch contains coherent commits and remains unmerged/unpushed pending authorization.

If any mandatory gate cannot pass, the iteration ends in **BLOCKED**, not complete, with reproducible evidence and the smallest next action documented.
