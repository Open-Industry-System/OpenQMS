# Product Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a cross-factory "product type" taxonomy as the parent of product lines, and add a `current_product_type` recommendation scope so FMEA recommendations and semantic search can recall history across all product lines of the same type.

**Architecture:** New `product_types` master-data table (cross-factory, no `factory_id`) with `product_lines.product_type_code` FK. A new `recommendation_scope.py` module resolves any scope + current product line + `RequestScope` into a `product_line_codes` set (business scope ∩ user-accessible product lines ∩ accessible-factory product lines). FMEA recommendation + graph similarity + the `/similar-nodes` debug endpoint + semantic search/QA consume that set; embedding writes are untouched (no vector backfill). 8D pipeline is explicitly left unchanged.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 async + Alembic (PostgreSQL 15) | React 18 + TypeScript 5.6 + Ant Design 5.29 + i18next (zh-CN/en-US)

## Global Constraints

- Chinese UI, bilingual zh-CN/en-US i18n throughout (menu, fields, messages).
- Document numbering / codes: uppercase `^[A-Z0-9_-]+$`, max 20 chars (matches `ProductLineCreate.code`).
- PKs: UUID v4 generated in Python for audit rows; `product_types.code` is a string PK (matches `product_lines.code`).
- Every CRUD operation manually creates an `AuditLog` in its service method (model: `app.models.audit.AuditLog`, fields `table_name/record_id/action/changed_fields/operated_by`).
- `factory_id` is NOT NULL on all business tables; `product_types` is the exception — cross-factory, no `factory_id`.
- Services raise `ValueError`; API layer converts to `HTTPException` (400 for validation, 403 for permission, 404 for not-found, 409/400 for reference conflicts).
- List endpoints return `{ items }` for product_type/product_line lists (matches `ProductLineListResponse`).
- FMEA graph: `find_similar_nodes_advanced` lives on abstract `FMEAGraphRepository` (`graph/repository.py:37`) with two impls — JSONB (`graph/jsonb_repository.py:224`) and Neo4j (`graph/neo4j_repository.py:276`); both must stay signature-compatible. **Final signature (no `scope` param):** `find_similar_nodes_advanced(self, node_type, query_text, product_line_codes, limit=10, min_similarity=0.3)` where `product_line_codes: list[str] | None` (`None` = global, no filter).
- Test auth pattern (from `tests/test_graph_api.py`): override `app.dependency_overrides[get_current_user]`, `[get_request_scope]`, and `[get_db]` for ASGI-transport clients. Existing conftest fixtures: `db` (AsyncSession), `default_factory` (Factory), `admin_user` (User) — see `tests/conftest.py`.
- Backend tests: `SECRET_KEY=test-secret-key pytest tests/ -x`; frontend: `npm run build` (tsc --noEmit + vite build), `npm run lint`, `vitest` for component tests. Worktree-local run: backend tests via main checkout's `backend/.venv`; `npm install` needed in worktree frontend before first build/test.
- No embedding backfill; `document_embeddings` table is NOT touched by this plan.

---

## File Structure

**New backend files:**
- `backend/app/models/product_type.py` — `ProductType` ORM model.
- `backend/app/schemas/product_type.py` — Pydantic create/update/response/list schemas.
- `backend/app/services/product_type_service.py` — CRUD + AuditLog + soft-delete reference check.
- `backend/app/services/recommendation_scope.py` — `resolve_product_line_codes()` (scope → codes ∩ permissions).
- `backend/app/api/product_type.py` — `/api/product-types` router.
- `backend/alembic/versions/<new>_add_product_types.py` — migration + downgrade.

**Modified backend files:**
- `backend/app/models/product_line.py` — add `product_type_code` column + FK.
- `backend/app/schemas/product_line.py` — add `product_type_code` to create/update/response (nullable, clearable).
- `backend/app/services/product_line_service.py` — `create_product_line`/`update_product_line` accept + validate `product_type_code` (sentinel for "clear to null").
- `backend/app/api/product_line.py` — pass `product_type_code` through; 400 on invalid type.
- `backend/app/schemas/recommendation.py` — extend `scope` Literal to 3 values; `effective_scope` Literal; `SimilarNodesRequest` (product_line_code optional + scope 3-value) / `SimilarNodesResponse.effective_scope`.
- `backend/app/services/recommendation_service.py` — `recommend()` accepts `request_scope`; use `resolve_product_line_codes`; pass codes to graph repo.
- `backend/app/graph/repository.py` — abstract `find_similar_nodes_advanced` final signature (no `scope`).
- `backend/app/graph/jsonb_repository.py` — impl uses `FMEADocument.product_line_code.in_(codes)`.
- `backend/app/graph/neo4j_repository.py` — impl uses `n.product_line_code IN $codes` Cypher.
- `backend/app/api/fmea.py` — pass `scope` (RequestScope) into `RecommendationService.recommend`.
- `backend/app/api/graph.py:218` — `/similar-nodes` endpoint calls resolver + passes codes.
- `backend/app/services/search_service.py` — `semantic_search` + `ask` accept `product_type_code`, resolve to codes (uses `self.db`).
- `backend/app/schemas/search.py` — `QARequest` add `product_type_code`.
- `backend/app/api/search.py` — `/semantic` GET query param `product_type_code`; `/ask` passes it.
- `backend/app/main.py` — register `product_type_router`.
- `backend/app/seed.py` — seed `POWER`/`PCB` types, assign `DC-DC-100` + `PCB-SMT-200`.

**New frontend files:**
- `frontend/src/api/productType.ts` — product type API client.
- `frontend/src/pages/admin/ProductTypePage.tsx` — product type CRUD admin page.
- `frontend/src/pages/admin/ProductLinePage.tsx` — product line CRUD admin page (minimal, with type assignment).
- `frontend/src/locales/zh-CN/productType.json`, `frontend/src/locales/en-US/productType.json` — i18n.

**Modified frontend files:**
- `frontend/src/types/index.ts` — add `ProductType` interface; `ProductLine.product_type_code`.
- `frontend/src/api/productLine.ts` — `createProductLine`/`updateProductLine` accept `product_type_code`.
- `frontend/src/api/recommendation.ts` — `RecommendRequest.scope` / `RecommendResponse.effective_scope` 3-value union.
- `frontend/src/api/search.ts` — semantic search + QA request params add `product_type_code`.
- `frontend/src/pages/graph/SemanticSearchTab.tsx` — product type filter dropdown + linkage.
- `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx` + `InlineRecommendations.tsx` — scope 3 options.
- `frontend/src/App.tsx` — routes for `/admin/product-types` + `/admin/product-lines`.
- `frontend/src/components/layout/AppLayout.tsx` — menu items (admin only).
- `frontend/src/locales/zh-CN/layout.json` + `en-US/layout.json` — menu labels.

**New/modified test files:**
- `backend/tests/test_product_type_api.py` — product type CRUD + permissions + soft-delete.
- `backend/tests/test_recommendation_scope.py` — `resolve_product_line_codes` cases + permission intersection.
- `backend/tests/test_product_line_type_field.py` — type field create/update + clear-null + invalid-type 400.
- `backend/tests/test_search_product_type.py` — search/QA product_type_code filter.
- `backend/tests/conftest.py` — add shared fixtures (admin_client/viewer_user/request_scope_all/request_scope_restricted_other_factory/product_type_power) building on existing `db`/`default_factory`/`admin_user`.

---

## Task 1: ProductType ORM model + migration

**Files:**
- Create: `backend/app/models/product_type.py`
- Create: `backend/alembic/versions/<rev>_add_product_types.py`

**Interfaces:**
- Produces: `ProductType` model with columns `code: str (PK)`, `name: str`, `description: str | None`, `is_active: bool`, `created_at`, `updated_at`.

- [ ] **Step 1: Write the model**

`backend/app/models/product_type.py`:
```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductType(Base):
    __tablename__ = "product_types"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

- [ ] **Step 2: Verify model imports cleanly**

Run: `cd backend && python -c "from app.models.product_type import ProductType; print(ProductType.__tablename__)"`
Expected: prints `product_types`

- [ ] **Step 3: Write the migration**

Find current head: `cd backend && alembic heads` (note the head revision id).

Create `backend/alembic/versions/<new_rev_id>_add_product_types.py` with `down_revision = "<current head>"`:
```python
"""add product_types table and product_lines.product_type_code

Revision ID: <new_rev_id>
Revises: <current_head>
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa


revision = "<new_rev_id>"
down_revision = "<current_head>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_types",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("product_lines", sa.Column("product_type_code", sa.String(20), nullable=True))
    op.create_foreign_key(
        "fk_product_lines_product_type",
        "product_lines", "product_types",
        ["product_type_code"], ["code"], ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_product_lines_product_type", "product_lines", type_="foreignkey")
    op.drop_column("product_lines", "product_type_code")
    op.drop_table("product_types")
```

- [ ] **Step 4: Verify migration applies (if DB available)**

Run: `cd backend && alembic upgrade head`
Expected: no errors. (If no DB in worktree, skip and note in commit message.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/product_type.py backend/alembic/versions/<new_rev_id>_add_product_types.py
git commit -m "feat(product_type): add ProductType model + migration with product_lines.product_type_code FK"
```

---

## Task 2: Shared test fixtures (conftest additions)

**Files:**
- Modify: `backend/tests/conftest.py`

> **Why this comes first:** Tasks 3-7 depend on `admin_client`, `viewer_user`, `request_scope_all`, `request_scope_restricted_other_factory`, `product_type_power`. Existing conftest already provides `db` (AsyncSession), `default_factory` (Factory), `admin_user` (User) — we build on those. `require_admin` depends on `get_current_user` (`permissions.py:145`), so admin clients MUST override `get_current_user` too, not just `get_request_scope`/`get_db`.

**Interfaces:**
- Produces: `admin_client`, `viewer_user`, `request_scope_all`, `request_scope_restricted_other_factory`, `product_type_power` — all building on existing `db`/`default_factory`/`admin_user`.

- [ ] **Step 1: Inspect existing conftest**

Run: `cd backend && grep -n "async def db\|async def default_factory\|async def admin_user\|get_current_user\|get_request_scope\|RequestScope\|FactoryScope\|ProductLineScope" tests/conftest.py`
Confirm `db`, `default_factory`, `admin_user` exist and note their imports.

- [ ] **Step 2: Add shared fixtures**

Append to `backend/tests/conftest.py` (use `@pytest_asyncio.fixture` to match the existing fixtures at `conftest.py:108,129`; `pytest_asyncio` is already imported there — confirm with `grep -n "import pytest_asyncio\|from pytest_asyncio" tests/conftest.py`). Mirror the override pattern in `tests/test_graph_api.py:144-188`:
```python
import uuid
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.deps import RequestScope, get_current_user, get_db, get_request_scope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.services.product_type_service import create_product_type


def _scope_for(user, default_factory, accessible_factory_ids=None, pl_mode="ALL", pl_codes=None):
    return RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=accessible_factory_ids, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode=pl_mode, codes=pl_codes),
        user=user,
    )


@pytest_asyncio.fixture
async def admin_client(db, admin_user, default_factory):
    """ASGI client authenticated as admin. Overrides get_current_user (required by require_admin),
    get_db, and get_request_scope. Clears overrides on teardown."""
    scope = _scope_for(admin_user, default_factory, accessible_factory_ids=None)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def viewer_user(db: AsyncSession, default_factory: Factory) -> User:
    """Create a user whose role is non-admin so require_admin (permissions.py:145) raises 403.
    Mirrors admin_user (conftest.py:129) but uses a viewer RoleDefinition."""
    from app.models.role import RoleDefinition
    result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "viewer"))
    role = result.scalar_one_or_none()
    if role is None:
        role = RoleDefinition(role_key="viewer", name_zh="只读用户", name_en="Viewer", is_system=True, is_active=True)
        db.add(role)
        await db.flush()
    user = User(
        user_id=uuid.uuid4(),
        username=f"test_viewer_{uuid.uuid4().hex[:8]}",
        display_name="Test Viewer",
        password_hash="hashed",
        role_id=role.id,
        legacy_role="viewer",
        is_active=True,
        factory_id=default_factory.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def request_scope_all(admin_user, default_factory):
    return _scope_for(admin_user, default_factory, accessible_factory_ids=None)


@pytest_asyncio.fixture
async def request_scope_restricted_other_factory(admin_user, default_factory):
    other = uuid.uuid4()
    return _scope_for(admin_user, default_factory, accessible_factory_ids=[other])


@pytest_asyncio.fixture
async def product_type_power(db, admin_user):
    return await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)
```

> **No `viewer_client` fixture.** `require_admin` (`permissions.py:145`) checks the user's role via `get_current_user`; a client backed by `admin_user` would pass the admin guard, so a `viewer_client` fixture would be misleading. The 403 test in Task 4 builds its own ASGI client inline with `viewer_user` (which has a non-admin role), exactly like `test_graph_api.py:258-294` swaps scope per-test. `viewer_user` is the fixture non-admin tests depend on.

> **`admin_user` side-effect:** the existing `admin_user` fixture idempotently pre-creates `ProductLine(code="DC-DC-100", factory_id=default_factory.id)` with `product_type_code=None` (conftest.py:136-146). Tests below use **unique product-line codes** (e.g. `PT-DC-100`, `PT-AC-200`, `PT-MOTOR-100`) to avoid PK collisions; tests that specifically need to type the existing `DC-DC-100` use `update_product_line`, not `create_product_line`.

- [ ] **Step 3: Verify fixtures load**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/conftest.py --collect-only -q 2>&1 | head -5 && python -c "import tests.conftest"`
Expected: no import errors.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test(fixtures): add shared product-type/recommendation-scope test fixtures"
```

---

## Task 3: ProductLine carries product_type_code (nullable, clearable, validated)

**Files:**
- Modify: `backend/app/models/product_line.py`
- Modify: `backend/app/schemas/product_line.py`
- Modify: `backend/app/services/product_line_service.py:28-46`
- Modify: `backend/app/api/product_line.py:30-63`
- Test: `backend/tests/test_product_line_type_field.py`

**Interfaces:**
- Consumes: `ProductType` from Task 1 (FK target + existence validation).
- Produces: `ProductLineCreate.product_type_code: str | None`, `ProductLineResponse.product_type_code: str | None`; service `create_product_line(..., product_type_code=None)`, `update_product_line(..., product_type_code=...)` where `product_type_code` is a sentinel-aware optional that can clear to NULL.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_product_line_type_field.py`:
```python
import pytest
from app.services.product_line_service import create_product_line, update_product_line, get_product_line
from app.services.product_type_service import create_product_type


@pytest.mark.asyncio
async def test_create_product_line_with_type(db, default_factory, admin_user):
    # NOTE: admin_user fixture pre-creates DC-DC-100; use a unique code to avoid PK collision.
    await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)
    pl = await create_product_line(db, code="PT-DC-100", name="DC-DC 100W", factory_id=default_factory.id, product_type_code="POWER")
    assert pl.product_type_code == "POWER"
    assert (await get_product_line(db, "PT-DC-100")).product_type_code == "POWER"


@pytest.mark.asyncio
async def test_create_product_line_invalid_type_raises(db, default_factory, admin_user):
    with pytest.raises(ValueError):
        await create_product_line(db, code="PT-X-1", name="X", factory_id=default_factory.id, product_type_code="NOPE")


@pytest.mark.asyncio
async def test_update_product_line_clears_type_to_null(db, default_factory, admin_user):
    await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)
    pl = await create_product_line(db, code="PT-CLR-1", name="Clearable", factory_id=default_factory.id, product_type_code="POWER")
    # Sentinel UNSET for name/is_active; explicit None for product_type_code clears it.
    updated = await update_product_line(db, pl, name=None, is_active=None, product_type_code=None)
    assert updated.product_type_code is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_product_line_type_field.py -x -v`
Expected: FAIL — `product_type_code` not a parameter / no UNSET sentinel.

- [ ] **Step 3: Add column to ProductLine model**

In `backend/app/models/product_line.py`, add inside the class (after `factory_id`):
```python
    product_type_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("product_types.code", ondelete="RESTRICT"), nullable=True
    )
```
Add `ForeignKey` to the existing `from sqlalchemy import ...` import line.

- [ ] **Step 4: Update schemas (nullable + clearable)**

In `backend/app/schemas/product_line.py`:
```python
class ProductLineCreate(BaseModel):
    code: str = Field(..., max_length=20, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(..., max_length=100)
    product_type_code: str | None = Field(default=None, max_length=20)


class ProductLineUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    product_type_code: str | None = Field(default=None, max_length=20)


class ProductLineResponse(BaseModel):
    code: str
    name: str
    is_active: bool
    product_type_code: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
```

> **Clear-to-null semantics:** `ProductLineUpdate` uses `product_type_code: str | None = None`. To distinguish "field omitted" from "explicitly clear to null", the service uses a sentinel: callers pass the Pydantic-validated value, and the service treats `None` as "clear to null" only when the field was explicitly provided. We detect "provided" via `req.model_fields_set` (Pydantic v2). See Step 5.

- [ ] **Step 5: Update service signatures (sentinel + validation)**

In `backend/app/services/product_line_service.py`, add a module-level sentinel and rewrite create/update:
```python
# Sentinel for "field not provided" (distinct from None = "clear to null").
UNSET = object()


async def _validate_product_type_code(db: AsyncSession, product_type_code: str | None) -> str | None:
    """Validate the type exists when set; raise ValueError on invalid. None means clear-to-null."""
    if product_type_code is None:
        return None
    from app.models.product_type import ProductType
    existing = await db.execute(select(ProductType).where(ProductType.code == product_type_code))
    if existing.scalar_one_or_none() is None:
        raise ValueError(f"产品类型 '{product_type_code}' 不存在")
    return product_type_code


async def create_product_line(
    db: AsyncSession, code: str, name: str, factory_id: uuid.UUID | None = None, product_type_code: str | None = None
) -> ProductLine:
    existing = await get_product_line(db, code)
    if existing:
        raise ValueError(f"产品线 '{code}' 已存在")
    product_type_code = await _validate_product_type_code(db, product_type_code)
    pl = ProductLine(code=code, name=name, factory_id=factory_id, product_type_code=product_type_code)
    db.add(pl)
    await db.commit()
    await db.refresh(pl)
    return pl


async def update_product_line(
    db: AsyncSession,
    pl: ProductLine,
    name: str | None,
    is_active: bool | None,
    product_type_code=UNSET,
) -> ProductLine:
    """product_type_code: UNSET = leave unchanged; None = clear to null; str = set."""
    if name is not None:
        pl.name = name
    if is_active is not None:
        pl.is_active = is_active
    if product_type_code is not UNSET:
        pl.product_type_code = await _validate_product_type_code(db, product_type_code)
    await db.commit()
    await db.refresh(pl)
    return pl
```

- [ ] **Step 6: Update API to thread product_type_code + sentinel**

In `backend/app/api/product_line.py`:
- create endpoint:
```python
        pl = await product_line_service.create_product_line(
            db, req.code, req.name, factory_id=factory_id, product_type_code=req.product_type_code
        )
```
- update endpoint — detect explicit provision via `model_fields_set` and pass sentinel otherwise:
```python
    pt_code = req.product_type_code if "product_type_code" in req.model_fields_set else product_line_service.UNSET
    try:
        updated = await product_line_service.update_product_line(db, pl, req.name, req.is_active, pt_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.ProductLineResponse.model_validate(updated)
```
Add `from fastapi import HTTPException` import if missing (it's already imported in the file).

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_product_line_type_field.py -x -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/product_line.py backend/app/schemas/product_line.py backend/app/services/product_line_service.py backend/app/api/product_line.py backend/tests/test_product_line_type_field.py
git commit -m "feat(product_line): carry + validate + clear product_type_code (sentinel for clear-to-null)"
```

---

## Task 4: ProductType service + schema + API (CRUD + soft-delete)

**Files:**
- Create: `backend/app/schemas/product_type.py`
- Create: `backend/app/services/product_type_service.py`
- Create: `backend/app/api/product_type.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_product_type_api.py`

**Interfaces:**
- Produces: `product_type_service.list_product_types(db, is_active=None)`, `get_product_type(db, code)`, `create_product_type(db, code, name, description, operated_by)`, `update_product_type(...)`, `delete_product_type(db, pt, operated_by)` (soft-delete + reference check). API `GET/POST/PUT/DELETE /api/product-types` (admin-gated writes via `require_admin`).

- [ ] **Step 1: Write schemas**

`backend/app/schemas/product_type.py`:
```python
from datetime import datetime

from pydantic import BaseModel, Field


class ProductTypeCreate(BaseModel):
    code: str = Field(..., max_length=20, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(..., max_length=100)
    description: str | None = Field(default=None, max_length=500)


class ProductTypeUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class ProductTypeResponse(BaseModel):
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ProductTypeListResponse(BaseModel):
    items: list[ProductTypeResponse]
```

- [ ] **Step 2: Write failing tests**

`backend/tests/test_product_type_api.py`:
```python
import pytest
from app.models.product_line import ProductLine


@pytest.mark.asyncio
async def test_create_product_type_admin_ok(admin_client):
    resp = await admin_client.post("/api/product-types", json={"code": "POWER", "name": "电源类"})
    assert resp.status_code == 200
    assert resp.json()["code"] == "POWER"


@pytest.mark.asyncio
async def test_create_product_type_non_admin_forbidden(db, viewer_user, default_factory):
    # Build an ASGI client authenticated as viewer_user (non-admin role) — require_admin raises 403.
    from app.main import app
    from app.core.deps import get_current_user, get_db, get_request_scope, RequestScope
    from app.core.factory_scope import FactoryScope, ProductLineScope
    from httpx import ASGITransport, AsyncClient
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=default_factory.id),
        effective_factory_id=default_factory.id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=viewer_user,
    )
    app.dependency_overrides[get_current_user] = lambda: viewer_user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_request_scope] = lambda: scope
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/product-types", json={"code": "X", "name": "X"})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_product_type_refused_when_active_product_line_references(admin_client, db, default_factory):
    await admin_client.post("/api/product-types", json={"code": "POWER", "name": "电源类"})
    # Use a unique product-line code (admin_user fixture pre-creates DC-DC-100).
    db.add(ProductLine(code="PT-REF-1", name="Ref PL", factory_id=default_factory.id, product_type_code="POWER"))
    await db.commit()
    resp = await admin_client.delete("/api/product-types/POWER")
    assert resp.status_code == 400
    assert "引用" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_delete_product_type_soft_deletes_when_no_references(admin_client):
    await admin_client.post("/api/product-types", json={"code": "MOTOR", "name": "电机类"})
    resp = await admin_client.delete("/api/product-types/MOTOR")
    assert resp.status_code == 200
    resp = await admin_client.get("/api/product-types")
    motor = next(i for i in resp.json()["items"] if i["code"] == "MOTOR")
    assert motor["is_active"] is False
```

> The `viewer_user` fixture is defined in Task 2's conftest additions. It has a non-admin `RoleDefinition` so `require_admin` (`permissions.py:145`) raises 403 — no per-test permission patching needed.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_product_type_api.py -x -v`
Expected: FAIL — no `/api/product-types` route.

- [ ] **Step 4: Write the service**

`backend/app/services/product_type_service.py`:
```python
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.product_type import ProductType


async def list_product_types(db: AsyncSession, is_active: bool | None = None) -> list[ProductType]:
    query = select(ProductType).order_by(ProductType.code)
    if is_active is not None:
        query = query.where(ProductType.is_active == is_active)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_product_type(db: AsyncSession, code: str) -> ProductType | None:
    result = await db.execute(select(ProductType).where(ProductType.code == code))
    return result.scalar_one_or_none()


async def create_product_type(
    db: AsyncSession, code: str, name: str, description: str | None, operated_by: uuid.UUID
) -> ProductType:
    existing = await get_product_type(db, code)
    if existing:
        raise ValueError(f"产品类型 '{code}' 已存在")
    pt = ProductType(code=code, name=name, description=description)
    db.add(pt)
    db.add(AuditLog(
        table_name="product_types",
        record_id=uuid.uuid4(),  # string-PK table; log a generated UUID, code in changed_fields
        action="CREATE",
        changed_fields={"code": code, "name": name, "description": description},
        operated_by=operated_by,
    ))
    await db.commit()
    await db.refresh(pt)
    return pt


async def update_product_type(
    db: AsyncSession, pt: ProductType, name: str | None, description: str | None, is_active: bool | None, operated_by: uuid.UUID
) -> ProductType:
    changed: dict = {}
    if name is not None and name != pt.name:
        pt.name = name; changed["name"] = name
    if description is not None and description != pt.description:
        pt.description = description; changed["description"] = description
    if is_active is not None and is_active != pt.is_active:
        pt.is_active = is_active; changed["is_active"] = is_active
    if changed:
        db.add(AuditLog(
            table_name="product_types",
            record_id=uuid.uuid4(),
            action="UPDATE",
            changed_fields=changed,
            operated_by=operated_by,
        ))
    await db.commit()
    await db.refresh(pt)
    return pt


async def delete_product_type(db: AsyncSession, pt: ProductType, operated_by: uuid.UUID) -> None:
    # Soft-delete; refused while active product lines reference it.
    result = await db.execute(
        text("SELECT COUNT(*) FROM product_lines WHERE product_type_code = :code AND is_active = true"),
        {"code": pt.code},
    )
    if result.scalar() > 0:
        raise ValueError(f"产品类型 {pt.code} 仍被活跃产品线引用，无法停用")
    pt.is_active = False
    db.add(AuditLog(
        table_name="product_types",
        record_id=uuid.uuid4(),
        action="DEACTIVATE",
        changed_fields={"is_active": False},
        operated_by=operated_by,
    ))
    await db.commit()
```

> `AuditLog.record_id` is `UUID`; `product_types.code` is a string PK. We log a generated UUID and put the code in `changed_fields` for traceability. Audit is informational; this is acceptable.

- [ ] **Step 5: Write the API router (correct admin guard as real params)**

`backend/app/api/product_type.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope, get_request_scope
from app.core.permissions import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas import product_type as schemas
from app.services import product_type_service

router = APIRouter(prefix="/api/product-types", tags=["product-types"])


@router.get("", response_model=schemas.ProductTypeListResponse)
async def list_product_types(
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _scope: RequestScope = Depends(get_request_scope),
):
    items = await product_type_service.list_product_types(db, is_active)
    return schemas.ProductTypeListResponse(items=[schemas.ProductTypeResponse.model_validate(i) for i in items])


@router.post("", response_model=schemas.ProductTypeResponse)
async def create_product_type(
    req: schemas.ProductTypeCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _user: User = Depends(require_admin),
):
    try:
        pt = await product_type_service.create_product_type(db, req.code, req.name, req.description, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.ProductTypeResponse.model_validate(pt)


@router.put("/{code}", response_model=schemas.ProductTypeResponse)
async def update_product_type(
    code: str,
    req: schemas.ProductTypeUpdate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _user: User = Depends(require_admin),
):
    pt = await product_type_service.get_product_type(db, code)
    if not pt:
        raise HTTPException(status_code=404, detail=f"产品类型 '{code}' 不存在")
    try:
        updated = await product_type_service.update_product_type(db, pt, req.name, req.description, req.is_active, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.ProductTypeResponse.model_validate(updated)


@router.delete("/{code}")
async def delete_product_type(
    code: str,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
    _user: User = Depends(require_admin),
):
    pt = await product_type_service.get_product_type(db, code)
    if not pt:
        raise HTTPException(status_code=404, detail=f"产品类型 '{code}' 不存在")
    try:
        await product_type_service.delete_product_type(db, pt, scope.user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": f"产品类型 '{code}' 已停用"}
```

- [ ] **Step 6: Register router in main.py**

In `backend/app/main.py`, add near the product_line import (line 42):
```python
from app.api.product_type import router as product_type_router
```
And near the `product_line_router` include line (find `app.include_router(product_line_router, ...)`):
```python
app.include_router(product_type_router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_product_type_api.py -x -v`
Expected: PASS (4 tests). `viewer_user` is provided by the Task 2 conftest additions.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/product_type.py backend/app/services/product_type_service.py backend/app/api/product_type.py backend/app/main.py backend/tests/test_product_type_api.py
git commit -m "feat(product_type): CRUD service + /api/product-types router with soft-delete + audit + admin guard"
```

---

## Task 5: recommendation_scope resolver (scope + permissions → codes)

**Files:**
- Create: `backend/app/services/recommendation_scope.py`
- Test: `backend/tests/test_recommendation_scope.py`

**Interfaces:**
- Consumes: `ProductLine` model (Task 3), `RequestScope` (`app.core.deps.RequestScope`), `product_line_service.list_product_lines`.
- Produces: `async def resolve_product_line_codes(scope: str, current_product_line_code: str | None, db: AsyncSession, request_scope: RequestScope) -> list[str] | None`. Returns `None` for `global`; otherwise a (possibly empty) list = business set ∩ user-accessible product lines ∩ accessible-factory product lines.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_recommendation_scope.py`:
```python
import pytest
from app.services.recommendation_scope import resolve_product_line_codes
from app.services.product_line_service import create_product_line
from app.services.product_type_service import create_product_type


async def _seed_two_types(db, default_factory, request_scope_all):
    # Use unique codes (PT-* prefix) — admin_user fixture pre-creates DC-DC-100.
    await create_product_type(db, "POWER", "电源类", None, request_scope_all.user.user_id)
    await create_product_type(db, "MOTOR", "电机类", None, request_scope_all.user.user_id)
    await create_product_line(db, "PT-DC-100", "DC-DC 100W", factory_id=default_factory.id, product_type_code="POWER")
    await create_product_line(db, "PT-AC-200", "AC-DC 200W", factory_id=default_factory.id, product_type_code="POWER")
    await create_product_line(db, "PT-MOTOR-100", "电机 100W", factory_id=default_factory.id, product_type_code="MOTOR")


@pytest.mark.asyncio
async def test_global_returns_none(db, request_scope_all):
    assert await resolve_product_line_codes("global", "PT-DC-100", db, request_scope_all) is None


@pytest.mark.asyncio
async def test_current_product_line_returns_single(db, request_scope_all, default_factory):
    await _seed_two_types(db, default_factory, request_scope_all)
    codes = await resolve_product_line_codes("current_product_line", "PT-DC-100", db, request_scope_all)
    assert codes == ["PT-DC-100"]


@pytest.mark.asyncio
async def test_current_product_type_returns_same_type_codes(db, request_scope_all, default_factory):
    await _seed_two_types(db, default_factory, request_scope_all)
    codes = await resolve_product_line_codes("current_product_type", "PT-DC-100", db, request_scope_all)
    assert set(codes) == {"PT-DC-100", "PT-AC-200"}
    assert "PT-MOTOR-100" not in codes


@pytest.mark.asyncio
async def test_current_product_type_untyped_degrades_to_current(db, request_scope_all, default_factory):
    await create_product_line(db, "PT-UNTYPED-1", "未分类线", factory_id=default_factory.id, product_type_code=None)
    codes = await resolve_product_line_codes("current_product_type", "PT-UNTYPED-1", db, request_scope_all)
    assert codes == ["PT-UNTYPED-1"]


@pytest.mark.asyncio
async def test_current_product_type_excludes_inaccessible_factory(db, request_scope_restricted_other_factory, default_factory, request_scope_all):
    # Seed under default_factory (accessible to request_scope_all, NOT to restricted scope)
    await _seed_two_types(db, default_factory, request_scope_all)
    codes = await resolve_product_line_codes("current_product_type", "PT-DC-100", db, request_scope_restricted_other_factory)
    assert codes == []  # restricted scope can access a different factory only
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommendation_scope.py -x -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the resolver**

`backend/app/services/recommendation_scope.py`:
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import RequestScope
from app.models.product_line import ProductLine
from app.services.product_line_service import list_product_lines


async def _user_accessible_product_lines(db: AsyncSession, request_scope: RequestScope) -> list[str] | None:
    """Codes the user may see, filtered by accessible factories + pl_scope.

    Returns None if the user has unrestricted access (group admin: all factories + ALL pl_scope).
    """
    accessible = request_scope.factory_scope.accessible_factory_ids
    pl_scope = request_scope.pl_scope

    if pl_scope is not None and pl_scope.mode == "ALL" and accessible is None:
        return None  # unrestricted

    pls = await list_product_lines(db, is_active=True, accessible_factory_ids=accessible)
    codes = {pl.code for pl in pls}

    if pl_scope is not None and pl_scope.mode == "EXPLICIT":
        codes = codes & set(pl_scope.codes or [])
    if pl_scope is not None and pl_scope.mode == "NONE":
        codes = set()
    return list(codes)


async def resolve_product_line_codes(
    scope: str,
    current_product_line_code: str | None,
    db: AsyncSession,
    request_scope: RequestScope,
) -> list[str] | None:
    if scope == "global":
        return None
    if current_product_line_code is None:
        return []

    if scope == "current_product_line":
        business = {current_product_line_code}
    elif scope == "current_product_type":
        result = await db.execute(
            select(ProductLine.product_type_code).where(ProductLine.code == current_product_line_code)
        )
        pt_code = result.scalar_one_or_none()
        if not pt_code:
            business = {current_product_line_code}  # untyped → degrade
        else:
            type_result = await db.execute(
                select(ProductLine.code).where(ProductLine.product_type_code == pt_code)
            )
            business = {row[0] for row in type_result.fetchall()}
    else:
        business = {current_product_line_code}

    accessible = await _user_accessible_product_lines(db, request_scope)
    if accessible is None:
        return sorted(business)
    return sorted(business & set(accessible))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_recommendation_scope.py -x -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_scope.py backend/tests/test_recommendation_scope.py
git commit -m "feat(recommend): add recommendation_scope resolver — scope+permissions -> product_line_codes"
```

---

## Task 6: scope Literal + RecommendationService wiring + graph repo (unified signature) + /similar-nodes endpoint

**Files:**
- Modify: `backend/app/schemas/recommendation.py`
- Modify: `backend/app/graph/repository.py:37-53`
- Modify: `backend/app/graph/jsonb_repository.py:224-242`
- Modify: `backend/app/graph/neo4j_repository.py:276-295`
- Modify: `backend/app/services/recommendation_service.py:412,450-554`
- Modify: `backend/app/api/fmea.py:269-330`
- Modify: `backend/app/api/graph.py:218-270`

> **Signature is final from the start (no "write then rewrite"):** `find_similar_nodes_advanced(self, node_type, query_text, product_line_codes: list[str] | None, limit=10, min_similarity=0.3)`. `product_line_codes is None` = global (no filter). The `scope: str` parameter is removed from the repo entirely; callers resolve scope → codes via `resolve_product_line_codes` and pass codes.

**Interfaces:**
- Consumes: `resolve_product_line_codes` (Task 5), `RequestScope` (deps).
- Produces: 3-value `scope` Literal in `RecommendRequest`/`RecommendResponse`/`SimilarNodesRequest`/`SimilarNodesResponse`; `RecommendationService.recommend(fmea_id, request, user, request_scope)`; `find_similar_nodes_advanced(..., product_line_codes, ...)` on all three repo classes; `/similar-nodes` endpoint uses the resolver.

- [ ] **Step 1: Extend scope Literals**

In `backend/app/schemas/recommendation.py`:
```python
class RecommendRequest(BaseModel):
    trigger_type: Literal[...]
    context: dict = Field(default_factory=dict)
    scope: Literal["global", "current_product_type", "current_product_line"] = "global"
    include_graph: bool = True
```
```python
class RecommendResponse(BaseModel):
    ...
    effective_scope: Literal["global", "current_product_type", "current_product_line"] = "global"
```
And `SimilarNodesRequest`:
```python
class SimilarNodesRequest(BaseModel):
    node_type: str
    query_text: str
    scope: Literal["global", "current_product_type", "current_product_line"] = "global"
    product_line_code: str | None = None   # now optional; codes resolved server-side
    limit: int = Field(10, ge=1, le=100)
    min_similarity: float = Field(0.3, ge=0.0, le=1.0)
```
And `SimilarNodesResponse.effective_scope`:
```python
    effective_scope: Literal["global", "current_product_type", "current_product_line"] = "global"
```

- [ ] **Step 2: Update abstract graph repo (final signature)**

In `backend/app/graph/repository.py:37`, replace the method signature (remove `scope: str`, replace `product_line_code: str | None` with `product_line_codes: list[str] | None`):
```python
    @abstractmethod
    async def find_similar_nodes_advanced(
        self,
        node_type: str,
        query_text: str,
        product_line_codes: list[str] | None,
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict]:
        """跨 FMEA 相似节点搜索（增强版）。

        product_line_codes: None = global (no filter); a list = restrict to those codes.
        返回项包含 node_id, name, type, fmea_id, document_no, product_line_code,
        product_line_name, similarity_score, match_reason.
        """
```

- [ ] **Step 3: Update JSONB impl**

In `backend/app/graph/jsonb_repository.py:224`, change signature to `(self, node_type, query_text, product_line_codes: list[str] | None, limit=10, min_similarity=0.3)` and the filter (replace the `if scope == "current_product_line" and product_line_code:` block at 239-240):
```python
        if product_line_codes is not None:
            query = query.where(FMEADocument.product_line_code.in_(product_line_codes))
```

- [ ] **Step 4: Update Neo4j impl**

In `backend/app/graph/neo4j_repository.py:276`, change signature to `(self, node_type, query_text, product_line_codes: list[str] | None, limit=10, min_similarity=0.3)` and the filter (replace the `if scope == "current_product_line" and product_line_code:` block at 291-293):
```python
            if product_line_codes is not None:
                cypher += " AND n.product_line_code IN $codes"
                params["codes"] = product_line_codes
```

- [ ] **Step 5: Update the test stub in recommendation_service.py**

`backend/app/services/recommendation_service.py:47` has a stub `find_similar_nodes_advanced(self, *a, **kw): return []`. `*a, **kw` absorbs the new signature — no change needed. Verify by reading the line; if it's a class used as a fake repo in tests, leave it.

- [ ] **Step 6: Wire RecommendationService to use the resolver**

In `backend/app/services/recommendation_service.py`:
- Change `recommend` signature (line 412) to:
```python
    async def recommend(self, fmea_id: _uuid.UUID, request: RecommendRequest, user: User, request_scope: RequestScope) -> RecommendResponse:
```
- After `effective_scope` is resolved (lines 418-420), add codes resolution:
```python
        from app.services.recommendation_scope import resolve_product_line_codes
        product_line_codes = await resolve_product_line_codes(effective_scope, fmea.product_line_code, self.db, request_scope)
```
- Change `_query_graph_similarity` (line 514) signature from `(self, fmea, trigger_type, context, scope: str)` to `(self, fmea, trigger_type, context, product_line_codes: list[str] | None)` and update the repo call (line 526) to:
```python
        fm_matches = await self.graph_repo.find_similar_nodes_advanced(
            node_type="FailureMode",
            query_text=query_text,
            product_line_codes=product_line_codes,
            limit=20,
            min_similarity=0.3,
        )
```
- Update the call site in `recommend` (lines 450-451) to pass `product_line_codes` instead of `effective_scope`:
```python
                graph_matches = await self._query_graph_similarity(fmea, request.trigger_type, request.context, product_line_codes)
```

- [ ] **Step 7: Pass request_scope from the FMEA API**

In `backend/app/api/fmea.py` recommend endpoint (line 269+), find the `.recommend(` invocation (around line 325) and change to pass `scope` (the RequestScope dependency injected at line 274) as the 4th arg:
```python
        result = await service.recommend(fmea_id, request, scope.user, scope)
```

- [ ] **Step 8: Update /similar-nodes debug endpoint**

In `backend/app/api/graph.py:218`, the endpoint currently calls `repo.find_similar_nodes_advanced(scope=effective_scope, product_line_code=req.product_line_code, ...)`. Replace the resolution + call (lines 234-245) with the resolver:
```python
    from app.services.recommendation_scope import resolve_product_line_codes
    # scope downgrade for no-KG users stays (existing behavior), then resolve codes.
    has_kg = await get_user_permission(scope.user, Module.KNOWLEDGE_GRAPH, db) >= PermissionLevel.VIEW
    effective_scope = "current_product_line" if (not has_kg and req.scope in ("global", "current_product_type")) else req.scope
    codes = await resolve_product_line_codes(effective_scope, req.product_line_code, db, scope)

    matches = await repo.find_similar_nodes_advanced(
        node_type=req.node_type,
        query_text=req.query_text,
        product_line_codes=codes,
        limit=req.limit,
        min_similarity=req.min_similarity,
    )
```
Keep the defensive masking block (lines 247-264) unchanged. The `current_pl = req.product_line_code` line stays; when `req.product_line_code` is None (global), mask cross-PL names for no-KG users — but since `effective_scope` downgrades to `current_product_line` for no-KG users, `codes` will be a single-PL list (or `None` only when `current_product_line_code` is None AND scope is global AND has_kg). Add a guard:
```python
    current_pl = req.product_line_code
```
(no change needed; downstream `m.get("product_line_code") != current_pl` works when `current_pl` is None too — then no masking triggers, which is fine for has_kg users).

- [ ] **Step 9: Write a service-layer recommend test**

`backend/tests/test_fmea_recommend_scope.py` — test at the service layer with a mocked graph_repo so the cross-PL recall is deterministic:
```python
import pytest
from unittest.mock import AsyncMock
from app.services.recommendation_service import RecommendationService


@pytest.mark.asyncio
async def test_recommend_current_product_type_passes_sibling_codes(db, default_factory, admin_user, request_scope_all):
    # Seed two unique product lines under POWER; create an FMEA in PT-DC-100.
    # (Use PT-* codes — admin_user fixture pre-creates DC-DC-100.)
    await create_product_type(db, "POWER", "电源类", None, admin_user.user_id)
    await create_product_line(db, "PT-DC-100", "DC-DC 100W", factory_id=default_factory.id, product_type_code="POWER")
    await create_product_line(db, "PT-AC-200", "AC-DC 200W", factory_id=default_factory.id, product_type_code="POWER")
    fmea = FMEADocument(fmea_id=uuid.uuid4(), document_no="PFMEA-PT-1", title="PT test", fmea_type="PFMEA",
                        product_line_code="PT-DC-100", status="draft", version=1, graph_data={"nodes": [], "edges": []},
                        lock_version=1, factory_id=default_factory.id, created_by=admin_user.user_id)
    db.add(fmea); await db.commit()

    captured: dict = {}
    fake_repo = AsyncMock()
    async def _capture(**kwargs):
        captured.update(kwargs); return []
    fake_repo.find_similar_nodes_advanced = _capture

    service = RecommendationService(db, llm_provider=None, graph_repo=fake_repo)
    req = RecommendRequest(trigger_type="failure_mode", context={"function_description": "test"}, scope="current_product_type")
    await service.recommend(fmea.fmea_id, req, admin_user, request_scope_all)
    assert set(captured["product_line_codes"]) == {"PT-DC-100", "PT-AC-200"}
```
(Imports needed in the test file: `uuid`, `from app.models.fmea import FMEADocument`, `from app.schemas.recommendation import RecommendRequest`, `from app.services.recommendation_service import RecommendationService`, `from app.services.product_line_service import create_product_line`, `from app.services.product_type_service import create_product_type`. Verify the `FMEADocument` required fields against `backend/app/models/fmea.py` before finalizing the insert.)

- [ ] **Step 10: Run tests**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -x -k "recommend or product_type or recommendation_scope or product_line or graph" -v`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add backend/app/schemas/recommendation.py backend/app/graph/repository.py backend/app/graph/jsonb_repository.py backend/app/graph/neo4j_repository.py backend/app/services/recommendation_service.py backend/app/api/fmea.py backend/app/api/graph.py backend/tests/test_fmea_recommend_scope.py
git commit -m "feat(recommend): 3-value scope, resolver wiring, unified graph repo codes-based filtering, /similar-nodes endpoint"
```

---

## Task 7: Semantic search + QA product_type_code filter

**Files:**
- Modify: `backend/app/services/search_service.py:47-75,172-185`
- Modify: `backend/app/schemas/search.py:40-44`
- Modify: `backend/app/api/search.py:28-76`
- Test: `backend/tests/test_search_product_type.py`

> **Uses `self.db`, not `db`.** `SearchService.semantic_search` is a method; the session is `self.db`.

- [ ] **Step 1: Write failing test**

`backend/tests/test_search_product_type.py`:
```python
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_semantic_search_filters_by_product_type(monkeypatch):
    # Mock the vector+fulltext search to return rows tagged with product_line_code,
    # then assert the service excludes rows whose product_line_code is NOT under the POWER type.
    # (Full embedding setup is heavy; test the filter logic at the service layer.)
    ...
```
(Write a focused service-layer test: construct a `SearchService` with a mocked `self.db` whose `execute` returns rows for `PT-DC-100`, `PT-AC-200`, and `PT-MOTOR-100`; call `semantic_search(query, user, product_type_code="POWER")`; assert only the two POWER rows survive. If `SearchService` construction needs a real `db`, use the `db` fixture and seed `ProductLine` rows (unique PT-* codes) + mock the pgvector query path.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_search_product_type.py -x -v`
Expected: FAIL — `product_type_code` param not accepted.

- [ ] **Step 3: Add product_type_code to semantic_search (uses self.db)**

In `backend/app/services/search_service.py`, add `product_type_code: str | None = None` to `semantic_search` (line 47). After the existing `product_line_code` block (lines 65-73), add type resolution using **`self.db`**:
```python
        if product_type_code and not product_line_code:
            from app.models.product_line import ProductLine
            from sqlalchemy import select
            type_pls = await self.db.execute(
                select(ProductLine.code).where(ProductLine.product_type_code == product_type_code)
            )
            codes = [r[0] for r in type_pls.fetchall()]
            if codes:
                filters.append("product_line_code = ANY(:product_type_codes)")
                params["product_type_codes"] = codes
            else:
                filters.append("1 = 0")
```

- [ ] **Step 4: Add to ask()**

In `ask()` (line 172), add `product_type_code: str | None = None` param and forward at line 185:
```python
            product_type_code=product_type_code,
```

- [ ] **Step 5: Update QARequest schema**

In `backend/app/schemas/search.py`:
```python
class QARequest(BaseModel):
    ...
    product_line_code: str | None = None
    product_type_code: str | None = None
```

- [ ] **Step 6: Update API endpoints**

In `backend/app/api/search.py`:
- `/semantic` (line 29): add `product_type_code: str | None = Query(None),` and pass `product_type_code=product_type_code` to the service (line 46).
- `/ask` (line 53): pass `body.product_type_code` to `ask(...)` (line 72).

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/test_search_product_type.py -x -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/search_service.py backend/app/schemas/search.py backend/app/api/search.py backend/tests/test_search_product_type.py
git commit -m "feat(search): product_type_code filter on semantic search + QA (self.db)"
```

---

## Task 8: Seed product types + assign existing product lines

**Files:**
- Modify: `backend/app/seed.py:1770-1780` (and the second product-line seed block at 1971-1980)

- [ ] **Step 1: Add product type seeding before product lines**

In `backend/app/seed.py` before the `# Product lines` block (line 1770), insert:
```python
        # Product types (cross-factory taxonomy)
        from app.models.product_type import ProductType
        pt_data = [
            {"code": "POWER", "name": "电源类", "description": "电源模块/电源线", "is_active": True},
            {"code": "PCB", "name": "PCB 类", "description": "印制电路板/贴片线", "is_active": True},
        ]
        for pt_dict in pt_data:
            existing = await db.execute(select(ProductType).where(ProductType.code == pt_dict["code"]))
            if not existing.scalar_one_or_none():
                db.add(ProductType(**pt_dict))
        await db.flush()
```
Then update `pl_data` to include `product_type_code`:
```python
        pl_data = [
            {"code": "DC-DC-100", "name": "DC-DC 100W 电源模块", "product_type_code": "POWER"},
            {"code": "PCB-SMT-200", "name": "PCB SMT 200 贴片线", "product_type_code": "PCB"},
        ]
```

- [ ] **Step 2: Repeat for the second product-line seed block (line 1971-1980)**

Inspect that block; if it seeds product lines, add `product_type_code` consistently so every seeded product line is typed.

- [ ] **Step 3: Verify seed imports/runs**

Run: `cd backend && python -c "import app.seed"` (and `python -m app.seed` against a fresh DB if available)
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/seed.py
git commit -m "feat(seed): seed POWER/PCB product types, assign DC-DC-100 + PCB-SMT-200"
```

---

## Task 9: Frontend types + API clients

**Files:**
- Modify: `frontend/src/types/index.ts:466-472`, add `ProductType`
- Modify: `frontend/src/api/productLine.ts`
- Create: `frontend/src/api/productType.ts`
- Modify: `frontend/src/api/recommendation.ts:18-32`
- Modify: `frontend/src/api/search.ts`

- [ ] **Step 1: Add ProductType type + extend ProductLine**

In `frontend/src/types/index.ts`:
```typescript
export interface ProductType {
  code: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductLine {
  code: string;
  name: string;
  is_active: boolean;
  product_type_code: string | null;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Extend productLine API client**

In `frontend/src/api/productLine.ts`:
```typescript
export async function createProductLine(data: { code: string; name: string; product_type_code?: string | null }): Promise<ProductLine> {
  const resp = await client.post("/product-lines", data);
  return resp.data;
}

export async function updateProductLine(code: string, data: { name?: string; is_active?: boolean; product_type_code?: string | null }): Promise<ProductLine> {
  const resp = await client.put(`/product-lines/${code}`, data);
  return resp.data;
}
```

- [ ] **Step 3: Create productType API client**

`frontend/src/api/productType.ts`:
```typescript
import client from "./client";
import type { ProductType } from "../types";

export async function listProductTypes(isActive?: boolean): Promise<ProductType[]> {
  const params: Record<string, unknown> = {};
  if (isActive !== undefined) params.is_active = isActive;
  const resp = await client.get("/product-types", { params });
  return resp.data.items;
}

export async function createProductType(data: { code: string; name: string; description?: string | null }): Promise<ProductType> {
  const resp = await client.post("/product-types", data);
  return resp.data;
}

export async function updateProductType(code: string, data: { name?: string; description?: string | null; is_active?: boolean }): Promise<ProductType> {
  const resp = await client.put(`/product-types/${code}`, data);
  return resp.data;
}

export async function deleteProductType(code: string): Promise<void> {
  await client.delete(`/product-types/${code}`);
}
```

- [ ] **Step 4: Extend recommendation scope union**

In `frontend/src/api/recommendation.ts`:
```typescript
export interface RecommendRequest {
  trigger_type: string;
  context: Record<string, unknown>;
  scope?: "global" | "current_product_type" | "current_product_line";
  include_graph?: boolean;
}

export interface RecommendResponse {
  suggestions: Suggestion[];
  source: "rule" | "graph" | "hybrid" | "rule_fallback" | "graph_enriched";
  cached: boolean;
  llm_available: boolean;
  graph_match_count: number;
  effective_scope: "global" | "current_product_type" | "current_product_line";
}
```

- [ ] **Step 5: Extend search API params**

In `frontend/src/api/search.ts`, add `product_type_code?: string` to the semantic search params interface and the `askQuestion` request body type, alongside `product_line_code`.

- [ ] **Step 6: Verify build**

Run: `cd frontend && npm install && npm run build`
Expected: tsc --noEmit passes.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/productLine.ts frontend/src/api/productType.ts frontend/src/api/recommendation.ts frontend/src/api/search.ts
git commit -m "feat(frontend): ProductType types + API clients, scope union, search product_type_code"
```

---

## Task 10: Admin pages (ProductType + ProductLine) + routes + menu

**Files:**
- Create: `frontend/src/pages/admin/ProductTypePage.tsx`
- Create: `frontend/src/pages/admin/ProductLinePage.tsx`
- Create: `frontend/src/locales/zh-CN/productType.json`, `frontend/src/locales/en-US/productType.json`
- Modify: `frontend/src/App.tsx:80,219`
- Modify: `frontend/src/components/layout/AppLayout.tsx:267`
- Modify: `frontend/src/locales/zh-CN/layout.json` + `en-US/layout.json`
- Test: `frontend/src/pages/admin/ProductTypePage.test.tsx`

- [ ] **Step 1: Write i18n files**

`frontend/src/locales/zh-CN/productType.json`:
```json
{
  "title": "产品类型管理",
  "fields": { "code": "类型代码", "name": "类型名称", "description": "描述", "is_active": "启用" },
  "actions": { "create": "新建类型", "edit": "编辑", "delete": "停用", "cancel": "取消", "save": "保存" },
  "messages": {
    "created": "产品类型已创建",
    "updated": "产品类型已更新",
    "deactivated": "产品类型已停用",
    "deleteConfirm": "确定停用该产品类型？",
    "refused": "无法停用：{{detail}}"
  },
  "productLine": {
    "title": "产品线管理",
    "fields": { "product_type_code": "产品类型" },
    "assignType": "分配产品类型"
  }
}
```
`frontend/src/locales/en-US/productType.json`: mirror in English.

- [ ] **Step 2: Write ProductTypePage (final, compiles)**

`frontend/src/pages/admin/ProductTypePage.tsx`:
```tsx
import { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Tag, Space, App } from "antd";
import { useTranslation } from "react-i18next";
import { PlusOutlined } from "@ant-design/icons";
import { PageShell } from "../../components/design";
import { listProductTypes, createProductType, updateProductType, deleteProductType } from "../../api/productType";
import type { ProductType } from "../../types";

export default function ProductTypePage() {
  const { t } = useTranslation("productType");
  const { message, modal } = App.useApp();
  const [rows, setRows] = useState<ProductType[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ProductType | null>(null);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try { setRows(await listProductTypes()); } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const onSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) { await updateProductType(editing.code, values); message.success(t("messages.updated")); }
      else { await createProductType(values); message.success(t("messages.created")); }
      setOpen(false); form.resetFields(); await load();
    } catch (e: any) { message.error(e?.response?.data?.detail || "error"); }
  };

  const onDeactivate = (row: ProductType) => {
    modal.confirm({
      title: t("messages.deleteConfirm"),
      onOk: async () => {
        try { await deleteProductType(row.code); message.success(t("messages.deactivated")); await load(); }
        catch (e: any) { message.error(t("messages.refused", { detail: e?.response?.data?.detail || "" })); }
      },
    });
  };

  const columns = [
    { title: t("fields.code"), dataIndex: "code" },
    { title: t("fields.name"), dataIndex: "name" },
    { title: t("fields.description"), dataIndex: "description" },
    { title: t("fields.is_active"), dataIndex: "is_active", render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "ON" : "OFF"}</Tag> },
    { title: "", render: (_: unknown, row: ProductType) => (
      <Space>
        <Button size="small" onClick={() => { setEditing(row); form.setFieldsValue(row); setOpen(true); }}>{t("actions.edit")}</Button>
        <Button size="small" danger onClick={() => onDeactivate(row)}>{t("actions.delete")}</Button>
      </Space>
    ) },
  ];

  return (
    <PageShell title={t("title")} extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>{t("actions.create")}</Button>}>
      <Table rowKey="code" dataSource={rows} columns={columns} loading={loading} />
      <Modal open={open} title={editing ? t("actions.edit") : t("actions.create")} onCancel={() => setOpen(false)} onOk={onSubmit}>
        <Form form={form} layout="vertical">
          <Form.Item name="code" label={t("fields.code")} rules={[{ required: true }]}><Input disabled={!!editing} /></Form.Item>
          <Form.Item name="name" label={t("fields.name")} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label={t("fields.description")}><Input.TextArea /></Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
```

- [ ] **Step 3: Write ProductLinePage**

`frontend/src/pages/admin/ProductLinePage.tsx` — same structure; columns: code, name, product type (render product type name via a lookup built from `listProductTypes()`), is_active, actions. Edit modal includes a `Select` for `product_type_code` (options from `listProductTypes()`, allowClear to support clearing to null). Use `updateProductLine(code, { product_type_code: values.product_type_code ?? null })`.

- [ ] **Step 4: Add routes**

In `frontend/src/App.tsx`, add lazy imports near line 80:
```tsx
const ProductTypePage = lazy(() => import("./pages/admin/ProductTypePage"));
const ProductLinePage = lazy(() => import("./pages/admin/ProductLinePage"));
```
Add routes near line 219:
```tsx
        <Route path="/admin/product-types" element={<ProtectedRoute requireAdmin><ProductTypePage /></ProtectedRoute>} />
        <Route path="/admin/product-lines" element={<ProtectedRoute requireAdmin><ProductLinePage /></ProtectedRoute>} />
```

- [ ] **Step 5: Add menu items**

In `frontend/src/components/layout/AppLayout.tsx` after the `ai-config` entry (line 267):
```tsx
          { key: "/admin/product-types", icon: <AppstoreOutlined />, label: t("menu.productTypes"), adminOnly: true },
          { key: "/admin/product-lines", icon: <ProfileOutlined />, label: t("menu.productLines"), adminOnly: true },
```
Add `AppstoreOutlined, ProfileOutlined` to the `@ant-design/icons` import.

- [ ] **Step 6: Add menu i18n keys**

In `frontend/src/locales/zh-CN/layout.json` `menu` block (after `aiConfig`):
```json
    "productTypes": "产品类型管理",
    "productLines": "产品线管理",
```
In `en-US/layout.json`:
```json
    "productTypes": "Product Types",
    "productLines": "Product Lines",
```

- [ ] **Step 7: Write component test**

`frontend/src/pages/admin/ProductTypePage.test.tsx`:
```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "antd";
import ProductTypePage from "./ProductTypePage";

vi.mock("../../api/productType", () => ({
  listProductTypes: vi.fn().mockResolvedValue([{ code: "POWER", name: "电源类", description: null, is_active: true, created_at: "", updated_at: "" }]),
  createProductType: vi.fn().mockResolvedValue({}),
  updateProductType: vi.fn(),
  deleteProductType: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe("ProductTypePage", () => {
  it("lists existing product types", async () => {
    render(<App><MemoryRouter><ProductTypePage /></MemoryRouter></App>);
    await waitFor(() => expect(screen.getByText("POWER")).toBeInTheDocument());
  });
});
```

- [ ] **Step 8: Run build + test**

Run: `cd frontend && npm run build && npx vitest run src/pages/admin/ProductTypePage.test.tsx`
Expected: pass.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/admin/ProductTypePage.tsx frontend/src/pages/admin/ProductLinePage.tsx frontend/src/locales/zh-CN/productType.json frontend/src/locales/en-US/productType.json frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx frontend/src/locales/zh-CN/layout.json frontend/src/locales/en-US/layout.json frontend/src/pages/admin/ProductTypePage.test.tsx
git commit -m "feat(frontend): product type + product line admin pages, routes, menu, i18n"
```

---

## Task 11: FMEA recommend scope selector + SemanticSearchTab type filter

**Files:**
- Modify: `frontend/src/components/dfmea/SmartSuggestionDropdown.tsx`
- Modify: `frontend/src/components/dfmea/InlineRecommendations.tsx`
- Modify: `frontend/src/pages/graph/SemanticSearchTab.tsx`
- Modify: `frontend/src/locales/zh-CN/dfmea.json` + `en-US/dfmea.json`
- Modify: `frontend/src/locales/zh-CN/search.json` + `en-US/search.json`

- [ ] **Step 1: Add scope selector to recommend trigger**

In `SmartSuggestionDropdown.tsx` (and/or `InlineRecommendations.tsx`), add a `Select` for scope next to the AI trigger, defaulting to `"current_product_type"`, with options: 同类产品 (`current_product_type`), 当前产品线 (`current_product_line`), 全局 (`global`). Pass `scope` through to `getRecommendations`.

- [ ] **Step 2: Add product type filter to SemanticSearchTab**

In `frontend/src/pages/graph/SemanticSearchTab.tsx`, add a `productType` state + `Select` (options from `listProductTypes()`). When a type is selected, filter the product-line `Select` options to product lines under that type (fetch via `listProductLines()` and client-filter by `product_type_code`). Pass `product_type_code` to both `semanticSearch` and `askQuestion` (both branches of the existing `handleSearch`).

- [ ] **Step 3: Add i18n keys**

In `dfmea.json` (zh-CN + en-US):
```json
"scope": { "currentProductType": "同类产品", "currentProductLine": "当前产品线", "global": "全局" }
```
In `search.json` (zh-CN + en-US): `"productType": "产品类型"` filter label.

- [ ] **Step 4: Write a vitest for the scope selector**

`frontend/src/components/dfmea/SmartSuggestionDropdown.test.tsx` — assert the three scope options render and the selected value is sent in the request (mock `getRecommendations`).

- [ ] **Step 5: Run build + tests**

Run: `cd frontend && npm run build && npx vitest run src/components/dfmea/SmartSuggestionDropdown.test.tsx`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dfmea/SmartSuggestionDropdown.tsx frontend/src/components/dfmea/InlineRecommendations.tsx frontend/src/pages/graph/SemanticSearchTab.tsx frontend/src/locales/zh-CN/dfmea.json frontend/src/locales/en-US/dfmea.json frontend/src/locales/zh-CN/search.json frontend/src/locales/en-US/search.json frontend/src/components/dfmea/SmartSuggestionDropdown.test.tsx
git commit -m "feat(frontend): 3-value recommend scope selector + semantic search product type filter"
```

---

## Task 12: Full verification + regression sweep

- [ ] **Step 1: Backend full test run**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -x --tb=short`
Expected: all pass. If an existing recommendation/search/graph test breaks because a fixture lacks `product_type_code` or uses the old 2-value `scope` Literal / old `find_similar_nodes_advanced(scope=..., product_line_code=...)` call, update the fixture (add `product_type_code=None`) and the call site to the new signature.

- [ ] **Step 2: Frontend full build + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: 0 errors.

- [ ] **Step 3: Frontend full vitest**

Run: `cd frontend && npx vitest run`
Expected: all pass.

- [ ] **Step 4: Migration round-trip (if DB available)**

Run: `cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
Expected: no errors; `product_types` table exists, `product_lines.product_type_code` exists.

- [ ] **Step 5: Manual smoke (optional, if app runnable)**

Run app, log in as admin, open `/admin/product-types`, create a type, assign a product line, open an FMEA editor, trigger AI recommend with each of the 3 scope values, confirm results differ. Open semantic search, filter by product type.

- [ ] **Step 6: Commit any test/fixture fixes from Step 1**

```bash
git add -A
git commit -m "test: regression fixes for product_type scope rollout"
```

---

## Self-Review Notes

**Spec coverage:**
- §1 Data model → Task 1 (table + FK), Task 3 (product_line column/schema/service/api).
- §2 Migration & backfill → Task 1 (migration + downgrade), Task 8 (seed = the only backfill; no embedding backfill).
- §3 Recommendation scope + permissions → Task 5 (resolver), Task 6 (wire into service + graph repo + /similar-nodes + scope Literal + request_scope threading). 8D explicitly untouched (no task touches `recommendation_types.py` / `recommendation_sources.py` / `api/capa.py`). Semantic search/QA → Task 7.
- §4 Frontend → Task 9 (types/API), Task 10 (admin pages + routes + menu + i18n), Task 11 (scope selector + search filter).
- §5 Tests → each task carries its own TDD test; Task 2 shared fixtures (moved before the tests that need them); Task 12 full regression.

**Placeholder scan:** No "write then rewrite" passages remain — the graph repo signature is final from Step 2 of Task 6. No known-bad code blocks — the admin guard in Task 4 Step 5 is a real FastAPI dependency (`_user: User = Depends(require_admin)` as a function parameter). `self.db` used in SearchService (Task 7 Step 3). ProductTypePage uses `onOk={onSubmit}` and imports `ProductType` (Task 10 Step 2). No `assert status in (200, 403)` placeholder — the 403 test uses a real `viewer_user` fixture (non-admin role) so `require_admin` raises 403 deterministically.

**Test fixture hygiene:** New fixtures use `@pytest_asyncio.fixture` (matching existing conftest at lines 108/129). `admin_client` overrides `get_current_user` + `get_db` + `get_request_scope` (all three, so `require_admin` resolves). `viewer_user` is a real non-admin fixture; no misleading `viewer_client` fixture. All test-created product lines use unique `PT-*` codes to avoid colliding with the `admin_user` fixture's idempotent `DC-DC-100` pre-seed (conftest.py:136-146); tests that need to type the existing `DC-DC-100` use `update_product_line`, not `create_product_line`.

**Type consistency:** `resolve_product_line_codes(scope, current_product_line_code, db, request_scope)` used consistently in Task 5 (impl) and Task 6 (call sites: RecommendationService + /similar-nodes). `find_similar_nodes_advanced(node_type, query_text, product_line_codes, limit, min_similarity)` unified across abstract/JSONB/Neo4j and both callers (recommendation_service.py, api/graph.py). `RecommendRequest.scope` / `effective_scope` 3-value Literal consistent across Task 6 (backend) and Task 9 (frontend). `ProductLine.product_type_code` and the `UNSET` sentinel consistent across Task 3 service + API + tests.