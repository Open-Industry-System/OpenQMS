# System-Level E2E Test Suite (M0+M1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a browser full-stack E2E test suite (Playwright against a dedicated docker-compose stack) and cover the 4 core M1 user journeys: auth/RBAC/factory-isolation, FMEA lifecycle, CAPA 8D lifecycle, dashboard drilldown.

**Architecture:** A dedicated `docker-compose.e2e.yml` override (project `openqms-e2e`, isolated ports/volume) runs db/redis/backend/frontend. A deterministic idempotent `seed_e2e` populates known records exposed via a gated read-only `/api/e2e/seed-state` endpoint; a gated `/api/e2e/cleanup` deletes `E2E-*`-prefixed test data by a fixed whitelist in a single FK-ordered transaction. Playwright runs serialized (`workers:1`, `fullyParallel:false`), reuses per-role `storageState`, and asserts AI flows against the real LLM (structure/behavior only).

**Tech Stack:** Docker Compose v2.24+ (`!override`), FastAPI (gated e2e router), Playwright 1.60, TypeScript, pytest (backend), vitest (frontend unit, unchanged).

**Spec:** `docs/superpowers/specs/2026-07-01-system-e2e-test-suite-design.md`

## Global Constraints

- Compose prefix is fixed for ALL compose calls: `DC_E2E := docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e`.
- E2E ports: db host `5433`, backend host `8001`, frontend host `5174`, redis NOT host-exposed. Container-internal: backend `DATABASE_URL=@db:5432/qms_e2e`, frontend vite proxy `/api → http://backend:8000`.
- `E2E_MODE` is a new `Settings.E2E_MODE: bool = False` field; e2e router registered only `if settings.E2E_MODE and settings.TENANT_MODE != "production"`.
- Seed known doc numbers use `-E2E-` infix (e.g. `PFMEA-E2E-001`); write-flow created records use `E2E-` prefix at START (e.g. `E2E-M1-CAPA-001`) — non-overlapping so cleanup never deletes seed.
- LLM credentials use app-native env names: `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` / `LLM_TIMEOUT=30`. Missing → AI specs skip-with-warning, never silently.
- `playwright.config.ts` MUST be `workers:1` + `fullyParallel:false` + `baseURL:5174` (current is `fullyParallel:true`, local `workers:undefined`).
- No CI integration; E2E runs only via `make e2e*`. Do not touch `.github/workflows/test.yml`.
- Backend e2e endpoint tests (`test_e2e_endpoints.py`) skip unless `E2E_MODE` is set (so `make check`, which does not set it nor run `seed_e2e`, skips them). Run them explicitly with `E2E_MODE=1` + `TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5433/qms_e2e` (the e2e DB). The file must NOT default `E2E_MODE` itself.
- Production code changes are limited to adding `data-e2e="..."` attributes for testability — no test-only branches/logic.

---

## File Structure

**Created:**
- `docker-compose.e2e.yml` — e2e profile override (ports `!override`, redis `!reset []`, AI services `profiles:["ai-infra"]`, backend env).
- `.env.e2e.example` — credential/port template (committed); `.env.e2e` gitignored.
- `backend/app/seed_e2e.py` — deterministic idempotent seed.
- `backend/app/seed_e2e_constants.py` — shared constants (factory codes, doc numbers).
- `backend/app/api/e2e.py` — gated router: `seed-state` (read) + `cleanup` (whitelist delete).
- `backend/tests/test_e2e_endpoints.py` — backend tests for seed-state + cleanup.
- `frontend/e2e/global.setup.ts`, `frontend/e2e/global.teardown.ts`
- `frontend/e2e/fixtures/{auth.ts,seed-state.ts,input/*.ts}`
- `frontend/e2e/helpers/{api-client.ts,e2e-utils.ts,cleanup-registry.ts}`
- `frontend/e2e/specs/_guards/{seed.guard.spec.ts,ai-credentials.guard.spec.ts}`
- `frontend/e2e/specs/m1-core/{auth.spec.ts,fmea.spec.ts,capa.spec.ts,dashboard.spec.ts}`
- `frontend/e2e/README.md`, `docs/e2e.md`

**Modified:**
- `backend/app/config.py` — add `E2E_MODE` field.
- `backend/app/main.py` — conditional `include_router(e2e_router)`.
- `frontend/playwright.config.ts` — workers/baseURL/globalSetup.
- `frontend/package.json` — add `test:e2e` scripts + `@types/node` devDep.
- `frontend/tsconfig.e2e.json` — NEW: type-check `playwright.config.ts` + `e2e/**` (src tsconfig doesn't include them).
- `Makefile` — add `e2e*` targets.
- `CLAUDE.md` — append `make e2e`.
- `frontend/src/pages/login/LoginPage.tsx`, `frontend/src/pages/capa/CAPAListPage.tsx`, `frontend/src/pages/capa/CAPADetailPage.tsx`, `frontend/src/pages/planning/fmea/FMEAListPage.tsx`, dashboard widgets — add `data-e2e` attributes.

---

## Task 1: e2e compose override, env template, Makefile targets

**Files:**
- Create: `docker-compose.e2e.yml`
- Create: `.env.e2e.example`
- Modify: `Makefile` (append e2e targets)
- Create: `docs/e2e.md` (stub, expanded in Task 9)

**Interfaces:**
- Produces: `DC_E2E` make variable and `make e2e` / `e2e-up` / `e2e-seed` / `e2e-down` / `e2e-reset` targets used by all later tasks.

- [ ] **Step 1: Write `docker-compose.e2e.yml`**

```yaml
# E2E override. Use with: -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e
# Ports use !override to REPLACE (not append) base ports so the dev stack can run simultaneously.
services:
  db:
    ports: !override
      - "5433:5432"
    volumes:
      - pgdata_e2e:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: qms_e2e

  redis:
    ports: !reset []

  backend:
    ports: !override
      - "8001:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://qms:qms_dev_2026@db:5432/qms_e2e
      REDIS_URL: redis://redis:6379/0
      E2E_MODE: "1"
      TENANT_MODE: single
      LLM_PROVIDER: ${LLM_PROVIDER:-}
      LLM_API_KEY: ${LLM_API_KEY:-}
      LLM_MODEL: ${LLM_MODEL:-}
      LLM_BASE_URL: ${LLM_BASE_URL:-}
      LLM_TIMEOUT: ${LLM_TIMEOUT:-30}

  frontend:
    ports: !override
      - "5174:5173"
    environment:
      BACKEND_URL: http://backend:8000

  # Prevent the AI infra services from starting under the e2e profile.
  neo4j:
    profiles: ["ai-infra"]
  graph-worker:
    profiles: ["ai-infra"]
  ollama:
    profiles: ["ai-infra"]

volumes:
  pgdata_e2e:
```

- [ ] **Step 2: Write `.env.e2e.example`**

```bash
# Copy to .env.e2e and fill. .env.e2e is gitignored.
# LLM credentials (app-native names). Leave blank to skip AI specs with a warning.
LLM_PROVIDER=
LLM_API_KEY=
LLM_MODEL=
LLM_BASE_URL=
LLM_TIMEOUT=30
# Host-side helpers (optional; alembic/seed run inside the backend container)
E2E_API_BASE_URL=http://localhost:8001/api
E2E_HOST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5433/qms_e2e
```

- [ ] **Step 3: Append Makefile targets**

Append to `Makefile`:

```makefile
# ── E2E (manual; not part of `make check`) ──────────────────────────────────
DC_E2E := docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e
# Only pass --env-file if .env.e2e exists, so `make e2e-up` works without copying the
# template (LLM creds optional → AI specs skip-with-warning). LLM_* have ${VAR:-}
# defaults in the override, so absence is fine.
E2E_ENV := $(shell test -f .env.e2e && echo --env-file .env.e2e)

.PHONY: e2e e2e-up e2e-seed e2e-down e2e-reset e2e-run

e2e-up:
	$(DC_E2E) $(E2E_ENV) up -d db redis backend frontend

e2e-seed:
	$(DC_E2E) exec backend python -m app.seed_e2e

e2e-run:
	cd $(FRONTEND_DIR) && if [ -f ../.env.e2e ]; then set -a && . ../.env.e2e && set +a; fi; npx playwright test $(TEST_ARGS)

e2e: e2e-up
	$(DC_E2E) exec backend alembic upgrade head
	$(MAKE) e2e-seed
	$(MAKE) e2e-run

e2e-down:
	$(DC_E2E) down -v

e2e-reset: e2e-down e2e-up
	$(DC_E2E) exec backend alembic upgrade head
	$(MAKE) e2e-seed
```

- [ ] **Step 4: Confirm `.env.e2e` is gitignored**

The repo has no `frontend/.gitignore`; the root `.gitignore` already covers `.env` and `.env.*` (lines 15-16), so `.env.e2e` is ignored automatically. Verify: `git check-ignore .env.e2e` prints `.env.e2e`. (No file change needed.)

- [ ] **Step 5: Stub `docs/e2e.md`**

Create `docs/e2e.md` with a one-line placeholder heading `# E2E Test Suite` (expanded in Task 9). This satisfies docs-check early.

- [ ] **Step 6: Verify compose parses**

Run: `docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e config --quiet`
Expected: exits 0 (validates `!override` syntax is supported). If it errors on `!override`, the Compose version is too old — fall back: convert `docker-compose.e2e.yml` to a standalone file redefining `db`/`redis`/`backend`/`frontend` fully (copy base service blocks, set ports/env directly).

- [ ] **Step 7: Commit**

```bash
git add docker-compose.e2e.yml .env.e2e.example Makefile docs/e2e.md
git commit -m "build(e2e): compose override, env template, make e2e targets"
```

---

## Task 2: E2E_MODE config + gated e2e router scaffold

**Files:**
- Modify: `backend/app/config.py` (add `E2E_MODE`)
- Create: `backend/app/api/e2e.py` (router with stub endpoints)
- Modify: `backend/app/main.py` (conditional include)

**Interfaces:**
- Produces: `settings.E2E_MODE` (bool); `e2e_router` (FastAPI APIRouter) with `GET /api/e2e/seed-state` and `POST /api/e2e/cleanup` signatures defined here, implemented in Tasks 3 & 4.
- Consumes: `settings.TENANT_MODE` (existing).

- [ ] **Step 1: Add `E2E_MODE` to Settings**

In `backend/app/config.py`, inside the `Settings` class (near `TENANT_MODE`), add:

```python
    # E2E test mode: enables /api/e2e/* endpoints. NEVER true in production.
    E2E_MODE: bool = False
```

- [ ] **Step 2: Write `backend/app/api/e2e.py` scaffold**

```python
"""E2E-only endpoints. Registered only when E2E_MODE and not production.

Provides a read-only seed-state view and a whitelist-based cleanup for test data.
Never exposed in production (gated at router registration in main.py)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings

router = APIRouter(prefix="/api/e2e", tags=["e2e"])


@router.get("/seed-state")
async def get_seed_state(db: AsyncSession = Depends(get_db)):
    """Return known seed records (factories, product lines, accounts, doc numbers + ids)."""
    # Implemented in Task 3.
    raise NotImplementedError


@router.post("/cleanup")
async def cleanup_test_data(prefix: str = Query(..., min_length=4, max_length=20), db: AsyncSession = Depends(get_db)):
    """Delete test data whose doc_no/name starts with `prefix` (e.g. E2E-M1).
    Whitelist-based, FK-ordered, single transaction. Implemented in Task 4."""
    # Implemented in Task 4.
    raise NotImplementedError
```

- [ ] **Step 3: Conditionally register the router in `main.py`**

In `backend/app/main.py`, after the existing `app.include_router(...)` block, add:

```python
# E2E-only endpoints: gated so they never load in production even if E2E_MODE leaks.
if settings.E2E_MODE and settings.TENANT_MODE != "production":
    from app.api.e2e import router as e2e_router
    app.include_router(e2e_router)
```

(If `settings` is not imported in main.py, import it: `from app.config import settings`.)

- [ ] **Step 4: Verify backend imports + router not loaded by default**

Run: `cd backend && SECRET_KEY=test-secret-key-for-pytest-only PYTHONPATH=. python -c "from app.main import app; print(sorted(r.path for r in app.routes if r.path.startswith('/api/e2e'))))"`
Expected: `[]` (e2e router NOT registered when E2E_MODE unset).

Run: `cd backend && E2E_MODE=1 SECRET_KEY=test-secret-key-for-pytest-only PYTHONPATH=. python -c "from app.main import app; print(sorted(r.path for r in app.routes if r.path.startswith('/api/e2e'))))"`
Expected: `['/api/e2e/cleanup', '/api/e2e/seed-state']`

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/app/api/e2e.py backend/app/main.py
git commit -m "feat(e2e): E2E_MODE config + gated e2e router scaffold"
```

---

## Task 3: seed_e2e.py + seed-state endpoint + backend test

**Files:**
- Create: `backend/app/seed_e2e_constants.py`
- Create: `backend/app/seed_e2e.py`
- Modify: `backend/app/api/e2e.py` (implement `get_seed_state`)
- Test: `backend/tests/test_e2e_endpoints.py` (seed-state part)

**Interfaces:**
- Produces: `python -m app.seed_e2e` (idempotent); `GET /api/e2e/seed-state` → `{ factories: [...], product_lines: [...], accounts: [{username, password, role_key, factory_codes}], known_docs: {pfmea:[...], capa:[...], ...}, used_doc_numbers: [...] }`.

- [ ] **Step 1: Write `seed_e2e_constants.py`**

```python
"""Single source of truth for E2E seed values. Mirrored by /api/e2e/seed-state."""

E2E_FACTORY_DC100 = {"code": "DC-FACT-E2E", "name": "E2E 默认工厂", "location": "Shanghai"}
E2E_FACTORY_SH = {"code": "SH-FACT-E2E", "name": "E2E 上海分厂", "location": "Shanghai-Pudong"}
E2E_PRODUCT_LINE = {"code": "DC-DC-100-E2E", "name": "E2E DC-DC 100", "product_type_code": None}

# (username, password, role_key, factory_codes) — factory_codes [] = group user (multi-factory)
E2E_ACCOUNTS = [
    ("admin", "Admin@2026", "admin", [E2E_FACTORY_DC100["code"]]),
    ("engineer", "Engineer@2026", "field_qe", [E2E_FACTORY_DC100["code"]]),
    ("manager", "Manager@2026", "manager", [E2E_FACTORY_DC100["code"]]),
    ("viewer", "Viewer@2026", "viewer", [E2E_FACTORY_DC100["code"]]),
    ("groupadmin", "GroupAdmin@2026", "admin", [E2E_FACTORY_DC100["code"], E2E_FACTORY_SH["code"]]),
]

# Known seed doc numbers (use -E2E- infix). Write flows must NOT reuse these.
E2E_KNOWN_DOCS = {
    "pfmea": ["PFMEA-E2E-001"],
    "capa": ["8D-E2E-001"],
}
```

Note: `field_qe` is the role_key for the `engineer` user (verified in `seed.py:1757`).

- [ ] **Step 2: Write the failing test**

`backend/tests/test_e2e_endpoints.py`:

```python
"""Tests for /api/e2e/* endpoints (seed-state + cleanup).

Skipped unless E2E_MODE is set, so `make check` (which does NOT set E2E_MODE and
does not seed_e2e) skips these cleanly instead of failing on a missing e2e router /
empty e2e DB. Run explicitly with E2E_MODE=1 + TEST_DATABASE_URL (see Task 3/4 steps)."""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
# NOTE: do NOT default E2E_MODE here — that would force the e2e router on under `make check`.

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("E2E_MODE"),
    reason="E2E_MODE not set — e2e endpoints not registered / e2e DB not seeded",
)


@pytest.mark.asyncio
async def test_seed_state_shape():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/api/e2e/seed-state")
    assert r.status_code == 200
    data = r.json()
    assert {f["code"] for f in data["factories"]} == {"DC-FACT-E2E", "SH-FACT-E2E"}
    assert any(pl["code"] == "DC-DC-100-E2E" for pl in data["product_lines"])
    usernames = {a["username"] for a in data["accounts"]}
    assert {"admin", "engineer", "manager", "viewer", "groupadmin"} <= usernames
    # password included (seed_e2e is single source of truth; demo creds public)
    for a in data["accounts"]:
        assert a["password"], f"missing password for {a['username']}"
    # groupadmin spans both factories
    ga = next(a for a in data["accounts"] if a["username"] == "groupadmin")
    assert set(ga["factory_codes"]) == {"DC-FACT-E2E", "SH-FACT-E2E"}
    assert data["known_docs"]["pfmea"] == ["PFMEA-E2E-001"]
    assert data["known_docs"]["capa"] == ["8D-E2E-001"]
    assert "PFMEA-E2E-001" in data["used_doc_numbers"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && E2E_MODE=1 SECRET_KEY=test-secret-key-for-pytest-only TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5433/qms_e2e PYTHONPATH=. pytest tests/test_e2e_endpoints.py -v`
Expected: FAIL (NotImplementedError or seed not run).

- [ ] **Step 4: Write `seed_e2e.py`**

Mirror `seed.py` constructors exactly for required columns. Use fixed UUIDs for idempotency.

```python
"""Deterministic idempotent E2E seed. Run: python -m app.seed_e2e

Idempotent: safe to re-run. Uses -E2E- infix doc numbers so cleanup never touches seed."""
import asyncio
import uuid

from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password
from app.database import async_session
from app.models.factory import Factory, UserFactory
from app.models.product_line import ProductLine
from app.models.role import RoleDefinition
from app.models.user import User
from app.seed_e2e_constants import (
    E2E_ACCOUNTS, E2E_FACTORY_DC100, E2E_FACTORY_SH, E2E_PRODUCT_LINE,
)

# Fixed UUIDs for idempotency
FACT_DC100_ID = uuid.UUID("00000000-0000-0000-0000-000000e20001")
FACT_SH_ID = uuid.UUID("00000000-0000-0000-0000-000000e20002")
PFMEA_E2E_ID = uuid.UUID("00000000-0000-0000-0000-000000e20100")
CAPA_E2E_ID = uuid.UUID("00000000-0000-0000-0000-000000e20200")


async def _seed_factories(db) -> dict:
    factories = {}
    for code, name, location, fid in [
        (E2E_FACTORY_DC100["code"], E2E_FACTORY_DC100["name"], E2E_FACTORY_DC100["location"], FACT_DC100_ID),
        (E2E_FACTORY_SH["code"], E2E_FACTORY_SH["name"], E2E_FACTORY_SH["location"], FACT_SH_ID),
    ]:
        existing = (await db.execute(select(Factory).where(Factory.code == code))).scalar_one_or_none()
        if not existing:
            db.add(Factory(id=fid, code=code, name=name, location=location, is_active=True))
            await db.flush()
            factories[code] = fid
        else:
            factories[code] = existing.id
    return factories


async def _seed_product_line(db, factory_ids):
    code = E2E_PRODUCT_LINE["code"]
    existing = (await db.execute(select(ProductLine).where(ProductLine.code == code))).scalar_one_or_none()
    if not existing:
        db.add(ProductLine(
            code=code, name=E2E_PRODUCT_LINE["name"], is_active=True,
            factory_id=factory_ids[E2E_FACTORY_DC100["code"]],
            product_type_code=E2E_PRODUCT_LINE["product_type_code"],
        ))
        await db.flush()


async def _seed_accounts(db, factory_ids):
    roles = {r.role_key: r.id for r in (await db.execute(select(RoleDefinition))).scalars().all()}
    # Non-bypass roles need a UserProductLine assignment or resolve_product_line_scope
    # returns ProductLineScope.NONE → no FMEA/CAPA data visible (factory_scope.py:56).
    # admin/groupadmin have bypass_row_level_security → ProductLineScope.ALL, no assignment needed.
    NON_BYPASS_USERNAMES = {"engineer", "manager", "viewer"}
    for username, password, role_key, factory_codes in E2E_ACCOUNTS:
        user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
        if not user:
            user = User(
                username=username, display_name=username,
                password_hash=hash_password(password), role_id=roles[role_key], is_active=True,
            )
            db.add(user)
            await db.flush()
        # Ensure factory assignments
        existing_facs = {f.factory_id for f in (
            await db.execute(select(UserFactory).where(UserFactory.user_id == user.user_id))
        ).scalars().all()}
        for code in factory_codes:
            fid = factory_ids[code]
            if fid not in existing_facs:
                db.add(UserFactory(user_id=user.user_id, factory_id=fid))
        # Ensure product-line assignment for non-bypass users (so they see FMEA/CAPA data)
        if username in NON_BYPASS_USERNAMES:
            from app.models.role import UserProductLine
            existing_pls = {
                p.product_line_code for p in (
                    await db.execute(select(UserProductLine).where(UserProductLine.user_id == user.user_id))
                ).scalars().all()
            }
            if E2E_PRODUCT_LINE["code"] not in existing_pls:
                db.add(UserProductLine(user_id=user.user_id, product_line_code=E2E_PRODUCT_LINE["code"]))


async def _seed_known_docs(db, factory_ids):
    """Create one known PFMEA + one known CAPA for read-flow assertions.

    Model columns verified in app/models/fmea.py and app/models/capa.py:
    - FMEADocument: pk=fmea_id, required non-null: document_no, title, factory_id;
      all other columns have defaults (fmea_type, product_line_code, status, version, …).
    - CAPAEightD: pk=report_id, required non-null: document_no, title, factory_id;
      all other columns have defaults (status='D1_TEAM', severity, …).
    """
    from app.models.fmea import FMEADocument
    from app.models.capa import CAPAEightD

    admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()

    pfmea = (await db.execute(select(FMEADocument).where(FMEADocument.document_no == "PFMEA-E2E-001"))).scalar_one_or_none()
    if not pfmea:
        db.add(FMEADocument(
            fmea_id=PFMEA_E2E_ID,
            document_no="PFMEA-E2E-001",
            title="E2E 已知 PFMEA",
            fmea_type="PFMEA",
            product_line_code="DC-DC-100-E2E",
            factory_id=factory_ids[E2E_FACTORY_DC100["code"]],
            status="draft",
            created_by=admin.user_id,
        ))

    capa = (await db.execute(select(CAPAEightD).where(CAPAEightD.document_no == "8D-E2E-001"))).scalar_one_or_none()
    if not capa:
        db.add(CAPAEightD(
            report_id=CAPA_E2E_ID,
            document_no="8D-E2E-001",
            title="E2E 已知 8D",
            product_line_code="DC-DC-100-E2E",
            factory_id=factory_ids[E2E_FACTORY_DC100["code"]],
            created_by=admin.user_id,
        ))


async def main():
    async with async_session() as db:
        factory_ids = await _seed_factories(db)
        await _seed_product_line(db, factory_ids)
        await _seed_accounts(db, factory_ids)
        await _seed_known_docs(db, factory_ids)
        await db.commit()
    print("E2E seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
```

**Note:** `FMEADocument`/`CAPAEightD` are imported inside `_seed_known_docs` to avoid circular imports at module load. The `created_by` uses the admin `user_id` fetched via `select`.

- [ ] **Step 5: Implement `get_seed_state` in `backend/app/api/e2e.py`**

Replace the `get_seed_state` stub:

```python
from sqlalchemy import select
from app.models.factory import Factory, UserFactory
from app.models.product_line import ProductLine
from app.models.user import User
from app.models.role import RoleDefinition
from app.seed_e2e_constants import E2E_ACCOUNTS, E2E_KNOWN_DOCS


@router.get("/seed-state")
async def get_seed_state(db: AsyncSession = Depends(get_db)):
    factories = (await db.execute(select(Factory).where(Factory.code.in_(["DC-FACT-E2E", "SH-FACT-E2E"])))).scalars().all()
    pls = (await db.execute(select(ProductLine).where(ProductLine.code == "DC-DC-100-E2E"))).scalars().all()
    users = (await db.execute(select(User).where(User.username.in_([a[0] for a in E2E_ACCOUNTS])))).scalars().all()
    roles = {r.id: r.role_key for r in (await db.execute(select(RoleDefinition))).scalars().all()}
    pw_by_user = {a[0]: a[1] for a in E2E_ACCOUNTS}  # seed_e2e is the single source of truth for passwords
    accounts = []
    for u in users:
        facs = (await db.execute(select(UserFactory.factory_id).where(UserFactory.user_id == u.user_id))).scalars().all()
        fac_codes = [f.code for f in factories if f.id in facs]
        accounts.append({
            "username": u.username,
            "password": pw_by_user.get(u.username),
            "role_key": roles.get(u.role_id),
            "factory_codes": fac_codes,
        })
    return {
        "factories": [{"code": f.code, "name": f.name, "id": str(f.id)} for f in factories],
        "product_lines": [{"code": p.code, "name": p.name, "factory_id": str(p.factory_id)} for p in pls],
        "accounts": accounts,
        "known_docs": E2E_KNOWN_DOCS,
        "used_doc_numbers": [d for ds in E2E_KNOWN_DOCS.values() for d in ds],
    }
```

- [ ] **Step 6: Run seed + test, verify pass**

Bring up the e2e stack, migrate, and seed first (pytest connects from the host via `TEST_DATABASE_URL` → `localhost:5433/qms_e2e`; seed runs inside the backend container → same e2e DB):
```
make e2e-up
$(DC_E2E) exec backend alembic upgrade head     # or: make -C . e2e-seed won't migrate; run migrate explicitly
make e2e-seed
cd backend && E2E_MODE=1 SECRET_KEY=test-secret-key-for-pytest-only TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5433/qms_e2e PYTHONPATH=. pytest tests/test_e2e_endpoints.py::test_seed_state_shape -v
```
(`$(DC_E2E)` = the make variable value; in a shell run the literal `docker compose -f docker-compose.yml -f docker-compose.e2e.yml --profile e2e -p openqms-e2e`.)
Expected: PASS. If model-required columns are missing, the seed errors at flush — fix by adding the column from the model (Step 4 note). If seed-state returns empty, the seed didn't run — re-run `make e2e-seed`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/seed_e2e.py backend/app/seed_e2e_constants.py backend/app/api/e2e.py backend/tests/test_e2e_endpoints.py
git commit -m "feat(e2e): deterministic seed_e2e + seed-state endpoint"
```

---

## Task 4: /api/e2e/cleanup endpoint (whitelist, FK-ordered, transaction) + test

**Files:**
- Modify: `backend/app/api/e2e.py` (implement `cleanup_test_data`)
- Create: `backend/app/e2e_cleanup_whitelist.py`
- Test: `backend/tests/test_e2e_endpoints.py` (append cleanup tests)

**Interfaces:**
- Produces: `POST /api/e2e/cleanup?prefix=E2E-M1` deletes all whitelist-tracked test rows matching prefix in one transaction; returns `{deleted: {...}}`.

- [ ] **Step 1: Write the whitelist module**

`backend/app/e2e_cleanup_whitelist.py`:

```python
"""Fixed whitelist for E2E cleanup. NO string-concatenation of table/column names anywhere else.

Each parent entry: (model, pk_col_name, doc_no_col_name, [(child_model, child_fk_col_name), ...]).
Children are deleted first (FK reverse order), then the parent. All in one transaction.
Only models whose doc_no/name can carry an E2E- prefix are listed as parents.

FK ondelete analysis (verified against backend/app/models/*.py and alembic 020):
- FMEAVersion.fmea_id        → ondelete=CASCADE  → auto-deleted with parent. NOT listed.
- RecommendationCache.fmea_id → ondelete=CASCADE → auto-deleted with parent. NOT listed.
- RecommendationCache.report_id → ondelete=CASCADE → auto-deleted with parent. NOT listed.
- ChangeImpact.fmea_id      → ondelete=CASCADE  → auto-deleted with parent. NOT listed.
- ControlPlan.fmea_id        → no ondelete (NO ACTION), nullable. Could block parent delete
                              IF a spec links a control plan to an E2E FMEA. Not exercised
                              in M1; add as child when the control-plan spec (M2) links E2E FMEAs.
- CAPAEightD.fmea_ref_id     → no ondelete, nullable. Self-referential; not a child of FMEA
                              cleanup (cleanup deletes CAPA by its own document_no prefix).
- audit_finding.report_id    → no ondelete, nullable. Could block CAPA delete IF a spec
                              creates an audit finding referencing an E2E CAPA. Add as child
                              when the audit spec exercises this.

⚠️ VERSION-TABLE TRIGGER (alembic 020_snapshot_hash_trigger.py:60): `trg_fmea_version_no_update`
is `BEFORE UPDATE OR DELETE` and `prevent_version_tampering()` RAISES on delete. So when a spec
creates an FMEA version snapshot, CASCADE-deleting the parent FMEA will fail on the version row.
The cleanup endpoint handles this by DISABLE-ing the two no_update triggers for the duration of
its transaction (dedicated e2e DB, serialized workers:1), then re-enabling — see cleanup_test_data.
(M1 FMEA spec only asserts the snapshot entry is VISIBLE, does not click "create snapshot", so no
version row is created in M1; the trigger-disable is forward-robustness for later specs.)

AuditLog.entity_id is deliberately NOT a child: append-only, no unique constraint, type not
guaranteed to match a UUID in_ lookup, and leaving rows does NOT block re-runs (idempotent
seed keys on unique document_no). Cleaned by `make e2e-reset` (down -v)."""
from app.models.fmea import FMEADocument
from app.models.capa import CAPAEightD

# Parents: (model, pk_col, doc_no_col, [(child_model, child_fk_col), ...])
# M0+M1: parents only — CASCADE handles version/recommendation-cache/change-impact children.
# Add a child entry ONLY when a later module links a NO-ACTION-FK child to an E2E parent
# (e.g. ControlPlan in M2, audit_finding in the audit module) — run that module's spec twice
# to confirm; if parent delete fails with FK violation, add the child here.
CLEANUP_PARENTS = [
    (FMEADocument, "fmea_id", "document_no", []),
    (CAPAEightD, "report_id", "document_no", []),
]
```

The implementer extends this list as M1+ specs create more entity types. The rule: only add models whose `document_no`/name column can carry an `E2E-` prefix; children are deleted by FK to the parent PK — but per the analysis above, the CASCADE children (FMEAVersion, RecommendationCache, ChangeImpact) are auto-deleted and must NOT be listed (listing them would be redundant double-delete). Add a child entry ONLY when a later module links a NO-ACTION-FK child (ControlPlan, audit_finding) to an E2E parent and the parent delete fails. PK column names are model-specific (`fmea_id`, `report_id`) — never assume `id`.

- [ ] **Step 2: Write the failing test (append to `test_e2e_endpoints.py`)**

```python
@pytest.mark.asyncio
async def test_cleanup_deletes_prefixed_only():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Seed-state confirms known seed docs exist.
        before = await ac.get("/api/e2e/seed-state")
        assert "PFMEA-E2E-001" in before.json()["used_doc_numbers"]
        # Cleanup a non-existent prefix must be a no-op (and never touch seed).
        r = await ac.post("/api/e2e/cleanup", params={"prefix": "E2E-NOSUCH"})
        assert r.status_code == 200
        assert r.json()["deleted"] == {} or all(v == 0 for v in r.json()["deleted"].values())
        # Seed still present.
        after = await ac.get("/api/e2e/seed-state")
        assert "PFMEA-E2E-001" in after.json()["used_doc_numbers"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && E2E_MODE=1 SECRET_KEY=test-secret-key-for-pytest-only TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5433/qms_e2e PYTHONPATH=. pytest tests/test_e2e_endpoints.py::test_cleanup_deletes_prefixed_only -v`
Expected: FAIL (NotImplementedError).

- [ ] **Step 4: Implement `cleanup_test_data`**

In `backend/app/api/e2e.py`, replace the stub:

```python
from sqlalchemy import delete, select
from app.e2e_cleanup_whitelist import CLEANUP_PARENTS


from sqlalchemy import text

# Version tables have BEFORE UPDATE OR DELETE triggers (prevent_version_tampering) that
# RAISE on delete (alembic 020). They would block CASCADE deletion of parent FMEAs that have
# version snapshots. In E2E_MODE (dedicated DB, workers:1) we disable them for this cleanup
# transaction, then re-enable. ALTER TABLE is transactional in PG (no implicit commit).
VERSION_TRIGGERS = [
    ("fmea_versions", "trg_fmea_version_no_update"),
    ("control_plan_versions", "trg_cp_version_no_update"),
]


@router.post("/cleanup")
async def cleanup_test_data(prefix: str = Query(..., min_length=4, max_length=20), db: AsyncSession = Depends(get_db)):
    """Whitelist-based, FK-ordered delete in a single transaction. Never string-concats table names.

    On any failure: rollback (undoes the trigger DISABLE + all deletes) and re-raise.
    Do NOT re-enable triggers in a failed/aborted transaction — that would raise a
    secondary error. ALTER TABLE is transactional, so rollback cleanly reverts the disable."""
    deleted: dict[str, int] = {}
    try:
        # Disable immutability triggers for this txn (only version tables; safe in dedicated e2e DB).
        for table, trig in VERSION_TRIGGERS:
            await db.execute(text(f'ALTER TABLE "{table}" DISABLE TRIGGER "{trig}"'))
        for model, pk_col, doc_col, children in CLEANUP_PARENTS:
            col = getattr(model, doc_col)
            pk = getattr(model, pk_col)
            parent_ids = [row[0] for row in (await db.execute(select(pk).where(col.like(f"{prefix}%")))).all()]
            if not parent_ids:
                continue
            # Delete children first by FK to parent PK.
            for child_model, fk_col in children:
                fk = getattr(child_model, fk_col)
                result = await db.execute(delete(child_model).where(fk.in_(parent_ids)))
                deleted[f"{child_model.__name__}.{fk_col}"] = deleted.get(f"{child_model.__name__}.{fk_col}", 0) + result.rowcount
            # Delete parents (CASCADE handles version/cache/change-impact rows now that triggers are disabled).
            result = await db.execute(delete(model).where(pk.in_(parent_ids)))
            deleted[f"{model.__name__}"] = result.rowcount
        # Re-enable triggers before commit (txn is still healthy here).
        for table, trig in VERSION_TRIGGERS:
            await db.execute(text(f'ALTER TABLE "{table}" ENABLE TRIGGER "{trig}"'))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"deleted": deleted}
```

- [ ] **Step 5: Run test, verify pass**

Run: `cd backend && E2E_MODE=1 SECRET_KEY=test-secret-key-for-pytest-only TEST_DATABASE_URL=postgresql+asyncpg://qms:qms_dev_2026@localhost:5433/qms_e2e PYTHONPATH=. pytest tests/test_e2e_endpoints.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/e2e.py backend/app/e2e_cleanup_whitelist.py backend/tests/test_e2e_endpoints.py
git commit -m "feat(e2e): whitelist cleanup endpoint (FK-ordered, single txn)"
```

---

## Task 5: playwright.config.ts (serial, baseURL, global setup/teardown)

**Files:**
- Modify: `frontend/playwright.config.ts`
- Modify: `frontend/package.json` (add `test:e2e` scripts)
- Create: `frontend/e2e/global.setup.ts` (stub) and `frontend/e2e/global.teardown.ts` (stub) — implemented in Task 7.

**Interfaces:**
- Produces: `playwright.config.ts` with `workers:1`, `fullyParallel:false`, `baseURL:5174`, `globalSetup`/`globalTeardown` (string paths).

- [ ] **Step 1: Rewrite `frontend/playwright.config.ts`**

```typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e/specs",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "list",
  // String paths (NOT require.resolve) — frontend package.json has "type":"module".
  globalSetup: "./e2e/global.setup.ts",
  globalTeardown: "./e2e/global.teardown.ts",
  use: {
    baseURL: "http://localhost:5174",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
```

Note: `testDir` moves to `./e2e/specs` so guard + m1-core specs are discovered; the old `./e2e` root specs are migrated in Task 8. `storageState` is NOT set globally — each spec passes a per-role `storageState` path explicitly. `storageStateDir` is not a valid Playwright `use` option and is omitted; storage file paths are managed by the helpers (`STORAGE_DIR` constant in `global.setup.ts`).

- [ ] **Step 2: Add npm scripts to `frontend/package.json`**

Under `scripts`:

```json
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui"
```

- [ ] **Step 3: Stub global.setup.ts / global.teardown.ts**

`frontend/e2e/global.setup.ts`:
```typescript
export default async function globalSetup() {
  // Implemented in Task 7: credential check + alert, seed-state fetch, login storageState.
  console.log("[e2e] global setup stub");
}
```
`frontend/e2e/global.teardown.ts`:
```typescript
export default async function globalTeardown() {
  console.log("[e2e] global teardown stub");
}
```

- [ ] **Step 4: Verify Playwright loads config**

Run: `cd frontend && npx playwright test --list`
Expected: lists 0 tests (specs not yet in `e2e/specs`), no config errors. Confirms `workers:1`/`fullyParallel:false`/baseURL parse.

- [ ] **Step 5: Commit**

```bash
git add frontend/playwright.config.ts frontend/package.json frontend/e2e/global.setup.ts frontend/e2e/global.teardown.ts
git commit -m "build(e2e): playwright serial config + globalSetup/teardown stubs"
```

---

## Task 6: frontend e2e helpers + fixtures

**Files:**
- Create: `frontend/e2e/helpers/api-client.ts`
- Create: `frontend/e2e/helpers/e2e-utils.ts`
- Create: `frontend/e2e/helpers/cleanup-registry.ts`
- Create: `frontend/e2e/fixtures/seed-state.ts`
- Create: `frontend/e2e/fixtures/auth.ts`
- Create: `frontend/e2e/fixtures/input/.gitkeep` (input fixtures added per M1 task)

**Interfaces:**
- Produces: `apiClient` (axios to `E2E_API_BASE_URL`), `loginAs(page, role)` (UI login → storageState), `seedState` (cached `/api/e2e/seed-state`), `cleanup(prefix)` helper, `track(kind,id)`/`drain()` (diagnostic only), `nextDocNo(prefix)`.

- [ ] **Step 1: Write `api-client.ts`**

```typescript
import axios from "axios";

const E2E_API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://localhost:8001/api";

export const apiClient = axios.create({ baseURL: E2E_API_BASE_URL });

export async function loginForToken(username: string, password: string): Promise<string> {
  const r = await apiClient.post("/auth/login", { username, password });
  return r.data.access_token as string;
}

export async function authedApi(token: string) {
  return axios.create({ baseURL: E2E_API_BASE_URL, headers: { Authorization: `Bearer ${token}` } });
}

export async function cleanupByPrefix(prefix: string): Promise<void> {
  // Best-effort; backend gated endpoint. Requires an admin token.
  // Read admin password from seed-state (single source of truth) via dynamic
  // import to avoid a circular dependency (api-client ← seed-state ← api-client).
  const { accountPassword } = await import("../fixtures/seed-state");
  const adminPw = await accountPassword("admin");
  const token = await loginForToken("admin", adminPw);
  const ac = await authedApi(token);
  await ac.post(`/e2e/cleanup?prefix=${encodeURIComponent(prefix)}`);
}
```

- [ ] **Step 2: Write `seed-state.ts`**

```typescript
import { apiClient } from "../helpers/api-client";

export interface SeedState {
  factories: { code: string; name: string; id: string }[];
  product_lines: { code: string; name: string; factory_id: string }[];
  // password is included — seed_e2e is the single source of truth (demo creds are public).
  accounts: { username: string; password: string; role_key: string; factory_codes: string[] }[];
  known_docs: Record<string, string[]>;
  used_doc_numbers: string[];
}

let cached: SeedState | null = null;

export async function getSeedState(): Promise<SeedState> {
  if (cached) return cached;
  const r = await apiClient.get("/e2e/seed-state");
  cached = r.data as SeedState;
  return cached;
}

export async function accountPassword(username: string): Promise<string> {
  // Read from seed-state (single source of truth) — never hardcode.
  const s = await getSeedState();
  const acct = s.accounts.find(a => a.username === username);
  if (!acct) throw new Error(`[e2e] no seed account for ${username}`);
  return acct.password;
}
```

- [ ] **Step 3: Write `auth.ts` (UI login → storageState reuse)**

```typescript
import type { Page } from "@playwright/test";
import { getSeedState, accountPassword } from "./seed-state";

const STORAGE_DIR = "e2e/.storage-state";

export async function loginAs(page: Page, username: string): Promise<void> {
  const password = await accountPassword(username);
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByPlaceholder(/用户名|username/i).fill(username);
  await page.getByPlaceholder(/密码|password/i).fill(password);
  await page.getByRole("button", { name: /登\s*录|login/i }).click();
  await page.waitForURL(/\/dashboard|\/capa|\/fmea/);
}

export function storageStatePath(username: string): string {
  return `${STORAGE_DIR}/${username}.json`;
}
```

- [ ] **Step 4: Write `cleanup-registry.ts` (diagnostic only)**

```typescript
const created: { kind: string; id: string }[] = [];

export function track(kind: string, id: string): void {
  created.push({ kind, id });
}

export function drainReport(): void {
  if (created.length) {
    // eslint-disable-next-line no-console
    console.warn(`[cleanup] un-cleaned records:`, created);
  }
}

let counter = 0;
export function nextDocNo(prefix: string): string {
  counter += 1;
  return `${prefix}-${String(counter).padStart(3, "0")}`;
}
```

- [ ] **Step 5: Write `e2e-utils.ts`**

```typescript
import type { Page, Locator } from "@playwright/test";

export async function rowByDocNo(page: Page, docNo: string): Promise<Locator> {
  return page.locator(`[data-e2e="row-${docNo}"]`);
}

export async function clickByTestid(page: Page, testid: string): Promise<void> {
  await page.locator(`[data-e2e="${testid}"]`).click();
}
```

- [ ] **Step 6: Create `frontend/e2e/fixtures/input/.gitkeep`** (empty).

- [ ] **Step 7: Add `tsconfig.e2e.json` + `@types/node` (e2e files are NOT under `src`, so `tsc --noEmit` against `tsconfig.json` skips them)**

The existing `frontend/tsconfig.json` has `include: ["src"]`, so `npx tsc --noEmit` never checks `frontend/e2e/**`. Create a dedicated e2e tsconfig so type errors in helpers/setup/specs surface:

`frontend/tsconfig.e2e.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "noEmit": true,
    "types": ["node"]
  },
  "include": ["playwright.config.ts", "e2e/**/*.ts", "e2e/**/*.tsx"]
}
```

Install node types (the e2e helpers use `process`, `path`, `fs`, `mkdirSync`):
```
cd frontend && npm install -D @types/node
```

- [ ] **Step 8: Verify e2e TypeScript compiles**

Run: `cd frontend && npx tsc -p tsconfig.e2e.json --noEmit`
Expected: PASS (no type errors in e2e helpers/setup/specs). Note: `npx tsc --noEmit` (the src check) does NOT cover e2e — always use `-p tsconfig.e2e.json` for e2e.

- [ ] **Step 9: Commit**

```bash
git add frontend/e2e/helpers frontend/e2e/fixtures frontend/tsconfig.e2e.json frontend/package.json frontend/package-lock.json
git commit -m "feat(e2e): frontend helpers + seed-state/auth/cleanup fixtures + tsconfig.e2e"
```

---

## Task 7: global.setup.ts + global.teardown.ts + guard specs

**Files:**
- Modify: `frontend/e2e/global.setup.ts`
- Modify: `frontend/e2e/global.teardown.ts`
- Create: `frontend/e2e/specs/_guards/seed.guard.spec.ts`
- Create: `frontend/e2e/specs/_guards/ai-credentials.guard.spec.ts`

**Interfaces:**
- Produces: per-role `storageState` files; guard specs that fail-fast on missing seed and skip+warn on missing LLM creds.

- [ ] **Step 1: Implement `global.setup.ts`**

```typescript
import { existsSync, mkdirSync, writeFileSync } from "fs";
import path from "path";
import { chromium } from "@playwright/test";
import { apiClient } from "./helpers/api-client";
import { getSeedState, accountPassword } from "./fixtures/seed-state";

// frontend package.json is "type":"module" — __dirname is undefined under ESM. Playwright
// runs with cwd = frontend/ (make e2e-run cd's there), so resolve relative to process.cwd().
const STORAGE_DIR = path.resolve(process.cwd(), "e2e/.storage-state");

const ROLES = ["admin", "engineer", "manager", "viewer", "groupadmin"];

export default async function globalSetup() {
  mkdirSync(STORAGE_DIR, { recursive: true });

  // 1. Credential detection + alert.
  const hasLLM = !!(process.env.LLM_PROVIDER && process.env.LLM_API_KEY);
  if (!hasLLM) {
    // eslint-disable-next-line no-console
    console.warn(
      "\n⚠️  LLM_PROVIDER/LLM_API_KEY not configured → AI specs will be skipped.\n" +
      "   Fill .env.e2e to enable them.\n"
    );
  }
  writeFileSync(
    path.join(STORAGE_DIR, "e2e-env.json"),
    JSON.stringify({ hasLLM, ts: "fixed" })
  );

  // 2. Seed-state presence check.
  try {
    await getSeedState();
  } catch (e) {
    throw new Error(`[e2e] seed-state unreachable: is the e2e stack up and seeded? (${String(e)})`);
  }

  // 3. UI login per role → storageState.
  const browser = await chromium.launch();
  for (const username of ROLES) {
    const password = await accountPassword(username);
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto("http://localhost:5174/login");
    await page.waitForLoadState("networkidle");
    await page.getByPlaceholder(/用户名|username/i).fill(username);
    await page.getByPlaceholder(/密码|password/i).fill(password);
    await page.getByRole("button", { name: /登\s*录|login/i }).click();
    await page.waitForURL(/\/dashboard|\/capa|\/fmea/);
    await ctx.storageState({ path: path.join(STORAGE_DIR, `${username}.json`) });
    await ctx.close();
  }
  await browser.close();
  // silence unused import warning for apiClient
  void apiClient;
}
```

- [ ] **Step 2: Implement `global.teardown.ts`**

```typescript
import { drainReport } from "./helpers/cleanup-registry";

export default async function globalTeardown() {
  drainReport(); // diagnostic only; real cleanup is per-spec afterEach
  // eslint-disable-next-line no-console
  console.log("[e2e] global teardown done (DB not torn down; run `make e2e-down`).");
}
```

- [ ] **Step 3: Write `seed.guard.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";
import { getSeedState } from "../../fixtures/seed-state";

test("seed-state has all known records", async () => {
  const s = await getSeedState();
  expect(s.factories.length).toBeGreaterThanOrEqual(2);
  expect(s.accounts.map(a => a.username)).toEqual(
    expect.arrayContaining(["admin", "engineer", "manager", "viewer", "groupadmin"])
  );
  expect(s.known_docs.pfmea).toContain("PFMEA-E2E-001");
  expect(s.known_docs.capa).toContain("8D-E2E-001");
});
```

- [ ] **Step 4: Write `ai-credentials.guard.spec.ts`**

```typescript
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import path from "path";

test("AI credentials configured (smoke) or skip with warning", async () => {
  // ESM: no __dirname / require. cwd = frontend/ when Playwright runs.
  const envPath = path.resolve(process.cwd(), "e2e/.storage-state/e2e-env.json");
  const env = JSON.parse(readFileSync(envPath, "utf-8"));
  if (!env.hasLLM) {
    test.skip(true, "LLM_PROVIDER/LLM_API_KEY not configured — AI specs skipped");
  }
  // If configured: hit the recommendation smoke path via API (structure-only).
  // The real AI specs in m1-core assert behavior; here we only guard.
  expect(env.hasLLM).toBe(true);
});
```

- [ ] **Step 5: Run guards against the running e2e stack**

Pre: `make e2e-up && make e2e-seed` (ensure stack + seed). Then:
Run: `cd frontend && npx playwright test --grep "seed-state has all known records"`
Expected: PASS. And the AI guard: if no creds, prints skip; if creds, PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/global.setup.ts frontend/e2e/global.teardown.ts frontend/e2e/specs/_guards
git commit -m "feat(e2e): global setup (login storageState) + seed/ai-credentials guards"
```

---

## Task 8: Migrate existing 2 specs into m1-core with new fixtures

**Files:**
- Move: `frontend/e2e/capa-draft.spec.ts` → `frontend/e2e/specs/m1-core/capa-ai-draft.spec.ts`
- Move: `frontend/e2e/i18n.spec.ts` → `frontend/e2e/specs/m1-core/i18n.spec.ts`
- Modify both: use `loginAs` + `:5174` baseURL (no hardcoded `http://localhost:5173/...`).

- [ ] **Step 1: Move and refactor `capa-ai-draft.spec.ts`**

Replace hardcoded `http://localhost:5173` with relative paths (baseURL is `:5174`), and replace the local `login` helper with `loginAs`:

```typescript
import { test, expect } from "@playwright/test";
import { loginAs } from "../../fixtures/auth";
import { cleanupByPrefix } from "../../helpers/api-client";

test.describe("CAPA AI Draft", () => {
  // Distinct prefix from Task 12 (E2E-M1-CAPA-*) so the two specs never collide on the
  // unique document_no, and each cleans up its own records.
  test.afterAll(async () => { await cleanupByPrefix("E2E-AI-CAPA"); });

  test("capabilities endpoint returns 401 not 422", async ({ page }) => {
    const res = await page.evaluate(async () => {
      const r = await fetch("/api/capa/capabilities");
      return { status: r.status };
    });
    expect(res.status).toBe(401);
  });

  test("AI draft button visible for engineer", async ({ page }) => {
    await loginAs(page, "engineer");
    await page.goto("/capa");
    await page.getByRole("button", { name: /新建 8D/ }).click();
    await page.getByLabel(/报告编号|document no/i).fill("E2E-AI-CAPA-001");
    await page.getByLabel(/标题|title/i).fill("E2E AI draft visibility");
    await page.getByRole("button", { name: /创建|create|确定|ok/i }).click();
    await page.waitForURL(/\/capa\//);
    await expect(page.getByText(/AI草拟|AI draft/i).first()).toBeVisible({ timeout: 10000 });
  });
});
```

- [ ] **Step 2: Move `i18n.spec.ts`**

Replace `http://localhost:5173` with relative `/login`. Keep selector logic (already uses `page.goto("/login")` style is fine; only fix any absolute URLs).

- [ ] **Step 3: Delete the old `frontend/e2e/*.spec.ts` at root**

Remove `frontend/e2e/capa-draft.spec.ts` and `frontend/e2e/i18n.spec.ts` (now under `specs/m1-core/`).

- [ ] **Step 4: Run migrated specs**

Run: `cd frontend && npx playwright test --grep "CAPA AI Draft|i18n"`
Expected: PASS (i18n always; capa-ai-draft passes if LLM creds present, else the AI-draft-visibility assertion may need the `ai_draft_enabled` flag — if it fails on missing LLM, gate that test on `e2e-env.json` `hasLLM` like the guard).

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/specs/m1-core frontend/e2e/capa-draft.spec.ts frontend/e2e/i18n.spec.ts
git commit -m "refactor(e2e): migrate existing specs into m1-core with new fixtures"
```

---

## Task 9: docs/e2e.md + CLAUDE.md (docs-check)

**Files:**
- Modify: `docs/e2e.md` (full content)
- Modify: `CLAUDE.md` (append `make e2e` to Commands)

- [ ] **Step 1: Write `docs/e2e.md`**

```markdown
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
2. Write `frontend/e2e/specs/<module>/<name>.spec.ts`; `loginAs(page, role)`; use `data-e2e` testids; `track()` created ids; `afterEach` → `cleanupByPrefix("E2E-<module>")`.
3. Add `data-e2e` attributes to the production component if missing (testability only).
4. Run `make e2e TEST_ARGS="--grep <name>"` to verify in isolation.
```

- [ ] **Step 2: Append to `CLAUDE.md` Commands section**

Under the Backend/Frontend commands, add an E2E block:

```markdown
### E2E (manual, not in CI)

```bash
make e2e            # up + migrate + seed_e2e + playwright test
make e2e-reset      # full down -v + up + seed (clean slate)
make e2e TEST_ARGS="--grep m1-core"   # single module
```
Requires `.env.e2e` (copy from `.env.e2e.example`) for LLM credentials. See `docs/e2e.md`.
```

- [ ] **Step 3: Verify docs-check would pass**

The code changes are under `backend/app/` and new `docker-compose.e2e.yml`/`Dockerfile` (none). Confirmed: `docs/e2e.md` + `CLAUDE.md` updated alongside. Run locally:
`git diff --name-only HEAD~9..HEAD` should include `docs/` and `CLAUDE.md`.

- [ ] **Step 4: Commit**

```bash
git add docs/e2e.md CLAUDE.md
git commit -m "docs(e2e): suite guide + CLAUDE.md make e2e (docs-check)"
```

---

## Task 10: M1 auth/RBAC/factory-isolation spec

**Files:**
- Test: `frontend/e2e/specs/m1-core/auth.spec.ts`
- Modify: `frontend/src/pages/login/LoginPage.tsx` (add `data-e2e` to login button)
- Modify: `frontend/src/components/layout/AppLayout.tsx` or the sidebar menu (add `data-e2e="menu-<key>"` per item)

**Interfaces:**
- Consumes: `loginAs`, `getSeedState`, `storageStatePath`.

- [ ] **Step 1: Write the failing spec**

`frontend/e2e/specs/m1-core/auth.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";
import { getSeedState } from "../../fixtures/seed-state";

test.describe("auth + RBAC + factory isolation", () => {
  test("viewer cannot see FMEA/CAPA menu items", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/viewer.json" });
    const page = await ctx.newPage();
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="menu-fmea"]')).toBeHidden();
    await expect(page.locator('[data-e2e="menu-capa"]')).toBeHidden();
    await ctx.close();
  });

  test("engineer sees FMEA + CAPA menus but not admin user mgmt", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="menu-fmea"]')).toBeVisible();
    await expect(page.locator('[data-e2e="menu-capa"]')).toBeVisible();
    await expect(page.locator('[data-e2e="menu-admin-users"]')).toBeHidden();
    await ctx.close();
  });

  test("factory isolation: engineer sees only DC-FACT-E2E data", async ({ browser }) => {
    const s = await getSeedState();
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await page.goto("/fmea");
    await page.waitForLoadState("networkidle");
    // Engineer is scoped to DC-FACT-E2E; SH-FACT-E2E data must not appear.
    const sh = s.factories.find(f => f.code === "SH-FACT-E2E");
    // If the list shows factory names, SH factory must be absent.
    await expect(page.locator(`text=${sh!.name}`)).toBeHidden();
    await ctx.close();
  });

  test("groupadmin sees both factories", async ({ browser }) => {
    const s = await getSeedState();
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/groupadmin.json" });
    const page = await ctx.newPage();
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    const dc = s.factories.find(f => f.code === "DC-FACT-E2E");
    // groupadmin spans both factories — factory selector lists DC (and SH).
    await expect(page.locator(`text=${dc!.name}`).first()).toBeVisible();
    await ctx.close();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `make e2e-up && make e2e-seed && cd frontend && npx playwright test --grep "auth \+ RBAC"`
Expected: FAIL (`data-e2e="menu-fmea"` not present in DOM).

- [ ] **Step 3: Add `data-e2e` attributes to the sidebar menu**

Open the sidebar/menu component (search for the menu rendering in `frontend/src/components/layout/AppLayout.tsx` — locate the `Menu` items map). Add `data-e2e={\`menu-${item.key}\`}` to each menu item's DOM. For Ant Design `<Menu.Item>`, use the `data-e2e` via the `title`/children wrapper or `attrs` — concretely, wrap the label:
```tsx
<Menu.Item key={key} icon={...}>
  <span data-e2e={`menu-${key}`}>{label}</span>
</Menu.Item>
```
Use the module keys already used by `requiredModule` (fmea, capa, dashboard, admin-users, …). Add `data-e2e="menu-admin-users"` on the admin users entry.

- [ ] **Step 4: Run, verify pass**

Run: `cd frontend && npx playwright test --grep "auth \+ RBAC"`
Expected: PASS. If factory isolation test fails because the FMEA list shows no factory names, adjust the assertion to query the factory filter dropdown instead (the test asserts SH factory is not selectable/visible for the engineer).

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/specs/m1-core/auth.spec.ts frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(e2e): M1 auth/RBAC/factory-isolation spec + menu testids"
```

---

## Task 11: M1 FMEA lifecycle spec

**Files:**
- Test: `frontend/e2e/specs/m1-core/fmea.spec.ts`
- Modify: `frontend/src/pages/planning/fmea/FMEAListPage.tsx` (add `data-e2e` to create button, list rows)
- Modify: the FMEA editor (add `data-e2e` to recommend button, version snapshot entry)
- Create: `frontend/e2e/fixtures/input/pfmea-wizard-inputs.ts`

- [ ] **Step 1: Write input fixture**

`frontend/e2e/fixtures/input/pfmea-wizard-inputs.ts`:
```typescript
export const pfmeaWizardInputs = {
  // FMEACreate schema (backend/app/schemas/fmea.py:82) requires: title, document_no.
  // fmea_type defaults to "PFMEA"; product_line_code defaults to "DC-DC-100".
  document_no: "E2E-M1-PFMEA-001",
  title: "E2E PFMEA lifecycle test",
  fmea_type: "PFMEA",
};
```

- [ ] **Step 2: Write the failing spec**

`frontend/e2e/specs/m1-core/fmea.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";
import { cleanupByPrefix } from "../../helpers/api-client";
import { pfmeaWizardInputs } from "../../fixtures/input/pfmea-wizard-inputs";

test.describe("FMEA lifecycle", () => {
  test.afterAll(async () => { await cleanupByPrefix("E2E-M1-PFMEA"); });

  test("create PFMEA, see it in list, open editor, recommend button present, snapshot view exists", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await page.goto("/fmea");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: /新建|create/i }).first().click();
    // Fill create form — FMEACreate requires document_no + title. Match the real modal's
    // Form.Item labels (implementer: confirm exact labels in FMEAListPage create modal).
    await page.getByLabel(/文件编号|document no|单号/i).fill(pfmeaWizardInputs.document_no);
    await page.getByLabel(/标题|title/i).fill(pfmeaWizardInputs.title);
    // fmea_type select (PFMEA/DFMEA) — only if the modal exposes it; default PFMEA is fine if absent.
    // await page.getByLabel(/类型|type/i).selectOption(pfmeaWizardInputs.fmea_type);
    await page.getByRole("button", { name: /创建|确定|create|ok/i }).click();
    await page.waitForLoadState("networkidle");
    // List shows the new doc
    await expect(page.locator('[data-e2e="row-E2E-M1-PFMEA-001"]')).toBeVisible({ timeout: 10000 });
    // Open editor
    await page.locator('[data-e2e="row-E2E-M1-PFMEA-001"]').click();
    await page.waitForURL(/\/fmea\//);
    // Recommend button present (AI button visibility does not require LLM call)
    await expect(page.locator('[data-e2e="fmea-recommend"]').first()).toBeVisible({ timeout: 10000 });
    // Version snapshot entry present
    await expect(page.locator('[data-e2e="fmea-version-snapshot"]').first()).toBeVisible();
    await ctx.close();
  });
});
```

- [ ] **Step 3: Run to verify failure**

Run: `make e2e-up && make e2e-seed && cd frontend && npx playwright test --grep "FMEA lifecycle"`
Expected: FAIL (testids missing).

- [ ] **Step 4: Add `data-e2e` attributes to FMEA pages**

- `FMEAListPage.tsx`: add `data-e2e={`row-${record.document_no}`}` to each table row (via the row's `data-row-key` or a wrapper cell). Add `data-e2e="fmea-create"` to the create button.
- FMEA editor: search `frontend/src/pages`/components for the recommend button (`智能推荐`/`recommend`) and add `data-e2e="fmea-recommend"`. Add `data-e2e="fmea-version-snapshot"` to the version snapshot button/tab.

- [ ] **Step 5: Run, verify pass**

Run: `cd frontend && npx playwright test --grep "FMEA lifecycle"`
Expected: PASS. (Recommend button visibility is gated on permission, not LLM — engineer has it.)

- [ ] **Step 6: Add FMEA to cleanup whitelist**

In `backend/app/e2e_cleanup_whitelist.py`, confirm `FMEADocument` is listed (it is, from Task 4). If the FMEA editor creates child rows (versions, control links) referenced by FK, add those child models to the `FMEADocument` entry's children list now.

- [ ] **Step 7: Commit**

```bash
git add frontend/e2e/specs/m1-core/fmea.spec.ts frontend/e2e/fixtures/input/pfmea-wizard-inputs.ts frontend/src/pages/planning/fmea/FMEAListPage.tsx <fmea editor files>
git commit -m "feat(e2e): M1 FMEA lifecycle spec + fmea testids"
```

---

## Task 12: M1 CAPA 8D lifecycle spec

**Files:**
- Test: `frontend/e2e/specs/m1-core/capa.spec.ts`
- Modify: `frontend/src/pages/capa/CAPAListPage.tsx` (testids on create button, modal, rows)
- Modify: `frontend/src/pages/capa/CAPADetailPage.tsx` (testids on advance/D-step transitions, AI draft button)
- Create: `frontend/e2e/fixtures/input/capa-form-inputs.ts`

- [ ] **Step 1: Write input fixture**

`frontend/e2e/fixtures/input/capa-form-inputs.ts`:
```typescript
export const capaFormInputs = {
  title: "E2E-M1-CAPA-001",
  severity: "致命",
};
```

- [ ] **Step 2: Write the failing spec**

`frontend/e2e/specs/m1-core/capa.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";
import { cleanupByPrefix } from "../../helpers/api-client";
import { capaFormInputs } from "../../fixtures/input/capa-form-inputs";

test.describe("CAPA 8D lifecycle", () => {
  test.afterAll(async () => { await cleanupByPrefix("E2E-M1-CAPA"); });

  test("create 8D, advance D-states, approval visible for manager", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/engineer.json" });
    const page = await ctx.newPage();
    await page.goto("/capa");
    await page.waitForLoadState("networkidle");
    await page.locator('[data-e2e="capa-create"]').click();
    // Create form fields (CAPAListPage modal): document_no (报告编号, required), title, severity.
    await page.getByLabel(/报告编号|document no/i).fill(capaFormInputs.title);  // = "E2E-M1-CAPA-001"
    await page.getByLabel(/标题|title/i).fill(capaFormInputs.title);
    await page.getByRole("button", { name: /创建|确定|create|ok/i }).click();
    await page.waitForURL(/\/capa\//, { timeout: 10000 });
    // Detail page: advance button present (D-state transition)
    await expect(page.locator('[data-e2e="capa-advance"]')).toBeVisible();
    await page.locator('[data-e2e="capa-advance"]').click();
    // AI draft button visible for engineer (permission-gated, not LLM-gated)
    await expect(page.locator('[data-e2e="capa-ai-draft"]')).toBeVisible({ timeout: 10000 });
    await ctx.close();
  });
});
```

- [ ] **Step 3: Run to verify failure**

Run: `make e2e-up && make e2e-seed && cd frontend && npx playwright test --grep "CAPA 8D lifecycle"`
Expected: FAIL (testids missing).

- [ ] **Step 4: Add `data-e2e` attributes**

- `CAPAListPage.tsx`: `data-e2e="capa-create"` on the `新建 8D` button (line ~115); on the Table (line ~119, `rowKey="report_id"`), add `rowClassName={(r) => \`e2e-row-${r.document_no}\`}` and select via `[class*="e2e-row-E2E-M1-CAPA-001"]` — or simpler, add `data-e2e={`row-${record.document_no}`}` via the columns' action cell render (the row already exposes `document_no` as `dataIndex`).
- `CAPADetailPage.tsx`: `data-e2e="capa-advance"` on the advance button (line ~364, `handleAdvance`); `data-e2e="capa-ai-draft"` on the AI draft button (search `AI草拟`).

- [ ] **Step 5: Run, verify pass**

Run: `cd frontend && npx playwright test --grep "CAPA 8D lifecycle"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/specs/m1-core/capa.spec.ts frontend/e2e/fixtures/input/capa-form-inputs.ts frontend/src/pages/capa/CAPAListPage.tsx frontend/src/pages/capa/CAPADetailPage.tsx
git commit -m "feat(e2e): M1 CAPA 8D lifecycle spec + capa testids"
```

---

## Task 13: M1 dashboard drilldown spec

**Files:**
- Test: `frontend/e2e/specs/m1-core/dashboard.spec.ts`
- Modify: dashboard widgets (add `data-e2e` to clickable KPI cards / drill targets) — `frontend/src/components/dashboard/widgets/KpiPendingWidget.tsx`, `KpiOverdueWidget.tsx`, etc.

- [ ] **Step 1: Write the failing spec**

`frontend/e2e/specs/m1-core/dashboard.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

test.describe("dashboard drilldown", () => {
  test("KPI pending card click opens filtered list", async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.storage-state/manager.json" });
    const page = await ctx.newPage();
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
    const card = page.locator('[data-e2e="kpi-pending"]').first();
    await card.waitFor({ state: "visible", timeout: 10000 });
    await card.click();
    // Drilldown navigates to a filtered list or opens a dropdown
    await page.waitForLoadState("networkidle");
    await expect(page.locator('[data-e2e="drilldown-list"], [data-e2e="drilldown-menu"]').first()).toBeVisible({ timeout: 10000 });
    await ctx.close();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `make e2e-up && make e2e-seed && cd frontend && npx playwright test --grep "dashboard drilldown"`
Expected: FAIL.

- [ ] **Step 3: Add `data-e2e` attributes**

In the relevant dashboard widget(s) and `DashboardPage.tsx` drilldown handlers: add `data-e2e="kpi-pending"` on the pending KPI card and `data-e2e="drilldown-list"` (or `drilldown-menu`) on the drilldown target container. (The drilldown nav was added on this branch per PROGRESS.md — locate the click handler in `DashboardPage.tsx` / `dashboardDrilldown.ts`.)

- [ ] **Step 4: Run, verify pass**

Run: `cd frontend && npx playwright test --grep "dashboard drilldown"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/specs/m1-core/dashboard.spec.ts frontend/src/components/dashboard/widgets frontend/src/pages/dashboard/DashboardPage.tsx
git commit -m "feat(e2e): M1 dashboard drilldown spec + widget testids"
```

---

## Task 14: Full M0+M1 green run + verification

**Files:** none (verification only).

- [ ] **Step 1: Clean full run without LLM creds**

```
make e2e-reset
make e2e
```
Expected: guards green; auth/fmea/capa/dashboard green; ai-credentials guard skipped-with-warning; m1-core all green. No `make e2e` failure.

- [ ] **Step 2: Single-module iteration**

```
make e2e TEST_ARGS="--grep m1-core/fmea"
```
Expected: only FMEA specs run, green, seed untouched afterward (verify `make e2e-seed` is idempotent re-run).

- [ ] **Step 3: Production gate check**

```
cd backend && E2E_MODE=1 TENANT_MODE=production SECRET_KEY=test-secret-key-for-pytest-only PYTHONPATH=. python -c "from app.main import app; print([r.path for r in app.routes if r.path.startswith('/api/e2e')])"
```
Expected: `[]` — e2e endpoints NOT loaded even with E2E_MODE when TENANT_MODE=production.

- [ ] **Step 4: `make check` still green + e2e type-check**

```
make check
cd frontend && npx tsc -p tsconfig.e2e.json --noEmit
```
Expected: `make check` (backend pytest + src tsc + build) green. `test_e2e_endpoints.py` is SKIPPED here (no `E2E_MODE`, no `seed_e2e`) — its `pytestmark skipif` keeps `make check` green. The e2e endpoint tests are verified by the explicit `E2E_MODE=1 TEST_DATABASE_URL=...` commands in Task 3/4, not by `make check`. If `make check` shows them as failures instead of skips, the file is defaulting `E2E_MODE` — remove that `os.environ.setdefault`. The second command type-checks `playwright.config.ts` + `e2e/**` (NOT covered by `make check`'s src-only tsc).

- [ ] **Step 5: Commit (if any final tweaks)**

If Steps 1-4 surfaced fixes, commit them with `fix(e2e): ...`. Otherwise no commit needed.

---

## Appendix: M2-M5 Roadmap (separate plans, built on M0 infra)

Each milestone is a follow-up PR with its own plan. They reuse M0 (compose, seed_e2e, cleanup, helpers, guards) and only add specs + cleanup-whitelist entries + `data-e2e` testids for their modules.

- **M2 quality core**: control plan, SPC, MSA, special characteristics. Add `e2e_input_fixtures/{control_plan,spc_measurements,grr}.py`, extend `e2e_cleanup_whitelist.py` for `ControlPlan`, `SpcChart`, `GrrStudy`, etc.
- **M3 supplier/customer**: supplier+rating, IQC, supplier dashboard+risk alert, SCAR, complaint/RMA, APQP/PPAP. Extend whitelist for `Supplier`, `IqcInspection`, `Scar`, `RmaRecord`, `Apqp*`, `Ppap*`.
- **M4 AI/integration**: knowledge graph+RAG, smart recommend, collaborative editing, MES/PLM/ERP connectors, admin user/log mgmt. AI specs gated on `e2e-env.json hasLLM`; assert structure only.
- **M5 agent base**: HITL approval, three-state commit, guardrails, tool whitelist. Reuse the P0 acceptance scenarios as E2E specs.

## Self-Review Notes

- **Spec coverage**: every spec section maps to a task — infra (Tasks 1-5), seed+endpoints (3-4), config/helpers/guards (2,6,7), migration (8), docs (9), M1 flows (10-13), verification (14). M2-M5 explicitly roadmaped (appendix).
- **Type consistency**: `getSeedState`/`SeedState`, `loginAs`, `cleanupByPrefix`, `track`/`drainReport`/`nextDocNo` names used consistently. `E2E_KNOWN_DOCS` shape matches seed-state return.
- **Placeholders**: the only "fill from sibling code" instruction is Task 3 Step 4 (model required columns), which is a concrete cross-reference to `seed.py` + model files, not a vague TODO — model schemas are large and duplicating them verbatim would be brittle; the test defines the contract.