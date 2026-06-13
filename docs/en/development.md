# Development Guide

This document is for OpenQMS developers and covers project conventions, development workflows, and how to add new modules.

---

## 1. Backend Development Conventions

### 1.1 Code Structure

```
backend/app/
├── api/           # Route handlers (thin layer)
├── services/      # Business logic layer
├── models/        # SQLAlchemy ORM models
├── schemas/       # Pydantic v2 request/response schemas
├── core/          # Security, dependency injection, permissions, factory scope
├── state_machines/ # State machines (FMEAState, EightDState, etc.)
├── main.py        # FastAPI entry point
└── seed.py        # Seed data script
```

### 1.2 Request Processing Pattern

```
API layer (api/*.py)
  ├── Parse request parameters
  ├── Call Service layer
  ├── Catch ValueError → HTTPException
  └── Return response

Service layer (services/*.py)
  ├── Business logic
  ├── Database operations
  ├── Manual AuditLog writes
  └── Raise ValueError (converted by API layer)
```

**Key conventions**:
- The API layer contains no business logic.
- The Service layer manually writes `AuditLog`; no automatic auditing is used.
- List endpoints uniformly return `{ items, total, page, page_size }`.
- Errors are thrown via `raise ValueError("error message")` and converted uniformly by the API layer.

### 1.3 Permission Checks

```python
# API layer: use the require_permission decorator
from app.core.permissions import require_permission, Module, PermissionLevel

@router.get("/", dependencies=[Depends(require_permission(Module.FMEA, PermissionLevel.VIEW))])
async def list_fmea(...):
    ...
```

### 1.4 Database Migrations

Migration files are **hand-written**; auto-generation is not used:

```bash
# Create a new migration file
alembic revision -m "add_new_table"

# Apply migrations
alembic upgrade head

# Roll back one version
alembic downgrade -1
```

---

## 2. Frontend Development Conventions

### 2.1 Code Structure

```
frontend/src/
├── api/           # Axios instance + per-module API functions
├── components/    # Layout components (AppLayout) + shared components
├── hooks/
│   └── usePermission.ts  # Permission hook
├── pages/         # Page components organized by module
├── store/
│   └── authStore.ts      # Zustand auth state
├── types/
│   └── index.ts           # Global TypeScript interfaces
├── utils/
│   ├── fmea.ts             # AIAG-VDA AP lookup table
│   └── fmeaTable.ts        # graph↔spreadsheet conversion
└── App.tsx        # Route definitions + ProtectedRoute
```

### 2.2 Route Registration

New modules need a route added in `App.tsx` with a `ProtectedRoute` module guard:

```tsx
<Route path="/my-module" element={<ProtectedRoute requiredModule="my_module"><MyModulePage /></ProtectedRoute>} />
```

### 2.3 Permission Hook

Use `usePermission` in page components to control button and form visibility:

```tsx
const { canView, canCreate, canEdit, canApprove } = usePermission();

// Hide the create button
{canCreate("fmea") && <Button onClick={handleCreate}>Create FMEA</Button>}

// Disable input
<Input disabled={!canEdit("fmea")} />
```

### 2.4 API Client

Each module creates a separate file in the `api/` directory:

```typescript
// api/myModule.ts
import client from './client';

export const listMyModule = (params: any) => client.get('/api/my-module', { params });
export const getMyModule = (id: string) => client.get(`/api/my-module/${id}`);
export const createMyModule = (data: any) => client.post('/api/my-module', data);
```

### 2.5 Build and Checks

```bash
cd frontend
npm run build    # TypeScript type check + Vite build
npm run lint     # ESLint check
npm run dev      # Dev server (:5173, proxies /api → :8000)
```

---

## 3. Adding a New Module

### 3.1 Backend Steps

1. **Create model**: Create `my_module.py` under `models/`, inheriting from `Base`.
2. **Register model**: Import and add to `__all__` in `models/__init__.py`.
3. **Create schema**: Create `my_module.py` under `schemas/`, defining request/response schemas.
4. **Create service**: Create `my_module_service.py` under `services/`, implementing CRUD + AuditLog.
5. **Create API**: Create `my_module.py` under `api/`, defining routes.
6. **Register routes**: Include the router in `main.py`.
7. **Add permission module**: Add `MY_MODULE = "my_module"` to the `Module` enum in `core/permissions.py`.
8. **Create migration**: Run `alembic revision -m "add_my_module_tables"`, write the table creation SQL.
9. **Add permission data**: In the migration, assign `my_module` permission levels for each role.
10. **Frontend sync**: Add `"my_module"` to the `ModuleKey` type in `usePermission.ts`.

### 3.2 Frontend Steps

1. **Add types**: Define interfaces in `types/index.ts`.
2. **Add API**: Create a module API file under `api/`.
3. **Create page**: Create `myModule/MyModulePage.tsx` under `pages/`.
4. **Register route**: Add route + `ProtectedRoute` in `App.tsx`.
5. **Add menu**: Add a sidebar menu item in `components/layout/`.

---

## 4. Testing

### 4.1 Backend

The project currently uses the manual test script `backend/app/test_schema.py`. There is no pytest framework.

```bash
cd backend
python app/test_schema.py
```

### 4.2 Frontend

The frontend currently has no test framework. It is recommended to introduce Vitest + React Testing Library in the future.

---

## 5. Commit Convention

```
<type>(<scope>): <subject>

<body>
```

Types: `feat` / `fix` / `docs` / `refactor` / `test` / `chore`

Examples:
```
feat(fmea): add DFMEA generation rules engine
fix(capa): fix D7/D8 transition permission check
docs(permissions): update permission matrix for new modules
```