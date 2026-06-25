# Architecture Overview

This document describes the OpenQMS system architecture, permission model, data flow, and development conventions.

---

## 1. Technology Stack

| Layer | Technology | Description |
|-------|------------|-------------|
| Backend | Python 3.11 / FastAPI 0.115 | Async framework, auto-generated OpenAPI docs |
| ORM | SQLAlchemy 2.0 (async) | UUID v4 primary keys, async sessions |
| Database | PostgreSQL 15 | JSONB graph model storage, GIN index |
| Cache | Redis 7 | Configured, caching logic not yet implemented |
| Knowledge Graph | Neo4j 5 Community | FMEA/CP association visualization and intelligent recommendations |
| AI | Ollama | Local LLM inference for recommendation engine |
| Frontend | React 18 / TypeScript 5.6 | Single-page application |
| Build | Vite 5.4 | Dev server + proxy |
| UI Framework | Ant Design 5.21 | Chinese localization |
| State Management | Zustand | Auth state only |
| Migrations | Alembic | Hand-written migration files |
| Containers | Docker Compose | 6-service orchestration |

---

## 2. Directory Structure

```
OpenQMS/
├── backend/
│   ├── app/
│   │   ├── api/            # Route handlers (thin layer): parse request, call service, return response
│   │   ├── services/       # Business logic layer: all CRUD + AuditLog manual writes
│   │   ├── models/         # SQLAlchemy 2.0 ORM models (UUID PK, DeclarativeBase)
│   │   ├── schemas/         # Pydantic v2 request/response schemas
│   │   ├── core/
│   │   │   ├── security.py  # bcrypt password hashing + JWT/HS256 signing/verification
│   │   │   ├── deps.py      # FastAPI dependency injection (get_current_user, etc.)
│   │   │   ├── permissions.py # Module/PermissionLevel enums + require_permission decorator
│   │   │   └── factory_scope.py # Factory/product line scope filtering
│   │   ├── main.py          # FastAPI app entry, route registration, middleware
│   │   └── seed.py          # Demo data seed script
│   ├── alembic/             # Database migrations
│   └── tests/               # pytest backend tests (factory_id fixtures + multi-module regression)
├── frontend/
│   ├── src/
│   │   ├── api/             # Axios instance + per-module API functions
│   │   ├── components/      # Layout components (AppLayout) + shared components (KPICard)
│   │   ├── hooks/
│   │   │   └── usePermission.ts # Permission hook (ModuleKey × PermissionLevel)
│   │   ├── pages/           # Page components organized by module
│   │   ├── store/
│   │   │   └── authStore.ts  # Zustand auth state (token, user, permissions)
│   │   ├── types/
│   │   │   └── index.ts     # Global TypeScript interfaces
│   │   ├── utils/
│   │   │   ├── fmea.ts      # AIAG-VDA AP lookup table
│   │   │   └── fmeaTable.ts  # graph↔spreadsheet bidirectional conversion
│   │   └── App.tsx          # Route definitions + ProtectedRoute guard
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── docs/
    ├── deployment.md
    ├── architecture.md         # This document
    ├── permissions.md
    ├── user-guide.md
    ├── admin-guide.md
    ├── development.md
    └── modules/
        └── *.md                 # Module manuals by functional domain
```

---

## 3. Request Processing Flow

```
Browser → Vite Dev Server (:5173)
          ↓ /api/* proxy
        Nginx / Vite Proxy
          ↓
FastAPI (:8000)
  ├── CORS middleware
  ├── JWT authentication (get_current_user)
  ├── Permission check (require_permission)
  ├── API routes (api/*.py)
  │     ↓
  ├── Service layer (services/*.py)
  │     ├── Business logic
  │     ├── AuditLog writes
  │     └── ValueError → HTTPException
  └── SQLAlchemy AsyncSession
        ↓
      PostgreSQL
```

**Key conventions**:
- The API layer only handles request parsing and response formatting; it contains no business logic.
- The Service layer handles all business logic and manually writes `AuditLog`.
- The Service layer raises `ValueError`; the API layer converts it to `HTTPException`.
- List endpoints uniformly return `{ items, total, page, page_size }`.

---

## 4. Permission Model

### 4.1 Model Structure

OpenQMS uses a **role + module permission level + factory/product line scope** three-tier permission model:

```
User → Role (role_key)
      → Role permissions (role_permissions: module × permission_level)
      → Factory scope (user_factories)
      → Product line scope (user_product_lines)
```

### 4.2 PermissionLevel

| Level | Constant | Description |
|:-----:|----------|-------------|
| 0 | NONE | No permission, access denied |
| 1 | VIEW | Read-only |
| 2 | CREATE | Can create |
| 3 | EDIT | Can edit |
| 4 | APPROVE | Can approve |
| 5 | ADMIN | Full control |

### 4.3 Frontend Permission Hook

```typescript
// frontend/src/hooks/usePermission.ts
const { canView, canCreate, canEdit, canApprove, canAdmin, isAdmin, roleKey } = usePermission();

// Check by module
canView("fmea")      // PermissionLevel >= 1
canCreate("fmea")    // PermissionLevel >= 2
canEdit("fmea")      // PermissionLevel >= 3
canApprove("fmea")   // PermissionLevel >= 4
canAdmin("fmea")     // PermissionLevel >= 5
```

### 4.4 Backend Permission Decorator

```python
# backend/app/core/permissions.py
@router.post("/", dependencies=[Depends(require_permission(Module.FMEA, PermissionLevel.CREATE))])
async def create_fmea(...):
    ...
```

### 4.5 Full Permission Matrix

See [Permissions Reference](permissions.md).

---

## 5. Data Model Overview

### 5.1 Core Tables

| Table | Description | Primary Key |
|-------|-------------|-------------|
| `users` | Users | UUID |
| `role_definitions` | Role definitions (7 preset roles) | UUID |
| `role_permissions` | Role × module × permission level | UUID |
| `user_factories` | User-factory scope | UUID |
| `user_product_lines` | User-product line scope | UUID |
| `factories` | Factories | UUID |
| `product_lines` | Product lines | UUID |
| `product_types` | Product type master data (shared across factories, referenced by product_lines) | String (code) |
| `fmea_documents` | FMEA documents (JSONB graph_data) | UUID |
| `capa_eightd` | 8D/CAPA reports | UUID |
| `audit_logs` | Audit logs | UUID |

### 5.2 FMEA Graph Model

FMEA uses a JSONB column `graph_data` to store graph structure:

```
{
  "nodes": [
    {"id": "ps_1", "type": "ProcessStep", "name": "...", "severity": 0, "occurrence": 0, "detection": 0},
    {"id": "fm_1", "type": "FailureMode", "name": "...", "severity": 0, "occurrence": 0, "detection": 0},
    ...
  ],
  "edges": [
    {"source": "ps_1", "target": "fm_1", "type": "HAS_FAILURE_MODE"},
    ...
  ]
}
```

The frontend `fmeaTable.ts` handles bidirectional conversion between graph structure and spreadsheet rows.

---

## 6. Inter-Module Data Flow

```
FMEA ──→ Special Characteristics (SC/CC) ──→ Control Plan (CP)
  │                                            │
  │                                            ↓
  └──→ 8D/CAPA ←── SCAR ←── IQC Incoming Inspection
        │    ↑         ↑
        │    │         │
        └→ SPC Control Charts   Supplier Management
             │                      │
             └──→ MSA ←────────────┘

Customer Complaint/RMA → SCAR → Supplier
  │                           │
  └→ FMEA ←───────────────────┘

Management Review ← Quality Objectives ← KPI Data
  ↑
  ├── CAPA Status Summary
  ├── SPC Process Capability
  └── Customer/Supplier Metrics

ERP/MES/PLM ──→ Dashboard Data Sync
Knowledge Graph ← FMEA/CP Association Data
Group Management ← Multi-Factory Aggregation
```

---

## 7. API Documentation

FastAPI auto-generates interactive API documentation:

| Documentation Type | URL | Description |
|-------------------|-----|-------------|
| Swagger UI | `http://localhost:8000/docs` | Interactive API testing interface |
| ReDoc | `http://localhost:8000/redoc` | More readable API reference |

All API endpoint paths start with `/api/`. Authentication uses Bearer Token (JWT).

---

## 8. Known Limitations

| Limitation | Description |
|------------|-------------|
| No test framework | ~~Backend uses manual `test_schema.py`; frontend has no tests~~ Backend migrated to pytest (factory_id fixtures, multi-module regression, API guard tests); frontend covered by vitest for key utils/pages; some legacy modules still need fixture backfill |
| Frontend does not auto-refresh tokens | Backend has `/api/auth/refresh`, but the frontend does not call it automatically; users must re-login after 120 minutes |
| No login rate limiting | Login endpoint has no rate limiting |
| Redis not used | Configured but caching logic is not implemented |
| Incomplete frontend route guards | `/knowledge-graph`, `/change-impact`, and MES routes lack `requiredModule` guards |