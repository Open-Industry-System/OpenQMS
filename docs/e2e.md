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
