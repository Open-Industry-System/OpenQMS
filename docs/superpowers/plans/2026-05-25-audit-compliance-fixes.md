# Audit Compliance Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix ~30 audit defects across 12 modules: add missing DB fields, create new tables (PPAP/IQC/SCAR/checklist templates), enforce cross-module linkages, and fix data isolation gaps.

**Architecture:** Changes span all 4 layers (Model → Schema → Service → API). New tables follow existing ORM patterns (UUID PKs, audit timestamps). Data isolation uses loose coupling with service-layer validation (no DB FK constraints per project convention).

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 async + Pydantic v2 | React 18 + TypeScript 5.6

---

### Task 1: Alembic Migration — Bundle All Schema Changes

**Files:**
- Create: `backend/alembic/versions/015_audit_compliance_fixes.py`

- [ ] **Step 1: Write the migration**

```python
"""audit compliance fixes — product_line isolation, cross-module linkages, new tables

Revision ID: 015
Revises: 014_add_version_tables
Create Date: 2026-05-25

Adds:
- product_line_code to audit_programs, audit_plans, gauges, GRR/bias/linearity/stability/attribute studies
- Rename quality_goals.product_line → product_line_code
- sop_ref, spc_chart_id, gauge_id to control_plan_items
- linked_fmea_node_id to spc_alarms
- data_source_formula to quality_goals
- New tables: supplier_ppap_submissions, supplier_ppap_elements, iqc_inspections, supplier_scars, audit_checklist_templates
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '015'
down_revision: Union[str, None] = '014_add_version_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === product_line_code additions ===
    for table in ['audit_programs', 'audit_plans', 'gauges', 'grr_studies',
                   'bias_studies', 'linearity_studies', 'stability_studies', 'attribute_studies']:
        op.add_column(table, sa.Column('product_line_code', sa.VARCHAR(20), nullable=True))
        op.create_index(f'ix_{table}_product_line', table, ['product_line_code'])

    # === quality_goals: rename product_line → product_line_code ===
    op.alter_column('quality_goals', 'product_line', new_column_name='product_line_code')

    # === control_plan_items: cross-module linkage fields ===
    op.add_column('control_plan_items', sa.Column('sop_ref', sa.VARCHAR(100), nullable=True))
    op.add_column('control_plan_items', sa.Column('spc_chart_id', postgresql.UUID(), nullable=True))
    op.add_column('control_plan_items', sa.Column('gauge_id', postgresql.UUID(), nullable=True))
    op.create_foreign_key('fk_cpi_gauge', 'control_plan_items', 'gauges', ['gauge_id'], ['gauge_id'], ondelete='SET NULL')
    op.create_foreign_key('fk_cpi_spc_chart', 'control_plan_items', 'inspection_characteristics', ['spc_chart_id'], ['ic_id'], ondelete='SET NULL')

    # === spc_alarms: FMEA traceability ===
    op.add_column('spc_alarms', sa.Column('linked_fmea_node_id', postgresql.UUID(), nullable=True))

    # === quality_goals: data_source_formula ===
    op.add_column('quality_goals', sa.Column('data_source_formula', sa.VARCHAR(200), nullable=True))

    # === New table: audit_checklist_templates ===
    op.create_table('audit_checklist_templates',
        sa.Column('template_id', postgresql.UUID(), primary_key=True),
        sa.Column('name', sa.VARCHAR(100), nullable=False),
        sa.Column('audit_type', sa.VARCHAR(20), nullable=False),
        sa.Column('items', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('is_default', sa.BOOLEAN(), nullable=False, server_default='false'),
        sa.Column('created_by', postgresql.UUID(), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_act_audit_type', 'audit_checklist_templates', ['audit_type'])

    # === New table: supplier_ppap_submissions ===
    op.create_table('supplier_ppap_submissions',
        sa.Column('submission_id', postgresql.UUID(), primary_key=True),
        sa.Column('supplier_id', postgresql.UUID(), sa.ForeignKey('suppliers.supplier_id', ondelete='CASCADE'), nullable=False),
        sa.Column('part_no', sa.VARCHAR(100), nullable=False),
        sa.Column('part_name', sa.VARCHAR(200), nullable=False),
        sa.Column('submission_level', sa.Integer(), nullable=False),
        sa.Column('submission_date', sa.Date(), nullable=True),
        sa.Column('status', sa.VARCHAR(20), nullable=False, server_default='draft'),
        sa.Column('approved_by', postgresql.UUID(), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(), sa.ForeignKey('users.user_id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_ppap_supplier', 'supplier_ppap_submissions', ['supplier_id'])

    # === New table: supplier_ppap_elements ===
    op.create_table('supplier_ppap_elements',
        sa.Column('element_id', postgresql.UUID(), primary_key=True),
        sa.Column('submission_id', postgresql.UUID(), sa.ForeignKey('supplier_ppap_submissions.submission_id', ondelete='CASCADE'), nullable=False),
        sa.Column('element_no', sa.Integer(), nullable=False),
        sa.Column('element_name', sa.VARCHAR(200), nullable=False),
        sa.Column('status', sa.VARCHAR(20), nullable=False, server_default='pending'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_ppap_elements_submission', 'supplier_ppap_elements', ['submission_id'])

    # === New table: iqc_inspections ===
    op.create_table('iqc_inspections',
        sa.Column('inspection_id', postgresql.UUID(), primary_key=True),
        sa.Column('inspection_no', sa.VARCHAR(50), unique=True, nullable=False),
        sa.Column('supplier_id', postgresql.UUID(), sa.ForeignKey('suppliers.supplier_id', ondelete='CASCADE'), nullable=False),
        sa.Column('part_no', sa.VARCHAR(100), nullable=True),
        sa.Column('part_name', sa.VARCHAR(200), nullable=True),
        sa.Column('lot_no', sa.VARCHAR(50), nullable=True),
        sa.Column('lot_qty', sa.Integer(), nullable=True),
        sa.Column('sample_qty', sa.Integer(), nullable=True),
        sa.Column('inspection_result', sa.VARCHAR(20), nullable=False, server_default='pending'),
        sa.Column('defect_qty', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('defect_description', sa.Text(), nullable=True),
        sa.Column('linked_capa_id', postgresql.UUID(), sa.ForeignKey('capa_eightd.report_id', ondelete='SET NULL'), nullable=True),
        sa.Column('inspection_date', sa.Date(), nullable=True),
        sa.Column('inspected_by', postgresql.UUID(), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_iqc_supplier', 'iqc_inspections', ['supplier_id'])
    op.create_index('ix_iqc_result', 'iqc_inspections', ['inspection_result'])

    # === New table: supplier_scars ===
    op.create_table('supplier_scars',
        sa.Column('scar_id', postgresql.UUID(), primary_key=True),
        sa.Column('scar_no', sa.VARCHAR(50), unique=True, nullable=False),
        sa.Column('supplier_id', postgresql.UUID(), sa.ForeignKey('suppliers.supplier_id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_type', sa.VARCHAR(20), nullable=False),
        sa.Column('source_id', postgresql.UUID(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('requested_action', sa.Text(), nullable=True),
        sa.Column('supplier_response', sa.Text(), nullable=True),
        sa.Column('status', sa.VARCHAR(20), nullable=False, server_default='open'),
        sa.Column('issued_by', postgresql.UUID(), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('issued_date', sa.Date(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('closed_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_scar_supplier', 'supplier_scars', ['supplier_id'])
    op.create_index('ix_scar_status', 'supplier_scars', ['status'])


def downgrade() -> None:
    op.drop_table('supplier_scars')
    op.drop_table('iqc_inspections')
    op.drop_table('supplier_ppap_elements')
    op.drop_table('supplier_ppap_submissions')
    op.drop_table('audit_checklist_templates')

    op.drop_column('quality_goals', 'data_source_formula')
    op.drop_column('spc_alarms', 'linked_fmea_node_id')
    op.drop_constraint('fk_cpi_spc_chart', 'control_plan_items', type_='foreignkey')
    op.drop_constraint('fk_cpi_gauge', 'control_plan_items', type_='foreignkey')
    op.drop_column('control_plan_items', 'gauge_id')
    op.drop_column('control_plan_items', 'spc_chart_id')
    op.drop_column('control_plan_items', 'sop_ref')

    op.alter_column('quality_goals', 'product_line_code', new_column_name='product_line')

    for table in ['attribute_studies', 'stability_studies', 'linearity_studies',
                   'bias_studies', 'grr_studies', 'gauges', 'audit_plans', 'audit_programs']:
        op.drop_index(f'ix_{table}_product_line', table_name=table)
        op.drop_column(table, 'product_line_code')
```

- [ ] **Step 2: Run migration to verify it applies**

Run: `docker compose exec backend alembic upgrade head`
Expected: Migration 015 applied successfully. If there are column name mismatches, fix and re-run.

---

### Task 2: ORM Model Updates — product_line_code Fields

**Files:**
- Modify: `backend/app/models/audit_program.py`
- Modify: `backend/app/models/audit_plan.py`
- Modify: `backend/app/models/gauge.py`
- Modify: `backend/app/models/grr.py`
- Modify: `backend/app/models/bias.py`
- Modify: `backend/app/models/linearity.py`
- Modify: `backend/app/models/stability.py`
- Modify: `backend/app/models/attribute.py`
- Modify: `backend/app/models/quality_goal.py`

- [ ] **Step 1: Add product_line_code to audit models**

In `backend/app/models/audit_program.py`, add:
```python
product_line_code = Column(String(20), nullable=True)
```

In `backend/app/models/audit_plan.py`, add:
```python
product_line_code = Column(String(20), nullable=True)
```

- [ ] **Step 2: Add product_line_code to MSA models**

In `backend/app/models/gauge.py`, add to Gauge class:
```python
product_line_code = Column(String(20), nullable=True)
```

In `backend/app/models/grr.py`, add to GrrStudy class:
```python
product_line_code = Column(String(20), nullable=True)
```

In `backend/app/models/bias.py`, add to BiasStudy class:
```python
product_line_code = Column(String(20), nullable=True)
```

In `backend/app/models/linearity.py`, add to LinearityStudy class:
```python
product_line_code = Column(String(20), nullable=True)
```

In `backend/app/models/stability.py`, add to StabilityStudy class:
```python
product_line_code = Column(String(20), nullable=True)
```

In `backend/app/models/attribute.py`, add to AttributeStudy class:
```python
product_line_code = Column(String(20), nullable=True)
```

- [ ] **Step 3: Rename product_line → product_line_code in QualityGoal**

In `backend/app/models/quality_goal.py`, change:
```python
product_line = Column(String(50), nullable=True)
```
to:
```python
product_line_code = Column(String(50), nullable=True)
```

Also add:
```python
data_source_formula = Column(String(200), nullable=True)
```

- [ ] **Step 4: Verify Python syntax**

Run: `cd backend && python -c "from app.models import *" 2>&1`
Expected: No import errors.

---

### Task 3: ORM Model Updates — Cross-Module Links & New Tables

**Files:**
- Modify: `backend/app/models/control_plan.py`
- Modify: `backend/app/models/spc.py`
- Modify: `backend/app/models/supplier.py`
- Create: `backend/app/models/iqc_inspection.py`

- [ ] **Step 1: Add cross-module fields to ControlPlanItem**

In `backend/app/models/control_plan.py`, add to ControlPlanItem:
```python
sop_ref = Column(String(100), nullable=True)
spc_chart_id = Column(UUID, ForeignKey('inspection_characteristics.ic_id', ondelete='SET NULL'), nullable=True)
gauge_id = Column(UUID, ForeignKey('gauges.gauge_id', ondelete='SET NULL'), nullable=True)
```

- [ ] **Step 2: Add linked_fmea_node_id to SPCAlarm**

In `backend/app/models/spc.py`, add to SPCAlarm:
```python
linked_fmea_node_id = Column(UUID, nullable=True)
```

- [ ] **Step 3: Add PPAP, SCAR models to supplier.py**

Add to `backend/app/models/supplier.py`:

```python
class SupplierPPAPSubmission(Base):
    __tablename__ = 'supplier_ppap_submissions'
    submission_id = Column(UUID, primary_key=True, default=uuid4)
    supplier_id = Column(UUID, ForeignKey('suppliers.supplier_id', ondelete='CASCADE'), nullable=False)
    part_no = Column(String(100), nullable=False)
    part_name = Column(String(200), nullable=False)
    submission_level = Column(Integer, nullable=False)
    submission_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default='draft')
    approved_by = Column(UUID, ForeignKey('users.user_id'), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(UUID, ForeignKey('users.user_id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier = relationship('Supplier', back_populates='ppap_submissions')
    elements = relationship('SupplierPPAPElement', back_populates='submission', cascade='all, delete-orphan')


class SupplierPPAPElement(Base):
    __tablename__ = 'supplier_ppap_elements'
    element_id = Column(UUID, primary_key=True, default=uuid4)
    submission_id = Column(UUID, ForeignKey('supplier_ppap_submissions.submission_id', ondelete='CASCADE'), nullable=False)
    element_no = Column(Integer, nullable=False)
    element_name = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    notes = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)

    submission = relationship('SupplierPPAPSubmission', back_populates='elements')


class SupplierSCAR(Base):
    __tablename__ = 'supplier_scars'
    scar_id = Column(UUID, primary_key=True, default=uuid4)
    scar_no = Column(String(50), unique=True, nullable=False)
    supplier_id = Column(UUID, ForeignKey('suppliers.supplier_id', ondelete='CASCADE'), nullable=False)
    source_type = Column(String(20), nullable=False)
    source_id = Column(UUID, nullable=True)
    description = Column(Text, nullable=False)
    requested_action = Column(Text, nullable=True)
    supplier_response = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default='open')
    issued_by = Column(UUID, ForeignKey('users.user_id'), nullable=True)
    issued_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    closed_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    supplier = relationship('Supplier', back_populates='scars')
```

Add to Supplier class:
```python
ppap_submissions = relationship('SupplierPPAPSubmission', back_populates='supplier', cascade='all, delete-orphan')
scars = relationship('SupplierSCAR', back_populates='supplier', cascade='all, delete-orphan')
```

- [ ] **Step 4: Create IqcInspection model**

Create `backend/app/models/iqc_inspection.py` with the IqcInspection ORM model matching the migration.

- [ ] **Step 5: Create AuditChecklistTemplate model**

In `backend/app/models/audit_program.py` (or new file), add:
```python
class AuditChecklistTemplate(Base):
    __tablename__ = 'audit_checklist_templates'
    template_id = Column(UUID, primary_key=True, default=uuid4)
    name = Column(String(100), nullable=False)
    audit_type = Column(String(20), nullable=False)
    items = Column(JSONB, nullable=False, default=list)
    is_default = Column(Boolean, nullable=False, default=False)
    created_by = Column(UUID, ForeignKey('users.user_id'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 6: Update __init__.py exports**

Add to `backend/app/models/__init__.py`:
```python
from .supplier import SupplierPPAPSubmission, SupplierPPAPElement, SupplierSCAR
from .iqc_inspection import IqcInspection
from .audit_program import AuditChecklistTemplate  # or wherever it lives
```

- [ ] **Step 7: Verify**

Run: `cd backend && python -c "from app.models import *; print('OK')"`

---

### Task 4: Schema Layer — Update Pydantic Schemas

**Files:**
- Modify: `backend/app/schemas/quality_goal.py`
- Modify: `backend/app/schemas/spc.py`
- Modify: `backend/app/schemas/control_plan.py`
- Modify: `backend/app/schemas/supplier.py`
- Modify: `backend/app/schemas/audit.py`

- [ ] **Step 1: Rename product_line → product_line_code in QualityGoal schemas**

Find and replace all `product_line` with `product_line_code` in quality_goal.py. Add `data_source_formula: str | None = None`.

- [ ] **Step 2: Add linked_fmea_node_id to SPCAlarm schemas**

Add `linked_fmea_node_id: str | None = None` to SPCAalarmCreate and SPCAalarmResponse.

- [ ] **Step 3: Add new fields to ControlPlanItem schemas**

Add `sop_ref: str | None`, `spc_chart_id: str | None`, `gauge_id: str | None` to ControlPlanItemCreate/Update/Response.

- [ ] **Step 4: Add PPAP, IQC, SCAR, AuditChecklistTemplate schemas**

Add new Pydantic models for each new table (Create, Update, Response variants).

- [ ] **Step 5: Verify**

Run: `cd backend && python -c "from app.schemas import *; print('OK')"`

---

### Task 5: Service Layer — Validation & Cross-Module Integrity

**Files:**
- Modify: `backend/app/services/product_line_service.py`
- Modify: `backend/app/services/audit_service.py`
- Modify: `backend/app/services/spc_service.py`

- [ ] **Step 1: Add downstream reference check to product_line delete**

In `product_line_service.py`, add to `delete_product_line`:
```python
async def delete_product_line(db: AsyncSession, code: str) -> dict:
    # Check downstream references before soft-deleting
    references = {}
    tables_to_check = [
        ('fmea_documents', 'product_line_code', "status != 'archived'"),
        ('capa_eightd', 'product_line_code', "status != 'closed'"),
        ('control_plans', 'product_line_code', "status != 'archived'"),
        ('inspection_characteristics', 'product_line', 'is_active = true'),
        ('special_characteristics', 'product_line_code', "status = 'active'"),
        ('quality_goals', 'product_line_code', "status = 'active'"),
    ]
    for table, col, status_filter in tables_to_check:
        result = await db.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {col} = :code AND {status_filter}"),
            {'code': code}
        )
        count = result.scalar()
        if count > 0:
            references[table] = count

    if references:
        raise ValueError(f"产品线 {code} 仍被 {len(references)} 个模块引用，无法停用: {references}")

    # existing soft-delete logic...
```

- [ ] **Step 2: Add auditor qualification check**

In `audit_service.py`, when assigning lead_auditor or team_members:
```python
# Check qualification validity
from datetime import date, datetime
result = await db.execute(
    select(User).where(User.user_id == auditor_id)
)
user = result.scalar_one_or_none()
if user and user.auditor_info and user.auditor_info.get('last_qualification_date'):
    qual_date = datetime.fromisoformat(user.auditor_info['last_qualification_date']).date()
    if (date.today() - qual_date).days > 365:
        raise ValueError("审核员资格已过期，请先完成资格再评审")
```

- [ ] **Step 3: Add change_reason requirement to SPC control limit activation**

Add `change_reason: str` parameter to `activate_control_limit_snapshot()`. Create AuditLog entry with `action='activate_control_limit'`.

---

### Task 6: Frontend — TypeScript Type Updates

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Rename product_line → product_line_code in QualityGoal**

Change `product_line: string | null` to `product_line_code: string | null`. Add `data_source_formula?: string`.

- [ ] **Step 2: Add new interfaces**

```typescript
interface PPAPSubmission {
  submission_id: string;
  supplier_id: string;
  part_no: string;
  part_name: string;
  submission_level: number;
  submission_date: string | null;
  status: 'draft' | 'submitted' | 'approved' | 'rejected';
  approved_by: string | null;
  approved_at: string | null;
  notes: string | null;
  elements: PPAPElement[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

interface PPAPElement {
  element_id: string;
  submission_id: string;
  element_no: number;
  element_name: string;
  status: 'pending' | 'submitted' | 'approved' | 'rejected';
  notes: string | null;
  sort_order: number;
}

interface IqcInspection {
  inspection_id: string;
  inspection_no: string;
  supplier_id: string;
  part_no: string | null;
  part_name: string | null;
  lot_no: string | null;
  lot_qty: number | null;
  sample_qty: number | null;
  inspection_result: 'pending' | 'accepted' | 'rejected' | 'concession';
  defect_qty: number;
  defect_description: string | null;
  linked_capa_id: string | null;
  inspection_date: string | null;
  inspected_by: string | null;
}

interface SupplierSCAR {
  scar_id: string;
  scar_no: string;
  supplier_id: string;
  source_type: 'iqc_reject' | 'audit_finding' | 'customer_complaint' | 'other';
  source_id: string | null;
  description: string;
  requested_action: string | null;
  supplier_response: string | null;
  status: 'open' | 'supplier_responded' | 'closed';
  issued_by: string | null;
  issued_date: string | null;
  due_date: string | null;
  closed_date: string | null;
}

interface AuditChecklistTemplate {
  template_id: string;
  name: string;
  audit_type: 'system' | 'process' | 'product';
  items: AuditChecklistItem[];
  is_default: boolean;
  created_by: string | null;
  created_at: string;
}
```

- [ ] **Step 3: Add new fields to ControlPlanItem**

Add to ControlPlanItem:
```typescript
sop_ref?: string;
spc_chart_id?: string;
gauge_id?: string;
```

- [ ] **Step 4: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`

---

### Task 7: Integration — Wire Up & Verify

- [ ] **Step 1: Run backend syntax check**

Run: `cd backend && python -c "from app.main import app; print('Backend OK')"`

- [ ] **Step 2: Run frontend build check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -20`

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "fix: implement 30 audit compliance fixes across 12 modules

- Add product_line_code to 8 tables (audit, MSA, quality goals)
- Create new tables: PPAP submissions/elements, IQC inspections, SCARs, checklist templates
- Add cross-module linkage fields (ControlPlanItem, SPCAlarm)
- Add product line deletion safety check
- Add auditor qualification validation
- Add change_reason to SPC control limit activation"
```
