# Product Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a cross-factory "product type" taxonomy as the parent of product lines, and add a `current_product_type` recommendation scope so FMEA recommendations and semantic search can recall history across all product lines of the same type.

**Architecture:** New `product_types` master-data table (cross-factory, no `factory_id`) with `product_lines.product_type_code` FK. A new `recommendation_scope.py` module resolves any scope + current product line + `RequestScope` into a `product_line_codes` set (business scope ∩ user-accessible product lines ∩ accessible-factory product lines). FMEA recommendation + graph similarity + semantic search/QA consume that set; embedding writes are untouched (no vector backfill). 8D pipeline is explicitly left unchanged.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 async + Alembic (PostgreSQL 15) | React 18 + TypeScript 5.6 + Ant Design 5.29 + i18next (zh-CN/en-US)

## Global Constraints

- Chinese UI, bilingual zh-CN/en-US i18n throughout (menu, fields, messages).
- Document numbering / codes: uppercase `^[A-Z0-9_-]+$`, max 20 chars (matches `ProductLineCreate.code`).
- PKs: UUID v4 generated in Python for audit rows; `product_types.code` is a string PK (matches `product_lines.code`).
- Every CRUD operation manually creates an `AuditLog` in its service method (model: `app.models.audit.AuditLog`, fields `table_name/record_id/action/changed_fields/operated_by`).
- `factory_id` is NOT NULL on all business tables; `product_types` is the exception — cross-factory, no `factory_id`.
- Services raise `ValueError`; API layer converts to `HTTPException`.
- List endpoints return `{ items, total, page, page_size }` where applicable; product_type list returns `{ items }` (matches `ProductLineListResponse`).
- FMEA graph: `find_similar_nodes_advanced` lives on abstract `FMEAGraphRepository` (`graph/repository.py:37`) with two impls — JSONB (`graph/jsonb_repository.py:224`) and Neo4j (`graph/neo4j_repository.py:276`); both must stay signature-compatible.
- Backend tests: `pytest tests/ -x`; frontend: `npm run build` (tsc --noEmit + vite build), `npm run lint`, `vitest` for component tests. Worktree-local run: backend tests via main checkout's `backend/.venv` with `SECRET_KEY=test-secret-key`; `npm install` needed in worktree frontend before first build/test.
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
- `backend/app/schemas/product_line.py` — add `product_type_code` to create/update/response.
- `backend/app/services/product_line_service.py` — `create_product_line`/`update_product_line` accept `product_type_code`.
- `backend/app/api/product_line.py` — pass `product_type_code` through.
- `backend/app/schemas/recommendation.py` — extend `scope` Literal to 3 values; `effective_scope` Literal; `SimilarNodesRequest.scope`/`SimilarNodesResponse.effective_scope`.
- `backend/app/services/recommendation_service.py` — `recommend()` accepts `request_scope`; use `resolve_product_line_codes`; pass codes to graph repo.
- `backend/app/graph/repository.py` — abstract `find_similar_nodes_advanced` signature: `product_line_codes: list[str] | None`.
- `backend/app/graph/jsonb_repository.py` — impl uses `FMEADocument.product_line_code.in_(codes)`.
- `backend/app/graph/neo4j_repository.py` — impl uses `n.product_line_code IN $codes` Cypher.
- `backend/app/api/fmea.py` — pass `scope` (RequestScope) into `RecommendationService.recommend`.
- `backend/app/api/graph.py` — debug similar-nodes endpoint: pass codes; update response Literal.
- `backend/app/services/search_service.py` — `semantic_search` + `ask` accept `product_type_code`, resolve to codes.
- `backend/app/schemas/search.py` — `QARequest` add `product_type_code`.
- `backend/app/api/search.py` — `/semantic` GET query param `product_type_code`; `/ask` passes it.
- `backend/app/main.py` — register `product_type_router`.
- `backend/app/seed.py` — seed `POWER` type, assign `DC-DC-100` + `PCB-SMT-200` to it.

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

**New test files:**
- `backend/tests/test_product_type_api.py` — product type CRUD + permissions + soft-delete.
- `backend/tests/test_recommendation_scope.py` — `resolve_product_line_codes` 4 cases + permission intersection.
- `frontend/src/pages/admin/ProductTypePage.test.tsx`, `ProductLinePage.test.tsx` — CRUD interactions.

**Modified test files:**
- `backend/tests/test_product_line_api.py` (if exists) or new — type field create/update.
- Existing recommendation/search tests — fixtures add `product_type_code` / scope Literal.

---

## Task 1: ProductType ORM model + migration

**Files:**
- Create: `backend/app/models/product_type.py`
- Create: `backend/alembic/versions/<rev>_add_product_types.py`
- Modify: `backend/app/models/__init__.py` (export `ProductType` if models are aggregated there)

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

Find the current head revision:
Run: `cd backend && alembic heads` (note the head revision id, e.g. `bfd90bb593fc`)

Create `backend/alembic/versions/<new_rev_id>_add_product_types.py` (use `down_revision = "<current head>"`):
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
    op.add_column(
        "product_lines",
        sa.Column("product_type_code", sa.String(20), nullable=True),
    )
    op.create_foreign_key(
        "fk_product_lines_product_type",
        "product_lines",
        "product_types",
        ["product_type_code"],
        ["code"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_product_lines_product_type", "product_lines", type_="foreignkey")
    op.drop_column("product_lines", "product_type_code")
    op.drop_table("product_types")
```

- [ ] **Step 4: Verify migration applies (if a DB is available)**

Run: `cd backend && alembic upgrade head`
Expected: no errors. (If no DB in worktree, skip — note in commit message; CI/main will run it.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/product_type.py backend/alembic/versions/<new_rev_id>_add_product_types.py
git commit -m "feat(product_type): add ProductType model + migration with product_lines.product_type_code FK"
```

---

## Task 2: ProductLine model + schema + service + API carry product_type_code

**Files:**
- Modify: `backend/app/models/product_line.py` (add column)
- Modify: `backend/app/schemas/product_line.py`
- Modify: `backend/app/services/product_line_service.py:28-46` (create/update accept `product_type_code`)
- Modify: `backend/app/api/product_line.py:30-63`

**Interfaces:**
- Consumes: `ProductType` from Task 1 (FK target).
- Produces: `ProductLineCreate.product_type_code: str | None`, `ProductLineResponse.product_type_code: str | None`; service `create_product_line(..., product_type_code=None)`, `update_product_line(..., product_type_code=...)`.

- [ ] **Step 1: Write failing test for product_line create with type field**

`backend/tests/test_product_line_type_field.py`:
```python
import pytest
from app.services.product_line_service import create_product_line, get_product_line


@pytest.mark.asyncio
async def test_create_product_line_with_type(db_session, default_factory_id, product_type_power):
    pl = await create_product_line(
        db_session, code="DC-DC-100", name="DC-DC 100W", factory_id=default_factory_id, product_type_code="POWER"
    )
    assert pl.product_type_code == "POWER"
    fetched = await get_product_line(db_session, "DC-DC-100")
    assert fetched.product_type_code == "POWER"
```

(`db_session`, `default_factory_id`, `product_type_power` fixtures: see Task 5 for the shared fixture file. For this task, define a minimal local `product_type_power` fixture that inserts a `ProductType(code="POWER", name="电源类")` row; Task 5 consolidates fixtures.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_product_line_type_field.py -x -v`
Expected: FAIL — `product_type_code` not a parameter / attribute.

- [ ] **Step 3: Add column to ProductLine model**

In `backend/app/models/product_line.py`, add inside the class (after `factory_id`):
```python
    product_type_code: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("product_types.code", ondelete="RESTRICT"), nullable=True
    )
```
Add `ForeignKey` to the existing `from sqlalchemy import ...` import line.

- [ ] **Step 4: Update schemas**

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

- [ ] **Step 5: Update service signatures**

In `backend/app/services/product_line_service.py`:
```python
async def create_product_line(
    db: AsyncSession, code: str, name: str, factory_id: uuid.UUID | None = None, product_type_code: str | None = None
) -> ProductLine:
    existing = await get_product_line(db, code)
    if existing:
        raise ValueError(f"产品线 '{code}' 已存在")
    pl = ProductLine(code=code, name=name, factory_id=factory_id, product_type_code=product_type_code)
    db.add(pl)
    await db.commit()
    await db.refresh(pl)
    return pl


async def update_product_line(
    db: AsyncSession, pl: ProductLine, name: str | None, is_active: bool | None, product_type_code: str | None = None
) -> ProductLine:
    if name is not None:
        pl.name = name
    if is_active is not None:
        pl.is_active = is_active
    if product_type_code is not None:
        pl.product_type_code = product_type_code
    await db.commit()
    await db.refresh(pl)
    return pl
```

- [ ] **Step 6: Update API to pass product_type_code**

In `backend/app/api/product_line.py` create endpoint:
```python
        pl = await product_line_service.create_product_line(
            db, req.code, req.name, factory_id=factory_id, product_type_code=req.product_type_code
        )
```
In update endpoint:
```python
    updated = await product_line_service.update_product_line(db, pl, req.name, req.is_active, req.product_type_code)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && pytest tests/test_product_line_type_field.py -x -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/product_line.py backend/app/schemas/product_line.py backend/app/services/product_line_service.py backend/app/api/product_line.py backend/tests/test_product_line_type_field.py
git commit -m "feat(product_line): carry product_type_code through model/schema/service/api"
```

---

## Task 3: ProductType service + schema + API (CRUD + soft-delete)

**Files:**
- Create: `backend/app/schemas/product_type.py`
- Create: `backend/app/services/product_type_service.py`
- Create: `backend/app/api/product_type.py`
- Modify: `backend/app/main.py` (register router)

**Interfaces:**
- Consumes: `ProductType` model (Task 1).
- Produces: `product_type_service.list_product_types(db, is_active=None) -> list[ProductType]`; `get_product_type(db, code) -> ProductType | None`; `create_product_type(db, code, name, description, operated_by) -> ProductType`; `update_product_type(...)`; `delete_product_type(db, pt, operated_by) -> None` (soft-delete with reference check). API `GET/POST/PUT/DELETE /api/product-types`.

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

- [ ] **Step 2: Write failing test for CRUD + soft-delete**

`backend/tests/test_product_type_api.py` (write the full test file; uses fixtures from Task 5 — for now assume `admin_client`, `viewer_client`, `db_session`, `default_factory_id` exist; if not, stub with the pattern from `tests/test_management_review_report_api.py`'s `ASGITransport` + `app.dependency_overrides`):
```python
import pytest
from app.models.product_line import ProductLine


@pytest.mark.asyncio
async def test_create_product_type_admin_ok(admin_client):
    resp = await admin_client.post("/api/product-types", json={"code": "POWER", "name": "电源类"})
    assert resp.status_code == 200
    assert resp.json()["code"] == "POWER"


@pytest.mark.asyncio
async def test_create_product_type_viewer_forbidden(viewer_client):
    resp = await viewer_client.post("/api/product-types", json={"code": "X", "name": "X"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_product_type_refused_when_active_product_line_references(admin_client, db_session, default_factory_id):
    await admin_client.post("/api/product-types", json={"code": "POWER", "name": "电源类"})
    db_session.add(ProductLine(code="DC-DC-100", name="DC-DC 100W", factory_id=default_factory_id, product_type_code="POWER"))
    await db_session.commit()
    resp = await admin_client.delete("/api/product-types/POWER")
    assert resp.status_code == 400
    assert "引用" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_delete_product_type_soft_deletes_when_no_references(admin_client):
    await admin_client.post("/api/product-types", json={"code": "MOTOR", "name": "电机类"})
    resp = await admin_client.delete("/api/product-types/MOTOR")
    assert resp.status_code == 200
    resp = await admin_client.get("/api/product-types")
    codes = [i["code"] for i in resp.json()["items"]]
    assert "MOTOR" in codes
    motor = next(i for i in resp.json()["items"] if i["code"] == "MOTOR")
    assert motor["is_active"] is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_product_type_api.py -x -v`
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
        record_id=uuid.uuid4(),  # string-PK table; use a generated UUID for the audit row
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
        pt.name = name
        changed["name"] = name
    if description is not None and description != pt.description:
        pt.description = description
        changed["description"] = description
    if is_active is not None and is_active != pt.is_active:
        pt.is_active = is_active
        changed["is_active"] = is_active
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
    # Soft-delete, refused while active product lines reference it.
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

> Note: `AuditLog.record_id` is `UUID`; `product_types.code` is a string PK. We log a generated UUID as `record_id` and put the code in `changed_fields` so the audit row is traceable. This mirrors how a string-PK table would be audited without a separate record_id mapping; acceptable since audit is informational.

- [ ] **Step 5: Write the API router**

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
    return schemas.ProductTypeListResponse(
        items=[schemas.ProductTypeResponse.model_validate(i) for i in items]
    )


@router.post("", response_model=schemas.ProductTypeResponse)
async def create_product_type(
    req: schemas.ProductTypeCreate,
    db: AsyncSession = Depends(get_db),
    scope: RequestScope = Depends(get_request_scope),
):
    # require_admin-style guard: only admin may create
    _user: User = Depends(require_admin)  # noqa  # placeholder; use real guard below
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

> Fix the `create_product_type` endpoint's admin guard: remove the placeholder `_user: User = Depends(require_admin)` line inside the body and add `scope: RequestScope = Depends(get_request_scope), _user: User = Depends(require_admin),` as real parameters (mirror the `update_product_type` signature). The body placeholder above is a known mistake — correct it before committing so admin enforcement actually runs via FastAPI dependency.

- [ ] **Step 6: Register router in main.py**

In `backend/app/main.py`, add near the product_line import (line 42):
```python
from app.api.product_type import router as product_type_router
```
And near `app.include_router(product_line_router, ...)` (search for the product-lines include_router line; add):
```python
app.include_router(product_type_router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_product_type_api.py -x -v`
Expected: PASS (4 tests).

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/product_type.py backend/app/services/product_type_service.py backend/app/api/product_type.py backend/app/main.py backend/tests/test_product_type_api.py
git commit -m "feat(product_type): CRUD service + /api/product-types router with soft-delete + audit"
```

---

## Task 4: recommendation_scope resolver (scope + permissions → codes)

**Files:**
- Create: `backend/app/services/recommendation_scope.py`
- Test: `backend/tests/test_recommendation_scope.py`

**Interfaces:**
- Consumes: `ProductLine` model (Task 2), `RequestScope` (`app.core.deps.RequestScope`), `product_line_service.list_product_lines`.
- Produces: `async def resolve_product_line_codes(scope: str, current_product_line_code: str | None, db: AsyncSession, request_scope: RequestScope) -> list[str] | None`. Returns `None` for `global` (no filter); otherwise a (possibly empty) list of codes = business set ∩ user-accessible product lines ∩ accessible-factory product lines.

- [ ] **Step 1: Write failing tests**

`backend/tests/test_recommendation_scope.py`:
```python
import pytest
from app.services.recommendation_scope import resolve_product_line_codes
from app.services.product_line_service import create_product_line
from app.services.product_type_service import create_product_type


async def _seed_two_types(db_session, default_factory_id, request_scope_all):
    await create_product_type(db_session, "POWER", "电源类", None, request_scope_all.user.user_id)
    await create_product_type(db_session, "MOTOR", "电机类", None, request_scope_all.user.user_id)
    await create_product_line(db_session, "DC-DC-100", "DC-DC 100W", factory_id=default_factory_id, product_type_code="POWER")
    await create_product_line(db_session, "AC-DC-200", "AC-DC 200W", factory_id=default_factory_id, product_type_code="POWER")
    await create_product_line(db_session, "MOTOR-100", "电机 100W", factory_id=default_factory_id, product_type_code="MOTOR")


@pytest.mark.asyncio
async def test_global_returns_none(db_session, request_scope_all):
    assert await resolve_product_line_codes("global", "DC-DC-100", db_session, request_scope_all) is None


@pytest.mark.asyncio
async def test_current_product_line_returns_single(db_session, request_scope_all, default_factory_id):
    await _seed_two_types(db_session, default_factory_id, request_scope_all)
    codes = await resolve_product_line_codes("current_product_line", "DC-DC-100", db_session, request_scope_all)
    assert codes == ["DC-DC-100"]


@pytest.mark.asyncio
async def test_current_product_type_returns_same_type_codes(db_session, request_scope_all, default_factory_id):
    await _seed_two_types(db_session, default_factory_id, request_scope_all)
    codes = await resolve_product_line_codes("current_product_type", "DC-DC-100", db_session, request_scope_all)
    assert set(codes) == {"DC-DC-100", "AC-DC-200"}
    assert "MOTOR-100" not in codes


@pytest.mark.asyncio
async def test_current_product_type_untyped_degrades_to_current(db_session, request_scope_all, default_factory_id):
    await create_product_line(db_session, "UNTYPED-1", "未分类线", factory_id=default_factory_id, product_type_code=None)
    codes = await resolve_product_line_codes("current_product_type", "UNTYPED-1", db_session, request_scope_all)
    assert codes == ["UNTYPED-1"]


@pytest.mark.asyncio
async def test_current_product_type_excludes_inaccessible_factory(db_session, request_scope_restricted_other_factory, default_factory_id):
    # request_scope_restricted_other_factory grants access only to a different factory
    await _seed_two_types(db_session, default_factory_id, request_scope_restricted_other_factory)
    codes = await resolve_product_line_codes("current_product_type", "DC-DC-100", db_session, request_scope_restricted_other_factory)
    # DC-DC-100 belongs to default_factory_id which the restricted scope cannot access
    assert codes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_recommendation_scope.py -x -v`
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
    """Resolve the set of product line codes the user may see, intersected with accessible factories.

    Returns None if the user has ALL product lines (pl_scope.mode == "ALL" and factory scope is all-factory group admin);
    otherwise a concrete list.
    """
    # Factory restriction: list_product_lines already filters by accessible_factory_ids.
    accessible = request_scope.factory_scope.accessible_factory_ids
    pl_scope = request_scope.pl_scope

    if pl_scope is not None and pl_scope.mode == "ALL" and accessible is None:
        return None  # group admin: no restriction

    # Filter by accessible factories
    pls = await list_product_lines(db, is_active=True, accessible_factory_ids=accessible)
    factory_codes = {pl.code for pl in pls}

    if pl_scope is not None and pl_scope.mode == "EXPLICIT":
        factory_codes = factory_codes & set(pl_scope.codes or [])
    if pl_scope is not None and pl_scope.mode == "NONE":
        factory_codes = set()
    return list(factory_codes)


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

    # Business set
    if scope == "current_product_line":
        business = {current_product_line_code}
    elif scope == "current_product_type":
        # Look up the type of the current product line
        result = await db.execute(
            select(ProductLine.product_type_code).where(ProductLine.code == current_product_line_code)
        )
        pt_code = result.scalar_one_or_none()
        if not pt_code:
            # Untyped: degrade to current_product_line
            business = {current_product_line_code}
        else:
            type_result = await db.execute(
                select(ProductLine.code).where(ProductLine.product_type_code == pt_code)
            )
            business = {row[0] for row in type_result.fetchall()}
    else:
        business = {current_product_line_code}

    # Permission intersection
    accessible = await _user_accessible_product_lines(db, request_scope)
    if accessible is None:
        return list(business)
    return sorted(business & set(accessible))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_recommendation_scope.py -x -v`
Expected: PASS (5 tests). (If `request_scope_restricted_other_factory` fixture does not exist yet, stub it in Task 5's conftest; for now mark the last test xfail until Task 5, or implement the fixture inline.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recommendation_scope.py backend/tests/test_recommendation_scope.py
git commit -m "feat(recommend): add recommendation_scope resolver — scope+permissions -> product_line_codes"
```

---

## Task 5: Shared test fixtures (conftest additions)

**Files:**
- Modify: `backend/tests/conftest.py` (add/extend fixtures used by Tasks 2-4)

**Interfaces:**
- Produces: `db_session`, `default_factory_id`, `product_type_power`, `admin_client`, `viewer_client`, `request_scope_all`, `request_scope_restricted_other_factory`.

- [ ] **Step 1: Inspect existing conftest**

Run: `cd backend && grep -n "def db_session\|def default_factory_id\|def admin_client\|def request_scope\|ASGITransport\|async_session" tests/conftest.py`
Note which fixtures already exist; only add missing ones.

- [ ] **Step 2: Add missing fixtures**

Append to `backend/tests/conftest.py` (adapt imports to what's already there):
```python
import uuid
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.deps import RequestScope
from app.core.factory_scope import FactoryScope, ProductLineScope
from app.services.product_type_service import create_product_type


@pytest.fixture
async def admin_client(db_session, default_factory_id):
    # admin user with ALL product lines + all-factory access
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=default_factory_id),
        effective_factory_id=default_factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=_make_admin_user(),
    )
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def viewer_client(db_session, default_factory_id):
    scope = RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=[default_factory_id], default_factory_id=default_factory_id),
        effective_factory_id=default_factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=_make_viewer_user(),
    )
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_request_scope] = lambda: scope
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def request_scope_all(default_factory_id):
    return RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=None, default_factory_id=default_factory_id),
        effective_factory_id=default_factory_id,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=_make_admin_user(),
    )


@pytest.fixture
async def request_scope_restricted_other_factory(default_factory_id):
    other = uuid.uuid4()
    return RequestScope(
        factory_scope=FactoryScope(accessible_factory_ids=[other], default_factory_id=other),
        effective_factory_id=other,
        pl_scope=ProductLineScope(mode="ALL", codes=None),
        user=_make_admin_user(),
    )


@pytest.fixture
async def product_type_power(db_session, request_scope_all):
    return await create_product_type(db_session, "POWER", "电源类", None, request_scope_all.user.user_id)
```

Add `_make_admin_user` / `_make_viewer_user` helpers mirroring `_make_mock_user` in `tests/test_management_review_report_api.py:20` (MagicMock spec=User with `user_id`, `is_active`, `role_definition.bypass_row_level_security`). Import `get_db`, `get_request_scope` from `app.core.deps` and `User` from `app.models.user` at top of conftest if not present.

- [ ] **Step 3: Run all new tests together**

Run: `cd backend && pytest tests/test_product_type_api.py tests/test_recommendation_scope.py tests/test_product_line_type_field.py -x -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test(fixtures): add shared product-type/recommendation-scope test fixtures"
```

---

## Task 6: Extend scope Literal + wire RecommendationService + graph repo

**Files:**
- Modify: `backend/app/schemas/recommendation.py`
- Modify: `backend/app/services/recommendation_service.py:412,450-454,514-554`
- Modify: `backend/app/graph/repository.py:37-45`
- Modify: `backend/app/graph/jsonb_repository.py:224-242`
- Modify: `backend/app/graph/neo4j_repository.py:276-295`
- Modify: `backend/app/api/fmea.py:269-330`

**Interfaces:**
- Consumes: `resolve_product_line_codes` (Task 4), `RequestScope` (deps).
- Produces: `RecommendRequest.scope` 3-value Literal; `RecommendationService.recommend(fmea_id, request, user, request_scope)`; `FMEAGraphRepository.find_similar_nodes_advanced(..., product_line_codes: list[str] | None, ...)`.

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
    suggestions: list[SuggestionItem]
    source: Literal[...]
    cached: bool = False
    llm_available: bool = False
    graph_match_count: int = 0
    effective_scope: Literal["global", "current_product_type", "current_product_line"] = "global"
```
And `SimilarNodesRequest.scope` + `SimilarNodesResponse.effective_scope`:
```python
scope: Literal["global", "current_product_type", "current_product_line"] = "global"
```

- [ ] **Step 2: Update abstract graph repo signature**

In `backend/app/graph/repository.py:37`:
```python
    @abstractmethod
    async def find_similar_nodes_advanced(
        self,
        node_type: str,
        query_text: str,
        scope: str,
        product_line_codes: list[str] | None,
        limit: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict]:
        ...
```

- [ ] **Step 3: Update JSONB impl**

In `backend/app/graph/jsonb_repository.py:224`, change signature to `product_line_codes: list[str] | None` and the filter:
```python
        if scope != "global" and product_line_codes is not None:
            query = query.where(FMEADocument.product_line_code.in_(product_line_codes))
```
(Replace the existing `if scope == "current_product_line" and product_line_code:` block at lines 239-240.)

- [ ] **Step 4: Update Neo4j impl**

In `backend/app/graph/neo4j_repository.py:276`, change signature to `product_line_codes: list[str] | None` and:
```python
            if scope != "global" and product_line_codes is not None:
                cypher += " AND n.product_line_code IN $codes"
                params["codes"] = product_line_codes
```
(Replace the `if scope == "current_product_line" and product_line_code:` block at lines 291-293.)

- [ ] **Step 5: Wire RecommendationService to use the resolver**

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
- In `_query_graph_similarity` (line 514), change signature to accept `product_line_codes: list[str] | None` instead of `scope: str`, and pass it to the repo:
```python
    async def _query_graph_similarity(self, fmea, trigger_type, context, product_line_codes):
        ...
        fm_matches = await self.graph_repo.find_similar_nodes_advanced(
            node_type="FailureMode",
            query_text=query_text,
            scope=...,  # pass effective_scope from caller; keep param name as needed
            product_line_codes=product_line_codes,
            limit=20,
            min_similarity=0.3,
        )
```
> Adjust: the repo's `scope` param is still present in the signature (Task 6 Step 2 kept `scope`). Pass `effective_scope` through `_query_graph_similarity` as well, or drop `scope` from the repo entirely and rely solely on `product_line_codes` (None means global). **Decision: drop `scope` from the repo signature** — `product_line_codes is None` already encodes "global". Update Steps 2-4 accordingly: remove the `scope` param from both repo impls and the abstract method; keep only `product_line_codes`. The caller passes the codes (None for global).

Apply that decision: in Steps 2-4 remove `scope: str` from `find_similar_nodes_advanced` signatures; the `if scope != "global"` guard becomes `if product_line_codes is not None:`.

- Update the call site in `recommend` (lines 450-454) to pass `product_line_codes` instead of `effective_scope`.

- [ ] **Step 6: Pass request_scope from the API**

In `backend/app/api/fmea.py` recommend endpoint (line 269-330), find the `service.recommend(...)` call and add `scope` (the RequestScope) as the 4th arg:
```python
        result = await service.recommend(db=db, llm_provider=llm, graph_repo=graph_repo, llm_timeout=llm_timeout)
```
Wait — that's the `RecommendationService` constructor call. Find the `.recommend(` invocation (around line 325) and change:
```python
        result = await service.recommend(fmea_id, request, scope.user, scope)
```
(`scope` here is the `RequestScope` dependency already injected at line 274.)

- [ ] **Step 7: Write/update recommendation service test**

Add to `backend/tests/test_recommendation_scope.py` or a new `test_fmea_recommend_scope.py`:
```python
@pytest.mark.asyncio
async def test_recommend_current_product_type_cross_product_line(client_admin_with_kg, db_session, default_factory_id, fmea_factory):
    # Two product lines under POWER type; an approved FMEA in each.
    # Requesting current_product_type for fmea in DC-DC-100 should also recall matches from AC-DC-200.
    ...
    resp = await client_admin_with_kg.post(f"/api/fmea/{fmea_id}/recommend", json={"trigger_type": "failure_mode", "context": {...}, "scope": "current_product_type"})
    assert resp.status_code == 200
    assert resp.json()["effective_scope"] == "current_product_type"
    # graph_match_count should include matches from the sibling product line
```
Keep this test focused; if wiring a full approved-FMEA fixture is heavy, assert at the service layer by calling `service.recommend(...)` directly with a mocked `graph_repo` returning sibling matches. Prefer service-layer test for determinism.

- [ ] **Step 8: Run tests**

Run: `cd backend && pytest tests/ -x -k "recommend or product_type or recommendation_scope or product_line" -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas/recommendation.py backend/app/graph/repository.py backend/app/graph/jsonb_repository.py backend/app/graph/neo4j_repository.py backend/app/services/recommendation_service.py backend/app/api/fmea.py backend/tests/
git commit -m "feat(recommend): 3-value scope Literal, resolver wiring, graph repo codes-based filtering"
```

---

## Task 7: Semantic search + QA product_type_code filter

**Files:**
- Modify: `backend/app/services/search_service.py:47,172-185`
- Modify: `backend/app/schemas/search.py:40-44` (QARequest)
- Modify: `backend/app/api/search.py:28-50,52-76`

**Interfaces:**
- Produces: `SearchService.semantic_search(..., product_type_code: str | None = None)`; `ask(..., product_type_code: str | None = None)`; `QARequest.product_type_code: str | None`; `/api/search/semantic` GET `product_type_code` query param.

- [ ] **Step 1: Write failing test**

`backend/tests/test_search_product_type.py`:
```python
@pytest.mark.asyncio
async def test_semantic_search_filters_by_product_type(client, db_session, default_factory_id, seeded_embeddings_two_types):
    resp = await client.get("/api/search/semantic", params={"q": "电源", "product_type_code": "POWER"})
    assert resp.status_code == 200
    pl_codes = {r.metadata.get("product_line_code") for r in resp.json()["results"]}
    assert pl_codes <= {"DC-DC-100", "AC-DC-200"}
```
(Use a stubbed/seeded embedding set; if full embedding setup is heavy in tests, mock `SearchService._vector_search` to return rows tagged with product_line_code and assert the filter excludes MOTOR-type rows.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_search_product_type.py -x -v`
Expected: FAIL — `product_type_code` param not accepted.

- [ ] **Step 3: Add product_type_code to semantic_search**

In `backend/app/services/search_service.py` `semantic_search` (line 47), add param `product_type_code: str | None = None`. After `product_line_code` handling (lines 65-73), resolve type → codes:
```python
        if product_type_code and not product_line_code:
            # Resolve all product_line_codes under this type
            type_pls = await db.execute(
                select(ProductLine.code).where(ProductLine.product_type_code == product_type_code)
            )
            codes = [r[0] for r in type_pls.fetchall()]
            if codes:
                filters.append("product_line_code = ANY(:product_type_codes)")
                params["product_type_codes"] = codes
            else:
                filters.append("1 = 0")  # type has no product lines -> no results
```
Add `from app.models.product_line import ProductLine` and `from sqlalchemy import select` imports if missing.

- [ ] **Step 4: Add to ask()**

In `ask()` (line 172), add `product_type_code: str | None = None` param and forward it to `semantic_search(..., product_type_code=product_type_code)` at line 185.

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
- `/semantic` (line 29): add `product_type_code: str | None = Query(None),` param and pass `product_type_code=product_type_code` to the service (line 46).
- `/ask` (line 53): pass `body.product_type_code` to `ask(...)` (line 72).

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && pytest tests/test_search_product_type.py -x -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/search_service.py backend/app/schemas/search.py backend/app/api/search.py backend/tests/test_search_product_type.py
git commit -m "feat(search): product_type_code filter on semantic search + QA"
```

---

## Task 8: Seed product types + assign existing product lines

**Files:**
- Modify: `backend/app/seed.py:1770-1780` (and the second product-line seed block at 1971-1980)

**Interfaces:**
- Consumes: `ProductType` model (Task 1).

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
Then update the `pl_data` dicts to include `product_type_code`:
```python
        pl_data = [
            {"code": "DC-DC-100", "name": "DC-DC 100W 电源模块", "product_type_code": "POWER"},
            {"code": "PCB-SMT-200", "name": "PCB SMT 200 贴片线", "product_type_code": "PCB"},
        ]
```
If `PCB-SMT-200` is intended under a different type, adjust; the point is every seeded product line gets a `product_type_code`.

- [ ] **Step 2: Repeat for the second product-line seed block (line 1971-1980)**

Apply the same `product_type_code` assignment there if it seeds product lines (inspect the block; if it's a migration-style reseed, add the field consistently).

- [ ] **Step 3: Verify seed runs**

Run: `cd backend && python -m app.seed` (against a fresh/empty DB; in worktree without DB, at minimum verify the file imports: `python -c "import app.seed"`)
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/seed.py
git commit -m "feat(seed): seed POWER/PCB product types, assign DC-DC-100 + PCB-SMT-200"
```

---

## Task 9: Frontend types + API clients

**Files:**
- Modify: `frontend/src/types/index.ts:466-472` (ProductLine), add `ProductType`
- Modify: `frontend/src/api/productLine.ts`
- Create: `frontend/src/api/productType.ts`
- Modify: `frontend/src/api/recommendation.ts:18-32`
- Modify: `frontend/src/api/search.ts`

**Interfaces:**
- Produces: `ProductType` TS interface; `listProductTypes/createProductType/updateProductType/deleteProductType` API fns; `RecommendRequest.scope` union `"global" | "current_product_type" | "current_product_line"`; search API param `product_type_code`.

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

In `frontend/src/api/productLine.ts`, update `createProductLine`/`updateProductLine` payloads:
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
Add `export async function listProductTypes(): Promise<ProductType[]>` is in productType.ts below.

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
  ...
  effective_scope: "global" | "current_product_type" | "current_product_line";
}
```

- [ ] **Step 5: Extend search API params**

In `frontend/src/api/search.ts`, add `product_type_code?: string` to both the semantic search params type and the `askQuestion` request body type (find the existing param interfaces; add the field alongside `product_line_code`).

- [ ] **Step 6: Verify build**

Run: `cd frontend && npm run build`
Expected: tsc --noEmit passes, no type errors.

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
- Modify: `frontend/src/App.tsx` (routes)
- Modify: `frontend/src/components/layout/AppLayout.tsx:267` (menu)
- Modify: `frontend/src/locales/zh-CN/layout.json` + `en-US/layout.json` (menu labels)

**Interfaces:**
- Consumes: API clients from Task 9.
- Produces: two admin pages with CRUD; menu entries under admin; i18n keys.

- [ ] **Step 1: Write i18n files**

`frontend/src/locales/zh-CN/productType.json`:
```json
{
  "title": "产品类型管理",
  "fields": {
    "code": "类型代码",
    "name": "类型名称",
    "description": "描述",
    "is_active": "启用"
  },
  "actions": {
    "create": "新建类型",
    "edit": "编辑",
    "delete": "停用",
    "cancel": "取消",
    "save": "保存"
  },
  "messages": {
    "created": "产品类型已创建",
    "updated": "产品类型已更新",
    "deactivated": "产品类型已停用",
    "deleteConfirm": "确定停用该产品类型？",
    "refused": "无法停用：{{detail}}"
  },
  "productLine": {
    "title": "产品线管理",
    "fields": { "product_type_code": "产品类型", "factory": "工厂" },
    "assignType": "分配产品类型"
  }
}
```
`frontend/src/locales/en-US/productType.json`: mirror with English values (`"Product Type Management"`, `"Type Code"`, etc.).

- [ ] **Step 2: Write ProductTypePage**

`frontend/src/pages/admin/ProductTypePage.tsx` — follow `AIConfigPage.tsx` patterns (useTranslation ns `productType`, `App.useApp()` for message, `PageShell` from `components/design`). Table columns: code, name, description, is_active (Tag), actions (edit / deactivate). Edit/Create Modal with Form fields: code (Input, disabled on edit), name (Input), description (TextArea). Deactivate calls `deleteProductType` with confirm Modal; on 400 response show `message.error(t("messages.refused", {detail}))`.

Skeleton:
```tsx
import { useState, useEffect } from "react";
import { Table, Button, Modal, Form, Input, Tag, Space, App } from "antd";
import { useTranslation } from "react-i18next";
import { PlusOutlined } from "@ant-design/icons";
import { PageShell } from "../../components/design";
import { listProductTypes, createProductType, updateProductType, deleteProductType, type ProductTypeApi } from "../../api/productType";

export default function ProductTypePage() {
  const { t } = useTranslation("productType");
  const { message, modal } = App.useApp();
  const [rows, setRows] = useState<ProductTypeApi[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ProductTypeApi | null>(null);
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

  const onDeactivate = (row: ProductTypeApi) => {
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
    { title: "", render: (_: unknown, row: ProductTypeApi) => (
      <Space>
        <Button size="small" onClick={() => { setEditing(row); form.setFieldsValue(row); setOpen(true); }}>{t("actions.edit")}</Button>
        <Button size="small" danger onClick={() => onDeactivate(row)}>{t("actions.delete")}</Button>
      </Space>
    ) },
  ];

  return (
    <PageShell title={t("title")} extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>{t("actions.create")}</Button>}>
      <Table rowKey="code" dataSource={rows} columns={columns} loading={loading} />
      <Modal open={open} title={editing ? t("actions.edit") : t("actions.create")} onCancel={() => setOpen(false)} onOk={onOk}>
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
(Replace `ProductTypeApi` with the imported `ProductType` type from `../../types`.)

- [ ] **Step 3: Write ProductLinePage**

`frontend/src/pages/admin/ProductLinePage.tsx` — same structure; columns: code, name, product_type_code (render product type name via a `productTypes` lookup map), is_active, actions. Edit modal includes a `Select` for `product_type_code` populated from `listProductTypes()`. Reuse `productLine` API client.

- [ ] **Step 4: Add routes**

In `frontend/src/App.tsx`, add lazy imports near line 80:
```tsx
const ProductTypePage = lazy(() => import("./pages/admin/ProductTypePage"));
const ProductLinePage = lazy(() => import("./pages/admin/ProductLinePage"));
```
Add routes near line 219 (`/admin/ai-config`):
```tsx
        <Route path="/admin/product-types" element={<ProtectedRoute requireAdmin><ProductTypePage /></ProtectedRoute>} />
        <Route path="/admin/product-lines" element={<ProtectedRoute requireAdmin><ProductLinePage /></ProtectedRoute>} />
```

- [ ] **Step 5: Add menu items**

In `frontend/src/components/layout/AppLayout.tsx` near line 267 (after the `ai-config` entry):
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

- [ ] **Step 7: Write a component test**

`frontend/src/pages/admin/ProductTypePage.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
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
Expected: build passes, test passes.

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
- Modify: `frontend/src/locales/zh-CN/dfmea.json` + `en-US/dfmea.json` (scope labels)
- Modify: `frontend/src/locales/zh-CN/search.json` + `en-US/search.json`

**Interfaces:**
- Consumes: `RecommendRequest.scope` 3-value union (Task 9); search `product_type_code` param (Task 9).

- [ ] **Step 1: Add scope selector to recommend trigger**

In `SmartSuggestionDropdown.tsx` (and/or `InlineRecommendations.tsx`), add a `Select` for scope next to the AI trigger, defaulting to `"current_product_type"` (the new value-add), with options: 同类产品 (`current_product_type`), 当前产品线 (`current_product_line`), 全局 (`global`). Pass `scope` through to `getRecommendations`. Add i18n keys `scope.currentProductType` / `scope.currentProductLine` / `scope.global` to `dfmea.json`.

- [ ] **Step 2: Add product type filter to SemanticSearchTab**

In `frontend/src/pages/graph/SemanticSearchTab.tsx`, add a `productType` state + `Select` (populated from `listProductTypes()`). When a type is selected, filter the product-line `Select` options to product lines under that type (fetch via `listProductLines()` and client-filter by `product_type_code`, or add a server param). Pass `product_type_code` to `semanticSearch` / `askQuestion`. Both search and QA modes pass it (the existing `handleSearch` branches on `mode`).

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

**Files:** none (verification only)

- [ ] **Step 1: Backend full test run**

Run: `cd backend && SECRET_KEY=test-secret-key pytest tests/ -x --tb=short`
Expected: all pass. Investigate any failures; if an existing recommendation/search test breaks because a fixture lacks `product_type_code` or uses the old 2-value `scope` Literal, update the fixture (add `product_type_code=None`) and the test's expected `effective_scope` Literal.

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
- §1 Data model → Task 1 (table + FK), Task 2 (product_line column/schema/service/api).
- §2 Migration & backfill → Task 1 (migration + downgrade), Task 8 (seed = the only backfill; no embedding backfill per spec).
- §3 Recommendation scope + permissions → Task 4 (resolver), Task 6 (wire into service + graph repo + scope Literal + request_scope threading). 8D explicitly untouched (no task touches `recommendation_types.py` / `recommendation_sources.py` / `api/capa.py`). Semantic search/QA → Task 7.
- §4 Frontend → Task 9 (types/API), Task 10 (admin pages + routes + menu + i18n), Task 11 (scope selector + search filter).
- §5 Tests → each task carries its own TDD test; Task 5 shared fixtures; Task 12 full regression.

**Placeholder scan:** One known issue flagged inline in Task 3 Step 5 (the `create_product_type` admin-guard placeholder) — explicitly corrected in the same step. No TBD/TODO elsewhere.

**Type consistency:** `resolve_product_line_codes(scope, current_product_line_code, db, request_scope)` signature used consistently in Task 4 (impl) and Task 6 (call site). `find_similar_nodes_advanced` signature unified to `(node_type, query_text, product_line_codes, limit, min_similarity)` after the Task 6 Step 5 decision to drop `scope` from the repo. `RecommendRequest.scope` / `effective_scope` 3-value Literal consistent across Task 6 (backend) and Task 9 (frontend).