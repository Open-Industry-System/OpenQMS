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
- `backend/app/api/group.py` — Group route endpoints
- `backend/alembic/versions/035_add_factory_tables.py` — Alembic migration
- `frontend/src/api/factory.ts` — Factory API client
- `frontend/src/api/group.ts` — Group API client
- `frontend/src/pages/group/GroupDashboard.tsx` — Group dashboard page
- `frontend/src/pages/group/FactoryManagement.tsx` — Factory CRUD page
- `frontend/src/pages/group/FactoryComparison.tsx` — Factory comparison page
- `frontend/src/pages/group/GroupSuppliers.tsx` — Shared suppliers page
- `frontend/src/pages/group/GroupAudits.tsx` — Cross-factory audits page

### Modified Files
- `backend/app/models/__init__.py` — Import new models
- `backend/app/models/product_line.py` — Add `factory_id` column
- `backend/app/models/user.py` — Add `factory_id` column
- `backend/app/models/role.py` — Add `UserFactory` model
- `backend/app/models/supplier.py` — Add `factory_id`, `shared_profile_id`, change unique constraint
- `backend/app/models/audit_program.py` — Add `factory_id` to AuditProgram, AuditChecklistTemplate
- `backend/app/core/permissions.py` — Add `Module.GROUP`
- `backend/app/core/deps.py` — Add `get_factory_scope`, `get_product_line_scope` dependencies
- `backend/app/api/auth.py` — Return FactoryScope + permissions.group in /auth/me
- `backend/app/api/product_line.py` — Add factory_id filtering
- `frontend/src/types/index.ts` — Add Factory, FactoryScope, GroupDashboard types
- `frontend/src/store/authStore.ts` — Store factory scope from /auth/me
- `frontend/src/components/layout/AppLayout.tsx` — Factory switcher in header, group menu items

---

## Phase 1: Foundation (Models + Migration + Scope Layer)

### Task 1: Factory Model + UserFactory + GroupKPISnapshot

**Files:**
- Create: `backend/app/models/factory.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write Factory, UserFactory, GroupKPISnapshot models**

```python
# backend/app/models/factory.py
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Date, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
        # UniqueConstraint added inline below
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "factory_id", name="uq_user_factory"),
    )


class GroupKPISnapshot(Base):
    __tablename__ = "group_kpi_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=False)
    snapshot_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    kpi_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("factory_id", "snapshot_date", name="uq_factory_snapshot_date"),
    )
```

- [ ] **Step 2: Add imports to `backend/app/models/__init__.py`**

Add `Factory`, `UserFactory`, `GroupKPISnapshot` to the imports and `__all__` list.

- [ ] **Step 3: Verify models import correctly**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.models import Factory, UserFactory, GroupKPISnapshot; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/factory.py backend/app/models/__init__.py
git commit -m "feat(multi-factory): add Factory, UserFactory, GroupKPISnapshot models"
```

---

### Task 2: SupplierSharedProfile Model

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

### Task 3: Add factory_id to Existing Models

**Files:**
- Modify: `backend/app/models/product_line.py` — add `factory_id`
- Modify: `backend/app/models/user.py` — add `factory_id`
- Modify: `backend/app/models/role.py` — add `UserFactory` model (already in factory.py, reference here)
- Modify: `backend/app/models/supplier.py` — add `factory_id`, `shared_profile_id`, change unique constraint

This task adds `factory_id` to the **anchor models** that other models reference. The full ~50-model migration will be in Task 5 (Alembic migration). For now, add the column definitions.

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
- Change `supplier_no` unique constraint: remove `unique=True` from column, add `__table_args__` with `UniqueConstraint("factory_id", "supplier_no", name="uq_supplier_no_per_factory")`

- [ ] **Step 4: Add `factory_id` to AuditProgram and AuditChecklistTemplate**

In `backend/app/models/audit_program.py`, add `factory_id` to both models.

- [ ] **Step 5: Verify all models import correctly**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.models import *; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/
git commit -m "feat(multi-factory): add factory_id to anchor models (ProductLine, User, Supplier, AuditProgram)"
```

---

### Task 4: Core Scope Layer — factory_scope.py

**Files:**
- Create: `backend/app/core/factory_scope.py`
- Modify: `backend/app/core/permissions.py` — add `Module.GROUP`
- Modify: `backend/app/core/deps.py` — add dependency functions

- [ ] **Step 1: Add `Module.GROUP` to permissions.py**

In `backend/app/core/permissions.py`, add to the `Module` enum:
```python
GROUP = "group"
```

- [ ] **Step 2: Write `backend/app/core/factory_scope.py`**

This is the core file implementing `FactoryScope`, `ProductLineScope`, `resolve_factory_scope`, `resolve_product_line_scope`, `resolve_effective_factory_id`, `apply_scope_filter`, `populate_factory_id`, and `validate_factory_invariant`. Reference the spec §4.1-4.3 for the full implementation. Key points:
- Import `PRODUCT_LINE_FIELD_MAP` from `product_line_filter.py`
- `resolve_factory_scope` takes `has_group_admin: bool` parameter
- `resolve_product_line_scope` returns `ProductLineScope(mode="ALL"|"EXPLICIT"|"NONE", codes=...)`
- `apply_scope_filter` takes both `FactoryScope` and `ProductLineScope`, does NOT call old `apply_product_line_filter`

- [ ] **Step 3: Add dependency functions to `backend/app/core/deps.py`**

```python
async def get_user_factory_ids(user: User, db: AsyncSession) -> list[UUID]:
    result = await db.execute(
        select(UserFactory.factory_id).where(UserFactory.user_id == user.user_id)
    )
    return [row[0] for row in result.all()]

async def get_factory_scope(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FactoryScope:
    user_factory_ids = await get_user_factory_ids(user, db)
    group_level = await get_user_permission(user, Module.GROUP, db)
    has_group_admin = group_level >= PermissionLevel.ADMIN
    return resolve_factory_scope(user, user_factory_ids, has_group_admin)

async def get_product_line_scope(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[str]:
    return await get_user_product_line_codes(user, db)
```

- [ ] **Step 4: Verify imports work**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.core.factory_scope import FactoryScope, ProductLineScope, resolve_factory_scope, resolve_product_line_scope, apply_scope_filter; print('OK')"`

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/factory_scope.py backend/app/core/permissions.py backend/app/core/deps.py
git commit -m "feat(multi-factory): add core scope layer with FactoryScope, ProductLineScope, Module.GROUP"
```

---

### Task 5: Alembic Migration — All Schema Changes

**Files:**
- Create: `backend/alembic/versions/035_add_factory_tables.py`

This is the big migration task. The migration must:
1. Create `factories` table
2. Insert seed factory (code='DEFAULT')
3. Add `factory_id` to `product_lines` (nullable → backfill → not null)
4. Add `factory_id` to `users` (nullable)
5. Create `user_factories` table
6. Backfill `user_factories` for all existing users
7. Add `factory_id` to all ~50 business tables (nullable → backfill → not null)
8. Create `supplier_shared_profiles` table
9. Add `factory_id` + `shared_profile_id` to `suppliers`
10. Change `supplier_no` unique constraint to composite `(factory_id, supplier_no)`
11. Create `audit_program_target_factories` table
12. Create `group_kpi_snapshots` table
13. Add `factory_id` to `audit_programs` and `audit_checklist_templates`

The backfill logic must follow §3.5 derivation matrix (product-line-derived, parent-derived, supplier-derived, explicit).

- [ ] **Step 1: Generate migration skeleton**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && alembic revision -m "add_factory_tables" -o 035_add_factory_tables.py`

- [ ] **Step 2: Write the full upgrade/downgrade migration**

Write all CREATE TABLE, ALTER TABLE ADD COLUMN, UPDATE backfill, ALTER COLUMN SET NOT NULL, and constraint changes. Follow the spec §7.1-7.2 exactly. Use `op.execute()` for data backfills with parameterized SQL.

- [ ] **Step 3: Run migration on dev database**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && alembic upgrade head`

- [ ] **Step 4: Verify seed data**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.database import async_session; from sqlalchemy import text; import asyncio; async def check(): async with async_session() as s: r = await s.execute(text('SELECT count(*) FROM factories')); print('factories:', r.scalar()); r = await s.execute(text('SELECT count(*) FROM user_factories')); print('user_factories:', r.scalar()); asyncio.run(check())"`

Expected: `factories: 1` (seed), `user_factories: N` (one per existing user)

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/035_add_factory_tables.py
git commit -m "feat(multi-factory): alembic migration — factories table, factory_id on all tables, backfill"
```

---

### Task 6: Factory CRUD — Service + Schema + API

**Files:**
- Create: `backend/app/schemas/factory.py`
- Create: `backend/app/services/factory_service.py`
- Create: `backend/app/api/factory.py`
- Modify: `backend/app/main.py` — register factory router

- [ ] **Step 1: Write factory schemas**

`backend/app/schemas/factory.py`:
- `FactoryCreate(code, name, location?)`
- `FactoryUpdate(name?, location?, is_active?)`
- `FactoryResponse(id, code, name, location, is_active, created_at, updated_at)`
- `FactoryListResponse(items, total)`

- [ ] **Step 2: Write factory service**

`backend/app/services/factory_service.py`: CRUD operations (list, get, create, update, soft_delete). Follow `product_line_service.py` patterns exactly (including reference check before soft delete).

- [ ] **Step 3: Write factory API routes**

`backend/app/api/factory.py`: Follow `product_line.py` patterns. All routes require admin. Add `?factory_id=` query parameter support.

- [ ] **Step 4: Register router in main.py**

- [ ] **Step 5: Verify endpoint works**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &` then `curl http://localhost:8000/api/factories`

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/factory.py backend/app/services/factory_service.py backend/app/api/factory.py backend/app/main.py
git commit -m "feat(multi-factory): Factory CRUD service, schema, and API routes"
```

---

### Task 7: Auth Endpoint — Return FactoryScope + permissions.group

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

### Task 8: Add factory_id to All Business Models (Bulk)

**Files:**
- Modify: ~50 model files to add `factory_id` column

Add `factory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("factories.id", ondelete="RESTRICT"), nullable=True)` to each model per §3.5 derivation matrix. All nullable for now — the migration already backfills and sets NOT NULL at the DB level.

- [ ] **Step 1: Add factory_id to product-line-derived models**

FMEADocument, CAPAEightD, ControlPlan, ControlPlanItem, InspectionCharacteristic, SampleBatch, SampleValue, SPCAlarm, ControlLimitSnapshot, etc. (~30 files)

- [ ] **Step 2: Add factory_id to parent-derived models**

FMEAVersion (from fmea_id), ControlPlanVersion (from cp_id), SupplierCertification, SupplierEvaluation, SupplierPPAPSubmission, SupplierSCAR (from supplier_id), AuditPlan, AuditFinding (from program_id), etc.

- [ ] **Step 3: Add factory_id to connection-derived models**

MES/PLM/ERP sub-tables (SyncJob, PushOutbox from connection_id).

- [ ] **Step 4: Add factory_id to AuditChecklistTemplate** (explicit scope)

- [ ] **Step 5: Verify all models import**

Run: `cd /Users/sam/Documents/Code/OpenQMS/backend && python -c "from app.models import *; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/
git commit -m "feat(multi-factory): add factory_id to all business models per derivation matrix"
```

---

### Task 9: AuditProgramTargetFactories Model

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

### Task 10: Apply Scope Filter to Key APIs (First Wave)

**Files:**
- Modify: `backend/app/api/fmea.py`
- Modify: `backend/app/api/capa.py`
- Modify: `backend/app/api/dashboard.py`
- Modify: `backend/app/api/supplier.py`
- Modify: other high-traffic APIs

For each API file, add `factory_scope: FactoryScope = Depends(get_factory_scope)` and `pl_scope: ProductLineScope = Depends(get_product_line_scope)` to list endpoints, then wrap queries with `apply_scope_filter`.

This is the most labor-intensive task. Each API needs:
1. Import `apply_scope_filter`, `resolve_effective_factory_id`, etc.
2. Add dependencies to list endpoints
3. Replace `apply_product_line_filter` calls with `apply_scope_filter`
4. Add `factory_id` query parameter and `resolve_effective_factory_id` call

- [ ] **Step 1: Migrate FMEA list endpoint**

- [ ] **Step 2: Migrate CAPA list endpoint**

- [ ] **Step 3: Migrate dashboard endpoint**

- [ ] **Step 4: Migrate supplier list endpoint**

- [ ] **Step 5: Verify each endpoint returns correct filtered data**

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/
git commit -m "feat(multi-factory): apply scope filter to FMEA, CAPA, dashboard, supplier APIs"
```

---

### Task 11: Apply Scope Filter to Remaining APIs (Second Wave)

**Files:**
- Modify: all remaining API files that have list endpoints

Same pattern as Task 10, applied to the remaining ~15 API modules.

- [ ] **Step 1: Migrate SPC, MSA, Gauge APIs**

- [ ] **Step 2: Migrate IQC, PPAP, QualityGoal APIs**

- [ ] **Step 3: Migrate Audit, ManagementReview APIs**

- [ ] **Step 4: Migrate CustomerQuality, APQP, ChangeImpact APIs**

- [ ] **Step 5: Migrate MES, PLM, ERP APIs**

- [ ] **Step 6: Migrate IQC AQL, SupplierRisk, CPValidation APIs**

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/
git commit -m "feat(multi-factory): apply scope filter to all remaining APIs"
```

---

### Task 12: populate_factory_id + validate_factory_invariant in Services

**Files:**
- Modify: `backend/app/core/factory_scope.py` — add `populate_factory_id` and `validate_factory_invariant`
- Modify: key service files to call these functions on create/update

- [ ] **Step 1: Implement `populate_factory_id` and `validate_factory_invariant`** (spec §4.3)

- [ ] **Step 2: Add calls to FMEA service create/update**

- [ ] **Step 3: Add calls to CAPA service create/update**

- [ ] **Step 4: Add calls to Supplier service create/update**

- [ ] **Step 5: Add calls to remaining services (IQC, SPC, Audit, etc.)**

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/factory_scope.py backend/app/services/
git commit -m "feat(multi-factory): add factory_id population and validation to services"
```

---

## Phase 3: Group APIs

### Task 13: Group Dashboard + Factory Comparison API

**Files:**
- Create: `backend/app/schemas/group.py`
- Create: `backend/app/services/group_service.py`
- Create: `backend/app/api/group.py`
- Modify: `backend/app/main.py` — register group router

- [ ] **Step 1: Write group schemas** (FactoryKPI, GroupDashboard, etc.)

- [ ] **Step 2: Write group_service.py** — KPI snapshot aggregation, factory comparison

- [ ] **Step 3: Write group API routes** — all protected by `require_permission(Module.GROUP, PermissionLevel.VIEW)`

- [ ] **Step 4: Write factory CRUD routes** — list, create, update, soft_delete factories

- [ ] **Step 5: Register group router**

- [ ] **Step 6: Verify endpoints**

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/group.py backend/app/services/group_service.py backend/app/api/group.py backend/app/main.py
git commit -m "feat(multi-factory): Group API — dashboard, comparison, factory CRUD"
```

---

### Task 14: Group Supplier + Audit APIs

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

### Task 15: Factory Switcher + Auth Store Update

**Files:**
- Modify: `frontend/src/store/authStore.ts`
- Modify: `frontend/src/components/layout/AppLayout.tsx`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add Factory, FactoryScope types to types/index.ts**

- [ ] **Step 2: Update authStore to store factoryScope, factories, and permissions.group**

- [ ] **Step 3: Add factory switcher dropdown to AppLayout header**

Only visible when `factoryScope.accessibleFactoryIds === null || factoryScope.accessibleFactoryIds.length > 1`. Uses `factories` list for options. Changing factory updates a global `currentFactoryId` state.

- [ ] **Step 4: Add group menu items to sidebar**

Visible when `permissions.group >= 1 && (factoryScope.accessibleFactoryIds === null || factoryScope.accessibleFactoryIds.length > 1)`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/authStore.ts frontend/src/components/layout/AppLayout.tsx frontend/src/types/index.ts
git commit -m "feat(multi-factory): factory switcher and group menu in sidebar"
```

---

### Task 16: Frontend API Clients

**Files:**
- Create: `frontend/src/api/factory.ts`
- Create: `frontend/src/api/group.ts`

- [ ] **Step 1: Write factory API client** (listFactories, createFactory, updateFactory, deactivateFactory)

- [ ] **Step 2: Write group API client** (getDashboard, getComparison, getSharedSuppliers, getCrossFactoryAudits)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/factory.ts frontend/src/api/group.ts
git commit -m "feat(multi-factory): frontend API clients for factory and group"
```

---

### Task 17: Group Dashboard + Factory Management Pages

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

### Task 18: Factory Comparison + Shared Suppliers + Cross-Factory Audits Pages

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

### Task 19: Pass factory_id Query Parameter on All Frontend List Pages

**Files:**
- Modify: all frontend list page components that call list APIs

When `currentFactoryId` is set (from factory switcher), append `?factory_id=` to all API calls.

- [ ] **Step 1: Create a shared hook `useFactoryScope`** that returns currentFactoryId from authStore

- [ ] **Step 2: Update API client functions to accept optional `factoryId` parameter**

- [ ] **Step 3: Update list page components to pass factoryId**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(multi-factory): pass factory_id query parameter on all frontend list pages"
```

---

## Phase 5: Testing + Seed Data

### Task 20: Seed Data — Second Factory

**Files:**
- Modify: `backend/app/seed.py`

Add a second factory (e.g., code='SH-02', name='上海工厂') and assign some product lines and users to it.

- [ ] **Step 1: Add second factory to seed.py**

- [ ] **Step 2: Assign some product lines to second factory**

- [ ] **Step 3: Create a group admin user with GROUP ADMIN permission**

- [ ] **Step 4: Run seed and verify**

- [ ] **Step 5: Commit**

```bash
git add backend/app/seed.py
git commit -m "feat(multi-factory): add second factory and group admin to seed data"
```

---

### Task 21: Isolation Tests

**Files:**
- Create: `backend/tests/test_factory_isolation.py`

Test that factory A users cannot see factory B data, GROUP ADMIN can see all, bypass without GROUP cannot cross factories, ProductLineScope NONE returns empty, etc. Per spec §10.

- [ ] **Step 1: Write isolation test suite** (factory A user vs factory B user vs group admin)

- [ ] **Step 2: Write bypass vs GROUP decoupling tests** (per spec §10.2)

- [ ] **Step 3: Write factory_id invariant tests** (per spec §10.3)

- [ ] **Step 4: Write boundary tests** (per spec §10.4)

- [ ] **Step 5: Run tests and verify all pass**

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_factory_isolation.py
git commit -m "test(multi-factory): factory isolation, bypass/GROUP decoupling, invariant, boundary tests"
```

---

### Task 22: Integration Verification

- [ ] **Step 1: Run full backend startup**

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 2: Login as admin, verify /auth/me returns factory_scope and permissions.group**

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

### Task 23: Update ROADMAP

**Files:**
- Modify: `docs/ROADMAP.md`

Mark the multi-factory deployment row as complete.

- [ ] **Step 1: Update ROADMAP.md status**

- [ ] **Step 2: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): mark multi-factory deployment support as complete"
```