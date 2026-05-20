# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Behavioral Guidelines

**Tradeoff:** bias toward caution and simplicity. For trivial fixes, use judgment and move fast.

### 1. Think Before Coding

Before implementing, state assumptions explicitly. If multiple interpretations exist, present them — don't pick silently. If a simpler approach exists, say so. If something is unclear, name what's confusing and ask.

### 2. Simplicity First

Minimum code that solves the problem. No features beyond what was asked, no abstractions for single-use code, no "flexibility" that wasn't requested, no error handling for impossible states. If 200 lines could be 50, rewrite. Test: "Would a senior engineer say this is overcomplicated?"

### 3. Surgical Changes

Touch only what must change. Don't improve adjacent code, comments, or formatting. Don't refactor things that aren't broken. Match existing style, even if you'd do it differently. Remove imports/variables/functions that your changes made unused, but leave pre-existing dead code alone unless asked. Every changed line must trace to the user's request.

### 4. Verify Before Claiming Success

Run the relevant command (build, lint, test, or start the app) before declaring work done. "It should work" is not verification. If you can't verify, say so explicitly rather than claiming completion.

---

## Project Overview

OpenQMS is a full-stack quality management platform targeting Chinese manufacturing. Covers FMEA (AIAG-VDA 7-step PFMEA/DFMEA), 8D/CAPA, and dashboard. UI in Chinese (zh_CN).

**Stack:** Python 3.11 + FastAPI 0.115 (async) | React 18 + TypeScript 5.6 + Vite 5.4 + Ant Design 5.21 | PostgreSQL 15 + SQLAlchemy 2.0 (async) | Redis 7 (configured, no logic yet)

## Commands

### Docker (recommended)

```bash
docker compose up                         # Start all services
docker compose exec backend alembic upgrade head  # Run DB migrations
docker compose exec backend python -m app.seed    # Seed demo data
```

### Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head && python -m app.seed  # Fresh DB setup
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
python app/test_schema.py                 # Only tests (manual, no pytest)
```

### Frontend

```bash
cd frontend
npm install && npm run dev                # Vite on :5173, proxies /api → :8000
npm run build                             # tsc --noEmit + vite build
npm run lint                              # ESLint
```

### Seed accounts

| Username | Password | Role |
|----------|----------|------|
| admin | Admin@2026 | admin |
| engineer | Engineer@2026 | quality_engineer |
| manager | Manager@2026 | manager |
| viewer | Viewer@2026 | viewer |

## Architecture

### Backend (`backend/app/`)

```
api/          → Route handlers (thin): parse, call service, return response
services/     → Business logic + manual AuditLog on every CRUD
models/       → SQLAlchemy 2.0 ORM (UUID PKs, DeclarativeBase)
schemas/      → Pydantic v2 request/response schemas
core/         → security.py (bcrypt + JWT/HS256), deps.py (FastAPI Depends guards)
state_machines/ → FMEAState / EightDState enums + transition tables
```

- PKs are UUID v4 generated in Python. FMEA uses a **graph model** in a single JSONB column (`graph_data`): `{nodes: [...], edges: [...]}`. Frontend flattens it to spreadsheet rows.
- CAPA 8D steps are individual text columns (`d1_team`–`d8_closure`), with `d1_team` also JSONB for team member structs.
- Dashboard service uses raw SQL (`text()`) with `jsonb_array_elements()` for RPN aggregation.
- Services raise `ValueError`; API layer converts to `HTTPException`.
- List endpoints return `{ items, total, page, page_size }` — no shared pagination helper.

### Auth & Permissions

4-role RBAC, single `users.role` VARCHAR column, no permissions table:

| Role | Level | Capabilities |
|------|:-----:|-------------|
| admin | L4 | Everything |
| manager | L3 | CRUD all + approve FMEA / close CAPA (D7/D8) |
| quality_engineer | L2 | CRUD FMEA/CAPA, non-approval transitions |
| viewer | L1 | Read-only |

- JWT: HS256, 120 min expiry, `sub`=user_id. No refresh mechanism.
- Backend: 4 guards in `core/deps.py` — `get_current_user`, `require_admin`, `require_engineer_or_admin`, `require_manager_or_admin` (the last is defined but **unused** — FMEA/CAPA do manager-level checks inline).
- FMEA approval and CAPA D7/D8 advancement have additional inline `user.role in ["admin", "manager"]` checks beyond route-level deps.
- Frontend `ProtectedRoute` checks token existence only (not role). Pages use `isViewer`/`isAdminOrManager` booleans to disable inputs and hide buttons.
- Full reference: `docs/permissions.md`

### Frontend (`frontend/src/`)

```
pages/           → One file per route, local useState for all page data
components/      → layout/ (AppLayout: sidebar+header+Outlet), shared/ (KPICard)
store/           → Zustand — auth state only
api/             → Axios instance + per-module functions (auth, fmea, capa, dashboard)
utils/           → fmea.ts (AIAG-VDA AP lookup), fmeaTable.ts (graph↔rows conversion)
types/           → All TS interfaces in single index.ts
```

- Routes: `/login` (public), `/dashboard`, `/fmea`, `/fmea/:id`, `/capa`, `/capa/:id` (protected)
- Vite proxies `/api` → backend (`localhost:8000` or `BACKEND_URL` in Docker)
- Axios interceptor injects Bearer token; 401 clears token → `/login`
- FMEA editor is a custom 20+ column spreadsheet on Ant `Input`+`Select` (no third-party grid)
- No form library beyond raw Ant Form. No test framework on frontend.

### Database

PostgreSQL 15 (asyncpg), 4 tables: `users`, `fmea_documents`, `capa_eightd`, `audit_logs`. Alembic migrations are hand-written (2 files), not autogenerated.

## Key Conventions

- Chinese UI, mixed Chinese/English comments
- Document numbering: `PFMEA-2026-001`, `DFMEA-2026-001`, `8D-2026-001`
- Product line: `DC-DC-100` (hardcoded in models)
- Severity labels: `致命`, `严重`, `一般`, `轻微`
- Every CRUD operation manually creates an `AuditLog` in its service method
- FMEA graph nodes carry AIAG-VDA 7-step properties (Step 2 structure → Step 3 function → Steps 4-5 risk S/O/D → Step 6 optimization + revised S/O/D)
- `frontend/src/utils/fmea.ts` has the AIAG-VDA Action Priority lookup table (H/M/L from S×O×D)

## Working with the FMEA Graph

The JSONB graph is the most complex part of the system:

- **DFMEA chain:** System → Subsystem → Component → Function → FailureMode → FailureEffect/Cause → Controls
- **PFMEA chain:** ProcessItem → ProcessStep → WorkElement → Function → FailureMode → FailureEffect/Cause → Controls
- **Edge types:** `HAS_PROCESS_STEP`, `FUNCTION_MAPPED_TO`, `HAS_FAILURE_MODE`, `EFFECT_OF`, `CAUSE_OF`, `PREVENTED_BY`, `DETECTED_BY`, `OPTIMIZED_BY`
- `fmeaTable.ts` handles graph↔spreadsheet bidirectional conversion
- Reference examples: `SAMPLE_PFMEA_GRAPH` / `SAMPLE_DFMEA_GRAPH` in `seed.py`

## Known Gaps

- No test framework (no pytest, no Vitest). Single manual `test_schema.py`.
- No token refresh — 120 min hard expiry logs users out.
- No rate limiting on login. No auth audit logging.
- Redis configured but no caching logic implemented.
- `require_manager_or_admin` dependency exists but unused (inline checks instead).
- Frontend list pages show Create buttons to all roles; backend rejects viewers with 403.
- Docker targets Python 3.11; local dev verified on 3.12 only.
