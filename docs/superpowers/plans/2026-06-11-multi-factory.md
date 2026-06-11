# 多工厂部署支持 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement multi-factory data isolation with group-level aggregation, using application-layer `factory_id` row-level filtering with a three-layer scope model (FactoryScope / ProductLineScope / PermissionScope).

**Architecture:** Single shared database. New `Factory` model as top-level org unit. `factory_id` column on ~50 business tables. Unified scope filter layer (`core/factory_scope.py`) replaces per-module ad-hoc filtering. `Module.GROUP` permission controls cross-factory access, independent from `bypass_row_level_security`.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL 15 + Alembic + React 18 + TypeScript + Ant Design 5

**Spec:** `docs/superpowers/specs/2026-06-11-multi-factory-design.md`

---

## File Structure

### New Files
- `backend/app/models/factory.py` — Factory + UserFactory ORM models
- `backend/app/models/supplier_shared_profile.py` — SupplierSharedProfile ORM model
- `backend/app/models/group_kpi_snapshot.py` — GroupKPISnapshot ORM model
- `backend/app/schemas/factory.py` — Factory Pydantic schemas
- `backend/app/schemas/group.py` — Group API response schemas
- `backend/app/services/factory_service.py` — Factory CRUD service
- `backend/app/services/group_service.py` — Group dashboard/comparison service
- `backend/app/core/factory_scope.py` — FactoryScope, ProductLineScope, resolve_*, apply_scope_filter, populate_factory_id, validate_factory_invariant
- `backend/app/api/group.py` — Group route endpoints (including factory CRUD under /api/group/factories)
- `backend/alembic/versions/035_add_factory_tables.py` — Alembic migration
- `frontend/src/api/group.ts` — Group + Factory API client (combined)
- `frontend/src/pages/group/GroupDashboard.tsx` — Group dashboard page
- `frontend/src/pages/group/FactoryManagement.tsx` — Factory CRUD page
- `frontend/src/pages/group/FactoryComparison.tsx` — Factory comparison page
- `frontend/src/pages/group/GroupSuppliers.tsx` — Shared suppliers page
- `frontend/src/pages/group/GroupAudits.tsx` — Cross-factory audits page

### Modified Files
- `backend/app/models/__init__.py` — Import new models
- `backend/app/models/product_line.py` — Add `factory_id` column
- `backend/app/models/user.py` — Add `factory_id` column
- `backend/app/models/supplier.py` — Add `factory_id`, `shared_profile_id`, change unique constraint
- `backend/app/models/audit_program.py` — Add `factory_id` to AuditProgram, AuditChecklistTemplate
- `backend/app/core/permissions.py` — Add `Module.GROUP`
- `backend/app/core/deps.py` — Add `RequestScope` dataclass, `get_request_scope` dependency
- `backend/app/api/auth.py` — Return FactoryScope + permissions.group in /auth/me
- `backend/app/services/erp_ingestion.py` — Use connection.factory_id for background sync
- `backend/app/services/mes_ingestion.py` — Use connection.factory_id for background sync
- `frontend/src/types/index.ts` — Add Factory, FactoryScope, GroupDashboard types
- `frontend/src/store/authStore.ts` — Store factory scope from /auth/me
- `frontend/src/components/layout/AppLayout.tsx` — Factory switcher in header, group menu items
- `frontend/src/api/client.ts` — Axios interceptor for factory_id auto-injection

---

## Phase 1: Foundation (Models + Migration + Scope Layer)

### Task 1: Factory + UserFactory Models

**Files:**
- Create: `backend/app/models/factory.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write Factory and UserFactory models**

```python
# backend/app/models/factory.py
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Factory(Base):
    __tablename__ = "factories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class UserFactory(Base):
    __tablename__ = "user_factories"
    __table_args__ = (
        UniqueConstraint("user_id", "factory_id", name="uq_user_factory"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="CASCADE"), nullable=False)
```

- [ ] **Step 2: Add imports to `backend/app/models/__init__.py`**

Add `Factory`, `UserFactory` to the imports and `__all__` list.

- [ ] **Step 3: Verify models import correctly**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.models import Factory, UserFactory; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/factory.py backend/app/models/__init__.py
git commit -m "feat(multi-factory): add Factory and UserFactory models"
```

---

### Task 2: GroupKPISnapshot Model

**Files:**
- Create: `backend/app/models/group_kpi_snapshot.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write GroupKPISnapshot model**

```python
# backend/app/models/group_kpi_snapshot.py
import uuid
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class GroupKPISnapshot(Base):
    __tablename__ = "group_kpi_snapshots"
    __table_args__ = (
        UniqueConstraint("factory_id", "snapshot_date", name="uq_factory_snapshot_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    kpi_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

- [ ] **Step 2: Add import to `__init__.py` and `__all__`**

- [ ] **Step 3: Verify import**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.models import GroupKPISnapshot; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/group_kpi_snapshot.py backend/app/models/__init__.py
git commit -m "feat(multi-factory): add GroupKPISnapshot model"
```

---

### Task 3: SupplierSharedProfile Model

**Files:**
- Create: `backend/app/models/supplier_shared_profile.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write SupplierSharedProfile model**

```python
# backend/app/models/supplier_shared_profile.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SupplierSharedProfile(Base):
    __tablename__ = "supplier_shared_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unified_credit_code: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

- [ ] **Step 2: Add import to `__init__.py` and `__all__`**

- [ ] **Step 3: Verify import**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.models import SupplierSharedProfile; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/supplier_shared_profile.py backend/app/models/__init__.py
git commit -m "feat(multi-factory): add SupplierSharedProfile model"
```

---

### Task 4: Add factory_id to Anchor Models + Core Scope Layer

This task combines model changes with the core scope layer so that scope resolution and populate/validate functions are available before any API migration.

**Files:**
- Modify: `backend/app/models/product_line.py` — add `factory_id`
- Modify: `backend/app/models/user.py` — add `factory_id`
- Modify: `backend/app/models/supplier.py` — add `factory_id`, `shared_profile_id`, change unique constraint
- Modify: `backend/app/models/audit_program.py` — add `factory_id` to AuditProgram, AuditChecklistTemplate
- Create: `backend/app/core/factory_scope.py`
- Modify: `backend/app/core/permissions.py` — add `Module.GROUP`
- Modify: `backend/app/core/deps.py` — add dependency functions

- [ ] **Step 1: Add `factory_id` to ProductLine**

In `backend/app/models/product_line.py`, add:
```python
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import ForeignKey
# Add to class ProductLine:
factory_id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True  # nullable during migration
)
```

- [ ] **Step 2: Add `factory_id` to User**

In `backend/app/models/user.py`, add:
```python
factory_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("factories.id", ondelete="SET NULL"), nullable=True
)
```

- [ ] **Step 3: Modify Supplier — add `factory_id`, `shared_profile_id`, change unique**

In `backend/app/models/supplier.py`:
- Add `factory_id: Mapped[uuid.UUID]` with `ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True`
- Add `shared_profile_id: Mapped[uuid.UUID | None]` with `ForeignKey("supplier_shared_profiles.id", ondelete="SET NULL"), nullable=True`
- Remove `unique=True` from `supplier_no` column
- Add `__table_args__` with `UniqueConstraint("factory_id", "supplier_no", name="uq_supplier_no_per_factory")`

- [ ] **Step 4: Add `factory_id` to AuditProgram and AuditChecklistTemplate**

- [ ] **Step 5: Add `Module.GROUP` to permissions.py**

- [ ] **Step 6: Write `backend/app/core/factory_scope.py`**

Implement `FactoryScope`, `ProductLineScope`, `resolve_factory_scope`, `resolve_product_line_scope`, `resolve_effective_factory_id`, `apply_scope_filter`, `populate_factory_id`, and `validate_factory_invariant`. Reference spec §4.1-4.3.

- [ ] **Step 7: Add a unified `RequestScope` dependency to `backend/app/core/deps.py`**

Create a single dependency that resolves factory scope, effective factory ID, and product line scope in one call. This avoids multiple `Depends` that redundantly query the user, and ensures endpoints don't need to manually resolve `effective_factory_id` or call `resolve_product_line_scope`.

```python
from dataclasses import dataclass
from uuid import UUID

@dataclass
class RequestScope:
    """Pre-resolved scope for the current request. One object, one Depends."""
    factory_scope: FactoryScope
    effective_factory_id: UUID | None
    pl_scope: ProductLineScope
    user: User

async def get_request_scope(
    request: Request,
    factory_id: UUID | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequestScope:
    # 1. Factory scope
    user_factory_ids = await get_user_factory_ids(user, db)
    group_level = await get_user_permission(user, Module.GROUP, db)
    has_group_admin = group_level >= PermissionLevel.ADMIN
    factory_scope = resolve_factory_scope(user, user_factory_ids, has_group_admin)
    effective_factory_id = resolve_effective_factory_id(factory_scope, factory_id)

    # 2. Product line scope
    user_pl_codes = await get_user_product_line_codes(user, db)
    pl_scope = resolve_product_line_scope(user, user_pl_codes, factory_scope, db)

    return RequestScope(
        factory_scope=factory_scope,
        effective_factory_id=effective_factory_id,
        pl_scope=pl_scope,
        user=user,
    )
```

API endpoints then receive a single `scope: RequestScope = Depends(get_request_scope)` and use `scope.effective_factory_id`, `scope.pl_scope`, etc.

- [ ] **Step 8: Verify all imports work**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.core.factory_scope import FactoryScope, ProductLineScope, resolve_factory_scope, resolve_product_line_scope, apply_scope_filter, populate_factory_id, validate_factory_invariant; print('OK')"`

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/ backend/app/core/factory_scope.py backend/app/core/permissions.py backend/app/core/deps.py
git commit -m "feat(multi-factory): anchor model factory_id + core scope layer + Module.GROUP"
```

---

### Task 5: Scope Unit Tests

**Files:**
- Create: `backend/tests/test_factory_scope.py`

Write tests for the scope resolution logic BEFORE any API migration. This ensures the foundation is correct before building on it.

- [ ] **Step 1: Test `resolve_factory_scope`**

Test all 5 user types from spec §2:
- Factory operator → `accessible_factory_ids=[user.factory_id]`
- Factory admin (bypass) → `accessible_factory_ids=[user.factory_id]` (NOT None — bypass doesn't grant cross-factory)
- Group viewer → `accessible_factory_ids=user_factories`
- Group admin (GROUP ADMIN) → `accessible_factory_ids=None`
- No factory → `accessible_factory_ids=[]`

- [ ] **Step 2: Test `resolve_product_line_scope`**

Test bypass vs non-bypass, empty user_product_lines vs populated.

- [ ] **Step 3: Test `resolve_effective_factory_id`**

Test: single factory user locked, multi-factory user with/without query param, GROUP ADMIN with/without query param, unauthorized factory_id raises 403.

- [ ] **Step 4: Test `apply_scope_filter`**

Test factory filtering + product line filtering composition on a sample model.

- [ ] **Step 5: Test `populate_factory_id` and `validate_factory_invariant`**

Test product-line-derived, parent-derived, and explicit scope derivation paths.

- [ ] **Step 6: Run tests**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/test_factory_scope.py -v`

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_factory_scope.py
git commit -m "test(multi-factory): scope resolution unit tests — factory, product line, effective ID, filter, invariant"
```

---

### Task 6: Alembic Migration Part 1 — Schema + Nullable Columns + Backfill

**Files:**
- Create: `backend/alembic/versions/035_add_factory_tables_nullable.py`

This migration adds all schema changes with `factory_id` columns as **NULLABLE** and backfills data. It does NOT set columns to NOT NULL — that happens in Part 2 after all API/service code writes `factory_id` correctly.

The migration must:
1. Create `factories` table
2. Insert seed factory (code='DEFAULT')
3. Add `factory_id` to `product_lines` as **NULLABLE** → backfill with seed factory UUID
4. Add `factory_id` to `users` as **NULLABLE** → backfill all users with seed factory UUID
5. Create `user_factories` table → backfill for all existing users
6. Add `factory_id` to all ~50 business tables as **NULLABLE** → backfill per §3.5 derivation matrix
7. Create `supplier_shared_profiles` table
8. Add `factory_id` + `shared_profile_id` to `suppliers` as **NULLABLE** → backfill
9. Drop `supplier_no` unique constraint, add composite `(factory_id, supplier_no)` unique constraint
10. Create `audit_program_target_factories` table
11. Create `group_kpi_snapshots` table
12. Add `factory_id` to `audit_programs` and `audit_checklist_templates` as **NULLABLE** → backfill

**Why NULLABLE first:** Between this migration and Task 17 (NOT NULL enforcement), the existing create/update APIs will still work because `factory_id` is nullable. Once Tasks 4-12 add `populate_factory_id` to all services, we can safely enforce NOT NULL.

The backfill logic must follow §3.5 derivation matrix. For background sync (ERP/MES ingestion), `factory_id` must come from `ERPConnection.factory_id` / `MESConnection.factory_id` — handled in the service layer, not the migration.

- [ ] **Step 1: Generate migration**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && alembic revision -m "add_factory_tables_nullable"`

Note: Use `--rev-id` prefix if you need to control the revision ID. Alembic does not support `-o` for output filename.

- [ ] **Step 2: Write the full upgrade/downgrade migration**

Write all CREATE TABLE, ALTER TABLE ADD COLUMN (NULLABLE), UPDATE backfill, DROP/ADD constraint changes. **Do NOT** add ALTER COLUMN SET NOT NULL in this migration — that comes in Task 17.

For each backfill category, use the correct derivation path:
- Product-line-derived tables: `UPDATE ... SET factory_id = (SELECT factory_id FROM product_lines WHERE product_lines.code = table.product_line_code)`
- Parent-derived tables: `UPDATE ... SET factory_id = (SELECT factory_id FROM parent_table WHERE parent_table.pk = table.fk)`
- Explicit scope tables (Supplier, AuditChecklistTemplate): `UPDATE ... SET factory_id = default_factory_id`
- Nullable product_line_code: `UPDATE ... SET factory_id = COALESCE((SELECT ...), default_factory_id)`

- [ ] **Step 3: Run migration on dev database**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && alembic upgrade head`

- [ ] **Step 4: Verify seed data**

Create a temporary script `scripts/verify_migration.py`:
```python
import asyncio
from sqlalchemy import text
from app.database import async_session

async def check():
    async with async_session() as s:
        r = await s.execute(text('SELECT count(*) FROM factories'))
        print('factories:', r.scalar())
        r = await s.execute(text('SELECT count(*) FROM user_factories'))
        print('user_factories:', r.scalar())
        r = await s.execute(text("SELECT count(*) FROM fmea_documents WHERE factory_id IS NOT NULL"))
        print('fmea_documents with factory_id:', r.scalar())

asyncio.run(check())
```
Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python scripts/verify_migration.py && rm scripts/verify_migration.py`

Expected: `factories: 1` (seed), `user_factories: N` (one per existing user), `fmea_documents with factory_id: N` (all backfilled)

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/035_add_factory_tables_nullable.py
git commit -m "feat(multi-factory): migration part 1 — nullable factory_id columns + backfill"
```

---

### Task 7: Factory CRUD — Service + Schema (under /api/group/)

**Files:**
- Create: `backend/app/schemas/factory.py`
- Create: `backend/app/services/factory_service.py`

Note: Factory CRUD API routes will be in `backend/app/api/group.py` (Task 13), not a separate `api/factory.py`. This avoids route duplication.

- [ ] **Step 1: Write factory schemas**

`backend/app/schemas/factory.py`:
- `FactoryCreate(code, name, location?)`
- `FactoryUpdate(name?, location?, is_active?)`
- `FactoryResponse(id, code, name, location, is_active, created_at, updated_at)`
- `FactoryListResponse(items, total)`

- [ ] **Step 2: Write factory service**

`backend/app/services/factory_service.py`: CRUD operations (list, get, create, update, soft_delete). Follow `product_line_service.py` patterns exactly (including reference check before soft delete — check if any product_lines reference this factory before deactivating).

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/factory.py backend/app/services/factory_service.py
git commit -m "feat(multi-factory): Factory CRUD service and schemas (API routes in group.py)"
```

---

### Task 8: Auth Endpoint — Return FactoryScope + permissions.group

**Files:**
- Modify: `backend/app/api/auth.py` — add factory scope to /auth/me response
- Modify: `backend/app/schemas/auth.py` (or wherever auth response schema is)

- [ ] **Step 1: Add factory scope fields to auth response**

In the `/auth/me` endpoint response, add:
```python
"factory_scope": {
    "accessible_factory_ids": [...],  # list of UUID strings or null
    "default_factory_id": "...",     # UUID string or null
},
"factories": [...],                  # list of Factory objects user can access
"permissions": {
    ...
    "group": permission_level_int,   # NEW
}
```

**Note on field naming:** The backend uses snake_case (`accessible_factory_ids`). The frontend should use camelCase (`accessibleFactoryIds`) as per existing project conventions. The auth response schema should use `alias` in Pydantic v2 (`Field(alias="accessibleFactoryIds")`) OR the frontend should do the conversion in `authStore.ts`. Pick one approach and be consistent — the recommended approach is: keep the backend as snake_case, add `model_config = ConfigDict(populate_by_name=True)` to the schema, and convert to camelCase in the frontend store.

- [ ] **Step 2: Update frontend auth types**

In `frontend/src/types/index.ts`, add `Factory` interface and update the auth response type.

- [ ] **Step 3: Update `frontend/src/store/authStore.ts`**

Store `factoryScope` and `factories` from `/auth/me` response.

- [ ] **Step 4: Verify with curl**

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py frontend/src/types/index.ts frontend/src/store/authStore.ts
git commit -m "feat(multi-factory): return FactoryScope and permissions.group from /auth/me"
```

---

## Phase 2: Scope Filtering Rollout

### Task 9: Add factory_id to All Business Models (Bulk)

**Files:**
- Modify: ~50 model files to add `factory_id` column

Add `factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True)` to each model per §3.5 derivation matrix. All nullable — Part 1 migration (Task 6) backfills data while columns are nullable; Part 2 (Task 13) enforces NOT NULL after all services write factory_id correctly.

**Important for background sync services:** ERP/MES ingestion services must read `factory_id` from their parent `ERPConnection`/`MESConnection` record, not from request context. The `populate_factory_id` function handles this via parent-object derivation.

- [ ] **Step 1: Add factory_id to product-line-derived models**

FMEADocument, CAPAEightD, ControlPlan, ControlPlanItem, InspectionCharacteristic, SampleBatch, SampleValue, SPCAlarm, ControlLimitSnapshot, etc. (~30 files)

- [ ] **Step 2: Add factory_id to parent-derived models**

FMEAVersion (from fmea_id), ControlPlanVersion (from cp_id), SupplierCertification, SupplierEvaluation, SupplierPPAPSubmission, SupplierSCAR (from supplier_id), AuditPlan, AuditFinding (from program_id), etc.

- [ ] **Step 3: Add factory_id to connection-derived models**

MES/PLM/ERP sub-tables (SyncJob, PushOutbox from connection_id).

- [ ] **Step 4: Verify all models import**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.models import *; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/
git commit -m "feat(multi-factory): add factory_id to all business models per derivation matrix"
```

---

### Task 10: AuditProgramTargetFactories Model

**Files:**
- Modify: `backend/app/models/audit_program.py` — add `AuditProgramTargetFactory` association model

- [ ] **Step 1: Add AuditProgramTargetFactory model**

```python
class AuditProgramTargetFactory(Base):
    __tablename__ = "audit_program_target_factories"
    __table_args__ = (
        UniqueConstraint("program_id", "factory_id", name="uq_program_factory"),
    )

    program_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("audit_programs.program_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
```

- [ ] **Step 2: Add to `__init__.py` imports and `__all__`**

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/audit_program.py backend/app/models/__init__.py
git commit -m "feat(multi-factory): add AuditProgramTargetFactory association model"
```

---

### Task 11: Apply Scope Filter to Key APIs (First Wave)

**Files:**
- Modify: `backend/app/api/fmea.py`
- Modify: `backend/app/api/capa.py`
- Modify: `backend/app/api/dashboard.py`
- Modify: `backend/app/api/supplier.py`

For each API file, add `scope: RequestScope = Depends(get_request_scope)` to list endpoints, then use `scope.effective_factory_id` and `scope.pl_scope` with `apply_scope_filter`.

This is the most labor-intensive task. Each API needs:
1. Import `RequestScope` from `app.core.deps` and `get_request_scope` from `app.core.deps`
2. Import `apply_scope_filter`, `populate_factory_id`, `validate_factory_invariant` from `app.core.factory_scope`
3. Add `scope: RequestScope = Depends(get_request_scope)` to list endpoint signatures (replaces any manual `factory_id` query param + resolve logic)
4. Replace `apply_product_line_filter` calls with `apply_scope_filter(query, Model, "module", scope.factory_scope, scope.effective_factory_id, scope.pl_scope, scope.user, db, request)`
5. Add `populate_factory_id` on create endpoints (using `scope` for default factory)
6. Add `validate_factory_invariant` on create/update endpoints

- [ ] **Step 1: Migrate FMEA list + create endpoints**

- [ ] **Step 2: Migrate CAPA list + create endpoints**

- [ ] **Step 3: Migrate dashboard endpoint**

- [ ] **Step 4: Migrate supplier list + create endpoints**

- [ ] **Step 5: Verify each endpoint returns correct filtered data**

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/
git commit -m "feat(multi-factory): apply scope filter to FMEA, CAPA, dashboard, supplier APIs"
```

---

### Task 12: Apply Scope Filter to Remaining APIs (Second Wave)

**Files:**
- Modify: all remaining API files that have list endpoints

Same pattern as Task 11, applied to the remaining ~15 API modules.

**For ERP/MES background sync services specifically:** These run without HTTP request context. The `factory_id` must be derived from the parent connection record (`ERPConnection.factory_id` / `MESConnection.factory_id`), not from `get_factory_scope`. Update `erp_service.py` and `mes_ingestion_service.py` (or equivalent) to set `factory_id` from the connection before writing business entities.

- [ ] **Step 1: Migrate SPC, MSA, Gauge APIs**

- [ ] **Step 2: Migrate IQC, PPAP, QualityGoal APIs**

- [ ] **Step 3: Migrate Audit, ManagementReview APIs**

- [ ] **Step 4: Migrate CustomerQuality, APQP, ChangeImpact APIs**

- [ ] **Step 5: Migrate MES, PLM, ERP APIs + fix background sync factory_id derivation**

- [ ] **Step 6: Migrate IQC AQL, SupplierRisk, CPValidation APIs**

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/
git commit -m "feat(multi-factory): apply scope filter to all remaining APIs + background sync factory_id"
```

### Task 13: Alembic Migration Part 2 — NOT NULL Enforcement

**Files:**
- Create: `backend/alembic/versions/036_factory_id_not_null_enforcement.py`

This migration runs **after** Tasks 4-12 have added `populate_factory_id` to all services. It converts business ownership `factory_id` columns from NULLABLE to NOT NULL.

**Why two migrations:** Between Part 1 (nullable + backfill) and this migration, existing create/update APIs work because `factory_id` is nullable. Once all services populate `factory_id` via `populate_factory_id()`, we can safely enforce NOT NULL without breaking inserts.

**Important exclusion:** `users.factory_id` must remain **NULLABLE** per the design — group users can have no default factory (`factory_id IS NULL`). This migration only enforces NOT NULL on business ownership tables.

- [ ] **Step 1: Generate migration**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && alembic revision -m "factory_id_not_null_enforcement"`

- [ ] **Step 2: Write ALTER COLUMN SET NOT NULL for business ownership factory_id columns**

For each business table that has `factory_id` (excluding `users.factory_id` which stays nullable):
```python
op.alter_column('fmea_documents', 'factory_id', nullable=False)
op.alter_column('capa_eightd', 'factory_id', nullable=False)
# ... all ~50 business tables, BUT NOT users.factory_id
op.alter_column('suppliers', 'factory_id', nullable=False)
op.alter_column('product_lines', 'factory_id', nullable=False)
# NOTE: users.factory_id stays NULLABLE — group users have no default factory
```

Also add indexes for factory_id on all affected tables:
```python
op.create_index('ix_fmea_documents_factory_id', 'fmea_documents', ['factory_id'])
# ... one index per table with factory_id
```

- [ ] **Step 3: Run migration**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && alembic upgrade head`

- [ ] **Step 4: Verify all business factory_id columns are NOT NULL (users.factory_id should remain nullable)**

```python
# scripts/verify_not_null.py
import asyncio
from sqlalchemy import text
from app.database import engine

async def check():
    async with engine.connect() as conn:
        # Check that no business ownership factory_id column allows NULL
        # (users.factory_id is intentionally nullable — group users have no default factory)
        result = await conn.execute(text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE column_name = 'factory_id' AND is_nullable = 'YES'
            AND table_schema = 'public'
            AND table_name != 'users'
        """))
        nullable = result.fetchall()
        if nullable:
            print("WARNING: These factory_id columns are still nullable:")
            for row in nullable:
                print(f"  {row[0]}.{row[1]}")
        else:
            print("All business factory_id columns are NOT NULL ✓")

        # Verify users.factory_id is still nullable
        result2 = await conn.execute(text("""
            SELECT is_nullable FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'factory_id'
        """))
        row = result2.fetchone()
        if row and row[0] == 'YES':
            print("users.factory_id is correctly nullable ✓")
        else:
            print("ERROR: users.factory_id should be nullable!")

asyncio.run(check())
```

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/036_factory_id_not_null_enforcement.py
git commit -m "feat(multi-factory): migration part 2 — enforce NOT NULL on business factory_id columns"
```

---

## Phase 3: Group APIs

### Task 14: Group API — Dashboard, Comparison, Factory CRUD

**Files:**
- Create: `backend/app/schemas/group.py`
- Create: `backend/app/services/group_service.py`
- Create: `backend/app/api/group.py`
- Modify: `backend/app/main.py` — register group router

Note: Factory CRUD is under `/api/group/factories` (not a separate `/api/factories`), guarded by `require_permission(Module.GROUP, VIEW)` for read and `require_permission(Module.GROUP, ADMIN)` for write.

- [ ] **Step 1: Write group schemas** (FactoryKPI, GroupDashboard, etc.)

- [ ] **Step 2: Write group_service.py** — KPI snapshot aggregation, factory comparison

- [ ] **Step 3: Write group API routes**

All routes protected by `require_permission(Module.GROUP, PermissionLevel.VIEW)`. Factory CRUD routes under `/api/group/factories` with ADMIN for write operations.

- [ ] **Step 4: Register group router in main.py**

- [ ] **Step 5: Verify endpoints**

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/group.py backend/app/services/group_service.py backend/app/api/group.py backend/app/main.py
git commit -m "feat(multi-factory): Group API — dashboard, comparison, factory CRUD"
```

---

### Task 15: Group Supplier + Audit APIs

**Files:**
- Modify: `backend/app/api/group.py` — add supplier and audit endpoints
- Modify: `backend/app/services/group_service.py` — add shared supplier aggregation

- [ ] **Step 1: Add shared supplier list/merge endpoints**

- [ ] **Step 2: Add cross-factory audit program endpoints**

- [ ] **Step 3: Verify endpoints**

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/group.py backend/app/services/group_service.py
git commit -m "feat(multi-factory): Group supplier and audit endpoints"
```

---

## Phase 4: Frontend

### Task 16: Factory Switcher + Auth Store Update

**Files:**
- Modify: `frontend/src/store/authStore.ts`
- Modify: `frontend/src/components/layout/AppLayout.tsx`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add Factory, FactoryScope types to types/index.ts**

- [ ] **Step 2: Update authStore to store factoryScope, factories, and permissions.group**

- [ ] **Step 3: Add factory switcher dropdown to AppLayout header**

Visible when `factoryScope.accessibleFactoryIds === null || factoryScope.accessibleFactoryIds.length > 1`. Uses `factories` list for options. Changing factory updates a global `currentFactoryId` state.

- [ ] **Step 4: Add group menu items to sidebar**

Visible when `permissions.group >= PermissionLevel.VIEW` — regardless of factory count. A group user with only 1 factory still needs access to the group dashboard.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/authStore.ts frontend/src/components/layout/AppLayout.tsx frontend/src/types/index.ts
git commit -m "feat(multi-factory): factory switcher and group menu in sidebar"
```

---

### Task 17: Axios Interceptor for factory_id Auto-Injection

**Files:**
- Modify: `frontend/src/api/client.ts` (or equivalent Axios instance file)

Instead of modifying 30+ frontend list pages individually, inject `factory_id` automatically via Axios request interceptor — but only on business list APIs, not on auth/group/factory management endpoints:

- When `currentFactoryId` is set in authStore, automatically append `factory_id=<value>` to GET request query params.
- POST/PUT/PATCH requests do NOT inject `factory_id` — the backend derives it from `product_line_code` or `scope.default_factory_id`.
- Exclude `/api/auth/`, `/api/group/`, `/api/product-lines`, and `/api/factories` from injection.

- [ ] **Step 1: Add Axios request interceptor**

```typescript
// In the Axios instance setup
const FACTORY_ID_EXCLUDE_PREFIXES = ['/api/auth/', '/api/group/', '/api/product-lines', '/api/factories'];

apiClient.interceptors.request.use((config) => {
  const currentFactoryId = useAuthStore.getState().currentFactoryId;
  const isGetRequest = config.method === 'get';
  const isExcluded = FACTORY_ID_EXCLUDE_PREFIXES.some(prefix => config.url?.startsWith(prefix));

  if (currentFactoryId && isGetRequest && !isExcluded) {
    config.params = config.params || {};
    config.params.factory_id = currentFactoryId;
  }
  return config;
});
```

- [ ] **Step 2: Verify GET requests include factory_id in query params**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(multi-factory): Axios interceptor auto-injects factory_id on GET requests"
```

---

### Task 18: Frontend API Clients

**Files:**
- Create: `frontend/src/api/group.ts` (includes factory CRUD + group endpoints)

- [ ] **Step 1: Write group API client** — includes:
  - `listFactories()`, `createFactory()`, `updateFactory()`, `deactivateFactory()`
  - `getDashboard()`, `getComparison()`, `getSharedSuppliers()`, `getCrossFactoryAudits()`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/group.ts
git commit -m "feat(multi-factory): frontend API client for group endpoints"
```

---

### Task 19: Group Dashboard + Factory Management Pages

**Files:**
- Create: `frontend/src/pages/group/GroupDashboard.tsx`
- Create: `frontend/src/pages/group/FactoryManagement.tsx`
- Modify: `frontend/src/App.tsx` or router file — add group routes

- [ ] **Step 1: Write GroupDashboard.tsx** — KPI cards per factory, totals row, comparison link

- [ ] **Step 2: Write FactoryManagement.tsx** — Ant Design Table + CRUD modal

- [ ] **Step 3: Add routes to router** (`/group/dashboard`, `/group/factories`)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/group/ frontend/src/App.tsx
git commit -m "feat(multi-factory): Group dashboard and factory management pages"
```

---

### Task 20: Factory Comparison + Shared Suppliers + Cross-Factory Audits Pages

**Files:**
- Create: `frontend/src/pages/group/FactoryComparison.tsx`
- Create: `frontend/src/pages/group/GroupSuppliers.tsx`
- Create: `frontend/src/pages/group/GroupAudits.tsx`

- [ ] **Step 1: Write FactoryComparison.tsx** — side-by-side KPI table per factory

- [ ] **Step 2: Write GroupSuppliers.tsx** — shared supplier table with per-factory evaluation columns

- [ ] **Step 3: Write GroupAudits.tsx** — cross-factory audit program list

- [ ] **Step 4: Add routes** (`/group/comparison`, `/group/suppliers`, `/group/audits`)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/group/
git commit -m "feat(multi-factory): comparison, shared suppliers, cross-factory audits pages"
```

---

## Phase 5: Testing + Seed Data

### Task 21: Seed Data — Second Factory

**Files:**
- Modify: `backend/app/seed.py`

Add a second factory (e.g., code='SH-02', name='上海工厂') and assign some product lines and users to it. Also create a group admin user with GROUP ADMIN permission.

- [ ] **Step 1: Add second factory to seed.py**

- [ ] **Step 2: Assign some product lines to second factory**

- [ ] **Step 3: Create a group admin user with GROUP ADMIN permission**

- [ ] **Step 4: Run seed and verify**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -m app.seed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/seed.py
git commit -m "feat(multi-factory): add second factory and group admin to seed data"
```

---

### Task 22: Integration + Isolation Tests

**Files:**
- Create: `backend/tests/test_factory_isolation.py`

Test that factory A users cannot see factory B data, GROUP ADMIN can see all, bypass without GROUP cannot cross factories, ProductLineScope NONE returns empty, etc. Per spec §10.

- [ ] **Step 1: Write isolation test suite** (factory A user vs factory B user vs group admin)

- [ ] **Step 2: Write bypass vs GROUP decoupling tests** (per spec §10.2)

- [ ] **Step 3: Write factory_id invariant tests** (per spec §10.3)

- [ ] **Step 4: Write boundary tests** (per spec §10.4)

- [ ] **Step 5: Run tests and verify all pass**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -m pytest tests/test_factory_isolation.py -v`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_factory_isolation.py
git commit -m "test(multi-factory): factory isolation, bypass/GROUP decoupling, invariant, boundary tests"
```

---

### Task 23: Integration Verification

- [ ] **Step 1: Verify no import/startup errors**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.main import app; print('App loaded OK')"
```

- [ ] **Step 2: Start backend in background and verify endpoints**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT
sleep 3
# Login as admin
TOKEN=$(curl -s http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"Admin@2026"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
# Check /auth/me returns factory_scope
curl -s http://localhost:8000/api/auth/me -H "Authorization: Bearer $TOKEN" | python -m json.tool
# Stop server
kill "$SERVER_PID" 2>/dev/null
```

- [ ] **Step 3: Login as factory user, verify data is filtered to their factory**

- [ ] **Step 4: Test factory switcher on frontend**

- [ ] **Step 5: Test group dashboard page**

- [ ] **Step 6: Fix any issues found**

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat(multi-factory): integration verification and fixes"
```

---

### Task 24: Update ROADMAP

**Files:**
- Modify: `docs/ROADMAP.md`

Mark the multi-factory deployment row as complete. Only execute after Task 22 passes.

- [ ] **Step 1: Update ROADMAP.md status**

- [ ] **Step 2: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): mark multi-factory deployment support as complete"
```