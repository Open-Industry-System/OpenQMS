# E2E Test Suite

Browser full-stack E2E via Playwright against a dedicated docker-compose stack. Manual only — not in CI.

## Run

```bash
make e2e           # up + migrate + seed + playwright test
make e2e-up        # start e2e stack (db/redis/backend/frontend)
make e2e-seed      # re-run deterministic seed (idempotent)
make e2e-down      # down -v (clears e2e DB volume)
make e2e-reset     # down -v + up + migrate + seed
```

Single module: `make e2e TEST_ARGS="--grep m1-core/fmea"`.

## Credentials

Copy `.env.e2e.example` → `.env.e2e` (gitignored) and fill `LLM_PROVIDER`/`LLM_API_KEY`/`LLM_MODEL`/`LLM_BASE_URL`. Missing → AI specs skip with a warning; the rest stays green.

## Conventions

- Seed known docs use `-E2E-` infix (`PFMEA-E2E-001`); write-flow created docs use `E2E-` prefix at start (`E2E-M1-CAPA-001`). Cleanup never deletes seed.
- Account names/factories come from `/api/e2e/seed-state` — never hardcode in specs.
- Selectors use `data-e2e="..."` attributes; prefer `getByRole`. AI assertions check structure/behavior, never exact text.
- `workers:1`, `fullyParallel:false` (serial — cleanup prefixes must not race).
- E2E endpoints are gated: `E2E_MODE=1` AND `TENANT_MODE != "production"` or they don't load.

## Add a spec

1. Add input fixtures under `frontend/e2e/fixtures/input/` if needed.
2. Write `frontend/e2e/specs/<module>/<name>.spec.ts`; `loginAs(page, role)`; use `data-e2e` testids; `afterAll` → `cleanupByPrefix("E2E-<module>")`.
3. Add `data-e2e` attributes to the production component if missing (testability only).
4. Run `make e2e TEST_ARGS="--grep <name>"` to verify in isolation.

## Owned CAPA outcome-review acceptance (Task 7)

This gate is separate from the seeded Compose suite above. Do **not** use its
reset/seed commands or six synthetic passed-gate reports as positive evidence.
Use only the registered resources in the isolated outcome-review worktree and
its authorized Python interpreter; no DB creation/reset, plugin enablement,
scanner operation, browser/dependency installation, or production configuration.

From the isolated worktree, the controlled runner is:

```bash
"$OPENQMS_OUTCOME_PYTHON" backend/tests/e2e/capa_outcome_runner.py api
"$OPENQMS_OUTCOME_PYTHON" backend/tests/e2e/capa_outcome_runner.py acceptance
```

`api` runs the full outcome API/concurrency tests and runner environment tests.
`acceptance` runs **all** outcome browser-file cases, without exclusions/skips:
installed-Chromium protection, genuine HTTP/provider/Chromium approval, and a
source-bound HTTP case checking FMEA and PLANNING independently. Missing test
configuration/provider/browser is a failed, BLOCKED gate, not a skip/pass.
`browser` and `live` are explicitly partial diagnostic modes, not acceptance.

The runner reads only the existing private owned resource profile and, for
`live`/`acceptance` opt-in, the worktree's authorized `.env.e2e`. Only
`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT` are loaded;
no shell evaluation, dotenv interpolation, ambient credentials/proxies or
arbitrary environment passthrough. Do not copy production/main-checkout config.
Node/Vite/Chromium receive a separate safe environment containing disposable
employee logins, but **no provider or database credentials**. Missing profile
still exercises the real app's fail-closed path; ordinary private `run-owned.py`
clears provider credentials and is never live-provider evidence.

`owned_outcome_server` provisions two nonce-owned business tenants with real
migrations and TenantSession, normal auth/permissions/get_db/commit, allocated
loopback sockets, and narrow production review-error handlers. Identical report
UUIDs in separate schemas contain distinguishable material. Legacy terminal
protection records are explicitly synthetic, contain no fabricated approval or
gate, and cannot count as a successful lifecycle. An unbound legacy source
correctly returns conflict rather than reconstructing an approval version.

The live report starts at D1 through the real business POST. D3 import/provider,
root-cause verification, implemented D5/D6 material, current D7 dispositions and
real D8 document services precede pending. Empty-source and new-controlled-document
paths are distinct. The latter publishes actual FMEA/CP versions and requires the
provider's actual affected documents and real audit to pass; no invented decision
or skipped source is substituted. Knowledge/lateral services run unmodified on
browser approval. A legitimate empty lateral result is not evidence of a lateral
LLM call. Pending/stale-round assertions remain unverified when the provider blocks.

Chromium logs in normally and captures the actual outgoing displayed revision/
round on approval. Same-document identity switching calls the production login
action with real credentials while a nonce-controlled window holds actual server
response bytes; no forged store authority, synthetic DTO or browser sleep.
Post-close direct HTTP rejection compares material/audit/embedding/outbox snapshots.
Supplement is visibly unreviewed; archive-only supplement keeps existing 400,
while reviewed-core or mixed PUT remains 409. Transaction proofs use actual
PostgreSQL blocking witnesses, including rejection source-row waits.

Timestamped redacted logs/exit JSON and secret-free resource teardown journals
are written under `.superpowers/sdd/2026-10-23-capa-outcome-review/`. Only run-owned
tenants, sockets and Node/server processes are cleaned; registered PG databases,
container and volume are preserved for Task 8. Normal backend hashing explicitly
uses `public.digest`, matching the existing tenant trigger without adding public
to strict search_path. CP creation returns the existing eager-loaded service view
so async serialization does not lazy-load `items` after commit.
