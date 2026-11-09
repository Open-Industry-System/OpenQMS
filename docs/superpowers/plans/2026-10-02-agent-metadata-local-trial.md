# Agent R4a Metadata Local Trial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the accepted D4 metadata-only runtime configurable and permanently revocable for an explicitly scoped trial on a trusted local host.

**Architecture:** An immutable startup policy selects a server-owned canonical capability profile at an exact tenant/installation/executor/report binding. Existing current permission intersections and final delivery checks remain authoritative. A credential-epoch fence revokes the trial atomically, while a fixed launcher and loopback ingress limit the first delivery environment.

**Tech Stack:** Existing FastAPI, Pydantic, SQLAlchemy, PostgreSQL 15, Python stdlib, pytest, React/TypeScript and installed Playwright/Chromium. No new provider, SDK, dependency or database migration.

**Status (2026-10-05):** User confirmed the reviewed written design and six-task continuation and authorized owned database lifecycles. R4a metadata-only local trial is implemented and fully verified: frozen backend `2859 passed / 4 skipped / 3 xfailed / 2 xpassed` (1977.86s, exit 0), normal-policy focused `147 passed`, frontend build/type, `74` focused unit tests and E2E type check pass. All 1197 frozen source/config hashes remain unchanged. Defaults remain off; no commit, merge, deployment or production/body/model gate approval. Final evidence and preserved pre-existing database notes are recorded below; R3 counts are historical only.

## Execution boundary

Use the existing `.claude/worktrees/agent-module-permission-kernel` worktree on `feature/agent-task-runtime-foundation`. Preserve its cumulative tenant/R1–R3 edits and main-workspace user changes. Do not commit, stage, push, merge, deploy, install a browser, operate shared container lifecycle, reset shared E2E data, change business data or enable production as part of this plan. Recorded review checkpoints replace commit steps until the user authorizes commits.

Read PROGRESS, relevant DECISIONS, architecture-maintenance and this design first. Establish the related test baseline, then execute tasks in order with observed contract RED → GREEN and the selected workflow's specification/quality reviews. Changes to a completed task require focused reverification; broad repeat checks require new evidence. Approval of metadata scope does not prove approval of this written design or production delivery.

## Files and responsibilities

| Files | Responsibility |
|---|---|
| New `backend/app/services/agent_runtime/trial_policy.py` | Strict file load, immutable entries, exact current-fact selection, declaration hash |
| Modify `backend/app/config.py`, `main.py`, `database.py` | Default-off settings, lifespan snapshot, trusted app-state reference on request sessions |
| Modify `backend/app/services/agent/permissions/catalog.py`, `types.py`, `access.py` | Explicit immutable canonical profiles; default baseline; kernel re-reads selected definition |
| Modify `backend/app/services/agent_runtime/plugin_registry.py`, `task_service.py`, `task_reads.py`, `runtime_access.py` | Bounded grant bootstrap, final directory/create admission and current runtime authority |
| Modify `run_auth.py`, `run_dispatch.py`, `task_controls.py`, `readonly_delivery.py`, `runtime_messages.py`, `checkpoint_service.py` in that directory | Binding JWT, deadline, final proof, resume/restart and delivery; history remains current-user authorized |
| New `backend/app/core/agent_local_trial.py`; modify `core/tenant_context.py` | Actual-peer admission after off gate, before tenant/body/database work |
| Modify `backend/app/schemas/agent_plugin.py`, `api/admin/agent_plugins.py`, `plugin_registry.py` | Strict revoke request/response, atomic CAS fence and audit |
| New `backend/app/services/agent_runtime/trial_launcher.py`, `backend/app/cli/agent_local_trial.py` | Secure fixed-worker launch and thin check/run/revoke CLI; no privileged direct SQL |
| New test helpers `backend/tests/services/agent_runtime/trial_support.py`, `backend/tests/e2e/agent_local_trial_harness.py` | Synthetic policy and owned real tenant/HTTP/browser infrastructure; no policy-authority monkeypatch |
| New tests listed per task; new `frontend/e2e/specs/agent/local-trial.spec.ts`; modify `frontend/playwright.agent.config.ts` | Meaningful policy, real transaction, real process and normal-policy browser acceptance |
| New `docs/development/agent-local-trial.md`; modify service/CLI README, architecture, permissions, development, PROGRESS and runtime roadmap | Implemented behavior and operational procedure, after code verification |

Paths in the runtime row are relative to `backend/app/services/agent_runtime/`. Do not restructure unrelated AgentSession, provider, graph or tenant migration modules.

## Verification commands and fixture contracts

All SQL tests use a newly migrated random `_test` database and complete owned TenantSessions with real commits. The existing local runner creates and drops only its owned database:

```sh
PG15_CONTAINER=agent-module-permission-kernel-db-1 /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python /tmp/openqms_tenant_checks.py tests/services/agent_runtime -q -rs
```

Run this command from the worktree. Change test nodes as specified below. If the local runner is absent, first provide an equivalent owned database runner with random `_test` names, the actual migration heads, NullPool and finally cleanup; do not fall back to qms/qms_test or flush-only root fixtures. Do not print runner/config secrets. Keep baseline and RED/GREEN summaries in the execution ledger.

`trial_support.write_policy(path, entry)` writes schema_version=1 and a single JSON entry to a newly created 0600 file, using the complete entry below. Its unit fixture uses a fixed aware UTC clock; HTTP fixtures use current time plus 20 minutes.

```python
import json
from pathlib import Path

WORKER_SHA256 = "ab4645b4a57a55f2d17117fad64bf1aabac8a450e34f445c8a718449b039ed54"

def write_policy(path: Path, entry: dict) -> Path:
    with path.open("x", encoding="utf-8") as stream:
        path.chmod(0o600)
        json.dump({"schema_version": 1, "entries": [entry]}, stream)
    return path

UNIT_ENTRY = {
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "tenant_generation": 1,
    "installation_id": "00000000-0000-0000-0000-000000000002",
    "credential_epoch": 0,
    "plugin_key": "openqms.local-d4-metadata", "plugin_version": "1.0.0",
    "executor_user_id": "00000000-0000-0000-0000-000000000003",
    "report_id": "00000000-0000-0000-0000-000000000004",
    "factory_id": "00000000-0000-0000-0000-000000000005",
    "product_line_code": "TRIAL-LINE", "expires_at": "2030-01-01T00:20:00Z",
    "worker_sha256": WORKER_SHA256,
}
```

New `owned_local_trial` fixture provisions a complete random tenant through the existing tenant migrator into the runner's owned database, creates synthetic users/report/verification facts, and supplies `factory`, `binding`, `user_id` (executor), `admin_user_id`, `report_id`, `factory_id`, `line`, `installation_id`, `secret`, `entry`, `policy`, `admin_token`, `user_token`. Registration, enable/grant, task creation and claims use normal services/API; only seed business facts before the trial. Its app uses actual lifespan policy loading and get_db, NullPool and allocated loopback ports. No DIRECT, TRUSTED_DELIVERY_DEPLOYMENTS, authorize or delivery replacement. Expose `client`, `base_url` and a `session()` async context manager attaching the same actual parsed app-state policy for service tests. Track and clean only fixture-created tenants, ports/processes and directories. Do not inherit `process_tenant`, whose legacy test-only DIRECT patch would invalidate this proof.

## Task 1 — Strict immutable startup policy

**Files:** Create `trial_policy.py`, `trial_support.py`, `backend/tests/services/agent_runtime/test_trial_policy.py`. Modify config, main lifespan and get_db.

- [x] Add unit contract tests with UNIT_ENTRY and explicit `now=datetime(2030,1,1,tzinfo=UTC)`. Cover valid, empty, absent, disabled, invalid tenant mode, duplicate keys, all spec field bounds, naive/expired/>24h dates, symlink/owner/mode/oversize and fixed-worker mismatch. Meaningful valid-load and denial examples:

```python
from datetime import UTC, datetime
from app.services.agent_runtime.trial_policy import load_policy
from tests.services.agent_runtime.trial_support import UNIT_ENTRY, write_policy

def test_policy_requires_enabled_dev_mode(tmp_path):
    path = write_policy(tmp_path / "policy.json", UNIT_ENTRY)
    now = datetime(2030, 1, 1, tzinfo=UTC)
    allowed = load_policy(path, mode="local_metadata", tenant_mode="dev", now=now)
    assert allowed.diagnostic == "TRIAL_READY"
    assert len(allowed.entries) == 1
    assert len(allowed.entries[0].binding_sha256) == 64
    for tenant_mode in ("single", "production"):
        denied = load_policy(path, mode="local_metadata", tenant_mode=tenant_mode, now=now)
        assert denied.entries == ()
        assert denied.diagnostic == "TRIAL_MODE_DENIED"

def test_expired_policy_fails_closed(tmp_path):
    path = write_policy(tmp_path / "policy.json", UNIT_ENTRY)
    result = load_policy(path, mode="local_metadata", tenant_mode="dev",
                         now=datetime(2030, 1, 1, 1, tzinfo=UTC))
    assert result.entries == ()
    assert result.diagnostic == "TRIAL_POLICY_INVALID"
```

- [x] Run the owned runner node `tests/services/agent_runtime/test_trial_policy.py -q -rs`; confirm the new missing loader contract fails, rather than unrelated database setup.
- [x] Implement `load_policy(path: Path|None, *, mode: str, tenant_mode: str, now: datetime) -> TrialPolicy`. Define frozen `TrialEntry` with spec fields and computed binding_sha256, frozen `TrialPolicy(entries: tuple[TrialEntry,...], diagnostic: str)` and `EMPTY_POLICY`. Use O_NOFOLLOW, fstat, bounded descriptor read, duplicate-key rejecting JSON decoder and strict Pydantic validation; normalize entry values before deterministic SHA-256. Resolve worker path relative to this packaged module, not policy or cwd. Reject inconsistent same-install declarations. All expected validation/read failures return empty policy and constant codes; do not log exception text or payload. Exact mode diagnostics: disabled/absent path → TRIAL_DISABLED; non-dev enabled mode → TRIAL_MODE_DENIED; malformed/unknown mode/file → TRIAL_POLICY_INVALID; valid/empty file → TRIAL_READY.
- [x] Wire lifespan and request session reference; do not initialize providers for this trial or change get_db tenant binding/rollback:

```python
# lifespan after settings are available
app.state.agent_local_trial_policy = load_policy(
    settings.AGENT_LOCAL_TRIAL_POLICY_PATH,
    mode=settings.AGENT_LOCAL_TRIAL_MODE,
    tenant_mode=settings.TENANT_MODE, now=datetime.now(UTC),
)
# inside existing get_db session block, before yield
session.info["agent_local_trial_policy"] = getattr(
    request.app.state, "agent_local_trial_policy", EMPTY_POLICY,
)
```

- [x] Re-run policy tests; assert the snapshot is immutable and replacing the file after startup does not replace it. Record review evidence and unchanged default-off settings.

## Task 2 — Canonical profile and normal grant/task admission

**Files:** Modify permission catalog/types/access, plugin_registry, task_service, task_reads and runtime_access. Create `backend/tests/services/agent_runtime/test_trial_admission.py`, owned_local_trial helper and `backend/tests/services/agent/permissions/test_profiles.py`.

- [x] Add tests preserving baseline DENY and canonical re-read:

```python
from app.services.agent.permissions.catalog import get_capability
from app.services.agent.permissions.types import ApprovalFloor

def test_profile_does_not_enable_baseline_or_commands():
    summary = "capa.d4.summary.masked.v1"
    assert get_capability(summary).approval_floor == ApprovalFloor.DENY
    assert get_capability(summary, profile="local_metadata_v1").approval_floor == ApprovalFloor.DIRECT
    assert get_capability("capa.d4.candidate.propose.v1",
                          profile="local_metadata_v1").approval_floor == ApprovalFloor.DENY
    assert get_capability(summary, profile="caller-chosen") is None
```

- [x] Add normal-policy fixture tests proving admin can enable only summary grants with explicit current report/factory/line and finite expiry within approval; out-of-scope object, null scope, unbounded expiry and command grants fail. Test final installation directory and create_task both select the same executor/target declaration. Change each exact binding field independently and verify no ready run or usable directory candidate. Enabled plugin/grant and current VIEW remain necessary; a matching file alone is insufficient. Run `tests/services/agent/permissions tests/services/agent_runtime/test_trial_admission.py -q -rs` and observe contract RED.
- [x] Add `AccessAttempt.catalog_profile: str="baseline"` at the end; implement immutable profile selection in get_capability and re-read `get_capability(attempt.spec.id, profile=attempt.catalog_profile)` in authorize. Do not mutate CAPA_CAPABILITIES or accept profile in request DTOs. Unknown profile remains denied.
- [x] Define frozen `TrialAdmission(profile: str, binding_sha256: str, expires_at: datetime, installation_id: UUID)` and `select_admission(policy, *, binding, installation, executor_user_id, report_id, factory_id, product_line_code, now) -> TrialAdmission|None`. Inputs are current trusted server facts; require binding.mode=business and exact active dev tenant facts. `policy` is the actual loaded object from db.info; missing defaults EMPTY_POLICY. No schema fields or arbitrary request claims in this selector.
- [x] Pass selected admission explicitly to `_read_grants(..., *, trial=None)` at task creation and both install-directory calculations. Derivation and the kernel use `trial.profile` only after actual selection; ready still requires all manifest requirements and summary. At create/enable grant, recheck current admin after INSTALL lock and validate all real targets against matching installation declarations; disable requires no declaration. Preserve target-fixed grant expiry and existing API errors.
- [x] Return frozen `TaskAuthority(scope, capabilities, target_product_line_code, trial)` from authorize_task; update its existing claim/verify/refresh/control callers to named fields. Historical source recognition deliberately calls baseline get_capability. Run this task's tests plus existing `tests/services/agent_runtime tests/api/test_admin_agent_plugins.py tests/api/test_agent_tasks.py tests/api/test_agent_activity.py -q -rs`; review bootstrap and default DENY behavior before Task 3.

## Task 3 — Bound runtime credentials and final delivery

**Files:** Modify run_auth, run_dispatch, runtime_access, readonly_delivery, runtime_messages, checkpoint_service and task_controls. Create `backend/tests/services/agent_runtime/test_trial_runtime.py`, `backend/tests/api/test_trial_runtime.py`.

- [x] With the actual normal-policy fixture, claim a ready task and inspect the signed private claims. Assert binding equals the server-selected row, exp and lease deadline never exceed policy expiry, same-key retry preserves lease/epoch, and absent/malformed/stale binding claims fail under the trial. API claim DTO stays seven fields. Run these nodes and observe RED.
- [x] Extend `issue_run_token(..., *, trial: TrialAdmission|None=None)`: insert only server-owned trial_binding_sha256 and clamp exp. Type-check optional claim in `_claims`; ordinary run JWT validation remains current tenant/install/run/credential/lease checks. RuntimeIdentity gains selected admission; full refresh compares token binding with fresh TaskAuthority, never trusts it to select profile.
- [x] New claim sets `lease_expires_at=min(now+configuredTTL, trial.expires_at)`; retry only reissues a token within the existing lease and current selected policy. Recheck the deadline after lock wait and before successful write. Make delivery depend on this exact admission and only the two spec tuples; retain baseline empty legacy trusted directory. Resume/restart call full current authority plus scoped restricted/raw delivery. Pause/cancel and user history do not require active trial.
- [x] Add actual-commit tests with asyncio Events between RR snapshot and final INSTALL lock: advance past real short expiry before releasing delivery and assert no returned content, receipt or successful delivery audit. Test credential rotation, policy-binding change after owned app restart, target factory/line changes and source withdrawal. Ensure final output/checkpoint/ACK/finish paths all refresh current authority; accepted history still does not prove execution.
- [x] Run `tests/services/agent_runtime/test_trial_runtime.py tests/api/test_trial_runtime.py tests/api/test_readonly_context.py tests/api/test_readonly_outputs.py tests/api/test_runtime_messages.py tests/api/test_readonly_checkpoints.py tests/api/test_agent_controls.py -q -rs`; record GREEN and focused review. Do not loosen schema/receipt/source checks to admit trial metadata.

## Task 4 — Local peer gate and atomic permanent revoke

**Files:** Create core/agent_local_trial.py, `backend/tests/api/test_trial_peer.py`, `backend/tests/services/agent_runtime/test_trial_revoke.py`, `backend/tests/api/test_trial_revoke.py`. Modify tenant_context, plugin schemas/service/admin API.

- [x] Test runtime off precedence with a sentinel body/tenant lookup that raises if read. Explicit trial-mode requests from nonliteral-loopback peers or with Forwarded/X-Forwarded-* must fail before tenant DB lookup, including admin and task paths. Test actual 127.0.0.1/::1 allowed and legacy paths unaffected; use ASGI client scope for peer variants plus real TCP in Task 5. Run peer node and observe RED.
- [x] Implement the small gate called from existing early tenant middleware: flag off keeps existing 404 first; requested local_metadata mode then checks actual request.client.host and forwarded header presence. Reject invalid peer with constant 403. No proxy/header reinterpretation, no changes to tenant slug/JWT/generation resolution.
- [x] Define strict `LocalTrialRevoke(expected_credential_epoch)` and `LocalTrialRevokeOut(installation_id, credential_epoch, enabled: Literal[False], outcome: Literal["revoked","already_fenced"])`. Define service `revoke_local_trial(db, actor, installation_id, expected_epoch)` with the exact spec CAS and INSTALL lock; refresh admin after waiting. Hash a fresh unreturned random secret, disable and increment atomically, flush and audit once; API commits once. Version conflict maps to 409; policy expiry/absence cannot prevent revoke.
- [x] Add a real SQL persistence test with the fixture's actual parsed policy:

```python
import pytest
from sqlalchemy import select
from app.models.agent_plugin import AgentPluginInstallation
from app.models.user import User
from app.services.agent_runtime.plugin_registry import revoke_local_trial

@pytest.mark.asyncio
async def test_revoke_retry_does_not_bump_twice(owned_local_trial):
    owned = owned_local_trial
    async with owned.session() as db:
        actor = await db.scalar(select(User).where(User.user_id == owned.admin_user_id))
        first = await revoke_local_trial(db, actor, owned.installation_id, 0)
        await db.commit()
        second = await revoke_local_trial(db, actor, owned.installation_id, 0)
        await db.commit()
        assert first.outcome == "revoked"
        assert second.outcome == "already_fenced"
        plugin = await db.get(AgentPluginInstallation, owned.installation_id,
                              populate_existing=True)
        assert plugin.enabled is False
        assert plugin.credential_epoch == 1
```

- [x] Use separate sessions, real commits and Events for same-expected concurrency, revoke/metadata delivery in each order, and admin withdrawal while waiting on INSTALL. Assert one epoch increment/audit, no partial changes on exception, and only one successful side of conflicting delivery/fence ordering. Re-enable with the old policy and prove old secret/JWT and declarations remain denied. Preserve queued/claimed proof and user history/stop controls. Run all three new nodes plus existing credential/admin/control groups; record review and GREEN.

## Task 5 — Fixed-worker CLI and normal local process trial

**Files:** Create trial_launcher.py, CLI module, `backend/tests/services/agent_runtime/test_trial_launcher.py`, `backend/tests/e2e/test_agent_local_trial_process.py`; extend owned harness. Leave fixed worker unchanged unless tests demonstrate a required correction and the reviewed pinned hash is updated deliberately.

- [x] Launcher tests pass sentinel parent environment variables for database/admin/provider/proxy secrets, alter worker bytes and symlink credential paths, and use a real loopback malformed/redirect server. Assert zero unauthorized destinations, no sentinel in child environment or output, hash mismatch before spawning, no arbitrary report/command argument, and fixed-size/300-second timeout cleanup only of the owned child. Run launcher node and observe RED.
- [x] Define `run_fixed_worker(*, installation_id, secret_file, tenant_slug, api_base_url, claim_key, checkpoint, finish) -> int`. Use literal loopback URL validation, secure descriptor reads, pinned bytes → owned 0700 directory → `sys.executable -I`. Build the environment from LANG=C, LC_ALL=C and the seven OPENQMS worker options only. Drain stdout/stderr concurrently with a cumulative 1 MiB cap per pipe; kill and await the owned child immediately on overflow or the 300-second deadline, then finally clean the owned directory. Do not collect unlimited output with communicate(), forward raw stderr, inherit process secrets or use shell=True. CLI argparse exposes only the three design subcommands and their exact flags. check-policy calls the same loader; revoke uses a no-proxy/no-redirect bounded HTTP client with admin-token-file and strict response validation.
- [x] Build the new real process fixture through empty-file startup → normal register → explicit exact policy restart → normal grant/enable → user create → actual CLI run. Owned business seed is allowed; claims and authority must not be synthesized. The fixture's current admin/user login JWTs stay in the parent, not worker environment. Compare full business snapshots before/after and prove D4 text/body markers never enter business projection or output.
- [x] Exercise two dependent query receipts and full digests, ordered ACK/history, results, checkpoint/restart/current-fact reread, pause and revoke between rounds; verify revoked claim and no later delivery. Test local actual peer and spoofed forwarded headers. Keep existing R2 22-process and R3 resume regressions as independent prior contracts, not substitutes for normal-policy acceptance.
- [x] Run `tests/services/agent_runtime/test_trial_launcher.py tests/e2e/test_agent_local_trial_process.py tests/e2e/test_readonly_agent_process.py tests/e2e/test_agent_readonly_resume_process.py -q -rs`; inspect each result, missing installed browser is a failure with explicit executable override, never install/skip automatically. Record code/spec review and subprocess cleanup evidence.

## Task 6 — Browser, frozen full checks and operating guide

**Files:** Create local-trial.spec.ts and `backend/tests/e2e/test_agent_local_trial_browser.py`; extend dedicated playwright.agent.config.ts match to both Agent specs. Create docs/development/agent-local-trial.md; modify relevant README/fact docs and progress/roadmap.

- [x] Run the new browser fixture using normal policy/admin/user setup, allocated Vite/backend ports and the existing installed Chromium. Browser scenario contracts: directory and fixed-target task creation; two metadata rounds and full source digest rendering; same-run pause/continue; checkpoint new run with current facts; revoke prevents plugin calls/resume while authorized historical results remain readable; current business/source withdrawal clears content. Reuse the existing sidebar assertions and eight R3 scenarios without altering their semantics. No generic E2E setup/reset or conventional shared ports.
- [x] The owned pytest browser fixture invokes the existing local Node CLI with `test --config playwright.agent.config.ts local-trial.spec.ts`; set AGENT_BROWSER_URL, AGENT_BROWSER_ARTIFACTS and OPENQMS_AGENT_BROWSER_EXECUTABLE to fixture-owned resources. Missing browser/Node dependency fails with a useful constant setup message. This final integration gate may already pass after Tasks 1–5; do not deliberately break working behavior to manufacture a RED. If it reveals a product defect, preserve the failing browser scenario and fix only that demonstrated defect before rerunning; existing R3 gates must remain green.
- [x] Write the actual operating guide with empty policy registration, exact binding/epoch/hash approval, safe secret-file handling, owned backend restart, grant enablement, trial run, expiry, temporary disable versus permanent revoke, response-loss retry, and new approval after rotation. Include trusted-host/one-worker/loopback/no-provider limits and no automatic grant renewal. CLI README distinguishes this HTTP-authorized CLI from privileged SQL maintenance. Architecture/permissions state only verified implementation and default DENY, not production readiness.
- [x] Freeze source hashes before final verification. Run the new normal-policy browser node and the configured complete backend in fresh owned databases:

```sh
PG15_CONTAINER=agent-module-permission-kernel-db-1 /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python /tmp/openqms_tenant_checks.py tests/e2e/test_agent_local_trial_browser.py -q -rs
PG15_CONTAINER=agent-module-permission-kernel-db-1 /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python /tmp/openqms_tenant_checks.py tests -q -rs --ignore=tests/test_graph_sync_worker.py --ignore=tests/test_graph_projection.py
make check-frontend
```

The two graph exclusions are existing Makefile-configured exclusions; report them. Run frontend focused tests from frontend with `npm exec vitest run src/api/agentTasks.test.ts src/api/client.agentTasks.test.ts src/components/agent src/pages/capa/CAPADetailPage.test.tsx`, then `npm exec tsc -- --project tsconfig.e2e.json --noEmit`. These commands do not install dependencies. Confirm actual exit codes, backend skip/xfail/xpass reasons, owned cleanup and unchanged frozen sources; new code after freezing requires affected reverification.
- [x] Check local doc links and `git diff --check`, synchronize worktree PROGRESS and only the main pointer. Record final reviews and exact evidence. Mark R4a complete only when this normal configuration path and all applicable gates pass; leave R4b/production/body/model gates open. User-visible completion must name remaining boundaries and absence of merge/deployment.

## Execution ledger

At initial preparation on 2026-10-02, no R4a code or runtime activation had been performed. Record actual execution evidence here; never substitute R3 counts.

### 2026-10-05 execution

- Written review/continuation approved by the user's explicit confirmation; runner-owned random `_test` database lifecycle additionally approved in the permission clarification.
- Task 0: original status/diff/untracked hashes captured under `/tmp/openqms-r4a-CUi1gSs7` (existing edits preserved). Recreated missing `/tmp/openqms_tenant_checks.py`: psycopg CREATE, actual `alembic upgrade head`, NullPool via root conftest and real TenantSession fixtures, finally cleanup only the generated database. PostgreSQL 15.18 confirmed. CodeGraph CLI reports `locking protocol`; use specifically identified files, without changing the index.
- Baseline: permissions/runtime/admin-plugin/task API `526 passed` (896.93s, exit 0); `make check-frontend` exit 0. Owned database cleaned.
- Task 1: missing loader RED `51 failed`; strict parser GREEN `51 passed`. Actual lifespan/get_db wiring RED `2 failed / 51 passed`; GREEN `53 passed` (exit 0). Default-off settings, frozen snapshots and full pinned worker hash preserved. File safety, duplicate/strict fields and deadlines reviewed inline against the design.
- Task 2 profile/selector RED `13 failed`; permissions + policy GREEN `85 passed` (exit 0). Normal grant bootstrap RED reproduced as actual API 409, without DIRECT/delivery/authorize replacements; normal-policy admission GREEN `8 passed` (28.77s, exit 0). New fixture corrected its missing `legacy_role` and isolates in-memory per-IP login rate limiting; real logins and authorization remain unchanged. Broad Task 2 regression and Task 3 RED are recorded when they finish.


- Task 2 broad permissions/runtime/admin/user/activity regression: `606 passed` (994.93s, exit 0). Normal-policy fixtures use actual startup snapshots and normal logins/grants, never test-only authority replacement.
- Task 3 RED: `5 failed` (missing private binding and delivery admission); GREEN `5 passed`, and affected context/output/messages/checkpoint/control API regression `26 passed` (51.39s, exit 0). Own new tests corrected missing `{}` claim body and respected existing 401-at-auth/403-at-business exception contracts. Actual short-deadline snapshot proves no receipt or successful delivery audit after final expiry refusal.
- Task 4 RED `12 failed / 3 passed`; real-transaction/admin/credential regression GREEN `61 passed` (51.84s, exit 0), including equal-expected concurrency, caller rollback, admin withdrawal during real INSTALL wait and revoke/delivery commit ordering in both directions. Test audit evidence is scalar JSON, not rollback-expired detached ORM state.
- Task 5 launcher RED `18 failed`; parser/launcher GREEN `71 passed`. Actual malformed TCP revoke proof revealed and fixed HTTP status-line traceback content exposure, coercive epoch/false response values and duplicate JSON keys (RED `4 failed / 21 passed`). After fixes, real launch/overflow/timeout/clean-environment/private-file/no-redirect/no-proxy contracts passed. Extra interrupt cleanup RED reproduced an unreaped owned child; finally cleanup now reaps on interruption as well. Worker pinned source remained unchanged.
- Normal-policy actual CLI/TCP process: `3 passed` (17.06s, exit 0), two dependent receipts/digests, same-run pause/continue, checkpoint new run reading changed current verification facts, ordered input/history, permanent revoke between rounds, spoofed forwarded header refusal and complete business-table snapshots (excluding authentication refresh/operational logs). Only explicit test-fixture edits change business facts.
- Normal-policy Chromium lifecycle GREEN `1 passed` (25.34s, exit 0). New test harness corrected a nonexistent browser-side result-fetch wait (activity already embeds results) and scopes identical digests to their distinct receipt rows; product behavior was not weakened. Normal UI creation, full digest rendering, pause/continue, checkpoint new run, revoke, authorized historical reads and source withdrawal all passed.
- Final R4a new-contract/permission/normal-process/Chromium focused run: `147 passed` (124.10s, exit 0). Includes wildcard-scope RED `2 failed / 53 passed` then explicit denial, and interrupt cleanup proof. Fresh frozen frontend build/type exit 0, focused vitest `74 passed / 6 files`, dedicated E2E tsc exit 0. Differences from R3's historical 78 count reflect the specified current focused command, not copied evidence.
- Final review: independent reviewer examined the specified R4a implementation/spec paths only and found no concrete important defect; no code was changed by review. Source freeze records `1197` source/config hashes in `/tmp/openqms-r4a-CUi1gSs7/frozen-sources.json`; full fresh-owned backend gate was started (final result below). User additionally approved nested original-fixture database lifecycles (`qms_migtest_<UUID>_test`, `qms_apqp_iso_<random>`, `qms_release_target_<random>`), never existing/shared/business databases. Complete gate output, skip/xfail/xpass reasons, unchanged hashes and cleanup were confirmed in final acceptance below.

### Final frozen acceptance — 2026-10-05

- Full backend command: `PG15_CONTAINER=agent-module-permission-kernel-db-1 /Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python /tmp/openqms_tenant_checks.py tests -q -rs --ignore=tests/test_graph_sync_worker.py --ignore=tests/test_graph_projection.py`. Fresh parent database `openqms_r4a_73c675406233447797379b2465ff54ee_test`; actual migration head applied. Result **2859 passed / 4 skipped / 3 xfailed / 2 xpassed / 5 warnings**, **1977.86s**, **exit 0**. Log: `/tmp/openqms-r4a-CUi1gSs7/final-backend.log`.
- Two graph exclusions exactly match Makefile. Skip reasons: Redis unavailable in agent memory (1); E2E_MODE false/not registered/not seeded in legacy E2E endpoint tests (3). R4a normal-policy Chromium and old R3 eight scenarios ran in the complete suite, not skipped. Existing non-strict MES expected-failure/pass markers concern separate session transaction visibility and SKIP LOCKED against uncommitted fixture data; retained without unrelated refactoring. Existing Pydantic/websocket deprecation warnings remain.
- Frontend frozen build/type **exit 0**; focused vitest **74 passed / 6 files**; dedicated E2E tsc **exit 0**, logs in the same evidence directory. Independent reviewer found no concrete important issue in the specified R4a code/spec scope. Final check reports **all 1197 source/config hashes unchanged**, fixed worker hash unchanged, **47 local document links / 0 broken**, `git diff --check` exit 0.
- Parent runner reports its owned database dropped; no `openqms_r4a_*` databases or owned plugin/CLI/Vite/Playwright/runner processes remain. Four other matching random disposable databases were preserved: their physical PostgreSQL directory birth times are **2026-09-27/28**, before this session, so they were not treated as this run's cleanup targets. No business/shared database reset or pre-existing database deletion.
- Main progress pointer initially refused by worktree isolation. User explicitly chose to preserve and exit the worktree; only the main `PROGRESS.md` pointer/date was then updated successfully, preserving all other shared-checkout changes. Main code stays unchanged. No commit/stage/push/merge/deploy, no browser installation or shared container/E2E lifecycle operation. R4a metadata local trial accepted; R4b body/attachment/model/production and future business-write gates remain open.

2026-10-02 documentation verification: 15 relevant local links resolve, both workspaces' `git diff --check` exit 0, new documents have no trailing whitespace/unclosed fences/placeholders, five Python plan blocks parse, and all 61 R3 frozen source hashes are unchanged. This is a documentation-only check; no tests or migrations were run for R4a.
