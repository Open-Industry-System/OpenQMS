# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenQMS is a full-stack quality management platform targeting Chinese manufacturing. It covers FMEA (AIAG-VDA 7-step PFMEA/DFMEA), 8D/CAPA, and a dashboard. The UI is in Chinese (zh_CN).

**Stack:** Python 3.11 + FastAPI 0.115 (async) | React 18 + TypeScript 5.6 + Vite 5.4 + Ant Design 5.21 | PostgreSQL 15 + SQLAlchemy 2.0 (async) | Redis 7 (configured but not yet used)

## Commands

### Docker (recommended)

```bash
docker compose up                         # Start all services (db, redis, backend, frontend)
docker compose exec backend alembic upgrade head  # Run DB migrations
docker compose exec backend python -m app.seed    # Seed demo data (users + sample FMEA/CAPA)
```

### Backend (standalone)

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head                     # Run migrations
python -m app.seed                        # Seed demo data
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
python app/test_schema.py                 # Run schema validation tests (no pytest)
```

### Frontend (standalone)

```bash
cd frontend
npm install
npm run dev                               # Vite dev server on :5173, proxies /api to backend
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

Layered FastAPI app with explicit service classes (not Fat Model pattern):

```
api/          → Route handlers, thin — parse requests, call services, return responses
services/     → Business logic + manual audit logging on every CRUD operation
models/       → SQLAlchemy 2.0 ORM models (UUID PKs, DeclarativeBase)
schemas/      → Pydantic v2 request/response schemas
core/         → security.py (bcrypt + JWT/HS256), deps.py (FastAPI Depends guards)
state_machines/ → FMEA and 8D state enums + transition tables
```

- All PKs are UUID v4 (generated in Python, not DB)
- FMEA data uses a **graph model** stored as a single JSONB column (`graph_data`): `{nodes: [...], edges: [...]}`. The frontend flattens this into spreadsheet rows for editing.
- CAPA 8D steps are individual text columns (`d1_team` through `d8_closure`), with `d1_team` also stored as JSONB for structured team member data.
- Dashboard service uses raw SQL (`text()`) with `jsonb_array_elements()` for RPN aggregation from the graph JSONB.
- Error handling: services raise `ValueError`, API layer catches and converts to `HTTPException`.
- List endpoints return `{ items: [...], total, page, page_size }` — no shared pagination helper.

### Auth & Permissions

4-role RBAC with a single `users.role` VARCHAR column (no permissions table):

| Role | Level | Capabilities |
|------|:-----:|-------------|
| admin | L4 | Everything |
| manager | L3 | CRUD all + approve FMEA / close CAPA (D7/D8) |
| quality_engineer | L2 | CRUD FMEA/CAPA, non-approval transitions |
| viewer | L1 | Read-only |

- JWT tokens: HS256, 120 min expiry, `sub` = user_id, no refresh mechanism
- Backend enforces via FastAPI `Depends()` — four guards in `core/deps.py`: `get_current_user`, `require_admin`, `require_engineer_or_admin`, `require_manager_or_admin`
- FMEA approval and CAPA D7/D8 advancement have **additional inline role checks** beyond the route-level dependency
- `require_manager_or_admin` is defined but unused — both modules duplicate the check inline
- Frontend `ProtectedRoute` only checks token existence, not role — viewers can navigate to any URL
- Frontend pages use `isViewer` / `isAdminOrManager` booleans from `useAuthStore` to disable inputs and hide buttons
- Full audit: `docs/permissions.md`

### Frontend (`frontend/src/`)

```
pages/           → One file per route, each manages its own state with useState
components/      → layout/ (AppLayout with sidebar+header+Outlet), shared/ (KPICard)
store/           → Zustand, auth state only (user, token, login, logout, fetchUser)
api/             → Axios instance + per-module API functions (auth, fmea, capa, dashboard)
utils/           → fmea.ts (AIAG-VDA AP lookup table), fmeaTable.ts (graph↔spreadsheet conversion)
types/           → All TypeScript interfaces in a single index.ts
```

- Routing: `/login` (public), `/dashboard`, `/fmea`, `/fmea/:id`, `/capa`, `/capa/:id` (protected)
- Vite proxies `/api` to backend (`localhost:8000` or `BACKEND_URL` env var in Docker)
- Axios interceptor injects Bearer token from localStorage; 401 clears token and redirects to `/login`
- No component library beyond Ant Design; no form library (raw Ant Form)
- FMEA editor is a custom spreadsheet (20+ columns) built on Ant `Input` + `Select` — not a third-party grid

### Database

PostgreSQL 15 with asyncpg. Four tables: `users`, `fmea_documents`, `capa_eightd`, `audit_logs`. Alembic migrations are hand-written (not autogenerated). Two migration files exist.

## Key Conventions

- Chinese UI labels, mixed Chinese/English in code comments
- Document numbering: `PFMEA-2026-001`, `DFMEA-2026-001`, `8D-2026-001`
- Product line defaults to `DC-DC-100` (hardcoded in models)
- Severity labels: `致命`, `严重`, `一般`, `轻微`
- **Every CRUD operation** manually creates an `AuditLog` record in its service method
- FMEA graph nodes carry AIAG-VDA 7-step properties: Step 2 (structure), Step 3 (function), Steps 4-5 (risk: S/O/D), Step 6 (optimization: actions, revised S/O/D)
- `frontend/src/utils/fmea.ts` contains the AIAG-VDA Action Priority lookup table (H/M/L from S×O×D combinations)

## Working with the FMEA Graph

The FMEA graph node/edge JSONB structure is the most complex part of the system. Key points:

- **DFMEA node chain:** System → Subsystem → Component → Function → FailureMode → FailureEffect / FailureCause → Controls
- **PFMEA node chain:** ProcessItem → ProcessStep → ProcessWorkElement → Function → FailureMode → FailureEffect / FailureCause → Controls
- Edge types express relationships: `HAS_PROCESS_STEP`, `FUNCTION_MAPPED_TO`, `HAS_FAILURE_MODE`, `EFFECT_OF`, `CAUSE_OF`, `PREVENTED_BY`, `DETECTED_BY`, `OPTIMIZED_BY`
- `frontend/src/utils/fmeaTable.ts` handles the bidirectional conversion between graph data and spreadsheet rows
- Seed data in `backend/app/seed.py` contains `SAMPLE_PFMEA_GRAPH` and `SAMPLE_DFMEA_GRAPH` — those are the reference examples for what valid graph data looks like

## Known Gaps

- No test framework (no pytest, no Vitest). Only a manual `test_schema.py`.
- No token refresh — 120 min hard expiry logs users out
- No rate limiting on login
- Redis configured in settings but no caching logic is implemented
- `require_manager_or_admin` dependency exists but is unused (inline checks instead)
- Frontend list pages show Create buttons to all roles; backend rejects viewers with 403
- Python 3.11 is the Docker target; local development has been verified on 3.12 only
