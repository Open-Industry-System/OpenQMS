# 产品线选择器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a product_lines table, global header selector, and data filtering across all modules.

**Architecture:** A new `product_lines` table stores product line metadata. Frontend Zustand store holds the selected product line (persisted in localStorage). A `<Select>` in AppLayout header lets users switch. All list pages read from the store and pass the selection to API calls. Backend list endpoints accept an optional `product_line` query parameter and filter with `.where()`.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 async | React 18 + TypeScript + Zustand + Ant Design

---

## Task 1: Backend — ProductLine Model, Schema, Service, API, Migration, Seed

**Files:**
- Create: `backend/app/models/product_line.py`
- Create: `backend/app/schemas/product_line.py`
- Create: `backend/app/services/product_line_service.py`
- Create: `backend/app/api/product_line.py`
- Create: `backend/alembic/versions/011_add_product_lines.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/seed.py`

### Step 1: Create the ProductLine model

Create `backend/app/models/product_line.py`:

```python
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ProductLine(Base):
    __tablename__ = "product_lines"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
```

### Step 2: Register the model in `backend/app/models/__init__.py`

Append to the end of the file:

```python
from app.models.product_line import ProductLine
```

### Step 3: Create Pydantic schemas

Create `backend/app/schemas/product_line.py`:

```python
from datetime import datetime
from pydantic import BaseModel, Field


class ProductLineCreate(BaseModel):
    code: str = Field(..., max_length=20, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(..., max_length=100)


class ProductLineUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class ProductLineResponse(BaseModel):
    code: str
    name: str
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class ProductLineListResponse(BaseModel):
    items: list[ProductLineResponse]
```

Register in `backend/app/schemas/__init__.py` by appending:

```python
from app.schemas import product_line
```

### Step 4: Create the Alembic migration

> **Note:** There are two `010_*` migrations sharing `down_revision = "009_add_msa_tables"`. Before creating this migration, run `cd backend && alembic heads` to identify the current head(s). If there are two heads, use `alembic merge` to create a merge point first, then set `down_revision` to that merge revision. Otherwise use the single head as `down_revision`.

Create `backend/alembic/versions/011_add_product_lines.py`:

```python
"""add product_lines table

Revision ID: 011_add_product_lines
Revises: <fill in actual head revision after running alembic heads>
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa

revision = "011_add_product_lines"
down_revision = "<fill in actual head revision>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_lines",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("product_lines")
```

### Step 5: Create the service

Create `backend/app/services/product_line_service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product_line import ProductLine


async def list_product_lines(db: AsyncSession, is_active: bool | None = None) -> list[ProductLine]:
    query = select(ProductLine).order_by(ProductLine.code)
    if is_active is not None:
        query = query.where(ProductLine.is_active == is_active)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_product_line(db: AsyncSession, code: str) -> ProductLine | None:
    result = await db.execute(select(ProductLine).where(ProductLine.code == code))
    return result.scalar_one_or_none()


async def create_product_line(db: AsyncSession, code: str, name: str) -> ProductLine:
    pl = ProductLine(code=code, name=name)
    db.add(pl)
    await db.commit()
    await db.refresh(pl)
    return pl


async def update_product_line(db: AsyncSession, pl: ProductLine, name: str | None, is_active: bool | None) -> ProductLine:
    if name is not None:
        pl.name = name
    if is_active is not None:
        pl.is_active = is_active
    await db.commit()
    await db.refresh(pl)
    return pl


async def delete_product_line(db: AsyncSession, pl: ProductLine) -> None:
    pl.is_active = False
    await db.commit()


async def validate_product_line(db: AsyncSession, code: str) -> None:
    """Raise ValueError if product_line code doesn't exist or is inactive."""
    pl = await get_product_line(db, code)
    if pl is None:
        raise ValueError(f"产品线 '{code}' 不存在")
    if not pl.is_active:
        raise ValueError(f"产品线 '{code}' 已停用")
```

### Step 6: Create the API router

Create `backend/app/api/product_line.py`:

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.schemas import product_line as schemas
from app.services import product_line_service

router = APIRouter(prefix="/api/product-lines", tags=["product-lines"])


@router.get("", response_model=schemas.ProductLineListResponse)
async def list_product_lines(
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items = await product_line_service.list_product_lines(db, is_active)
    return schemas.ProductLineListResponse(
        items=[schemas.ProductLineResponse.model_validate(i) for i in items]
    )


@router.post("", response_model=schemas.ProductLineResponse)
async def create_product_line(
    req: schemas.ProductLineCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    existing = await product_line_service.get_product_line(db, req.code)
    if existing:
        raise ValueError(f"产品线 '{req.code}' 已存在")
    pl = await product_line_service.create_product_line(db, req.code, req.name)
    return schemas.ProductLineResponse.model_validate(pl)


@router.put("/{code}", response_model=schemas.ProductLineResponse)
async def update_product_line(
    code: str,
    req: schemas.ProductLineUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    pl = await product_line_service.get_product_line(db, code)
    if not pl:
        raise ValueError(f"产品线 '{code}' 不存在")
    updated = await product_line_service.update_product_line(db, pl, req.name, req.is_active)
    return schemas.ProductLineResponse.model_validate(updated)


@router.delete("/{code}")
async def delete_product_line(
    code: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    pl = await product_line_service.get_product_line(db, code)
    if not pl:
        raise ValueError(f"产品线 '{code}' 不存在")
    await product_line_service.delete_product_line(db, pl)
    return {"message": f"产品线 '{code}' 已停用"}
```

### Step 7: Register the router in `backend/app/main.py`

Add after the existing imports (around line 31):

```python
from app.api.product_line import router as product_line_router
```

Add after the existing `app.include_router(sc_router)` (around line 78):

```python
app.include_router(product_line_router)
```

### Step 8: Add seed data

In `backend/app/seed.py`, add before the final `await db.commit()`:

```python
    # Product lines
    from app.models.product_line import ProductLine

    pl_data = [
        {"code": "DC-DC-100", "name": "DC-DC 100W 电源模块"},
        {"code": "PCB-SMT-200", "name": "PCB SMT 200 贴片线"},
    ]
    for pl_dict in pl_data:
        existing = await db.execute(select(ProductLine).where(ProductLine.code == pl_dict["code"]))
        if not existing.scalar_one_or_none():
            db.add(ProductLine(**pl_dict))

    await db.commit()
```

### Step 9: Verify

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -c "from app.models.product_line import ProductLine; print('Model OK')"
python -c "from app.schemas.product_line import ProductLineCreate, ProductLineResponse; print('Schema OK')"
```

### Step 10: Commit

```bash
git add backend/app/models/product_line.py backend/app/schemas/product_line.py backend/app/services/product_line_service.py backend/app/api/product_line.py backend/alembic/versions/011_add_product_lines.py backend/app/models/__init__.py backend/app/schemas/__init__.py backend/app/main.py backend/app/seed.py
git commit -m "feat(product-line): add ProductLine model, CRUD API, migration, and seed data"
```

---

## Task 2: Backend — Add product_line Filter to FMEA, CAPA, ControlPlan List Endpoints

**Files:**
- Modify: `backend/app/services/fmea_service.py`
- Modify: `backend/app/api/fmea.py`
- Modify: `backend/app/schemas/fmea.py`
- Modify: `backend/app/services/capa_service.py`
- Modify: `backend/app/api/capa.py`
- Modify: `backend/app/schemas/capa.py`
- Modify: `backend/app/services/control_plan_service.py`
- Modify: `backend/app/api/control_plan.py`
- Modify: `backend/app/schemas/control_plan.py`
- Modify: `backend/app/services/dashboard_service.py`
- Modify: `backend/app/api/dashboard.py`

### Step 1: Add product_line filter to FMEA service

In `backend/app/services/fmea_service.py`, modify `list_fmeas`:

```python
async def list_fmeas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    product_line: str | None = None,
) -> tuple[list[FMEADocument], int]:
    query = select(FMEADocument)
    count_query = select(func.count(FMEADocument.fmea_id))

    if status:
        query = query.where(FMEADocument.status == status)
        count_query = count_query.where(FMEADocument.status == status)
    if product_line:
        query = query.where(FMEADocument.product_line_code == product_line)
        count_query = count_query.where(FMEADocument.product_line_code == product_line)

    query = query.order_by(FMEADocument.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = list(result.scalars().all())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    return items, total
```

### Step 2: Add product_line param to FMEA API

In `backend/app/api/fmea.py`, modify `list_fmeas` endpoint:

```python
@router.get("", response_model=FMEAListResponse)
async def list_fmeas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    status: str | None = None,
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items, total = await fmea_service.list_fmeas(db, page, page_size, status, product_line)
    return FMEAListResponse(
        items=[FMEAResponse.model_validate(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )
```

### Step 3: Add product_line filter to CAPA service

In `backend/app/services/capa_service.py`, modify `list_capas`:

```python
async def list_capas(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    product_line: str | None = None,
) -> tuple[list[CAPAEightD], int]:
    query = select(CAPAEightD)
    count_query = select(func.count(CAPAEightD.report_id))

    if status:
        query = query.where(CAPAEightD.status == status)
        count_query = count_query.where(CAPAEightD.status == status)
    if product_line:
        query = query.where(CAPAEightD.product_line_code == product_line)
        count_query = count_query.where(CAPAEightD.product_line_code == product_line)

    query = query.order_by(CAPAEightD.created_at.desc())
    # ... rest unchanged
```

### Step 4: Add product_line param to CAPA API

In `backend/app/api/capa.py`, modify `list_capas` endpoint. Add `product_line: str | None = None` parameter and pass it to the service call.

### Step 5: Add product_line filter to ControlPlan service

In `backend/app/services/control_plan_service.py`, modify `list_control_plans`:

```python
async def list_control_plans(
    db: AsyncSession, page: int = 1, page_size: int = 20, product_line: str | None = None
) -> dict:
    query = select(ControlPlan).order_by(ControlPlan.created_at.desc())
    count_query = select(func.count(ControlPlan.cp_id))

    if product_line:
        query = query.where(ControlPlan.product_line_code == product_line)
        count_query = count_query.where(ControlPlan.product_line_code == product_line)

    query = query.offset((page - 1) * page_size).limit(page_size)
    # ... rest unchanged
```

### Step 6: Add product_line param to ControlPlan API

In `backend/app/api/control_plan.py`, modify `list_control_plans` endpoint. Add `product_line: str | None = None` parameter and pass it to the service call.

### Step 7: Add product_line_code to creation schemas

In `backend/app/schemas/fmea.py`, add to `FMEACreate`:

```python
product_line_code: str = "DC-DC-100"
```

In `backend/app/schemas/capa.py`, add to `CAPACreate`:

```python
product_line_code: str = "DC-DC-100"
```

In `backend/app/schemas/control_plan.py`, add to `ControlPlanCreate`:

```python
product_line_code: str = "DC-DC-100"
```

### Step 8: Add validation + product_line_code to create/update services

**FMEA — `backend/app/services/fmea_service.py`:**

Update the `create_fmea` function signature to accept `product_line_code` and pass it to the model:

```python
from app.services.product_line_service import validate_product_line

async def create_fmea(
    db: AsyncSession, title: str, document_no: str, fmea_type: str,
    user_id: uuid.UUID, product_line_code: str = "DC-DC-100",
) -> FMEADocument:
    await validate_product_line(db, product_line_code)
    fmea = FMEADocument(
        title=title,
        document_no=document_no,
        fmea_type=fmea_type,
        created_by=user_id,
        product_line_code=product_line_code,
    )
    db.add(fmea)
    await db.commit()
    await db.refresh(fmea)
    return fmea
```

Update `update_fmea` — if `product_line_code` is being changed, call `await validate_product_line(db, new_product_line_code)` before applying.

**FMEA API — `backend/app/api/fmea.py`:**

Pass `req.product_line_code` through to the service:

```python
fmea = await fmea_service.create_fmea(
    db, req.title, req.document_no, req.fmea_type, user.user_id, req.product_line_code
)
```

**CAPA — `backend/app/services/capa_service.py`:**

```python
from app.services.product_line_service import validate_product_line

async def create_capa(
    db: AsyncSession, title: str, document_no: str, severity: str,
    due_date, user_id: uuid.UUID, product_line_code: str = "DC-DC-100",
) -> CAPAEightD:
    await validate_product_line(db, product_line_code)
    capa = CAPAEightD(
        title=title,
        document_no=document_no,
        severity=severity,
        due_date=due_date,
        created_by=user_id,
        product_line_code=product_line_code,
    )
    db.add(capa)
    await db.commit()
    await db.refresh(capa)
    return capa
```

**CAPA API — `backend/app/api/capa.py`:**

```python
capa = await capa_service.create_capa(
    db, req.title, req.document_no, req.severity, req.due_date, user.user_id, req.product_line_code
)
```

**ControlPlan — `backend/app/services/control_plan_service.py`:**

The `create_control_plan` function already accepts a `ControlPlanCreate` object. Add validation and explicit assignment:

```python
from app.services.product_line_service import validate_product_line

async def create_control_plan(db: AsyncSession, data: ControlPlanCreate, user_id: uuid.UUID) -> ControlPlan:
    await validate_product_line(db, data.product_line_code)
    cp = ControlPlan(
        plan_name=data.plan_name,
        product_line_code=data.product_line_code,
        # ... other fields
    )
    db.add(cp)
    await db.commit()
    await db.refresh(cp)
    return cp
```

For all three services, repeat validation in the corresponding `update_*` function if `product_line_code` is being modified.

### Step 9: Add product_line filter to dashboard service and API

In `backend/app/api/dashboard.py`, modify the `/kpi` endpoint:

```python
@router.get("/kpi")
async def get_kpi(
    product_line: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await dashboard_service.get_dashboard(db, product_line)
    return data["kpi"]
```

In `backend/app/services/dashboard_service.py`, modify `get_dashboard` to accept `product_line: str | None = None`. When `product_line` is provided, add `.where()` clauses to the count queries for FMEA, CAPA, and other entities:

```python
async def get_dashboard(db: AsyncSession, product_line: str | None = None) -> dict:
    # For each count query, conditionally filter:
    fmea_query = select(func.count(FMEADocument.fmea_id))
    if product_line:
        fmea_query = fmea_query.where(FMEADocument.product_line_code == product_line)
    # Same pattern for CAPA, ControlPlan, etc.
    # For RPN aggregation, filter FMEA docs by product_line before iterating graph_data
    fmea_doc_query = select(FMEADocument.fmea_id, FMEADocument.graph_data)
    if product_line:
        fmea_doc_query = fmea_doc_query.where(FMEADocument.product_line_code == product_line)
```

### Step 10: Verify Python syntax

```bash
cd /Users/sam/Documents/Code/OpenQMS/backend
python -c "from app.api.fmea import router; from app.api.capa import router; from app.api.control_plan import router; from app.api.dashboard import router; print('All OK')"
```

### Step 11: Commit

```bash
git add backend/app/services/fmea_service.py backend/app/api/fmea.py backend/app/schemas/fmea.py backend/app/services/capa_service.py backend/app/api/capa.py backend/app/schemas/capa.py backend/app/services/control_plan_service.py backend/app/api/control_plan.py backend/app/schemas/control_plan.py backend/app/services/dashboard_service.py backend/app/api/dashboard.py
git commit -m "feat(product-line): add product_line filter + validation to FMEA, CAPA, ControlPlan, Dashboard"
```

---

## Task 3: Frontend — Store, Global Selector, Types, API Client

**Files:**
- Create: `frontend/src/store/productLineStore.ts`
- Create: `frontend/src/api/productLine.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

### Step 1: Add ProductLine type to types/index.ts

Append to the types file:

```ts
export interface ProductLine {
  code: string;
  name: string;
  is_active: boolean;
  created_at: string;
}
```

### Step 2: Create the API client

Create `frontend/src/api/productLine.ts`:

```ts
import client from "./client";
import type { ProductLine } from "../types";

export async function listProductLines(isActive?: boolean): Promise<ProductLine[]> {
  const params: Record<string, unknown> = {};
  if (isActive !== undefined) params.is_active = isActive;
  const resp = await client.get("/product-lines", { params });
  return resp.data.items;
}

export async function createProductLine(data: { code: string; name: string }): Promise<ProductLine> {
  const resp = await client.post("/product-lines", data);
  return resp.data;
}

export async function updateProductLine(code: string, data: { name?: string; is_active?: boolean }): Promise<ProductLine> {
  const resp = await client.put(`/product-lines/${code}`, data);
  return resp.data;
}

export async function deleteProductLine(code: string): Promise<void> {
  await client.delete(`/product-lines/${code}`);
}
```

### Step 3: Create the Zustand store

Create `frontend/src/store/productLineStore.ts`:

```ts
import { create } from "zustand";
import type { ProductLine } from "../types";
import { listProductLines } from "../api/productLine";

const STORAGE_KEY = "openqms_product_line";

interface ProductLineState {
  productLines: ProductLine[];
  selected: string | null;
  setSelected: (code: string | null) => void;
  load: () => Promise<void>;
}

export const useProductLineStore = create<ProductLineState>((set) => ({
  productLines: [],
  selected: localStorage.getItem(STORAGE_KEY),
  setSelected: (code) => {
    if (code) {
      localStorage.setItem(STORAGE_KEY, code);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    set({ selected: code });
  },
  load: async () => {
    try {
      const items = await listProductLines(true);
      const current = useProductLineStore.getState().selected;
      if (current && !items.some((pl) => pl.code === current)) {
        useProductLineStore.getState().setSelected(null);
      }
      set({ productLines: items });
    } catch {
      // silently fail — selector will show empty
    }
  },
}));
```

### Step 4: Add the global selector to AppLayout

In `frontend/src/components/layout/AppLayout.tsx`:

Add imports at the top:

```ts
import { Select } from "antd";
import { useProductLineStore } from "../../store/productLineStore";
```

Inside the `AppLayout` component, before the `return`, add:

```ts
const { productLines, selected, setSelected, load } = useProductLineStore();

useEffect(() => { load(); }, [load]);
```

In the header's right-side `<Space>`, insert before the user `<Dropdown>`:

```tsx
<Select
  allowClear
  placeholder="全部产品线"
  style={{ width: 200 }}
  value={selected || undefined}
  onChange={(v) => setSelected(v || null)}
>
  {productLines.map((pl) => (
    <Select.Option key={pl.code} value={pl.code}>
      {pl.code} - {pl.name}
    </Select.Option>
  ))}
</Select>
```

### Step 5: Verify TypeScript

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npx tsc --noEmit
```

### Step 6: Commit

```bash
git add frontend/src/store/productLineStore.ts frontend/src/api/productLine.ts frontend/src/types/index.ts frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(product-line): add Zustand store, API client, and global selector in AppLayout header"
```

---

## Task 4: Frontend — Adapt All List Pages to Use Global Product Line Store

**Files:**
- Modify: `frontend/src/pages/fmea/FMEAListPage.tsx`
- Modify: `frontend/src/pages/capa/CAPAListPage.tsx`
- Modify: `frontend/src/pages/controlPlan/ControlPlanListPage.tsx`
- Modify: `frontend/src/api/fmea.ts`
- Modify: `frontend/src/api/capa.ts`
- Modify: `frontend/src/api/dashboard.ts`
- Modify: `frontend/src/pages/spc/SPCListPage.tsx`
- Modify: `frontend/src/pages/special-characteristic/SCListPage.tsx`
- Modify: `frontend/src/pages/special-characteristic/SCMatrixPage.tsx`
- Modify: `frontend/src/pages/qualityGoal/QualityGoalListPage.tsx`
- Modify: `frontend/src/pages/dashboard/DashboardPage.tsx`

### Step 1: Add product_line to FMEA API client

In `frontend/src/api/fmea.ts`, add `product_line?: string` to the params of `listFMEAs` and pass it through.

### Step 2: Adapt FMEAListPage

In `frontend/src/pages/fmea/FMEAListPage.tsx`:

Add import:

```ts
import { useProductLineStore } from "../../store/productLineStore";
```

Inside the component:

```ts
const productLine = useProductLineStore((s) => s.selected);
```

Modify `fetchData` to pass productLine:

```ts
const fetchData = (p: number = page) => {
  setLoading(true);
  listFMEAs({ page: p, page_size: 20, status, product_line: productLine || undefined })
    .then((res) => { setData(res.items); setTotal(res.total); })
    .finally(() => setLoading(false));
};
```

Change useEffect dependency:

```ts
useEffect(() => { fetchData(); }, [productLine]);
```

### Step 3: Add product_line to CAPA API client and adapt CAPAListPage

Same pattern as Step 1-2. In `frontend/src/api/capa.ts`, add `product_line?: string` to params. In `CAPAListPage.tsx`, import store, read `selected`, pass to API, add to useEffect deps.

### Step 4: Adapt SPCListPage

`SPCListPage` already has a local `productLine` state. Replace it with the global store:

- Remove local `const [productLine, setProductLine] = useState<string>("");`
- Add `const productLine = useProductLineStore((s) => s.selected);`
- Remove the local product line `<Select>` from the page header (it's now in AppLayout)
- Ensure useEffect depends on `productLine`

### Step 5: Adapt SCMatrixPage

Same pattern as SPCListPage — replace local product line state with global store, remove the page-level Select dropdown.

### Step 6: Adapt QualityGoalListPage

Same pattern. Replace local product line state with global store. Remove page-level product line filter Select if present.

### Step 7: Adapt ControlPlanListPage

Same pattern as FMEAListPage. Import store, read `selected`, pass to API, add to useEffect deps.

### Step 8: Adapt SCListPage

In `frontend/src/pages/special-characteristic/SCListPage.tsx`:

```ts
import { useProductLineStore } from "../../store/productLineStore";
const productLine = useProductLineStore((s) => s.selected);
```

Pass `productLine` to the list API call. Add `productLine` to useEffect deps.

### Step 9: Add product_line to dashboard API client

In `frontend/src/api/dashboard.ts`, update the KPI fetch function to accept and pass `product_line`:

```ts
export async function getKPI(productLine?: string): Promise<KPIResponse> {
  const params: Record<string, unknown> = {};
  if (productLine) params.product_line = productLine;
  const resp = await client.get("/dashboard/kpi", { params });
  return resp.data;
}
```

### Step 10: Adapt DashboardPage

In `frontend/src/pages/dashboard/DashboardPage.tsx`:

```ts
const productLine = useProductLineStore((s) => s.selected);
```

Pass `productLine` to the KPI API call. Add `productLine` to useEffect deps so the dashboard auto-refreshes on product line change.

### Step 11: Handle new document default product_line

When creating a new FMEA, CAPA, or ControlPlan, the creation form/modal should pre-fill the product line field from the global store:

```ts
const productLine = useProductLineStore((s) => s.selected);
```

- If `productLine` is set: pre-fill the form field with that value
- If `productLine` is null ("全部"): leave the field empty and let the user select manually

This applies to any create modal/form in FMEAListPage, CAPAListPage, ControlPlanListPage, and QualityGoalListPage.

### Step 12: Verify TypeScript

```bash
cd /Users/sam/Documents/Code/OpenQMS/frontend
npx tsc --noEmit
```

### Step 13: Commit

```bash
git add frontend/src/pages/fmea/FMEAListPage.tsx frontend/src/pages/capa/CAPAListPage.tsx frontend/src/pages/controlPlan/ControlPlanListPage.tsx frontend/src/api/fmea.ts frontend/src/api/capa.ts frontend/src/api/dashboard.ts frontend/src/pages/spc/SPCListPage.tsx frontend/src/pages/special-characteristic/SCListPage.tsx frontend/src/pages/special-characteristic/SCMatrixPage.tsx frontend/src/pages/qualityGoal/QualityGoalListPage.tsx frontend/src/pages/dashboard/DashboardPage.tsx
git commit -m "feat(product-line): adapt all list pages to use global product line store"
```

---

## Task 5: Update ROADMAP.md

**Files:**
- Modify: `docs/ROADMAP.md`

### Step 1: Mark product line selector as complete

In `docs/ROADMAP.md`, change the product line selector row:

```markdown
| 产品线选择器 | P0 | ✅ 完成 | product_lines 表 + 全局选择器 + 所有模块统一过滤 |
```

And in the "下一步行动" section, check the box:

```markdown
- [x] 添加产品线选择器（多产品线支持）
```

### Step 2: Commit

```bash
git add docs/ROADMAP.md
git commit -m "docs: mark product line selector as complete in ROADMAP"
```
