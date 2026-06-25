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

OpenQMS is a full-stack quality management platform for manufacturing. Covers FMEA (AIAG-VDA 7-step PFMEA/DFMEA), 8D/CAPA, SPC, MSA, IQC, supplier quality, customer quality, APQP, PPAP, control plans, knowledge graph, and more. UI in Chinese (zh_CN).

**Stack:** Python 3.11+ + FastAPI 0.115 (async) | React 18 + TypeScript 5.6 + Vite 5.4 + Ant Design 5.29 | PostgreSQL 15 + SQLAlchemy 2.0 (async) | Redis 7 (configured, no logic yet)

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
pytest tests/ -x --tb=short               # Run tests
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
models/       → SQLAlchemy 2.0 ORM (UUID PKs, DeclarativeBase, 50+ tables)
schemas/      → Pydantic v2 request/response schemas
core/         → security.py, deps.py (RequestScope + FastAPI Depends guards), factory_scope.py
state_machines/ → FMEAState / EightDState enums + transition tables
graph/        → FMEA graph repository + recommendation pipeline
```

- PKs are UUID v4 generated in Python. FMEA uses a **graph model** in JSONB (`graph_data`): `{nodes: [...], edges: [...]}`. Frontend flattens it to spreadsheet rows.
- CAPA 8D steps are individual text columns (`d1_team`–`d8_closure`), with `d1_team` also JSONB for team member structs.
- Dashboard service uses raw SQL (`text()`) with `jsonb_array_elements()` for RPN aggregation.
- Services raise `ValueError`; API layer converts to `HTTPException`.
- List endpoints return `{ items, total, page, page_size }` — unified as `PaginatedResponse<T>` on frontend.

### Auth & Permissions

7-role RBAC with permission matrix (25 modules × 5 levels). Multi-tenant with factory isolation.

| Role | Level | Capabilities |
|------|:-----:|-------------|
| admin | L5 | Everything (all modules, all factories) |
| manager | L3-L4 | CRUD all + approve FMEA / close CAPA (D7/D8) |
| quality_engineer | L2 | CRUD FMEA/CAPA, non-approval transitions |
| viewer | L1 | Read-only |
| + group_admin, supplier_manager, customer_manager | varies | Module-specific access |

- JWT: HS256, 120 min expiry, `sub`=user_id. Frontend validates expiry in `ProtectedRoute`.
- Backend: `RequestScope` dependency in `core/deps.py` resolves factory + product line scope per request. `check_factory_access()` from `core/factory_scope.py` enforces row-level security.
- `ProtectedRoute` on frontend validates token + optional `requiredModule` permission.
- Full reference: `docs/permissions.md`

### Frontend (`frontend/src/`)

```
pages/           → One file per route, local useState for all page data
components/      → layout/ (AppLayout: sidebar+header+Outlet), shared/ (KPICard)
store/           → Zustand — auth + product line + factory state
api/             → Axios instance + per-module functions
hooks/           → usePermission (useCallback-stabilized), useProductLineStore
utils/           → fmea.ts (AP lookup), fmeaTable.ts (graph↔rows)
types/           → All TS interfaces in single index.ts, PaginatedResponse<T> generic
```

- Routes: All protected via `<ProtectedRoute requiredModule="...">`. Menu items filtered by permissions.
- Vite proxies `/api` → backend (`localhost:8000` or `BACKEND_URL` in Docker)
- Axios interceptor injects Bearer token; 401 clears token → `/login`
- FMEA editor is a custom 20+ column spreadsheet on Ant `Input`+`Select` (no third-party grid)
- No form library beyond raw Ant Form.

### Database

PostgreSQL 15 (asyncpg), 50+ tables across 7 modules. Multi-tenant with factory isolation (`factory_id` NOT NULL on all business tables). Alembic migrations are hand-written.

**Key tables:** `users`, `role_definitions`, `user_roles`, `permissions`, `factories`, `product_lines`, `fmea_documents`, `capa_eightd`, `suppliers`, `spc_charts`, `iqc_materials`, `control_plans`, `audit_programs`, `audit_findings`, `customer_complaints`, `rma_records`, `scar_records`, plus 30+ more.

## Key Conventions

- Chinese UI, mixed Chinese/English comments
- Document numbering: `PFMEA-2026-001`, `DFMEA-2026-001`, `8D-2026-001`
- Product line: `DC-DC-100` (seed data default)
- Severity labels: `致命`, `严重`, `一般`, `轻微`
- Every CRUD operation manually creates an `AuditLog` in its service method
- FMEA graph nodes carry AIAG-VDA 7-step properties
- `frontend/src/utils/fmea.ts` has the AIAG-VDA Action Priority lookup table (H/M/L from S×O×D)
- `factory_id` is NOT NULL on all business tables. Users may have NULL `factory_id` (group admins).
- `RequestScope` in `core/deps.py` resolves factory + product line scope per request. Use `check_factory_access(entity_id, scope)` for row-level security.
- Use `enqueue_embedding()` BEFORE `await db.commit()` to prevent outbox row loss.

## Working with the FMEA Graph

The JSONB graph is the most complex part of the system:

- **DFMEA chain:** System → Subsystem → Component → Function → FailureMode → FailureEffect/Cause → Controls
- **PFMEA chain:** ProcessItem → ProcessStep → WorkElement → Function → FailureMode → FailureEffect/Cause → Controls
- **Edge types:** `HAS_PROCESS_STEP`, `FUNCTION_MAPPED_TO`, `HAS_FAILURE_MODE`, `EFFECT_OF`, `CAUSE_OF`, `PREVENTED_BY`, `DETECTED_BY`, `OPTIMIZED_BY`
- `fmeaTable.ts` handles graph↔spreadsheet bidirectional conversion
- Reference examples: `SAMPLE_PFMEA_GRAPH` / `SAMPLE_DFMEA_GRAPH` in `seed.py`
- **Row deletion**: Only deletes shared control/action nodes if no other row references them
- **Multi-Effect**: Each FailureMode can have multiple Effects; rows fan out per (cause × effect) pair

## Known Gaps

- Test suite expanding (backend pytest with factory_id fixtures + frontend vitest); some legacy modules still need fixture backfill
- No rate limiting on login
- Redis configured but no caching logic implemented
- Frontend bundle is 5.5MB — needs code splitting
- Some Alembic migration numbers overlap; needs normalization