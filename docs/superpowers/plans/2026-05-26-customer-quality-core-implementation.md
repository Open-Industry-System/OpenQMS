# Customer Quality Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 2 customer quality core loop: customer master data, complaints, RMA, CAPA/FMEA links, risk dashboard, frontend workspace, and ROADMAP updates.

**Architecture:** Follow the existing OpenQMS four-layer backend pattern: SQLAlchemy models, Pydantic schemas, service functions with manual `AuditLog`, and thin FastAPI routes. Frontend follows existing Ant Design page/API/type patterns and the global product line filter.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, Alembic, PostgreSQL JSONB, pytest/manual backend tests, React 18, TypeScript, Ant Design, Vite.

---

## File Structure

Backend files:

- Create `backend/app/models/customer_quality.py`: `Customer`, `CustomerComplaint`, `RMARecord` ORM models.
- Modify `backend/app/models/__init__.py`: export the new models.
- Create `backend/app/schemas/customer_quality.py`: request/response/list/dashboard schemas and validators.
- Modify `backend/app/schemas/__init__.py`: import `customer_quality`.
- Create `backend/app/services/customer_quality_service.py`: pure functions, CRUD, status transitions, CAPA/FMEA linking, dashboard metrics, audit logging.
- Create `backend/app/api/customer_quality.py`: `/api/customers`, `/api/customer-complaints`, `/api/rma-records`, `/api/customer-quality/*` routes.
- Modify `backend/app/main.py`: include the customer quality router.
- Create `backend/alembic/versions/021_customer_quality_core.py`: migration for the three tables and indexes.
- Modify `backend/app/seed.py`: add customer quality demo data after existing product lines, users, FMEA, and CAPA seed data.
- Create `backend/tests/test_customer_quality.py`: pure function tests for states, overdue, PPM, and risk lights.

Frontend files:

- Modify `frontend/src/types/index.ts`: add customer quality interfaces.
- Create `frontend/src/api/customerQuality.ts`: typed API functions.
- Create `frontend/src/pages/customerQuality/CustomerQualityPage.tsx`: workspace with KPI, customer list, tabs, create/edit modals.
- Create `frontend/src/pages/customerQuality/ComplaintDetailPage.tsx`: complaint detail and CAPA/FMEA/status actions.
- Create `frontend/src/pages/customerQuality/RMADetailPage.tsx`: RMA detail and link/status actions.
- Modify `frontend/src/App.tsx`: add routes.
- Modify `frontend/src/components/layout/AppLayout.tsx`: add menu item.

Docs:

- Modify `docs/ROADMAP.md`: mark customer quality core items complete and add follow-up plan for reserved interfaces.

---

## Task 1: Customer Quality Pure Rules

**Files:**
- Create: `backend/tests/test_customer_quality.py`
- Create: `backend/app/services/customer_quality_service.py`

- [ ] **Step 1: Write failing tests for state transitions, overdue, PPM, and risk lights**

Create `backend/tests/test_customer_quality.py`:

```python
from datetime import date, timedelta

import pytest

from app.services.customer_quality_service import (
    ComplaintStatus,
    RMAStatus,
    calculate_customer_ppm,
    complaint_is_overdue,
    transition_complaint_status,
    transition_rma_status,
    calculate_risk_light,
)


def test_complaint_status_transitions():
    assert transition_complaint_status("open", "start_investigation") == "investigating"
    assert transition_complaint_status("investigating", "mark_responded") == "responded"
    assert transition_complaint_status("responded", "close") == "closed"
    assert transition_complaint_status("open", "cancel") == "cancelled"
    with pytest.raises(ValueError, match="invalid complaint transition"):
        transition_complaint_status("closed", "start_investigation")


def test_rma_status_transitions():
    assert transition_rma_status("open", "start_analysis") == "analysis"
    assert transition_rma_status("analysis", "mark_action_pending") == "action_pending"
    assert transition_rma_status("action_pending", "close") == "closed"
    assert transition_rma_status("open", "cancel") == "cancelled"
    with pytest.raises(ValueError, match="invalid RMA transition"):
        transition_rma_status("closed", "start_analysis")


def test_complaint_overdue_excludes_closed_and_cancelled():
    yesterday = date.today() - timedelta(days=1)
    assert complaint_is_overdue("open", yesterday) is True
    assert complaint_is_overdue("investigating", yesterday) is True
    assert complaint_is_overdue("closed", yesterday) is False
    assert complaint_is_overdue("cancelled", yesterday) is False
    assert complaint_is_overdue("open", None) is False


def test_ppm_returns_none_without_shipment_denominator():
    assert calculate_customer_ppm(impact_qty=5, independent_rma_qty=2, shipment_qty=None, annual_shipment_qty=None, date_from=None, date_to=None) is None


def test_ppm_uses_explicit_window_shipment_without_prorating():
    result = calculate_customer_ppm(impact_qty=5, independent_rma_qty=5, shipment_qty=1000, annual_shipment_qty=365000, date_from=date(2026, 1, 1), date_to=date(2026, 1, 10))
    assert result == 10000.0


def test_ppm_prorates_annual_shipment_by_inclusive_window():
    result = calculate_customer_ppm(impact_qty=10, independent_rma_qty=0, shipment_qty=None, annual_shipment_qty=36500, date_from=date(2026, 1, 1), date_to=date(2026, 1, 10))
    assert result == 10000.0


def test_risk_light_priority():
    assert calculate_risk_light(open_fatal_count=1, overdue_count=0, open_count=0, ppm=None, ppm_target=100) == "red"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=1, open_count=0, ppm=None, ppm_target=100) == "red"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=0, open_count=0, ppm=250, ppm_target=100) == "red"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=0, open_count=1, ppm=None, ppm_target=100) == "yellow"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=0, open_count=0, ppm=120, ppm_target=100) == "yellow"
    assert calculate_risk_light(open_fatal_count=0, overdue_count=0, open_count=0, ppm=80, ppm_target=100) == "green"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
pytest tests/test_customer_quality.py -v
```

Expected: FAIL during import because `customer_quality_service` or the listed functions do not exist.

- [ ] **Step 3: Implement minimal pure functions**

Create `backend/app/services/customer_quality_service.py` with this initial content:

```python
from datetime import date, timedelta
from enum import StrEnum


class ComplaintStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESPONDED = "responded"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class RMAStatus(StrEnum):
    OPEN = "open"
    ANALYSIS = "analysis"
    ACTION_PENDING = "action_pending"
    CLOSED = "closed"
    CANCELLED = "cancelled"


COMPLAINT_TRANSITIONS = {
    ("open", "start_investigation"): "investigating",
    ("investigating", "mark_responded"): "responded",
    ("responded", "close"): "closed",
    ("open", "cancel"): "cancelled",
    ("investigating", "cancel"): "cancelled",
    ("responded", "start_investigation"): "investigating",
}

RMA_TRANSITIONS = {
    ("open", "start_analysis"): "analysis",
    ("analysis", "mark_action_pending"): "action_pending",
    ("action_pending", "close"): "closed",
    ("open", "cancel"): "cancelled",
    ("analysis", "cancel"): "cancelled",
}


def transition_complaint_status(current_status: str, action: str) -> str:
    try:
        return COMPLAINT_TRANSITIONS[(current_status, action)]
    except KeyError:
        raise ValueError(f"invalid complaint transition: {current_status} + {action}") from None


def transition_rma_status(current_status: str, action: str) -> str:
    try:
        return RMA_TRANSITIONS[(current_status, action)]
    except KeyError:
        raise ValueError(f"invalid RMA transition: {current_status} + {action}") from None


def complaint_is_overdue(status: str, due_date: date | None, today: date | None = None) -> bool:
    if status in ("closed", "cancelled") or due_date is None:
        return False
    return due_date < (today or date.today())


def _default_window(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    end = date_to or date.today()
    start = date_from or (end - timedelta(days=89))
    return start, end


def calculate_customer_ppm(
    *,
    impact_qty: int,
    independent_rma_qty: int,
    shipment_qty: int | None,
    annual_shipment_qty: int | None,
    date_from: date | None,
    date_to: date | None,
) -> float | None:
    numerator = max(0, impact_qty) + max(0, independent_rma_qty)
    if shipment_qty is not None:
        denominator = float(shipment_qty)
    elif annual_shipment_qty is not None:
        start, end = _default_window(date_from, date_to)
        period_days = (end - start).days + 1
        if period_days <= 0:
            return None
        denominator = float(annual_shipment_qty) * (period_days / 365.0)
    else:
        return None

    if denominator <= 0:
        return None
    return round((numerator / denominator) * 1_000_000, 2)


def calculate_risk_light(
    *,
    open_fatal_count: int,
    overdue_count: int,
    open_count: int,
    ppm: float | None,
    ppm_target: float | None,
) -> str:
    if open_fatal_count > 0 or overdue_count > 0:
        return "red"
    if ppm is not None and ppm_target is not None and ppm > ppm_target * 2:
        return "red"
    if open_count > 0:
        return "yellow"
    if ppm is not None and ppm_target is not None and ppm > ppm_target:
        return "yellow"
    return "green"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd backend
pytest tests/test_customer_quality.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_customer_quality.py backend/app/services/customer_quality_service.py
git commit -m "test: add customer quality rule coverage"
```

---

## Task 2: Database Models and Migration

**Files:**
- Modify: `backend/app/services/customer_quality_service.py`
- Create: `backend/app/models/customer_quality.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/021_customer_quality_core.py`
- Test: `backend/tests/test_customer_quality.py`

- [ ] **Step 1: Extend tests to verify model imports**

Append to `backend/tests/test_customer_quality.py`:

```python
def test_customer_quality_models_have_table_names():
    from app.models.customer_quality import Customer, CustomerComplaint, RMARecord

    assert Customer.__tablename__ == "customers"
    assert CustomerComplaint.__tablename__ == "customer_complaints"
    assert RMARecord.__tablename__ == "rma_records"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
pytest tests/test_customer_quality.py::test_customer_quality_models_have_table_names -v
```

Expected: FAIL because `app.models.customer_quality` does not exist.

- [ ] **Step 3: Create ORM models**

Create `backend/app/models/customer_quality.py`:

```python
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    segment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    csr_list: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    ppm_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    annual_shipment_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    complaints = relationship("CustomerComplaint", back_populates="customer")
    rma_records = relationship("RMARecord", back_populates="customer")


class CustomerComplaint(Base):
    __tablename__ = "customer_complaints"

    complaint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    complaint_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), ForeignKey("product_lines.code"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    batch_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    defect_desc: Mapped[str] = mapped_column(Text, nullable=False)
    impact_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    occurred_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    fmea_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id"), nullable=True)
    capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id"), nullable=True)
    has_rma: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preliminary_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    supplier_responsibility: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scar_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer", back_populates="complaints")
    rma_records = relationship("RMARecord", back_populates="complaint")


class RMARecord(Base):
    __tablename__ = "rma_records"

    rma_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rma_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    product_line_code: Mapped[str] = mapped_column(String(20), ForeignKey("product_lines.code"), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.customer_id"), nullable=False)
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_complaints.complaint_id"), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    batch_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    return_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    defect_type: Mapped[str] = mapped_column(String(50), nullable=False)
    responsibility: Mapped[str | None] = mapped_column(String(50), nullable=True)
    analysis_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    fmea_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fmea_documents.fmea_id"), nullable=True)
    capa_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("capa_eightd.report_id"), nullable=True)
    scar_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    attachments: Mapped[list | None] = mapped_column(JSONB, default=list, nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    customer = relationship("Customer", back_populates="rma_records")
    complaint = relationship("CustomerComplaint", back_populates="rma_records")
```

- [ ] **Step 4: Export models**

Modify `backend/app/models/__init__.py`:

```python
from app.models.customer_quality import Customer, CustomerComplaint, RMARecord
```

Add to `__all__`:

```python
"Customer", "CustomerComplaint", "RMARecord",
```

- [ ] **Step 5: Add Alembic migration**

Create `backend/alembic/versions/021_customer_quality_core.py` with tables, indexes, and check constraints matching the model and spec. The current migration head is `020`, so use:

```python
revision = "021_customer_quality_core"
down_revision = "020"
branch_labels = None
depends_on = None
```

- [ ] **Step 6: Run model test**

Run:

```bash
cd backend
pytest tests/test_customer_quality.py::test_customer_quality_models_have_table_names -v
```

Expected: PASS.

- [ ] **Step 7: Run migration syntax check**

Run:

```bash
cd backend
python -m py_compile alembic/versions/021_customer_quality_core.py
```

Expected: no output and exit code 0.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/customer_quality.py backend/app/models/__init__.py backend/alembic/versions/021_customer_quality_core.py backend/tests/test_customer_quality.py
git commit -m "feat: add customer quality data model"
```

---

## Task 3: Schemas and Service CRUD

**Files:**
- Create: `backend/app/schemas/customer_quality.py`
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/services/customer_quality_service.py`
- Test: `backend/tests/test_customer_quality.py`

- [ ] **Step 1: Add schema validation tests**

Append to `backend/tests/test_customer_quality.py`:

```python
def test_complaint_schema_rejects_invalid_category():
    from app.schemas.customer_quality import ComplaintCreate
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ComplaintCreate(
            complaint_no="CC-2026-001",
            product_line_code="DC-DC-100",
            customer_id="00000000-0000-0000-0000-000000000001",
            category="bad",
            severity="一般",
            defect_desc="功能异常",
            received_date=date.today(),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_customer_quality.py::test_complaint_schema_rejects_invalid_category -v
```

Expected: FAIL because `app.schemas.customer_quality` does not exist.

- [ ] **Step 3: Create Pydantic schemas**

Create `backend/app/schemas/customer_quality.py`. Include:

- `CustomerCreate`, `CustomerUpdate`, `CustomerResponse`, `CustomerListResponse`, `CustomerSummaryResponse`
- `ComplaintCreate`, `ComplaintUpdate`, `ComplaintResponse`, `ComplaintListResponse`
- `RMARecordCreate`, `RMARecordUpdate`, `RMARecordResponse`, `RMARecordListResponse`
- `CustomerQualityDashboardResponse`

Use validators for:

```python
VALID_CATEGORIES = {"safety", "function", "appearance", "delivery"}
VALID_SEVERITIES = {"致命", "严重", "一般", "轻微"}
VALID_COMPLAINT_STATUSES = {"open", "investigating", "responded", "closed", "cancelled"}
VALID_RMA_STATUSES = {"open", "analysis", "action_pending", "closed", "cancelled"}
VALID_RESPONSIBILITIES = {"supplier", "internal", "transport", "customer_misuse", "unknown"}
```

- [ ] **Step 4: Export schema module**

Modify `backend/app/schemas/__init__.py`:

```python
from app.schemas import customer_quality
```

- [ ] **Step 5: Extend service with CRUD and query functions**

In `backend/app/services/customer_quality_service.py`, keep the pure functions from Task 1 and add:

- `_audit(db, table_name, record_id, action, user_id, changed_fields)`
- `list_customers`, `get_customer`, `create_customer`, `update_customer`, `customer_summary`
- `list_complaints`, `get_complaint`, `create_complaint`, `update_complaint`, `transition_complaint`, `link_complaint_capa`, `link_complaint_fmea`, `create_capa_from_complaint`
- `list_rma_records`, `get_rma_record`, `create_rma_record`, `update_rma_record`, `transition_rma`, `link_rma_complaint`, `link_rma_capa`, `link_rma_fmea`
- `dashboard`

Use existing helpers:

```python
from app.services.product_line_service import validate_product_line
from app.services import capa_service
from app.models.audit import AuditLog
```

For every create/update/transition/link operation, write `AuditLog`.

- [ ] **Step 6: Run schema and pure tests**

Run:

```bash
cd backend
pytest tests/test_customer_quality.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/customer_quality.py backend/app/schemas/__init__.py backend/app/services/customer_quality_service.py backend/tests/test_customer_quality.py
git commit -m "feat: add customer quality schemas and service"
```

---

## Task 4: FastAPI Routes

**Files:**
- Create: `backend/app/api/customer_quality.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add customer quality router**

Create `backend/app/api/customer_quality.py` with one `APIRouter(tags=["customer-quality"])` and route groups for:

- `/api/customers`
- `/api/customer-complaints`
- `/api/rma-records`
- `/api/customer-quality/dashboard`
- `/api/customer-quality/customers/{customer_id}/trend`

Use permission dependencies:

```python
get_current_user
require_engineer_or_admin
require_manager_or_admin
```

Close routes use `require_manager_or_admin`. Create/update/link/status-action routes use `require_engineer_or_admin`. List/detail/dashboard routes use `get_current_user`.

- [ ] **Step 2: Register router**

Modify `backend/app/main.py`:

```python
from app.api.customer_quality import router as customer_quality_router
```

Add:

```python
app.include_router(customer_quality_router)
```

- [ ] **Step 3: Verify route import**

Run:

```bash
cd backend
python - <<'PY'
from app.main import app
paths = {route.path for route in app.routes}
assert "/api/customers" in paths
assert "/api/customer-complaints" in paths
assert "/api/rma-records" in paths
assert "/api/customer-quality/dashboard" in paths
print("customer quality routes registered")
PY
```

Expected output:

```text
customer quality routes registered
```

- [ ] **Step 4: Run backend tests**

Run:

```bash
cd backend
pytest tests/test_customer_quality.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/customer_quality.py backend/app/main.py
git commit -m "feat: expose customer quality APIs"
```

---

## Task 5: Seed Data

**Files:**
- Modify: `backend/app/seed.py`

- [ ] **Step 1: Add seed data**

Modify `backend/app/seed.py` to import:

```python
from app.models.customer_quality import Customer, CustomerComplaint, RMARecord
```

After users, product lines, FMEA, and CAPA seed data exist, add:

- 2 customers with `annual_shipment_qty` and `ppm_target`.
- 3 complaints: one fatal open, one overdue investigating, one closed.
- 2 RMA records: one linked to a complaint and one independent.

Use attachment metadata like:

```python
[{"file_name": "defect-photo.jpg", "file_url": "https://example.com/defect-photo.jpg", "uploaded_at": "2026-05-26T10:00:00Z", "uploaded_by": "seed", "category": "photo"}]
```

- [ ] **Step 2: Run seed import check**

Run:

```bash
cd backend
python -m py_compile app/seed.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Commit**

```bash
git add backend/app/seed.py
git commit -m "chore: seed customer quality demo data"
```

---

## Task 6: Frontend Types and API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/customerQuality.ts`

- [ ] **Step 1: Add TypeScript types**

Modify `frontend/src/types/index.ts` to add:

- `Customer`
- `CustomerComplaint`
- `RMARecord`
- `CustomerSummary`
- `CustomerQualityDashboard`
- `CustomerListResponse`
- `ComplaintListResponse`
- `RMARecordListResponse`

Fields must match `backend/app/schemas/customer_quality.py`.

- [ ] **Step 2: Add API functions**

Create `frontend/src/api/customerQuality.ts` with:

- `listCustomers`
- `getCustomer`
- `createCustomer`
- `updateCustomer`
- `getCustomerSummary`
- `listComplaints`
- `getComplaint`
- `createComplaint`
- `updateComplaint`
- `startComplaintInvestigation`
- `markComplaintResponded`
- `cancelComplaint`
- `closeComplaint`
- `linkComplaintCAPA`
- `createCAPAFromComplaint`
- `linkComplaintFMEA`
- `listRMARecords`
- `getRMARecord`
- `createRMARecord`
- `updateRMARecord`
- `startRMAAnalysis`
- `markRMAActionPending`
- `cancelRMA`
- `closeRMA`
- `linkRMAComplaint`
- `linkRMACAPA`
- `linkRMAFMEA`
- `getCustomerQualityDashboard`
- `getCustomerTrend`

Use the existing `client` from `frontend/src/api/client.ts`.

- [ ] **Step 3: Run frontend type check**

Run:

```bash
cd frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/customerQuality.ts
git commit -m "feat: add customer quality frontend API"
```

---

## Task 7: Customer Quality Frontend Workspace

**Files:**
- Create: `frontend/src/pages/customerQuality/CustomerQualityPage.tsx`
- Create: `frontend/src/pages/customerQuality/ComplaintDetailPage.tsx`
- Create: `frontend/src/pages/customerQuality/RMADetailPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Create workspace page**

Create `CustomerQualityPage.tsx` with:

- KPI row for total customers, open complaints, overdue complaints, RMA count, impact quantity.
- Customer table with risk light, customer code, name, open complaint count.
- Tabs for overview, complaints, RMA, and profile.
- Create/edit modals for customer, complaint, and RMA.
- "我的待办" filter using `assignee_id = user.user_id`.
- Product line filter integration via `useProductLineStore`.

- [ ] **Step 2: Create complaint detail page**

Create `ComplaintDetailPage.tsx` with:

- Basic fields including batch, serial number, occurred date, assignee, attachments metadata.
- Status action buttons.
- CAPA/FMEA link inputs.
- Create CAPA action.
- Close action hidden from non-manager/non-admin users.

- [ ] **Step 3: Create RMA detail page**

Create `RMADetailPage.tsx` with:

- Basic fields including batch, serial number, tracking number, assignee, attachments metadata.
- Status action buttons.
- Complaint/CAPA/FMEA link inputs.
- Close action hidden from non-manager/non-admin users.

- [ ] **Step 4: Wire routes**

Modify `frontend/src/App.tsx`:

```tsx
import CustomerQualityPage from "./pages/customerQuality/CustomerQualityPage";
import ComplaintDetailPage from "./pages/customerQuality/ComplaintDetailPage";
import RMADetailPage from "./pages/customerQuality/RMADetailPage";
```

Add routes:

```tsx
<Route path="/customer-quality" element={<CustomerQualityPage />} />
<Route path="/customer-quality/complaints/:id" element={<ComplaintDetailPage />} />
<Route path="/customer-quality/rma/:id" element={<RMADetailPage />} />
```

- [ ] **Step 5: Add sidebar menu**

Modify `frontend/src/components/layout/AppLayout.tsx`:

```tsx
import { CustomerServiceOutlined } from "@ant-design/icons";
```

Add menu item:

```tsx
{ key: "/customer-quality", icon: <CustomerServiceOutlined />, label: "客户质量" },
```

- [ ] **Step 6: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/customerQuality frontend/src/App.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat: add customer quality workspace"
```

---

## Task 8: ROADMAP and Final Verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update ROADMAP**

Modify Phase 2 rows:

- `客诉管理`: status `✅ 完成`, note `客诉接单 + 分类/严重等级 + 批次追溯 + 处理人 + 附件元数据 + 超期预警 + CAPA/FMEA 联动；SCAR 接口预留`
- `RMA 退货管理`: status `✅ 完成`, note `退货登记 + 批次/序列号 + 物流单号 + 不良分析 + 责任判定 + CAPA/FMEA 联动；SCAR 接口预留`
- `客户质量看板`: status `✅ 完成`, note `基于客诉/RMA 的投诉数、退货量、风险灯号、PPM 估算；0 公里 PPM/发运数据接口后续增强`

Add a short Phase 2 follow-up note below the table:

```markdown
**客户质量后续计划**:
1. SCAR 管理接入 `scar_ref_id`，支持供应商责任客诉/RMA 一键创建 SCAR。
2. 客户审核管理复用客户档案、CAPA 联动和附件元数据。
3. CSR/VOC 使用 `customers.csr_list`，后续同步控制计划。
4. 0 公里 PPM 引入发运和客户端接收质量数据源，替换临时 `shipment_qty` 参数。
5. 高级客户质量看板融合 SPC CPK、保修、满意度和客户审核数据。
```

- [ ] **Step 2: Run backend tests**

Run:

```bash
cd backend
pytest tests/test_customer_quality.py -v
```

Expected: PASS.

- [ ] **Step 3: Run backend import smoke**

Run:

```bash
cd backend
python - <<'PY'
from app.main import app
paths = {route.path for route in app.routes}
for path in ["/api/customers", "/api/customer-complaints", "/api/rma-records", "/api/customer-quality/dashboard"]:
    assert path in paths, path
print("customer quality backend smoke passed")
PY
```

Expected:

```text
customer quality backend smoke passed
```

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs: update roadmap for customer quality core"
```

---

## Self-Review Checklist

Spec coverage:

- Customer master data: Task 2, Task 3, Task 4, Task 7.
- Complaints: Task 1 through Task 7.
- RMA: Task 1 through Task 7.
- Attachments metadata: Task 2, Task 3, Task 7.
- Batch/serial tracking: Task 2, Task 3, Task 7.
- Assignee and "我的待办": Task 2, Task 3, Task 7.
- CAPA/FMEA linking: Task 3, Task 4, Task 7.
- PPM prorating and risk lights: Task 1, Task 3, Task 4, Task 7.
- Reserved SCAR/CSR/0公里 PPM interfaces: Task 2, Task 3, Task 8.
- ROADMAP update: Task 8.

Placeholder scan:

- No incomplete markers or intentionally vague implementation steps.

Type consistency:

- Backend model, schema, service, API, and frontend type names use `Customer`, `CustomerComplaint`, and `RMARecord`.
- Status values match the design spec: complaints use `open/investigating/responded/closed/cancelled`; RMA uses `open/analysis/action_pending/closed/cancelled`.
