# PLM BOM Import and Part-to-SC Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the existing PLM BOM tree/import flow from the PLM parts list page and implement a transactional Part-to-SC confirmation workflow that links pending PLM part flags to Special Characteristics.

**Architecture:** Keep changes surgical around the PLM parts surface. Backend adds one new PLM endpoint and a no-commit Special Characteristic helper; frontend adds a parts-list-driven BOM modal, a pending-link-driven SC confirmation modal, and an `sc_links`-aware permission surface.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 async, PostgreSQL 15, Alembic, Pydantic v2, React 18, TypeScript, Ant Design, Vitest.

---

## File Structure

### Backend

- `backend/alembic/versions/20260609_widen_sc_node_ids.py` (create)
  - Alembic migration widening `special_characteristics.source_node_id` and `special_characteristic_links.source_item_id` from `String(36)` to `String(128)` with downgrade support.

- `backend/app/models/special_characteristic.py` (modify)
  - Update `SpecialCharacteristic.source_node_id` to `String(128)`.

- `backend/app/models/special_characteristic_link.py` (modify)
  - Update `SpecialCharacteristicLink.source_item_id` to `String(128)`.

- `backend/app/services/special_characteristic_service.py` (modify)
  - Add `prepare_special_characteristic()` no-commit helper that creates the SC, flushes, and writes the audit log without committing.

- `backend/app/schemas/plm.py` (modify)
  - Add `PLMPartSCLinkResponse` and attach `sc_links` to `PLMPartResponse`.

- `backend/app/api/plm.py` (modify)
  - Add explicit SC link batch loading for `list_parts` and `get_part`.
  - Add `POST /api/plm/parts/{part_id}/confirm-sc` with dual permission checks and transactional confirmation logic.

- `backend/tests/test_plm_regressions.py` (modify)
  - Add regression tests for confirmation success paths, error paths, permission gating, and expanded PLM part response fields.

### Frontend

- `frontend/src/types/plm.ts` (modify)
  - Add `PLMPartSCLink`, `PLMPartConfirmSCRequest`, `PLMPartConfirmSCResponse`, and `PLMBOMImportResponse`.
  - Add `sc_links` to `PLMPart`.

- `frontend/src/api/plm.ts` (modify)
  - Add `confirmPLMPartSC()` and reuse existing BOM tree/import functions.

- `frontend/src/pages/plm/PLMPartsPage.tsx` (modify)
  - Add BOM modal, SC confirmation modal, permission-aware row actions, and refresh behavior.

- `frontend/src/pages/plm/PLMPermissions.test.tsx` (modify)
  - Add PLM parts tests covering BOM/import/SC actions visibility and link-state eligibility.

---

## Task 1: Add failing tests for widened node ID columns

**Files:**
- Modify: `backend/tests/test_plm_regressions.py`

- [ ] **Step 1: Add import for special-characteristic models**

```python
from app.models.special_characteristic import SpecialCharacteristic as SpecialCharacteristicModel
from app.models.special_characteristic_link import SpecialCharacteristicLink
```

- [ ] **Step 2: Add failing assertion for source_node_id length**

Append to the existing PLM regression test file:

```python
def test_special_characteristic_source_node_id_allows_long_node_ids():
    col = SpecialCharacteristicModel.__table__.c["source_node_id"]
    assert col.type.length >= 128


def test_special_characteristic_link_source_item_id_allows_long_node_ids():
    col = SpecialCharacteristicLink.__table__.c["source_item_id"]
    assert col.type.length >= 128
```

- [ ] **Step 3: Run the backend PLM regression tests**

Run from repo root:

```bash
SECRET_KEY=test-secret python -m pytest backend/tests/test_plm_regressions.py -v
```

Expected: the two new tests fail because current models are still `String(36)`.

- [ ] **Step 4: Commit the failing tests**

```bash
git add backend/tests/test_plm_regressions.py
git commit -m "test(plm): add failing node-id-length regression tests"
```

---

## Task 2: Widen node ID columns via migration and models

**Files:**
- Create: `backend/alembic/versions/20260609_widen_sc_node_ids.py`
- Modify: `backend/app/models/special_characteristic.py`
- Modify: `backend/app/models/special_characteristic_link.py`

- [ ] **Step 1: Update the SpecialCharacteristic model**

In `backend/app/models/special_characteristic.py`, change:

```python
    source_node_id: Mapped[str] = mapped_column(String(36), nullable=False)
```

to:

```python
    source_node_id: Mapped[str] = mapped_column(String(128), nullable=False)
```

- [ ] **Step 2: Update the SpecialCharacteristicLink model**

In `backend/app/models/special_characteristic_link.py`, change:

```python
    source_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
```

to:

```python
    source_item_id: Mapped[str] = mapped_column(String(128), nullable=False)
```

- [ ] **Step 3: Create the Alembic migration**

Create `backend/alembic/versions/20260609_widen_sc_node_ids.py`:

```python
"""widen sc node id columns

Revision ID: 20260609_widen_sc_node_ids
Revises: 031_add_plm_tables
Create Date: 2026-06-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260609_widen_sc_node_ids"
down_revision: Union[str, None] = "031_add_plm_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "special_characteristics",
        "source_node_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
    op.alter_column(
        "special_characteristic_links",
        "source_item_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "special_characteristic_links",
        "source_item_id",
        existing_type=sa.String(length=128),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
    op.alter_column(
        "special_characteristics",
        "source_node_id",
        existing_type=sa.String(length=128),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
```

- [ ] **Step 4: Run the backend PLM regression tests**

```bash
SECRET_KEY=test-secret python -m pytest backend/tests/test_plm_regressions.py -v
```

Expected: the two node-id-length tests now pass.

- [ ] **Step 5: Commit the schema fix**

```bash
git add backend/alembic/versions/20260609_widen_sc_node_ids.py backend/app/models/special_characteristic.py backend/app/models/special_characteristic_link.py backend/tests/test_plm_regressions.py
git commit -m "feat(plm): widen SC node id columns for PLM workflow"
```

---

## Task 3: Add a no-commit SC preparation helper

**Files:**
- Modify: `backend/app/services/special_characteristic_service.py`

- [ ] **Step 1: Add the helper to the special-characteristic service**

Append after the existing `create_special_characteristic()` function in `backend/app/services/special_characteristic_service.py`:

```python
async def prepare_special_characteristic(
    db: AsyncSession,
    data: SCCreate,
    user_id: uuid.UUID,
) -> SpecialCharacteristic:
    """Stage a SpecialCharacteristic without committing.

    Explicitly flushes so the caller can safely reference the newly created
    ``sc_id`` before any follow-on writes (e.g., PLM SC link confirmation).
    """
    sc_code = await generate_sc_code(db)
    item = SpecialCharacteristic(
        sc_code=sc_code,
        sc_name=data.sc_name,
        sc_type=data.sc_type,
        customer_symbol=data.customer_symbol,
        sc_category=data.sc_category,
        spec_requirement=data.spec_requirement,
        source_fmea_id=data.source_fmea_id,
        source_node_id=data.source_node_id or "",
        source_type=data.source_type or "PFMEA",
        sop_ref=data.sop_ref,
        product_line_code=data.product_line_code,
        created_by=user_id,
    )
    db.add(item)
    await db.flush()
    await _create_audit(
        db,
        "CREATE",
        item.sc_id,
        user_id,
        {"sc_code": sc_code, "sc_name": data.sc_name},
    )
    return item
```

- [ ] **Step 2: Run backend PLM regression tests**

```bash
SECRET_KEY=test-secret python -m pytest backend/tests/test_plm_regressions.py -v
```

Expected: existing tests continue to pass; no behavioral change yet.

- [ ] **Step 3: Commit the helper**

```bash
git add backend/app/services/special_characteristic_service.py
git commit -m "feat(sc): add no-commit prepare_special_characteristic helper"
```

---

## Task 4: Add failing tests for PLM part SC link exposure and confirmation endpoint

**Files:**
- Modify: `backend/tests/test_plm_regressions.py`

- [ ] **Step 1: Import the PLM schemas and special-characteristic service helper**

```python
from app.services.special_characteristic_service import (
    SafetyApprovalStatus,
    prepare_special_characteristic,
)
```

Also ensure this import exists near the top of the file:

```python
from app.schemas import plm as plm_schemas
```

- [ ] **Step 2: Add helpers for part, SC link, and FMEA graph fixtures**

Append these helpers below the existing fixture helpers:

```python
def _part(**overrides):
    data = {
        "part_id": uuid.uuid4(),
        "connection_id": uuid.uuid4(),
        "external_id": "ext-p1",
        "part_number": "P-1",
        "name": "Part 1",
        "revision": "A",
        "material": None,
        "specification": None,
        "status": "active",
        "is_safety_related": False,
        "is_key_characteristic": False,
        "source_updated_at": None,
        "product_line_code": None,
        "plm_raw_data": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _sc_link(**overrides):
    data = {
        "link_id": uuid.uuid4(),
        "part_id": uuid.uuid4(),
        "sc_id": None,
        "characteristic_type": "safety",
        "status": "pending",
        "confirmed_by": None,
        "confirmed_at": None,
        "product_line_code": "DC-DC-100",
    }
    data.update(overrides)
    return SimpleNamespace(**data)
```

- [ ] **Step 3: Add failing test that PLM part responses expose SC links**

```python
@pytest.mark.asyncio
async def test_get_part_includes_sc_links(monkeypatch):
    part_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    part = _part(
        part_id=part_id,
        connection_id=connection_id,
        is_safety_related=True,
        product_line_code="DC-DC-100",
    )
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    db = _FakeDb([part, [link]])
    user = SimpleNamespace()

    async def allow_access(_user, _plc, _db):
        return None

    monkeypatch.setattr(plm_api, "enforce_product_line_access", allow_access)

    result = await plm_api.get_part(part_id, db, user)

    assert result.sc_links[0].characteristic_type == "safety"
    assert result.sc_links[0].status == "pending"
```

- [ ] **Step 4: Add failing test for successful SC confirmation**

```python
@pytest.mark.asyncio
async def test_confirm_sc_creates_sc_and_confirms_link(monkeypatch):
    part_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(
        part_id=part_id,
        connection_id=connection_id,
        is_safety_related=True,
        product_line_code="DC-DC-100",
    )
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    created_sc = SimpleNamespace(sc_id=uuid.uuid4())
    db = _FakeDb([part, link])
    user = SimpleNamespace(user_id=uuid.uuid4())

    async def allow_access(_user, _plc, _db):
        return None

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    async def fake_prepare_special_characteristic(_db, _data, _user_id):
        return created_sc

    monkeypatch.setattr(plm_api, "enforce_product_line_access", allow_access)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "prepare_special_characteristic", fake_prepare_special_characteristic)

    result = await plm_api.confirm_part_sc(
        part_id,
        plm_schemas.PLMPartConfirmSCRequest(
            fmea_id=fmea_id,
            node_id="node-1",
            characteristic_type="safety",
        ),
        db,
        user,
    )

    assert result.status == "confirmed"
    assert result.sc_id == created_sc.sc_id
    assert link.status == "confirmed"
    assert link.sc_id == created_sc.sc_id
    assert link.confirmed_by == user.user_id
    assert db.commits == 1
```

- [ ] **Step 5: Add failing tests for route permission dependencies, missing pending link, already confirmed link, flag mismatch, product-line mismatch, missing FMEA node, invalid FMEA type, and long node id**

```python
from app.core import permissions as permissions_core


@pytest.mark.asyncio
async def test_confirm_sc_route_rejects_plm_only_user(monkeypatch):
    route = _route("/parts/{part_id}/confirm-sc", "POST")
    sig = inspect.signature(route.endpoint)
    plm_dep = sig.parameters["user"].default.dependency
    sc_dep = sig.parameters["_sc_user"].default.dependency
    user = SimpleNamespace(user_id=uuid.uuid4())
    db = SimpleNamespace()

    async def fake_get_user_permission(_user, module, _db):
        if module == permissions_core.Module.PLM:
            return permissions_core.PermissionLevel.EDIT
        if module == permissions_core.Module.SPECIAL_CHARACTERISTIC:
            return permissions_core.PermissionLevel.VIEW
        return permissions_core.PermissionLevel.NONE

    monkeypatch.setattr(permissions_core, "get_user_permission", fake_get_user_permission)

    assert await plm_dep(user, db) is user
    with pytest.raises(HTTPException) as exc:
        await sc_dep(user, db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_confirm_sc_route_rejects_sc_only_user(monkeypatch):
    route = _route("/parts/{part_id}/confirm-sc", "POST")
    sig = inspect.signature(route.endpoint)
    plm_dep = sig.parameters["user"].default.dependency
    sc_dep = sig.parameters["_sc_user"].default.dependency
    user = SimpleNamespace(user_id=uuid.uuid4())
    db = SimpleNamespace()

    async def fake_get_user_permission(_user, module, _db):
        if module == permissions_core.Module.PLM:
            return permissions_core.PermissionLevel.VIEW
        if module == permissions_core.Module.SPECIAL_CHARACTERISTIC:
            return permissions_core.PermissionLevel.CREATE
        return permissions_core.PermissionLevel.NONE

    monkeypatch.setattr(permissions_core, "get_user_permission", fake_get_user_permission)

    with pytest.raises(HTTPException) as exc:
        await plm_dep(user, db)
    assert exc.value.status_code == 403
    assert await sc_dep(user, db) is user


@pytest.mark.asyncio
async def test_confirm_sc_rejects_missing_pending_link(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part, None])
    user = SimpleNamespace(user_id=uuid.uuid4())

    async def allow_access(_user, _plc, _db):
        return None

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "enforce_product_line_access", allow_access)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            user,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_confirm_sc_rejects_already_confirmed_link(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="confirmed")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part, link])
    user = SimpleNamespace(user_id=uuid.uuid4())

    async def allow_access(_user, _plc, _db):
        return None

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "enforce_product_line_access", allow_access)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            user,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_confirm_sc_rejects_flag_mismatch(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=False, product_line_code="DC-DC-100")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part])
    user = SimpleNamespace(user_id=uuid.uuid4())

    async def allow_access(_user, _plc, _db):
        return None

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "enforce_product_line_access", allow_access)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            user,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_confirm_sc_rejects_product_line_mismatch(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="LINE-A")
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="LINE-B",
        fmea_type="PFMEA",
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part, link, fmea])
    user = SimpleNamespace(user_id=uuid.uuid4())

    async def allow_access(_user, _plc, _db):
        return None

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "enforce_product_line_access", allow_access)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            user,
        )

    assert exc.value.status_code == 400
    assert "Product line mismatch" in exc.value.detail


@pytest.mark.asyncio
async def test_confirm_sc_rejects_missing_fmea_node(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part, link, fmea])
    user = SimpleNamespace(user_id=uuid.uuid4())

    async def allow_access(_user, _plc, _db):
        return None

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "enforce_product_line_access", allow_access)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-999",
                characteristic_type="safety",
            ),
            db,
            user,
        )

    assert exc.value.status_code == 400
    assert "节点" in exc.value.detail


@pytest.mark.asyncio
async def test_confirm_sc_rejects_invalid_fmea_type(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="BAD",
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    db = _FakeDb([part, link, fmea])
    user = SimpleNamespace(user_id=uuid.uuid4())

    async def allow_access(_user, _plc, _db):
        return None

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    monkeypatch.setattr(plm_api, "enforce_product_line_access", allow_access)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id="node-1",
                characteristic_type="safety",
            ),
            db,
            user,
        )

    assert exc.value.status_code == 400
    assert "FMEA 类型" in exc.value.detail


@pytest.mark.asyncio
async def test_confirm_sc_locks_pending_link_row(monkeypatch):
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(part_id=part_id, is_safety_related=True, product_line_code="DC-DC-100")
    link = _sc_link(part_id=part_id, characteristic_type="safety", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    created_sc = SimpleNamespace(sc_id=uuid.uuid4())
    db = _FakeDb([part, link])
    user = SimpleNamespace(user_id=uuid.uuid4())

    async def allow_access(_user, _plc, _db):
        return None

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    async def fake_prepare_special_characteristic(_db, _data, _user_id):
        return created_sc

    monkeypatch.setattr(plm_api, "enforce_product_line_access", allow_access)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "prepare_special_characteristic", fake_prepare_special_characteristic)

    await plm_api.confirm_part_sc(
        part_id,
        plm_schemas.PLMPartConfirmSCRequest(
            fmea_id=fmea_id,
            node_id="node-1",
            characteristic_type="safety",
        ),
        db,
        user,
    )

    compiled_statements = [str(stmt.compile(dialect=postgresql.dialect())) for stmt in db.executed]
    assert any("FOR UPDATE" in sql for sql in compiled_statements)


@pytest.mark.asyncio
async def test_confirm_sc_rejects_oversized_node_id():
    part_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    oversized_node_id = "node-" + "x" * 129

    with pytest.raises(HTTPException) as exc:
        await plm_api.confirm_part_sc(
            part_id,
            plm_schemas.PLMPartConfirmSCRequest(
                fmea_id=fmea_id,
                node_id=oversized_node_id,
                characteristic_type="safety",
            ),
            _FakeDb(),
            SimpleNamespace(user_id=uuid.uuid4()),
        )

    assert exc.value.status_code == 400
    assert "128" in exc.value.detail
```

- [ ] **Step 6: Run backend tests to confirm they fail**

```bash
SECRET_KEY=test-secret python -m pytest backend/tests/test_plm_regressions.py -v
```

Expected: the new PLM part and confirmation tests fail because the endpoint and schema changes do not exist yet.

- [ ] **Step 7: Commit the failing tests**

```bash
git add backend/tests/test_plm_regressions.py
git commit -m "test(plm): add failing SC confirmation and link-exposure tests"
```

---

## Task 5: Implement PLM part SC link exposure and confirm-sc endpoint

**Files:**
- Modify: `backend/app/schemas/plm.py`
- Modify: `backend/app/api/plm.py`

- [ ] **Step 1: Add the PLM SC link response schema**

In `backend/app/schemas/plm.py`, add `PLMPartSCLinkResponse` **above** `PLMPartResponse` so the type name exists before `PLMPartResponse` references it:

```python
class PLMPartSCLinkResponse(BaseModel):
    link_id: uuid.UUID
    characteristic_type: str
    status: str
    sc_id: uuid.UUID | None = None
    confirmed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
```

Then add `PLMPartConfirmSCResponse` before it is used as a FastAPI `response_model`:

```python
class PLMPartConfirmSCResponse(BaseModel):
    status: str
    sc_id: uuid.UUID
    link_id: uuid.UUID
```

- [ ] **Step 2: Attach SC links to PLM part responses**

In `backend/app/schemas/plm.py`, add the new field:

```python
class PLMPartResponse(BaseModel):
    part_id: uuid.UUID
    connection_id: uuid.UUID
    external_id: str
    part_number: str
    name: str
    revision: str
    material: Optional[str] = None
    specification: Optional[str] = None
    status: str
    is_safety_related: bool
    is_key_characteristic: bool
    source_updated_at: Optional[datetime] = None
    product_line_code: Optional[str] = None
    plm_raw_data: Optional[dict[str, Any]] = None
    sc_links: list[PLMPartSCLinkResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 3: Add PLM API imports for the new schema/helper**

In `backend/app/api/plm.py`, ensure these imports exist:

```python
from app.models.plm import (
    PLMBOM,
    PLMChangeImpactTask,
    PLMChangeOrder,
    PLMConnection,
    PLMPart,
    PLMPartFMEALink,
    PLMPartSCLink,
)
from app.services.special_characteristic_service import (
    SafetyApprovalStatus,
    prepare_special_characteristic,
)
```

- [ ] **Step 4: Add a scalar-only PLM part response helper**

Add this helper near the existing small helpers in `backend/app/api/plm.py`. It deliberately constructs the response from scalar fields and the explicitly queried SC links so Pydantic never touches the ORM `part.sc_links` relationship and never triggers async lazy loading.

```python
def _plm_part_response(
    part: PLMPart,
    sc_links: list[PLMPartSCLink],
) -> schemas.PLMPartResponse:
    return schemas.PLMPartResponse.model_validate(
        {
            "part_id": part.part_id,
            "connection_id": part.connection_id,
            "external_id": part.external_id,
            "part_number": part.part_number,
            "name": part.name,
            "revision": part.revision,
            "material": part.material,
            "specification": part.specification,
            "status": part.status,
            "is_safety_related": part.is_safety_related,
            "is_key_characteristic": part.is_key_characteristic,
            "source_updated_at": part.source_updated_at,
            "product_line_code": part.product_line_code,
            "plm_raw_data": part.plm_raw_data,
            "sc_links": [
                schemas.PLMPartSCLinkResponse.model_validate(link)
                for link in sc_links
            ],
        }
    )
```

- [ ] **Step 5: Add explicit SC link loading to `list_parts` and `get_part`**

Replace the final return in `backend/app/api/plm.py:list_parts` with:

```python
    part_list = list(items)
    if not part_list:
        return {
            "items": [],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    part_ids = [part.part_id for part in part_list]
    links_result = await db.execute(
        select(PLMPartSCLink)
        .where(PLMPartSCLink.part_id.in_(part_ids))
        .order_by(PLMPartSCLink.created_at.asc())
    )
    links = links_result.scalars().all()
    links_by_part: dict[uuid.UUID, list[PLMPartSCLink]] = defaultdict(list)
    for link in links:
        links_by_part[link.part_id].append(link)

    return {
        "items": [
            _plm_part_response(part, links_by_part.get(part.part_id, []))
            for part in part_list
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
```

In `backend/app/api/plm.py:get_part`, replace the direct return with:

```python
    links_result = await db.execute(
        select(PLMPartSCLink).where(PLMPartSCLink.part_id == part.part_id)
    )
    links = links_result.scalars().all()
    return _plm_part_response(part, list(links))
```

- [ ] **Step 6: Add the confirmation endpoint**

Add the new endpoint after the existing link/FMEA block in `backend/app/api/plm.py`:

```python
_MAX_NODE_ID_LENGTH = 128
_VALID_FMEA_TYPES = {"DFMEA", "PFMEA"}


@router.post(
    "/parts/{part_id}/confirm-sc",
    response_model=schemas.PLMPartConfirmSCResponse,
)
async def confirm_part_sc(
    part_id: uuid.UUID,
    req: schemas.PLMPartConfirmSCRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(
        require_permission(Module.PLM, PermissionLevel.EDIT)
    ),
    _sc_user: User = Depends(
        require_permission(Module.SPECIAL_CHARACTERISTIC, PermissionLevel.CREATE)
    ),
):
    if len(req.node_id) > _MAX_NODE_ID_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"node_id 长度不能超过 {_MAX_NODE_ID_LENGTH}",
        )

    part_result = await db.execute(select(PLMPart).where(PLMPart.part_id == part_id))
    part = part_result.scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")

    part_plc = part.product_line_code
    if part_plc is None:
        conn_result = await db.execute(
            select(PLMConnection.product_line_code).where(
                PLMConnection.connection_id == part.connection_id
            )
        )
        part_plc = conn_result.scalar_one_or_none()
    await enforce_product_line_access(user, part_plc, db)

    fmea = await get_fmea(db, req.fmea_id)
    if fmea is None:
        raise HTTPException(status_code=404, detail="FMEA not found")
    await enforce_product_line_access(user, fmea.product_line_code, db)

    if fmea.fmea_type not in _VALID_FMEA_TYPES:
        raise HTTPException(status_code=400, detail="FMEA 类型必须是 DFMEA 或 PFMEA")

    if part_plc and fmea.product_line_code and part_plc != fmea.product_line_code:
        raise HTTPException(
            status_code=400,
            detail=f"Product line mismatch: part '{part_plc}' vs FMEA '{fmea.product_line_code}'",
        )

    if req.characteristic_type == "safety" and not part.is_safety_related:
        raise HTTPException(status_code=400, detail="该零件不是安全件，无法确认安全特性")
    if req.characteristic_type == "key_characteristic" and not part.is_key_characteristic:
        raise HTTPException(status_code=400, detail="该零件不是关键特性，无法确认关键特性")

    link_result = await db.execute(
        select(PLMPartSCLink)
        .where(
            PLMPartSCLink.part_id == part.part_id,
            PLMPartSCLink.characteristic_type == req.characteristic_type,
        )
        .with_for_update()
    )
    link = link_result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=400, detail="该零件没有对应的待确认请求")
    if link.status != "pending":
        raise HTTPException(status_code=400, detail="该请求已处理，无法重复确认")

    graph = fmea.graph_data if isinstance(fmea.graph_data, dict) else {}
    graph_nodes = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
    if not any(isinstance(node, dict) and node.get("id") == req.node_id for node in graph_nodes):
        raise HTTPException(status_code=400, detail="目标 FMEA 节点不存在")

    from datetime import datetime, timezone

    sc_type_by_characteristic_type = {
        "safety": "CC",
        "key_characteristic": "SC",
    }
    product_line_code = fmea.product_line_code or part_plc
    if not product_line_code:
        raise HTTPException(status_code=400, detail="无法确定特殊特性的产品线")

    sc_create = schemas_special_characteristic.SCCreate(
        sc_name=part.name or part.part_number,
        sc_type=sc_type_by_characteristic_type[req.characteristic_type],
        source_fmea_id=req.fmea_id,
        source_node_id=req.node_id,
        source_type=fmea.fmea_type,
        product_line_code=product_line_code,
    )

    sc = await prepare_special_characteristic(db, sc_create, user.user_id)
    if req.characteristic_type == "safety":
        sc.is_safety_related = True
        sc.safety_approval_status = SafetyApprovalStatus.PENDING.value

    link.sc_id = sc.sc_id
    link.status = "confirmed"
    link.confirmed_by = user.user_id
    link.confirmed_at = datetime.now(timezone.utc)

    await db.commit()

    return schemas.PLMPartConfirmSCResponse(
        status="confirmed",
        sc_id=sc.sc_id,
        link_id=link.link_id,
    )
```

- [ ] **Step 7: Import the special-characteristic schema namespace**

In `backend/app/api/plm.py`, add:

```python
from app.schemas import special_characteristic as schemas_special_characteristic
```

- [ ] **Step 8: Confirm route dependencies are in the signature**

Verify the final `confirm_part_sc` signature includes both dependency parameters exactly as shown in Step 6:

```python
user: User = Depends(require_permission(Module.PLM, PermissionLevel.EDIT))
_sc_user: User = Depends(require_permission(Module.SPECIAL_CHARACTERISTIC, PermissionLevel.CREATE))
```

Do not place `Depends(...)` assignments inside the function body; FastAPI only runs dependencies declared in the signature.

- [ ] **Step 9: Run backend PLM regression tests**

```bash
SECRET_KEY=test-secret python -m pytest backend/tests/test_plm_regressions.py -v
```

Expected: all PLM confirmation and link-exposure tests pass.

- [ ] **Step 10: Commit backend implementation**

```bash
git add backend/app/schemas/plm.py backend/app/api/plm.py backend/tests/test_plm_regressions.py
git commit -m "feat(plm): add SC link exposure and confirm-sc endpoint"
```

---

## Task 6: Implement frontend types and API client changes

**Files:**
- Modify: `frontend/src/types/plm.ts`
- Modify: `frontend/src/api/plm.ts`

- [ ] **Step 1: Add new PLM types**

In `frontend/src/types/plm.ts`, append:

```typescript
export interface PLMPartSCLink {
  link_id: string;
  characteristic_type: string;
  status: string;
  sc_id: string | null;
  confirmed_at: string | null;
}

export interface PLMPartConfirmSCRequest {
  fmea_id: string;
  node_id: string;
  characteristic_type: "safety" | "key_characteristic";
}

export interface PLMPartConfirmSCResponse {
  status: string;
  sc_id: string;
  link_id: string;
}

export interface PLMBOMImportResponse {
  imported_nodes: number;
  imported_edges: number;
  root: string;
  revision: string;
  bom_revision: string;
  fmea_id: string;
}
```

- [ ] **Step 2: Add SC links to PLMPart**

In `frontend/src/types/plm.ts`, add the new field to `PLMPart`:

```typescript
  plm_raw_data: Record<string, unknown> | null;
  sc_links: PLMPartSCLink[];
}
```

- [ ] **Step 3: Update PLM API imports and confirmation function**

In `frontend/src/api/plm.ts`, import the new types:

```typescript
import type {
  PLMConnection,
  PLMConnectionCreate,
  PLMConnectionUpdate,
  PLMConnectionListResponse,
  PLMConnectionTestResponse,
  PLMPart,
  PLMPartListResponse,
  PLMBOM,
  PLMBOMListResponse,
  PLMBOMTreeResponse,
  PLMChangeOrder,
  PLMChangeOrderListResponse,
  PLMChangeImpactTask,
  PLMDashboard,
  PLMPartConfirmSCRequest,
  PLMPartConfirmSCResponse,
  PLMBOMImportResponse,
} from "../types/plm";
```

- [ ] **Step 4: Replace the inline import response type**

In `frontend/src/api/plm.ts`, replace the existing `importBOMToFMEA` return/response type with `PLMBOMImportResponse`:

```typescript
export async function importBOMToFMEA(
  connectionId: string,
  partNumber: string,
  body: { fmea_id: string; overwrite?: boolean },
  params?: { revision?: string; bom_revision?: string },
): Promise<PLMBOMImportResponse> {
  const resp = await client.post<PLMBOMImportResponse>(
    `/plm/connections/${connectionId}/boms/${encodeURIComponent(partNumber)}/import-to-fmea`,
    body,
    { params },
  );
  return resp.data;
}
```

- [ ] **Step 5: Add the confirmation API call**

Append to `frontend/src/api/plm.ts`:

```typescript
export async function confirmPLMPartSC(
  partId: string,
  body: PLMPartConfirmSCRequest,
): Promise<PLMPartConfirmSCResponse> {
  const resp = await client.post<PLMPartConfirmSCResponse>(
    `/plm/parts/${partId}/confirm-sc`,
    body,
  );
  return resp.data;
}
```

- [ ] **Step 6: Run frontend TypeScript build/tests**

Run from repo root:

```bash
npm --prefix frontend run build
npm --prefix frontend run test -- src/pages/plm/PLMPermissions.test.tsx --run
```

Expected: TypeScript build succeeds; existing/new tests may still fail until the page changes land.

- [ ] **Step 7: Commit frontend type and API changes**

```bash
git add frontend/src/types/plm.ts frontend/src/api/plm.ts
git commit -m "feat(plm): add SC link types and confirm PLM SC API"
```

---

## Task 7: Add failing frontend tests for parts-page BOM and SC flows

**Files:**
- Modify: `frontend/src/pages/plm/PLMPermissions.test.tsx`

> This task intentionally runs after frontend API client changes so `confirmPLMPartSC` exists and red tests fail for missing UI behavior, not for missing exports.

- [ ] **Step 1: Add mock imports for the new PLM API functions**

Append these mock declarations alongside existing PLM API mocks:

```tsx
vi.mocked(plmApi.getPLMParts).mockResolvedValue({
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
});

vi.mocked(plmApi.getPLMBOMTree).mockResolvedValue({
  root: "P-1",
  revision: "A",
  bom_revision: "A",
  items: [],
  total: 0,
});

vi.mocked(plmApi.importBOMToFMEA).mockResolvedValue({
  imported_nodes: 1,
  imported_edges: 0,
  root: "P-1",
  revision: "A",
  bom_revision: "A",
  fmea_id: "fmea-1",
});

vi.mocked(plmApi.confirmPLMPartSC).mockResolvedValue({
  status: "confirmed",
  sc_id: "sc-1",
  link_id: "link-1",
});
```

Also import the page under test:

```tsx
import PLMPartsPage from "./PLMPartsPage";
```

- [ ] **Step 2: Add helpers to seed permissions and a PLM part row with SC links**

Replace the existing `setPLMPermission` helper with a generic permissions helper and keep `setPLMPermission` as a convenience wrapper for older tests:

```tsx
function setPermissions(permissions: Record<string, number>) {
  useAuthStore.setState({
    user: {
      user_id: "u1",
      username: "tester",
      role_key: permissions.plm >= 5 ? "admin" : "quality_engineer",
      permissions,
    } as any,
    token: "test-token",
  });
}

function setPLMPermission(level: number) {
  setPermissions({ plm: level });
}

function seedPartMocks(parts: any[]) {
  vi.mocked(plmApi.getPLMParts).mockResolvedValue({
    items: parts,
    total: parts.length,
    page: 1,
    page_size: 20,
  });
}
```

- [ ] **Step 3: Add failing test that PLM viewers can view BOM but not import or confirm SC**

```tsx
it("allows PLM viewers to view BOM but hides import and SC confirmation", async () => {
  setPermissions({ plm: 1, special_characteristic: 2 });
  seedPartMocks([
    {
      part_id: "part-1",
      connection_id: "conn-1",
      external_id: "ext-1",
      part_number: "P-1",
      name: "Part 1",
      revision: "A",
      material: null,
      specification: null,
      status: "active",
      is_safety_related: true,
      is_key_characteristic: false,
      source_updated_at: null,
      product_line_code: "DC-DC-100",
      plm_raw_data: null,
      sc_links: [
        { link_id: "link-1", characteristic_type: "safety", status: "pending", sc_id: null, confirmed_at: null },
      ],
    },
  ]);

  renderWithApp(<PLMPartsPage />);

  await screen.findByText("Part 1");
  expect(screen.getByText("BOM")).toBeInTheDocument();
  expect(screen.queryByText("导入 FMEA")).not.toBeInTheDocument();
  expect(screen.queryByText("确认SC")).not.toBeInTheDocument();
});
```

- [ ] **Step 4: Add failing test that dual-permission users with pending links see BOM/import/SC actions**

```tsx
it("shows BOM/import/SC actions to users with PLM edit and SC create when pending link exists", async () => {
  setPermissions({ plm: 3, special_characteristic: 2 });
  seedPartMocks([
    {
      part_id: "part-1",
      connection_id: "conn-1",
      external_id: "ext-1",
      part_number: "P-1",
      name: "Part 1",
      revision: "A",
      material: null,
      specification: null,
      status: "active",
      is_safety_related: true,
      is_key_characteristic: false,
      source_updated_at: null,
      product_line_code: "DC-DC-100",
      plm_raw_data: null,
      sc_links: [
        { link_id: "link-1", characteristic_type: "safety", status: "pending", sc_id: null, confirmed_at: null },
      ],
    },
  ]);

  renderWithApp(<PLMPartsPage />);

  await screen.findByText("Part 1");
  expect(screen.getByText("BOM")).toBeInTheDocument();
  expect(screen.getByText("导入 FMEA")).toBeInTheDocument();
  expect(screen.getByText("确认SC")).toBeInTheDocument();
});
```

- [ ] **Step 5: Add failing tests for missing-side frontend permissions and confirmed links**

```tsx
it("hides SC action from PLM editors without SC create permission", async () => {
  setPermissions({ plm: 3, special_characteristic: 1 });
  seedPartMocks([
    {
      part_id: "part-1",
      connection_id: "conn-1",
      external_id: "ext-1",
      part_number: "P-1",
      name: "Part 1",
      revision: "A",
      material: null,
      specification: null,
      status: "active",
      is_safety_related: true,
      is_key_characteristic: false,
      source_updated_at: null,
      product_line_code: "DC-DC-100",
      plm_raw_data: null,
      sc_links: [
        { link_id: "link-1", characteristic_type: "safety", status: "pending", sc_id: null, confirmed_at: null },
      ],
    },
  ]);

  renderWithApp(<PLMPartsPage />);

  await screen.findByText("Part 1");
  expect(screen.getByText("BOM")).toBeInTheDocument();
  expect(screen.getByText("导入 FMEA")).toBeInTheDocument();
  expect(screen.queryByText("确认SC")).not.toBeInTheDocument();
});

it("hides SC action once link is confirmed even if part flag remains true", async () => {
  setPermissions({ plm: 3, special_characteristic: 2 });
  seedPartMocks([
    {
      part_id: "part-1",
      connection_id: "conn-1",
      external_id: "ext-1",
      part_number: "P-1",
      name: "Part 1",
      revision: "A",
      material: null,
      specification: null,
      status: "active",
      is_safety_related: true,
      is_key_characteristic: false,
      source_updated_at: null,
      product_line_code: "DC-DC-100",
      plm_raw_data: null,
      sc_links: [
        { link_id: "link-1", characteristic_type: "safety", status: "confirmed", sc_id: "sc-1", confirmed_at: "2026-06-09T00:00:00Z" },
      ],
    },
  ]);

  renderWithApp(<PLMPartsPage />);

  await screen.findByText("Part 1");
  expect(screen.getByText("BOM")).toBeInTheDocument();
  expect(screen.getByText("导入 FMEA")).toBeInTheDocument();
  expect(screen.queryByText("确认SC")).not.toBeInTheDocument();
});
```

- [ ] **Step 6: Run frontend tests**

Run from repo root:

```bash
npm --prefix frontend run test -- src/pages/plm/PLMPermissions.test.tsx --run
```

Expected: the new tests fail because the PLM parts page does not yet expose those actions or link-driven eligibility.

- [ ] **Step 7: Commit the failing frontend tests**

```bash
git add frontend/src/pages/plm/PLMPermissions.test.tsx
git commit -m "test(plm): add failing frontend parts-page BOM/SC tests"
```

---

## Task 8: Implement PLM parts page BOM and SC flows

**Files:**
- Modify: `frontend/src/pages/plm/PLMPartsPage.tsx`

- [ ] **Step 1: Add required hooks and imports**

Replace the top of `frontend/src/pages/plm/PLMPartsPage.tsx` with:

```tsx
import { useEffect, useState, useCallback } from "react";
import {
  Table,
  Input,
  Button,
  Typography,
  Tag,
  Drawer,
  Descriptions,
  App,
  Modal,
  Form,
  Select,
  Switch,
  Space,
  Tooltip,
} from "antd";
import { ApartmentOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import {
  getPLMParts,
  getPLMBOMTree,
  importBOMToFMEA,
  confirmPLMPartSC,
} from "../../api/plm";
import { useProductLineStore } from "../../store/productLineStore";
import type { PLMPart, PLMBOMTreeNode, PLMPartConfirmSCRequest } from "../../types/plm";
import { usePermission } from "../../hooks/usePermission";
```

- [ ] **Step 2: Add permission and modal state**

Replace the existing top-level state block in `PLMPartsPage` with:

```tsx
export default function PLMPartsPage() {
  const { message } = App.useApp();
  const productLine = useProductLineStore((s) => s.selected);
  const { canEdit, canCreate } = usePermission();
  const canEditPlm = canEdit("plm");
  const canCreateSc = canCreate("special_characteristic");
  const [data, setData] = useState<PLMPart[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [drawerPart, setDrawerPart] = useState<PLMPart | null>(null);
  const [bomPart, setBomPart] = useState<PLMPart | null>(null);
  const [bomItems, setBomItems] = useState<PLMBOMTreeNode[]>([]);
  const [bomLoading, setBomLoading] = useState(false);
  const [bomForm] = Form.useForm();
  const [scPart, setScPart] = useState<PLMPart | null>(null);
  const [scForm] = Form.useForm();
  const [scLoading, setScLoading] = useState(false);
```

- [ ] **Step 3: Add helper to filter pending SC links and reload parts**

Add these helpers immediately below the state declarations:

```tsx
  const pendingScTypes = (part: PLMPart): string[] =>
    (part.sc_links || [])
      .filter((link) => link.status === "pending")
      .map((link) => link.characteristic_type);

  const reload = (p: number, q: string, plCode?: string | null) => {
    fetchData(p, q, plCode);
  };
```

- [ ] **Step 4: Add BOM modal handlers**

Append these handlers below the existing search handler:

```tsx
  const openBomModal = async (part: PLMPart) => {
    setBomPart(part);
    setBomItems([]);
    bomForm.setFieldsValue({
      revision: part.revision || "A",
      bom_revision: part.revision || "A",
    });
    await loadBomTree(part, part.revision || "A", part.revision || "A");
  };

  const loadBomTree = async (part: PLMPart, revision: string, bomRevision: string) => {
    setBomLoading(true);
    try {
      const result = await getPLMBOMTree(part.connection_id, part.part_number, {
        revision,
        bom_revision: bomRevision,
      });
      setBomItems(result.items);
    } catch {
      message.error("未找到该零件的 BOM");
    } finally {
      setBomLoading(false);
    }
  };

  const refreshBomTree = async () => {
    if (!bomPart) return;
    const { revision, bom_revision } = bomForm.getFieldsValue();
    await loadBomTree(bomPart, revision || "A", bom_revision || "A");
  };

  const handleImportToFMEA = async (values: { fmea_id: string; overwrite?: boolean }) => {
    if (!bomPart) return;
    const { revision, bom_revision } = bomForm.getFieldsValue();
    try {
      await importBOMToFMEA(
        bomPart.connection_id,
        bomPart.part_number,
        { fmea_id: values.fmea_id, overwrite: values.overwrite },
        { revision, bom_revision },
      );
      message.success("BOM 导入 FMEA 成功");
    } catch {
      message.error("BOM 导入 FMEA 失败");
    }
  };
```

- [ ] **Step 5: Add SC confirmation modal handler**

Append these handlers below the BOM handlers:

```tsx
  const openScModal = (part: PLMPart) => {
    setScPart(part);
    const pendingTypes = pendingScTypes(part);
    scForm.setFieldsValue({
      characteristic_type: pendingTypes.length === 1 ? pendingTypes[0] : undefined,
      fmea_id: undefined,
      node_id: undefined,
    });
  };

  const handleConfirmSC = async (values: PLMPartConfirmSCRequest) => {
    if (!scPart) return;
    setScLoading(true);
    try {
      await confirmPLMPartSC(scPart.part_id, values);
      message.success("特殊特性已确认");
      setScPart(null);
      reload(page, search, productLine);
    } catch {
      message.error("确认特殊特性失败");
    } finally {
      setScLoading(false);
    }
  };
```

- [ ] **Step 6: Add row action buttons for BOM and SC confirmation**

Replace the existing `columns` action block with:

```typescript
    {
      title: "操作",
      key: "actions",
      width: 260,
      render: (_: unknown, record: PLMPart) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => setDrawerPart(record)}>
            详情
          </Button>
          <Button type="link" size="small" icon={<ApartmentOutlined />} onClick={() => openBomModal(record)}>
            BOM
          </Button>
          {canEditPlm && (
            <Button type="link" size="small" onClick={() => openBomModal(record)}>
              导入 FMEA
            </Button>
          )}
          {canEditPlm && canCreateSc && pendingScTypes(record).length > 0 && (
            <Tooltip title="确认 pending 特殊特性请求">
              <Button type="link" size="small" icon={<SafetyCertificateOutlined />} onClick={() => openScModal(record)}>
                确认SC
              </Button>
            </Tooltip>
          )}
        </Space>
      ),
    },
```

- [ ] **Step 7: Add BOM and SC modals to the page output**

After the existing `</Drawer>`, add:

```tsx
      <Modal
        title={bomPart ? `${bomPart.part_number} BOM` : "BOM"}
        open={!!bomPart}
        onCancel={() => setBomPart(null)}
        footer={null}
        width={720}
      >
        {bomPart && (
          <Space direction="vertical" size="middle" style={{ width: "100%" }}>
            <Form form={bomForm} layout="inline">
              <Form.Item name="revision" label="零件版本" rules={[{ required: true }]}> 
                <Input style={{ width: 140 }} />
              </Form.Item>
              <Form.Item name="bom_revision" label="BOM 版本" rules={[{ required: true }]}> 
                <Input style={{ width: 140 }} />
              </Form.Item>
              <Form.Item>
                <Button onClick={refreshBomTree} loading={bomLoading}>查询 BOM</Button>
              </Form.Item>
            </Form>

            <Table<PLMBOMTreeNode>
              size="small"
              loading={bomLoading}
              dataSource={bomItems}
              rowKey={(row) => `${row.parent_part_number}-${row.parent_revision}-${row.child_part_number}-${row.child_revision}-${row.bom_revision}`}
              pagination={false}
              columns={[
                { title: "父件", dataIndex: "parent_part_number", key: "parent_part_number" },
                { title: "子件", dataIndex: "child_part_number", key: "child_part_number" },
                { title: "数量", dataIndex: "quantity", key: "quantity", width: 90 },
                { title: "层级", dataIndex: "level", key: "level", width: 90 },
                { title: "BOM 版本", dataIndex: "bom_revision", key: "bom_revision", width: 120 },
              ]}
            />

            {canEditPlm && (
              <Form layout="inline" onFinish={handleImportToFMEA}>
                <Form.Item name="fmea_id" label="目标 FMEA ID" rules={[{ required: true, message: "请输入 FMEA ID" }]}>
                  <Input style={{ width: 260 }} />
                </Form.Item>
                <Form.Item name="overwrite" label="覆盖已有图形" valuePropName="checked">
                  <Switch />
                </Form.Item>
                <Form.Item>
                  <Button type="primary" htmlType="submit">导入 FMEA</Button>
                </Form.Item>
              </Form>
            )}
          </Space>
        )}
      </Modal>

      <Modal
        title="确认特殊特性"
        open={!!scPart}
        onCancel={() => setScPart(null)}
        onOk={() => scForm.submit()}
        confirmLoading={scLoading}
      >
        {scPart && (
          <Form form={scForm} layout="vertical" onFinish={handleConfirmSC}>
            <Form.Item name="characteristic_type" label="特性类型" rules={[{ required: true, message: "请选择特性类型" }]}>
              <Select
                options={pendingScTypes(scPart).map((t) => ({
                  value: t,
                  label: t === "safety" ? "安全特性" : "关键特性",
                }))}
              />
            </Form.Item>
            <Form.Item name="fmea_id" label="目标 FMEA ID" rules={[{ required: true, message: "请输入 FMEA ID" }]}>
              <Input />
            </Form.Item>
            <Form.Item name="node_id" label="FMEA 节点 ID" rules={[{ required: true, message: "请输入节点 ID" }]}>
              <Input />
            </Form.Item>
          </Form>
        )}
      </Modal>
```

- [ ] **Step 8: Run frontend tests and build**

Run from repo root:

```bash
npm --prefix frontend run build
npm --prefix frontend run test -- src/pages/plm/PLMPermissions.test.tsx --run
```

Expected: the new frontend tests pass, and the TypeScript build succeeds.

- [ ] **Step 9: Commit frontend implementation**

```bash
git add frontend/src/pages/plm/PLMPartsPage.tsx frontend/src/pages/plm/PLMPermissions.test.tsx
git commit -m "feat(plm): add parts-page BOM and SC confirmation flows"
```

---

## Task 9: Update backend regression tests for key-characteristic confirmation

**Files:**
- Modify: `backend/tests/test_plm_regressions.py`

- [ ] **Step 1: Add test for key-characteristic confirmation success**

```python
@pytest.mark.asyncio
async def test_confirm_sc_creates_key_characteristic_sc(monkeypatch):
    part_id = uuid.uuid4()
    connection_id = uuid.uuid4()
    fmea_id = uuid.uuid4()
    part = _part(
        part_id=part_id,
        connection_id=connection_id,
        is_key_characteristic=True,
        product_line_code="DC-DC-100",
    )
    link = _sc_link(part_id=part_id, characteristic_type="key_characteristic", status="pending")
    fmea = SimpleNamespace(
        fmea_id=fmea_id,
        product_line_code="DC-DC-100",
        fmea_type="PFMEA",
        graph_data={"nodes": [{"id": "node-1"}], "edges": []},
    )
    created_sc = SimpleNamespace(sc_id=uuid.uuid4())
    db = _FakeDb([part, link])
    user = SimpleNamespace(user_id=uuid.uuid4())

    async def allow_access(_user, _plc, _db):
        return None

    async def fake_get_fmea(_db, requested_fmea_id):
        assert requested_fmea_id == fmea_id
        return fmea

    async def fake_prepare_special_characteristic(_db, _data, _user_id):
        return created_sc

    monkeypatch.setattr(plm_api, "enforce_product_line_access", allow_access)
    monkeypatch.setattr(plm_api, "get_fmea", fake_get_fmea)
    monkeypatch.setattr(plm_api, "prepare_special_characteristic", fake_prepare_special_characteristic)

    result = await plm_api.confirm_part_sc(
        part_id,
        plm_schemas.PLMPartConfirmSCRequest(
            fmea_id=fmea_id,
            node_id="node-1",
            characteristic_type="key_characteristic",
        ),
        db,
        user,
    )

    assert result.status == "confirmed"
    assert result.sc_id == created_sc.sc_id
    assert link.status == "confirmed"
    assert link.sc_id == created_sc.sc_id
```

- [ ] **Step 2: Run backend PLM regression tests**

```bash
SECRET_KEY=test-secret python -m pytest backend/tests/test_plm_regressions.py -v
```

Expected: new key-characteristic confirmation test passes.

- [ ] **Step 3: Commit backend test additions**

```bash
git add backend/tests/test_plm_regressions.py
git commit -m "test(plm): cover key-characteristic SC confirmation path"
```

---

## Task 10: Run full backend/frontend regression and finalize

**Files:**
- Modify: `backend/tests/test_plm_regressions.py` (if needed for small fixes)
- Modify: `frontend/src/pages/plm/PLMPartsPage.tsx` (if needed for small fixes)

- [ ] **Step 1: Run the backend PLM regression tests**

```bash
SECRET_KEY=test-secret python -m pytest backend/tests/test_plm_regressions.py -v
```

Expected: all PLM regression tests pass.

- [ ] **Step 2: Run the frontend tests**

Run from repo root:

```bash
npm --prefix frontend run test -- src/pages/plm/PLMPermissions.test.tsx --run
```

Expected: all PLM permission and parts-page tests pass.

- [ ] **Step 3: Run the frontend build**

```bash
npm --prefix frontend run build
```

Expected: TypeScript build succeeds with no errors.

- [ ] **Step 4: Commit any final cleanup changes if edits were required**

```bash
git add -A
git commit -m "fix(plm): finalize BOM and SC confirmation integration"
```

If no additional edits were needed, mark this commit step complete without creating a new commit.
